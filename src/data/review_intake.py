"""Read-only intake checks and descriptive agreement for two trial reviewers.

Filled records and registration are self-reported. Structural validation does
not authenticate human identity, certify blinding, accept gold or freeze data.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path


FORM_KEYS = {
    "review_form.csv": ("unit_type", "unit_id", "query_id"),
    "family_pair_review_form.csv": ("pair_id",),
}
PROTECTED_FIELDS = {
    "review_form.csv": FORM_KEYS["review_form.csv"],
    "family_pair_review_form.csv": ("pair_id", "query_id_a", "query_text_a", "query_id_b", "query_text_b"),
}
FLAG_FIELDS = ("source_identity_correct", "quote_and_location_correct", "evidence_role_correct")
JUDGMENT_FIELDS = (*FLAG_FIELDS, "relevance_grade", "event_date_supported_by_system_input",
                   "event_date", "temporal_applicability", "answerability")
RELATIONS = {"same_family", "same_event", "near_duplicate", "shared_target_evidence", "different", "unresolved"}
UNKNOWN = {"", "u", "na", "unknown", "unresolved"}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        headers = reader.fieldnames or []
        if not headers or len(headers) != len(set(headers)):
            raise ValueError("Missing or duplicated CSV headers")
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("CSV cell count does not match the header")
            if any(value.strip() for value in row.values()):
                rows.append(row)
    return headers, rows


def code(value) -> str:
    return str(value or "").strip().casefold()


def valid_date(value: str) -> bool:
    try:
        if "T" in value or " " in value:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            date.fromisoformat(value)
        return True
    except ValueError:
        return False


def agreement(pairs: list[tuple[str, str]], *, ordinal_labels: tuple[str, ...] | None = None) -> dict:
    """Pairwise complete-case Cohen kappa, with unknown coverage retained."""
    cleaned = [(code(a), code(b)) for a, b in pairs]
    judged = [(a, b) for a, b in cleaned if a not in UNKNOWN and b not in UNKNOWN]
    result = {"total_pairs": len(pairs), "both_judged_pairs": len(judged),
              "excluded_unknown_or_na_pairs": len(pairs) - len(judged),
              "left_unknown_or_na": sum(a in UNKNOWN for a, _ in cleaned),
              "right_unknown_or_na": sum(b in UNKNOWN for _, b in cleaned),
              "agreement_rate": None, "cohen_kappa": None,
              "kappa_unavailable_reason": None}
    if not judged:
        result["kappa_unavailable_reason"] = "no_both_judged_pairs"
        return result
    n = len(judged)
    left, right = Counter(a for a, _ in judged), Counter(b for _, b in judged)
    labels = sorted(set(left) | set(right))
    observed = sum(a == b for a, b in judged) / n
    expected = sum(left[label] * right[label] for label in labels) / (n * n)
    result.update({"agreement_rate": observed, "expected_agreement": expected,
                   "left_label_counts": dict(left), "right_label_counts": dict(right)})
    if expected >= 1.0:
        result["kappa_unavailable_reason"] = "degenerate_constant_marginals"
    else:
        result["cohen_kappa"] = (observed - expected) / (1 - expected)
    if ordinal_labels is not None:
        if len(ordinal_labels) < 2 or not set(labels).issubset(ordinal_labels):
            raise ValueError("Ordinal labels must include every judged category")
        positions = {label: i for i, label in enumerate(ordinal_labels)}
        weight = lambda a, b: abs(positions[a] - positions[b]) / (len(ordinal_labels) - 1)
        observed_disagreement = sum(weight(a, b) for a, b in judged) / n
        expected_disagreement = sum(weight(a, b) * left[a] * right[b]
                                    for a in labels for b in labels) / (n * n)
        result["linear_weighted_kappa"] = (1 - observed_disagreement / expected_disagreement
                                            if expected_disagreement else None)
    return result


def inspect_submissions(packet_dir: Path, submissions: dict[str, Path], registration: Path, *,
                        expected_packet_manifest_sha256: str) -> dict:
    manifest_path = packet_dir / "release_manifest.json"
    if file_sha256(manifest_path) != expected_packet_manifest_sha256.lower():
        raise ValueError("Trial packet manifest SHA256 mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = packet_dir.resolve()
    for entry in manifest["artifacts"]:
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root) or file_sha256(path) != entry["sha256"]:
            raise ValueError("Trial packet source/template hash mismatch or escaped path")
    if set(submissions) != {"R1", "R2"}:
        raise ValueError("Submissions must have distinct R1 and R2 roles")
    errors, normalized, by_reviewer = [], [], {}

    def issue(role, filename, unit, field, message):
        errors.append({"reviewer_role": role, "file": filename, "unit": list(unit),
                       "field": field, "message": message})

    registrations = {}
    _, registration_rows = read_csv(registration)
    for row in registration_rows:
        role, actual_id = row.get("reviewer_code", "").strip(), row.get("actual_reviewer_id", "").strip()
        if role in registrations:
            issue(role, registration.name, (), "reviewer_code", "Duplicate reviewer role")
        registrations[role] = actual_id
    ids = [registrations.get(role, "") for role in ("R1", "R2")]
    if not all(ids) or len(set(ids)) != 2:
        issue("both", registration.name, (), "actual_reviewer_id",
              "Two distinct nonempty self-reported reviewer IDs are required")

    for role in ("R1", "R2"):
        collected = {}
        for filename, keys in FORM_KEYS.items():
            _, expected_rows = read_csv(packet_dir / f"reviewer_{role}_stage1" / filename)
            expected = {tuple(row[key] for key in keys): row for row in expected_rows}
            try:
                headers, rows = read_csv(submissions[role] / filename)
            except (OSError, UnicodeError, csv.Error, ValueError) as exc:
                issue(role, filename, (), "file", str(exc))
                continue
            required_headers = set(expected_rows[0]) if expected_rows else set(keys)
            if not required_headers.issubset(headers):
                issue(role, filename, (), "headers", "Submitted form lost required headers")
                continue
            submitted = {}
            for row in rows:
                unit = tuple(row[key] for key in keys)
                if unit in submitted:
                    issue(role, filename, unit, "unit_id", "Duplicate review unit")
                submitted[unit] = row
            if set(submitted) != set(expected):
                issue(role, filename, (), "unit_set", "Submitted units must match the assigned template exactly")
            for unit in sorted(set(submitted) & set(expected)):
                row, source = submitted[unit], expected[unit]
                for field in PROTECTED_FIELDS[filename]:
                    if row[field] != source[field]:
                        issue(role, filename, unit, field, "Protected question or unit content was changed")
                if not row["reviewer_id"].strip() or row["reviewer_id"].strip() != registrations.get(role):
                    issue(role, filename, unit, "reviewer_id", "Row reviewer ID does not match registration")
                for field in ("reason", "blind_status", "reviewed_at"):
                    if not row[field].strip():
                        issue(role, filename, unit, field, "Required actual review field is blank")
                if row["reviewed_at"].strip() and not valid_date(row["reviewed_at"].strip()):
                    issue(role, filename, unit, "reviewed_at", "Expected ISO date or datetime")
                uncertain = False
                if filename == "review_form.csv":
                    if not row["decision"].strip():
                        issue(role, filename, unit, "decision", "Review decision is blank")
                    for field in FLAG_FIELDS:
                        value = code(row[field])
                        if value not in {"yes", "no", "u", "na"}:
                            issue(role, filename, unit, field, "Use yes/no/U/NA")
                        uncertain |= value == "u"
                    if row["unit_type"] != "question":
                        if code(row["relevance_grade"]) not in {"0", "1", "2", "u"}:
                            issue(role, filename, unit, "relevance_grade", "Use 0/1/2/U for evidence")
                        uncertain |= code(row["relevance_grade"]) == "u"
                    temporal = code(row["temporal_applicability"])
                    if temporal not in {"applicable", "not_applicable", "unknown", "na"}:
                        issue(role, filename, unit, "temporal_applicability", "Use applicable/not_applicable/unknown/NA")
                    uncertain |= temporal == "unknown"
                    answerability = code(row["answerability"])
                    if answerability not in {"answerable", "partially_answerable", "insufficient", "conflicted", "unresolved", "na"}:
                        issue(role, filename, unit, "answerability", "Answerability code is missing or unsupported")
                    uncertain |= answerability == "unresolved"
                    date_support = code(row["event_date_supported_by_system_input"])
                    if date_support not in {"yes", "no", "u", "na"}:
                        issue(role, filename, unit, "event_date_supported_by_system_input", "Use yes/no/U/NA")
                    event = row["event_date"].strip()
                    if event and (date_support != "yes" or not valid_date(event)):
                        issue(role, filename, unit, "event_date", "A filled event date requires yes support and an ISO date")
                    if date_support == "yes" and not event:
                        issue(role, filename, unit, "event_date", "Supported event date must be supplied")
                    uncertain |= date_support == "u"
                else:
                    relation = code(row["relation"])
                    if relation not in RELATIONS:
                        issue(role, filename, unit, "relation", "Relation is missing or unsupported")
                    if relation in {"same_event", "shared_target_evidence"} and not row["source_or_event_basis"].strip():
                        issue(role, filename, unit, "source_or_event_basis", "Event/evidence grouping needs a traceable basis")
                    uncertain = relation == "unresolved"
                if uncertain and not row["uncertainty_reason"].strip():
                    issue(role, filename, unit, "uncertainty_reason", "Unknown judgments require their reason")
                collected[(filename, unit)] = row
                normalized.append({"reviewer_role": role, "form": filename, **row})
        by_reviewer[role] = collected

    # A decisive applicability judgment cannot borrow a hidden/external date
    # missing from the reviewer's system-visible question assessment.
    for role, rows in by_reviewer.items():
        question_dates = {row["query_id"]: row for (filename, _), row in rows.items()
                          if filename == "review_form.csv" and row["unit_type"] == "question"}
        for (filename, unit), row in rows.items():
            if filename == "review_form.csv" and code(row["temporal_applicability"]) in {"applicable", "not_applicable"}:
                question = question_dates.get(row["query_id"], {})
                if code(question.get("event_date_supported_by_system_input")) != "yes" or not question.get("event_date"):
                    issue(role, filename, unit, "temporal_applicability", "Decisive applicability requires a system-supported date in the question assessment")

    comparisons, disagreements, stats = [], [], {}
    if not errors:
        pairs_by_field = defaultdict(list)
        for key in sorted(by_reviewer["R1"]):
            filename, unit = key
            first, second = by_reviewer["R1"][key], by_reviewer["R2"][key]
            fields = JUDGMENT_FIELDS if filename == "review_form.csv" else ("relation",)
            scope = first["unit_type"] if filename == "review_form.csv" else "question_pair"
            for field in fields:
                left, right = code(first[field]), code(second[field])
                comparison = {"scope": scope, "unit": list(unit), "field": field,
                              "reviewer_1_value": first[field], "reviewer_2_value": second[field]}
                comparisons.append(comparison)
                if left != right:
                    disagreements.append({**comparison, "adjudicator_id": "", "adjudicated_value": "",
                                          "adjudication_reason": "", "adjudicated_at": ""})
                if field in {*FLAG_FIELDS, "relevance_grade", "answerability", "temporal_applicability", "relation"} and \
                        not (scope == "question" and field == "relevance_grade"):
                    pairs_by_field[(scope, field)].append((left, right))
        for (scope, field), values in pairs_by_field.items():
            stats[f"{scope}.{field}"] = agreement(values, ordinal_labels=("0", "1", "2") if field == "relevance_grade" else None)
            if field == "relevance_grade":
                binary = [("U" if a in UNKNOWN else "yes" if a == "2" else "no",
                           "U" if b in UNKNOWN else "yes" if b == "2" else "no") for a, b in values]
                stats[f"{scope}.direct_support_binary"] = agreement(binary)
            if field == "relation":
                binary = [("U" if a in UNKNOWN else "different" if a == "different" else "same_group",
                           "U" if b in UNKNOWN else "different" if b == "different" else "same_group") for a, b in values]
                stats["question_pair.shared_group_binary"] = agreement(binary)
    return {
        "status": "invalid_or_incomplete_submission" if errors else "valid_trial_submission_structure",
        "errors": errors, "normalized_working_rows": normalized,
        "judgment_comparisons": comparisons, "disagreements_for_adjudication": disagreements,
        "descriptive_trial_agreement": stats,
        "completed_form_rows_after_structure_checks": len(normalized) if not errors else 0,
        "registration_and_blinding_are_self_reported": True,
        "human_identity_authenticated": False, "actual_blinding_verified": False,
        "semantic_support_verified": False, "accepted_as_gold": False, "frozen_test_set": False,
        "limitations": "Trial descriptive statistics only, before adjudication; no pooled cross-field kappa, formal inference, confidence intervals, quality certification or label replacement.",
    }
