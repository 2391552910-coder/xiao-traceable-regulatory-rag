"""
评价生成器：按模式组装提示词 → 调用大模型 → 解析结果 → 抽取引用

引用抽取双通道：
1. 模型自报 JSON citations 字段（ours 模式）；
2. 评价正文正则扫描 【依据：《X》第Y条】（三模式通用，用于交叉核验）。
"""
import re

from src.generation.llm_client import LLMClient, parse_json
from src.generation.prompts import PROMPT_BY_MODE

CITATION_PATTERN = re.compile(r"【依据：\s*《(.+?)》\s*(第[一二三四五六七八九十百千零0-9]+条(?:之[一二三四五六七八九十0-9]+)?)?】")
EVIDENCE_CITATION_PATTERN = re.compile(r"【(年报|法规)依据：\s*\[([AR]\d+)\]】")
EVIDENCE_ID_PATTERN = re.compile(r"^\[([AR]\d+)\]", re.MULTILINE)


class Evaluator:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def evaluate(self, mode: str, stock_name: str, stock_code: str, year: int,
                 dimension_name: str, facts: str = "", regulations: str = "",
                 annual_evidence: str | None = None,
                 query: str | None = None,
                 supplied_evidence_ids: set[str] | None = None) -> dict:
        template = PROMPT_BY_MODE[mode]
        prompt = template.format(
            stock_name=stock_name, stock_code=stock_code, year=year,
            dimension_name=dimension_name,
            user_question=query or f"请评价{dimension_name}维度的公司表现。",
            annual_evidence=annual_evidence if annual_evidence is not None else facts,
            regulations=regulations,
        )
        raw = self.llm.chat(prompt)
        result = parse_json(raw)
        result["raw"] = raw
        result["mode"] = mode
        result["inline_citations"] = self.extract_inline_citations(
            result.get("evaluation", ""))
        # The no-RAG template does not include either evidence argument.  An ID
        # from a retrieved but undisclosed source must not resolve as supplied.
        if mode == "no_rag":
            supplied_ids = set()
            id_method = "no_evidence_in_prompt"
        elif supplied_evidence_ids is not None:
            supplied_ids = set(supplied_evidence_ids)
            id_method = "explicit_retrieval_ids"
        else:
            supplied_ids = set(EVIDENCE_ID_PATTERN.findall(
                (annual_evidence if annual_evidence is not None else facts) + "\n" + regulations))
            id_method = "text_pattern_fallback"
        raw_citations = result.get("citations")
        malformed_indices = ([i for i, item in enumerate(raw_citations)
                              if not isinstance(item, dict)
                              or not isinstance(item.get("evidence_id"), str)
                              or not item["evidence_id"]]
                             if isinstance(raw_citations, list) else [])
        citations = result.get("citations", [])
        if not isinstance(citations, list):
            citations = []
        result["citation_id_audit"] = [
            {"evidence_id": str(item.get("evidence_id", "")),
             "resolves_to_supplied_evidence": str(item.get("evidence_id", "")) in supplied_ids}
            for item in citations if isinstance(item, dict)
        ]
        result["inline_citation_id_audit"] = [
            {**item, "resolves_to_supplied_evidence": item["evidence_id"] in supplied_ids}
            for item in result["inline_citations"] if item.get("evidence_id")
        ]
        if annual_evidence is not None:
            claims = result.get("claims")
            claim_rows = claims if isinstance(claims, list) else []
            malformed_claim_indices = []
            unresolved_claim_ids = set()
            supported_claims_without_resolved_ids = []
            for index, claim in enumerate(claim_rows):
                ids = claim.get("evidence_ids") if isinstance(claim, dict) else None
                if not isinstance(ids, list) or any(not isinstance(item, str) or not item for item in ids):
                    malformed_claim_indices.append(index)
                if isinstance(ids, list):
                    unresolved_claim_ids.update(item for item in ids
                                                if isinstance(item, str) and item not in supplied_ids)
                if (isinstance(claim, dict) and claim.get("evidence_status") == "supported"
                        and not (isinstance(ids, list) and any(
                            isinstance(item, str) and item in supplied_ids for item in ids))):
                    supported_claims_without_resolved_ids.append(index)
            result["citation_diagnostics"] = {
                "supplied_id_method": id_method,
                "citation_list_valid": isinstance(raw_citations, list),
                "malformed_citation_indices": malformed_indices,
                "unresolved_declared_ids": sorted({item["evidence_id"]
                    for item in result["citation_id_audit"]
                    if not item["resolves_to_supplied_evidence"]}),
                "unresolved_inline_ids": sorted({item["evidence_id"]
                    for item in result["inline_citation_id_audit"]
                    if not item["resolves_to_supplied_evidence"]}),
                "claims_list_valid": isinstance(claims, list),
                "malformed_claim_evidence_indices": malformed_claim_indices,
                "unresolved_claim_ids": sorted(unresolved_claim_ids),
                "supported_claims_without_resolved_ids": supported_claims_without_resolved_ids,
                "inline_source_type_mismatches": [item for item in result["inline_citations"]
                    if item.get("evidence_id") and
                    ((item["source_type"] == "annual_report") != item["evidence_id"].startswith("A"))],
                "semantic_support_verified": False,
                "legal_applicability_verified": False,
            }
        return result

    @staticmethod
    def extract_inline_citations(text: str) -> list[dict]:
        """Extract legacy law citations and source-addressed A/R evidence IDs."""
        citations = [{"title": m.group(1), "clause": m.group(2)}
                     for m in CITATION_PATTERN.finditer(text)]
        citations.extend({"source_type": "annual_report" if m.group(1) == "年报" else "regulation",
                          "evidence_id": m.group(2)}
                         for m in EVIDENCE_CITATION_PATTERN.finditer(text))
        return citations
