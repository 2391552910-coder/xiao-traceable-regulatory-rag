from src.data.holdout import release_errors


def test_ai_candidates_never_pass_release_gate():
    errors = release_errors([{"query_id": "H1", "query": "新问题", "family_id": "new",
                             "origin": "ai_authored_candidate", "used_for_tuning": False}])
    assert {r[1] for r in errors} >= {"semantic_leakage_review_required",
                                    "two_distinct_human_reviewers_required", "verified_evidence_required"}


def test_paraphrase_family_and_company_reuse_are_blocked():
    row = {"query_id": "H1", "query": "不同措辞", "family_id": "same_topic", "company_id": "same_company"}
    errors = release_errors([row], development_families=["same_topic"], development_companies=["same_company"])
    assert ("H1", "missing_or_development_family") in errors
    assert ("H1", "development_company") in errors


def test_normalized_query_overlap_and_empty_set_are_blocked():
    assert ("H1", "empty_duplicate_or_development_query") in release_errors(
        [{"query_id": "H1", "query": "年报，披露？"}], development_queries=["年报披露"])
    assert release_errors([])
