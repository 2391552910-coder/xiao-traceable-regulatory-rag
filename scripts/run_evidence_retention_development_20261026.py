"""Prospectively recorded, exposed-case regression of evidence retention.

No reference labels are loaded by generation. Four contemporaneous conditions
share the exact saved initial prompts. This is not an independent holdout.
"""
from pathlib import Path
import sys,json,datetime,random,subprocess,time,threading,argparse,copy,shutil
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.config import load_config
from src.generation.annual_audit_development import (
    FrozenAuditIndex,answer_prompt,planning_prompt,parse_planning,valid_answer,
    file_sha256,FIXED_QUERIES)
from src.generation.comparison import canonical_sha256
from src.generation.supplementary_retrieval import validate_context
from src.generation.evidence_retention import extend_retained_context
from src.generation.request_journal import UnitJournal,atomic_write_json,recover_unit
from src.generation.llm_client import parse_json

SOURCE=ROOT/'results/paper/heldout_validation_20261023_01'
OUT=ROOT/'results/runs/evidence_retention_development_20261026_03'
MODES=('k3_single_dev','k3_fixed_preserve','k3_refine3_dev','k3_agent_preserve')
STOP=threading.Event()
FAILURE_LOCK=threading.Lock()
TRANSPORT_FAILURES=0

def load(path):return json.loads(path.read_bytes())
def save(path,value):atomic_write_json(path,value)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()

def init():
    replay_source=ROOT/'results/runs/evidence_retention_development_20261026_01/offline_replay.json'
    if not (OUT/'offline_replay.json').exists():save(OUT/'offline_replay.json',load(replay_source))
    replay=load(OUT/'offline_replay.json')
    if replay['status']!='passed' or replay['initial_contexts_reproduced']!=8 or replay['historical_steps_reproduced']!=32:
        raise ValueError('Require a successful exact historical context replay before generation')
    source_protocol=load(SOURCE/'execution_protocol.json')
    oldplan=load(ROOT/'results/runs/compact_final_execution_windows_20261020_01/execution_plan.json')
    index=FrozenAuditIndex(SOURCE/'index_pdfium.sqlite',oldplan['reference_tokenizer_file'],tokenizer_sha256=source_protocol['reference_tokenizer_sha256'])
    packets=[load(p) for p in sorted((SOURCE/'packets').glob('*.json'))]
    if len(packets)!=8:raise ValueError('Expected exactly eight saved development packets')
    for p in packets:
        validate_context(p['context'])
        if answer_prompt(p['question'],p['context']['context'])!=p['prompt']:
            raise ValueError('Saved single-call prompt changed')
    schedule=[dict(question_id=p['question']['question_id'],mode=m) for p in packets for m in MODES]
    random.Random(20261026).shuffle(schedule)
    bound=[Path(__file__),ROOT/'scripts/invoke_verified_model_request.ps1',ROOT/'src/generation/annual_audit_development.py',ROOT/'src/generation/evidence_retention.py',ROOT/'src/generation/request_journal.py',ROOT/'src/generation/supplementary_retrieval.py',ROOT/'src/generation/comparison.py',OUT/'offline_replay.json']
    hashes={str(p.relative_to(ROOT)):file_sha256(p) for p in bound}
    protocol=dict(schema_version='evidence-retention-development-v1',classification='exposed development regression, not independent test',scope='One packing change plus durable common execution; no adjacent chunk expansion, gold-driven queries or legal applicability score',source_protocol_sha256=file_sha256(SOURCE/'execution_protocol.json'),source_database_sha256=file_sha256(SOURCE/'index_pdfium.sqlite'),source_packets={p.name:file_sha256(p) for p in sorted((SOURCE/'packets').glob('*.json'))},reference_labels_sha256=file_sha256(SOURCE/'reference_labels.json'),corrected_reference_labels_sha256=file_sha256(SOURCE/'reference_labels_corrected.json'),reference_labels_loaded_by_generation=False,code_and_replay_sha256=hashes,model='k3',temperature=1,max_output_tokens=8192,reasoning_effort='provider default; no claim of matched realized reasoning compute',reference_token_cap=6000,maximum_new_sources_per_round=8,reference_tokenizer_sha256=source_protocol['reference_tokenizer_sha256'],retrieval='Same read-only FTS5 BM25 index, jieba first 60 alphanumeric terms OR, top five per role; no new retrieval exclusions',source_filter='exact company and report year; regulation pool unchanged and date applicability unverified',fixed_queries=FIXED_QUERIES,initial_evidence='Byte-identical saved context and answer prompt, all four conditions',retention_policy='Existing supplementary_retrieval.extend_context through evidence_retention adapter; original text and IDs remain prefix; only whole new chunks that fit',controller='Exactly two query planning rounds then answer; at most two queries per round. No adaptive stop or initial budget reduction introduced.',modes=list(MODES),units=32,maximum_model_calls=64,maximum_concurrency=2,automatic_retries=0,stop_on_http_429=True,strict_final_schema=True,output_exhausted_policy='Record separately and do not count as completed answer even if partial text exists',failure_scoring='All eight planned questions per condition; failed final units score zero for extraction, successful-only quality reported separately',schedule=schedule)
    protocol.update(transport='System.Net.Http.HttpClient through PowerShell, default certificate and hostname verification; authentication over subprocess stdin; no redirects',https_head_preflight=True,stop_after_consecutive_transport_failures=3,stop_on_http_status=[401,403,429],offline_replay_source=str(replay_source.relative_to(ROOT)),offline_replay_source_sha256=file_sha256(replay_source),previous_attempts={'evidence_retention_development_20261026_01':'All 32 initial requests lacked HTTP response due curl Schannel CRYPT_E_NO_REVOCATION_CHECK; retained separately','evidence_retention_development_20261026_02':'All 32 initial requests returned HTTP403 permission_denied_error; no model answers; retained separately'},pre_generation_amendment='Add authorization-failure dispatch stop before a future fresh batch; user selected offline work while service access is unavailable',rerun_classification='Future explicit fresh batch only after service restored; never automatically overwrite or redispatch prior failed units')
    path=OUT/'generation_protocol.json'
    if path.exists():
        if canonical_sha256(load(path))!=canonical_sha256(protocol):raise ValueError('Frozen generation protocol or runtime code changed')
    else:
        if list((OUT/'calls').rglob('call*.json')):raise ValueError('Cannot freeze after calls already exist')
        save(path,protocol)
    return index,packets,protocol

