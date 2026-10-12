"""
冒烟测试：不下载模型、不调 API，验证全流程可运行
运行：python -m pytest tests/test_smoke.py -v  或  python tests/test_smoke.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.alignment.citation_alignment import align_citations, citation_stats
from src.config import load_config, ROOT
from src.data.clause_splitter import split_document
from src.data.eval_dataset import load_company_samples, load_retrieval_queries
from src.data.knowledge_loader import load_documents
from src.generation.evaluator import Evaluator
from src.metrics.retrieval_metrics import ndcg_at_k, recall_at_k, reciprocal_rank
from src.pipeline import build_knowledge_index, make_llm, make_router


def test_clause_splitting():
    docs = load_documents(ROOT / "data" / "knowledge_base")
    chunks = [c for d in docs for c in split_document(d, "clause")]
    assert len(chunks) >= 8
    # 法规类文档条款号解析率应较高（处罚/通报类无"第X条"结构，允许整块）
    reg_chunks = [c for c in chunks if c.doc_id in {d["doc_id"] for d in docs if d["doc_type"] == "regulation"}]
    ratio = sum(1 for c in reg_chunks if c.clause_no) / max(len(reg_chunks), 1)
    assert ratio > 0.8, f"法规条款号解析率 {ratio:.2%} 过低"
    window = [c for d in docs for c in split_document(d, "window", window_size=100, overlap=20)]
    assert len(window) > len(chunks)


def test_retrieval_pipeline():
    cfg = load_config()
    cfg["retrieval"]["embedding_backend"] = "tfidf"
    cfg["retrieval"]["reranker"]["enabled"] = False
    chunks, retriever = build_knowledge_index(cfg)
    router = make_router(retriever)
    queries = load_retrieval_queries(ROOT / "data" / "annotation" / "retrieval_queries.csv")
    assert queries
    hits = router.search(queries[0].dimension, queries[0].query, 5, routed=True)
    ranked = [c.chunk_id for c, _ in hits]
    assert len(ranked) > 0
    assert 0 <= recall_at_k(ranked, queries[0].relevant, 5) <= 1


def test_generation_mock_and_alignment():
    cfg = load_config()
    cfg["retrieval"]["embedding_backend"] = "tfidf"
    cfg["retrieval"]["reranker"]["enabled"] = False
    chunks, retriever = build_knowledge_index(cfg)
    router = make_router(retriever)
    llm = make_llm(cfg, mock=True)
    evaluator = Evaluator(llm)
    samples = load_company_samples(ROOT / "data" / "companies")
    facts = samples[0]["dimensions"]["D1"]
    hits = router.search("D1", facts[:200], 5, routed=True)
    regs = router.format_for_prompt(hits)
    result = evaluator.evaluate("ours", "示例银行", "000001", 2025, "信息披露质量", facts, regs)
    citations = result.get("citations", []) + result.get("inline_citations", [])
    aligned = align_citations(citations, hits)
    stats = citation_stats(aligned)
    assert stats["n_citations"] >= 1
    assert stats["citation_accuracy"] == 1.0  # mock 引用必在检索结果中


if __name__ == "__main__":
    test_clause_splitting()
    test_retrieval_pipeline()
    test_generation_mock_and_alignment()
    print("SMOKE TESTS PASSED")
