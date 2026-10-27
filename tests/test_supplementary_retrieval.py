import copy
import json

import pytest

from scripts.run_fixed_context_baselines import execute_baselines
from src.data.clause_splitter import Chunk
from src.data.document_corpora import DualCorpusRetriever
from src.generation.comparison import MODES, _source_record, canonical_sha256, text_sha256
from src.generation.strong_baselines import prepare_supplement, validate_verification
from src.generation.joint_verification import validate_joint_verification
from src.generation.supplementary_retrieval import (GENERIC_RETRIEVE_MODE, JOINT_RETRIEVE_MODE,
    ScopedSupplementRetriever, extend_context, plan_supplement, split_blocks)


def chunk(cid='REG-1', role='regulation', text='规范正文。', code='000001.SZ', year=2024):
    meta = {'corpus_type': role, 'stock_code': code, 'report_year': year, 'company_name': '公司',
        'physical_pdf_page_1based': 2, 'source_pdf_sha256': 'a' * 64, 'source_document_sha256': 'b' * 64,
        'applicability_status': 'metadata_unverified'}
    return Chunk(chunk_id=cid, doc_id=cid.split('-')[0], doc_title='文件', doc_type='regulation',
                 source='fixture', clause_no=None, text=text, meta=meta)


def bundle(both=False, a_id='A1', r_id='R1', trailing=False):
    chunks = [(chunk('AR-1', 'annual_report', '公司原文。\n ' if trailing else '公司原文。'), a_id)]
    if both: chunks.append((chunk(), r_id))
    blocks, records = [], []
    for c, eid in chunks:
        block = DualCorpusRetriever.format_evidence([(c, 1)], prefix=eid[0])
        block = '[' + eid + ']' + block[4:]
        blocks.append(block); records.append(_source_record(c, 1, eid))
    context = '\n\n'.join(blocks); prompt = '根据材料回答：\n' + context
    return {'question': {'question_id': 'SUPP_DEV_01', 'company_name': '公司', 'stock_code': '000001.SZ',
        'report_year': 2024, 'dimension': 'D1', 'query': '请评价该公司的披露。'},
        'budget': {'max_reference_context_tokens': 3000},
        'contexts': {'dual': {'context': context, 'context_sha256': text_sha256(context),
            'source_records': records, 'source_records_sha256': canonical_sha256(records)}},
        'modes': {m: {'context_key': 'dual', 'prompt': prompt, 'prompt_sha256': text_sha256(prompt)} for m in MODES}}


def checks(payload, ids=None, verdict='supported', joint=True):
    proposal = {'checks': [{'text': '公司披露事项。', 'claim_type': 'evaluation',
        'time_scope': 'company_application', 'verdict': verdict, 'evidence_ids': ['A1'] if ids is None else ids,
        'reason': 'explicit fixture'}], 'no_substantive_claims': False}
    return (validate_joint_verification if joint else validate_verification)(proposal, payload, '公司披露事项。')


def test_missing_context_role_and_uncited_available_role_have_different_actions():
    p = prepare_supplement(bundle())
    plan = plan_supplement(p, checks(p), joint=True)
    assert plan['roles'] == ['regulation'] and plan['search_needed']
    p = prepare_supplement(bundle(both=True))
    plan = plan_supplement(p, checks(p), joint=True)
    assert not plan['search_needed'] and plan['reason'] == 'role_available_but_uncited_revision_only'


def test_unknown_date_alone_does_not_trigger_blind_search_but_negative_support_does():
    p = prepare_supplement(bundle(both=True))
    plan = plan_supplement(p, checks(p, ['A1', 'R1']), joint=True)
    assert not plan['search_needed'] and plan['reason'] == 'unknown_target_date_not_inferred_by_search'
    plan = plan_supplement(p, checks(p, ['A1', 'R1'], 'partial'), joint=True)
    assert set(plan['roles']) == {'annual_report', 'regulation'}
    p['declared_target_date'] = '2024-12-31'
    p['declared_target_date_role'] = 'company_event_date'
    assert plan_supplement(p, checks(p, ['A1', 'R1']), joint=True)['roles'] == ['regulation']


