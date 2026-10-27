"""Deterministic, label-free allocation of whole table and neighbor evidence.

Boundary cues are scheduling heuristics, never proof of relevance or truth.
The immutable initial context is retained; no new query, truncation or model is
used. Actual PDF/adjacency verification belongs to the frozen source indexes.
"""
from __future__ import annotations

import copy
import math
import re
from itertools import zip_longest

from src.generation.comparison import canonical_sha256, _source_record
from src.generation.evidence_retention import extend_retained_context
from src.retrieval.annual_table_index import verify_field_views

POLICIES = ('initial', 'table_first', 'adjacent_first', 'boundary_first', 'boundary_round_robin')
WINDOW = re.compile(r'HELD-(\d{6})-(\d{4})-P([1-9]\d*)-S(0|[1-9]\d*)\Z')


def boundary_cues(text):
    """Use only the seed's literal suffix; a complete closed date has no cue."""
    tail = re.sub(r'\s+', '', text.rstrip()[-120:])
    cues = []
    if re.search(r'[（(]\d{1,2}月\d{1,2}日?$', tail):
        cues.append('unclosed_calendar_parenthesis')
    if re.search(r'(?:19|20)\d{2}年(?:\d{1,2}(?:月\d{0,2})?)?$', tail):
        cues.append('unfinished_chinese_calendar_suffix')
    if re.search(r'(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{0,1}$', tail):
        cues.append('possible_partial_numeric_calendar_suffix')
    return cues


def _interleave(left, right):
    return [value for pair in zip_longest(left, right) for value in pair if value is not None]


def _coordinates(record):
    match = WINDOW.fullmatch(record['chunk_id'])
    if not match:
        raise ValueError('Neighbor provenance requires a canonical frozen window ID')
    stock, year, page, start = match.groups()
    if (type(record['meta'].get('report_year')) is not int or
            type(record['meta'].get('physical_pdf_page_1based')) is not int or
            stock != record['meta'].get('stock_code') or int(year) != record['meta'].get('report_year') or
            int(page) != record['meta'].get('physical_pdf_page_1based')):
        raise ValueError('Window ID and metadata coordinates disagree')
    return int(page), int(start)


