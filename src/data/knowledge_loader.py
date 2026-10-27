"""
监管知识库加载器

语料格式（data/knowledge_base/*.txt）：
    @DOC_ID: DOC001
    @TITLE: 上市公司信息披露管理办法（节选）
    @TYPE: regulation          # regulation 监管规则 / penalty 处罚案例 / announcement 历史公告
    @SOURCE: 中国证监会
    @DATE: 2021-03-18
    @DIMENSION: D1             # 维度路由标签（可选）
    ---
    第二十一条 年度报告应当在每个会计年度结束之日起四个月内……

---
分隔元信息与正文；文件之间任意数量。
"""
import hashlib
from pathlib import Path

REQUIRED_META = ("DOC_ID", "TITLE", "TYPE", "SOURCE")


def load_document(path: str | Path) -> dict:
    """读取单个原文件；保持既有metadata正文框架及换行口径。"""
    path = Path(path)
    raw = path.read_bytes()
    decoded = raw.decode("utf-8")
    newline_normalization = "crlf_to_lf" if "\r\n" in decoded else "none"
    content = decoded.replace("\r\n", "\n")
    if "\n---\n" not in content:
        raise ValueError(f"{path} 缺少 --- 分隔符")
    meta_raw, text = content.split("\n---\n", 1)
    meta: dict[str, str] = {}
    for line in meta_raw.strip().splitlines():
        line = line.strip()
        if line.startswith("@"):
            key, _, value = line[1:].partition(":")
            meta[key.strip()] = value.strip()
    missing = [k for k in REQUIRED_META if k not in meta]
    if missing:
        raise ValueError(f"{path} 缺少元信息字段: {missing}")
    body = text.strip()
    return {
            "doc_id": meta["DOC_ID"],
            "title": meta["TITLE"],
            "doc_type": meta["TYPE"],
            "source": meta["SOURCE"],
            "date": meta.get("DATE", ""),
            "dimension": meta.get("DIMENSION") or None,
            "text": body,
            "source_file": str(path.resolve()),
            "source_file_sha256": hashlib.sha256(raw).hexdigest(),
            "source_text_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "source_text_newline_normalization": newline_normalization,
            "effective_from": meta.get("EFFECTIVE_FROM") or None,
            "effective_to": meta.get("EFFECTIVE_TO") or None,
            "version_id": meta.get("VERSION_ID") or None,
    }


def load_documents(base_dir: str | Path) -> list[dict]:
    """读取语料目录，返回文档列表"""
    docs = [load_document(path) for path in sorted(Path(base_dir).glob("*.txt"))]
    if not docs:
        raise FileNotFoundError(f"{base_dir} 下未找到任何 .txt 语料文件")
    return docs
