"""
端到端流水线：知识库构建 → 检索 → 评价生成 → 证据对齐 → 评测汇总
"""
from src.config import load_config
from src.data.clause_splitter import split_document
from src.data.knowledge_loader import load_documents
from src.generation.llm_client import LLMClient
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.router import DimensionRoutedRetriever
from src.retrieval.model_runtime import SequentialModelRuntime


def build_knowledge_index(cfg: dict, chunking: str | None = None):
    """加载语料并按指定策略切分，构建混合检索器"""
    kb_cfg = cfg["knowledge_base"]
    strategy = chunking or kb_cfg["chunking"]
    docs = load_documents(kb_cfg["path"])
    chunks = []
    for doc in docs:
        chunks.extend(split_document(doc, strategy=strategy,
                                     window_size=kb_cfg["window_size"],
                                     window_overlap=kb_cfg["window_overlap"]))
    ret_cfg = cfg["retrieval"]
    runtime = SequentialModelRuntime()
    reranker = None
    rr_cfg = ret_cfg.get("reranker") or {}
    if rr_cfg.get("enabled"):
        if rr_cfg.get("url"):  # 远端重排服务（Xinference / vLLM / TEI 兼容）
            from src.retrieval.reranker import APIReranker
            reranker = APIReranker(base_url=rr_cfg["url"],
                                   model_name=rr_cfg.get("model", "Qwen3-Reranker-0.6B"),
                                   api_key=rr_cfg.get("api_key", ""))
        else:
            from src.retrieval.reranker import Reranker
            reranker = Reranker(model_name=rr_cfg.get("model", "Qwen/Qwen3-Reranker-0.6B"),
                                device=rr_cfg.get("device", "cpu"), model_runtime=runtime,
                                revision=rr_cfg.get("revision"),
                                max_length=rr_cfg.get("max_length", 8192),
                                batch_size=rr_cfg.get("batch_size", 1))
    retriever = HybridRetriever(
        chunks, vector_weight=ret_cfg["vector_weight"],
        reranker=reranker,
        rerank_pool_factor=rr_cfg.get("pool_factor", 4),
        backend=ret_cfg["embedding_backend"],
        model_name=ret_cfg["embedding_model"],
        device=ret_cfg.get("embedding_device", "cpu"),
        base_url=ret_cfg.get("embedding_base_url", ""),
        api_key=ret_cfg.get("embedding_api_key", ""),
        batch_size=ret_cfg.get("embedding_batch_size", 32),
        query_prompt=ret_cfg.get("embedding_query_prompt", ""),
        max_seq_length=ret_cfg.get("embedding_max_seq_length"),
        model_runtime=runtime, revision=ret_cfg.get("embedding_revision"),
    )
    return chunks, retriever


def make_llm(cfg: dict, mock: bool | None = None) -> LLMClient:
    llm_cfg = cfg["llm"]
    return LLMClient(base_url=llm_cfg["base_url"], api_key=llm_cfg["api_key"],
                     model=llm_cfg["model"], temperature=llm_cfg["temperature"],
                     mock=mock if mock is not None else llm_cfg["mock"])


def make_router(retriever: HybridRetriever) -> DimensionRoutedRetriever:
    return DimensionRoutedRetriever(retriever)
