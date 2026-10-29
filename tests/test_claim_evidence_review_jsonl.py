from scripts.validate_claim_evidence_review_jsonl import validate_rows


def casebook_row():
    return {"review_case_id": "case-1", "output_id": "output-1", "question_id": "question-1"}


def annotation_row():
    return {
        "review_case_id": "case-1",
        "output_id": "output-1",
        "question_id": "question-1",
        "reviewer_id": "R1",
        "overall_answerability": "answerable",
        "required_answer_points_covered": "complete",
        "claims": [
            {
                "claim_text": "The report states the meeting date.",
                "claim_type": "company_fact",
                "support_status": "supported",
                "cited_evidence_ids": ["A1"],
                "supporting_evidence_ids": ["A1"],
                "required_source_roles": ["annual_report"],
                "role_status": "correct",
                "event_date": "2024-04-01",
                "regulation_applicability": "not_required",
                "rationale": "The cited annual-report passage states this date.",
            }
        ],
        "unresolved_or_missing_evidence": "",
        "reviewer_rationale": "",
    }


def test_blank_review_template_can_be_checked_without_accepting_labels():
    row = annotation_row()
    row.update(
        overall_answerability="",
        required_answer_points_covered="",
        claims=[],
    )
    report = validate_rows([row], [casebook_row()], allow_blank=True)
    assert report["status"] == "valid"
    assert report["rows_blank"] == 1
    assert report["rows_filled"] == 0


def test_complete_structural_annotation_is_valid():
    report = validate_rows([annotation_row()], [casebook_row()])
    assert report["status"] == "valid"
    assert report["rows_filled"] == 1


def test_blank_row_is_not_accepted_as_a_completed_submission():
    row = annotation_row()
    row.update(overall_answerability="", required_answer_points_covered="", claims=[])
    report = validate_rows([row], [casebook_row()])
    assert report["status"] == "invalid"
    assert any(issue["code"] == "blank_annotation" for issue in report["issues"])


def test_invalid_enum_and_evidence_reference_are_reported():
    row = annotation_row()
    row["claims"][0]["support_status"] = {"not": "an enum"}
    row["claims"][0]["cited_evidence_ids"] = ["[A1]"]
    report = validate_rows([row], [casebook_row()])
    codes = {issue["code"] for issue in report["issues"]}
    assert report["status"] == "invalid"
    assert "invalid_enum" in codes
    assert "invalid_evidence_ids" in codes


def test_duplicate_or_mismatched_case_rows_are_rejected():
    row = annotation_row()
    row["output_id"] = "wrong-output"
    report = validate_rows([row, row.copy()], [casebook_row()])
    codes = {issue["code"] for issue in report["issues"]}
    assert "case_mapping_mismatch" in codes
    assert "duplicate_review_case" in codes
    assert "row_count_mismatch" in codes

