"""
混合检索：BM25 稀疏 + 稠密向量，分数归一化后加权融合重排
"""
from src.data.clause_splitter import Chunk
from src.retrieval.bm25 import BM25Retriever
from src.retrieval.dense import DenseRetriever


class HybridRetriever:
    def __init__(self, chunks: list[Chunk], vector_weight: float = 0.7,
                 reranker=None, rerank_pool_factor: int = 4, **dense_kw):
        self.chunks = chunks
        self.vector_weight = vector_weight
        self.reranker = reranker          # 交叉编码精排器（None=不重排）
        self.rerank_pool_factor = rerank_pool_factor
        self.bm25 = BM25Retriever(chunks)
        self.dense = DenseRetriever(chunks, **dense_kw)

    @staticmethod
    def _normalize(hits: list[tuple[Chunk, float]]) -> dict[str, float]:
        if not hits:
            return {}
        max_s = max(s for _, s in hits) or 1.0
        return {c.chunk_id: s / max_s for c, s in hits}

    def search(self, query: str, top_k: int = 5,
               pool: list[Chunk] | None = None) -> list[tuple[Chunk, float]]:
        """
        pool 不为空时只在候选子库内检索（维度路由使用），
        为空时在全库检索。
        """
        candidates = pool or self.chunks
        by_id = {c.chunk_id: c for c in candidates}

        vec_hits = self.dense.search(query, top_k=top_k * 2)
        kw_hits = self.bm25.search(query, top_k=top_k * 2)

        vec_norm = self._normalize([(c, s) for c, s in vec_hits if c.chunk_id in by_id])
        kw_norm = self._normalize([(c, s) for c, s in kw_hits if c.chunk_id in by_id])

        fused: dict[str, float] = {}
        for cid, s in vec_norm.items():
            fused[cid] = fused.get(cid, 0.0) + s * self.vector_weight
        for cid, s in kw_norm.items():
            fused[cid] = fused.get(cid, 0.0) + s * (1 - self.vector_weight)

        ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)

        # 交叉编码精排：取融合分前 top_k * rerank_pool_factor 名，用 reranker 重打分
        if self.reranker is not None and ranked:
            pool = ranked[:top_k * self.rerank_pool_factor]
            rr_scores = self.reranker.score(query, [by_id[cid] for cid, _ in pool])
            ranked = sorted(zip((cid for cid, _ in pool), rr_scores),
                            key=lambda x: x[1], reverse=True)

        return [(by_id[cid], s) for cid, s in ranked[:top_k]]
