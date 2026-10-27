"""Small, deterministic extraction fixtures; no API, actual run, or network use."""
import copy
import json

import pytest

from scripts import score_evidence_retention_development_20261026 as scoring


def ref(qid="Q1"):
    return {"question_id": qid, "members": ["甲", "乙"], "meeting_count": 2,
            "meeting_dates": ["2023-01-01", "2023-02-01"]}


def answer(qid="Q1", mode="m", *, members=None, count=2, dates=None):
    parsed = {"members": ["甲", "乙"] if members is None else members,
              "meeting_count": count, "meeting_dates": ["2023-01-01", "2023-02-01"] if dates is None else dates,
              "citations": {k: ["A1"] for k in ("members", "meeting_count", "meeting_dates")}, "limitations": []}
    return {"question": {"question_id": qid}, "mode": mode, "status": "completed",
            "text": json.dumps(parsed, ensure_ascii=False), "parsed": parsed}


def schedule(*qids):
    return [{"question_id": qid, "mode": "m"} for qid in qids]


def test_known_precision_recall_and_macro_f1_use_shared_normalization():
    first = answer(members=[" 甲 ", "乙", "丙"], dates=["2023-01-01"])
    second = answer("Q2", members=["甲"], dates=["2023-01-01", "2023-02-01", "2023-03-01"])
    result = scoring.summarize([first, second], {"Q1": ref(), "Q2": ref("Q2")}, schedule("Q1", "Q2"))
    g = result["groups"][0]
    assert g["status"] == "complete" and g["quality_published"]
    assert g["members_precision"] == pytest.approx(5 / 6)
    assert g["members_recall"] == pytest.approx(3 / 4)
    assert g["members_f1"] == pytest.approx((.8 + 2 / 3) / 2)
    assert g["dates_precision"] == pytest.approx(5 / 6)
    assert g["dates_recall"] == pytest.approx(3 / 4)
    assert g["count_accuracy"] == 1 and g["three_field_exact"] == 0


def test_terminal_failure_is_zero_only_after_condition_has_a_valid_answer():
    failed = {"question_id": "Q2", "mode": "m", "status": "failed", "failure_reason": "http_failed"}
    result = scoring.summarize([answer(), failed], {"Q1": ref(), "Q2": ref("Q2")}, schedule("Q1", "Q2"))
    group = result["groups"][0]
    assert group["valid_model_answers"] == 1 and group["terminal_units"] == 2
    assert all(group[k] == .5 for k in scoring.METRICS)
    assert result["rows"][1]["failure_zero_in_denominator"]


@pytest.mark.parametrize("kind,expected_status", [("absent", "awaiting"), ("partial", "partial"),
                                                 ("running", "partial"), ("403", "no_answers")])
def test_no_unfinished_or_all_service_failure_batch_publishes_quality(kind, expected_status):
    results = []
    if kind in {"partial", "running"}:
        results = [answer()]
        if kind == "running":
            results.append({"question_id": "Q2", "mode": "m", "status": "running"})
    elif kind == "403":
        results = [{"question_id": q, "mode": "m", "status": "failed", "failure_reason": "http_failed"} for q in ["Q1", "Q2"]]
    result = scoring.summarize(results, {"Q1": ref(), "Q2": ref("Q2")}, schedule("Q1", "Q2"))
    assert result["groups"][0]["status"] == expected_status
    assert not result["groups"][0]["quality_published"]
    assert all(result["groups"][0][k] is None for k in scoring.METRICS)
    assert all(row[k] is None for row in result["rows"] for k in scoring.METRICS)


def test_boolean_count_does_not_equal_integer_reference():
    one = ref(); one["meeting_count"] = 1
    result = scoring.summarize([answer(count=True), answer("Q2")], {"Q1": one, "Q2": ref("Q2")}, schedule("Q1", "Q2"))
    assert result["groups"][0]["count_accuracy"] == .5
    assert not result["rows"][0]["valid_model_answer"]
    assert result["rows"][0]["count_accuracy"] == 0


def test_schema_valid_abstention_is_an_answer_with_zero_extraction_not_service_failure():
    result = scoring.summarize([answer(members=[], count=None, dates=[])], {"Q1": ref()}, schedule("Q1"))
    group = result["groups"][0]
    assert group["status"] == "complete" and group["valid_model_answers"] == 1
    assert all(group[k] == 0 for k in scoring.METRICS)


def test_empty_or_malformed_completed_result_is_not_a_valid_answer():
    bad = answer(); bad["text"] = ""
    result = scoring.summarize([bad], {"Q1": ref()}, schedule("Q1"))
    assert result["groups"][0]["status"] == "no_answers"
    bad["text"] = "not empty"; bad["parsed"] = {"queries": ["a planner output"]}
    assert scoring.summarize([bad], {"Q1": ref()}, schedule("Q1"))["groups"][0]["status"] == "no_answers"


@pytest.mark.parametrize("kind", ["duplicate_result", "unscheduled_result", "duplicate_schedule", "missing_reference"])
def test_ambiguous_inventory_or_reference_is_rejected(kind):
    results, refs, planned = [answer()], {"Q1": ref()}, schedule("Q1")
    if kind == "duplicate_result": results.append(answer())
    elif kind == "unscheduled_result": results.append(answer("Q2"))
    elif kind == "duplicate_schedule": planned += schedule("Q1")
    else: refs = {}
    with pytest.raises(ValueError):
        scoring.summarize(results, refs, planned)


def test_summary_is_pure_and_each_condition_is_gated_independently():
    results = [answer(), {"question_id": "Q1", "mode": "other", "status": "failed"}]
    refs = {"Q1": ref()}; planned = schedule("Q1") + [{"question_id": "Q1", "mode": "other"}]
    before = copy.deepcopy((results, refs, planned))
    result = scoring.summarize(results, refs, planned)
    assert (results, refs, planned) == before
    assert [g["status"] for g in result["groups"]] == ["complete", "no_answers"]
