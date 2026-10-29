from src.generation.comparison import audit_response_ids


def test_grouped_body_citations_include_unresolved_id():
    result = {"evaluation": "披露 [A1, R99]；另见 [A2、R3]。", "citations": [], "claims": []}
    audit = audit_response_ids(result, [{"evidence_id": item} for item in ("A1", "A2", "R3")])
    assert audit["cited_ids"] == ["A1", "A2", "R3", "R99"]
    assert audit["unresolved_ids"] == ["R99"]
    assert not audit["semantic_support_verified"]


def test_single_body_citation_remains_supported():
    audit = audit_response_ids({"evaluation": "事实 [A1]"}, [{"evidence_id": "A1"}])
    assert audit["cited_ids"] == ["A1"]
    assert audit["unresolved_ids"] == []
