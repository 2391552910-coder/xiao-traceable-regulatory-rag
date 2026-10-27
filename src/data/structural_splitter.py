"""Opt-in complete-coverage segmentation; the frozen legacy splitter is unchanged."""
import re

from src.data.clause_splitter import Chunk

STRUCTURAL_HEADING_PATTERN = re.compile(
    r"(?m)^[ \t\u3000]*(?:(?P<clause>第[一二三四五六七八九十百千零0-9]+条"
    r"(?:之[一二三四五六七八九十0-9]+)?)|"
    r"(?P<section>[0-9]+(?:\.[0-9]+){1,5})(?![0-9.]))"
)


def split_by_structure(doc_id: str, doc_title: str, doc_type: str, source: str,
                       text: str, size: int = 1200, overlap: int = 160,
                       dimension: str | None = None, boundary_starts: dict[int, int] | None = None) -> list[Chunk]:
    """Split at line-heading candidates, then window each region without loss.

    This opt-in strategy has new IDs and exact source substrings. Anchoring
    avoids treating inline law references as headings. Detected headings are
    structural candidates, not certified legal clause identities; numbered
    sections and preamble text remain distinguishable in metadata.
    """
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError("size must be positive and overlap must be in [0, size)")
    headings = {match.start(): match for match in STRUCTURAL_HEADING_PATTERN.finditer(text)}
    if boundary_starts:
        if set(boundary_starts) - set(headings): raise ValueError('Unknown structural heading boundary override')
        adjusted, previous_end = {}, -1
        for position, match in headings.items():
            start = boundary_starts.get(position, position)
            if type(start) is not int or not previous_end < start <= position:
                raise ValueError('Structural boundary override crosses a previous heading')
            adjusted[start] = match; previous_end = match.end() - 1
        headings = adjusted
    boundaries = sorted({0, len(text), *headings})
    chunks = []
    for region_index, (left, right) in enumerate(zip(boundaries, boundaries[1:]), start=1):
        heading = headings.get(left)
        clause = heading.group("clause") if heading else None
        section = heading.group("section") if heading else None
        start, window_index = left, 0
        while start < right:
            end = min(start + size, right)
            if end < right:
                floor = start + max(size // 2, 1)
                boundary = max(text.rfind(mark, floor, end) for mark in ("\n", "。", "；", "！", "？"))
                if boundary >= floor:
                    end = boundary + 1
            a, b = start, end
            while a < b and text[a].isspace():
                a += 1
            while b > a and text[b-1].isspace():
                b -= 1
            if a < b:
                window_index += 1
                chunks.append(Chunk(
                    chunk_id=f"{doc_id}-S{region_index:04d}-W{window_index:03d}",
                    doc_id=doc_id, doc_title=doc_title, doc_type=doc_type,
                    source=source, clause_no=clause, text=text[a:b], dimension=dimension,
                    meta={"source_start": a, "source_end": b, "raw_end": b,
                          "truncated": False, "region_start": left, "region_end": right,
                          "structural_heading": clause or section,
                          "structural_heading_kind": "clause" if clause else "numbered_section" if section else "preamble",
                          "heading_detection": "anchored_line_candidate_unreviewed",
                          "is_continuation": window_index > 1,
                          "is_clause_heading": bool(clause and window_index == 1),
                          "owner_clause_no": clause},
                ))
            if end >= right:
                break
            start = max(end-overlap, start+1)
    return chunks


def split_structural_document(doc: dict, *, window_size: int = 1200,
                              window_overlap: int = 160) -> list[Chunk]:
    return split_by_structure(doc["doc_id"], doc["title"], doc["doc_type"],
                              doc["source"], doc["text"], size=window_size,
                              overlap=window_overlap, dimension=doc.get("dimension"))
