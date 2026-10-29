"""Produce descriptive report-year strata for the saved Qwen/K3 cross-family run.

This is a post-hoc sensitivity analysis of the already saved eight paired
outputs. It makes no model calls and creates no labels.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY = ROOT / "results/runs/qwen_cuda_cross_model_score_20261029_04/summary.json"
DEFAULT_PROTOCOL = ROOT / "results/runs/qwen_cuda_cross_model_20261029_01/protocol.json"
DEFAULT_QWEN = ROOT / "results/runs/qwen_cuda_cross_model_20261029_01"
DEFAULT_K3 = ROOT / "results/paper/heldout_validation_20261023_01/calls"
METRICS = (
    "members_precision", "members_recall", "members_f1",
    "meeting_count_exact", "dates_precision", "dates_recall", "dates_f1",
    "all_three_exact",
)
MODELS = ("qwen06", "k3_single")
REFERENCES = ("before_generation", "post_output_erratum")
ID_PATTERN = re.compile(r"^NEW-(?P<company>\d+)-(?P<year>20\d{2})-")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def metric_number(value):
    if isinstance(value, bool):
        return float(value)
    return float(value)


def raw_output_path(question_id: str, model: str) -> Path:
    if model == "qwen06":
        return DEFAULT_QWEN / f"{question_id}.json"
    return DEFAULT_K3 / question_id / "k3_single" / "result.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty output directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    details = summary["details"]
    groups = defaultdict(list)
    raw_hashes = {}
    questions = {}
    for row in details:
        match = ID_PATTERN.match(row["question_id"])
        if not match:
            raise ValueError(f"Unexpected question ID: {row['question_id']}")
        row = dict(row)
        row["year"] = int(match.group("year"))
        row["company"] = match.group("company")
        key = (row["reference"], row["year"], row["mode"])
        groups[key].append(row)
        questions.setdefault((row["reference"], row["year"], row["mode"]), set()).add(row["question_id"])
        raw_path = raw_output_path(row["question_id"], row["mode"])
        if not raw_path.is_file():
            raise FileNotFoundError(raw_path)
        raw_hashes[str(raw_path.relative_to(ROOT))] = digest(raw_path)

    strata = []
    for reference in REFERENCES:
        for year in (2023, 2024):
            for model in MODELS:
                rows = groups[(reference, year, model)]
                if len({r["question_id"] for r in rows}) != len(rows):
                    raise ValueError(f"Duplicate answer rows in {(reference, year, model)}")
                expected = 4
                nonempty = [r for r in rows if r["status"] == "completed" and r["nonempty"]]
                item = {
                    "reference": reference,
                    "year": year,
                    "model": model,
                    "planned_questions": expected,
                    "observed_questions": len(rows),
                    "nonempty_questions": len(nonempty),
                    "companies_observed": len({r["company"] for r in rows}),
                    "schema_valid_count": sum(r["status"] == "completed" and r["schema_valid"] is True for r in rows),
                    "citation_lists_valid_count": sum(r["status"] == "completed" and r["citation_lists_valid"] is True for r in rows),
                    "unknown_citation_id_count": sum(len(r["unknown_citation_ids"] or []) for r in rows),
                    "malformed_citation_list_entry_count": sum(len(r["malformed_citation_values"] or []) for r in rows),
                }
                item["schema_valid_rate_planned"] = item["schema_valid_count"] / expected
                item["citation_lists_valid_rate_planned"] = item["citation_lists_valid_count"] / expected
                for metric in METRICS:
                    observed = [metric_number(r[metric]) for r in nonempty if r.get(metric) is not None]
                    item[f"{metric}_macro_nonempty"] = mean(observed) if observed else None
                strata.append(item)

    paired = []
    for reference in REFERENCES:
        for year in (2023, 2024):
            qwen = {r["question_id"]: r for r in groups[(reference, year, "qwen06")]}
            k3 = {r["question_id"]: r for r in groups[(reference, year, "k3_single")]}
            common = sorted(set(qwen) & set(k3))
            complete = [qid for qid in common
                        if qwen[qid]["status"] == k3[qid]["status"] == "completed"
                        and qwen[qid]["nonempty"] and k3[qid]["nonempty"]]
            row = {
                "reference": reference,
                "year": year,
                "planned_questions": 4,
                "common_question_ids": common,
                "complete_paired_questions": len(complete),
                "companies_in_complete_pairs": len({ID_PATTERN.match(qid).group("company") for qid in complete}),
            }
            for metric in METRICS:
                deltas = [metric_number(qwen[qid][metric]) - metric_number(k3[qid][metric]) for qid in complete]
                row[f"{metric}_qwen_minus_k3_macro"] = mean(deltas) if deltas else None
            paired.append(row)

    report = {
        "title": "Descriptive year-stratified sensitivity of the saved cross-family comparison",
        "source_summary_sha256": digest(args.summary),
        "source_protocol_sha256": digest(args.protocol),
        "raw_output_sha256": dict(sorted(raw_hashes.items())),
        "strata": strata,
        "paired_differences": paired,
        "interpretation_limits": [
            "This analysis reuses the saved eight outputs; it makes no model calls and creates no labels.",
            "Each year contains four audit-committee questions from the same four companies; the year strata are not an independent temporal test set.",
            "References were assistant-extracted and not independently validated; both frozen and post-output-corrected references are shown.",
            "One sampled output per model and question; model capacity, output budget, decoding settings, and compute are not matched.",
            "Report-year strata are descriptive only; no significance, causal, cross-year-generalization, citation-support, or legal-applicability claim is warranted.",
            "Schema and citation-list validity are mechanical format checks, not semantic correctness."
        ],
    }
    (args.output_dir / "year_stratified_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (args.output_dir / "year_stratified_models.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        fields = list(strata[0])
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(strata)
    with (args.output_dir / "year_stratified_pairs.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        fields = list(paired[0])
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(paired)
    print(json.dumps({
        "output_dir": str(args.output_dir),
        "input_summary_sha256": report["source_summary_sha256"],
        "strata": len(strata),
        "paired_strata": len(paired),
        "all_strata_have_four_questions": all(x["observed_questions"] == 4 for x in strata),
        "all_pairs_have_four_complete_questions": all(x["complete_paired_questions"] == 4 for x in paired),
        "models": MODELS,
        "references": REFERENCES,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
