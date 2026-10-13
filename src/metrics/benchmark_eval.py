"""在冻结 gold 证据单元上评测不同切分；所有分数均按检索块的 rank 计。"""
from __future__ import annotations

import csv
import importlib.metadata
import json
import math
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

import numpy as np

from src.config import ROOT
from src.config import load_config
from src.data.benchmark import load_benchmark, resolve_path
from src.data.benchmark import Benchmark, sha256_file, write_json


def union_length(intervals: list[tuple[int, int]]) -> int:
    total, end = 0, -1
    for left, right in sorted(intervals):
        total += max(0, right - max(left, end))
        end = max(end, right)
    return total


def score_evidence(hits, relevant: set[str], gold_chunks: dict, k: int,
                   coverage_threshold: float = 0.5) -> dict:
    """累计源文本覆盖至少阈值才命中。重叠窗口和重复命中不重复贡献增益。

    clause 同一 ID 直接命中；window 以同一文档的字符跨度累计覆盖 gold 可见文本。
    这是已标注证据的覆盖代理，不能替代对滑窗的独立语义标注。
    """
    if k < 1 or not 0 < coverage_threshold <= 1 or not relevant:
        raise ValueError("k、覆盖阈值或正例集无效")
    covered = defaultdict(list)
    matched, gains = set(), []
    for chunk, _ in hits[:k]:
        before = set(matched)
        for cid in relevant - matched:
            gold = gold_chunks[cid]
            if chunk.chunk_id == cid:
                matched.add(cid)
                continue
            # 条款组仍精确匹配历史 C ID，避免改变原标注语义。
            if "-W" not in chunk.chunk_id or gold.doc_id != chunk.doc_id:
                continue
            left = max(chunk.meta["source_start"], gold.meta["source_start"])
            right = min(chunk.meta["source_end"], gold.meta["source_end"])
            if left < right:
                covered[cid].append((left, right))
                length = gold.meta["source_end"] - gold.meta["source_start"]
                if union_length(covered[cid]) / length >= coverage_threshold:
                    matched.add(cid)
        gains.append(int(bool(matched - before)))
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return {f"recall@{k}": len(matched) / len(relevant),
            "mrr": next((1 / (i + 1) for i, g in enumerate(gains) if g), 0.0),
            f"ndcg@{k}": dcg / ideal,
            f"hit@{k}": float(bool(matched)),
            "matched_gold_ids": sorted(matched)}


def evaluate_queries(name, benchmark: Benchmark, search_fn, top_k=5,
                     coverage_threshold=0.5, **settings) -> list[dict]:
    rows = []
    for q in benchmark.queries:
        started = time.perf_counter()
        hits = search_fn(q)[:top_k]
        elapsed = time.perf_counter() - started
        ids = [c.chunk_id for c, _ in hits]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{name}/{q.query_id}: 检索返回重复 chunk_id")
        score = score_evidence(hits, q.relevant, benchmark.chunks, top_k, coverage_threshold)
        matched = score.pop("matched_gold_ids")
        rows.append({"config": name, "query_id": q.query_id, "dimension": q.dimension,
                     **score, **settings, "latency_seconds": elapsed,
                     "ranked_ids": json.dumps(ids),
                     "matched_gold_ids": json.dumps(matched),
                     "relevant_ids": json.dumps(sorted(q.relevant))})
    return rows


def summarize(rows: list[dict], top_k: int, by_dimension=False) -> list[dict]:
    groups = defaultdict(list)
    metrics = [f"recall@{top_k}", "mrr", f"ndcg@{top_k}", f"hit@{top_k}"]
    for row in rows:
        key = (row["config"], row["dimension"] if by_dimension else "all")
        groups[key].append(row)
    result = []
    for (name, dimension), values in groups.items():
        summary = {"config": name}
        if by_dimension:
            summary["dimension"] = dimension
        summary.update(n_queries=len(values), **{
            metric: sum(row[metric] for row in values) / len(values) for metric in metrics})
        for key in ("ablation", "chunking", "routing", "vector_weight", "query_expansion", "reranker"):
            if key in values[0]:
                summary[key] = values[0][key]
        result.append(summary)
    return result


def bootstrap_intervals(rows: list[dict], top_k: int, seed=42, samples=2000) -> list[dict]:
    """按查询成对重采样，同一索引用于每个配置；报告 95% percentile CI。"""
    if samples < 1:
        raise ValueError("bootstrap_samples 必须为正数")
    groups = defaultdict(dict)
    for row in rows:
        if row["query_id"] in groups[row["config"]]:
            raise ValueError("bootstrap 输入存在重复查询")
        groups[row["config"]][row["query_id"]] = row
    reference = next(iter(groups))
    query_ids = sorted(groups[reference])
    if any(set(values) != set(query_ids) for values in groups.values()):
        raise ValueError("各配置的评测查询必须一致")
    indices = np.random.default_rng(seed).integers(0, len(query_ids), (samples, len(query_ids)))
    result = []
    for name, values in groups.items():
        for metric in (f"recall@{top_k}", "mrr", f"ndcg@{top_k}", f"hit@{top_k}"):
            scores = np.array([values[qid][metric] for qid in query_ids])
            base = np.array([groups[reference][qid][metric] for qid in query_ids])
            low, high = np.quantile(scores[indices].mean(axis=1), [.025, .975])
            delta_low, delta_high = np.quantile((scores - base)[indices].mean(axis=1), [.025, .975])
            result.append({"config": name, "metric": metric, "mean": float(scores.mean()),
                           "ci95_low": float(low), "ci95_high": float(high),
                           "reference": reference, "delta_mean": float((scores - base).mean()),
                           "delta_ci95_low": float(delta_low), "delta_ci95_high": float(delta_high)})
    return result


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("不能写入空评测结果")
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def output_paths(summary_path: Path) -> dict[str, Path]:
    stem = summary_path.stem
    return {"summary": summary_path, **{
        name: summary_path.with_name(f"{stem}_{name}.{suffix}")
        for name, suffix in (("detail", "csv"), ("by_dimension", "csv"), ("bootstrap", "csv"),
                             ("run", "json"), ("audit", "json"), ("human_review", "csv"))}}


