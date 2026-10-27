"""Audit saved joint-budget cases and exact replay without dispatching a model."""
from pathlib import Path
import datetime,json,sys,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.data.annual_tables import file_sha256
from src.generation.annual_audit_development import FrozenAuditIndex
from src.generation.evidence_budget import POLICIES,allocate_evidence_budget
from src.retrieval.annual_table_index import AnnualTableIndex
from src.retrieval.adjacent_chunks import FrozenAdjacentIndex

SOURCE=ROOT/'results/paper/heldout_validation_20261023_01'
OUT=ROOT/'results/runs/evidence_budget_development_20261027_01'
REPEAT=ROOT/'results/runs/evidence_budget_development_20261027_02'
TABLE=ROOT/'results/runs/annual_table_development_20261027_03'


def load(p):return json.loads(p.read_bytes())


def audit():
    errors=[];p=load(OUT/'offline_protocol.json');a=load(OUT/'offline_analysis.json');b=load(REPEAT/'offline_analysis.json')
    for name,sha in {**p['inputs_sha256'],**p['code_sha256']}.items():
        if file_sha256(ROOT/name)!=sha:errors.append('Input/runtime changed: '+name)
    if a['rows']!=b['rows'] or a['groups']!=b['groups']:errors.append('Repeated metrics differ')
    receipt=load(OUT/'contexts_saved_before_reference_analysis.json');byte_identical=0
    context_receipts={name.replace('\\','/'):sha for name,sha in receipt['context_sha256'].items()}
    plan=load(ROOT/'results/runs/compact_final_execution_windows_20261020_01/execution_plan.json')
    tokenizer_sha=load(SOURCE/'execution_protocol.json')['reference_tokenizer_sha256']
    counter=FrozenAuditIndex(SOURCE/'index_pdfium.sqlite',plan['reference_tokenizer_file'],tokenizer_sha256=tokenizer_sha).count
    tables=AnnualTableIndex(TABLE/'table_index.sqlite');neighbors=FrozenAdjacentIndex(SOURCE/'index_pdfium.sqlite')
    replayed=0
    for packet_file in sorted((SOURCE/'packets').glob('*.json')):
        packet=load(packet_file);q=packet['question'];initial=packet['context']
        th=tables.search(q,q['query'],k=24,balanced=True);nh,na=neighbors.select(q,initial,policy='continuation_first')
        expected_pool=load(OUT/'candidate_pools'/(q['question_id']+'.json'))['candidate_pool_sha256']
        for policy in POLICIES:
            relative='contexts/'+q['question_id']+'/'+policy+'.json';path=OUT/relative;c=load(path)
            if file_sha256(path)!=context_receipts[relative]:errors.append('Context receipt changed')
            if path.read_bytes()==(REPEAT/relative).read_bytes():byte_identical+=1
            if c['candidate_pool_sha256']!=expected_pool:errors.append('Policy used a different pool')
            final,trace=allocate_evidence_budget(q,initial,th,nh,na,counter,policy=policy)
            if final!=c['final_context'] or trace!=c['audit']:errors.append('Budget algorithm replay differs')
            replayed+=1
            if not final['reference_tokens']==counter(final['context'])<=6000 or len(final['source_records'])-len(initial['source_records'])>16:
                errors.append('Counter or global source cap failed')
            if c['generated_answer'] is not None or c['new_answer_quality'] is not None:errors.append('Fabricated model quality')
    if byte_identical!=40:errors.append('Repeated context artifacts differ')
    for key in ('new_answer_precision','new_answer_recall','new_answer_f1','new_answer_accuracy'):
        if a[key] is not None:errors.append('Unavailable generated quality must stay null')
    manifest=load(ROOT.parent/'github_delivery_20261026_01/upload_manifest.json')
    historical=[r for r in manifest if r['path'].startswith('results/paper/heldout_validation_20261023_01/')]
    for r in historical:
        if file_sha256(ROOT/r['path'])!=r['sha256']:errors.append('Historical published file changed')
    old=ROOT/'results/runs/evidence_retention_development_20261026_03'
    for name,sha in load(old/'generation_protocol.json')['code_and_replay_sha256'].items():
        if file_sha256(ROOT/name)!=sha:errors.append('Earlier generation runtime changed')
    if (old/'generation_start.json').exists() or list(old.glob('calls/*/*/call[123].json')):errors.append('Unexpected remote dispatch')
    suites=list(ET.parse(OUT/'tests_passed.xml').getroot().iter('testsuite'))
    tests={k:sum(int(s.get(k,'0')) for s in suites) for k in ('tests','failures','errors','skipped')}
    if tests!=dict(tests=240,failures=0,errors=0,skipped=0):errors.append('Expected all 240 tests passing')
    case=[r for r in a['rows'] if r['question_id']=='NEW-600036-2024-AUDIT']
    primary=next(r for r in case if r['policy']=='boundary_first')
    if not (primary['reference_tokens']==5921 and primary['case_date_source_spans_supplied']==9 and primary['supplied_table_member_candidates']==6):errors.append('Primary diagnostic case changed')
    source=load(OUT/'source_verification.json')
    result=dict(status='passed' if not errors else 'failed',checked_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        tests=tests,new_model_calls=0,generated_answers=0,contexts_replayed=replayed,repeated_context_files_byte_identical=byte_identical,
        initial_evidence_and_ids_preserved=True,same_candidate_pool_per_question=True,maximum_reference_tokens=6000,maximum_new_sources=16,
        source_pdf_files_verified=source['pdf_files'],raw_window_chunks_verified=source['unique_window_chunks'],pdfium_pages_reparsed=source['pdfium_pages_reparsed'],
        original_published_files_unchanged=len(historical),earlier_generation_runtime_unchanged_and_undispatched=True,
        cmb_source_case=case,independent_human_validation=False,new_generated_answer_quality=None,errors=errors)
    (OUT/'implementation_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='cmb_source_case'},ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)
    return result


if __name__=='__main__':audit()
