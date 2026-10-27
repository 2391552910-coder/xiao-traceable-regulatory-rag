import copy

import pytest

from src.data.clause_splitter import Chunk
from src.data.document_corpora import DualCorpusRetriever
from src.generation.comparison import _pack_context, canonical_sha256
from src.generation.evidence_retention import extend_retained_context
from src.generation.supplementary_retrieval import split_blocks


QUESTION = {'question_id': 'RETENTION-2024', 'stock_code': '000001.SZ',
            'company_name': '示例公司', 'report_year': 2024,
            'query': '提取审计委员会成员及会议日期。'}


def chunk(cid, role='annual_report', text='来源正文。\n ', *, stock='000001.SZ', year=2024):
    return Chunk(cid, 'annual-2024' if role == 'annual_report' else 'law-v1',
                 '示例公司2024年报' if role == 'annual_report' else '示例规范',
                 role, 'https://example.test/source.pdf', None, text,
                 meta={'corpus_type': role, 'stock_code': stock, 'report_year': year,
                       'company_name': '示例公司', 'physical_pdf_page_1based': 93,
                       'source_pdf_sha256': 'a' * 64,
                       'source_document_sha256': 'b' * 64, 'system_corpus_input': True})


def context():
    # Use the real project serializer/packer rather than constructing a
    # simplified stand-in for its IDs, whitespace and source-record format.
    return _pack_context([(chunk('AR-1'), .8),
                          (chunk('REG-1', 'regulation', '规范原文。'), .6)], len, 6000)


def test_real_pack_format_retains_original_bytes_records_ids_and_inputs():
    original = context(); q = copy.deepcopy(QUESTION)
    hits = [(chunk('AR-2', text='新增成员。'), .7),
            (chunk('REG-2', 'regulation', '新增规范。'), .5)]
    before_context = copy.deepcopy(original); before_hits = copy.deepcopy(hits)
    updated, audit = extend_retained_context(q, original, hits, len)
    assert original == before_context and hits == before_hits and q == QUESTION
    assert updated is not original
    assert updated['context'].startswith(original['context'] + '\n\n')
    assert updated['source_records'][:2] == original['source_records']
    assert [r['evidence_id'] for r in updated['source_records']] == ['A1', 'R1', 'A2', 'R2']
    assert split_blocks(updated)[0].endswith('来源正文。\n ')
    assert split_blocks(updated)[2] == DualCorpusRetriever.format_evidence(hits[:1], prefix='A').replace('[A1]', '[A2]', 1)
    assert audit['initial_reference_tokens'] == len(original['context'])
    assert audit['final_reference_tokens'] == len(updated['context'])
    assert audit['accepted_count'] == 2 and audit['outcome'] == 'evidence_added'
    assert audit['old_context_is_unchanged_prefix'] and audit['old_ids_and_source_records_preserved']
    assert audit['semantic_support_verified'] is False and audit['source_files_reverified'] is False


def test_missing_source_records_hash_is_added_only_on_a_copy():
    original = context(); del original['source_records_sha256']; before = copy.deepcopy(original)
    updated, audit = extend_retained_context(QUESTION, original, [], len)
    assert original == before and 'source_records_sha256' not in original
    assert updated['source_records_sha256'] == canonical_sha256(original['source_records'])
    assert audit['source_records_hash_added'] and audit['no_new_evidence']
    assert audit['outcome'] == 'no_hits'


def test_full_budget_omits_whole_new_chunk_without_eviction():
    original = context(); cap = len(original['context'])
    updated, audit = extend_retained_context(
        QUESTION, original, [(chunk('AR-2'), .7)], len, max_context_tokens=cap)
    assert updated == original
    assert audit['accepted'] == [] and audit['omitted'][0]['reason'] == 'reference_token_cap_no_truncation'
    assert audit['budget_blocked'] and audit['token_budget_exhausted']
    assert audit['no_new_evidence'] and audit['outcome'] == 'token_budget_blocked'


def test_duplicates_are_accounted_and_new_source_cap_is_delegated():
    original = context()
    hits = [(chunk('AR-1'), .8), (chunk('AR-2'), .7),
            (chunk('AR-2'), .7), (chunk('AR-3'), .6)]
    updated, audit = extend_retained_context(
        QUESTION, original, hits, len, max_new_sources=1)
    assert len(updated['source_records']) == 3
    assert audit['omitted_reason_counts'] == {'duplicate_chunk_id': 2, 'new_source_cap': 1}
    assert audit['new_source_limit_reached'] and audit['accepted_count'] == 1
    unchanged, audit = extend_retained_context(QUESTION, original, hits[:1], len)
    assert unchanged == original and audit['outcome'] == 'duplicates_only'