def final_validator(value):
    if not valid_answer(value):raise ValueError('Final answer violates the extraction schema')

def make_transport(folder,call_number,config):
    def transport(request):
        # Request journal and transport_entered are durable before this callback.
        request_path=folder/f'call{call_number}_transport_request.json'
        response_path=folder/f'call{call_number}_response.part'
        save(request_path,request)
        pwsh=shutil.which('pwsh.exe')
        if not pwsh:raise RuntimeError('PowerShell 7 runtime unavailable')
        proc=subprocess.run([pwsh,'-NoLogo','-NoProfile','-NonInteractive','-File',str(ROOT/'scripts/invoke_verified_model_request.ps1'),'-RequestPath',str(request_path),'-ResponsePath',str(response_path)],input=json.dumps(dict(base_url=config['base_url'],api_key=config['api_key'])),text=True,encoding='utf-8',capture_output=True,creationflags=0x08000000)
        try:diagnostic=json.loads(proc.stdout.strip())
        except (ValueError,UnicodeError):diagnostic=dict(http_status=None,transport_error=proc.stderr[-2000:])
        status=diagnostic.get('http_status');body=None
        if response_path.exists():
            try:body=json.loads(response_path.read_bytes())
            except (ValueError,UnicodeError):body={'unparsed_response':response_path.read_text(encoding='utf-8',errors='replace')[:12000]}
        if status in [401,403,429]:STOP.set()
        if body is None and diagnostic.get('transport_error'):body={'transport_diagnostic':diagnostic}
        # No credentials or raw HTTP headers are included in this return value.
        return dict(http_status=status,response=body,transport_exit_code=proc.returncode)
    return transport

def register_outcome(record):
    global TRANSPORT_FAILURES
    with FAILURE_LOCK:
        if record.get('http_status') in [401,403,429]:STOP.set()
        if record['status']=='remote_unknown' and record.get('transport_entered'):
            TRANSPORT_FAILURES+=1
            if TRANSPORT_FAILURES>=3:STOP.set()
        elif record.get('http_status') is not None:
            TRANSPORT_FAILURES=0

