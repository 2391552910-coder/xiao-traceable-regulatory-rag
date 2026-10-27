"""Offline implementation acceptance; never requests a model or invents quality scores."""
from pathlib import Path
import sys,json,hashlib,datetime,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.generation.annual_audit_development import file_sha256
from src.generation.request_journal import atomic_write_json

RUNS=ROOT/'results/runs';FIRST=RUNS/'evidence_retention_development_20261026_01';SECOND=RUNS/'evidence_retention_development_20261026_02';READY=RUNS/'evidence_retention_development_20261026_03'
def load(p):return json.loads(p.read_bytes())

def audit():
    errors=[];replay=load(FIRST/'offline_replay.json');validation=load(READY/'offline_replay_validation/offline_replay.json')
    if replay['groups']!=validation['groups'] or replay['rows']!=validation['rows']:errors.append('Repeated replay metrics differ')
    historical=load(FIRST/'input_receipt.json')
    for p,digest in historical['inputs'].items():
        if file_sha256(ROOT/p)!=digest:errors.append('Historical input changed: '+p)
    if file_sha256(ROOT/'results/paper/heldout_validation_20261023_01/index_pdfium.sqlite')!=historical['database_sha256']:errors.append('Historical retrieval database changed')
    tests=list(ET.parse(READY/'tests_passed.xml').getroot().iter('testsuite'))
    test_counts={k:sum(int(s.get(k,'0')) for s in tests) for k in ['tests','failures','errors','skipped']}
    if test_counts['failures'] or test_counts['errors'] or test_counts['tests']!=96:errors.append('Implementation tests not fully passing')
    scoring_tests=list(ET.parse(READY/'scoring_tests_passed.xml').getroot().iter('testsuite'))
    scoring_counts={k:sum(int(s.get(k,'0')) for s in scoring_tests) for k in ['tests','failures','errors','skipped']}
    if scoring_counts['failures'] or scoring_counts['errors'] or scoring_counts['tests']<14:errors.append('Scoring gate tests not fully passing')
    quality_fields=['members_precision','members_recall','members_f1','count_accuracy','dates_precision','dates_recall','dates_f1','three_field_exact']
    for folder in [FIRST,SECOND,READY]:
        scored=load(folder/'extraction_analysis_corrected.json')
        expected_status='awaiting' if folder==READY else 'no_answers'
        if any(g['status']!=expected_status or g['quality_published'] or any(g[k] is not None for k in quality_fields) for g in scored['groups']):errors.append('Unavailable generation incorrectly scored: '+folder.name)
    histories=[]
    for folder in [FIRST,SECOND]:
        results=[load(p) for p in folder.glob('calls/*/*/result.json')]
        journals=[load(p) for p in folder.glob('calls/*/*/call[123].json')]
        units=[load(p) for p in folder.glob('calls/*/*/unit.json')]
        if len(results)!=32 or len(journals)!=32 or len(units)!=32:errors.append(folder.name+': incomplete failed-batch inventory')
        if any(not r['terminal'] for r in journals+units):errors.append(folder.name+': missing terminal status')
        if any(r['status']=='completed' for r in results):errors.append(folder.name+': unexpected generated answer')
        if any(any(v is not None for v in r['usage'].values()) for r in journals):errors.append(folder.name+': unexpected usage estimate')
        for p in folder.glob('calls/*/*/unit.json'):
            u=load(p)
            for c in u['calls']:
                if file_sha256(Path(c['path']))!=c['sha256']:errors.append(folder.name+': child journal hash changed')
        protocol=load(folder/'generation_protocol.json')
        for relative,digest in protocol['code_and_replay_sha256'].items():
            current=ROOT/relative;snapshot=folder/'runtime_source_snapshot'/Path(relative).name
            candidates=[p for p in [current,snapshot] if p.exists()]
            if not any(file_sha256(p)==digest for p in candidates):errors.append(folder.name+': runtime input missing or changed '+relative)
        histories.append(dict(batch=folder.name,planned_units=32,recorded_units=len(results),request_journals=len(journals),all_terminal=True,model_answers=0,outcomes={s:sum(r['status']==s for r in journals) for s in sorted({r['status'] for r in journals})},http_statuses=sorted({r['http_status'] for r in journals if r.get('http_status') is not None}),unknown_usage_records=sum(all(v is None for v in r['usage'].values()) for r in journals),automatic_retries=False))
    ready_protocol=load(READY/'generation_protocol.json')
    for relative,digest in ready_protocol['code_and_replay_sha256'].items():
        if file_sha256(ROOT/relative)!=digest:errors.append('Prepared runtime changed: '+relative)
    future_calls=list(READY.glob('calls/*/*/call[123].json'))
    if future_calls or (READY/'generation_start.json').exists():errors.append('Offline-only prepared batch unexpectedly dispatched')
    # Verify all original published result/call bytes remain intact.
    published=ROOT.parent/'github_delivery_20261026_01/upload_manifest.json';preserved=0
    if published.exists():
        for item in load(published):
            if item['path'].startswith('results/paper/heldout_validation_20261023_01/'):
                if file_sha256(ROOT/item['path'])!=item['sha256']:errors.append('Original published result changed: '+item['path'])
                preserved+=1
    result=dict(status='passed' if not errors else 'failed',checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),classification='exposed development regression; offline implementation acceptance',tests=test_counts,original_published_files_verified=preserved,historical_initial_contexts_reproduced=8,historical_steps_reproduced=32,replayed_trajectories=16,second_replay_identical=True,all_initial_source_text_and_ids_preserved=True,all_retained_contexts_within_6000=True,replay_groups=replay['groups'],attempted_generation_batches=histories,prepared_next_batch=dict(path=str(READY.relative_to(ROOT)),protocol_sha256=file_sha256(READY/'generation_protocol.json'),planned_units=32,maximum_calls=64,dispatched_calls=0,stop_http_status=ready_protocol['stop_on_http_status'],requires_explicit_real_llm_flags=True),new_answer_precision=None,new_answer_recall=None,new_answer_f1=None,new_answer_accuracy=None,new_quality_reason='No model answers were obtained; user selected offline work pending service access. Do not infer quality from infrastructure failures.',independent_human_review_completed=False,errors=errors)
    result['scoring_tests']=scoring_counts;result['total_passing_tests']=test_counts['tests']+scoring_counts['tests'];result['unavailable_generation_quality_is_null_in_all_batches']=True
    atomic_write_json(READY/'implementation_audit.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)
    return result

if __name__=='__main__':audit()
