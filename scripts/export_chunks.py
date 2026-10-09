"""
按 chunk_id 导出知识库条款块原文（人工/AI 标注辅助工具）。

用法：
  python scripts/export_chunks.py DOC007-C086 DOC090-C127 ...
  python scripts/export_chunks.py --query-file data/annotation/retrieval_queries_for_annotation.csv --query-id Q01
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data.knowledge_loader import load_documents  # noqa: E402
from data.clause_splitter import split_document  # noqa: E402

KB_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge_base"


def build_chunk_index() -> dict:
    docs = load_documents(KB_DIR)
    index = {}
    for doc in docs:
        for chunk in split_document(doc, strategy="clause"):
            index[chunk.chunk_id] = chunk
    return index


def export(index: dict, chunk_ids: list[str]) -> None:
    for cid in chunk_ids:
        chunk = index.get(cid)
        if chunk is None:
            print(f"### {cid}\n[未找到该 chunk_id]\n")
            continue
        clause = chunk.clause_no or "(无条款号)"
        print(f"### {cid} | {chunk.doc_title} | {clause}")
        print(chunk.text.strip())
        print()


def ids_from_query(csv_path: str, query_id: str) -> list[str]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["query_id"] == query_id:
                return [c.strip() for c in row["candidate_chunk_ids"].split(";") if c.strip()]
    raise SystemExit(f"查询 {query_id} 不存在于 {csv_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("chunk_ids", nargs="*")
    ap.add_argument("--query-file")
    ap.add_argument("--query-id")
    args = ap.parse_args()

    ids = args.chunk_ids
    if args.query_file and args.query_id:
        ids = ids_from_query(args.query_file, args.query_id)

    if not ids:
        ap.error("请提供 chunk_id 或 --query-file + --query-id")

    export(build_chunk_index(), ids)
