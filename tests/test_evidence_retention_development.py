import importlib.util,json
from pathlib import Path
import pytest
from src.data.clause_splitter import Chunk
from src.generation.comparison import _pack_context
from src.generation.annual_audit_development import answer_prompt

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('retention_runner',ROOT/'scripts/run_evidence_retention_development_20261026.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


class Index:
    count=staticmethod(len)
    def fresh_hits(self,q,queries):
        return [(Chunk('new','doc','title','annual_report','official',None,'新增原文',meta=dict(corpus_type='annual_report',company_name='测试公司',physical_pdf_page_1based=2,stock_code='600036',report_year=2023,source_pdf_sha256='a'*64,system_corpus_input=True)),1.)]


def packet():
    q=dict(question_id='fixture',stock_code='600036',report_year=2023,query='仅提取')
    c=Chunk('initial','doc','title','annual_report','official',None,'初始原文',meta=dict(corpus_type='annual_report',company_name='测试公司',physical_pdf_page_1based=1,stock_code='600036',report_year=2023,source_pdf_sha256='a'*64,system_corpus_input=True))
    ctx=_pack_context([(c,1.)],len,6000)
    return dict(question=q,context=ctx,prompt=answer_prompt(q,ctx['context']))


def transport(calls,error=False):
    def call(request):
        calls.append(request)
        if error:raise OSError('simulated local transport failure')
        planning=request['messages'][0]['content'].startswith('只负责检索规划')
        value=dict(queries=['补充']) if planning else dict(members=['甲'],meeting_count=4,meeting_dates=['2023-04-28'],citations={k:['A1'] for k in ['members','meeting_count','meeting_dates']},limitations=[])
        return dict(http_status=200,response={'model':'fixture-only','choices':[{'message':{'content':json.dumps(value,ensure_ascii=False)},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}},curl_exit=0)
    return call


@pytest.mark.parametrize('mode,expected',[(m,n) for m,n in zip(runner.MODES,[1,1,3,3])])
def test_all_conditions_use_common_durable_calls_and_preserve_sources(tmp_path,monkeypatch,mode,expected):
    monkeypatch.setattr(runner,'OUT',tmp_path);runner.STOP.clear();calls=[]
    monkeypatch.setattr(runner,'make_transport',lambda *args:transport(calls))
    p=packet();result=runner.job(p,mode,Index(),{'api_key':'fixture-secret'})
    assert result['status']=='completed' and len(calls)==expected
    assert result['final_context']['context'].startswith(p['context']['context'])
    assert result['final_context']['source_records'][:1]==p['context']['source_records']
    assert all(json.loads(f.read_bytes())['terminal'] for f in tmp_path.rglob('call[123].json'))
    runner.job(p,mode,Index(),{'api_key':'fixture-secret'});assert len(calls)==expected


def test_transport_failure_is_terminal_and_not_reissued(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'OUT',tmp_path);runner.STOP.clear();calls=[]
    monkeypatch.setattr(runner,'TRANSPORT_FAILURES',0)
    monkeypatch.setattr(runner,'make_transport',lambda *args:transport(calls,error=True))
    result=runner.job(packet(),'k3_agent_preserve',Index(),{'api_key':'fixture-secret'})
    assert result['status']=='failed' and result['failure_reason']=='remote_unknown'
    assert len(calls)==1
    runner.job(packet(),'k3_agent_preserve',Index(),{'api_key':'fixture-secret'});assert len(calls)==1


def test_completed_final_call_can_restore_missing_result_without_request(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'OUT',tmp_path);runner.STOP.clear();calls=[]
    monkeypatch.setattr(runner,'make_transport',lambda *args:transport(calls))
    original=runner.job(packet(),'k3_agent_preserve',Index(),{'api_key':'fixture-secret'})
    (tmp_path/'calls/fixture/k3_agent_preserve/result.json').unlink()
    restored=runner.job(packet(),'k3_agent_preserve',Index(),{'api_key':'fixture-secret'})
    assert restored['status']=='completed' and restored['recovered_from_terminal_journal']
    assert restored['text']==original['text'] and restored['final_context']==original['final_context']
    assert len(calls)==3


def test_three_transport_failures_stop_future_dispatch(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'OUT',tmp_path);runner.STOP.clear();calls=[]
    monkeypatch.setattr(runner,'TRANSPORT_FAILURES',0)
    monkeypatch.setattr(runner,'make_transport',lambda *args:transport(calls,error=True))
    results=[runner.job(packet(),mode,Index(),{'api_key':'fixture-secret'}) for mode in runner.MODES]
    assert len(calls)==3 and runner.STOP.is_set()
    assert results[-1]['failure_reason']=='not_dispatched'
    runner.STOP.clear()


@pytest.mark.parametrize('http_status',[401,403,429])
def test_auth_and_quota_errors_stop_future_model_dispatch(tmp_path,monkeypatch,http_status):
    monkeypatch.setattr(runner,'OUT',tmp_path);runner.STOP.clear();calls=[]
    def rejected(request):
        calls.append(request);return dict(http_status=http_status,response={'error':{'type':'fixture_permission_denied'}},curl_exit=0)
    monkeypatch.setattr(runner,'make_transport',lambda *args:rejected)
    first=runner.job(packet(),'k3_single_dev',Index(),{'api_key':'fixture-secret'})
    second=runner.job(packet(),'k3_agent_preserve',Index(),{'api_key':'fixture-secret'})
    assert len(calls)==1 and runner.STOP.is_set()
    assert first['failure_reason']=='http_failed' and second['failure_reason']=='not_dispatched'
    runner.STOP.clear()