def test_append_preserves_old_ids_and_source_whitespace_without_renumbering():
    p = prepare_supplement(bundle(a_id='A3', trailing=True)); original = copy.deepcopy(p)
    new, result = extend_context(p, [(chunk('AR-2', 'annual_report'), .5), (chunk(), .4)], len,
                                 max_context_tokens=3000, max_new_sources=2)
    assert [r['evidence_id'] for r in new['context']['source_records']] == ['A3', 'A4', 'R1']
    assert new['context']['context'].startswith(p['context']['context'] + '\n\n')
    assert new['context']['source_records'][0] == p['context']['source_records'][0]
    assert split_blocks(new['context'])[0].endswith('公司原文。\n ')
    assert p == original and result['old_ids_and_source_records_preserved']
    assert new['context']['context'] in new['generic_prompt']
    assert new['context']['context'] in new['attribution_prompt']


def test_duplicate_budget_and_source_caps_skip_whole_chunks():
    p = prepare_supplement(bundle()); original_text = p['context']['context']
    duplicate = chunk('AR-1', 'annual_report', '公司原文。')
    n, info = extend_context(p, [(duplicate, 1), (chunk(text='X' * 1000), 1)], len,
                            max_context_tokens=len(original_text) + 10, max_new_sources=2)
    assert n['context']['context'] == original_text
    assert [r['reason'] for r in info['omitted']] == ['duplicate_chunk_id', 'reference_token_cap_no_truncation']
    n, info = extend_context(p, [(chunk(), 1), (chunk('REG-2'), .5)], len,
                            max_context_tokens=3000, max_new_sources=1)
    assert len(info['accepted']) == 1 and info['omitted'][0]['reason'] == 'new_source_cap'


@pytest.mark.parametrize('fault', ['company', 'year', 'reviewer', 'role', 'hash', 'score'])
def test_untrusted_out_of_scope_or_unbound_candidates_are_rejected(fault):
    c = chunk('AR-2', 'annual_report'); score = 1
    if fault == 'company': c.meta['stock_code'] = '000002.SZ'
    elif fault == 'year': c.meta['report_year'] = 2023
    elif fault == 'reviewer': c.meta['system_corpus_input'] = False
    elif fault == 'role': c.meta['corpus_type'] = 'reviewer_notes'
    elif fault == 'hash': c.meta['source_pdf_sha256'] = ''
    else: score = float('nan')
    with pytest.raises(ValueError):
        extend_context(prepare_supplement(bundle()), [(c, score)], len, max_context_tokens=3000, max_new_sources=2)


def test_bad_counter_or_initial_hash_is_not_repaired_by_repacking():
    p = prepare_supplement(bundle())
    with pytest.raises(ValueError): extend_context(p, [], lambda _: True, max_context_tokens=3000, max_new_sources=2)
    p['context']['context'] += 'changed'
    with pytest.raises(ValueError): extend_context(p, [], len, max_context_tokens=3000, max_new_sources=2)


class ScopedFixture:
    def __init__(self, fake=False): self.calls, self.fake = [], fake

    def search(self, query, top_k, pool):
        self.calls.append([c.chunk_id for c in pool])
        if self.fake:
            c = copy.deepcopy(pool[0]); c.text = 'forged with same ID'; return [(c, 1)]
        return [(c, 1) for c in pool[:top_k]]


def test_scoped_callback_uses_company_year_subcorpus_and_binds_returned_content():
    class Dual: pass
    d = Dual(); d.annual_chunks = [chunk('AR-1', 'annual_report'), chunk('AR-OTHER', 'annual_report', code='000002.SZ')]
    d.regulation_chunks = [chunk()]; d.retriever = ScopedFixture()
    backend = ScopedSupplementRetriever(d)
    req = {'roles': ['annual_report', 'regulation'], 'max_new_sources': 2,
           'stock_code': '000001.SZ', 'report_year': 2024, 'query': 'fixture'}
    hits = backend(req)
    assert [c.chunk_id for c, _ in hits] == ['AR-1', 'REG-1']
    assert d.retriever.calls == [['AR-1'], ['REG-1']]
    d.retriever = ScopedFixture(fake=True)
    with pytest.raises(ValueError, match='content disagrees'): backend(req)


