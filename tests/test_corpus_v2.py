import pytest

from src.data.corpus_v2 import split_v2, migrate_span
from src.data.clause_splitter import split_document


def document(text, doc_type="regulation"):
    return {"doc_id": "DOCX", "title": "test", "doc_type": doc_type, "source": "fixture", "text": text}


def test_inline_citation_not_heading_and_all_characters_retained():
    d = document("序言\n第一条 根据第二条执行。\n第二条 " + "甲" * 4100)
    chunks = split_v2(d)
    assert "".join(c["text"] for c in chunks) == d["text"]
    assert len([c for c in chunks if c["clause_no"] == "第一条"]) == 1
    assert all(c["text"] == d["text"][c["source_start"]:c["source_end"]] for c in chunks)
    assert all(len(c["text"]) <= 1800 and not c["truncated"] for c in chunks)
    assert all(migrate_span(c, chunks) for c in split_document(d))


def test_penalty_quotes_do_not_acquire_article_identity():
    assert all(c["clause_no"] is None for c in split_v2(document("第一条 处罚引用。", "penalty")))
