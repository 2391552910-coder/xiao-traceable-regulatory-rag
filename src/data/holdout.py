"""Fail-closed release checks for a future independent test set."""
import re
import unicodedata


def normalized_query(text):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text).lower())


def release_errors(rows, development_queries=(), development_families=(), development_companies=()):
    """Human identities/reviews must be supplied externally, never synthesized here."""
    errors, seen = [], set()
    dev = {normalized_query(q) for q in development_queries}
    for row in rows:
        qid = row.get("query_id", "")
        norm = normalized_query(row.get("query", ""))
        if not qid or not norm or norm in seen or norm in dev:
            errors.append((qid, "empty_duplicate_or_development_query"))
        seen.add(norm)
        family = row.get("family_id")
        if not family or family in development_families:
            errors.append((qid, "missing_or_development_family"))
        if row.get("company_id") in development_companies:
            errors.append((qid, "development_company"))
        if row.get("semantic_leakage_review") != "human_approved":
            errors.append((qid, "semantic_leakage_review_required"))
        reviewers = row.get("human_reviewers", [])
        if len(set(reviewers)) < 2 or any(not str(r).strip() for r in reviewers):
            errors.append((qid, "two_distinct_human_reviewers_required"))
        if row.get("adjudication_status") != "resolved":
            errors.append((qid, "unresolved_labels"))
        if row.get("source_verified") is not True or not row.get("evidence_ids"):
            errors.append((qid, "verified_evidence_required"))
        if row.get("used_for_tuning") is not False:
            errors.append((qid, "tuning_exposure_unknown_or_true"))
    if not rows:
        errors.append(("", "empty_test_set"))
    return errors
