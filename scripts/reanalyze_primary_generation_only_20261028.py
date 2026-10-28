"""Reanalyze human scores after excluding session-authored non-protocol supplements.

The formal generation protocol was the Kimi `k3` API. Thirty-three response
supplements were authored in the current assistant session with no API calls;
they are useful demonstrations but cannot be pooled into the controlled Kimi
comparison. This script preserves the original score artifact and creates a
new, explicitly filtered audit output.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.metrics.compact_paper_statistics import paired_company_statistics, quadratic_kappa

SCORES = ROOT / "results/runs/two_reviewer_statistics_windows_20261023_01/per_output_scores.json"
SUPPLEMENTS = ROOT / "results/runs/compact_final_execution_windows_20261020_01/assistant_supplement_windows_20261020_01/answers_session_supplement.jsonl"
PRIMARY_AUDIT = ROOT / "results/runs/compact_final_execution_windows_20261020_01/failure_recovery_v1/primary_audit.json"
FREEZE = ROOT / "results/runs/paper_execution_freeze_windows_20261020_01/execution_freeze.json"
OUT = ROOT / "results/runs/primary_generation_only_reanalysis_windows_20261028_01"
MAIN_MODES = [
    "merged_corpus_generic_cited_rag",
    "dual_source_generic_cited_rag",
    "dual_source_role_grounded_rag",
]
FIELDS = ["company_facts", "regulation", "citations", "uncertainty"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def company_macro(rows, field):
    by_company = defaultdict(list)
    for row in rows:
        value = row[field]
        if value is not None:
            by_company[row["company"]].append(value)
    means = [sum(vals) / len(vals) for _, vals in sorted(by_company.items())]
    return (sum(means) / len(means) if means else None), len(means)


def main():
    if OUT.exists():
        raise SystemExit(f"Refusing to overwrite existing audit: {OUT}")
    scores = read_json(SCORES)
    supplements = [json.loads(line) for line in SUPPLEMENTS.read_text(encoding="utf-8").splitlines() if line.strip()]
    supplement_keys = {(x["question_id"], x["original_condition"]) for x in supplements}
    freeze = read_json(FREEZE)
    audit = read_json(PRIMARY_AUDIT)
    questions = [
        {"question_id": x["question_id"], "company": x.get("company_cluster", x.get("stock_code"))}
        for x in freeze["grouping"]
    ]
    if len(questions) != 60 or len({q["question_id"] for q in questions}) != 60:
        raise ValueError("Expected the frozen 60-question inventory")
    supplemented_scored = [r for r in scores if (r["question_id"], r["mode"]) in supplement_keys]
    filtered = [r for r in scores if (r["question_id"], r["mode"]) not in supplement_keys]
    if len(supplements) != 33 or len(supplemented_scored) != 31 or len(filtered) != 355:
        raise ValueError("Source counts differ from the audited supplement and score inventories")
    primary_by_mode = Counter(r["mode"] for r in filtered if r["mode"] in MAIN_MODES)
    expected_primary = {
        "merged_corpus_generic_cited_rag": 52,
        "dual_source_generic_cited_rag": 47,
        "dual_source_role_grounded_rag": 48,
    }
    if dict(primary_by_mode) != expected_primary or audit["structured_successful"] != 147:
        raise ValueError(f"Primary generation audit mismatch: {dict(primary_by_mode)}")

    conditions = {}
    modes = sorted({r["mode"] for r in scores})
    for mode in modes:
        rows = [r for r in filtered if r["mode"] == mode]
        item_mean = sum(r["mean"]["total"] for r in rows) / len(rows) if rows else None
        macro, clusters = company_macro(rows, "total") if rows and "total" in rows[0] else (None, 0)
        # Existing per-output file stores the two-reviewer mean in `mean`.
        means_by_company = defaultdict(list)
        for r in rows:
            if r["mean"]["total"] is not None:
                means_by_company[r["company"]].append(r["mean"]["total"])
        company_means = [sum(v) / len(v) for _, v in sorted(means_by_company.items())]
        conditions[mode] = {
            "planned": sum(1 for q in freeze["grouping"] for _ in [0]) if mode in MAIN_MODES else None,
            "scored_primary_model_outputs": len(rows),
            "item_mean": item_mean,
            "company_macro_mean": sum(company_means) / len(company_means) if company_means else None,
            "companies_observed": len(company_means),
            "dimensions_mean": {
                field: sum(r["mean"][field] for r in rows if r["mean"][field] is not None)
                / max(1, sum(r["mean"][field] is not None for r in rows))
                for field in FIELDS
            },
        }

    by_qm = {(r["question_id"], r["mode"]): r for r in filtered}
    contrasts = {}
    for name, baseline, treatment in [
        ("G2-G1", MAIN_MODES[0], MAIN_MODES[1]),
        ("G3-G2", MAIN_MODES[1], MAIN_MODES[2]),
        ("G3-G1", MAIN_MODES[0], MAIN_MODES[2]),
    ]:
        result_by_reviewer = {}
        for rating in ("mean", "R1", "R2"):
            rows = []
            for q in questions:
                a = by_qm.get((q["question_id"], baseline), {}).get(rating, {}).get("total")
                b = by_qm.get((q["question_id"], treatment), {}).get(rating, {}).get("total")
                rows.append({"question_id": q["question_id"], "company": q["company"],
                             "baseline": a, "treatment": b})
            result_by_reviewer[rating] = paired_company_statistics(rows, draws=20000, seed=20261028)
        contrasts[name] = result_by_reviewer

    agreement = {}
    for field in FIELDS:
        agreement[field] = quadratic_kappa(
            [r["R1"][field] for r in filtered], [r["R2"][field] for r in filtered]
        )

    OUT.mkdir(parents=True)
    filtered_path = OUT / "per_output_scores_primary_model_only.json"
    filtered_path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "status": "completed_filtered_reanalysis_excluding_nonprotocol_session_authored_supplements",
        "created_at_local_date": "2026-10-28",
        "scope": "Exploratory post-hoc reanalysis; not preregistered and not a new model run.",
        "excluded_generation_origin": {
            "units_authored_in_current_assistant_session": len(supplements),
            "scored_supplement_units_excluded": len(supplemented_scored),
            "supplements_without_two_reviewer_score": len(supplements) - len(supplemented_scored),
            "additional_api_calls": 0,
            "original_prompt_executed": False,
            "identical_api_protocol": False,
        },
        "primary_model_generation": {
            "planned_all_conditions": 400,
            "two_reviewer_scored_primary_model_outputs": len(filtered),
            "primary_three_conditions_planned": 180,
            "primary_three_conditions_successful_generation": audit["structured_successful"],
            "primary_condition_success_counts": dict(primary_by_mode),
        },
        "input_hashes": {str(p.relative_to(ROOT)): sha(p) for p in [SCORES, SUPPLEMENTS, PRIMARY_AUDIT, FREEZE]},
        "filtered_scores_sha256": sha(filtered_path),
        "conditions": conditions,
        "contrasts": contrasts,
        "reviewer_agreement": agreement,
        "interpretation_limits": [
            "Excluding post-hoc session-authored supplements removes cross-model contamination from the controlled Kimi comparison.",
            "The resulting condition comparisons have substantial and unequal missingness; estimates are conditional on observed pairs.",
            "Company-cluster percentile intervals are exploratory and not confirmatory tests.",
            "The Qwen/CUDA retrieval configuration and requested Kimi alias are not equivalent to a verified immutable provider model revision.",
        ],
    }
    report_path = OUT / "analysis.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"files": []}
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name != "artifact_manifest.json":
            manifest["files"].append({"file": p.name, "sha256": sha(p), "bytes": p.stat().st_size})
    (OUT / "artifact_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "supplements": report["excluded_generation_origin"],
        "primary_generation": report["primary_model_generation"],
        "condition_counts_and_means": {m: {k: v for k, v in c.items() if k in ("scored_primary_model_outputs", "item_mean", "company_macro_mean", "companies_observed")} for m, c in conditions.items() if m in MAIN_MODES},
        "contrasts": {k: {"known_pairs": v["mean"]["known_pairs"], "company_macro_difference_on_known_pairs": v["mean"]["company_macro_difference_on_known_pairs"], "company_cluster_bootstrap_ci95": v["mean"]["company_cluster_bootstrap_ci95"], "wins_ties_losses": None} for k, v in contrasts.items()},
        "out": str(OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
