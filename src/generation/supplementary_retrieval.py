"""One-shot supplemental retrieval with stable local citations and whole chunks.

Role/citation gaps are not semantic gold. The callback must search a verified
index; source eligibility and quote correctness still need separate audits.
"""
from __future__ import annotations

import copy
import math
import re

from src.data.document_corpora import DualCorpusRetriever
from src.retrieval.temporal import select_temporal_candidates
from src.generation.comparison import _source_record, canonical_sha256, text_sha256

GENERIC_RETRIEVE_MODE = 'generic_verify_retrieve_revise_v1'
JOINT_RETRIEVE_MODE = 'joint_role_verify_retrieve_revise_v1'
RETRIEVAL_METHODS = (GENERIC_RETRIEVE_MODE, JOINT_RETRIEVE_MODE)
ROLES = ('annual_report', 'regulation')


def reference_count(counter, text):
    value = counter(text)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError('Reference token counter must return a nonnegative integer')
    return value


def validate_context(context):
    if text_sha256(context['context']) != context['context_sha256'] or \
            canonical_sha256(context['source_records']) != context['source_records_sha256']:
        raise ValueError('Context or source records changed')
    ids = [row['evidence_id'] for row in context['source_records']]
    chunks = [row.get('chunk_id') for row in context['source_records']]
    if len(ids) != len(set(ids)) or len(chunks) != len(set(chunks)) or any(not isinstance(x, str) or not x for x in chunks):
        raise ValueError('Stable source IDs require unique original chunk IDs')
    headers = re.findall(r'^\[([AR][1-9]\d*)\]', context['context'], re.MULTILINE)
    if headers != ids:
        raise ValueError('Context header order must equal source record order')


def split_blocks(context):
    """Remove only the two separator LFs, preserving source boundary whitespace."""
    validate_context(context)
    text = context['context']
    matches = list(re.finditer(r'^\[([AR][1-9]\d*)\]', text, re.MULTILINE))
    blocks = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        if i + 1 < len(matches):
            if text[end - 2:end] != '\n\n':
                raise ValueError('Context block separator is not the recorded format')
            end -= 2
        blocks.append(text[match.start():end])
    if '\n\n'.join(blocks) != text:
        raise ValueError('Context blocks cannot be reconstructed exactly')
    return blocks


def plan_supplement(payload: dict, checks: dict, *, joint: bool) -> dict:
    available = {row.get('meta', {}).get('corpus_type') for row in payload['context']['source_records']}
    wanted = {role for row in checks['checks'] for role in row.get('missing_source_roles', [])} if joint else set()
    absent = wanted - available
    negatives = [row for row in checks['checks'] if row['verdict'] != 'supported']
    if absent:
        roles, reason = sorted(absent), 'required_role_absent_from_context'
    elif negatives:
        roles, reason = list(ROLES), 'model_reports_insufficient_or_conflicting_support'
    elif joint and payload.get('declared_target_date') and any(
            'application_date_or_version_metadata_unknown' in row.get('guard_issues', []) for row in checks['checks']):
        roles, reason = ['regulation'], 'version_metadata_gap_with_explicit_target_date'
    else:
        reason = ('role_available_but_uncited_revision_only' if wanted else
                  'unknown_target_date_not_inferred_by_search' if joint and any(
                      'application_date_or_version_metadata_unknown' in row.get('guard_issues', []) for row in checks['checks'])
                  else 'no_searchable_gap_identified')
        return {'search_needed': False, 'reason': reason, 'roles': []}
    if any(role not in ROLES for role in roles):
        raise ValueError('Supplemental role must be annual_report or regulation')
    fragments = [row['text'][:200] for row in checks['checks'] if row['verdict'] != 'supported'
                 or set(row.get('missing_source_roles', [])) & absent][:2]
    query = payload['question']['query'][:1200]
    if fragments:
        query += '\n待补充依据的正文片段：\n' + '\n'.join(fragments)
    validate_context(payload['context'])
    return {'search_needed': True, 'reason': reason, 'roles': roles, 'query': query,
        'question_id': payload['question']['question_id'], 'stock_code': payload['question']['stock_code'],
        'report_year': payload['question']['report_year'],
        'declared_target_date': payload.get('declared_target_date'),
        'declared_target_date_role': payload.get('declared_target_date_role'),
        'semantic_gap_verified': False,
        'exclude_chunk_ids': [row['chunk_id'] for row in payload['context']['source_records']]}


