"""实验 04：同一 gold 证据单元上的切分、维度路由与融合权重消融。"""
import argparse
import gc
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.metrics.benchmark_eval import (
    add_evaluation_arguments, evaluate_queries, prepare_evaluation, save_run, summarize,
)
from src.pipeline import build_knowledge_index, make_router


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_evaluation_arguments(parser)
    args = parser.parse_args()
    cfg, benchmark, output = prepare_evaluation(args, "ablation")
    top_k = cfg["retrieval"]["top_k"]
    threshold = cfg["evaluation"]["coverage_threshold"]
    rows = []
    model_metadata = {}
    for chunking in ("clause", "window"):
        _, retriever = build_knowledge_index(cfg, chunking=chunking)
        router = make_router(retriever)
        for routed in (False, True):
            name = f"{chunking}/routing={routed}"
            rows.extend(evaluate_queries(name, benchmark,
                        lambda q: router.search(q.dimension, q.query, top_k, routed=routed),
                        top_k, threshold, ablation="chunking×routing", chunking=chunking,
                        routing=routed, query_expansion=True,
                        vector_weight=cfg["retrieval"]["vector_weight"], reranker=args.rerank))
        model_metadata[chunking] = {
            "embedding": getattr(getattr(retriever, 'dense', None), 'encoding_metadata', None),
            "reranker": getattr(getattr(retriever, 'reranker', None), 'encoding_metadata', None),
        }
        # Drop both owners before the next index loads model weights. Dense query
        # encoder closures can form cycles, so reference deletion alone is insufficient.
        del router, retriever
        gc.collect()
    _, retriever = build_knowledge_index(cfg, chunking="clause")
    router = make_router(retriever)
    for weight in (0.3, 0.5, 0.7, 0.9):
        retriever.vector_weight = weight
        rows.extend(evaluate_queries(f"weight={weight}", benchmark,
                    lambda q: router.search(q.dimension, q.query, top_k, routed=True),
                    top_k, threshold, ablation="vector_weight", chunking="clause",
                    routing=True, query_expansion=True, vector_weight=weight, reranker=args.rerank))
    model_metadata['weight_sweep'] = {
        "embedding": getattr(getattr(retriever, 'dense', None), 'encoding_metadata', None),
        "reranker": getattr(getattr(retriever, 'reranker', None), 'encoding_metadata', None),
    }
    save_run(output, rows, benchmark, cfg, model_metadata=model_metadata)
    for summary in summarize(rows, top_k):
        print(f"{summary['config']:<24} Recall@{top_k}={summary[f'recall@{top_k}']:.4f} "
              f"MRR@{top_k}={summary['mrr']:.4f}")
    print(f"输出：{output}；滑窗指标为 gold 源文本覆盖代理，正式结论需补充独立语义标注。")


if __name__ == "__main__":
    main()