def test_scoped_supplemental_regulation_search_uses_same_explicit_date_scope():
    class Dual: pass
    valid, future = chunk('REG-VALID'), chunk('REG-FUTURE')
    for law, start, end in ((valid, '2020-01-01', '2025-01-01'),
                            (future, '2025-01-01', '2026-01-01')):
        law.meta.update(version_id=law.chunk_id, applicability_status='version_interval_confirmed',
                        effective_from=start, effective_to_exclusive=end)
    d = Dual(); d.annual_chunks = []; d.regulation_chunks = [future, valid]
    d.retriever = ScopedFixture()
    request = {'roles': ['regulation'], 'max_new_sources': 1, 'query': '截至2024-12-31请查适用规则。',
        'declared_target_date': '2024-12-31', 'declared_target_date_role': 'company_event_date',
        'exclude_chunk_ids': []}
    backend = ScopedSupplementRetriever(d)
    hits = backend(request)
    assert [c.chunk_id for c, _ in hits] == ['REG-VALID']
    assert backend.calls[0]['quotas']['regulation']['temporal_scope_audit']['excluded_outside_declared_interval'] == 1


def test_temporal_filter_then_seen_id_exclusion_skips_empty_regulation_backend():
    class Dual: pass
    future = chunk('REG-FUTURE')
    future.meta.update(version_id='v1', applicability_status='version_interval_confirmed',
                       effective_from='2025-01-01', effective_to_exclusive='2026-01-01')
    d = Dual(); d.annual_chunks = []; d.regulation_chunks = [future]
    class Forbidden:
        def search(self, *args, **kwargs): raise AssertionError('empty post-filter pool must not search')
    d.retriever = Forbidden()
    backend = ScopedSupplementRetriever(d)
    request = {'roles': ['regulation'], 'max_new_sources': 1,
        'query': '截至2024-12-31评价。', 'declared_target_date': '2024-12-31',
        'declared_target_date_role': 'company_event_date', 'exclude_chunk_ids': []}
    assert backend(request) == []
    quota = backend.calls[0]['quotas']['regulation']
    assert quota['temporal_scope_audit']['excluded_outside_declared_interval'] == 1
    assert quota['eligible_chunks_before_exclusion'] == quota['eligible_chunks'] == 0
    assert quota['skipped_empty_pool']


def test_supplement_plan_carries_prepared_date_into_request():
    b = bundle()
    b['question']['query'] = '截至2024-12-31评价该公司的披露。'
    b['declared_target_date'] = '2024-12-31'
    b['declared_target_date_role'] = 'company_event_date'
    b['temporal_scope_audit'] = {'target_date': '2024-12-31', 'unknown_policy': 'retain'}
    p = prepare_supplement(b)
    assert p['temporal_scope_audit'] == b['temporal_scope_audit']
    plan = plan_supplement(p, checks(p), joint=True)
    assert plan['declared_target_date'] == '2024-12-31'
    assert plan['declared_target_date_role'] == 'company_event_date'


def test_generic_and_joint_plans_exclude_identical_provided_chunks_without_mutation():
    p = prepare_supplement(bundle(both=True)); original = copy.deepcopy(p)
    for joint in (False, True):
        result = checks(p, ['A1', 'R1'], 'partial', joint=joint)
        plan = plan_supplement(p, result, joint=joint)
        assert plan['exclude_chunk_ids'] == ['AR-1', 'REG-1']
    assert p == original


def test_seen_candidates_do_not_consume_scoped_search_quotas():
    class Dual: pass
    d = Dual()
    d.annual_chunks = [chunk('AR-1', 'annual_report'), chunk('AR-2', 'annual_report'),
        chunk('AR-OTHER', 'annual_report', code='000002.SZ'), chunk('AR-OLD', 'annual_report', year=2023)]
    d.regulation_chunks = [chunk('REG-1'), chunk('REG-2')]; d.retriever = ScopedFixture()
    backend = ScopedSupplementRetriever(d)
    request = {'roles': ['annual_report', 'regulation'], 'max_new_sources': 2,
        'stock_code': '000001.SZ', 'report_year': 2024, 'query': 'fixture',
        'exclude_chunk_ids': ['AR-1', 'REG-1']}
    found = backend(request)
    assert [c.chunk_id for c, _ in found] == ['AR-2', 'REG-2']
    assert d.retriever.calls == [['AR-2'], ['REG-2']]
    assert all(q['excluded_already_provided'] == 1 for q in backend.calls[0]['quotas'].values())


def test_exhausted_subcorpora_do_not_fall_back_to_global_search():
    class Dual: pass
    class Forbidden:
        def search(self, *a, **kw): raise AssertionError('empty scope must not search globally')
    d = Dual(); d.annual_chunks = [chunk('AR-1', 'annual_report')]
    d.regulation_chunks = [chunk('REG-1')]; d.retriever = Forbidden()
    backend = ScopedSupplementRetriever(d)
    found = backend({'roles': ['annual_report', 'regulation'], 'max_new_sources': 2,
        'stock_code': '000001.SZ', 'report_year': 2024, 'query': 'fixture',
        'exclude_chunk_ids': ['AR-1', 'REG-1']})
    assert found == [] and all(q['skipped_empty_pool'] for q in backend.calls[0]['quotas'].values())


