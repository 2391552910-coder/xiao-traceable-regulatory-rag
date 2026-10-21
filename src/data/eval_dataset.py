"""
检索评测集与生成评测输入加载

检索评测集 CSV（data/annotation/retrieval_queries.csv）：
    query_id,dimension,query,relevant_chunk_ids
    - relevant_chunk_ids：人工标注的相关条款 chunk_id，多个用 ; 分隔
    - 双人标注计算 Cohen's Kappa（见 docs/标注规范.md）

生成评测输入 JSON（data/companies/*.json）：
    年报抽取事实样本（真实实验时由第四章系统的抽取模块产出）
"""
import csv
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RetrievalQuery:
    query_id: str
    dimension: str
    query: str
    relevant: set[str]  # 相关 chunk_id 集合


def load_retrieval_queries(path: str | Path) -> list[RetrievalQuery]:
    queries: list[RetrievalQuery] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("query_id"):
                continue
            relevant = {c.strip() for c in row["relevant_chunk_ids"].split(";") if c.strip()}
            queries.append(RetrievalQuery(
                query_id=row["query_id"], dimension=row["dimension"],
                query=row["query"], relevant=relevant,
            ))
    return queries


def load_company_samples(base_dir: str | Path) -> list[dict]:
    samples = []
    for path in sorted(Path(base_dir).glob("*.json")):
        samples.append(json.loads(path.read_text(encoding="utf-8")))
    if not samples:
        raise FileNotFoundError(f"{base_dir} 下未找到公司事实样本")
    return samples
