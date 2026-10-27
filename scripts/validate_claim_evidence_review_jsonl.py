"""Validate completed claim–evidence review JSONL files without judging labels."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROW_FIELDS = {
    "review_case_id",
    "output_id",
    "question_id",
    "reviewer_id",
    "overall_answerability",
    "required_answer_points_covered",
    "claims",
    "unresolved_or_missing_evidence",
    "reviewer_rationale",
}
CLAIM_FIELDS = {
    "claim_text",
    "claim_type",
    "support_status",
    "cited_evidence_ids",
    "supporting_evidence_ids",
    "required_source_roles",
    "role_status",
    "event_date",
    "regulation_applicability",
    "rationale",
}
ENUMS = {
    "overall_answerability": {"answerable", "partially_answerable", "unanswerable", "unknown"},
    "required_answer_points_covered": {"complete", "partial", "missing", "unknown"},
    "claim_type": {"company_fact", "normative_requirement", "comparison", "other"},
    "support_status": {"supported", "contradicted", "insufficient", "unresolved"},
    "required_source_roles": {"annual_report", "regulation"},
    "role_status": {"correct", "missing", "wrong", "unknown"},
    "regulation_applicability": {"applicable", "not_applicable", "unknown", "not_required"},
}
EVIDENCE_ID = re.compile(r"^[AR]\d+$")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_no}: each JSONL row must be an object")
        rows.append(value)
    return rows


def _blank(row: dict[str, Any]) -> bool:
    return (
        row.get("overall_answerability") in (None, "")
        and row.get("required_answer_points_covered") in (None, "")
        and row.get("claims") == []
        and row.get("unresolved_or_missing_evidence") in (None, "")
        and row.get("reviewer_rationale") in (None, "")
    )


def validate_rows(
    rows: list[dict[str, Any]],
    casebook: list[dict[str, Any]],
    *,
    allow_blank: bool = False,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    def issue(code: str, message: str, row: int | None = None, claim: int | None = None) -> None:
        item: dict[str, Any] = {"code": code, "message": message}
        if row is not None:
            item["row"] = row
        if claim is not None:
            item["claim"] = claim
        issues.append(item)

    expected = {r.get("review_case_id"): r for r in casebook}
    seen: set[str] = set()
    if len(rows) != len(casebook):
        issue("row_count_mismatch", f"Expected {len(casebook)} rows, received {len(rows)}.")

    reviewer_values = [r.get("reviewer_id") for r in rows]
    reviewer_ids = {value for value in reviewer_values if isinstance(value, str)}
    if (
        len(reviewer_ids) != 1
        or any(not isinstance(value, str) or value not in {"R1", "R2"} for value in reviewer_values)
    ):
        issue("reviewer_id_mismatch", "All rows must use the same reviewer_id, either R1 or R2.")

    filled = blank = 0
    for line_no, row in enumerate(rows, start=1):
        missing = ROW_FIELDS - row.keys()
        if missing:
            issue("missing_row_fields", "Missing fields: " + ", ".join(sorted(missing)), line_no)
            continue

        case_id = row.get("review_case_id")
        if not isinstance(case_id, str) or case_id not in expected:
            issue("unknown_review_case", f"Unknown review_case_id: {case_id!r}.", line_no)
        elif case_id in seen:
            issue("duplicate_review_case", f"Duplicate review_case_id: {case_id}.", line_no)
        else:
            seen.add(case_id)
            case = expected[case_id]
            for field in ("output_id", "question_id"):
                if row.get(field) != case.get(field):
                    issue("case_mapping_mismatch", f"{field} does not match the casebook.", line_no)

        if _blank(row):
            blank += 1
            if not allow_blank:
                issue("blank_annotation", "This row has no reviewer judgments.", line_no)
            continue
        filled += 1

        for field in ("overall_answerability", "required_answer_points_covered"):
            value = row.get(field)
            if not isinstance(value, str) or value not in ENUMS[field]:
                issue("invalid_enum", f"{field} must be one of {sorted(ENUMS[field])}.", line_no)
        for field in ("unresolved_or_missing_evidence", "reviewer_rationale"):
            if not isinstance(row.get(field), str):
                issue("invalid_field_type", f"{field} must be a string.", line_no)

        claims = row.get("claims")
        if not isinstance(claims, list) or not claims:
            issue("claims_required", "A completed row must contain at least one claim object.", line_no)
            continue

        for claim_no, claim in enumerate(claims, start=1):
            if not isinstance(claim, dict):
                issue("invalid_claim_type", "Each claim must be an object.", line_no, claim_no)
                continue
            missing_claim = CLAIM_FIELDS - claim.keys()
            if missing_claim:
                issue("missing_claim_fields", "Missing fields: " + ", ".join(sorted(missing_claim)), line_no, claim_no)
                continue
            for field in ("claim_text", "rationale"):
                if not isinstance(claim.get(field), str) or not claim[field].strip():
                    issue("empty_claim_text", f"{field} must be a nonempty string.", line_no, claim_no)
            for field in ("claim_type", "support_status", "role_status", "regulation_applicability"):
                value = claim.get(field)
                if not isinstance(value, str) or value not in ENUMS[field]:
                    issue("invalid_enum", f"Invalid {field}: {claim.get(field)!r}.", line_no, claim_no)

            roles = claim.get("required_source_roles")
            if not isinstance(roles, list) or not roles or any(
                not isinstance(role, str) or role not in ENUMS["required_source_roles"] for role in roles
            ):
                issue("invalid_source_roles", "required_source_roles must be a nonempty list of annual_report/regulation.", line_no, claim_no)
            elif len(roles) != len(set(roles)):
                issue("duplicate_source_role", "required_source_roles contains duplicates.", line_no, claim_no)

            for field in ("cited_evidence_ids", "supporting_evidence_ids"):
                ids = claim.get(field)
                if not isinstance(ids, list) or any(not isinstance(eid, str) or not EVIDENCE_ID.fullmatch(eid) for eid in ids):
                    issue("invalid_evidence_ids", f"{field} must be a list of IDs such as A1 or R2.", line_no, claim_no)
                elif len(ids) != len(set(ids)):
                    issue("duplicate_evidence_id", f"{field} contains duplicate IDs.", line_no, claim_no)
            if not isinstance(claim.get("event_date"), str):
                issue("invalid_field_type", "event_date must be a string; leave it empty when unknown.", line_no, claim_no)

    missing_cases = set(expected) - seen
    if missing_cases:
        issue("missing_cases", f"{len(missing_cases)} expected review cases are missing.")

    return {
        "status": "valid" if not issues else "invalid",
        "rows_total": len(rows),
        "rows_filled": filled,
        "rows_blank": blank,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path, help="R1/R2 annotations JSONL")
    parser.add_argument("--casebook", type=Path, help="Defaults to casebook.jsonl beside submission")
    parser.add_argument("--allow-blank", action="store_true", help="Validate a blank template without treating blank rows as errors")
    parser.add_argument("--out", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    casebook_path = args.casebook or args.submission.with_name("casebook.jsonl")
    try:
        result = validate_rows(read_jsonl(args.submission), read_jsonl(casebook_path), allow_blank=args.allow_blank)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["status"] == "valid" else 1


if __name__ == "__main__":
    sys.exit(main())

