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


def test_claim_evidence_is_audited_independently_of_citations():
    claims = [{'claim': '甲', 'evidence_status': 'supported', 'evidence_ids': ['A1', 'R99']},
              {'claim': '乙', 'evidence_status': 'supported', 'evidence_ids': []},
              {'claim': '丙', 'evidence_status': 'supported', 'evidence_ids': ['R99']},
              {'claim': '丁', 'evidence_status': 'insufficient', 'evidence_ids': ['A1', 3]}, None]
    result, _ = evaluate({'evaluation': '', 'citations': [], 'claims': claims})
    diagnostic = result['citation_diagnostics']
    assert result['claims'] == claims
    assert diagnostic['claims_list_valid']
    assert diagnostic['malformed_claim_evidence_indices'] == [3, 4]
    assert diagnostic['unresolved_claim_ids'] == ['R99']
    assert diagnostic['supported_claims_without_resolved_ids'] == [1, 2]
    assert not diagnostic['semantic_support_verified']


def test_missing_or_wrong_claim_container_is_reported():
    for claims in (None, {'claim': '甲'}):
        result, _ = evaluate({'evaluation': '', 'citations': [], 'claims': claims})
        assert not result['citation_diagnostics']['claims_list_valid']


def test_no_rag_claim_cannot_resolve_unseen_evidence():
    result, _ = evaluate({'evaluation': '', 'citations': [], 'claims': [
        {'claim': '甲', 'evidence_status': 'supported', 'evidence_ids': ['A1']}]}, 'no_rag')
    assert result['citation_diagnostics']['unresolved_claim_ids'] == ['A1']
    assert result['citation_diagnostics']['supported_claims_without_resolved_ids'] == [0]


def test_dual_pipeline_ignores_id_like_text_inside_evidence():
    from src.data.clause_splitter import Chunk
    from src.pipeline import generate_dual_corpus_answer

    annual = Chunk('AR-P1', 'AR', '示例年报', 'annual_report', 'report', None,
                   '年报正文\n[A99] 这不是系统分配的来源。',
                   meta={'corpus_type': 'annual_report', 'company_name': '示例公司',
                         'stock_code': '000001.SZ', 'report_year': 2024,
                         'physical_pdf_page_1based': 12})
    law = Chunk('LAW-C1', 'LAW', '公司法', 'regulation', '官方', '第一条', '法规正文',
                meta={'corpus_type': 'regulation'})

    class Dual:
        def search(self, *args, **kwargs):
            return {'company_evidence': [(annual, 1)], 'regulation_evidence': [(law, 1)]}

    llm = FakeLLM({'evaluation': '【年报依据：[A99]】',
                   'citations': [{'evidence_id': 'A99'}]})
    result = generate_dual_corpus_answer(
        Dual(), Evaluator(llm), query='评价问题', stock_name='示例公司',
        stock_code='000001.SZ', report_year=2024, dimension_name='董事会治理')
    assert '[A99]' in llm.prompt
    assert result['citation_diagnostics']['supplied_id_method'] == 'explicit_retrieval_ids'
    assert result['citation_diagnostics']['unresolved_declared_ids'] == ['A99']
    assert result['citation_diagnostics']['unresolved_inline_ids'] == ['A99']
    assert result['resolved_citations'] == []
    assert result['inline_resolved_citations'] == []