def preflight(config):
    pwsh=shutil.which('pwsh.exe')
    if not pwsh:raise RuntimeError('PowerShell 7 runtime unavailable')
    proc=subprocess.run([pwsh,'-NoLogo','-NoProfile','-NonInteractive','-File',str(ROOT/'scripts/invoke_verified_model_request.ps1'),'-HeadOnly'],input=json.dumps(dict(base_url=config['base_url'])),text=True,encoding='utf-8',capture_output=True,creationflags=0x08000000)
    try:result=json.loads(proc.stdout.strip())
    except (ValueError,UnicodeError):result=dict(http_status=None,transport_error=proc.stderr[-2000:])
    result.update(checked_at_utc=now(),authentication_sent=False,model_generation_requested=False,process_exit_code=proc.returncode)
    save(OUT/'https_preflight.json',result)
    if proc.returncode or result.get('http_status') is None:raise RuntimeError('HTTPS preflight failed; no model requests dispatched')
    print('HTTPS_PREFLIGHT',result['http_status'],flush=True)

def job(packet,mode,index,config):
    q=packet['question'];folder=OUT/'calls'/q['question_id']/mode;folder.mkdir(parents=True,exist_ok=True)
    result_path=folder/'result.json';unit_path=folder/'unit.json'
    if result_path.exists():return load(result_path)
    expected=3 if mode in ['k3_refine3_dev','k3_agent_preserve'] else 1
    if unit_path.exists():
        recovered=recover_unit(unit_path,secrets=[config['api_key']])
        progress=load(folder/'context_progress.json') if (folder/'context_progress.json').exists() else dict(context=packet['context'],trace=[])
        finalpath=folder/f'call{expected}.json'
        if recovered['status']=='completed' and finalpath.exists():
            final=load(finalpath)
            if final['status']=='completed' and valid_answer(final.get('parsed')) and recovered.get('result',{}).get('final_context_sha256')==progress['context']['context_sha256']:
                result=dict(status='completed',question=q,mode=mode,text=final['text'],parsed=final['parsed'],initial_context=packet['context'],final_context=progress['context'],trace=progress['trace'],calls=expected,recovered_from_terminal_journal=True)
                save(result_path,result);return result
        # Preserve interrupted output state. Never infer a missing answer from an earlier call.
        result=dict(status='failed',question=q,mode=mode,initial_context=packet['context'],final_context=progress['context'],trace=progress['trace'],calls=len(recovered['calls']),failure_reason='existing_unit_recovered_without_redispatch',journal_status=recovered['status'])
        save(result_path,result);return result
    initial=packet['context'];ctx=copy.deepcopy(initial);trace=[];body='';final_parsed=None
    try:
        with UnitJournal(unit_path,metadata=dict(question_id=q['question_id'],mode=mode,initial_context_sha256=initial['context_sha256']),secrets=[config['api_key']],expected_calls=expected) as unit:
            if mode=='k3_fixed_preserve':
                for step,queries in enumerate(FIXED_QUERIES,1):
                    ctx,audit=extend_retained_context(q,ctx,index.fresh_hits(q,queries),index.count,max_context_tokens=6000,max_new_sources=8)
                    trace.append(dict(step=step,queries=list(queries),context_sha256=ctx['context_sha256'],retention_audit=audit))
                save(folder/'context_progress.json',dict(context=ctx,trace=trace))
            for step in range(expected):
                planning=mode=='k3_agent_preserve' and step<2
                prompt=planning_prompt(q,ctx['context']) if planning else answer_prompt(q,ctx['context'])
                if mode=='k3_refine3_dev' and body:prompt+='\n检查并修订上一轮回答，不能补造来源：'+body
                request=dict(model='k3',messages=[dict(role='user',content=prompt)],temperature=1,max_tokens=8192)
                def before_dispatch(_):
                    if STOP.is_set():raise RuntimeError('Dispatch stopped after quota/interruption signal')
                    validate_context(ctx)
                    if index.count(ctx['context'])>6000:raise ValueError('Reference token budget exceeded')
                    if not ctx['context'].startswith(initial['context']):raise ValueError('Initial evidence text lost')
                    if ctx['source_records'][:len(initial['source_records'])]!=initial['source_records']:raise ValueError('Initial source records changed')
                record=unit.run_call(folder/f'call{step+1}.json',request,make_transport(folder,step+1,config),parser=parse_json,validator=None if planning else final_validator,before_dispatch=before_dispatch,metadata=dict(question_id=q['question_id'],mode=mode,step=step+1,phase='planning' if planning else 'answer',context_sha256=ctx['context_sha256'],source_records_sha256=ctx['source_records_sha256'],reference_tokens=ctx['reference_tokens']))
                register_outcome(record)
                if record['status']!='completed':
                    unit.finish(dict(failure_status=record['status']))
                    result=dict(status='failed',question=q,mode=mode,initial_context=initial,final_context=ctx,trace=trace,calls=step+1,failure_reason=record['status'],failed_call=step+1,partial_text=record.get('text'))
                    save(result_path,result);print('FAILED',q['question_id'],mode,record['status'],flush=True);return result
                body=record['text'];final_parsed=record['parsed']
                if planning:
                    queries,valid=parse_planning(final_parsed)
                    ctx,audit=extend_retained_context(q,ctx,index.fresh_hits(q,queries),index.count,max_context_tokens=6000,max_new_sources=8)
                    trace.append(dict(step=step+1,queries=queries,planning_schema_valid=valid,context_sha256=ctx['context_sha256'],retention_audit=audit))
                    save(folder/'context_progress.json',dict(context=ctx,trace=trace))
            unit.finish(dict(final_context_sha256=ctx['context_sha256']))
            result=dict(status='completed',question=q,mode=mode,text=body,parsed=final_parsed,initial_context=initial,final_context=ctx,trace=trace,calls=expected)
            save(result_path,result);print('SAVED',q['question_id'],mode,flush=True);return result
    except BaseException as exc:
        result=dict(status='failed',question=q,mode=mode,initial_context=initial,final_context=ctx,trace=trace,failure_reason='unit_exception',error_type=type(exc).__name__)
        save(result_path,result);print('UNIT_FAILED',q['question_id'],mode,type(exc).__name__,flush=True)
        if not isinstance(exc,Exception):STOP.set();raise
        return result

