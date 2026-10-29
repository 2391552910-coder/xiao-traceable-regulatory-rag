import json
import sys

import pytest

import scripts.dual_corpus_rag as cli
from src.data.clause_splitter import Chunk


class LLM:
    mock = True
    model = 'fixture'
    temperature = 0.0

    def chat(self, prompt):
        return json.dumps({'evaluation': '', 'claims': [], 'citations': []})


def arguments(out, query='事项日期 2024-12-31'):
    return ['dual_corpus_rag.py', '--load-index-dir', 'fixture', '--query', query,
            '--company-name', '示例', '--stock-code', '000001.SZ', '--report-year', '2024',
            '--out-dir', str(out), '--mock']


def test_cli_passes_temporal_options_and_persists_audit(tmp_path, monkeypatch):
    annual = Chunk('A', 'A', '年报', 'annual_report', 'fixture', None, '年报', meta={
        'corpus_type': 'annual_report', 'company_name': '示例', 'report_year': 2024,
        'stock_code': '000001.SZ', 'physical_pdf_page_1based': 1})
    law = Chunk('L', 'L', '法规', 'regulation', 'fixture', None, '法规',
                meta={'corpus_type': 'regulation'})

    class Dual:
        def search(self, query, **kwargs):
            assert kwargs['temporal_filter'] is True
            assert kwargs['target_date'] == '2024-12-31'
            assert kwargs['target_date_role'] == 'company_event_date'
            assert kwargs['unknown_temporal'] == 'retain'
            return {'company_evidence': [(annual, 1.0)], 'regulation_evidence': [(law, 1.0)],
                    'temporal_filter_audit': {'target_date': '2024-12-31', 'legal_applicability_verified': False,
                                              'rows': [{'chunk_id': 'L', 'relation': 'unknown'}]}}

    monkeypatch.setattr(cli, 'load_config', lambda path: {
        'retrieval': {'reranker': {'enabled': False}, 'embedding_backend': 'fixture'}, 'llm': {}})
    monkeypatch.setattr(cli, 'load_dual_corpus_index', lambda *args, **kwargs: ([], Dual(), {}))
    monkeypatch.setattr(cli, 'make_llm', lambda *args, **kwargs: LLM())
    out = tmp_path/'output'
    monkeypatch.setattr(sys, 'argv', arguments(out) + ['--temporal-filter', '--target-date', '2024-12-31',
                                                      '--target-date-role', 'company_event_date'])
    assert cli.main() == 0
    result = json.loads((out/'answer_and_sources.json').read_text(encoding='utf-8'))
    assert result['temporal_filter_audit']['target_date'] == '2024-12-31'
    assert result['legal_applicability_verified'] is False


@pytest.mark.parametrize('query,options', [
    ('事项日期 2024-12-31', ['--target-date', '2024-12-31']),
    ('评价2024年报告', ['--temporal-filter', '--target-date', '2024-12-31',
                      '--target-date-role', 'company_event_date']),
    ('事项日期 2024-12-31', ['--temporal-filter', '--target-date', '2024-12-31']),
])
def test_cli_rejects_invalid_date_options_before_any_output(tmp_path, monkeypatch, query, options):
    out = tmp_path/'output'
    monkeypatch.setattr(sys, 'argv', arguments(out, query) + options)
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert not out.exists()