@pytest.mark.parametrize('stock,year', [('000002.SZ', 2024), ('000001.SZ', 2023)])
def test_new_annual_hit_outside_public_company_or_year_is_rejected(stock, year):
    original = context(); before = copy.deepcopy(original)
    with pytest.raises(ValueError, match='company/year'):
        extend_retained_context(QUESTION, original, [(chunk('AR-WRONG', stock=stock, year=year), 1)], len)
    assert original == before


@pytest.mark.parametrize('field,value', [('stock_code', '000002.SZ'), ('report_year', 2023),
                                        ('source_pdf_sha256', '')])
def test_initial_scope_and_source_digest_are_checked_too(field, value):
    initial = chunk('AR-1'); initial.meta[field] = value
    original = _pack_context([(initial, 1)], len, 6000)
    with pytest.raises(ValueError, match='company/year|SHA256'):
        extend_retained_context(QUESTION, original, [], len)


@pytest.mark.parametrize('role', ['annual_report', 'regulation'])
def test_new_source_hash_is_required_for_each_role(role):
    new = chunk('NEW', role)
    del new.meta['source_pdf_sha256' if role == 'annual_report' else 'source_document_sha256']
    with pytest.raises(ValueError, match='SHA256'):
        extend_retained_context(QUESTION, context(), [(new, 1)], len)


def test_two_rounds_keep_ids_and_never_rewrite_first_round_sources():
    original = context()
    first, _ = extend_retained_context(QUESTION, original, [(chunk('AR-2'), .7)], len)
    first_snapshot = copy.deepcopy(first)
    second, audit = extend_retained_context(
        QUESTION, first, [(chunk('AR-2'), .7), (chunk('REG-2', 'regulation'), .6),
                          (chunk('AR-3'), .5)], len)
    assert first == first_snapshot
    assert second['source_records'][:len(first['source_records'])] == first['source_records']
    assert second['context'].startswith(first['context'] + '\n\n')
    assert [r['evidence_id'] for r in second['source_records']] == ['A1', 'R1', 'A2', 'R2', 'A3']
    assert audit['parent_context_sha256'] == first['context_sha256']
    assert audit['omitted_reason_counts'] == {'duplicate_chunk_id': 1}


@pytest.mark.parametrize('fault', ['context_hash', 'record_hash', 'token_count', 'role_id', 'record_text'])
def test_existing_integrity_errors_are_not_silently_repaired(fault):
    original = context()
    if fault == 'context_hash': original['context'] += 'changed'
    elif fault == 'record_hash': original['source_records_sha256'] = '0' * 64
    elif fault == 'token_count': original['reference_tokens'] += 1
    else:
        record = original['source_records'][0]
        if fault == 'role_id': record['meta']['corpus_type'] = 'regulation'
        else: record['text'] = 'forged original text'
        original['source_records_sha256'] = canonical_sha256(original['source_records'])
    before = copy.deepcopy(original)
    with pytest.raises(ValueError):extend_retained_context(QUESTION, original, [], len)
    assert original == before


def test_existing_context_over_cap_is_rejected_instead_of_truncated():
    original = context()
    with pytest.raises(ValueError, match='already exceeds'):
        extend_retained_context(QUESTION, original, [], len,
                                max_context_tokens=len(original['context']) - 1)


@pytest.mark.parametrize('counter', [lambda text: True, lambda text: -1])
def test_invalid_counter_results_are_rejected(counter):
    with pytest.raises(ValueError, match='counter'):
        extend_retained_context(QUESTION, context(), [], counter)


def test_empty_context_noop_works_and_first_retrieval_is_not_supplemented():
    empty = _pack_context([], len, 6000)
    updated, audit = extend_retained_context(QUESTION, empty, [], len)
    assert updated == empty and audit['outcome'] == 'no_hits'
    assert audit['initial_reference_tokens'] == audit['final_reference_tokens'] == 0
    with pytest.raises(ValueError, match='empty context'):
        extend_retained_context(QUESTION, empty, [(chunk('AR-1'), 1)], len)
    assert empty['context'] == '' and empty['source_records'] == []
