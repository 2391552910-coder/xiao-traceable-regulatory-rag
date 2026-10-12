"""
合成评测数据集构建（用于测评 embedding 与 rerank 模型）

数据源：data/knowledge_base/ 全量知识库（315 篇，条款级切分）

产出（data/annotation/）：
  synth_eval_embedding.csv —— embedding 检索评测
      query_id,dimension,query,positive_chunk_id,hard_negative_chunk_ids
      格式与 retrieval_queries.csv 对齐（relevant 即 positive），
      可直接复用 src/metrics/retrieval_metrics.py 的 Recall@k/MRR/nDCG。
  synth_eval_rerank.csv —— rerank 评测（也可作微调样本）
      query_id,query,chunk_id,label,split
      label=1 为合成查询的正例条款，label=0 为难负例（BM25 top-10 未命中 +
      同文档异条款各若干）与随机负例；split ∈ train/dev/test（默认 7/1.5/1.5）。

两种合成模式：
  --mode llm       调用 LLM 为每个条款生成 N 条真实感监管咨询问题（需 LLM_API_KEY）
  --mode template  离线模板法：从条款抽取关键词，套用监管咨询句式（冒烟/打底用）

用法：
  python experiments/07_synth_eval_dataset.py --mode template --n-chunks 200
  python experiments/07_synth_eval_dataset.py --mode llm --n-chunks 400
"""
import argparse
import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jieba

from src.data.clause_splitter import Chunk, split_document
from src.data.knowledge_loader import load_documents
from src.retrieval.bm25 import BM25Retriever, tokenize

STOPWORDS = set("的了和与及或在为对是于以中内其等之上所可以应当不得通过按照进行".split()) | {
    "规定", "相关", "有关", "下列", "情形", "本法", "条例", "办法", "公司", "其他"}

QUERY_TEMPLATES = [
    "《{title}》对{term}是如何规定的？",
    "上市公司在{term}方面需要满足哪些监管要求？",
    "根据《{title}》，{term}应当怎么做？",
    "{term}的监管依据是什么？",
    "《{title}》{clause}关于{term}有哪些要求？",
]

LLM_PROMPT = """你是一名证券监管合规分析师。请阅读下面的法规条款，写出 {n} 条
合规人员在实务中会提出的检索问题。要求：每条问题可以且只能由该条款回答；
句式多样（直接提问/情景描述/引用法规名）；不要出现条款原文超过 10 字的连续片段；
只输出 JSON 数组，如 ["问题1","问题2"]。

【法规】《{title}》{clause}
【条款】{text}"""


def top_terms(text: str, k: int = 5) -> list[str]:
    """从条款文本抽取高频关键词（2 字以上，去停用词）"""
    words = [w for w in tokenize(text) if len(w) >= 2 and w not in STOPWORDS]
    return [w for w, _ in Counter(words).most_common(k)]


def template_queries(chunk: Chunk, n: int, rng: random.Random) -> list[str]:
    terms = top_terms(chunk.text, k=6)
    if not terms:
        return []
    queries, templates = [], rng.sample(QUERY_TEMPLATES, min(n, len(QUERY_TEMPLATES)))
    for i, tpl in enumerate(templates):
        term = terms[i % len(terms)]
        q = tpl.format(title=chunk.doc_title, term=term,
                       clause=chunk.clause_no or "")
        q = re.sub(r"\s+", "", q).replace("》关于", "》中关于")  # 无条款号时去掉空格
        queries.append(q)
    return queries


def llm_queries(chunk: Chunk, n: int, llm) -> list[str]:
    prompt = LLM_PROMPT.format(n=n, title=chunk.doc_title,
                               clause=chunk.clause_no or "", text=chunk.text[:600])
    try:
        raw = llm.chat(prompt)
        arr = json.loads(re.search(r"\[.*\]", raw, re.DOTALL).group(0))
        return [q.strip() for q in arr if isinstance(q, str) and len(q.strip()) >= 6][:n]
    except Exception as e:  # 解析失败降级为模板
        print(f"  [warn] {chunk.chunk_id} LLM 合成失败({e})，降级为模板法")
        return template_queries(chunk, n, random.Random(hash(chunk.chunk_id)))


