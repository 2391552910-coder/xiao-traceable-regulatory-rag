"""Deterministic, metadata-only neighbours in a frozen annual-report index.

Only the initial annual evidence supplies seeds. Each seed has at most its
direct successor and predecessor in the same document/file coordinate sequence.
This selector does not read labels, inspect query terms, rank by answer content,
pack a token budget, or extend recursively from newly selected neighbours.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from src.data.clause_splitter import Chunk


POLICIES = ('direction_round_robin', 'continuation_first')
_COORDINATE_ID = re.compile(
    r'HELD-(?P<stock>[0-9]{6})-(?P<year>[0-9]{4})-'
    r'P(?P<page>[1-9][0-9]*)-S(?P<start>0|[1-9][0-9]*)\Z')
_HASH = re.compile(r'[0-9a-fA-F]{64}\Z')
_EVIDENCE_ID = re.compile(r'[AR][1-9][0-9]*\Z')
_BOUND_RECORD_FIELDS = (
    ('chunk_id', 'chunk_id'), ('doc_id', 'doc_id'),
    ('document_title', 'doc_title'), ('doc_type', 'doc_type'),
    ('source', 'source'), ('clause_no', 'clause_no'), ('text', 'text'),
    ('meta', 'meta'),
)


def _file_sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _coordinates(chunk):
    """Bind numeric ID coordinates to the source metadata; never execute them."""
    match = _COORDINATE_ID.fullmatch(chunk.chunk_id)
    if match is None:
        raise ValueError('Annual chunk ID lacks canonical HELD page/start coordinates')
    meta = chunk.meta
    if not isinstance(meta, dict):
        raise ValueError('Annual chunk requires source metadata')
    stock, year, page, start = match['stock'], int(match['year']), int(match['page']), int(match['start'])
    if (meta.get('stock_code') != stock or type(meta.get('report_year')) is not int
            or meta['report_year'] != year or year < 1000):
        raise ValueError('Annual chunk ID and company/year metadata disagree')
    if type(meta.get('physical_pdf_page_1based')) is not int or meta['physical_pdf_page_1based'] != page:
        raise ValueError('Annual chunk ID and physical page metadata disagree')
    digest = meta.get('source_pdf_sha256')
    if not isinstance(digest, str) or _HASH.fullmatch(digest) is None:
        raise ValueError('Annual chunk requires original PDF SHA256 metadata')
    if str(meta.get('system_corpus_input', '')).lower() == 'false':
        raise ValueError('Reviewer-only annual chunks cannot supply neighbours')
    if chunk.doc_type != 'annual_report' or not isinstance(chunk.doc_id, str) or not chunk.doc_id.strip():
        raise ValueError('Annual chunk requires annual_report type and document identity')
    if not isinstance(chunk.text, str) or not chunk.text.strip():
        raise ValueError('Annual neighbours require nonempty original text')
    # A character start stored by a later importer must not disagree with the
    # frozen ID coordinate. The original held-out index carries it only in ID.
    if 'page_text_char_start' in meta and (
            type(meta['page_text_char_start']) is not int or meta['page_text_char_start'] != start):
        raise ValueError('Annual character-start metadata disagrees with its ID')
    return stock, year, page, start, digest.lower()


class FrozenAdjacentIndex:
    """Load and validate a read-only snapshot of the SQLite ``chunks`` table.

    The frozen held-out schema is ``chunks(position INTEGER PRIMARY KEY,
    payload TEXT)``, where each payload contains the ``Chunk`` dataclass fields.
    Nonannual chunks are excluded from neighbour sequences. All chunk IDs must
    nevertheless be unique, so a conflicting record cannot hide a seed.
    Coordinate validation establishes ID/metadata consistency, not a fresh
    extraction or independent check of the original PDF offsets.
    """

    def __init__(self, database):
        self.path = Path(database).resolve()
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        self.database_sha256 = _file_sha256(self.path)
        self._chunks, self._coordinates, self._groups = {}, {}, defaultdict(list)
        with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as connection:
            connection.execute('PRAGMA query_only=ON')
            for position, raw in connection.execute('SELECT position,payload FROM chunks ORDER BY position'):
                try:
                    payload = json.loads(raw)
                    if not isinstance(payload, dict):
                        raise TypeError('Chunk payload must be an object')
                    chunk = Chunk(**payload)
                except (ValueError, TypeError) as error:
                    raise ValueError(f'Invalid chunk payload at SQLite position {position}') from error
                if not isinstance(chunk.chunk_id, str) or not chunk.chunk_id:
                    raise ValueError('Every indexed chunk requires a nonempty ID')
                if chunk.chunk_id in self._chunks:
                    raise ValueError('Duplicate chunk ID in SQLite index')
                self._chunks[chunk.chunk_id] = chunk
                if not isinstance(chunk.meta, dict):
                    raise ValueError('Every indexed chunk requires metadata')
                if chunk.meta.get('corpus_type') != 'annual_report':
                    continue
                stock, year, page, start, digest = _coordinates(chunk)
                group = (chunk.doc_id, stock, year, digest)
                self._coordinates[chunk.chunk_id] = (page, start)
                self._groups[group].append(chunk.chunk_id)
        if _file_sha256(self.path) != self.database_sha256:
            raise ValueError('SQLite index changed while its snapshot was loaded')
        self._locations = {}
        for group, ids in self._groups.items():
            ids.sort(key=lambda cid: self._coordinates[cid])
            for offset, cid in enumerate(ids):
                self._locations[cid] = (group, offset)

    def select(self, question, context, *, policy='direction_round_robin'):
        """Return ``([(unchanged Chunk copy, 0.0), ...], audit)``.

        ``context`` must be the frozen initial packed context or its source
        records, not a context already extended by this selector's caller.
        Seed order is the initial annual-source order. The default visits all
        direct successors in that order, then all direct predecessors. The
        ``continuation_first`` policy visits same-page successors, cross-page
        successors, same-page predecessors and cross-page predecessors, keeping
        seed order within each group. Both policies enumerate the same one-hop
        candidates before deduplication. A neighbour already present is skipped
        without advancing to a second neighbour. Scores are a finite zero
        placeholder for the existing packer, not a measured relevance signal.
        """
        if policy not in POLICIES:
            raise ValueError('Unknown deterministic adjacency policy')
        if not isinstance(question, dict) or not isinstance(question.get('stock_code'), str):
            raise ValueError('Question requires its public stock_code')
        stock, year = question['stock_code'], question.get('report_year')
        if re.fullmatch(r'[0-9]{6}', stock) is None or type(year) is not int or not 1000 <= year <= 9999:
            raise ValueError('Question requires a six-digit stock code and integer report year')
        records = context.get('source_records') if isinstance(context, dict) else context
        if not isinstance(records, list):
            raise ValueError('Provide a packed context or source-record list')
        existing, evidence_ids, seeds, ignored = set(), set(), [], []
        for source_rank, record in enumerate(records, 1):
            if not isinstance(record, dict) or not isinstance(record.get('chunk_id'), str) or not record['chunk_id']:
                raise ValueError('Initial sources require chunk IDs')
            cid = record['chunk_id']
            if cid in existing:
                raise ValueError('Duplicate initial source chunk ID')
            existing.add(cid)
            evidence_id = record.get('evidence_id')
            if evidence_id is not None:
                if not isinstance(evidence_id, str) or _EVIDENCE_ID.fullmatch(evidence_id) is None:
                    raise ValueError('Initial evidence ID is invalid')
                if evidence_id in evidence_ids:
                    raise ValueError('Duplicate initial evidence ID')
                evidence_ids.add(evidence_id)
            meta = record.get('meta')
            if not isinstance(meta, dict):
                raise ValueError('Initial source metadata is required')
            if meta.get('corpus_type') != 'annual_report':
                if cid in self._locations:
                    raise ValueError('Initial source role disagrees with the SQLite annual chunk')
                ignored.append(dict(chunk_id=cid, source_rank=source_rank, reason='nonannual_source_not_a_seed'))
                continue
            if cid not in self._locations:
                raise ValueError('Initial annual seed is absent from the SQLite index')
            indexed = self._chunks[cid]
            if any(record.get(record_key) != getattr(indexed, chunk_key)
                   for record_key, chunk_key in _BOUND_RECORD_FIELDS):
                raise ValueError('Initial annual seed content differs from the SQLite payload')
            seed_stock, seed_year, page, start, digest = _coordinates(indexed)
            if seed_stock != stock or seed_year != year:
                raise ValueError('Initial annual seed is outside the question company/year')
            if evidence_id is not None and not evidence_id.startswith('A'):
                raise ValueError('Initial annual seed must have an A evidence ID')
            seeds.append(dict(seed_chunk_id=cid, seed_evidence_id=evidence_id,
                              seed_rank=len(seeds) + 1, source_rank=source_rank,
                              doc_id=indexed.doc_id, stock_code=stock, report_year=year,
                              source_pdf_sha256=digest, seed_page=page, seed_start=start))

        proposals = []
        for direction, delta in [('successor', 1), ('predecessor', -1)]:
            for seed in seeds:
                group, offset = self._locations[seed['seed_chunk_id']]
                neighbour = offset + delta
                row = {**seed, 'direction': direction, 'adjacent_hop': 1,
                       'chunk_id': None, 'page': None, 'start': None,
                       'same_page': None, 'physical_page_delta': None}
                if 0 <= neighbour < len(self._groups[group]):
                    cid = self._groups[group][neighbour]
                    page, start = self._coordinates[cid]
                    row.update(chunk_id=cid, page=page, start=start,
                               same_page=page == seed['seed_page'],
                               physical_page_delta=page - seed['seed_page'])
                proposals.append(row)
        if policy == 'continuation_first':
            proposals.sort(key=lambda r: (
                (0 if r['same_page'] else 1) if r['direction'] == 'successor'
                else (2 if r['same_page'] else 3), r['seed_rank']))
        hits, selected, seen, candidate_rank = [], [], set(), 0
        for attempt_rank, row in enumerate(proposals, 1):
            cid = row['chunk_id'];row['attempt_rank'] = attempt_rank
            row['candidate_rank'] = None;row['selection_rank'] = None
            reason = None
            if cid is None:
                reason = 'document_coordinate_sequence_boundary'
            else:
                candidate_rank += 1;row['candidate_rank'] = candidate_rank
                if cid in existing:
                    reason = 'already_in_initial_context'
                elif cid in seen:
                    reason = 'duplicate_neighbour_candidate'
            row['selected'] = reason is None;row['omission_reason'] = reason
            if reason is None:
                seen.add(cid);row['selection_rank'] = len(hits) + 1
                hits.append((copy.deepcopy(self._chunks[cid]), 0.0));selected.append(copy.deepcopy(row))
        audit = dict(
            policy=policy, database=str(self.path), database_sha256=self.database_sha256,
            query_terms_used=False, reference_labels_read=False, recursive_expansion=False,
            adjacent_hops=1, score_kind='unscored_adjacency_zero_placeholder',
            token_budget_applied=False, coordinate_order=['physical_pdf_page_1based', 'ID_character_start'],
            neighbour_scope=['doc_id', 'stock_code', 'report_year', 'source_pdf_sha256'],
            initial_source_count=len(records), seed_count=len(seeds), seeds=seeds,
            ignored_sources=ignored, attempts=proposals,
            candidates=[copy.deepcopy(r) for r in proposals if r['chunk_id'] is not None],
            selected_candidates=selected, selected_count=len(hits),
            omission_reason_counts=dict(Counter(r['omission_reason'] for r in proposals if not r['selected'])),
            source_files_reverified=False,
            coordinate_validation='ID and metadata consistency; PDF text offsets not independently re-extracted')
        return hits, audit