def extend_context(payload: dict, hits: list, counter, *, max_context_tokens: int,
                   max_new_sources: int) -> tuple[dict, dict]:
    if not isinstance(max_context_tokens, int) or isinstance(max_context_tokens, bool) or max_context_tokens < 1:
        raise ValueError('Context token cap must be positive')
    if not isinstance(max_new_sources, int) or isinstance(max_new_sources, bool) or not 1 <= max_new_sources <= 8:
        raise ValueError('Supplemental source cap must be in [1,8]')
    original = payload['context']
    validate_context(original)
    if reference_count(counter, original['context']) > max_context_tokens:
        raise ValueError('Original context already exceeds the declared reference cap')
    updated = copy.deepcopy(payload)
    context = updated['context']
    seen = {row['chunk_id'] for row in original['source_records']}
    counts = {prefix: max([int(row['evidence_id'][1:]) for row in original['source_records']
                         if row['evidence_id'].startswith(prefix)], default=0) for prefix in ('A', 'R')}
    accepted, omitted = [], []
    for chunk, score in hits:
        role = chunk.meta.get('corpus_type')
        if role not in ROLES or str(chunk.meta.get('system_corpus_input', '')).lower() == 'false':
            raise ValueError('Supplement returned an unsupported or reviewer-only source')
        if role == 'annual_report' and (str(chunk.meta.get('stock_code', '')).upper() !=
                str(payload['question']['stock_code']).upper() or chunk.meta.get('report_year') != payload['question']['report_year']):
            raise ValueError('Supplement returned annual evidence outside the question company/year')
        digest = chunk.meta.get('source_pdf_sha256' if role == 'annual_report' else 'source_document_sha256', '')
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest) or not math.isfinite(float(score)):
            raise ValueError('Supplement requires original file SHA256 and finite retrieval scores')
        if chunk.chunk_id in seen:
            omitted.append({'chunk_id': chunk.chunk_id, 'reason': 'duplicate_chunk_id'})
            continue
        if len(accepted) >= max_new_sources:
            omitted.append({'chunk_id': chunk.chunk_id, 'reason': 'new_source_cap'})
            continue
        prefix = 'A' if role == 'annual_report' else 'R'
        evidence_id = prefix + str(counts[prefix] + 1)
        block = DualCorpusRetriever.format_evidence([(chunk, score)], prefix=prefix)
        if not block.startswith('[' + prefix + '1]'):
            raise ValueError('Unexpected evidence header serialization')
        block = '[' + evidence_id + ']' + block[len(prefix) + 3:]
        candidate = context['context'] + '\n\n' + block
        if reference_count(counter, candidate) > max_context_tokens:
            omitted.append({'chunk_id': chunk.chunk_id, 'reason': 'reference_token_cap_no_truncation'})
            continue
        context['context'] = candidate
        record = _source_record(chunk, float(score), evidence_id)
        context['source_records'].append(record)
        counts[prefix] += 1
        seen.add(chunk.chunk_id)
        accepted.append({'chunk_id': chunk.chunk_id, 'evidence_id': evidence_id})
    context.update(context_sha256=text_sha256(context['context']),
        source_records_sha256=canonical_sha256(context['source_records']),
        reference_tokens=reference_count(counter, context['context']))
    old = original['context']
    if payload['generic_prompt'].count(old) != 1:
        raise ValueError('Generic prompt must contain the original context exactly once')
    for prompt_name in ('generic_prompt', 'attribution_prompt'):
        if prompt_name in payload:
            if payload[prompt_name].count(old) != 1:
                raise ValueError('Each stored prompt must contain the original context exactly once')
            updated[prompt_name] = payload[prompt_name].replace(old, context['context'], 1)
            updated[prompt_name + '_sha256'] = text_sha256(updated[prompt_name])
    validate_context(context)
    assert context['source_records'][:len(original['source_records'])] == original['source_records']
    return updated, {'accepted': accepted, 'omitted': omitted, 'parent_context_sha256': original['context_sha256'],
        'context_sha256': context['context_sha256'], 'source_records_sha256': context['source_records_sha256'],
        'max_context_tokens': max_context_tokens, 'reference_tokens': context['reference_tokens'],
        'max_new_sources': max_new_sources, 'old_ids_and_source_records_preserved': True,
        'old_context_is_unchanged_prefix': context['context'].startswith(old), 'semantic_support_verified': False}


