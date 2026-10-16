"""
稠密向量检索

默认 Qwen3-Embedding（sentence-transformers 本地加载，归一化后点积=余弦）。
embedding_backend=bge 时兼容 BGE-M3；embedding_backend=tfidf 时降级为
TF-IDF 余弦（供无法下载模型时的冒烟测试）；embedding_backend=api 时调用
远端 OpenAI 兼容嵌入服务（vLLM / Xinference / Ollama 的 /v1/embeddings），
适合模型部署在另一台机器、本机只做评测的场景。

"""
import json
import hashlib
import urllib.request
from collections import OrderedDict

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
                 base_url: str = "", api_key: str = "", batch_size: int = 32,
                 query_prompt: str = "", max_seq_length: int | None = None,
                 model_runtime=None, revision: str | None = None):
        if batch_size < 1:
            raise ValueError("batch_size 必须为正数")
        if max_seq_length is not None and max_seq_length < 1:
            raise ValueError("max_seq_length 必须为正数")
        self.chunks = chunks
        self.backend = backend
        self.query_prompt = query_prompt if backend != "tfidf" else ""
        self._runtime = model_runtime
        self._model = None
        self._model_name, self._device = model_name, device
        self._revision, self._max_seq_length = revision, max_seq_length
        self._batch_size = batch_size
        self._query_cache = OrderedDict()
        self.encoding_metadata = {"backend": backend, "batch_size": batch_size,
                                  "query_prompt": self.query_prompt,
                                  "query_prompt_sha256": hashlib.sha256(self.query_prompt.encode()).hexdigest(),
                                  "document_prompt": "", "normalize_embeddings": True}
        if backend in ("bge", "qwen"):
            # sentence-transformers 统一加载：BGE-M3 / 本项目固定 Qwen3-Embedding-0.6B
            # 查询指令显式配置；文档不添加指令，也不继承模型的默认 prompt。
            encode_documents = lambda texts: self._encode_model(texts, "")
            self._encode = self._encode_local_queries
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
            encode_documents = lambda texts: _api_embed(
                texts, base_url, model_name, api_key, batch_size)
            self._encode = lambda texts: encode_documents([self.query_prompt + t for t in texts])
        else:
            raise ValueError(f"未知嵌入后端: {backend}")
        self._sparse = backend == "tfidf"

        if backend in ("bge", "qwen", "api"):
            self._matrix = encode_documents([c.text for c in chunks])

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        """按当前查询指令与批量设置编码查询；文档向量使用独立的无指令路径。"""
        return self._encode(texts)

    def _load_weights(self):
        from sentence_transformers import SentenceTransformer
        kwargs = {"revision": self._revision} if self._revision else {}
        self._model = SentenceTransformer(self._model_name, device=self._device, **kwargs)
        if self._max_seq_length is not None:
            if self._max_seq_length > self._model.max_seq_length:
                self._model = None
                raise ValueError("max_seq_length 超过模型支持的长度")
            self._model.max_seq_length = self._max_seq_length
        self.encoding_metadata.update(max_seq_length=self._model.max_seq_length,
                                      device=str(self._model.device), requested_revision=self._revision,
                                      model_dtype=str(next(self._model.parameters()).dtype))
        first = self._model._first_module() if hasattr(self._model, '_first_module') else None
        config = getattr(getattr(first, 'auto_model', None), 'config', None)
        self.encoding_metadata['resolved_revision'] = getattr(config, '_commit_hash', None)

    def _unload_weights(self):
        self._model = None

    def _encode_model(self, texts, prompt):
        if self._runtime is not None:
            self._runtime.acquire(self)
        elif self._model is None:
            self._load_weights()
        return self._model.encode(texts, prompt=prompt, normalize_embeddings=True,
                                  batch_size=self._batch_size)

    def _encode_local_queries(self, texts):
        if not texts:
            return np.empty((0, self._matrix.shape[1]), dtype=np.float32)
        self.encoding_metadata.update(query_prompt=self.query_prompt,
            query_prompt_sha256=hashlib.sha256(self.query_prompt.encode()).hexdigest())
        keys = [(self.query_prompt, text) for text in texts]
        missing = list(dict.fromkeys(key for key in keys if key not in self._query_cache))
        fresh = {}
        if missing:
            vectors = self._encode_model([key[1] for key in missing], self.query_prompt)
            fresh = {key: vector for key, vector in zip(missing, vectors)}
        result = np.stack([self._query_cache[key] if key in self._query_cache else fresh[key] for key in keys])
        for key, vector in fresh.items():
            self._query_cache[key] = np.array(vector, copy=True)
        while len(self._query_cache) > 256:
            self._query_cache.popitem(last=False)
        return result

    def search(self, query: str, top_k: int = 5) -> list[tuple[Chunk, float]]:
        q_vec = self._encode([query])
        if self._sparse:
            scores = (self._matrix @ q_vec.T).toarray().ravel()
        else:
            scores = self._matrix @ q_vec[0]
        idx = np.argsort(-scores)[:top_k]
        return [(self.chunks[i], float(scores[i])) for i in idx]
