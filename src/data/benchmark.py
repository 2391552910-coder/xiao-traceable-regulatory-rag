"""冻结检索标注、语料与切分版本；结构审计不替代人工语义核验。"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from src.config import ROOT
from src.data.clause_splitter import Chunk, split_document
from src.data.eval_dataset import RetrievalQuery, load_retrieval_queries
from src.data.knowledge_loader import load_documents


# Win32 forbids `*` in file names. This one knowledge-base title is materialized
# under a full-width-star alias on Windows; map it back to its tracked Git name
# so the canonical corpus hash remains byte-for-byte comparable across systems.
WINDOWS_CORPUS_FILENAME_ALIASES = {
    "DOC304_证监会对＊ST普利重大财务造假案依法从严行政处罚.txt":
        "DOC304_证监会对*ST普利重大财务造假案依法从严行政处罚.txt",
}


def resolve_path(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corpus_hash(path: Path) -> str:
    files = [
        (WINDOWS_CORPUS_FILENAME_ALIASES.get(p.name, p.name), sha256_file(p))
        for p in path.glob("*.txt")
    ]
    files.sort(key=lambda item: item[0])
    return hashlib.sha256(json.dumps(files, ensure_ascii=False).encode()).hexdigest()


def annotation_hash(path: Path) -> str:
    files = sorted((path / "rounds").glob("*.csv"))
    files += [p for p in (path / "retrieval_queries_for_annotation.csv",
                         path / "rounds/suggested_supplements.md") if p.exists()]
    # Frozen manifests are shared across Windows and POSIX hosts. Native Path
    # rendering uses backslashes on Windows, so hash a canonical POSIX name.
    records = [(p.relative_to(path).as_posix(), sha256_file(p)) for p in files]
    return hashlib.sha256(json.dumps(records, ensure_ascii=False).encode()).hexdigest()


def read_rounds(path: Path, pattern: str) -> dict[str, int]:
    labels = {}
    for file in sorted(path.glob(pattern)):
        seen = set()
        with file.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f):
                if len(row) != 2 or row[1] not in {"0", "1"} or row[0] in seen:
                    raise ValueError(f"无效或重复的轮次标注：{file.name}")
                seen.add(row[0])
                labels[row[0]] = int(row[1])
    return labels


def audit_rounds(benchmark) -> dict:
    path = benchmark.query_path.parent / "rounds"
    rows = []
    for q in benchmark.queries:
        a = read_rounds(path, f"passA_{q.query_id}*.csv")
        b = read_rounds(path, f"passB_{q.query_id}*.csv")
        if not a and not b:
            continue
        if a.keys() != b.keys() or set(a) - benchmark.chunks.keys():
            raise ValueError(f"{q.query_id}: 双通道候选不一致或引用不存在")
        n = len(a)
        agreement = sum(a[c] == b[c] for c in a) / n
        pa, pb = sum(a.values()) / n, sum(b.values()) / n
        expected = pa * pb + (1 - pa) * (1 - pb)
        kappa = (agreement - expected) / (1 - expected) if expected < 1 else None
        disputes = {c for c in a if a[c] != b[c]}
        adjudicated = read_rounds(path, f"adjudicate_{q.query_id}*.csv")
        unresolved = disputes - adjudicated.keys()
        reconstructed = {c for c in a if a[c] == b[c] == 1}
        reconstructed.update(c for c in disputes if adjudicated.get(c) == 1)
        rows.append({"query_id": q.query_id, "n_candidates": n,
                     "agreement": agreement, "kappa": kappa,
                     "kappa_undefined_reason": "single_class_identical_labels" if kappa is None else None,
                     "below_0_6": kappa is not None and kappa < .6,
                     "unresolved_disputes": sorted(unresolved),
                     "gold_matches_rounds": reconstructed == q.relevant})
    defined = [r["kappa"] for r in rows if r["kappa"] is not None]
    return {"per_query": rows, "n_queries_with_rounds": len(rows),
            "n_undefined_kappa": sum(r["kappa"] is None for r in rows),
            "mean_defined_kappa": sum(defined) / len(defined) if defined else None,
            "note": "单一类别完全一致时 Kappa 未定义，不记作 1.0；逐查询平均仅描述候选池内一致性。"}


@dataclass
class Benchmark:
    queries: list[RetrievalQuery]
    chunks: dict[str, Chunk]
    documents: dict[str, dict]
    rows: list[dict]
    query_path: Path
    kb_path: Path
    hashes: dict[str, str]
    manifest: dict | None = None

    def audit(self) -> dict:
        refs = {cid for q in self.queries for cid in q.relevant}
        issues = []
        for cid in sorted(refs):
            chunk = self.chunks[cid]
            flags = []
            if chunk.clause_no and not chunk.meta["is_clause_heading"]:
                flags.append("inline_reference_used_as_heading")
            if chunk.meta["truncated"]:
                flags.append("truncated_evidence")
            if flags:
                issues.append({"chunk_id": cid, "flags": flags,
                               "stored_clause_no": chunk.clause_no,
                               "owner_clause_no": chunk.meta["owner_clause_no"],
                               "query_ids": [q.query_id for q in self.queries if cid in q.relevant]})
        sources = Counter(r.get("label_source", "unspecified") for r in self.rows)
        document_groups = {}
        for doc in self.documents.values():
            digest = hashlib.sha256(doc["text"].encode()).hexdigest()
            document_groups.setdefault(digest, []).append(doc["doc_id"])
        duplicate_documents = [ids for ids in document_groups.values() if len(ids) > 1]
        return {
            "status": "provisional", "usage": "development_only",
            "frozen": self.manifest is not None,
            "benchmark_id": self.manifest.get("benchmark_id") if self.manifest else None,
            "n_documents": len(self.documents), "n_chunks": len(self.chunks),
            "document_types": dict(Counter(d["doc_type"] for d in self.documents.values())),
            "n_queries": len(self.queries),
            "queries_by_dimension": dict(Counter(q.dimension for q in self.queries)),
            "n_positive_pairs": sum(len(q.relevant) for q in self.queries),
            "n_unique_positive_chunks": len(refs), "label_sources": dict(sources),
            "hashes": self.hashes, "structural_issues": issues,
            "duplicate_document_groups": duplicate_documents,
            "annotation_consistency": audit_rounds(self),
            "limitations": [
                "AI 双通道标注与仲裁；未记录独立人工语义复核，Kappa 不是正确率。",
                "候选池由弱标注构造，尚未证明全库相关条款已完整覆盖。",
                "历史切分在正文法规引用处也分块，并将长块截到 2000 字。",
                "40 条查询已用于开发，不应作为未见过的独立最终测试集。",
                "重复文档与不同法规版本可能影响相关证据计数；需人工明确保留/去重规则。",
            ],
        }


def load_benchmark(cfg: dict, query_path: str | Path | None = None,
                   verify_manifest: bool = True) -> Benchmark:
    evaluation = cfg.get("evaluation", {})
    queries_path = resolve_path(query_path or evaluation.get(
        "queries_path", "data/annotation/retrieval_queries_gold.csv"))
    kb_path = resolve_path(cfg["knowledge_base"]["path"])
    docs = load_documents(kb_path)
    if len({d["doc_id"] for d in docs}) != len(docs):
        raise ValueError("知识库包含重复 doc_id")
    chunks = [c for d in docs for c in split_document(d, "clause")]
    by_id = {c.chunk_id: c for c in chunks}
    if len(by_id) != len(chunks):
        raise ValueError("知识库包含重复 chunk_id")
    with queries_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    required = {"query_id", "dimension", "query", "relevant_chunk_ids"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("评测集为空或缺少必需字段")
    seen = set()
    for row in rows:
        qid = row["query_id"]
        if not qid.strip() or qid in seen:
            raise ValueError(f"空白或重复 query_id: {qid!r}")
        seen.add(qid)
        if row["dimension"] not in {"D1", "D2", "D3", "D4"} or not row["query"].strip():
            raise ValueError(f"{qid}: 查询为空或维度无效")
        refs = [s.strip() for s in row["relevant_chunk_ids"].split(";") if s.strip()]
        if not refs or len(refs) != len(set(refs)):
            raise ValueError(f"{qid}: 正例为空或重复")
        missing = set(refs) - by_id.keys()
        if missing:
            raise ValueError(f"{qid}: 无法定位相关块 {sorted(missing)}")
        if "n_relevant" in row and row["n_relevant"] and int(row["n_relevant"]) != len(refs):
            raise ValueError(f"{qid}: n_relevant 与标注数量不一致")
    hashes = {"queries_sha256": sha256_file(queries_path),
              "corpus_sha256": corpus_hash(kb_path),
              "annotation_sha256": annotation_hash(queries_path.parent),
              "splitter_sha256": sha256_file(ROOT / "src/data/clause_splitter.py")}
    benchmark = Benchmark(load_retrieval_queries(queries_path), by_id,
                          {d["doc_id"]: d for d in docs}, rows, queries_path, kb_path, hashes)
    manifest_path = resolve_path(evaluation.get(
        "manifest_path", "data/annotation/benchmark_manifest.json"))
    if verify_manifest:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1:
            raise ValueError("不支持的基准清单版本")
        if manifest.get("hashes") != hashes:
            raise ValueError("评测集、语料或切分器与冻结版本不一致；请审计并建立新的基准版本")
        benchmark.manifest = manifest
    return benchmark


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def review_candidates(benchmark: Benchmark) -> dict[str, set[str]]:
    """收集原候选池、两轮标注及补标；不把旧候选自动加入 gold。"""
    candidates = {q.query_id: set(q.relevant) for q in benchmark.queries}
    original = benchmark.query_path.parent / "retrieval_queries_for_annotation.csv"
    if original.exists():
        with original.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row["query_id"] in candidates:
                    candidates[row["query_id"]].update(row["candidate_chunk_ids"].split(";"))
    for qid, ids in candidates.items():
        for pattern in (f"passA_{qid}*.csv", f"passB_{qid}*.csv"):
            for path in sorted((benchmark.query_path.parent / "rounds").glob(pattern)):
                with path.open(encoding="utf-8-sig", newline="") as f:
                    ids.update(row[0] for row in csv.reader(f) if row)
    return candidates


def export_review(benchmark: Benchmark, path: Path,
                  extra_candidates: dict[str, set[str]] | None = None) -> int:
    """盲审工作表：不展示现有正负标签；需由真人填写，不自动认证。"""
    candidates = review_candidates(benchmark)
    for qid, ids in (extra_candidates or {}).items():
        candidates[qid].update(ids)
    fields = ["query_id", "dimension", "query", "chunk_id", "doc_title", "doc_date",
              "source", "stored_clause_no", "owner_clause_no", "is_clause_heading",
              "truncated", "text_sha256", "text", "human_label", "annotator", "comment"]
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for q in benchmark.queries:
            for cid in sorted(candidates[q.query_id]):
                if cid not in benchmark.chunks:
                    raise ValueError(f"{q.query_id}: 复核候选无法定位 {cid}")
                c = benchmark.chunks[cid]
                writer.writerow({"query_id": q.query_id, "dimension": q.dimension,
                                 "query": q.query, "chunk_id": cid, "doc_title": c.doc_title,
                                 "doc_date": benchmark.documents[c.doc_id]["date"],
                                 "source": c.source, "stored_clause_no": c.clause_no,
                                 "owner_clause_no": c.meta["owner_clause_no"],
                                 "is_clause_heading": c.meta["is_clause_heading"],
                                 "truncated": c.meta["truncated"],
                                 "text_sha256": hashlib.sha256(c.text.encode()).hexdigest(),
                                 "text": c.text})
                count += 1
    return count
