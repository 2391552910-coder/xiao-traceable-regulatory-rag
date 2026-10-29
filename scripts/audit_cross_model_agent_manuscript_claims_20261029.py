"""Audit saved cross-model, year-stratified, and Agent claims in the DOCX.

This checks numeric consistency and source/version bindings only. It does not
validate answer correctness, the reference answers, semantic citation support,
or generalization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_跨模型与Agent年度分层复算候选稿_待终审.docx"
YEAR_SUMMARY = ROOT / "results/runs/qwen_cross_model_year_sensitivity_20261029_01/year_stratified_summary.json"
YEAR_RECEIPT = ROOT / "results/runs/qwen_cross_model_year_sensitivity_20261029_01/manuscript_update_receipt.json"
RENDER_RECEIPT = ROOT / "results/runs/qwen_cross_model_year_sensitivity_20261029_01/render_qa_receipt.json"
MODEL_SUMMARY = ROOT / "results/runs/qwen_cuda_cross_model_score_20261029_04/summary.json"
MODEL_PROTOCOL = ROOT / "results/runs/qwen_cuda_cross_model_20261029_01/protocol.json"
AGENT_SUMMARY = ROOT / "results/runs/agent_pairs_reanalysis_20261029_01/agent_pair_comparison.json"
AGENT_PAPER_AUDIT = ROOT / "results/runs/agent_pairs_reanalysis_20261029_01/paper_update_audit.json"
DEFAULT_OUTPUT = ROOT / "results/runs/manuscript_claim_consistency_20261029_01/claim_audit.json"
YEAR_ANCHOR = "补充开展跨模型族、跨年度的小样本探索："


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_json_sha256(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def docx_paragraphs(path: Path) -> list[str]:
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find(f"{{{namespace}}}body")
    if body is None:
        raise ValueError("DOCX has no document body")
    paragraphs = []
    for node in body.iter(f"{{{namespace}}}p"):
        text = "".join(item.text or "" for item in node.iter(f"{{{namespace}}}t"))
        if text.strip():
            paragraphs.append(text)
    return paragraphs


def one(items: list[dict], **keys: object) -> dict:
    matches = [item for item in items if all(item.get(k) == v for k, v in keys.items())]
    if len(matches) != 1:
        raise ValueError(f"Expected one row for {keys}, found {len(matches)}")
    return matches[0]


def required(checks: list[dict], name: str, condition: bool, evidence: object) -> None:
    checks.append({"check": name, "passed": bool(condition), "evidence": evidence})
    if not condition:
        raise AssertionError(f"Claim consistency check failed: {name}: {evidence}")


def formatted(row: dict, field: str) -> str:
    return f"{float(row[field]):.3f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    inputs = (
        CANDIDATE,
        YEAR_SUMMARY,
        YEAR_RECEIPT,
        RENDER_RECEIPT,
        MODEL_SUMMARY,
        MODEL_PROTOCOL,
        AGENT_SUMMARY,
        AGENT_PAPER_AUDIT,
    )
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing audit inputs: " + ", ".join(missing))

    year = load_json(YEAR_SUMMARY)
    year_receipt = load_json(YEAR_RECEIPT)
    render_receipt = load_json(RENDER_RECEIPT)
    model = load_json(MODEL_SUMMARY)
    agent = load_json(AGENT_SUMMARY)
    agent_audit = load_json(AGENT_PAPER_AUDIT)
    paragraphs = docx_paragraphs(CANDIDATE)
    checks: list[dict] = []

    candidate_hash = sha256(CANDIDATE)
    year_summary_hash = sha256(YEAR_SUMMARY)
    model_summary_hash = sha256(MODEL_SUMMARY)
    protocol_hash = sha256(MODEL_PROTOCOL)
    agent_summary_hash = sha256(AGENT_SUMMARY)

    required(checks, "candidate_matches_year_update_receipt",
             candidate_hash == year_receipt["output_docx_sha256"],
             {"candidate_sha256": candidate_hash,
              "receipt_sha256": year_receipt["output_docx_sha256"]})
    required(checks, "candidate_matches_render_receipt",
             candidate_hash.lower() == render_receipt["candidate_sha256"].lower(),
             {"candidate_sha256": candidate_hash,
              "render_receipt_sha256": render_receipt["candidate_sha256"]})
    required(checks, "year_summary_matches_update_receipt",
             year_summary_hash == year_receipt["analysis_json_sha256"],
             {"summary_sha256": year_summary_hash,
              "receipt_sha256": year_receipt["analysis_json_sha256"]})
    canonical_year_hash = canonical_json_sha256(year)
    reconciliation = year_receipt.get("analysis_json_line_ending_reconciliation", {})
    required(checks, "year_summary_canonical_hash_matches_receipt",
             canonical_year_hash == year_receipt.get("analysis_json_canonical_sha256"),
             {"canonical_sha256": canonical_year_hash,
              "receipt_sha256": year_receipt.get("analysis_json_canonical_sha256")})
    required(checks, "year_summary_line_ending_reconciliation_is_explicit",
             reconciliation.get("prior_copy") == "CRLF"
             and reconciliation.get("current_copy") == "LF"
             and reconciliation.get("normalized_bytes_identical") is True
             and reconciliation.get("parsed_json_identical") is True,
             reconciliation)
    render_reconciliation = render_receipt.get("analysis_summary_line_ending_reconciliation", {})
    required(checks, "render_receipt_binds_current_year_summary",
             render_receipt.get("analysis_summary_sha256") == year_summary_hash
             and render_receipt.get("analysis_summary_canonical_sha256") == canonical_year_hash,
             {"summary_sha256": year_summary_hash,
              "render_receipt_sha256": render_receipt.get("analysis_summary_sha256"),
              "canonical_sha256": canonical_year_hash,
              "render_receipt_canonical_sha256": render_receipt.get("analysis_summary_canonical_sha256")})
    required(checks, "render_receipt_line_ending_reconciliation_is_explicit",
             render_reconciliation.get("prior_copy") == "CRLF"
             and render_reconciliation.get("current_copy") == "LF"
             and render_reconciliation.get("normalized_bytes_identical") is True
             and render_reconciliation.get("parsed_json_identical") is True,
             render_reconciliation)
    required(checks, "year_summary_binds_model_summary_and_protocol",
             year["source_summary_sha256"] == model_summary_hash
             and year["source_protocol_sha256"] == protocol_hash
             and model["run_protocol_sha256"] == protocol_hash,
             {"year_summary_model_sha256": year["source_summary_sha256"],
              "model_summary_sha256": model_summary_hash,
              "year_protocol_sha256": year["source_protocol_sha256"],
              "protocol_sha256": protocol_hash})
    latest_rerender = render_receipt.get("latest_rerender", {})
    required(checks, "renderer_receipt_is_codex_not_wps",
             render_receipt.get("wps_used") is False
             and render_receipt.get("layout_review_status") == "passed"
             and render_receipt.get("pdf_page_count") == render_receipt.get("rendered_png_count"),
             {"renderer": render_receipt.get("renderer"),
              "wps_used": render_receipt.get("wps_used"),
              "pages": render_receipt.get("pdf_page_count"),
              "layout_review_status": render_receipt.get("layout_review_status")})
    required(checks, "latest_codex_rerender_matches_all_recorded_page_hashes",
             latest_rerender.get("wps_used") is False
             and latest_rerender.get("renderer") == render_receipt.get("renderer")
             and latest_rerender.get("page_png_sha256_match") is True
             and latest_rerender.get("pdf_page_count") == len(render_receipt.get("pages", []))
             and latest_rerender.get("rendered_png_count") == len(render_receipt.get("pages", []))
             and latest_rerender.get("pdf_sha256") == render_receipt.get("pdf_sha256"),
             latest_rerender)

    year_paragraphs = [p for p in paragraphs if p.startswith(YEAR_ANCHOR)]
    required(checks, "unique_year_stratified_paragraph", len(year_paragraphs) == 1,
             {"matches": len(year_paragraphs)})
    year_paragraph = year_paragraphs[0]
    inserted = year_receipt["inserted_text"]
    required(checks, "year_paragraph_matches_recorded_insert",
             year_paragraph.endswith(inserted),
             {"anchor": YEAR_ANCHOR,
              "inserted_text_sha256": hashlib.sha256(inserted.encode("utf-8")).hexdigest()})

    strata = {(x["reference"], int(x["year"]), x["model"]): x for x in year["strata"]}
    year_tokens = []
    for reporting_year in (2023, 2024):
        qwen = strata[("post_output_erratum", reporting_year, "qwen06")]
        k3 = strata[("post_output_erratum", reporting_year, "k3_single")]
        year_tokens.extend([
            f"{formatted(qwen, 'members_f1_macro_nonempty')}/{formatted(k3, 'members_f1_macro_nonempty')}",
            f"{formatted(qwen, 'dates_f1_macro_nonempty')}/{formatted(k3, 'dates_f1_macro_nonempty')}",
            f"{int(round(qwen['meeting_count_exact_macro_nonempty'] * 4))}/4与{int(round(k3['meeting_count_exact_macro_nonempty'] * 4))}/4",
            f"{int(round(qwen['all_three_exact_macro_nonempty'] * 4))}/4与{int(round(k3['all_three_exact_macro_nonempty'] * 4))}/4",
            f"{qwen['malformed_citation_list_entry_count']}",
        ])
        required(checks, f"year_{reporting_year}_stratum_has_four_paired_outputs",
                 qwen["planned_questions"] == qwen["observed_questions"] == 4
                 and k3["planned_questions"] == k3["observed_questions"] == 4
                 and qwen["companies_observed"] == k3["companies_observed"] == 4,
                 {"qwen_questions": qwen["observed_questions"],
                  "k3_questions": k3["observed_questions"],
                  "companies": qwen["companies_observed"]})
    missing_year_tokens = [token for token in year_tokens if token not in year_paragraph]
    required(checks, "year_metrics_match_recomputed_summary", not missing_year_tokens,
             {"missing_tokens": missing_year_tokens})

    summaries = {(x["reference"], x["mode"]): x for x in model["summaries"]}
    qwen = summaries[("post_output_erratum", "qwen06")]
    k3 = summaries[("post_output_erratum", "k3_single")]
    cross_model_paragraphs = [
        p for p in paragraphs
        if "0.651" in p and "0.975" in p and "0.600" in p and "0.953" in p
    ]
    required(checks, "unique_cross_model_paragraph", len(cross_model_paragraphs) == 1,
             {"matches": len(cross_model_paragraphs)})
    cross_model_paragraph = cross_model_paragraphs[0]
    qwen_tokens = [
        formatted(qwen["macro_successful"], "members_f1"),
        formatted(k3["macro_successful"], "members_f1"),
        formatted(qwen["macro_successful"], "dates_f1"),
        formatted(k3["macro_successful"], "dates_f1"),
        f"{int(round(qwen['macro_successful']['meeting_count_exact'] * 8))}/8",
        f"{int(round(k3['macro_successful']['meeting_count_exact'] * 8))}/8",
        f"{int(round(qwen['macro_successful']['schema_valid'] * 8))}/8",
        f"{int(round(k3['macro_successful']['schema_valid'] * 8))}/8",
    ]
    missing_qwen_tokens = [token for token in qwen_tokens if token not in cross_model_paragraph]
    required(checks, "cross_model_metrics_match_saved_outputs", not missing_qwen_tokens
             and qwen["planned"] == qwen["observed"] == 8
             and k3["planned"] == k3["observed"] == 8,
             {"missing_tokens": missing_qwen_tokens,
              "qwen_observed": qwen["observed"], "k3_observed": k3["observed"]})
    required(checks, "cross_model_paragraph_retains_scope_limits",
             all(token in cross_model_paragraph for token in
                 ("非独立裁定", "模型规模", "输出预算不同", "不能证明")),
             {"required_limitations": ["non-adjudicated reference", "unequal model/output budgets",
                                        "no generalization claim"]})

    agent_rows = agent["comparisons"]
    agent_pair = one(agent_rows, reference_version="post_output_erratum", baseline="k3_refine3")
    old_reference_pair = one(agent_rows, reference_version="before_generation", baseline="k3_refine3")
    agent_paragraphs = [p for p in paragraphs if "102600" in p and "97441" in p]
    required(checks, "unique_agent_pair_paragraph", len(agent_paragraphs) == 1,
             {"matches": len(agent_paragraphs)})
    agent_paragraph = agent_paragraphs[0]
    agent_exact = int(round(agent_pair["means"]["three_field_exact"]["agent"]
                            * agent_pair["observed_pairs"]))
    revision_exact = int(round(agent_pair["means"]["three_field_exact"]["baseline"]
                               * agent_pair["observed_pairs"]))
    agent_tokens = [
        formatted(agent_pair["means"]["members_f1"], "agent"),
        formatted(agent_pair["means"]["members_f1"], "baseline"),
        formatted(agent_pair["means"]["dates_f1"], "agent"),
        formatted(agent_pair["means"]["dates_f1"], "baseline"),
        f"{agent_exact}/6", f"{revision_exact}/6",
        str(agent_pair["observed_pairs"]), str(agent_pair["observed_companies"]),
        str(agent_pair["agent_recorded_calls"]), str(agent_pair["baseline_recorded_calls"]),
        str(agent_pair["agent_provider_total_tokens"]), str(agent_pair["baseline_provider_total_tokens"]),
    ]
    post_bounds = agent_pair["full_question_mean_delta_bounds"]["three_field_exact"]
    original_bounds = old_reference_pair["full_question_mean_delta_bounds"]["three_field_exact"]
    bound_tokens = [f"{post_bounds[0]:.3f}", f"{post_bounds[1]:.3f}",
                    f"{original_bounds[0]:.3f}"]
    missing_agent_tokens = [token for token in agent_tokens + bound_tokens if token not in agent_paragraph]
    required(checks, "agent_metrics_and_missing_outcome_bounds_match_summary",
             not missing_agent_tokens
             and agent_pair["observed_pairs"] == 6
             and agent_pair["agent_recorded_calls"] == agent_pair["baseline_recorded_calls"] == 18,
             {"missing_tokens": missing_agent_tokens,
              "post_erratum_bounds": post_bounds,
              "original_reference_bounds": original_bounds})
    required(checks, "agent_paragraph_retains_scope_limits",
             all(token in agent_paragraph for token in
                 ("参考未独立裁定", "样本小", "不能据此断言Agent普遍无效", "未新增模型调用或人工标注")),
             {"required_limitations": ["unadjudicated reference", "small sample",
                                        "no population claim", "no new calls or labels"]})

    source_hashes = {str(path.relative_to(ROOT)): sha256(path) for path in inputs}
    source_candidate_hash = year_receipt["source_docx_sha256"]
    source_hashes_from_agent_audit = agent_audit.get("files_sha256", {})
    required(checks, "year_candidate_parent_matches_agent_audit",
             source_candidate_hash in source_hashes_from_agent_audit.values(),
             {"year_source_docx_sha256": source_candidate_hash,
              "found_in_agent_audit": source_candidate_hash in source_hashes_from_agent_audit.values()})

    report = {
        "audit": "cross-model, year-stratified, and Agent numeric manuscript consistency",
        "candidate_docx": str(CANDIDATE.relative_to(ROOT)),
        "candidate_docx_sha256": candidate_hash,
        "checks_passed": sum(check["passed"] for check in checks),
        "checks_total": len(checks),
        "checks": checks,
        "source_sha256": source_hashes,
        "year_summary_canonical_sha256": canonical_year_hash,
        "year_summary_line_ending_reconciliation": reconciliation,
        "latest_render": latest_rerender,
        "scope": {
            "numeric_claims_match_saved_outputs": True,
            "candidate_version_and_render_receipt_bound": True,
            "full_manuscript_semantic_review": False,
            "independent_reference_validation": False,
            "human_labels_added": False,
            "model_calls_added": False,
            "journal_readiness_established": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise SystemExit(f"Refusing to overwrite existing audit: {args.output}")
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.relative_to(ROOT)),
                      "checks_passed": report["checks_passed"],
                      "checks_total": report["checks_total"],
                      "candidate_sha256": candidate_hash}, ensure_ascii=False))


if __name__ == "__main__":
    main()
