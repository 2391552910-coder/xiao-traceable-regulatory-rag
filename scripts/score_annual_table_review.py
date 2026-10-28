"""Score completed two-stage blind annual-report table annotations."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
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


def yes_no(value: str, field: str, row_id: str) -> bool:
    value = norm(value)
    if value in YES:
        return True
    if value in NO:
        return False
    raise ValueError(f"{field} must be yes/no for {row_id}; got {value!r}")


def prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score(packet: Path) -> dict:
    audit = json.loads((packet / "holdout_audit.json").read_text(encoding="utf-8"))
    page_rows = read_csv(packet / "page_review_template.csv")
    gold_rows = read_csv(packet / "gold_table_blind_template.csv")
    match_rows = read_csv(packet / "prediction_gold_match_template.csv")
    gold_edges_rows = read_csv(packet / "gold_continuation_blind_template.csv")
    page_predictions = load_jsonl(packet / "page_predictions.jsonl")
    edge_predictions = load_jsonl(packet / "accepted_continuation_predictions.jsonl")

    pred_by_page = {(r["stock_code"], str(r["physical_page"])): r for r in page_predictions}
    expected_pages = set(pred_by_page)
    page_gold_present: dict[tuple[str, str], bool] = {}
    for row in page_rows:
        key = (row["stock_code"], str(row["physical_page"]))
        if key not in expected_pages or key in page_gold_present:
            raise ValueError(f"Unexpected or duplicate page review row: {key}")
        if not yes_no(row.get("review_complete", ""), "review_complete", str(key)):
            raise ValueError(f"Page review is not complete: {key}")
        if not row.get("independent_reviewer", "").strip():
            raise ValueError(f"Missing reviewer identity for page {key}")
        page_gold_present[key] = yes_no(row.get("gold_table_present", ""), "gold_table_present", str(key))
    if set(page_gold_present) != expected_pages:
        raise ValueError("Page review sheet does not cover every selected page exactly once")

    gold_tables: dict[tuple[str, str], dict] = {}
    gold_ids_by_page = defaultdict(list)
    page_sentinels = set()
    sentinel_counts = Counter()
    for idx, row in enumerate(gold_rows, 1):
        page_key = (row["stock_code"], str(row["physical_page"]))
        row_id = f"gold table row {idx}"
        if page_key not in expected_pages:
            raise ValueError(f"Gold table row refers to a page outside the packet: {page_key}")
        if not yes_no(row.get("review_complete", ""), "review_complete", row_id):
            raise ValueError(f"Gold table page inventory is incomplete: {page_key}")
        if not row.get("independent_reviewer", "").strip():
            raise ValueError(f"Missing reviewer identity for {row_id}")
        gold_id = row.get("gold_table_id", "").strip()
        if not gold_id:
            raise ValueError(f"Enter a gold table ID or NONE for {row_id}")
        if gold_id.casefold() == "none":
            if row.get("gold_category", "").strip() or row.get("gold_bbox_normalized_xyxy", "").strip():
                raise ValueError(f"NONE row must not have a category or bounding box: {row_id}")
            page_sentinels.add(page_key)
            sentinel_counts[page_key] += 1
            continue
        category = row.get("gold_category", "").strip()
        if not category:
            raise ValueError(f"Gold table category is missing for {gold_id}")
        try:
            bbox = json.loads(row.get("gold_bbox_normalized_xyxy", ""))
        except Exception as exc:
            raise ValueError(f"Invalid normalized bbox for {gold_id}") from exc
        if (not isinstance(bbox, list) or len(bbox) != 4 or
                any(not isinstance(v, (int, float)) or v < 0 or v > 1 for v in bbox) or
                bbox[0] >= bbox[2] or bbox[1] >= bbox[3]):
            raise ValueError(f"Invalid normalized bbox coordinates for {gold_id}: {bbox!r}")
        key = (row["stock_code"], gold_id)
        if key in gold_tables:
            raise ValueError(f"Duplicate gold table ID: {key}")
        gold_tables[key] = {"page": str(row["physical_page"]), "category": category, "bbox": bbox}
        gold_ids_by_page[page_key].append(gold_id)

    # Each selected page must have exactly one NONE marker iff it contains no
    # gold table; pages with tables must have one or more gold inventory rows.
    represented_pages = set(gold_ids_by_page) | page_sentinels
    if represented_pages != expected_pages:
        raise ValueError(f"Gold table inventory page coverage mismatch: {sorted(expected_pages-represented_pages)}")
    for key in expected_pages:
        if sentinel_counts[key] > 1:
            raise ValueError(f"Duplicate NONE sentinel for page: {key}")
        if page_gold_present[key] != bool(gold_ids_by_page[key]):
            raise ValueError(f"Page-presence label conflicts with gold table inventory: {key}")
        if bool(gold_ids_by_page[key]) == (key in page_sentinels):
            raise ValueError(f"Use NONE only for empty pages, and never with a gold table: {key}")

    expected_pred_ids = {
        (row["stock_code"], table_id): str(row["physical_page"])
        for row in page_predictions
        for table_id in row.get("detected_table_ids", [])
    }
    pred_to_gold: dict[tuple[str, str], str] = {}
    match_status: dict[tuple[str, str], str] = {}
    matched_gold = set()
    category = defaultdict(lambda: [0, 0, 0])
    tp = fp = 0
    for idx, row in enumerate(match_rows, 1):
        row_id = f"prediction match row {idx}"
        key = (row["stock_code"], row.get("prediction_table_id", "").strip())
        if key not in expected_pred_ids or key in match_status:
            raise ValueError(f"Unexpected or duplicate prediction table ID: {key}")
        if not row.get("independent_reviewer", "").strip():
            raise ValueError(f"Missing reviewer identity for {row_id}")
        if row.get("predicted_category", "").strip() == "":
            raise ValueError(f"Prediction category is missing for {key}")
        status = norm(row.get("match_status", ""))
        pred_category = row["predicted_category"].strip()
        if status == "matched":
            gold_id = row.get("gold_table_id", "").strip()
            gold_key = (row["stock_code"], gold_id)
            if gold_key not in gold_tables:
                raise ValueError(f"Matched prediction refers to unknown gold table: {gold_key}")
            if gold_tables[gold_key]["page"] != expected_pred_ids[key]:
                raise ValueError(f"Prediction matched across physical pages: {key} -> {gold_key}")
            if gold_key in matched_gold:
                raise ValueError(f"Gold table matched more than once: {gold_key}")
            matched_gold.add(gold_key)
            pred_to_gold[key] = gold_id
            tp += 1
            gold_category = gold_tables[gold_key]["category"]
            if pred_category == gold_category:
                category[gold_category][0] += 1
            else:
                category[pred_category][1] += 1
                category[gold_category][2] += 1
        elif status == "false_positive":
            if row.get("gold_table_id", "").strip():
                raise ValueError(f"False-positive prediction must not have a gold ID: {key}")
            fp += 1
            category[pred_category][1] += 1
        else:
            raise ValueError(f"match_status must be matched/false_positive for {key}")
        match_status[key] = status
    if set(match_status) != set(expected_pred_ids):
        raise ValueError("Prediction match sheet does not cover exactly all parser table predictions")
    fn_gold = set(gold_tables) - matched_gold
    for gold_key in fn_gold:
        category[gold_tables[gold_key]["category"]][2] += 1

    page_tp = page_fp = page_fn = 0
    for key, gold_present in page_gold_present.items():
        predicted_present = bool(pred_by_page[key].get("detected_table_ids"))
        if gold_present and predicted_present:
            page_tp += 1
        elif predicted_present and not gold_present:
            page_fp += 1
        elif gold_present and not predicted_present:
            page_fn += 1

    expected_boundaries = set()
    by_stock_pages = defaultdict(list)
    for row in page_predictions:
        by_stock_pages[row["stock_code"]].append(int(row["physical_page"]))
    for stock, pages in by_stock_pages.items():
        pages = sorted(pages)
        expected_boundaries.update((stock, str(left), str(right)) for left, right in zip(pages, pages[1:]) if right == left + 1)

    gold_edges: Counter = Counter()
    reviewed_boundaries = set()
    boundary_states = defaultdict(set)
    boundary_none_counts = Counter()
    for idx, row in enumerate(read_csv(packet / "gold_continuation_blind_template.csv"), 1):
        row_id = f"gold continuation row {idx}"
        stock = row["stock_code"]
        left, right = str(row["left_page"]), str(row["right_page"])
        boundary = (stock, left, right)
        if boundary not in expected_boundaries:
            raise ValueError(f"Unexpected gold continuation boundary: {boundary}")
        if not yes_no(row.get("review_complete", ""), "review_complete", row_id):
            raise ValueError(f"Continuation review incomplete: {boundary}")
        if not row.get("independent_reviewer", "").strip():
            raise ValueError(f"Missing reviewer identity for {row_id}")
        gold_yes = yes_no(row.get("gold_continuation", ""), "gold_continuation", row_id)
        boundary_states[boundary].add(gold_yes)
        left_id = row.get("gold_left_table_id", "").strip()
        right_id = row.get("gold_right_table_id", "").strip()
        if gold_yes:
            left_key, right_key = (stock, left_id), (stock, right_id)
            if left_key not in gold_tables or right_key not in gold_tables:
                raise ValueError(f"Gold continuation references unknown table: {boundary}")
            if gold_tables[left_key]["page"] != left or gold_tables[right_key]["page"] != right:
                raise ValueError(f"Gold continuation endpoints do not match boundary: {boundary}")
            gold_edges[(stock, left_id, right_id)] += 1
        elif left_id or right_id:
            raise ValueError(f"No-continuation row must not contain endpoint IDs: {boundary}")
        else:
            boundary_none_counts[boundary] += 1
        reviewed_boundaries.add(boundary)
    if reviewed_boundaries != expected_boundaries:
        raise ValueError(f"Gold continuation sheet lacks boundaries: {sorted(expected_boundaries-reviewed_boundaries)}")
    for boundary, states in boundary_states.items():
        if len(states) != 1 or (False in states and boundary_none_counts[boundary] != 1):
            raise ValueError(f"Conflicting or duplicate continuation labels for boundary: {boundary}")

    predicted_edges: Counter = Counter()
    for row in edge_predictions:
        stock = row["stock_code"]
        left_key = (stock, row["left_prediction_table_id"])
        right_key = (stock, row["right_prediction_table_id"])
        if left_key not in match_status or right_key not in match_status:
            raise ValueError(f"Accepted parser link references unknown predicted table: {row}")
        left_gold = pred_to_gold.get(left_key)
        right_gold = pred_to_gold.get(right_key)
        edge = (stock, left_gold or f"UNMATCHED:{left_key[1]}", right_gold or f"UNMATCHED:{right_key[1]}")
        predicted_edges[edge] += 1
    edge_tp = sum(min(count, gold_edges[key]) for key, count in predicted_edges.items())
    edge_fp = sum(count - min(count, gold_edges[key]) for key, count in predicted_edges.items())
    edge_fn = sum(count - min(count, predicted_edges[key]) for key, count in gold_edges.items())

    return {
        "status": "scored_from_completed_two_stage_reviewer_sheets",
        "parser_version": audit["parser_version"],
        "source_reports": [{"stock_code": r["stock_code"], "year": r["report_year"], "sha256": r["source_pdf_sha256"]} for r in audit["reports"]],
        "scope": "retrospectively selected 2024 governance keyword pages and fixed neighbors; not random, preregistered, full-report, cross-year, or end-to-end RAG validation",
        "page_detection": prf(page_tp, page_fp, page_fn),
        "table_detection": prf(tp, fp, len(fn_gold)),
        "table_category": {label: prf(*values) for label, values in sorted(category.items())},
        "continuation_link_detection": prf(edge_tp, edge_fp, edge_fn),
        "reviewer_identity_is_recorded_but_independence_is_not_cryptographically_or_externally_verified": True,
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

