"""Prepare source-bound paired perturbations, without accepting challenge labels."""
from __future__ import annotations

import copy
import re

from src.data.clause_splitter import Chunk
from src.generation.comparison import (COMMON_PROMPT, GENERIC_CONSTRAINT, ROLE_CONSTRAINT,
    MODES, _pack_context, canonical_sha256, public_question, text_sha256)

KINDS = ('missing_company_evidence', 'remove_key_regulation_candidate',
         'near_topic_nonsupport_candidate', 'wrong_version_candidate',
         'conflicting_evidence_candidate', 'no_evidence_candidate')
RECORD_FIELDS = {'evidence_id', 'chunk_id', 'doc_id', 'document_title', 'doc_type',
                 'source', 'clause_no', 'text', 'score', 'meta'}


def record_chunk(record):
    if not isinstance(record, dict) or set(record) != RECORD_FIELDS:
        raise ValueError('Evidence records must use the public source-record schema')
    if not isinstance(record['meta'], dict):
        raise ValueError('Evidence metadata must be an object')
    role = record['meta'].get('corpus_type')
    if role not in {'annual_report', 'regulation'} or record['doc_type'] != role:
        raise ValueError('Evidence role and document type must match')
    if not re.fullmatch(r'[AR][1-9]\d*', record['evidence_id']) or \
            record['evidence_id'][0] != ('A' if role == 'annual_report' else 'R'):
        raise ValueError('Evidence ID must match its source role')
    return Chunk(chunk_id=record['chunk_id'], doc_id=record['doc_id'],
        doc_title=record['document_title'], doc_type=record['doc_type'], source=record['source'],
        clause_no=record['clause_no'], text=record['text'], meta=copy.deepcopy(record['meta']))


