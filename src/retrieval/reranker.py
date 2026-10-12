"""
交叉编码重排器（reranker）

默认 Qwen3-Reranker-0.6B：query-passage 对经序列分类头输出相关性
logit，sigmoid 后为 [0,1] 分数。用于混合检索融合后的精排阶段。

显存参考（fp16）：0.6B ≈ 1.2GB，可在 16GB Apple Silicon 上与
4B embedding 共存；device 建议 mps（Metal），cpu 亦可。

模型部署在另一台机器时，用 APIReranker 走 HTTP 调用，接口与本地
Reranker 完全一致（score(query, chunks) -> list[float]），自动适配
Jina/Xinference/vLLM 的 {"results":[{index, relevance_score}]} 与
TEI 的 [{index, score}] 两种返回格式。
"""
import json
import urllib.request

import torch

from src.data.clause_splitter import Chunk


class Reranker:
    def __init__(self, model_name: str = "Qwen/Qwen3-Reranker-0.6B",
                 device: str = "cpu", max_length: int = 512, batch_size: int = 16):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self._tok = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(
            model_name, torch_dtype="auto", device_map=device)
        self._model.eval()
        self.max_length = max_length
        self.batch_size = batch_size

    @torch.no_grad()
    def score(self, query: str, chunks: list[Chunk]) -> list[float]:
        """返回与 chunks 等长的相关性分数列表"""
        scores: list[float] = []
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i:i + self.batch_size]
            pairs = [[query, c.text] for c in batch]
            enc = self._tok(pairs, padding=True, truncation=True,
                            max_length=self.max_length, return_tensors="pt")
            logits = self._model(**enc.to(self._model.device)).logits
            # Qwen3-Reranker 单输出头；多任务版可用 predict 接口
            scores.extend(torch.sigmoid(logits[:, 0]).float().cpu().tolist())
        return scores


class APIReranker:
    """远端重排服务客户端（Xinference / vLLM / TEI / Jina 兼容）"""

    def __init__(self, base_url: str, model_name: str = "Qwen3-Reranker-0.6B",
                 api_key: str = "", batch_size: int = 32):
        # base_url 指到服务根（如 http://192.168.1.10:9997/v1），自动拼 /rerank
        self._url = base_url.rstrip("/") + "/rerank"
        self._model = model_name
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self.batch_size = batch_size

    def score(self, query: str, chunks: list[Chunk]) -> list[float]:
        scores: list[float] = []
        for i in range(0, len(chunks), self.batch_size):
            docs = [c.text for c in chunks[i:i + self.batch_size]]
            payload = json.dumps(
                {"model": self._model, "query": query, "documents": docs}).encode()
            req = urllib.request.Request(self._url, data=payload, headers=self._headers)
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            # 两种主流返回：{"results":[{index, relevance_score}]} 或 [{index, score}]
            items = data["results"] if isinstance(data, dict) else data
            batch_scores = [0.0] * len(docs)
            for it in items:
                batch_scores[it["index"]] = float(it.get("relevance_score", it.get("score", 0.0)))
            scores.extend(batch_scores)
        return scores
