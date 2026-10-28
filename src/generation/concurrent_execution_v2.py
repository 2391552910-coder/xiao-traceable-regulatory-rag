"""API continuation up to 20 workers with explicit drain control and durable journals."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import threading
import time

from src.generation.comparison import canonical_sha256, audit_response_ids, validate_response_structure
from src.generation.llm_client import parse_json
from src.generation.experiment_protocol import ProtocolViolation


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    path=Path(path);temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temp.replace(path)


def remaining_schedule(parent,bundles,plan):
    if parent.get('active_request') is not None or parent['client_calls_attempted']!=parent['client_calls_returned']:
        raise ValueError('Resolve the active request before starting a concurrent continuation')
    units=[{'question_id':b['question']['question_id'],'mode':m,'repeat_id':i}
           for b in bundles for m in plan['methods'] for i in range(1,plan['repeats']+1)]
    random.Random(plan['randomization_seed']).shuffle(units)
    if parent['schedule']!=units or len(units)!=plan['maximum_client_calls']:
        raise ValueError('Parent schedule differs from the sealed randomized design')
    key=lambda r:(r['question_id'],r['mode'],r['repeat_id'])
    returned=[key(r) for r in parent['units']]
    if len(returned)!=len(set(returned)) or returned!=[key(r) for r in units[:len(returned)]]:
        raise ValueError('Parent returned units must be a unique prefix of the registered schedule')
    if len(returned)!=parent['client_calls_returned']:
        raise ValueError('Parent returned counter differs from its saved unit inventory')
    return units[len(returned):]


def remaining_after_concurrent(serial_parent,concurrent_parent,bundles,plan):
    suffix=remaining_schedule(serial_parent,bundles,plan)
    p=concurrent_parent
    if p.get('status')=='running' or p.get('active_requests') or p['client_calls_attempted']!=p['client_calls_returned']:
        raise ValueError('Concurrent parent must be drained with every attempted request returned')
    if p['schedule']!=suffix or len(p['units'])!=p['client_calls_returned']:
        raise ValueError('Concurrent parent schedule or returned count differs')
    key=lambda r:(r['question_id'],r['mode'],r['repeat_id'])
    returned=[key(r) for r in p['units']]
    expected=[key(r) for r in suffix[:p['client_calls_attempted']]]
    if len(returned)!=len(set(returned)) or set(returned)!=set(expected):
        raise ValueError('Concurrent returned inventory differs from the dispatched prefix')
    return suffix[p['client_calls_attempted']:]


def execute_concurrent(bundles,schedule,out_dir,*,client_factory,validate,plan,
                       inherited_units,concurrency=20,api_key='',metadata=None,control_file=None):
    if not isinstance(concurrency,int) or isinstance(concurrency,bool) or not 1<=concurrency<=20:
        raise ValueError('Concurrency must be an integer from 1 to 20')
    out=Path(out_dir)
    if out.exists():raise FileExistsError('Never overwrite a continuation')
    byid={b['question']['question_id']:b for b in bundles}
    keys=[(s['question_id'],s['mode'],s['repeat_id']) for s in schedule]
    inherited_keys={(s['question_id'],s['mode'],s['repeat_id']) for s in inherited_units}
    if not schedule or len(keys)!=len(set(keys)) or inherited_keys.intersection(keys):
        raise ValueError('Continuation must contain unique, previously unreturned units')
    for s in schedule:
        if s['question_id'] not in byid or s['mode'] not in plan['methods'] or s['repeat_id']!=1:
            raise ValueError('Unexpected continuation unit')
    out.mkdir(parents=True);journals=out/'request_journals';journals.mkdir()
    run={**(metadata or {}),'schema_version':'concurrent-page-generation-continuation-v1',
        'status':'running','mock':False,'concurrency':concurrency,'effective_concurrency':concurrency,
        'client_calls_planned':len(schedule),'client_calls_attempted':0,'client_calls_returned':0,
        'primary_total_units':plan['maximum_client_calls'],'inherited_units':inherited_units,
        'schedule':schedule,'units':[],'active_requests':[],'observed_total_tokens':0,
        'responses_with_unknown_usage':0,'automatic_sdk_retries':0,'retries_in_this_run':0,
        'rate_limit_events':0,'max_consecutive_failures':plan['max_consecutive_failures'],
        'max_output_tokens':plan['max_output_tokens'],'temperature':plan['temperature'],
        'request_timeout_seconds':plan['request_timeout_seconds'],'H1':None,'H2':None,
        'semantic_support_verified':False,'legal_applicability_verified':False,
        'created_at_utc':datetime.now(timezone.utc).isoformat()}
    run_path=out/'comparison_run.json';save(run_path,run)
    tls=threading.local();validation_lock=threading.Lock()

    def worker(spec,sequence,journal_path):
        b=byid[spec['question_id']];mode=b['modes'][spec['mode']]
        context=b['contexts'][mode['context_key']]
        unit={**spec,'prompt':mode['prompt'],'prompt_sha256':mode['prompt_sha256'],
            'context_sha256':context['context_sha256'],'source_records_sha256':context['source_records_sha256'],
            'prompt_reference_tokens':mode['prompt_reference_tokens'],
            'context_reference_tokens':context['reference_tokens'],'sequence_in_continuation':sequence,
            'request_started_at_utc':datetime.now(timezone.utc).isoformat(),
            'sdk_call_entered':False,'worker_thread':threading.current_thread().name}
        client=None;started=time.perf_counter();fatal=False;limited=False
        try:
            if not hasattr(tls,'client'):tls.client=client_factory()
            client=tls.client
            client.last_response_metadata={'mock':bool(client.mock)}
            client.last_response_text=None
            client.last_raw_response=None
            client.last_request=None
            with validation_lock:validate('before',client,None)
            journal={**spec,'status':'client_call_entered','sequence_in_continuation':sequence,
                'prompt_sha256':unit['prompt_sha256'],'started_at_utc':unit['request_started_at_utc'],
                'provider_receipt_confirmed':False}
            save(journal_path,journal)
            unit['sdk_call_entered']=True;api_started=time.perf_counter()
            raw=client.chat(mode['prompt']);unit['raw_response']=raw
            unit['api_elapsed_seconds']=time.perf_counter()-api_started
            with validation_lock:validate('after',client,mode['prompt'])
            if client.last_response_metadata.get('finish_reason')!='stop':
                raise ValueError('Generation did not finish as an answer: '+str(client.last_response_metadata.get('finish_reason')))
            result=parse_json(raw);validate_response_structure(result)
            unit.update(status='completed',response=result,citation_id_audit=audit_response_ids(result,context['source_records']))
        except Exception as error:
            fatal=isinstance(error,ProtocolViolation)
            limited=getattr(error,'status_code',None)==429 or type(error).__name__=='RateLimitError'
            unit.update(status='failed',error_type=type(error).__name__,error=str(error),
                protocol_violation=fatal,rate_limited=limited)
            unit['raw_response']=unit.get('raw_response',getattr(client,'last_response_text',None))
        unit.update(elapsed_seconds=time.perf_counter()-started,
            response_metadata=dict(getattr(client,'last_response_metadata',{}) or {}),
            raw_sdk_response=getattr(client,'last_raw_response',None),
            request_parameters=getattr(client,'last_request',None))
        original=json.dumps(unit,ensure_ascii=False,sort_keys=True)
        redacted=original.replace(api_key,'[REDACTED]') if api_key else original
        redacted=re.sub(r'(?i)(bearer\s+)[^\s,;"\\]+',r'\1[REDACTED]',redacted)
        unit=json.loads(redacted);unit.update(redaction_applied=original!=redacted,
            original_record_sha256=hashlib.sha256(original.encode('utf-8')).hexdigest())
        return unit,fatal,limited

    cursor=0;pending={};consecutive=0;pause_until=0.0
    with ThreadPoolExecutor(max_workers=concurrency,thread_name_prefix='rag-api') as pool:
        while cursor<len(schedule) or pending:
            if control_file and Path(control_file).exists():
                directive=json.loads(Path(control_file).read_text(encoding='utf-8'))
                if directive.get('action')=='drain':
                    run['stop_reason']='administrative_drain_requested'
                    run['administrative_control']=directive
            while (cursor<len(schedule) and len(pending)<run['effective_concurrency']
                   and not run.get('stop_reason') and time.monotonic()>=pause_until):
                spec=schedule[cursor];cursor+=1
                filename=f"{spec['question_id']}__{spec['mode']}__repeat_{spec['repeat_id']:03d}.json"
                journal_path=journals/filename
                save(journal_path,{**spec,'status':'logical_call_started','sequence_in_continuation':cursor,
                    'provider_receipt_confirmed':False})
                run['client_calls_attempted']+=1
                run['active_requests'].append({**spec,'journal':str(journal_path.relative_to(out)),
                    'sequence_in_continuation':cursor})
                save(run_path,run)
                future=pool.submit(worker,spec,cursor,journal_path)
                pending[future]=(spec,filename,journal_path)
            if not pending:
                if run.get('stop_reason'):break
                time.sleep(min(max(pause_until-time.monotonic(),0.05),1.0));continue
            done,_=wait(pending,timeout=1.0,return_when=FIRST_COMPLETED)
            for future in done:
                spec,filename,journal_path=pending.pop(future)
                unit,fatal,limited=future.result()
                path=out/filename;save(path,unit)
                entry={**spec,'status':unit['status'],'path':filename,'sha256':sha(path)}
                run['units'].append(entry);run['client_calls_returned']+=1
                run['active_requests']=[r for r in run['active_requests'] if (r['question_id'],r['mode'],r['repeat_id'])!=(spec['question_id'],spec['mode'],spec['repeat_id'])]
                save(journal_path,{**spec,'status':'logical_call_returned','response_file':filename,
                    'response_sha256':entry['sha256'],'response_unit_status':unit['status'],
                    'sdk_call_entered':unit['sdk_call_entered'],'provider_receipt_confirmed':False,
                    'returned_at_utc':datetime.now(timezone.utc).isoformat()})
                usage=unit['response_metadata'].get('total_tokens')
                if isinstance(usage,int) and not isinstance(usage,bool) and usage>=0:run['observed_total_tokens']+=usage
                else:run['responses_with_unknown_usage']+=1
                if not limited:consecutive=consecutive+1 if unit['status']=='failed' else 0
                if limited:
                    run['rate_limit_events']+=1
                    run['effective_concurrency']=max(1,run['effective_concurrency']//2)
                    pause_until=time.monotonic()+60
                    run['rate_limit_dispatch_pause_seconds']=60
                if fatal:run['stop_reason']='protocol_violation_stop_dispatch_drain_active'
                if consecutive>=plan['max_consecutive_failures']:
                    run['stop_reason']=run.get('stop_reason') or 'consecutive_failure_limit_stop_dispatch_drain_active'
                save(run_path,run)
                print(json.dumps({'returned':run['client_calls_returned'],'planned':len(schedule),
                    'active':len(pending),'effective_concurrency':run['effective_concurrency'],
                    'latest_status':unit['status']}),flush=True)
    run.update(status='stopped_by_control' if run.get('stop_reason') else 'completed' if all(e['status']=='completed' for e in run['units']) else 'completed_with_failures',
        unattempted_units=len(schedule)-run['client_calls_attempted'],finished_at_utc=datetime.now(timezone.utc).isoformat())
    save(run_path,run)
    return run
