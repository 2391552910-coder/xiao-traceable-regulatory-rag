"""Score completed independent holdout annotation sheets; refuse incomplete labels."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKET = ROOT / "results" / "runs" / "annual_table_holdout_review_v17_20261028_02"
YES = {"yes", "y", "true", "1"}
NO = {"no", "n", "false", "0"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def norm(value: str) -> str:
    return (value or "").strip().casefold()


def bool_label(value: str, field: str, row_id: str) -> bool:
    value = norm(value)
    if value in YES:
        return True
    if value in NO:
        return False
    raise ValueError(f"{field} must be yes/no for {row_id}; got {value!r}")


def metrics(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def score(packet: Path) -> dict:
    audit = json.loads((packet / "holdout_audit.json").read_text(encoding="utf-8"))
    pages = read_csv(packet / "page_review_template.csv")
    predictions = [json.loads(line) for line in (packet / "page_predictions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    tables = read_csv(packet / "table_review_template.csv")
    missed_rows = read_csv(packet / "missed_table_template.csv")
    continuations = read_csv(packet / "continuation_review_template.csv")

    if len(pages) != len(predictions):
        raise ValueError("Page labels and prediction manifest have different row counts")
    prediction_by_page = {(row["stock_code"], str(row["physical_page"])): row for row in predictions}
    page_false_ids = {}
    page_fn = defaultdict(int)
    page_missed_counts = defaultdict(int)
    page_complete = set()
    for row in missed_rows:
        key = (row["stock_code"], row["physical_page"])
        if norm(row.get("page_review_complete")) in YES:
            page_complete.add(key)
        elif norm(row.get("page_review_complete")) not in NO and norm(row.get("page_review_complete")):
            raise ValueError(f"Invalid page_review_complete label on {key}")
        if norm(row.get("missed_by_parser")) in YES:
            if not row.get("gold_table_id", "").strip() or not row.get("gold_category", "").strip() or not row.get("independent_reviewer", "").strip():
                raise ValueError(f"Missed table row lacks gold id/category/reviewer on {key}")
            page_fn[key] += 1
            page_missed_counts[key] += 1
        elif norm(row.get("missed_by_parser")) == "no":
            if not row.get("independent_reviewer", "").strip():
                raise ValueError(f"No-miss confirmation lacks reviewer identity on {key}")
        elif any(row.get(field, "").strip() for field in ("gold_table_id", "gold_category", "independent_reviewer")):
            raise ValueError(f"Partially filled missed-table row on {key}")

    page_tp = page_fp_count = page_fn_count = 0
    for row in pages:
        key = (row["stock_code"], row["physical_page"])
        if key not in page_complete:
            raise ValueError(f"Page has not been confirmed complete in missed_table_template.csv: {key}")
        gold = bool_label(row.get("page_has_governance_table_gold", ""), "page_has_governance_table_gold", str(key))
        detected = bool(prediction_by_page[key].get("detected_table_ids"))
        expected_missed = row.get("missed_table_count_gold", "").strip()
        if not expected_missed.isdigit() or int(expected_missed) != page_missed_counts[key]:
            raise ValueError(f"missed_table_count_gold disagrees with missed_table_template for {key}")
        false_text = row.get("false_positive_table_ids", "").strip()
        false_ids = set() if false_text.casefold() == "none" else {item.strip() for item in false_text.split(";") if item.strip()}
        page_false_ids[key] = false_ids
        predicted_ids = set(prediction_by_page[key].get("detected_table_ids", []))
        if false_ids - predicted_ids:
            raise ValueError(f"Unknown false-positive table IDs for {key}: {sorted(false_ids-predicted_ids)}")
        if not row.get("independent_reviewer", "").strip():
            raise ValueError(f"Missing reviewer identity for page {key}")
        if detected and not false_text:
            raise ValueError(f"Use 'none' or semicolon-separated IDs to explicitly review false positives on {key}")
        if false_text and false_text.casefold() != "none" and not false_ids:
            raise ValueError(f"false_positive_table_ids must be 'none' or semicolon-separated IDs on {key}")
        if gold and not detected:
            page_fn_count += 1
        elif detected and not gold:
            page_fp_count += 1
        elif detected and gold:
            page_tp += 1
    page_metrics = metrics(page_tp, page_fp_count, page_fn_count)

    expected_prediction_ids = {
        table_id
        for row in predictions
        for table_id in row.get("detected_table_ids", [])
    }
    seen_prediction_ids = set()
    detection_tp = detection_fp = 0
    category_counts = defaultdict(lambda: [0, 0, 0])
    matched_gold_ids = set()
    table_false_ids = defaultdict(set)
    for row in tables:
        if row.get("row_kind") != "prediction":
            raise ValueError("Unexpected row_kind in table_review_template.csv")
        table_id = row.get("prediction_table_id", "").strip()
        if not table_id or table_id in seen_prediction_ids:
            raise ValueError(f"Missing or duplicate prediction_table_id: {table_id!r}")
        seen_prediction_ids.add(table_id)
        if not row.get("independent_reviewer", "").strip():
            raise ValueError(f"Missing reviewer identity for table {table_id}")
        status = norm(row.get("match_status", ""))
        predicted_category = row.get("predicted_category", "").strip() or "unclassified_table"
        if status == "matched":
            gold_id = row.get("gold_table_id", "").strip()
            gold_category = row.get("gold_category", "").strip()
            if not gold_id or not gold_category or gold_id in matched_gold_ids:
                raise ValueError(f"Matched table requires unique gold_table_id and category: {table_id}")
            matched_gold_ids.add(gold_id)
            detection_tp += 1
            if predicted_category == gold_category:
                category_counts[gold_category][0] += 1
            else:
                category_counts[predicted_category][1] += 1
                category_counts[gold_category][2] += 1
        elif status == "false_positive":
            detection_fp += 1
            table_false_ids[(row["stock_code"], row["physical_page"])].add(table_id)
            category_counts[predicted_category][1] += 1
            if row.get("gold_table_id", "").strip() or row.get("gold_category", "").strip():
                raise ValueError(f"False-positive prediction must not have a matched gold table: {table_id}")
        else:
            raise ValueError(f"match_status must be matched/false_positive: {table_id}")
    if seen_prediction_ids != expected_prediction_ids:
        raise ValueError("Table review template does not cover exactly the predicted table IDs")
    for key, declared in page_false_ids.items():
        if declared != table_false_ids[key]:
            raise ValueError(f"Page and table sheets disagree about false-positive table IDs on {key}")

    missed_gold_ids = set()
    for row in missed_rows:
        if norm(row.get("missed_by_parser")) not in YES:
            continue
        gold_id = row["gold_table_id"].strip()
        if gold_id in matched_gold_ids or gold_id in missed_gold_ids:
            raise ValueError(f"Duplicate gold table ID across annotation sheets: {gold_id}")
        missed_gold_ids.add(gold_id)
        category_counts[row["gold_category"].strip()][2] += 1
    detection_fn = len(missed_gold_ids)

    continuation_tp = continuation_fp = continuation_fn = 0
    for idx, row in enumerate(continuations, 1):
        row_id = f"continuation row {idx}"
        gold = bool_label(row.get("gold_continuation", ""), "gold_continuation", row_id)
        if not row.get("independent_reviewer", "").strip():
            raise ValueError(f"Missing reviewer identity for {row_id}")
        predicted = norm(row.get("parser_link_accepted", "")) in YES
        if predicted and gold:
            continuation_tp += 1
        elif predicted and not gold:
            continuation_fp += 1
        elif not predicted and gold:
            continuation_fn += 1

    return {
        "status": "scored_from_completed_reviewer_sheets",
        "parser_version": audit["parser_version"],
        "source_reports": [{"stock_code": r["stock_code"], "year": r["report_year"], "sha256": r["source_pdf_sha256"]} for r in audit["reports"]],
        "scope": "retrospectively_selected 2024 governance keyword pages and fixed neighbors; not random, preregistered, all-report, or end-to-end RAG validation",
        "page_detection": page_metrics,
        "table_detection": metrics(detection_tp, detection_fp, detection_fn),
        "table_category": {label: metrics(*values) for label, values in sorted(category_counts.items())},
        "continuation_link_detection": metrics(continuation_tp, continuation_fp, continuation_fn),
        "independent_reviewer_identity_is_recorded_but_not_cryptographically_or_externally_verified": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = score(args.packet.resolve())
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()