@pytest.mark.parametrize('excluded', ['AR-1', ['AR-1', 'AR-1'], ['MISSING'], [True], ['']])
def test_bad_exclusion_registration_is_rejected_before_search(excluded):
    class Dual: pass
    d = Dual(); d.annual_chunks = [chunk('AR-1', 'annual_report')]
    d.regulation_chunks = [chunk('REG-1')]; d.retriever = ScopedFixture()
    with pytest.raises(ValueError, match='Excluded'):
        ScopedSupplementRetriever(d)({'roles': ['regulation'], 'max_new_sources': 1,
            'query': 'fixture', 'exclude_chunk_ids': excluded})
    assert not d.retriever.calls


def test_backend_cannot_return_an_excluded_source_even_with_a_valid_index_id():
    class Dual: pass
    old = chunk('REG-1'); new = chunk('REG-2')
    class Leaking:
        def search(self, *a, **kw): return [(old, 1)]
    d = Dual(); d.annual_chunks = []; d.regulation_chunks = [old, new]; d.retriever = Leaking()
    with pytest.raises(ValueError, match='outside'):
        ScopedSupplementRetriever(d)({'roles': ['regulation'], 'max_new_sources': 1,
            'query': 'fixture', 'exclude_chunk_ids': ['REG-1']})


def test_exclusion_plan_does_not_repair_changed_context_hash():
    p = prepare_supplement(bundle()); result = checks(p, ['A1'], 'partial')
    p['context']['context'] += 'changed'
    with pytest.raises(ValueError, match='changed'):
        plan_supplement(p, result, joint=True)


class Client:
    mock = True

    def __init__(self, generic=False): self.calls, self.generic = [], generic

    def chat(self, prompt):
        self.calls.append(prompt)
        if prompt.startswith('你对实际回答正文做双源角色核验') or prompt.startswith('你对一份回答做通用证据核验'):
            value = {'checks': [{'text': '公司披露事项。', 'claim_type': 'evaluation', 'time_scope': 'company_application',
                'verdict': 'unsupported' if self.generic else 'supported', 'evidence_ids': ['A1'],
                'reason': 'explicit fixture'}], 'no_substantive_claims': False}
        else:
            ids = ['A1', 'R1'] if '【最多一次修订】' in prompt and '[R1]' in prompt else ['A1']
            value = {'evaluation': '公司披露事项。' + ''.join('[' + x + ']' for x in ids),
                'claims': [{'claim': '公司披露事项。', 'evidence_status': 'supported', 'evidence_ids': ids}],
                'citations': [], 'overall_evidence_status': 'partial'}
        self.last_response_text = json.dumps(value, ensure_ascii=False)
        self.last_response_metadata = {'mock': True, 'finish_reason': 'stop', 'total_tokens': 1}
        return self.last_response_text


def run_fixture(out, client, backend, **extra):
    return execute_baselines([bundle()], client, client, out, modes=[JOINT_RETRIEVE_MODE], max_calls=3,
        supplemental_retriever=backend, reference_counter=len, max_supplemental_calls=1, **extra)


def test_integrated_one_search_and_one_revision_preserve_stage_context_lineage(tmp_path):
    out = tmp_path/'run'; client = Client(); calls = []
    def backend(request):
        state = json.loads((out/'baseline_run.json').read_text(encoding='utf-8'))
        assert state['supplemental_searches_attempted'] == 1 and state['active_retrieval']
        started = json.loads((out/state['active_retrieval']['path']).read_text(encoding='utf-8'))
        assert started['status'] == 'supplemental_search_started'
        assert request['roles'] == ['regulation'] and request['exclude_chunk_ids'] == ['AR-1']; calls.append(request)
        return [(chunk(), 1)]
    state = run_fixture(out, client, backend)
    assert state['status'] == 'completed' and len(calls) == 1 and len(client.calls) == 3
    assert state['supplemental_searches_returned'] == 1 and state['active_retrieval'] is None
    assert state['pipelines'][0]['revision_performed'] and not state['semantic_support_verified']
    records = [json.loads((out/e['path']).read_text(encoding='utf-8')) for e in state['stage_records']]
    assert records[0]['context_sha256'] != records[-1]['context_sha256']
    assert records[-1]['supplemental_context_variant'] == state['context_variants'][0]
    assert records[-1]['validated']['citation_id_audit']['unresolved_ids'] == []


