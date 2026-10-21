"""Build a versioned corpus and migration ledger; never modify frozen inputs or infer labels."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data.knowledge_loader import load_documents
from src.data.clause_splitter import split_document
from src.data.corpus_v2 import digest, split_v2, migrate_span
from src.data.benchmark import corpus_hash, sha256_file


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build(out: Path):
    out.mkdir(parents=True, exist_ok=False)
    kb = ROOT / "data/knowledge_base"
    before = corpus_hash(kb)
    docs = load_documents(kb)
    files = {}
    for p in sorted(kb.glob("*.txt")):
        key = next(line.split(":", 1)[1].strip() for line in p.read_text().splitlines()
                   if line.startswith("@DOC_ID:"))
        files[key] = p
    by_id = {d["doc_id"]: d for d in docs}
    groups = defaultdict(list)
    for d in docs:
        groups[digest(d["text"])].append(d["doc_id"])
    aliases, documents, chunks, new_by_doc, manifest = {}, [], [], {}, []
    for d in docs:
        did = d["doc_id"]
        # These are explicitly named excerpts, not full authoritative source documents.
        excerpt = "节选" in d["title"]
        eligible = sorted(i for i in groups[digest(d["text"])] if "节选" not in by_id[i]["title"])
        canonical = eligible[0] if eligible else None
        aliases[did] = None if excerpt else canonical
        status = "quarantined_excerpt" if excerpt else "duplicate_alias" if canonical != did else "retained"
        manifest.append({"old_doc_id": did, "canonical_doc_id": aliases[did], "status": status,
                         "title": d["title"], "source": d["source"],
                         "source_file": str(files[did].relative_to(ROOT)),
                         "source_file_sha256": sha256_file(files[did]),
                         "source_text_sha256": digest(d["text"]),
                         "date_as_recorded": d["date"] or None,
                         "date_status": "recorded_unverified" if d["date"] else "missing",
                         "effective_date": None, "legal_version_verified": False})
        if status == "retained":
            documents.append(d)
            new_by_doc[did] = split_v2(d)
            chunks.extend(new_by_doc[did])
    old_chunks = {c.chunk_id: c for d in docs for c in split_document(d)}
    mapping = []
    for old in old_chunks.values():
        canonical = aliases[old.doc_id]
        new_ids = migrate_span(old, new_by_doc[canonical]) if canonical else []
        mapping.append({"old_chunk_id": old.chunk_id, "old_doc_id": old.doc_id,
                        "old_text_sha256": digest(old.text),
                        "old_source_start": old.meta["source_start"],
                        "old_source_end": old.meta["source_end"], "old_raw_end": old.meta["raw_end"],
                        "old_truncated": old.meta["truncated"],
                        "old_inline_reference": bool(old.clause_no and not old.meta["is_clause_heading"]),
                        "canonical_doc_id": canonical, "new_chunk_ids": new_ids,
                        "migration_status": "coordinate_candidate_only" if new_ids else "quarantined",
                        "semantic_label_inherited": False})
    mappings = {r["old_chunk_id"]: r for r in mapping}
    migrations = []
    gold = ROOT / "data/annotation/retrieval_queries_gold.csv"
    reviewed = ROOT / "data/annotation/reviews/independent_20261013/reviewed_candidates.csv"
    for kind, source in [("original_ai_gold", gold), ("single_ai_review", reviewed)]:
        for r in read_csv(source):
            ids = r["relevant_chunk_ids"].split(";") if kind == "original_ai_gold" else [r["chunk_id"]]
            for cid in ids:
                migrations.append({"query_id": r["query_id"], "query": r["query"], "dimension": r["dimension"],
                                   "origin": kind, "input_sha256": sha256_file(source),
                                   "old_grade": "1" if kind == "original_ai_gold" else r["review_grade"],
                                   **mappings[cid], "new_grade": None,
                                   "human_annotator_a": None, "human_annotator_b": None,
                                   "review_status": "pending_context_relabel"})
    write_jsonl(out / "documents.jsonl", documents)
    write_jsonl(out / "chunks.jsonl", chunks)
    write_jsonl(out / "document_manifest.jsonl", manifest)
    write_jsonl(out / "chunk_migration.jsonl", mapping)
    write_jsonl(out / "label_migration.jsonl", migrations)
    write_jsonl(out / "date_review_queue.jsonl", [m for m in manifest if m["date_status"] == "missing"])
    assert corpus_hash(kb) == before
    summary = {"schema_version": 2, "status": "prepared_pending_semantic_and_temporal_review",
               "usage": "development_preparation_only", "source_corpus_sha256": before,
               "coordinate_system": "Unicode offsets in load_documents text (body.strip), not raw file bytes",
               "source_documents": len(docs), "document_status_counts": dict(Counter(m["status"] for m in manifest)),
               "exact_duplicate_groups": [v for v in groups.values() if len(v) > 1],
               "retained_documents": len(documents), "new_chunks": len(chunks),
               "old_chunks_mapped": len(mapping), "label_rows": len(migrations),
               "missing_dates": sum(m["date_status"] == "missing" for m in manifest),
               "human_labels_added": 0, "formal_gold_created": False,
               "tools_sha256": {p: sha256_file(ROOT/p) for p in ["src/data/corpus_v2.py", "scripts/prepare_corpus_v2.py"]},
               "artifacts_sha256": {p.name: sha256_file(p) for p in sorted(out.iterdir())}}
    write_json(out / "manifest.json", summary)
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", required=True, type=Path)
    print(json.dumps(build(ap.parse_args().out_dir), ensure_ascii=False, indent=2))
