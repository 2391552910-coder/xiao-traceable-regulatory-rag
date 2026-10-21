"""加载真实 embedding，验证向量与小规模检索；下载受阻时明确失败，不切换 TF-IDF。"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import load_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="Hugging Face 模型名或已有本地权重目录")
    parser.add_argument("--device", default=None)
    parser.add_argument("--out", default="results/runs/embedding_0_6b_20261013/deployment_test.json")
    args = parser.parse_args()
    cfg = load_config()["retrieval"]
    model_name = args.model or cfg["embedding_model"]
    device = args.device or cfg["embedding_device"]
    out = Path(args.out)
    report = {"tested_at_utc": datetime.now(timezone.utc).isoformat(),
              "model": model_name, "backend": "qwen", "device": device,
              "test_scope": "real model loading, normalized vectors, 3-chunk retrieval",
              "status": "started", "model_loaded": False, "inference_executed": False,
              "reranker_tested": False, "versions": {}}
    start = time.perf_counter()
    try:
        for package in ("torch", "transformers", "sentence-transformers", "numpy"):
            report["versions"][package] = importlib.metadata.version(package)
        import torch
        from sentence_transformers import SentenceTransformer
        from transformers import AutoConfig

        torch.set_num_threads(min(4, os.cpu_count() or 1))
        torch.manual_seed(42)
        report["cuda_available"] = torch.cuda.is_available()
        # 明确检查安装的 Transformers 能识别 Qwen3，不需下载权重。
        report["qwen3_architecture_supported"] = AutoConfig.for_model("qwen3").model_type == "qwen3"
        local = Path(model_name).is_dir()
        if not local:
            probe = f"https://huggingface.co/{model_name}/resolve/main/config.json"
            try:
                req = urllib.request.Request(probe, method="HEAD")
                with urllib.request.urlopen(req, timeout=10) as response:
                    report["download_probe"] = {"url": probe, "status": response.status}
            except (urllib.error.URLError, TimeoutError) as error:
                report["download_probe"] = {"url": probe, "error": str(error)}
                # 先尝试已有缓存。不能通过其他域名绕过当前下载拒绝。
                try:
                    SentenceTransformer(model_name, device=device, local_files_only=True)
                except Exception as cache_error:
                    report["cache_load_error"] = str(cache_error)
                    report["status"] = "blocked_model_download"
                    return 2
                report["using_cached_weights"] = True
        from src.data.clause_splitter import split_document
        from src.data.knowledge_loader import load_documents
        from src.retrieval.dense import DenseRetriever
        import numpy as np

        chunks = {c.chunk_id: c for d in load_documents(ROOT / "data/knowledge_base")
                  for c in split_document(d)}
        sample = [chunks[cid] for cid in ("DOC007-C086", "DOC007-C057", "DOC007-C059")]
        retriever = DenseRetriever(sample, backend="qwen", model_name=model_name,
                                   device=device, batch_size=1)
        report["model_loaded"] = True
        matrix = retriever._matrix
        report["vector_shape"] = list(matrix.shape)
        report["vector_norms"] = np.linalg.norm(matrix, axis=1).tolist()
        if matrix.ndim != 2 or matrix.shape[0] != 3 or not np.isfinite(matrix).all():
            raise ValueError("向量维度或数值无效")
        if not np.allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=1e-4):
            raise ValueError("向量未正确归一化")
        exact = retriever.search(sample[0].text, top_k=1)
        if not exact or exact[0][0].chunk_id != sample[0].chunk_id:
            raise ValueError("相同文本检索未返回自身")
        hits = retriever.search("上市公司年度报告应在多长时间内披露？", top_k=3)
        report["query"] = "上市公司年度报告应在多长时间内披露？"
        report["hits"] = [{"chunk_id": c.chunk_id, "score": score} for c, score in hits]
        report["inference_executed"] = True
        report["status"] = "passed"
        return 0
    except Exception as error:
        report["status"] = "failed"
        report["error_type"] = type(error).__name__
        report["error"] = str(error)
        return 1
    finally:
        report["elapsed_seconds"] = round(time.perf_counter() - start, 3)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
