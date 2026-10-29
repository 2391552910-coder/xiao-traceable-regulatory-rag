"""The generation entry point must expose temporal retrieval without inventing dates."""
import json

import pytest

from src.data.clause_splitter import Chunk
from src.data.document_corpora import DualCorpusRetriever
from src.generation.evaluator import Evaluator
from src.pipeline import generate_dual_corpus_answer


class PoolSearch:
    def search(self, query, top_k=5, pool=None):
        return [(chunk, 1.0) for chunk in pool[:top_k]]


class LLM:
    def __init__(self):
        self.calls = 0
        self.prompt = None

    def chat(self, prompt):
        self.calls += 1
        self.prompt = prompt
        return json.dumps({'evaluation': '', 'claims': [], 'citations': []})


def make_dual():
    annual = Chunk('A', 'A', '年报', 'annual_report', 'fixture', None, '年度信息',
        meta={'corpus_type': 'annual_report', 'stock_code': '000001.SZ',
              'company_name': '示例公司', 'report_year': 2024, 'physical_pdf_page_1based': 1})
    def law(cid, start, end, status='version_interval_confirmed'):
        return Chunk(cid, cid, cid, 'regulation', 'fixture', None, '法规正文', meta={
            'corpus_type': 'regulation', 'source_document_sha256': 'a'*64,
            'version_id': cid, 'applicability_status': status,
            'effective_from': start, 'effective_to_exclusive': end})
    return DualCorpusRetriever(PoolSearch(), [annual,
        law('future', '2025-01-01', '2026-01-01'),
        law('valid', '2020-01-01', '2025-01-01'),
        law('unknown', None, None, 'metadata_unverified')])


def run(query, llm, **kwargs):
    return generate_dual_corpus_answer(make_dual(), Evaluator(llm), query=query,
        stock_name='示例公司', stock_code='000001.SZ', report_year=2024,
        dimension_name='治理', **kwargs)


def test_generation_passes_explicit_date_and_preserves_unknown_audit():
    llm = LLM()
    result = run('事项日期 2024-12-31', llm, temporal_filter=True,
                 target_date='2024-12-31', target_date_role='company_event_date')
    assert [x['chunk_id'] for x in result['retrieved_evidence']['regulations']] == ['valid', 'unknown']
    audit = result['temporal_filter_audit']
    assert audit['applied_before_top_k'] and audit['unknown_policy'] == 'retain'
    assert audit['relation_counts'] == {'outside_declared_interval': 1,
                                        'within_declared_interval': 1, 'unknown': 1}
    assert result['legal_applicability_verified'] is False
    assert '来源R1：事项日期位于声明区间内（仅依据输入元数据）；法律适用性未验证。' in llm.prompt
    assert '来源R2：事项日期与声明区间的关系未知；法律适用性未验证。' in llm.prompt


def test_generation_does_not_infer_event_date_from_report_year():
    llm = LLM()
    with pytest.raises(ValueError, match='explicit'):
        run('评价2024年报告', llm, temporal_filter=True,
            target_date='2024-12-31', target_date_role='company_event_date')
    assert llm.calls == 0


def test_default_remains_unfiltered_and_reports_no_audit():
    llm = LLM()
    result = run('评价2024年报告', llm)
    assert result['retrieved_evidence']['regulations'][0]['chunk_id'] == 'future'
    assert result['temporal_filter_audit'] is None
    assert result['legal_applicability_verified'] is False
    assert '【法规时间筛选说明】' not in llm.prompt


def test_filter_without_target_date_retains_unknown_instead_of_guessing():
    result = run('评价2024年报告', LLM(), temporal_filter=True)
    assert [x['chunk_id'] for x in result['retrieved_evidence']['regulations']] == ['future', 'valid', 'unknown']
    assert result['temporal_filter_audit']['relation_counts'] == {'unknown': 3}
    assert result['temporal_filter_audit']['target_date'] is None