def test_available_but_uncited_role_revises_without_calling_retrieval(tmp_path):
    def forbidden(_): raise AssertionError('should use existing source')
    c = Client()
    state = execute_baselines([bundle(both=True)], c, c, tmp_path/'run', modes=[JOINT_RETRIEVE_MODE], max_calls=3,
        supplemental_retriever=forbidden, reference_counter=len, max_supplemental_calls=1)
    assert state['status'] == 'completed' and state['supplemental_searches_attempted'] == 0
    assert state['pipelines'][0]['supplemental_plan']['reason'] == 'role_available_but_uncited_revision_only'


def test_generic_supplemental_baseline_has_same_search_and_revision_caps(tmp_path):
    c = Client(generic=True); calls = []
    def backend(request): calls.append(request); return [(chunk(), 1)]
    state = execute_baselines([bundle()], c, c, tmp_path/'run', modes=[GENERIC_RETRIEVE_MODE], max_calls=3,
        supplemental_retriever=backend, reference_counter=len, max_supplemental_calls=1)
    assert state['status'] == 'completed' and len(calls) == 1 and len(c.calls) == 3
    assert set(calls[0]['roles']) == {'annual_report', 'regulation'}
    assert calls[0]['exclude_chunk_ids'] == ['AR-1']


@pytest.mark.parametrize('fault', ['callback', 'counter', 'retrieval_budget', 'model_budget', 'context_cap'])
def test_invalid_resources_are_rejected_before_output_or_model_calls(tmp_path, fault):
    out = tmp_path/'bad'; client = Client(); b = bundle()
    args = {'modes': [JOINT_RETRIEVE_MODE], 'max_calls': 3, 'supplemental_retriever': lambda _: [],
            'reference_counter': len, 'max_supplemental_calls': 1}
    if fault == 'callback': args['supplemental_retriever'] = None
    elif fault == 'counter': args['reference_counter'] = None
    elif fault == 'retrieval_budget': args['max_supplemental_calls'] = 0
    elif fault == 'model_budget': args['max_calls'] = 2
    else: b['budget']['max_reference_context_tokens'] = 1
    with pytest.raises(ValueError): execute_baselines([b], client, client, out, **args)
    assert not client.calls and not out.exists()


def test_failed_search_stops_without_revision_or_retry_and_redacts_secret(tmp_path):
    out = tmp_path/'run'; c = Client(); calls = []
    def backend(request): calls.append(request); raise RuntimeError('fixture secret-value')
    state = run_fixture(out, c, backend, secrets=('secret-value',))
    assert state['status'] == 'stopped_by_control' and len(c.calls) == 2 and len(calls) == 1
    assert not state['pipelines'][0]['revision_performed'] and not state['context_variants']
    for p in out.rglob('*.json'): assert 'secret-value' not in p.read_text(encoding='utf-8')


def test_interrupted_search_leaves_durable_started_record_not_a_return(tmp_path):
    out = tmp_path/'run'; c = Client()
    def interrupt(_): raise KeyboardInterrupt('fixture only')
    with pytest.raises(KeyboardInterrupt): run_fixture(out, c, interrupt)
    state = json.loads((out/'baseline_run.json').read_text(encoding='utf-8'))
    assert state['status'] == 'running' and state['active_retrieval']
    assert state['supplemental_searches_attempted'] == 1 and state['supplemental_searches_returned'] == 0
    assert len(c.calls) == 2


def test_observed_token_stop_prevents_even_supplemental_search(tmp_path):
    c = Client(); calls = []
    state = run_fixture(tmp_path/'run', c, lambda r: calls.append(r) or [], max_observed_tokens=2)
    assert state['status'] == 'stopped_by_control' and len(c.calls) == 2 and not calls


def test_changed_initial_input_prevents_revision_after_search(tmp_path):
    out = tmp_path/'run'; c = Client()
    def backend(_):
        (out/'inputs.json').write_text('changed', encoding='utf-8')
        return [(chunk(), 1)]
    state = run_fixture(out, c, backend)
    assert state['status'] == 'input_changed_during_run' and len(c.calls) == 2
    assert not state['pipelines'][0]['revision_performed']
