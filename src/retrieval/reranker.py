"""
交叉编码重排器（reranker）

默认候选 Qwen3-Reranker-0.6B，用于混合检索后的重排。
本地按官方 causal-LM 的 yes/no token 概率评分，按需加载；
离线接口测试不等于真实权重质量实验。

本项目本地 Embedding 与 Reranker 均限定 0.6B；device 可用 mps/cpu/cuda。
权重精度、batch、截断与峰值内存须实测，不以理论权重大小保证主机可运行。

模型部署在另一台机器时，用 APIReranker 走 HTTP 调用，接口与本地
Reranker 完全一致（score(query, chunks) -> list[float]），自动适配
Jina/Xinference/vLLM 的 {"results":[{index, relevance_score}]} 与
TEI 的 [{index, score}] 两种返回格式。
"""
import json
import urllib.request

import hashlib
import numpy as np

from src.data.clause_splitter import Chunk


class Reranker:
    def __init__(self, model_name: str = "Qwen/Qwen3-Reranker-0.6B",
                 device: str = "cpu", max_length: int = 8192, batch_size: int = 1,
                 model_runtime=None, revision: str | None = None,
                 instruction: str = 'Given a web search query, retrieve relevant passages that answer the query'):
        if max_length < 1 or batch_size < 1:
            raise ValueError('max_length and batch_size must be positive')
        if 'Qwen3-Reranker-' in model_name and 'Qwen3-Reranker-0.6B' not in model_name:
            raise ValueError('This project uses Qwen3-Reranker-0.6B')
        self._model_name, self._device, self._revision = model_name, device, revision
        self._runtime, self._model, self._tok = model_runtime, None, None
        self.instruction = instruction
        self.max_length = max_length
        self.batch_size = batch_size
        self.encoding_metadata = {'model':model_name, 'requested_revision':revision,
                                  'scoring':'P(yes | {no, yes}) at final token',
                                  'max_length':max_length, 'batch_size':batch_size,
                                  'instruction_sha256':hashlib.sha256(instruction.encode()).hexdigest(),
                                  'logits_to_keep':1, 'use_cache':False,
                                  'weights_loaded':False}

    def _load_weights(self):
        from transformers import AutoModelForCausalLM, AutoTokenizer
        kwargs = {'revision':self._revision} if self._revision else {}
        self._tok = AutoTokenizer.from_pretrained(self._model_name, padding_side='left', **kwargs)
        self._tok.padding_side = 'left'
        if self._tok.pad_token_id is None:
            self._tok.pad_token = self._tok.eos_token
        prefix = '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
        suffix = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
        self._prefix = self._tok.encode(prefix, add_special_tokens=False)
        self._suffix = self._tok.encode(suffix, add_special_tokens=False)
        self._budget = self.max_length - len(self._prefix) - len(self._suffix)
        if self._budget < 1:
            raise ValueError('max_length cannot fit the reranker template')
        self._no, self._yes = (self._tok.convert_tokens_to_ids(x) for x in ['no', 'yes'])
        if self._no == self._yes or any(i is None or i == self._tok.unk_token_id for i in [self._no,self._yes]):
            raise ValueError('Tokenizer does not expose distinct yes/no tokens')
        self._model = AutoModelForCausalLM.from_pretrained(self._model_name, torch_dtype='auto', **kwargs)
        self._model.to(self._device).eval()
        self.encoding_metadata.update(weights_loaded=True, device=str(self._model.device),
            model_dtype=str(next(self._model.parameters()).dtype),
            resolved_revision=getattr(self._model.config, '_commit_hash', None))

    def _unload_weights(self):
        self._model, self._tok = None, None
        self.encoding_metadata['weights_loaded'] = False

    def score(self, query: str, chunks: list[Chunk]) -> list[float]:
        """返回与 chunks 等长的相关性分数列表"""
        if not chunks:
            return []
        import torch
        if self._runtime is not None:
            self._runtime.acquire(self)
        elif self._model is None:
            self._load_weights()
        scores: list[float] = []
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i:i + self.batch_size]
            texts = [f'<Instruct>: {self.instruction}\n<Query>: {query}\n<Document>: {c.text}' for c in batch]
            tokens = self._tok(texts, padding=False, truncation='longest_first',
                               return_attention_mask=False, max_length=self._budget)
            tokens['input_ids'] = [self._prefix + ids + self._suffix for ids in tokens['input_ids']]
            enc = self._tok.pad(tokens, padding=True, return_tensors='pt', max_length=self.max_length)
            enc = {key: value.to(self._model.device) for key,value in enc.items()}
            with torch.inference_mode():
                logits = self._model(**enc, logits_to_keep=1, use_cache=False).logits[:, -1, :]
                pair = logits[:, [self._no, self._yes]].float().cpu().numpy()
            if not np.isfinite(pair).all():
                raise ValueError('Reranker returned non-finite yes/no logits')
            scores.extend(np.exp(pair[:,1]-np.logaddexp(pair[:,0],pair[:,1])).tolist())
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