def prepare_pairs(bundle, specs, candidates, count_tokens, verify_records):
    """Rebuild contexts, enforce exact perturbations, and verify every source.

    verify_records is required, including for engineering controls. It must bind
    records to original bytes/coordinates; it must not supply semantic labels.
    Challenge types, notes and expected judgments never enter model prompts.
    """
    question = public_question(bundle['question'])
    context = bundle['contexts']['dual']
    if text_sha256(context['context']) != context['context_sha256'] or \
            canonical_sha256(context['source_records']) != context['source_records_sha256']:
        raise ValueError('Unperturbed context or source hash mismatch')
    cap = bundle['budget']['max_reference_context_tokens']
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        raise ValueError('Reference token budget must be a positive integer')
    original = copy.deepcopy(context['source_records'])
    ids = [r['evidence_id'] for r in original]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Unperturbed context needs unique source IDs')
    by_id = dict(zip(ids, original))
    if not any(i.startswith('A') for i in ids) or not any(i.startswith('R') for i in ids):
        raise ValueError('Paired dual-source controls require both source roles')

    def pack(records):
        chunks = [record_chunk(r) for r in records]
        packed = _pack_context(list(zip(chunks, [r['score'] for r in records])), count_tokens, cap)
        if packed['omitted_candidates']:
            raise ValueError('Perturbation exceeds the unchanged whole-chunk context budget')
        bindings = verify_records(copy.deepcopy(packed['source_records']))
        if not isinstance(bindings, list) or len(bindings) != len(packed['source_records']):
            raise ValueError('Source verification must return one binding per evidence record')
        prompts = {}
        for mode, constraint in [(MODES[2], GENERIC_CONSTRAINT), (MODES[3], ROLE_CONSTRAINT)]:
            prompt = COMMON_PROMPT.format(**question, context=packed['context'], constraint=constraint)
            prompts[mode] = {'context_key': 'dual', 'prompt': prompt,
                            'prompt_sha256': text_sha256(prompt), 'prompt_reference_tokens': count_tokens(prompt)}
        return {'question': copy.deepcopy(question), 'budget': copy.deepcopy(bundle['budget']),
                'contexts': {'dual': packed}, 'modes': prompts}, bindings

    baseline, bound = pack(original)
    if baseline['contexts']['dual']['context'] != context['context'] or \
            baseline['contexts']['dual']['source_records'] != original:
        raise ValueError('Unperturbed context must reconstruct byte for byte')
    seen, variants = set(), []
    if not isinstance(specs, list) or not specs:
        raise ValueError('At least one explicit perturbation specification is required')
    for spec in specs:
        if not isinstance(spec, dict) or set(spec) != {'case_id', 'kind', 'remove_ids', 'add_candidate_ids'}:
            raise ValueError('Perturbation specifications have an explicit four-field schema')
        case_id, kind = spec['case_id'], spec['kind']
        if not isinstance(case_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', case_id) or \
                case_id in seen or case_id == 'unperturbed' or kind not in KINDS:
            raise ValueError('Unique safe case IDs and supported candidate kinds are required')
        seen.add(case_id)
        remove, adds = spec['remove_ids'], spec['add_candidate_ids']
        for values in (remove, adds):
            if not isinstance(values, list) or any(not isinstance(x, str) for x in values) or len(values) != len(set(values)):
                raise ValueError('Removal and insertion IDs must be unique string lists')
        if not set(remove) <= set(ids) or not set(adds) <= set(candidates):
            raise ValueError('Unknown original evidence or candidate source')
        incoming = [copy.deepcopy(candidates[key]) for key in adds]
        for row in incoming:
            record_chunk(row)
        annual_ids = {i for i in ids if i.startswith('A')}
        if kind == KINDS[0] and (set(remove) != annual_ids or adds):
            raise ValueError('Missing-company control removes exactly all annual evidence')
        if kind == KINDS[1] and (not remove or any(not i.startswith('R') for i in remove) or adds):
            raise ValueError('Regulation removal needs explicit regulation IDs only')
        if kind in KINDS[2:4] and (len(remove) != 1 or not remove[0].startswith('R') or len(incoming) != 1 or
                                  incoming[0]['meta']['corpus_type'] != 'regulation'):
            raise ValueError('Rule replacement needs one removed and one inserted regulation source')
        if kind == KINDS[3]:
            prior, later = by_id[remove[0]], incoming[0]
            if not prior['clause_no'] or prior['clause_no'] != later['clause_no'] or \
                    prior['doc_id'] != later['doc_id'] or \
                    not prior['meta'].get('source_document_sha256') or \
                    prior['meta']['source_document_sha256'] == later['meta'].get('source_document_sha256'):
                raise ValueError('Version candidate needs the same declared rule/clause and different source bytes')
        if kind == KINDS[4] and (remove or not adds):
            raise ValueError('Conflict candidates append sources without removing originals')
        if kind == KINDS[5] and (set(remove) != set(ids) or adds):
            raise ValueError('No-evidence control removes all evidence without replacements')
        records, origins = [], []
        replacement = kind in KINDS[2:4]
        for row in original:
            if row['evidence_id'] not in remove:
                records.append(row)
                origins.append({'original_id': row['evidence_id'], 'candidate_id': None})
            elif replacement:
                records.append(incoming[0])
                origins.append({'original_id': None, 'candidate_id': adds[0]})
        if not replacement:
            records.extend(incoming)
            origins.extend({'original_id': None, 'candidate_id': key} for key in adds)
        chunk_ids = [r['chunk_id'] for r in records]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError('A perturbation may not duplicate a source chunk')
        if incoming and canonical_sha256([record_chunk(r).__dict__ for r in incoming]) == \
                canonical_sha256([record_chunk(by_id[i]).__dict__ for i in remove]):
            raise ValueError('Replacement must change the actual source record')
        payload, bindings = pack(records)
        packed_records = payload['contexts']['dual']['source_records']
        mapping = [{**origin,
                    'chunk_id': old['chunk_id'], 'variant_evidence_id': new['evidence_id']}
                   for origin, old, new in zip(origins, records, packed_records)]
        variants.append({'case_id': case_id, 'proposed_kind': kind, 'operation': copy.deepcopy(spec),
            'payload': payload, 'source_bindings': bindings, 'evidence_id_mapping': mapping,
            'payload_sha256': canonical_sha256(payload), 'expected_answerability': None,
            'expected_support_or_applicability': None, 'challenge_label_independently_reviewed': False})
    return {'schema_version': 'fixed-context-robustness-pairs-v1',
        'purpose': 'source-bound development preparation;not an accepted challenge set',
        'question': question, 'unperturbed': {'payload': baseline, 'source_bindings': bound,
            'payload_sha256': canonical_sha256(baseline), 'quality_or_answerability_accepted': False},
        'variants': variants, 'same_public_question_across_all_cases': True,
        'same_reference_token_cap': cap, 'candidate_type_labels_enter_prompts': False,
        'source_IDs_reassigned_per_context_with_coordinator_mapping': True,
        'variants_are_not_independent_questions': True, 'new_generation_API_calls': 0,
        'accepted_challenge_cases': 0, 'formal_metrics': None}
