"""
稠密向量检索

默认 Qwen3-Embedding（sentence-transformers 本地加载，归一化后点积=余弦）。
embedding_backend=bge 时兼容 BGE-M3；embedding_backend=tfidf 时降级为
TF-IDF 余弦（供无法下载模型时的冒烟测试）；embedding_backend=api 时调用
远端 OpenAI 兼容嵌入服务（vLLM / Xinference / Ollama 的 /v1/embeddings），
适合模型部署在另一台机器、本机只做评测的场景。

"""
import json
import urllib.request

import numpy as np

from src.data.clause_splitter import Chunk


def _api_embed(texts: list[str], base_url: str, model: str,
               api_key: str = "", batch_size: int = 32) -> np.ndarray:
    """调用 OpenAI 兼容 /embeddings 接口，返回归一化向量矩阵"""
    url = base_url.rstrip("/") + "/embeddings"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    vecs: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        payload = json.dumps({"model": model, "input": texts[i:i + batch_size]}).encode()
        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        vecs.extend(d["embedding"] for d in sorted(data["data"], key=lambda x: x["index"]))
    arr = np.asarray(vecs, dtype=np.float32)
    return arr / np.linalg.norm(arr, axis=1, keepdims=True).clip(min=1e-12)


class DenseRetriever:
    def __init__(self, chunks: list[Chunk], backend: str = "bge",
                 model_name: str = "BAAI/bge-m3", device: str = "cpu",
                 base_url: str = "", api_key: str = "", batch_size: int = 32):
        self.chunks = chunks
        self.backend = backend
        if backend in ("bge", "qwen"):
            # sentence-transformers 统一加载：BGE-M3 / 本项目固定 Qwen3-Embedding-0.6B
            # 当前查询/文档编码共用路径；Qwen3 查询指令须按官方示例校正和受控评测
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name, device=device)
            self._encode = lambda texts: self._model.encode(
                texts, normalize_embeddings=True)
        elif backend == "tfidf":
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.preprocessing import normalize as sp_normalize
            from src.retrieval.bm25 import tokenize
            # 限制特征上限 + 保持稀疏矩阵，避免大规模语料下稠密化 OOM
            self._vectorizer = TfidfVectorizer(tokenizer=tokenize,
                                               max_features=60000, min_df=2)
            corpus = [c.text for c in chunks]
            self._matrix = sp_normalize(self._vectorizer.fit_transform(corpus))
            self._sparse = True

            def _encode(texts):
                return sp_normalize(self._vectorizer.transform(texts))
            self._encode = _encode
        elif backend == "api":
            if not base_url:
                raise ValueError("api 后端需传 base_url，如 http://192.168.1.10:8000/v1")
            self._encode = lambda texts: _api_embed(
                texts, base_url, model_name, api_key, batch_size)
        else:
            raise ValueError(f"未知嵌入后端: {backend}")
        self._sparse = backend == "tfidf"

        if backend in ("bge", "qwen", "api"):
            self._matrix = self._encode([c.text for c in chunks])

    def search(self, query: str, top_k: int = 5) -> list[tuple[Chunk, float]]:
        q_vec = self._encode([query])
        if self._sparse:
            scores = (self._matrix @ q_vec.T).toarray().ravel()
        else:
            scores = self._matrix @ q_vec[0]
        idx = np.argsort(-scores)[:top_k]
        return [(self.chunks[i], float(scores[i])) for i in idx]
