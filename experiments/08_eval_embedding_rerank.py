"""实验08：用合成评测集测评 Embedding 与 Reranker（对应 RQ1 的模型选型环节）。

输入 07 生成的 data/annotation/synth_eval_embedding.csv，分两段测评：
  A. Embedding 段：仅用稠密/稀疏检索，计算 Recall@1/5/10、MRR、nDCG@10
  B. Reranker 段：取检索 top-20 作为候选池，用交叉编码器重排后再算同一组指标
两段差值即 reranker 带来的增益，可直接写进论文实验表。

用法（Mac 本地）：
  # 1) 基线 embedding 测评（Qwen3-Embedding-4B，mps）
  python3 experiments/08_eval_embedding_rerank.py --backend qwen \
      --model Qwen/Qwen3-Embedding-4B --device mps --no-rerank

  # 2) embedding + reranker 完整测评
  python3 experiments/08_eval_embedding_rerank.py --backend qwen \
      --model Qwen/Qwen3-Embedding-4B --device mps \
      --reranker-model Qwen/Qwen3-Reranker-0.6B

  # 3) 离线冒烟（无模型下载）：TF-IDF + 不重排
  python3 experiments/08_eval_embedding_rerank.py --backend tfidf --no-rerank

  # 4) 模型部署在另一台电脑：api 后端直连远端服务（本机零显存占用）
  python3 experiments/08_eval_embedding_rerank.py --backend api \
      --base-url http://192.168.1.10:8000/v1 --model Qwen3-Embedding-4B \
      --reranker-url http://192.168.1.10:9997/v1 --reranker-model Qwen3-Reranker-0.6B

输出：
  results/embed_rerank_eval_summary.csv   每配置一行聚合指标
  results/embed_rerank_eval_detail.csv    每查询一行，便于错误分析
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.clause_splitter import split_document
from src.data.knowledge_loader import load_documents
from src.metrics.retrieval_metrics import aggregate, ndcg_at_k, recall_at_k, reciprocal_rank
from src.retrieval.dense import DenseRetriever

K_LIST = (1, 5, 10)
RERANK_POOL = 20  # rerank 候选池深度


def load_synth_queries(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(
                {
                    "query_id": r["query_id"],
                    "dimension": r["dimension"],
                    "query": r["query"],
                    "positive": r["positive_chunk_id"],
                }
            )
    return rows


def metrics_row(ranked_ids: list[str], relevant: set[str]) -> dict:
    return {
        **{f"recall@{k}": recall_at_k(ranked_ids, relevant, k) for k in K_LIST},
        "mrr": reciprocal_rank(ranked_ids, relevant),
        "ndcg@10": ndcg_at_k(ranked_ids, relevant, 10),
    }


def evaluate(
    queries: list[dict],
    retriever: DenseRetriever,
    reranker=None,
    rerank_pool: int = RERANK_POOL,
) -> tuple[list[dict], dict]:
    """逐查询检索（可选重排），返回明细行与聚合指标。"""
    detail: list[dict] = []
    for q in queries:
        hits = retriever.search(q["query"], top_k=rerank_pool if reranker else max(K_LIST))
        if reranker is not None:
            pool = [c for c, _ in hits]
            scores = reranker.score(q["query"], pool)
            ranked = [c.chunk_id for c, _ in sorted(zip(pool, scores), key=lambda x: x[1], reverse=True)]
        else:
            ranked = [c.chunk_id for c, _ in hits]
        m = metrics_row(ranked, {q["positive"]})
        m.update(
            query_id=q["query_id"],
            dimension=q["dimension"],
            query=q["query"],
            positive=q["positive"],
            top1=ranked[0] if ranked else "",
            hit10=q["positive"] in ranked[:10],
        )
        detail.append(m)
    return detail, aggregate([{k: r[k] for k in ("recall@1", "recall@5", "recall@10", "mrr", "ndcg@10")} for r in detail])


def main() -> None:
    ap = argparse.ArgumentParser(description="合成集测评 embedding 与 reranker")
    ap.add_argument("--queries", default="data/annotation/synth_eval_embedding.csv")
    ap.add_argument("--backend", default="tfidf", choices=["tfidf", "bge", "qwen", "api"])
    ap.add_argument("--model", default="Qwen/Qwen3-Embedding-4B",
                    help="api 后端时填远端服务的模型名，如 Qwen3-Embedding-4B")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--base-url", default="", help="api 后端：远端嵌入服务根地址，如 http://192.168.1.10:8000/v1")
    ap.add_argument("--api-key", default="", help="远端服务密钥（如有），也可走环境变量 EMB_API_KEY")
    ap.add_argument("--no-rerank", action="store_true", help="只测 embedding 段")
    ap.add_argument("--reranker-model", default="Qwen/Qwen3-Reranker-0.6B")
    ap.add_argument("--reranker-device", default=None, help="缺省与 --device 一致")
    ap.add_argument("--reranker-url", default="",
                    help="填则走远端重排服务（如 http://192.168.1.10:9997/v1），忽略本地加载")
    ap.add_argument("--out-dir", default="results")
    args = ap.parse_args()

    queries = load_synth_queries(args.queries)
    print(f"[08] 查询数: {len(queries)}")

    docs = load_documents("data/knowledge_base")
    chunks = [c for d in docs for c in split_document(d)]
    print(f"[08] 语料 chunk 数: {len(chunks)}")

    retriever = DenseRetriever(
        chunks, backend=args.backend, model_name=args.model, device=args.device,
        base_url=args.base_url, api_key=args.api_key or os.environ.get("EMB_API_KEY", ""))

    reranker = None
    if args.reranker_url:
        from src.retrieval.reranker import APIReranker

        reranker = APIReranker(base_url=args.reranker_url, model_name=args.reranker_model,
                               api_key=args.api_key or os.environ.get("EMB_API_KEY", ""))
        print(f"[08] reranker(远端): {args.reranker_url} [{args.reranker_model}]")
    elif not args.no_rerank:
        from src.retrieval.reranker import Reranker

        reranker = Reranker(model_name=args.reranker_model, device=args.reranker_device or args.device)
        print(f"[08] reranker(本地): {args.reranker_model}")

    os.makedirs(args.out_dir, exist_ok=True)
    summary_rows: list[dict] = []

    # A 段：纯 embedding（top-k 直接截断）
    detail_a, agg_a = evaluate(queries, retriever, reranker=None)
    agg_a.update(stage="embedding_only", backend=args.backend, model=args.model, n_queries=len(queries))
    summary_rows.append(agg_a)
    print(f"[08] embedding_only: {agg_a}")

    # B 段：embedding 召回 + reranker 重排
    detail_b = []
    if reranker is not None:
        detail_b, agg_b = evaluate(queries, retriever, reranker=reranker)
        agg_b.update(stage="with_reranker", backend=args.backend, model=args.reranker_model, n_queries=len(queries))
        summary_rows.append(agg_b)
        print(f"[08] with_reranker: {agg_b}")
        delta = {k: round(agg_b[k] - agg_a[k], 4) for k in ("recall@1", "recall@5", "recall@10", "mrr", "ndcg@10")}
        print(f"[08] reranker 增益: {delta}")

    summary_path = os.path.join(args.out_dir, "embed_rerank_eval_summary.csv")
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        w.writerows(summary_rows)

    detail_path = os.path.join(args.out_dir, "embed_rerank_eval_detail.csv")
    with open(detail_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(detail_a[0].keys()) + ["stage"])
        w.writeheader()
        for r in detail_a:
            w.writerow({**r, "stage": "embedding_only"})
        for r in detail_b:
            w.writerow({**r, "stage": "with_reranker"})

    print(f"[08] 输出: {summary_path} / {detail_path}")


if __name__ == "__main__":
    main()