class ScopedSupplementRetriever:
    """A callable over an already verified dual index; at most two scoped searches."""
    def __init__(self, dual):
        self.dual = dual
        self.calls = []

    def __call__(self, request: dict):
        roles, limit = request['roles'], request['max_new_sources']
        if not roles or len(set(roles)) != len(roles) or any(role not in ROLES for role in roles) or limit < len(roles):
            raise ValueError('Requested roles must fit the explicit supplemental source quota')
        excluded = request.get('exclude_chunk_ids', [])
        if not isinstance(excluded, list) or any(not isinstance(cid, str) or not cid for cid in excluded) \
                or len(excluded) != len(set(excluded)):
            raise ValueError('Excluded chunk IDs must be a unique list of original index IDs')
        excluded = set(excluded)
        known = {chunk.chunk_id for chunk in self.dual.annual_chunks + self.dual.regulation_chunks}
        if not excluded <= known:
            raise ValueError('Excluded chunk IDs are absent from the verified index')
        ordered = [role for role in ROLES if role in roles]
        hits, quotas = [], {}
        for index, role in enumerate(ordered):
            quota = limit // len(ordered) + (index < limit % len(ordered))
            pool = self.dual.annual_chunks if role == 'annual_report' else self.dual.regulation_chunks
            temporal_audit = None
            if role == 'regulation':
                eligible_ids, temporal_audit = select_temporal_candidates(
                    pool, request['query'], target_date=request.get('declared_target_date'),
                    target_date_role=request.get('declared_target_date_role'),
                    unknown_policy='retain')
                pool = [chunk for chunk in pool if chunk.chunk_id in eligible_ids]
            if role == 'annual_report':
                pool = [chunk for chunk in pool if str(chunk.meta.get('stock_code', '')).upper() ==
                    str(request['stock_code']).upper() and chunk.meta.get('report_year') == request['report_year']]
            before_exclusion = len(pool)
            pool = [chunk for chunk in pool if chunk.chunk_id not in excluded]
            quotas[role] = {'top_k': quota, 'eligible_chunks_before_exclusion': before_exclusion,
                'excluded_already_provided': before_exclusion - len(pool), 'eligible_chunks': len(pool),
                'skipped_empty_pool': not pool, 'temporal_scope_audit': temporal_audit}
            # Never pass an empty pool to a backend that might treat it as global.
            found = self.dual.retriever.search(request['query'], top_k=quota, pool=pool) if pool else []
            allowed = {chunk.chunk_id: chunk for chunk in pool}
            if len(found) > quota or any(chunk.chunk_id not in allowed for chunk, _ in found):
                raise ValueError('Scoped retriever returned candidates outside its index scope/quota')
            if any(canonical_sha256(_source_record(chunk, 0.0, 'source')) !=
                   canonical_sha256(_source_record(allowed[chunk.chunk_id], 0.0, 'source')) for chunk, _ in found):
                raise ValueError('Returned source content disagrees with its verified index chunk')
            hits.extend(found)
        self.calls.append({'roles': ordered, 'quotas': quotas, 'exclude_chunk_ids': sorted(excluded),
            'exclusion_policy': 'provided_original_chunk_ids_before_candidate_search',
            'returned_chunk_ids': [chunk.chunk_id for chunk, _ in hits]})
        return hits
