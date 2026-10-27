"""Source-frame evidence coverage across chunkings; no relevance acceptance.

Locations must come from the exact source verifier. Equal chunk IDs, titles or
text alone never establish a match. Scores measure supplied target-span coverage,
not semantic support, rule applicability, or standard graded nDCG.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from numbers import Real
from src.data.pdf_text_frames import NATIVE_PDF_PARSERS

ROLES = ('annual_report', 'regulation')
PARSERS = set(NATIVE_PDF_PARSERS) | {'declared_ocr_utf8_frame',
           'ooxml-main-body-v1', 'legacy-metadata-body-v1', 'raw-utf8-file-v1'}


def _integer(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f'{label} must be an integer >= {minimum}')
    return value


@dataclass(frozen=True)
class SourceSpan:
    role: str
    source_sha256: str
    text_frame_sha256: str
    frame_parser: str
    physical_page: int | None
    start: int
    end: int

    def __post_init__(self):
        if self.role not in ROLES or self.frame_parser not in PARSERS:
            raise ValueError('Unsupported source role or coordinate-frame parser')
        for value in (self.source_sha256, self.text_frame_sha256):
            if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
                raise ValueError('Source and text-frame SHA256 must be lowercase hex')
        pdf = self.frame_parser in NATIVE_PDF_PARSERS or self.frame_parser == 'declared_ocr_utf8_frame'
        if pdf:
            _integer(self.physical_page, 'physical_page', 1)
        elif self.physical_page is not None:
            raise ValueError('Non-PDF frames cannot have physical PDF pages')
        if self.role == 'annual_report' and not pdf:
            raise ValueError('Annual report evidence must refer to PDF coordinates')
        _integer(self.start, 'start')
        _integer(self.end, 'end', 1)
        if self.start >= self.end:
            raise ValueError('Source spans must be nonempty half-open intervals')

    @property
    def frame_key(self):
        return (self.role, self.source_sha256, self.text_frame_sha256,
                self.frame_parser, self.physical_page)


def verify_location(record: dict, verifier) -> SourceSpan:
    """Resolve and freshly verify source bytes/quote before accepting coordinates."""
    for name in ['source_char_start', 'source_char_end', 'pdf_physical_page_1based']:
        value = record.get(name)
        if name == 'pdf_physical_page_1based' and value in (None, ''):
            continue
        if isinstance(value, bool) or not (isinstance(value, int) or
                isinstance(value, str) and re.fullmatch('[0-9]+', value.strip())):
            raise ValueError(f'{name} must be an integer or decimal integer string')
    role = record.get('role')
    proof = verifier.verify(record, role)
    return SourceSpan(role, proof['source_sha256'], proof['text_frame_sha256'],
                      proof['frame_parser'], proof['physical_pdf_page_1based'],
                      proof['source_char_start'], proof['source_char_end'])


@dataclass(frozen=True)
class TargetSpan:
    target_id: str
    location: SourceSpan


@dataclass(frozen=True)
class RankedSpanHit:
    hit_id: str
    spans: tuple[SourceSpan, ...]


def union_length(intervals):
    total, rightmost = 0, -1
    for left, right in sorted(intervals):
        total += max(0, right - max(left, rightmost))
        rightmost = max(rightmost, right)
    return total


def score_span_retrieval(targets: list[TargetSpan], rankings: dict[str, list[RankedSpanHit]],
                         *, layout='dual', cutoffs=(1, 3, 5, 10), coverage_threshold=1.0):
    """Keep actual ranks in merged pools and independent ranks in dual pools.

    Coverage accumulates the union of intersecting source intervals, without
    double counting overlaps. Rank is never compressed after role filtering or
    duplicate-location hits. Multiple target units may finish at the same rank.
    An empty target role is unknown/NA, not a negative or a successful refusal.
    """
    if layout not in {'merged', 'dual'}:
        raise ValueError('layout must be merged or dual')
    expected = {'merged'} if layout == 'merged' else set(ROLES)
    if set(rankings) != expected:
        raise ValueError('Rankings do not match the declared retrieval layout')
    if isinstance(coverage_threshold, bool) or not isinstance(coverage_threshold, Real) or \
            not math.isfinite(coverage_threshold) or not 0 < coverage_threshold <= 1:
        raise ValueError('coverage_threshold must be finite and in (0,1]')
    cutoffs = tuple(cutoffs)
    if not cutoffs or any(isinstance(k, bool) or not isinstance(k, int) or k < 1 for k in cutoffs) or \
            tuple(sorted(set(cutoffs))) != cutoffs:
        raise ValueError('cutoffs must be distinct positive integers in ascending order')
    ids, locations = set(), set()
    for target in targets:
        if not isinstance(target.target_id, str) or not target.target_id.strip() or target.target_id in ids:
            raise ValueError('Target IDs must be nonempty and unique within a query')
        if target.location in locations:
            raise ValueError('Duplicate target locations must not inflate the denominator')
        ids.add(target.target_id)
        locations.add(target.location)
    for route, hits in rankings.items():
        seen = set()
        for hit in hits:
            if not isinstance(hit.hit_id, str) or not hit.hit_id.strip() or hit.hit_id in seen:
                raise ValueError('Hit IDs must be nonempty and unique within a ranked list')
            if not hit.spans:
                raise ValueError('Each ranked hit needs at least one source span')
            if layout == 'dual' and any(s.role != route for s in hit.spans):
                raise ValueError('Dual-route hit contains a different evidence role')
            seen.add(hit.hit_id)
    role_results = {}
    for role in ROLES:
        selected = [t for t in targets if t.location.role == role]
        hits = rankings['merged' if layout == 'merged' else role]
        intervals = {t.target_id: [] for t in selected}
        first_complete = {}
        snapshots = {}
        for rank, hit in enumerate(hits[:max(cutoffs)], 1):
            for target in selected:
                loc = target.location
                for span in hit.spans:
                    if loc.frame_key != span.frame_key:
                        continue
                    left, right = max(loc.start, span.start), min(loc.end, span.end)
                    if left < right:
                        intervals[target.target_id].append((left, right))
                if union_length(intervals[target.target_id]) / (loc.end - loc.start) >= coverage_threshold:
                    first_complete.setdefault(target.target_id, rank)
            snapshots[rank] = {t.target_id: union_length(intervals[t.target_id]) /
                               (t.location.end - t.location.start) for t in selected}
        metrics = {}
        for cutoff in cutoffs:
            matched = {key: rank for key, rank in first_complete.items() if rank <= cutoff}
            count = len(selected)
            first = min(matched.values(), default=None)
            metrics[str(cutoff)] = {
                'recall': len(matched) / count if count else None,
                'hit': float(bool(matched)) if count else None,
                'mrr': (1 / first if first else 0.0) if count else None,
                'mean_evidence_reciprocal_rank': sum(1 / r for r in matched.values()) / count if count else None,
                'evidence_discounted_coverage': sum(1 / math.log2(r + 1) for r in matched.values()) / count if count else None,
                'first_hit_rank': first, 'matched_target_ids': sorted(matched),
                'target_coverage_fractions': snapshots.get(min(cutoff, len(hits)), {t.target_id: 0.0 for t in selected})}
        role_results[role] = {'target_count': len(selected),
            'target_state': 'supplied_target_spans' if selected else 'no_targets_supplied_not_a_negative',
            'ranked_hit_count': len(hits), 'by_cutoff': metrics}
    joint = {}
    eligible = all(role_results[r]['target_count'] for r in ROLES)
    for cutoff in cutoffs:
        a, b = (role_results[r]['by_cutoff'][str(cutoff)] for r in ROLES)
        both_hit = eligible and bool(a['hit'] and b['hit'])
        joint[str(cutoff)] = {
            'both_roles_hit': float(both_hit) if eligible else None,
            'both_roles_all_target_evidence': float(a['recall'] == b['recall'] == 1) if eligible else None,
            'macro_role_recall': (a['recall'] + b['recall']) / 2 if eligible else None,
            'joint_mrr': (1 / max(a['first_hit_rank'], b['first_hit_rank']) if both_hit else 0.0) if eligible else None}
    return {'layout': layout, 'cutoffs': list(cutoffs), 'coverage_threshold': coverage_threshold,
            'cutoff_unit': 'actual merged rank' if layout == 'merged' else 'rank within each evidence route',
            'roles': role_results, 'joint_eligible': bool(eligible), 'joint_by_cutoff': joint,
            'target_semantics_independently_verified': False, 'accepted_as_gold': False}
