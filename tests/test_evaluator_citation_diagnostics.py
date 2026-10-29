import json

from src.generation.evaluator import Evaluator


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.prompt = None

    def chat(self, prompt):
        self.prompt = prompt
        return json.dumps(self.response, ensure_ascii=False)


def evaluate(response, mode='ours'):
    llm = FakeLLM(response)
    result = Evaluator(llm).evaluate(mode, '示例', '000001', 2024, '审计',
        annual_evidence='[A1] report', regulations='[R1] regulation')
    return result, llm.prompt


def test_no_rag_does_not_resolve_ids_from_retrieved_but_undisclosed_sources():
    result, prompt = evaluate({'evaluation': '【年报依据：[A1]】',
        'citations': [{'evidence_id': 'A1'}]}, 'no_rag')
    assert '[A1] report' not in prompt
    assert not result['citation_id_audit'][0]['resolves_to_supplied_evidence']
    assert result['citation_diagnostics']['unresolved_declared_ids'] == ['A1']
    assert result['citation_diagnostics']['unresolved_inline_ids'] == ['A1']


def test_bad_citation_entries_and_wrong_inline_source_type_are_visible():
    result, _ = evaluate({'evaluation': '【年报依据：[R1]】【法规依据：[R99]】',
        'citations': [None, {'evidence_id': 3}, {'evidence_id': 'R99'}, {'evidence_id': 'A1'}]})
    diagnostic = result['citation_diagnostics']
    assert diagnostic['citation_list_valid']
    assert diagnostic['malformed_citation_indices'] == [0, 1]
    assert diagnostic['unresolved_declared_ids'] == ['3', 'R99']
    assert diagnostic['unresolved_inline_ids'] == ['R99']
    assert diagnostic['inline_source_type_mismatches'][0]['evidence_id'] == 'R1'
    assert not diagnostic['semantic_support_verified']
    assert not diagnostic['legal_applicability_verified']


def test_wrong_citation_container_is_reported_without_rewriting_response():
    result, _ = evaluate({'evaluation': '', 'citations': {'members': ['A1']}})
    assert result['citations'] == {'members': ['A1']}
    assert not result['citation_diagnostics']['citation_list_valid']
    assert result['citation_id_audit'] == []
