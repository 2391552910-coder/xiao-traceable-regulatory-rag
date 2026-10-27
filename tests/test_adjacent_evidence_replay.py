import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.replay_adjacent_evidence_20261027 import (
    MODES, QUALITY, check_preservation, construct_context, evaluate_source_targets,
    save, source_characters,
)
from src.data.clause_splitter import Chunk
from src.generation.comparison import _pack_context


QUESTION = dict(stock_code='000001', report_year=2024, query='提取会议日期')


def annual(cid, text):
    return Chunk(cid, 'HELD-000001-2024', '示例公司2024年报', 'annual_report',
                 'https://example.invalid/report.pdf', None, text, meta=dict(
                     corpus_type='annual_report', stock_code='000001', report_year=2024,
                     company_name='示例公司', physical_pdf_page_1based=1,
                     source_pdf_sha256='a' * 64, system_corpus_input=True))


class Index:
    count = staticmethod(len)

    def fresh_hits(self, question, queries):
        assert question == QUESTION
        return [(annual('fixed', 'Fixed-query result'), 1.0)]


class Adjacent:
    def __init__(self):
        self.seeds = []

    def select(self, question, context, *, policy):
        self.seeds.append(copy.deepcopy(context))
        return [(annual('neighbor', 'Whole original neighbor'), 0.0)], dict(policy=policy)


@pytest.mark.parametrize('mode', MODES)
def test_all_predefined_modes_preserve_initial_and_use_original_seeds(mode):
    initial = _pack_context([(annual('seed', 'Original evidence'), 1.0)], len, 6000)
    before = copy.deepcopy(initial)
    adjacent = Adjacent()
    final, stages = construct_context(mode, QUESTION, initial, Index(), adjacent)
    assert initial == before
    check_preservation(initial, final, len)
    assert all(seed == initial for seed in adjacent.seeds)
    ids = [row['chunk_id'] for row in final['source_records']]
    assert len(ids) == len(set(ids))
    assert final['reference_tokens'] <= 6000
    assert all(value is None for value in QUALITY.values())
    if mode == 'initial':
        assert final == initial and stages == []
    if mode == 'fixed_then_adjacent':
        assert ids == ['seed', 'fixed', 'neighbor']
    if mode == 'adjacent_then_fixed':
        assert ids == ['seed', 'neighbor', 'fixed']


def test_whole_over_budget_neighbor_is_omitted_without_eviction():
    initial = _pack_context([(annual('seed', 'X' * 5700), 1.0)], len, 6000)
    class Huge(Adjacent):
        def select(self, *args, **kwargs):
            return [(annual('huge', 'Y' * 1000), 0.0)], dict(policy='continuation_first')
    final, stages = construct_context('adjacent_continuation', QUESTION, initial, Index(), Huge())
    assert final == initial
    assert stages[0]['packing']['budget_blocked']
    assert not stages[0]['packing']['accepted']


def test_preservation_check_catches_changed_record_with_unchanged_text():
    initial = _pack_context([(annual('seed', 'Original'), 1.0)], len, 6000)
    altered = copy.deepcopy(initial)
    altered['source_records'][0]['evidence_id'] = 'A9'
    with pytest.raises(ValueError, match='source records'):
        check_preservation(initial, altered, len)


def test_unique_source_characters_do_not_count_overlapping_windows_twice():
    spans = [dict(source_pdf_sha256='a', physical_pdf_page_1based=1, source_start=0, source_end=1200),
             dict(source_pdf_sha256='a', physical_pdf_page_1based=1, source_start=1000, source_end=1706),
             dict(source_pdf_sha256='a', physical_pdf_page_1based=2, source_start=0, source_end=1200)]
    assert source_characters(spans) == 2906


def test_other_committee_date_occurrence_cannot_satisfy_audit_source_span(tmp_path, monkeypatch):
    import scripts.replay_adjacent_evidence_20261027 as module
    # The same date appears at two locations; only the later one is audit evidence.
    page_text = '10月25日' + '隔' * 100 + '10月25日'
    target = dict(question_id='Q', source_pdf_sha256='a', page=1,
                  start=106, end=112, text='10月25日', label='2024-10-25', kind='audit_meeting_date')
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    path = tmp_path / 'target_fixture.json'
    save(path, dict(targets=[target]))
    verifier = SimpleNamespace(sources={('000001', 2024): dict(source={'sha256': 'a'}, pages={1: page_text})})
    case = dict(question={**QUESTION, 'question_id': 'Q'}, mode='initial', verified_annual_spans=[dict(
        source_pdf_sha256='a', physical_pdf_page_1based=1, source_start=0, source_end=106)])
    try:
        scored = evaluate_source_targets([case], verifier, path)
        assert scored['rows'][0]['full_span_supplied'] is False
        case['verified_annual_spans'][0]['source_end'] = 112
        scored = evaluate_source_targets([case], verifier, path)
        assert scored['rows'][0]['full_span_supplied'] is True
        assert scored['independent_human_validation'] is False
    finally:
        path.unlink()
