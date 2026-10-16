"""真实 Qwen 向量与混合检索的 12 片段/4 查询联调；不替代完整开发基准。"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="完整本地模型目录")
    parser.add_argument("--out-dir", required=True, help="本轮独立输出目录；不覆盖已有文件")
    args = parser.parse_args()
    out = Path(args.out_dir)
    if out.exists():
        raise ValueError(f"输出已存在：{out}")
    out.mkdir(parents=True)
    report = {"tested_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "started", "model_loaded": False, "inference_executed": False,
              "model": str(Path(args.model).resolve()), "device": "cpu", "backend": "qwen",
              "scope": "integration_only; 12 selected chunks, 4 development queries",
              "sample_selection": "two frozen direct positives per query plus four distractors",
              "quality_benchmark": False, "reranker_tested": False,
              "query_instruction_used": False, "batch_size": 1}
    started = time.perf_counter()
    try:
        import numpy as np
        import torch
        from src.config import load_config
        from src.data.benchmark import load_benchmark
        from src.retrieval.hybrid import HybridRetriever
        from scripts.compile_independent_review import check_artifacts

        torch.set_num_threads(min(4, os.cpu_count() or 1))
        torch.manual_seed(42)
        check_artifacts()
        benchmark = load_benchmark(load_config())
        source = ROOT / "data/annotation/reviews/independent_20261013/retrieval_queries_direct.csv"
        report["review_source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        report["baseline_hashes"] = benchmark.hashes
        with source.open(encoding="utf-8-sig", newline="") as f:
            rows = {q["query_id"]: q for q in csv.DictReader(f)}
        queries = []
        ids = []
        for qid in ("Q01", "Q11", "Q21", "Q31"):
            row = rows[qid]
            expected = row["relevant_chunk_ids"].split(";")[:2]
            queries.append({"query_id": qid, "text": row["query"],
                            "selected_direct_positive_ids": expected})
            ids.extend(expected)
        ids.extend(["DOC007-C057", "DOC007-C059", "DOC007-C001", "DOC004-C001"])
        chunks = [benchmark.chunks[cid] for cid in dict.fromkeys(ids)]
        # HybridRetriever forwards embedding options, including batch_size.
        index_started = time.perf_counter()
        retriever = HybridRetriever(chunks, backend="qwen", model_name=args.model,
                                    device="cpu", vector_weight=0.7, batch_size=1)
        report["model_loaded"] = True
        report["index_seconds"] = round(time.perf_counter() - index_started, 3)
        matrix = retriever.dense._matrix
        query_vectors = retriever.dense._encode([q["text"] for q in queries])
        for name, vectors, count in (("document", matrix, len(chunks)),
                                      ("query", query_vectors, len(queries))):
            norms = np.linalg.norm(vectors, axis=1)
            if vectors.shape != (count, 1024) or not np.isfinite(vectors).all():
                raise ValueError(f"{name} 向量维度或数值无效")
            if not np.allclose(norms, 1.0, atol=1e-4):
                raise ValueError(f"{name} 向量未归一化")
            report[f"{name}_vector_shape"] = list(vectors.shape)
            report[f"{name}_norm_range"] = [float(norms.min()), float(norms.max())]
        np.save(out / "document_vectors.npy", matrix, allow_pickle=False)
        np.save(out / "query_vectors.npy", query_vectors, allow_pickle=False)
        sample = [{"chunk_id": c.chunk_id, "doc_id": c.doc_id, "source": c.source,
                   "text": c.text, "text_sha256": hashlib.sha256(c.text.encode()).hexdigest()}
                  for c in chunks]
        (out / "sample.json").write_text(json.dumps({"chunks": sample, "queries": queries},
                                                    ensure_ascii=False, indent=2) + "\n")
        self_checks = []
        for c in chunks:
            hits = retriever.dense.search(c.text, top_k=1)
            passed = hits[0][0].chunk_id == c.chunk_id
            self_checks.append({"chunk_id": c.chunk_id, "top1": hits[0][0].chunk_id,
                                "score": hits[0][1], "passed": passed})
        report["self_retrieval"] = self_checks
        if not all(c["passed"] for c in self_checks):
            raise ValueError("相同文本检索未全部返回自身")
        results = []
        for i, q in enumerate(queries):
            expected = set(q["selected_direct_positive_ids"])
            for name, search in (("dense", retriever.dense.search),
                                  ("bm25", retriever.bm25.search),
                                  ("hybrid", retriever.search)):
                hits = search(q["text"], top_k=3)
                if len(hits) != 3 or len({c.chunk_id for c, _ in hits}) != 3:
                    raise ValueError("返回候选数量或唯一性错误")
                if not all(np.isfinite(score) for _, score in hits):
                    raise ValueError("检索得分包含无效数值")
                if name == "dense":
                    ranked = np.argsort(-(matrix @ query_vectors[i]))[:3]
                    if [chunks[j].chunk_id for j in ranked] != [c.chunk_id for c, _ in hits]:
                        raise ValueError("持久化向量无法复现检索顺序")
                results.append({"query_id": q["query_id"], "query": q["text"],
                                "method": name, "top_k": 3,
                                "hits": [{"chunk_id": c.chunk_id, "score": score,
                                          "selected_direct_positive": c.chunk_id in expected}
                                         for c, score in hits],
                                "top1_selected_direct_positive": hits[0][0].chunk_id in expected})
        report["retrieval_results"] = results
        report["inference_executed"] = True
        report["status"] = "passed"
        report["artifacts_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in out.iterdir() if p.is_file()}
        return 0
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__, error=str(error))
        return 1
    finally:
        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        (out / "retrieval_test.json").write_text(json.dumps(report, ensure_ascii=False,
                                                          indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
