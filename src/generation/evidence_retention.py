"""Adapt packed retrieval contexts to the existing append-only supplement policy.

This module performs no search, inference, file reads or source adjudication.
It checks the supplied metadata and delegates packing and stable-ID allocation
to ``supplementary_retrieval.extend_context``. A valid file-digest field does
not independently verify the file or establish semantic support.
"""
from __future__ import annotations

import copy
import math
import re
from collections import Counter
from typing import Callable

from src.generation.comparison import canonical_sha256
from src.generation.supplementary_retrieval import (
    ROLES, extend_context, reference_count, split_blocks, validate_context,
)


def _validate_initial_sources(question: dict, context: dict) -> None:
    """Apply the supplement's scope/digest requirements to retained sources too."""
    for record, block in zip(context['source_records'], split_blocks(context)):
        meta = record.get('meta')
        if not isinstance(meta, dict):
            raise ValueError('Initial evidence requires source metadata')
        role = meta.get('corpus_type')
        if role not in ROLES or str(meta.get('system_corpus_input', '')).lower() == 'false':
            raise ValueError('Initial evidence has an unsupported or reviewer-only source')
        expected_prefix = 'A' if role == 'annual_report' else 'R'
        if not record['evidence_id'].startswith(expected_prefix):
            raise ValueError('Initial source role disagrees with its evidence ID')
        if role == 'annual_report' and (
                str(meta.get('stock_code', '')).upper() != str(question['stock_code']).upper()
                or meta.get('report_year') != question['report_year']):
            raise ValueError('Initial annual evidence is outside the question company/year')
        digest = meta.get('source_pdf_sha256' if role == 'annual_report'
                          else 'source_document_sha256', '')
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
            raise ValueError('Initial evidence requires an original file SHA256')
        try:
            finite_score = math.isfinite(float(record['score']))
        except (KeyError, TypeError, ValueError, OverflowError):
            finite_score = False
        if not finite_score:
            raise ValueError('Initial evidence requires a finite retrieval score')
        if not isinstance(record.get('text'), str) or record['text'] not in block:
            raise ValueError('Initial source text is not bound to its own evidence block')


def extend_retained_context(
        question: dict, context: dict, hits: list,
        counter: Callable[[str], int], *, max_context_tokens: int = 6000,
        max_new_sources: int = 8) -> tuple[dict, dict]:
    """Return a new packed context and audit without changing any input.

    ``context`` is the result of ``comparison._pack_context``. Legacy contexts
    may omit ``source_records_sha256``; only that absent hash is calculated on
    a private copy. An existing wrong hash is rejected, never repaired. The
    supplied counter must be the same reference-token policy used to pack the
    original context. Annual evidence must match the public company/year;
    original file-digest metadata is required for both source roles.

    The original text, IDs and source records remain intact. New hits that do
    not fit are omitted as whole chunks under the existing supplement policy.
    Original retrieval/omission fields remain the initial packing provenance;
    added/omitted supplemental hits are reported by the returned audit.
    An empty initial context may be audited without hits. Adding its first
    source is rejected: the delegated append-only serializer expects an
    existing block and otherwise emits an unbound leading separator. Call
    ``_pack_context`` for that initial retrieval rather than treating it as a
    supplement.
    """
    if not isinstance(question, dict) or not isinstance(context, dict):
        raise ValueError('Question and packed context must be dictionaries')
    if not isinstance(question.get('stock_code'), str) or not question['stock_code'].strip():
        raise ValueError('Question requires a nonempty stock_code')
    if type(question.get('report_year')) is not int or question['report_year'] < 1:
        raise ValueError('Question requires an integer report_year')
    if not isinstance(context.get('context'), str) or not isinstance(context.get('source_records'), list):
        raise ValueError('Packed context requires text and source_records')
    if any(not isinstance(row, dict) for row in context['source_records']):
        raise ValueError('Packed source records must be dictionaries')
    if not isinstance(hits, list):
        raise ValueError('Supplemental retrieval hits must be a list')
    if not callable(counter):
        raise ValueError('A reference token counter is required')
    if not context['context'] and hits:
        raise ValueError('Initial retrieval into an empty context must use _pack_context')

    prepared = copy.deepcopy(context)
    hash_added = 'source_records_sha256' not in prepared
    if hash_added:
        prepared['source_records_sha256'] = canonical_sha256(prepared['source_records'])
    validate_context(prepared)
    initial_tokens = reference_count(counter, prepared['context'])
    if 'reference_tokens' in prepared and (
            type(prepared['reference_tokens']) is not int
            or prepared['reference_tokens'] != initial_tokens):
        raise ValueError('Initial reference_tokens differs from the supplied counter')
    _validate_initial_sources(question, prepared)
    # The existing supplement expects a prompt containing the old text exactly
    # once. The text itself satisfies this contract (also for an empty no-op);
    # this placeholder is not used for inference or returned to the caller.
    payload = {'question': {'stock_code': question['stock_code'],
                            'report_year': question['report_year']},
               'context': prepared, 'generic_prompt': prepared['context']}
    updated, audit = extend_context(
        payload, hits, counter, max_context_tokens=max_context_tokens,
        max_new_sources=max_new_sources)
    result = updated['context']
    reasons = Counter(row['reason'] for row in audit['omitted'])
    accepted_count = len(audit['accepted'])
    if accepted_count:
        outcome = 'evidence_added'
    elif not hits:
        outcome = 'no_hits'
    elif reasons.get('reference_token_cap_no_truncation'):
        outcome = 'token_budget_blocked'
    elif reasons.get('duplicate_chunk_id') == len(hits):
        outcome = 'duplicates_only'
    else:
        outcome = 'no_new_evidence'
    audit.update(
        policy='existing_append_only_supplement', outcome=outcome,
        initial_reference_tokens=initial_tokens,
        final_reference_tokens=result['reference_tokens'],
        initial_source_count=len(prepared['source_records']),
        final_source_count=len(result['source_records']),
        accepted_count=accepted_count, omitted_count=len(audit['omitted']),
        omitted_reason_counts=dict(reasons), no_new_evidence=accepted_count == 0,
        budget_blocked=bool(reasons.get('reference_token_cap_no_truncation')),
        token_budget_exhausted=result['reference_tokens'] == max_context_tokens,
        within_token_budget=result['reference_tokens'] <= max_context_tokens,
        new_source_limit_reached=accepted_count == max_new_sources,
        initial_source_records_sha256=prepared['source_records_sha256'],
        source_records_hash_added=hash_added, source_files_reverified=False,
        source_hash_metadata_checked=True)
    return result, audit
