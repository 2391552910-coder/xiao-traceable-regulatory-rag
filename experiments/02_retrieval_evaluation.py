"""实验 02：冻结 gold 开发基准上的检索对比；默认不加载重排模型。"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.benchmark import export_review
from src.metrics.benchmark_eval import (
    add_evaluation_arguments, evaluate_queries, prepare_evaluation, save_run, summarize,
)
from src.pipeline import build_knowledge_index, make_router


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_evaluation_arguments(parser)
    args = parser.parse_args()
    cfg, benchmark, output = prepare_evaluation(args, "retrieval_eval")
    top_k = cfg["retrieval"]["top_k"]
    if cfg["knowledge_base"]["chunking"] != "clause":
        raise ValueError("主检索对比使用 clause；滑窗对比请运行实验 04")
    _, retriever = build_knowledge_index(cfg)
    router = make_router(retriever)
    reranker = retriever.reranker
    retriever.reranker = None
    setups = [
        ("BM25-only", lambda q: retriever.bm25.search(q.query, top_k), False, False),
        ("Dense-only", lambda q: retriever.dense.search(q.query, top_k), False, False),
        ("Hybrid", lambda q: retriever.search(q.query, top_k), False, False),
        ("Hybrid+QueryExpansion", lambda q: router.search(q.dimension, q.query, top_k, routed=False), True, False),
        ("Hybrid+Routing (Ours)", lambda q: router.search(q.dimension, q.query, top_k, routed=True), True, True),
    ]
    rows = []
    for name, search, expansion, routing in setups:
        rows.extend(evaluate_queries(name, benchmark, search, top_k,
                    cfg["evaluation"]["coverage_threshold"], chunking="clause",
                    routing=routing, query_expansion=expansion, reranker=False))
    if reranker is not None:
        retriever.reranker = reranker
        for name, search, expansion, routing in setups[2:]:
            rows.extend(evaluate_queries(name + " +Reranker", benchmark, search, top_k,
                        cfg["evaluation"]["coverage_threshold"], chunking="clause",
                        routing=routing, query_expansion=expansion, reranker=True))
    candidates = {q.query_id: set() for q in benchmark.queries}
    for row in rows:
        candidates[row["query_id"]].update(json.loads(row["ranked_ids"]))
    export_review(benchmark, output.with_name(output.stem + "_human_review.csv"), candidates)
    save_run(output, rows, benchmark, cfg)
    for summary in summarize(rows, top_k):
        print(f"{summary['config']:<32} Recall@{top_k}={summary[f'recall@{top_k}']:.4f} "
              f"MRR@{top_k}={summary['mrr']:.4f} nDCG@{top_k}={summary[f'ndcg@{top_k}']:.4f}")
    print(f"输出：{output}（含逐查询明细、分维度指标、成对 bootstrap CI、审计与运行元信息）")


if __name__ == "__main__":
    main()