def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true');parser.add_argument('--real-llm',action='store_true');parser.add_argument('--out-dir',type=Path,default=OUT,help='Fresh batch directory inside project results/runs; default only freezes an offline protocol');args=parser.parse_args()
    OUT=args.out_dir.resolve()
    if not OUT.is_relative_to((ROOT/'results/runs').resolve()):raise ValueError('Development output must stay inside project results/runs')
    index,packets,protocol=init()
    print('PROTOCOL_FROZEN',protocol['units'],'units, maximum',protocol['maximum_model_calls'],'calls',flush=True)
    if not args.execute:return
    if not args.real_llm:raise ValueError('Real generation requires explicit --real-llm')
    config=load_config()['llm']
    if not config.get('api_key'):raise ValueError('No configured service credential')
    if not str(config.get('base_url','')).startswith('https://'):raise ValueError('Require the configured HTTPS service')
    preflight(config)
    start=OUT/'generation_start.json'
    if not start.exists():save(start,dict(started_utc=now(),protocol_sha256=file_sha256(OUT/'generation_protocol.json'),classification=protocol['classification']))
    elif load(start)['protocol_sha256']!=file_sha256(OUT/'generation_protocol.json'):raise ValueError('Generation protocol changed')
    qmap={p['question']['question_id']:p for p in packets};errors=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(job,qmap[s['question_id']],s['mode'],index,config):s for s in protocol['schedule']}
        for future in as_completed(futures):
            try:future.result()
            except Exception as exc:errors.append(dict(unit=futures[future],error_type=type(exc).__name__))
    results=[load(p) for p in (OUT/'calls').glob('*/*/result.json')]
    calls=[load(p) for p in (OUT/'calls').glob('*/*/call[123].json')]
    summary=dict(status='finished',finished_utc=now(),planned_units=32,recorded_units=len(results),completed_units=sum(r['status']=='completed' for r in results),failed_units=sum(r['status']!='completed' for r in results),maximum_calls=64,request_journals=len(calls),terminal_requests=sum(bool(c.get('terminal')) for c in calls),transport_entered=sum(bool(c.get('transport_entered')) for c in calls),request_outcomes={status:sum(c['status']==status for c in calls) for status in sorted({c['status'] for c in calls})},dispatch_stopped=STOP.is_set(),uncaught_future_errors=errors,automatic_retries=0)
    save(OUT/'generation_inventory.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
