"""Candidate selection using explicit query dates and declared version intervals.

This is interval arithmetic, conditional on upstream metadata. It does not accept
legal applicability, reviewer identity, source identity or event dates as facts.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from src.data.declared_time import bind_public_target_date, declared_interval_relation


def select_temporal_candidates(chunks, query: str, *, target_date=None,
                               target_date_role=None, unknown_policy='retain'):
    """Return chunk IDs to scope retrieval before any top-k truncation."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError('Temporal scope requires the actual nonempty public query')
    if unknown_policy not in {'retain', 'exclude'}:
        raise ValueError('unknown_policy must be retain or exclude')
    payload = {'question': {'query': query}}
    bind_public_target_date(payload, target_date, role=target_date_role)
    chunks = list(chunks)
    ids = [c.chunk_id for c in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError('Temporal input contains duplicate chunk IDs')
    signatures = defaultdict(set)
    fields = ('applicability_status', 'effective_from', 'effective_to_exclusive',
              'interval_end_status', 'metadata_as_of_date')
    for chunk in chunks:
        meta = chunk.meta
        if chunk.doc_type != 'regulation' or meta.get('corpus_type') != 'regulation':
            raise ValueError('Temporal selection may only scope regulation chunks')
        digest, version = meta.get('source_document_sha256'), meta.get('version_id')
        if isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest) and \
                isinstance(version, str) and version.strip() and meta.get('applicability_status') == 'version_interval_confirmed':
            signatures[(digest, version)].add(tuple(repr(meta.get(k)) for k in fields))
    conflicts = {key for key, values in signatures.items() if len(values) > 1}
    allowed, rows = set(), []
    for chunk in chunks:
        meta = chunk.meta; digest = meta.get('source_document_sha256');version = meta.get('version_id')
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            result = {'relation': 'unknown', 'reason': 'source_document_sha256_missing_or_invalid'}
        elif isinstance(version, str) and (digest, version) in conflicts:
            result = {'relation': 'unknown', 'reason': 'conflicting_declared_version_intervals'}
        else:
            result = declared_interval_relation({'meta': meta}, target_date)
        relation = result['relation']
        keep = relation == 'within_declared_interval' or relation == 'unknown' and unknown_policy == 'retain'
        if keep: allowed.add(chunk.chunk_id)
        rows.append({'chunk_id': chunk.chunk_id, 'doc_id': chunk.doc_id, 'source_document_sha256': digest,
                     'version_id': version, 'relation': relation, 'reason': result['reason'], 'retained': keep})
    counts = Counter(r['relation'] for r in rows)
    return allowed, {'target_date': target_date,
        'target_date_role': target_date_role,
        'target_date_basis': payload.get('target_date_basis', 'not_supplied_no_date_inferred'),
        'unknown_policy': unknown_policy, 'input_regulation_chunks': len(chunks), 'retained_chunks': len(allowed),
        'relation_counts': dict(counts), 'excluded_outside_declared_interval': sum(r['relation'] == 'outside_declared_interval' for r in rows),
        'excluded_unknown_by_explicit_policy': sum(r['relation'] == 'unknown' and not r['retained'] for r in rows),
        'rows': rows, 'applied_before_top_k': True, 'source_metadata_reverified_here': False,
        'event_date_independently_verified': False, 'legal_applicability_verified': False,
        'formal_time_evaluation_eligible_subset_verified': False}