def ensure_new_output(summary_path: Path) -> None:
    existing = [str(p) for p in output_paths(summary_path).values() if p.exists()]
    if existing:
        raise ValueError(f"输出已存在，请使用新目录以保留历史实验：{existing}")
    summary_path.parent.mkdir(parents=True, exist_ok=True)


def sanitized(value):
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if any(s in k.lower() for s in ("key", "token", "password", "secret"))
                    else sanitized(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitized(v) for v in value]
    return value


def add_evaluation_arguments(parser) -> None:
    parser.add_argument("--config", help="配置路径；自定义基准须提供对应 manifest_path")
    parser.add_argument("--backend", choices=["tfidf", "bge", "qwen", "api"])
    parser.add_argument("--device", help="覆盖 embedding/reranker 的设备")
    parser.add_argument("--queries", help="覆盖查询文件；仍须通过冻结版本校验")
    parser.add_argument("--rerank", action="store_true", help="显式启用精排；默认关闭以隔离检索组件")
    parser.add_argument("--output", help="汇总 CSV；已有实验不会被覆盖")


def prepare_evaluation(args, experiment_name: str):
    cfg = load_config(str(resolve_path(args.config)) if args.config else None)
    if args.backend:
        cfg["retrieval"]["embedding_backend"] = args.backend
    cfg["retrieval"].setdefault("reranker", {})["enabled"] = args.rerank
    if args.device:
        cfg["retrieval"]["embedding_device"] = args.device
        cfg["retrieval"]["reranker"]["device"] = args.device
    if cfg["retrieval"]["top_k"] < 1:
        raise ValueError("top_k 必须为正数")
    threshold = cfg.get("evaluation", {}).get("coverage_threshold", 0.5)
    if not 0 < threshold <= 1:
        raise ValueError("coverage_threshold 必须在 (0, 1] 内")
    benchmark = load_benchmark(cfg, args.queries)
    cfg["knowledge_base"]["path"] = str(benchmark.kb_path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = resolve_path(args.output) if args.output else (
        ROOT / "results/runs" / f"{experiment_name}_{stamp}" / f"{experiment_name}.csv")
    ensure_new_output(output)
    print(f"基准 {benchmark.manifest['benchmark_id']}：{len(benchmark.queries)} 查询；状态 provisional / development_only")
    return cfg, benchmark, output


def save_run(summary_path: Path, rows: list[dict], benchmark: Benchmark, cfg: dict) -> None:
    paths = output_paths(summary_path)
    top_k = cfg["retrieval"]["top_k"]
    evaluation = cfg.get("evaluation", {})
    write_csv(paths["summary"], summarize(rows, top_k))
    write_csv(paths["detail"], rows)
    write_csv(paths["by_dimension"], summarize(rows, top_k, by_dimension=True))
    write_csv(paths["bootstrap"], bootstrap_intervals(
        rows, top_k, cfg["seed"], evaluation.get("bootstrap_samples", 2000)))
    write_json(paths["audit"], benchmark.audit())
    git_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True)
    git_status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                                capture_output=True, text=True)
    versions = {}
    for package in ("numpy", "scikit-learn", "jieba", "sentence-transformers", "transformers", "torch"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    code = {str(p.relative_to(ROOT)): sha256_file(p)
            for folder in ("src", "experiments") for p in sorted((ROOT / folder).rglob("*.py"))}
    from src.retrieval.bm25 import _HAS_JIEBA
    backend = cfg["retrieval"]["embedding_backend"]
    write_json(paths["run"], {
        "schema_version": 1, "status": "provisional", "usage": "development_only",
        "benchmark_hashes": benchmark.hashes,
        "benchmark_id": benchmark.manifest.get("benchmark_id") if benchmark.manifest else None,
        "config": sanitized(cfg), "command": sys.argv,
        "python": platform.python_version(), "packages": versions,
        "git_head": git_head.stdout.strip() or None, "git_dirty": bool(git_status.stdout.strip()),
        "code_sha256": code, "tokenizer": "jieba" if _HAS_JIEBA else "character_bigram_fallback",
        "effective_embedding_model": "TF-IDF" if backend == "tfidf" else cfg["retrieval"]["embedding_model"],
        "metrics": {"cutoff": top_k, "mrr": f"MRR@{top_k} (检索列表截断)",
                    "aggregation": "query_macro_mean", "bootstrap_unit": "query",
                    "bootstrap_samples": evaluation.get("bootstrap_samples", 2000),
                    "coverage_threshold": evaluation.get("coverage_threshold", 0.5),
                    "window_matching": "同文档源跨度累计覆盖 gold 可见文本；重叠去重"},
        "artifacts_sha256": {name: sha256_file(path) for name, path in paths.items()
                             if name != "run" and path.exists()},
    })
