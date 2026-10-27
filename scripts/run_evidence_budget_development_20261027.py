"""Offline, equal-candidate/equal-budget scheduling comparison; no model path."""
from pathlib import Path
import argparse
import csv
import datetime
import json
import statistics
import sys
from dataclasses import asdict

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts._table_runtime import ensure_local_pdf_libraries
from src.data.annual_tables import file_sha256
from src.generation.annual_audit_development import FrozenAuditIndex,answer_prompt
from src.generation.comparison import _pack_context,canonical_sha256
from src.generation.evidence_budget import POLICIES,allocate_evidence_budget,WINDOW
from src.retrieval.adjacent_chunks import FrozenAdjacentIndex
from src.retrieval.annual_table_index import AnnualTableIndex
from src.retrieval.source_span_audit import FrozenAnnualSourceVerifier,covered_characters

SOURCE=ROOT/'results/paper/heldout_validation_20261023_01'
TABLE=ROOT/'results/runs/annual_table_development_20261027_03'
DEFAULT_OUT=ROOT/'results/runs/evidence_budget_development_20261027_01'


def load(path):return json.loads(path.read_bytes())
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(path)


def run(out):
    ensure_local_pdf_libraries();out=out.resolve()
    if not out.is_relative_to((ROOT/'results/runs').resolve()):raise ValueError('Output must stay in project results/runs')
    if out.exists():raise FileExistsError('Choose a fresh output directory; existing runs are preserved')
    sources=load(SOURCE/'sources.json')
    inputs=[SOURCE/'index_pdfium.sqlite',SOURCE/'execution_protocol.json',SOURCE/'reference_labels.json',SOURCE/'reference_labels_corrected.json',TABLE/'table_index.sqlite',TABLE/'source_verification.json',ROOT/'docs/adjacent_source_diagnostic_20261026.json',ROOT/'docs/预算分配优化实施规划_20261027.txt']
    inputs+=sorted((SOURCE/'packets').glob('*.json'))+sorted((SOURCE/'source_pages_pdfium').glob('*.json'))+[SOURCE/s['file'] for s in sources]
    code=[Path(__file__).resolve(),ROOT/'src/generation/evidence_budget.py',ROOT/'src/generation/evidence_retention.py',ROOT/'src/retrieval/adjacent_chunks.py',ROOT/'src/retrieval/annual_table_index.py',ROOT/'src/data/annual_tables.py']
    protocol=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),new_model_calls=0,
        classification='Already exposed development regression; heuristics designed after inspecting failures, no preregistration or independent holdout claim',
        policies=list(POLICIES),questions=8,planned_contexts=40,reference_token_cap=6000,total_new_source_cap=16,
        retrieval='Same fixed top24 category-balanced table hits and same original-seed one-hop continuation-first candidates in every policy',
        boundary_rule='Literal seed suffix only: unclosed calendar parenthesis or unfinished calendar; only direct same-page successors are promoted. A cue is not proof of relevance.',
        source_policy='Whole chunks only, exact company/year/PDF, immutable initial evidence/IDs, no query generation, no label access during selection',
        inputs_sha256={str(p.relative_to(ROOT)):file_sha256(p) for p in inputs},
        code_sha256={str(p.relative_to(ROOT)):file_sha256(p) for p in code})
    out.mkdir(parents=True);save(out/'offline_protocol.json',protocol)
    old_protocol=load(SOURCE/'execution_protocol.json');plan=load(ROOT/'results/runs/compact_final_execution_windows_20261020_01/execution_plan.json')
    index=FrozenAuditIndex(SOURCE/'index_pdfium.sqlite',plan['reference_tokenizer_file'],tokenizer_sha256=old_protocol['reference_tokenizer_sha256'])
    tables=AnnualTableIndex(TABLE/'table_index.sqlite');neighbors=FrozenAdjacentIndex(SOURCE/'index_pdfium.sqlite')
    verifier=FrozenAnnualSourceVerifier(SOURCE)
    contexts=[];rows=[];all_spans=[]
    for path in sorted((SOURCE/'packets').glob('*.json')):
        packet=load(path);q=packet['question'];initial=packet['context']
        if _pack_context(index.search(q,q['query']),index.count,6000)!=initial or answer_prompt(q,initial['context'])!=packet['prompt']:
            raise ValueError('Original context/prompt does not reproduce')
        table_hits=tables.search(q,q['query'],k=24,balanced=True)
        adjacent_hits,adjacent_audit=neighbors.select(q,initial,policy='continuation_first')
        pool_hash=canonical_sha256(dict(tables=[(asdict(c),s) for c,s in table_hits],neighbors=[(asdict(c),s) for c,s in adjacent_hits],audit=adjacent_audit))
        offered={n for c,_ in table_hits for n in c.meta['structured_fields']['member_name_candidates']}
        save(out/'candidate_pools'/(q['question_id']+'.json'),dict(question=q,candidate_pool_sha256=pool_hash,
            table_ids=[c.chunk_id for c,_ in table_hits],neighbor_ids=[c.chunk_id for c,_ in adjacent_hits],
            offered_table_member_candidates=sorted(offered),neighbor_selection=adjacent_audit))
        for policy in POLICIES:
            final,audit=allocate_evidence_budget(q,initial,table_hits,adjacent_hits,adjacent_audit,index.count,
                policy=policy,max_context_tokens=6000,max_new_sources=16)
            spans=[verifier.verify_record(r,q) for r in final['source_records'] if r['meta'].get('corpus_type')=='annual_report' and WINDOW.fullmatch(r['chunk_id'])]
            all_spans.extend(spans)
            case=dict(question=q,policy=policy,candidate_pool_sha256=pool_hash,final_context=final,audit=audit,
                      verified_window_spans=spans,generated_answer=None,new_answer_quality=None)
            save(out/'contexts'/q['question_id']/(policy+'.json'),case);contexts.append(case)
            structured=[r for r in final['source_records'] if r['meta'].get('source_representation')=='table_field_view']
            supplied={n for r in structured for n in r['meta']['structured_fields']['member_name_candidates']}
            rows.append(dict(question_id=q['question_id'],policy=policy,reference_tokens=final['reference_tokens'],
                new_source_count=len(final['source_records'])-len(initial['source_records']),initial_retention=1.0,
                new_table_row_views=len(structured),offered_table_member_candidates=len(offered),
                supplied_table_member_candidates=len(supplied&offered),
                table_candidate_name_supply_fraction=len(supplied&offered)/len(offered) if offered else None,
                all_offered_table_names_supplied=bool(offered) and offered<=supplied,
                priority_neighbor_count=len(audit['critical_neighbor_ids'])))
    files=sorted((out/'contexts').rglob('*.json'))
    save(out/'contexts_saved_before_reference_analysis.json',dict(contexts=len(files),model_calls=0,
        context_sha256={str(p.relative_to(out)):file_sha256(p) for p in files}))
    reparsed=verifier.reparse_pages(all_spans)
    save(out/'source_verification.json',dict(status='passed',pdf_files=8,
        exact_window_slice_checks=len(all_spans),unique_window_chunks=len({s['chunk_id'] for s in all_spans}),
        pdfium_pages_reparsed=len(reparsed),pdf_receipt=verifier.receipt,reparsed_pages=reparsed,
        table_sources='Reused source-bound table views and the frozen table index; prior 4326-cell re-verification receipt hash is recorded in inputs. Field/body bindings verified on lookup.',
        semantic_support_or_human_validation=False))
    # Only after all 40 contexts and their receipt are on disk may labels be read.
    corrected=load(SOURCE/'reference_labels_corrected.json')
    if corrected['parent_sha256']!=file_sha256(SOURCE/'reference_labels.json'):raise ValueError('Reference erratum parent changed')
    for version,filename in [('frozen','reference_labels.json'),('corrected','reference_labels_corrected.json')]:
        references={r['question_id']:r for r in load(SOURCE/filename)['records']}
        for row,case in zip(rows,contexts):
            pages=set()
            for record in case['final_context']['source_records']:
                m=record['meta']
                if m.get('corpus_type')=='annual_report':pages.update(m.get('physical_pdf_pages_1based',[m['physical_pdf_page_1based']]))
            gold=set(references[row['question_id']]['physical_pages'])
            row[version+'_reference_page_coverage']=len(gold&pages)/len(gold)
    diagnostic=load(ROOT/'docs/adjacent_source_diagnostic_20261026.json')
    targets=[t for t in diagnostic['targets'] if t['kind']=='audit_meeting_date']
    for row,case in zip(rows,contexts):
        relevant=[t for t in targets if t['question_id']==row['question_id']]
        count=None
        if relevant:
            count=0
            for target in relevant:
                entry=verifier.sources[(case['question']['stock_code'],case['question']['report_year'])]
                if entry['pages'][target['page']][target['start']:target['end']]!=target['text']:raise ValueError('Case target source span changed')
                intervals=[(s['source_start'],s['source_end']) for s in case['verified_window_spans'] if s['source_pdf_sha256']==target['source_pdf_sha256'] and s['physical_pdf_page_1based']==target['page']]
                count+=covered_characters(intervals,target['start'],target['end'])==target['end']-target['start']
        row['case_date_source_spans_supplied']=count
        row['case_date_source_spans_total']=len(relevant) if relevant else None
        row['case_joint_table_names_and_dates_supplied']=row['all_offered_table_names_supplied'] and count==len(relevant) if relevant else None
    groups=[]
    keys=['reference_tokens','new_source_count','initial_retention','new_table_row_views','table_candidate_name_supply_fraction','all_offered_table_names_supplied','priority_neighbor_count','frozen_reference_page_coverage','corrected_reference_page_coverage']
    for policy in POLICIES:
        rr=[r for r in rows if r['policy']==policy]
        groups.append(dict(policy=policy,n=len(rr),**{k:statistics.mean(r[k] for r in rr if r[k] is not None) for k in keys}))
    for name,sha in {**protocol['inputs_sha256'],**protocol['code_sha256']}.items():
        if file_sha256(ROOT/name)!=sha:raise ValueError('Input/runtime modified during experiment: '+name)
    summary=dict(status='passed',new_model_calls=0,generated_answers=0,contexts=40,
        initial_contexts_reproduced=8,same_candidate_pool_across_policies=True,
        all_initial_text_records_ids_preserved=True,all_contexts_within_6000=True,all_new_source_counts_within_16=True,
        independent_human_validation=False,new_answer_precision=None,new_answer_recall=None,new_answer_f1=None,new_answer_accuracy=None,
        source_verification=dict(pdf_files=8,unique_window_chunks=len({s['chunk_id'] for s in all_spans}),pdfium_pages_reparsed=len(reparsed)),
        groups=groups,rows=rows,
        limits=['Already exposed development cases; no independent validation or preregistration.',
                'Boundary suffixes are heuristic scheduling cues, not semantic support.',
                'Table candidate-name supply measures retained structured views only; original plain text may already contain these names.',
                'Reference-page coverage and CMB post-output source-span diagnosis are not generated-answer precision/recall.',
                'All five policies and any regressions are preserved; no model or query-planning call.'])
    save(out/'offline_analysis.json',summary)
    with (out/'offline_metrics.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('rows','limits')},ensure_ascii=False,indent=2))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out-dir',type=Path,default=DEFAULT_OUT)
    run(parser.parse_args().out_dir)
