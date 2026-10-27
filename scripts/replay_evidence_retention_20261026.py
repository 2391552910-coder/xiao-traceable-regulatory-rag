"""Counterfactual context replay with fixed historical queries, never answer generation."""
from pathlib import Path
import sys,json,copy,datetime,csv,statistics,argparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.generation.annual_audit_development import FrozenAuditIndex,answer_prompt,file_sha256
from src.generation.comparison import _pack_context,canonical_sha256
from src.generation.evidence_retention import extend_retained_context

SOURCE=ROOT/'results/paper/heldout_validation_20261023_01'
OUT=ROOT/'results/runs/evidence_retention_development_20261026_01'

def load(path):return json.loads(path.read_bytes())
def save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(path)

def initial_retention(initial,context):
 ids={r['chunk_id'] for r in context['source_records']}
 return sum(r['chunk_id'] in ids for r in initial['source_records'])/len(initial['source_records'])

def replay(source=SOURCE,out=OUT):
 if (out/'offline_replay.json').exists():raise FileExistsError('Preserve the completed replay; select a new output directory')
 out.mkdir(parents=True,exist_ok=True)
 oldprotocol=load(source/'execution_protocol.json');plan=load(ROOT/'results/runs/compact_final_execution_windows_20261020_01/execution_plan.json')
 index=FrozenAuditIndex(source/'index_pdfium.sqlite',plan['reference_tokenizer_file'],tokenizer_sha256=oldprotocol['reference_tokenizer_sha256'])
 inputs={str(p.relative_to(ROOT)):file_sha256(p) for p in sorted((source/'packets').glob('*.json'))}
 for p in [source/'execution_protocol.json',source/'generation_start.json',source/'reference_labels.json',source/'reference_labels_corrected.json']:
  inputs[str(p.relative_to(ROOT))]=file_sha256(p)
 save(out/'input_receipt.json',dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),classification='exposed development regression, not new holdout',historical_queries_reused=True,new_model_calls=0,database_sha256=file_sha256(source/'index_pdfium.sqlite'),inputs=inputs))
 steps=[];trajectories=[];initial_matches=0;trace_matches=0
 for packetpath in sorted((source/'packets').glob('*.json')):
  packet=load(packetpath);q=packet['question'];initial=packet['context'];hits=index.search(q,q['query']);rebuilt=_pack_context(hits,index.count,6000)
  assert rebuilt==initial,'Saved initial context does not reproduce'
  assert answer_prompt(q,initial['context'])==packet['prompt'],'Initial answer prompt changed'
  initial_matches+=1
  for mode in ['k3_agent3_v2','k3_fixed_expand']:
   original=load(source/'calls'/q['question_id']/mode/'result.json');oldhits=hits;retained=copy.deepcopy(initial);legacy=initial;trace=[]
   for t in original['trace']:
    queries=t['queries'];oldhits,legacy=index.legacy_extend(q,oldhits,queries)
    assert legacy['context_sha256']==t['context_sha256'],'Historical context trace does not reproduce'
    trace_matches+=1
    retained,audit=extend_retained_context(q,retained,index.fresh_hits(q,queries),index.count,max_context_tokens=6000,max_new_sources=8)
    assert retained['context'].startswith(initial['context'])
    assert retained['source_records'][:len(initial['source_records'])]==initial['source_records']
    assert retained['reference_tokens']<=6000
    record=dict(question_id=q['question_id'],historical_mode=mode,step=t['step'],queries=queries,legacy_context_sha256=legacy['context_sha256'],retained_context_sha256=retained['context_sha256'],initial_source_retention_legacy=initial_retention(initial,legacy),initial_source_retention_repaired=initial_retention(initial,retained),legacy_reference_tokens=legacy['reference_tokens'],retained_reference_tokens=retained['reference_tokens'],retention_audit=audit)
    steps.append(record);trace.append(record)
   assert legacy==original['final_context'],'Historical final context differs'
   save(out/'replayed_contexts'/q['question_id']/(mode+'.json'),dict(question=q,initial_context=initial,legacy_final_context=legacy,retained_final_context=retained,trace=trace,generated_answer=None,scope='Counterfactual contexts only; historical second query was not replanned on the retained context'))
   trajectories.append(dict(question_id=q['question_id'],historical_mode=mode,initial_retention_legacy=initial_retention(initial,legacy),initial_retention_repaired=initial_retention(initial,retained),new_chunks_repaired=len(retained['source_records'])-len(initial['source_records']),legacy_tokens=legacy['reference_tokens'],repaired_tokens=retained['reference_tokens']))
 # Reference pages are used only after all retrieval contexts are saved.
 refs={r['question_id']:r for r in load(source/'reference_labels_corrected.json')['records']}
 for row in trajectories:
  d=load(out/'replayed_contexts'/row['question_id']/(row['historical_mode']+'.json'));gold=set(refs[row['question_id']]['physical_pages'])
  for label,key in [('initial','initial_context'),('legacy','legacy_final_context'),('repaired','retained_final_context')]:
   pages={r['meta'].get('physical_pdf_page_1based') for r in d[key]['source_records'] if r['meta'].get('corpus_type')=='annual_report'}
   row[label+'_reference_page_coverage']=len(gold&pages)/len(gold)
 groups=[]
 for mode in ['k3_agent3_v2','k3_fixed_expand']:
  rr=[r for r in trajectories if r['historical_mode']==mode]
  keys=[k for k in rr[0] if k not in ['question_id','historical_mode']]
  groups.append(dict(historical_mode=mode,n=len(rr),**{k:statistics.mean(r[k] for r in rr) for k in keys}))
 for path,digest in inputs.items():assert file_sha256(ROOT/path)==digest,'Historical input was modified'
 summary=dict(status='passed',new_model_calls=0,initial_contexts_reproduced=initial_matches,historical_steps_reproduced=trace_matches,trajectories=len(trajectories),all_initial_text_prefixes_preserved=True,all_initial_source_records_and_ids_preserved=True,all_repaired_contexts_within_6000=True,groups=groups,rows=trajectories,limitations=['Saved planning queries are fixed historical traces, not counterfactual model outputs','Page and block coverage do not establish semantic support or answer improvement','All eight questions were already exposed; development regression only'],scripts={Path(__file__).name:file_sha256(Path(__file__)), 'annual_audit_development.py':file_sha256(ROOT/'src/generation/annual_audit_development.py'),'evidence_retention.py':file_sha256(ROOT/'src/generation/evidence_retention.py')})
 save(out/'offline_replay.json',summary)
 with (out/'offline_replay.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(trajectories[0]));writer.writeheader();writer.writerows(trajectories)
 print(json.dumps({k:v for k,v in summary.items() if k not in ['rows','scripts']},ensure_ascii=False,indent=2))
 return summary

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--out-dir',type=Path,default=OUT,help='Use a fresh directory; completed replays are never overwritten')
 args=parser.parse_args();target=args.out_dir.resolve()
 if not target.is_relative_to((ROOT/'results/runs').resolve()):raise ValueError('Replay output must stay inside project results/runs')
 replay(out=target)
