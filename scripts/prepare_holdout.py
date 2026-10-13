"""Reserve candidate questions; expose leakage and refuse to certify unreviewed labels.

No retrieval model is run and no final-test metric is computed. The candidates are
AI-authored, not independently human annotated. New wording alone is not independence.
"""
from __future__ import annotations
import argparse
import base64
import csv
import gzip
import io
import json
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_corpus_v2 import read_csv, write_json, write_jsonl
from src.data.benchmark import sha256_file
from src.data.holdout import normalized_query, release_errors

# Provisional semantic families, intentionally not inferred from different query IDs.
SEEDS = [
 ("D1", "earnings_forecast_correction", "公司发现已披露的业绩预告与最新预计结果存在重大差异，如何查找更正披露的依据？"),
 ("D1", "voluntary_disclosure_continuity", "上市公司主动披露经营数据后，后续期间能否任意停止披露同类数据？"),
 ("D1", "trade_secret_exemption", "上市公司主张商业秘密暂缓披露时，需要保留哪些能够核查豁免条件的证据？"),
 ("D1", "investor_relations_records", "投资者调研活动的记录、保存和公开应分别寻找哪些规则依据？"),
 ("D1", "sustainability_scope", "如何确定一家公司是否属于强制披露可持续发展报告的适用主体？"),
 ("D1", "accounting_error_correction", "对前期财务差错进行追溯更正时，如何区分更正程序和当期正常会计估计变更？"),
 ("D2", "cumulative_voting", "选举多名董事采用累积投票时，股东的投票权如何计算和分配？"),
 ("D2", "employee_director", "达到法定职工人数条件的公司，应如何安排职工代表参与董事会？"),
 ("D2", "director_liability_insurance", "公司为董事购买责任保险，相关事项需要向哪个公司机关报告？"),
 ("D2", "related_director_recusal", "关联董事回避后出席人数不足时，关联交易审议应如何继续？"),
 ("D2", "minority_proposal_right", "股东提出临时提案的持股门槛和提交期限，应以哪个时期适用的规则判断？"),
 ("D2", "director_resignation_transition", "董事辞任导致董事会人数低于法定要求时，其职责是否立即终止？"),
 ("D3", "whistleblower_protection", "企业内部举报渠道应如何设计，以保护举报人并跟踪处理结果？"),
 ("D3", "incompatible_duties", "采购付款环节中审批、执行和记账职责由同一人承担，应该检索哪类控制要求？"),
 ("D3", "information_access_control", "离职员工仍保留财务信息系统账号权限，应以哪些控制要求识别风险？"),
 ("D3", "emergency_response", "企业制定突发事件应急预案时，指挥、报告和恢复机制需要哪些证据支持？"),
 ("D3", "outsourcing_controls", "业务外包后，企业应如何证明对承包方的监督责任已经履行？"),
 ("D3", "contract_authorization", "超出授权范围签订重大合同，应如何定位授权审批和合同管理的控制依据？"),
 ("D4", "penalty_event_time", "只找到某公司十年前的处罚决定，能否据此认定该公司在2024年发生相同违规？"),
 ("D4", "absence_of_news", "检索不到负面新闻是否足以证明公司报告期内不存在违法违规行为？"),
 ("D4", "esg_rating_disagreement", "两家评级机构对同一公司的ESG评级不同，需要哪些来源信息才能解释差异？"),
 ("D4", "audit_opinion_scope", "无保留审计意见能否单独证明公司所有治理和合规活动都有效？"),
 ("D4", "penalty_remediation", "公司披露已完成监管整改时，应补充哪些独立证据核验整改结果？"),
 ("D4", "reputation_entity_resolution", "新闻中的公司简称与上市公司相同，如何核验负面事件是否属于同一法律主体？"),
]


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    annotation = ROOT / "data/annotation"
    exposures, historical_queries, inputs = defaultdict(set), [], {}
    for p in sorted(annotation.rglob("*")):
        if not p.is_file() or p.suffix not in {".csv", ".json", ".tsv", ".md", ".base64"}:
            continue
        rel = str(p.relative_to(ROOT))
        inputs[rel] = sha256_file(p)
        text = p.read_text(encoding="utf-8-sig")
        if p.suffix == ".base64":
            text = gzip.decompress(base64.b64decode(text)).decode("utf-8-sig")
        for did in set(re.findall(r"DOC\d+", text)):
            exposures[did].add(rel)
        if p.suffix == ".csv" or p.suffix == ".base64":
            for row in csv.DictReader(io.StringIO(text)):
                if row.get("query"):
                    historical_queries.append(row["query"])
    historical_queries = sorted(set(historical_queries))
    gold = read_csv(annotation / "retrieval_queries_gold.csv")
    rows = []
    for i, (dimension, family, query) in enumerate(SEEDS, 1):
        nearest = sorted(((SequenceMatcher(None, normalized_query(query), normalized_query(q)).ratio(), q)
                          for q in historical_queries), reverse=True)[:3]
        rows.append({"query_id": f"H{i:03d}", "dimension": dimension, "query": query,
                     "family_id": family, "company_id": None,
                     "origin": "ai_authored_candidate", "ai_review": "draft_author_self_check_only",
                     "semantic_leakage_review": "pending_human_family_review",
                     "nearest_historical_queries": [{"similarity": s, "query": q} for s, q in nearest],
                     "lexical_exact_overlap": normalized_query(query) in {normalized_query(q) for q in historical_queries},
                     "evidence_ids": [], "source_verified": False,
                     "human_reviewers": [], "adjudication_status": "not_started", "used_for_tuning": False,
                     "status": "quarantined_candidate_not_final_test"})
    write_jsonl(out / "candidate_queries.jsonl", rows)
    write_jsonl(out / "development_exposure.jsonl", [
        {"doc_id": did, "exposed_in": sorted(paths)} for did, paths in sorted(exposures.items())])
    write_jsonl(out / "development_queries.jsonl", gold)
    # Separate independent blank forms, no gold/AI grades exposed to annotators.
    for tag in ("A", "B"):
        with (out / f"human_review_{tag}.csv").open("w", encoding="utf-8-sig", newline="") as f:
            fields = ["query_id", "dimension", "query", "family_id", "overlaps_development_family",
                      "evidence_id", "source_sha256", "source_start", "source_end", "quote",
                      "relevance_grade", "answerability", "reviewer", "reviewed_at", "reason"]
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row[k] for k in ["query_id", "dimension", "query", "family_id"]})
    errors = release_errors(rows, historical_queries)
    write_json(out / "release_gate.json", {"passed": not errors, "errors": errors})
    manifest = {"status": "quarantined_candidates", "intended_usage": "future_heldout_test",
                "candidate_count": len(rows), "final_test_count": 0, "target_final_queries": 160,
                "development_queries": len(gold), "historical_query_texts": len(historical_queries),
                "exposed_document_ids": len(exposures), "human_labeled_queries": 0,
                "performance_evaluation_run": False, "release_gate_passed": not errors,
                "limitations": ["Lexical similarity cannot certify semantic family separation.",
                                "Source identity, temporal scope and evidence labels remain unverified.",
                                "D4 insufficiency probes extend beyond the existing positive-only retrieval benchmark.",
                                "All future tuning must exclude reserved candidates; release only after independent review."],
                "input_sha256": inputs,
                "code_sha256": {p: sha256_file(ROOT/p) for p in ["scripts/prepare_holdout.py", "src/data/holdout.py"]},
                "artifacts_sha256": {p.name: sha256_file(p) for p in sorted(out.iterdir())}}
    write_json(out / "manifest.json", manifest)
    return {k: v for k, v in manifest.items() if not k.endswith("sha256")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", required=True, type=Path)
    print(json.dumps(build(ap.parse_args().out_dir), ensure_ascii=False, indent=2))
