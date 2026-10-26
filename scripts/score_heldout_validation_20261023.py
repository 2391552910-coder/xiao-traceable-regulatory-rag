"""Deterministic scoring against locked, assistant-extracted source references."""
from pathlib import Path
import json,re,hashlib,statistics,csv,datetime,sys
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/paper/heldout_validation_20261023_01'
def load(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def names(a):return {re.sub(r'\s+','',str(s)) for s in a} if isinstance(a,list) else set()
def dates(a):
 out=set()
 if not isinstance(a,list):return out
 for s in a:
  t=re.sub(r'\s+','',str(s));m=re.fullmatch(r'(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})日?',t)
  if m:
   try:t=datetime.date(*map(int,m.groups())).isoformat()
   except ValueError:pass
  out.add(t)
 return out
def setscore(pred,gold):
 hit=len(pred&gold);p=hit/len(pred) if pred else 0;r=hit/len(gold)
 return dict(precision=p,recall=r,f1=2*p*r/(p+r) if p+r else 0,tp=hit,fp=len(pred-gold),fn=len(gold-pred),exact=pred==gold)
def main():
 corrected='--corrected' in sys.argv;suffix='_corrected' if corrected else '';refpath=OUT/('reference_labels_corrected.json' if corrected else 'reference_labels.json')
 refs={r['question_id']:r for r in load(refpath)['records']};start=load(OUT/'generation_start.json')
 assert sha(OUT/'reference_labels.json')==start['reference_labels_sha256']
 if corrected:assert load(refpath)['parent_sha256']==sha(OUT/'reference_labels.json')
 rows=[];detail=[]
 for path in sorted((OUT/'calls').rglob('result.json')):
  d=load(path);q=d['question'];g=refs[q['question_id']];p=d.get('parsed');p=p if isinstance(p,dict) else {}
  np=names(p.get('members'));nd=dates(p.get('meeting_dates'));ng=names(g['members']);dg=set(g['meeting_dates']);ms=setscore(np,ng);ds=setscore(nd,dg)
  count_ok=type(p.get('meeting_count')) is int and p['meeting_count']==g['meeting_count']
  schema=(isinstance(d.get('parsed'),dict) and isinstance(p.get('members'),list) and all(isinstance(x,str) for x in p['members']) and (p.get('meeting_count') is None or type(p.get('meeting_count')) is int) and 'meeting_count' in p and isinstance(p.get('meeting_dates'),list) and all(isinstance(x,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',x) for x in p['meeting_dates']) and isinstance(p.get('citations'),dict) and all(isinstance(p['citations'].get(k),list) and all(isinstance(z,str) for z in p['citations'][k]) for k in ['members','meeting_count','meeting_dates']) and isinstance(p.get('limitations'),list))
  src=d['final_context']['source_records'];initial=d['initial_context'];allowed={s['evidence_id'] for s in src}
  citations=p.get('citations',{});citations=citations if isinstance(citations,dict) else {}
  cited={str(x).strip('[] ') for xs in citations.values() if isinstance(xs,list) for x in xs}
  calls=[load(f) for f in path.parent.glob('call*.json') if '_request' not in f.stem]
  usage=[c.get('usage',c.get('response',{}).get('usage',{})) for c in calls]
  final_ids={s['chunk_id'] for s in src};initial_ids={s['chunk_id'] for s in initial['source_records']}
  row=dict(question_id=q['question_id'],company=q['company_name'],stock=q['stock_code'],year=q['report_year'],mode=d['mode'],status=d['status'],nonempty=bool(d.get('text','').strip()),schema_valid=bool(schema),members_f1=ms['f1'],members_precision=ms['precision'],members_recall=ms['recall'],count_exact=count_ok,dates_f1=ds['f1'],dates_precision=ds['precision'],dates_recall=ds['recall'],three_field_exact=ms['exact'] and ds['exact'] and count_ok,cited_ids=len(cited),unknown_cited_ids=len(cited-allowed),new_chunks=len(final_ids-initial_ids),calls=len(calls),tokens=sum(u.get('total_tokens',0) for u in usage),seconds=sum(c.get('elapsed',0) for c in calls),tool_queries=sum(len(t['queries']) for t in d['trace']),final_reference_tokens=d['final_context']['reference_tokens'])
  for stage,context in [('initial',initial),('final',d['final_context'])]:
   pages={s['meta'].get('physical_pdf_page_1based') for s in context['source_records'] if s['meta'].get('corpus_type')=='annual_report'}
   row[stage+'_reference_page_coverage']=len(pages&set(g['physical_pages']))/len(g['physical_pages'])
  rows.append(row);detail.append(dict(**row,reference=g,predicted=p,missing_names=sorted(ng-np),extra_names=sorted(np-ng),missing_dates=sorted(dg-nd),extra_dates=sorted(nd-dg),initial_context_sha256=initial['context_sha256'],final_context_sha256=d['final_context']['context_sha256'],result_sha256=sha(path)))
 modes=['k3_single','k28_single','k3_refine3','k3_agent3_v2','k3_fixed_expand','qwen06_single'];groups=[]
 for year in [None,2023,2024]:
  for mode in modes:
   rr=[r for r in rows if r['mode']==mode and (year is None or r['year']==year)]
   if not rr:continue
   groups.append(dict(year=year,mode=mode,n=len(rr),**{k:statistics.mean(r[k] for r in rr) for k in ['members_f1','count_exact','dates_f1','three_field_exact','nonempty','schema_valid','tokens','seconds','new_chunks','tool_queries']},unknown_cited_ids=sum(r['unknown_cited_ids'] for r in rr)))
 paired=[]
 for baseline in ['k3_single','k3_refine3','k3_fixed_expand']:
  for metric in ['members_f1','count_exact','dates_f1','three_field_exact']:
   delta=[]
   for q in refs:
    a=next((r for r in rows if r['question_id']==q and r['mode']=='k3_agent3_v2'),None);b=next((r for r in rows if r['question_id']==q and r['mode']==baseline),None)
    if a and b:delta.append((q,a[metric]-b[metric]))
   if delta:paired.append(dict(baseline=baseline,metric=metric,n=len(delta),mean_delta=statistics.mean(v for _,v in delta),wins=sum(v>0 for _,v in delta),ties=sum(v==0 for _,v in delta),losses=sum(v<0 for _,v in delta),individual_deltas=delta))
 summary=dict(reference_origin=load(OUT/'reference_labels.json')['annotator'],reference_sha256=sha(OUT/'reference_labels.json'),expected_api_units=40,expected_local_units=8,observed_units=len(rows),groups=groups,paired_agent=paired,rows=rows,limits=['Four purposively selected new company clusters; eight question units; no significance/generalization claim','Reference fields extracted and visually checked by current assistant, not independently annotated by humans','Strict extraction metrics do not measure narrative usefulness, semantic citation entailment or regulatory applicability','One draw per condition; provider reasoning defaults and model capacity differ','Haday 2024 member reference limited to explicitly linked current roster; cannot certify historical completeness'],script_sha256=sha(Path(__file__)))
 summary['membership_scope_sensitivity']=[dict(mode=m,n=len(rr),members_f1=statistics.mean(r['members_f1'] for r in rr)) for m in modes for rr in [[r for r in rows if r['mode']==m and r['question_id']!='NEW-603288-2024-AUDIT']] if rr]
 summary['successful_output_sensitivity']=[dict(mode=m,n=len(rr),members_f1=statistics.mean(r['members_f1'] for r in rr),count_exact=statistics.mean(r['count_exact'] for r in rr),dates_f1=statistics.mean(r['dates_f1'] for r in rr),three_field_exact=statistics.mean(r['three_field_exact'] for r in rr)) for m in modes for rr in [[r for r in rows if r['mode']==m and r['status']=='completed' and r['nonempty']]] if rr]
 summary['reference_page_coverage']=[dict(mode=m,n=len(rr),initial=statistics.mean(r['initial_reference_page_coverage'] for r in rr),final=statistics.mean(r['final_reference_page_coverage'] for r in rr)) for m in modes for rr in [[r for r in rows if r['mode']==m]] if rr]
 summary['reference_sha256']=sha(refpath);summary['reference_version']='post-output erratum' if corrected else 'frozen pre-generation'
 save(OUT/('heldout_analysis'+suffix+'.json'),summary);save(OUT/('heldout_scoring_details'+suffix+'.json'),detail)
 if rows:
  with (OUT/('heldout_metrics'+suffix+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print(json.dumps(dict(observed_units=len(rows),overall=[g for g in groups if g['year'] is None]),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