def mine_hard_negatives(query: str, positive: Chunk, chunks: list[Chunk],
                        bm25: BM25Retriever, by_doc: dict[str, list[Chunk]],
                        neg_k: int, rng: random.Random) -> list[Chunk]:
    """BM25 未命中 top-10 优先，同文档异条款补足，再随机补足"""
    pos_id = positive.chunk_id
    bm25_hits = [c for c, _ in bm25.search(query, top_k=10) if c.chunk_id != pos_id]
    negs = bm25_hits[:neg_k]
    if len(negs) < neg_k:
        sibs = [c for c in by_doc.get(positive.doc_id, []) if c.chunk_id != pos_id]
        rng.shuffle(sibs)
        for c in sibs:
            if len(negs) >= neg_k:
                break
            if c.chunk_id not in {n.chunk_id for n in negs}:
                negs.append(c)
    while len(negs) < neg_k:
        c = rng.choice(chunks)
        if c.chunk_id != pos_id and c.chunk_id not in {n.chunk_id for n in negs}:
            negs.append(c)
    return negs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["llm", "template"], default="template")
    ap.add_argument("--n-chunks", type=int, default=200, help="采样条款数")
    ap.add_argument("--queries-per-chunk", type=int, default=3)
    ap.add_argument("--neg-k", type=int, default=5, help="每条查询的负例数（写入 rerank 集）")
    ap.add_argument("--hard-k", type=int, default=3, help="写入 embedding 集列的难负例数")
    ap.add_argument("--train-ratio", type=float, default=0.7)
    ap.add_argument("--dev-ratio", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-dir", default="data/annotation")
    args = ap.parse_args()
    rng = random.Random(args.seed)

    kb_dir = Path(__file__).resolve().parent.parent / "data" / "knowledge_base"
    docs = load_documents(kb_dir)
    chunks = [c for d in docs for c in split_document(d, "clause")]
    chunks = [c for c in chunks if len(c.text) >= 30]  # 太短条款不适合合成问题
    print(f"知识库 {len(docs)} 篇文档，{len(chunks)} 个可用条款块")

    sampled = rng.sample(chunks, min(args.n_chunks, len(chunks)))
    by_doc: dict[str, list[Chunk]] = {}
    for c in chunks:
        by_doc.setdefault(c.doc_id, []).append(c)
    bm25 = BM25Retriever(chunks)

    llm = None
    if args.mode == "llm":
        import os
        from src.generation.llm_client import LLMClient
        llm = LLMClient(base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1"),
                        api_key=os.environ.get("LLM_API_KEY", ""),
                        model=os.environ.get("LLM_MODEL", "deepseek-chat"),
                        mock=False)

    emb_rows, rr_rows = [], []
    for i, chunk in enumerate(sampled):
        qs = (llm_queries(chunk, args.queries_per_chunk, llm) if llm
              else template_queries(chunk, args.queries_per_chunk, rng))
        for q in qs:
            qid = f"S{len(emb_rows) + 1:05d}"
            negs = mine_hard_negatives(q, chunk, chunks, bm25, by_doc,
                                       args.neg_k, rng)
            emb_rows.append({
                "query_id": qid,
                "dimension": chunk.dimension or "",
                "query": q,
                "positive_chunk_id": chunk.chunk_id,
                "hard_negative_chunk_ids": ";".join(n.chunk_id for n in negs[:args.hard_k]),
            })
            r = rng.random()
            split = ("train" if r < args.train_ratio
                     else "dev" if r < args.train_ratio + args.dev_ratio else "test")
            rr_rows.append({"query_id": qid, "query": q,
                            "chunk_id": chunk.chunk_id, "label": 1, "split": split})
            for n in negs:
                rr_rows.append({"query_id": qid, "query": q,
                                "chunk_id": n.chunk_id, "label": 0, "split": split})
        if (i + 1) % 50 == 0:
            print(f"  已处理 {i + 1}/{len(sampled)} 条款，累计 {len(emb_rows)} 条查询")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    emb_path = out_dir / "synth_eval_embedding.csv"
    with open(emb_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(emb_rows[0].keys()))
        w.writeheader(); w.writerows(emb_rows)
    rr_path = out_dir / "synth_eval_rerank.csv"
    with open(rr_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rr_rows[0].keys()))
        w.writeheader(); w.writerows(rr_rows)
    print(f"完成：{emb_path}（{len(emb_rows)} 条查询）")
    print(f"      {rr_path}（{len(rr_rows)} 条样本，正负比 1:{args.neg_k}）")


if __name__ == "__main__":
    main()
