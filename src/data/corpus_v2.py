"""Non-destructive corpus preparation. All offsets are in loader-normalized source text."""
from __future__ import annotations

import hashlib
import re

HEADING = re.compile(r"(?m)^[ \t\u3000]*(第[一二三四五六七八九十百千零0-9]+条(?:之[一二三四五六七八九十0-9]+)?)[ \t\u3000]*")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_v2(doc: dict, max_chars: int = 1800) -> list[dict]:
    """Only line-leading articles in regulations are headings; retain every source character.

    Long articles have multiple parts, never silent truncation. Penalty quotations do
    not become regulatory article headings. Coordinates remain exact even at whitespace.
    Heading detection is structural, not a certification of legal validity.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    text = doc["text"]
    headings = list(HEADING.finditer(text)) if doc["doc_type"] == "regulation" else []
    boundaries = sorted({0, len(text), *(m.start() for m in headings)})
    names = {m.start(): m.group(1) for m in headings}
    chunks = []
    for start, end in zip(boundaries, boundaries[1:]):
        cursor, part = start, 0
        while cursor < end:
            stop = min(cursor + max_chars, end)
            if stop < end:
                newline = text.rfind("\n", cursor + max_chars // 2, stop)
                if newline >= 0:
                    stop = newline + 1
            piece = text[cursor:stop]
            part += 1
            chunks.append({"chunk_id": f"{doc['doc_id']}-V2-{len(chunks)+1:04d}",
                           "doc_id": doc["doc_id"], "clause_no": names.get(start),
                           "part": part, "source_start": cursor, "source_end": stop,
                           "text": piece, "text_sha256": digest(piece),
                           "source_text_sha256": digest(text), "truncated": False})
            cursor = stop
    return chunks


def migrate_span(old, new_chunks: list[dict]) -> list[str]:
    return [c["chunk_id"] for c in new_chunks
            if max(c["source_start"], old.meta["source_start"])
            < min(c["source_end"], old.meta["source_end"])]