def allocate_evidence_budget(question, initial, table_hits, adjacent_hits, adjacent_audit, counter, *,
                             policy='boundary_first', max_context_tokens=6000, max_new_sources=16):
    if policy not in POLICIES:
        raise ValueError('Unknown predefined evidence budget policy')
    if type(max_new_sources) is not int or not 1 <= max_new_sources <= 16:
        raise ValueError('Global new-source cap must be an integer in [1,16]')
    # Validate initial evidence even in the initial/no-op condition.
    current, _ = extend_retained_context(question, initial, [], counter,
        max_context_tokens=max_context_tokens, max_new_sources=1)
    original = {row['chunk_id']: row for row in initial['source_records']}
    annual = [r for r in initial['source_records'] if r['meta'].get('corpus_type') == 'annual_report']
    if not annual:
        raise ValueError('An original annual source is required to bind the PDF identity')
    allowed = {(r['doc_id'], r['meta']['source_pdf_sha256']) for r in annual}
    proposals = adjacent_audit.get('selected_candidates', [])
    if (len(proposals) != len(adjacent_hits) or adjacent_audit.get('recursive_expansion') is not False or
            adjacent_audit.get('reference_labels_read') is not False or adjacent_audit.get('query_terms_used') is not False):
        raise ValueError('Neighbor audit does not bind a nonrecursive, label-free candidate list')
    seen = {}

    def validate(chunk, score):
        meta = chunk.meta
        if (meta.get('corpus_type') != 'annual_report' or meta.get('stock_code') != question['stock_code'] or
                type(meta.get('report_year')) is not int or meta['report_year'] != question['report_year'] or
                (chunk.doc_id, meta.get('source_pdf_sha256')) not in allowed):
            raise ValueError('Candidate is outside the original company/year/PDF scope')
        if not math.isfinite(float(score)):
            raise ValueError('Candidate score must be finite')
        record = _source_record(chunk, 0.0, 'source')
        signature = canonical_sha256(record)
        if chunk.chunk_id in seen and seen[chunk.chunk_id] != signature:
            raise ValueError('Duplicate candidate ID has conflicting source content')
        seen[chunk.chunk_id] = signature
        if chunk.chunk_id in original:
            old = copy.deepcopy(original[chunk.chunk_id]);old['score'] = 0.0;old['evidence_id'] = 'source'
            if old != record:
                raise ValueError('Candidate ID conflicts with an immutable original source')

    tables = []
    for chunk, score in table_hits:
        validate(chunk, score)
        if chunk.meta.get('source_representation') != 'table_field_view':
            raise ValueError('Table candidates require source-bound field views')
        verify_field_views(chunk)
        if chunk.meta.get('temporal_scope') == 'outside_reporting_year':
            raise ValueError('Outside-year table candidate must not enter the annual budget pool')
        tables.append(dict(chunk=chunk, score=score, lane='table', cues=[]))
    adjacent, critical = [], []
    for (chunk, score), proposal in zip(adjacent_hits, proposals):
        validate(chunk, score)
        if proposal.get('chunk_id') != chunk.chunk_id or proposal.get('adjacent_hop') != 1:
            raise ValueError('Neighbor hit differs from its one-hop selector audit')
        seed = original.get(proposal.get('seed_chunk_id'))
        if seed is None or seed['meta'].get('corpus_type') != 'annual_report':
            raise ValueError('Neighbor seed must be original annual evidence')
        seed_page, seed_start = _coordinates(seed)
        record = _source_record(chunk, score, 'source')
        page, start = _coordinates(record)
        same_page = page == seed_page
        direction = proposal.get('direction')
        if (direction not in ('successor','predecessor') or proposal.get('same_page') is not same_page or
                proposal.get('page') != page or proposal.get('start') != start or
                proposal.get('seed_page') != seed_page or proposal.get('seed_start') != seed_start or
                seed['doc_id'] != chunk.doc_id or seed['meta']['source_pdf_sha256'] != chunk.meta['source_pdf_sha256']):
            raise ValueError('Neighbor coordinate provenance disagrees with its original seed')
        if same_page and ((direction=='successor' and start<=seed_start) or (direction=='predecessor' and start>=seed_start)):
            raise ValueError('Neighbor direction disagrees with its character coordinates')
        cues = boundary_cues(seed['text']) if direction=='successor' and same_page else []
        entry = dict(chunk=chunk, score=score, lane='boundary_successor' if cues else 'adjacent', cues=cues,
                     seed_chunk_id=seed['chunk_id'])
        adjacent.append(entry)
        if cues:critical.append(entry)
    critical_ids = {entry['chunk'].chunk_id for entry in critical}
    ordinary = [entry for entry in adjacent if entry['chunk'].chunk_id not in critical_ids]
    if policy=='initial':schedule=[]
    elif policy=='table_first':schedule=tables+adjacent
    elif policy=='adjacent_first':schedule=adjacent+tables
    elif policy=='boundary_first':schedule=critical+tables+ordinary
    else:schedule=critical+_interleave(tables,ordinary)
    attempts, ordered, considered, added = [], [], set(), 0
    for rank, entry in enumerate(schedule, 1):
        chunk = entry['chunk']
        info=dict(candidate_rank=rank,chunk_id=chunk.chunk_id,lane=entry['lane'],boundary_cues=entry['cues'],
                  seed_chunk_id=entry.get('seed_chunk_id'),tokens_before=current['reference_tokens'])
        if chunk.chunk_id in considered:
            info.update(accepted=False,reason='duplicate_candidate_in_schedule',tokens_after=current['reference_tokens'])
        elif added>=max_new_sources:
            info.update(accepted=False,reason='global_new_source_cap',tokens_after=current['reference_tokens'])
        else:
            considered.add(chunk.chunk_id);ordered.append(chunk.chunk_id)
            current, packing = extend_retained_context(question,current,[(chunk,entry['score'])],counter,
                max_context_tokens=max_context_tokens,max_new_sources=1)
            accepted=bool(packing['accepted_count']);added+=int(accepted)
            info.update(accepted=accepted,reason='accepted' if accepted else packing['outcome'],
                        tokens_after=current['reference_tokens'],packing=packing)
        attempts.append(info)
    n=len(initial['source_records'])
    if not current['context'].startswith(initial['context']) or current['source_records'][:n]!=initial['source_records']:
        raise ValueError('Budget allocation changed the original evidence or IDs')
    audit=dict(policy=policy,source_cap=max_new_sources,reference_token_cap=max_context_tokens,
               candidate_table_count=len(tables),candidate_neighbor_count=len(adjacent),
               critical_neighbor_ids=[e['chunk'].chunk_id for e in critical],
               ordered_unique_candidate_ids=ordered,attempts=attempts,accepted_count=added,
               final_reference_tokens=current['reference_tokens'],initial_reference_tokens=initial['reference_tokens'],
               labels_read=False,queries_generated=False,model_calls=0,whole_chunks_only=True,
               initial_text_records_ids_preserved=True,source_files_reverified=False,
               boundary_cues_are_relevance_proof=False,
               adjacency_scope='Selector one-hop/coordinate metadata checked; actual index adjacency verified by the frozen selector, not recomputed here.')
    return current,audit
