"""Complete offline governance-table parsing, continuation and retrieval comparison."""
from __future__ import annotations

import argparse
import copy
import csv
import datetime
import html
import importlib.metadata
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts._table_runtime import ensure_local_pdf_libraries
from src.data.annual_tables import (
    VERSION, digest, extract_document, file_sha256, verify_cell,
)
from src.generation.annual_audit_development import FrozenAuditIndex, answer_prompt
from src.generation.comparison import _pack_context
from src.generation.evidence_retention import extend_retained_context
from src.retrieval.adjacent_chunks import FrozenAdjacentIndex
from src.retrieval.annual_table_index import AnnualTableIndex, build_index

SOURCE = ROOT/'results/paper/heldout_validation_20261023_01'
DEFAULT_OUT = ROOT/'results/runs/annual_table_development_20261027_03'
MODES = ('initial', 'adjacent_continuation', 'table_bm25', 'table_balanced', 'table_then_adjacent')


def load(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    tmp.replace(path)


def _source_previews(source_dir, out, document):
    import pypdfium2 as pdfium
    from PIL import ImageDraw
    source = document['source']
    stem = f"{source['stock']}-{source['year']}"
    by_page = defaultdict(list)
    for table in document['tables']:
        by_page[table['page']].append(table)
    split_cells = {c for chain in document['logical_tables'] for row in chain['rows']
                   if row['split_row_merged'] for group in row['parts'] for c in group}
    pdf = pdfium.PdfDocument(source_dir/source['file'])
    try:
        for page_number, tables in by_page.items():
            page = pdf[page_number-1]
            try:
                bitmap = page.render(scale=1.35)
                try:
                    image = bitmap.to_pil().convert('RGB')
                finally:
                    bitmap.close()
            finally:
                page.close()
            draw = ImageDraw.Draw(image)
            sx, sy = image.width/tables[0]['page_width'], image.height/tables[0]['page_height']
            for table in tables:
                draw.rectangle([table['bbox'][0]*sx,table['bbox'][1]*sy,table['bbox'][2]*sx,table['bbox'][3]*sy], outline='#185c9c', width=2)
                for cell in table['cells']:
                    if cell['cell_id'] in split_cells:
                        draw.rectangle([cell['bbox'][0]*sx,cell['bbox'][1]*sy,cell['bbox'][2]*sx,cell['bbox'][3]*sy], outline='#d04524', width=2)
            destination = out/'source_previews'/stem/f'page_{page_number:04d}.png'
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.save(destination)
    finally:
        pdf.close()


def review_materials(out, documents, queue):
    blocks = []
    forms = []
    for doc in documents:
        source = doc['source']
        key = f"{source['stock']}-{source['year']}"
        blocks.append('<h2>'+html.escape(source['company'])+' '+str(source['year'])+'</h2>')
        for chain in doc['logical_tables']:
            cells = {c['cell_id']:c for t in doc['tables'] for c in t['cells']}
            if not any(r['committee_labels'] for r in chain['rows']) and chain['category']=='unclassified_table':
                continue
            images = ' '.join(f'<a href="source_previews/{key}/page_{p:04d}.png" target="_blank">原页{p}</a>' for p in chain['pages'])
            blocks.append('<section><h3>'+html.escape(chain['category'])+' · '+images+'</h3><p>跨页行连接：'+str(chain['split_rows_merged'])+'；表头重复去除：'+str(chain['repeated_headers_removed_from_logical_rows'])+'</p><div class="scroll"><table><thead><tr>')
            columns = max([len(r['values']) for r in chain['rows']] or [len(chain['headers'])])
            headers = chain['headers'] or ['待核表头'+str(i+1) for i in range(columns)]
            blocks.append(''.join('<th>'+html.escape(h)+'</th>' for h in headers)+'<th>归属与复核</th></tr></thead><tbody>')
            for row in chain['rows']:
                is_audit = '审计' in row['committee_labels']
                blocks.append('<tr class="'+('audit' if is_audit else 'other')+'">')
                for value, refs in zip(row['values'],row['parts']):
                    pages = sorted({cells[c]['page'] for c in refs})
                    blocks.append('<td>'+html.escape(value).replace('\n','<br>')+'<small>物理页 '+','.join(map(str,pages))+'</small></td>')
                blocks.append('<td>'+html.escape('、'.join(row['committee_labels']) or '未定')+'<small>'+html.escape(row['scope_basis'])+'</small><small>AI规则建议，未人工确认</small></td></tr>')
                forms.append(dict(stock_code=source['stock'],report_year=source['year'],source_pdf_sha256=source['sha256'],
                                  table_chain_id=chain['chain_id'],row_id=row['row_id'],headers=chain['headers'],
                                  raw_layout_values=row['values'],cell_ids=row['parts'],proposed_committee_scope=row['committee_labels'],
                                  split_row_merged=row['split_row_merged'],reviewer_id=None,reviewer_role=None,
                                  committee_scope_confirmed=None,cell_geometry_confirmed=None,continuation_confirmed=None,
                                  corrected_fields=None,comments=None,independent_human_validation=False))
            blocks.append('</tbody></table></div></section>')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>年报表格与续表离线复核</title>
<style>body{font:15px/1.6 system-ui,sans-serif;margin:28px;color:#172b42;background:#f5f7fa}h1{font-size:28px}section{background:white;padding:18px;margin:18px 0;border:1px solid #d8e0e9;border-radius:10px}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:750px}th,td{border:1px solid #d9e1ea;padding:9px;vertical-align:top;max-width:420px;white-space:normal}th{background:#e9eff6}small{display:block;font-size:11px;color:#62758a;margin-top:6px}.audit{background:#f0faf6}button{padding:9px 15px;margin-right:8px;border:1px solid #98acbf;background:white;border-radius:6px;cursor:pointer}.note{padding:16px;background:#fff4d8;border-left:4px solid #d29b21}a{color:#145f9d}.hide-other .other{display:none}</style>
<h1>年报表格与跨页续表：离线复核</h1><p class="note">本页展示规则提取结果，未经过独立人工确认。蓝框为检测表格，红框为跨页拼接所用单元格。原页链接为本地图片，无网络或模型调用。日期属于人员任免还是会议，需按列标题判断。表格范围为治理关键词页及相邻页。</p>
<button onclick="document.body.classList.add('hide-other')">只看审计委员会候选行</button><button onclick="document.body.classList.remove('hide-other')">显示全部委员会</button><p>填写材料：human_review_template.jsonl；未解决项目：review_queue.json。请保留真实复核者及分歧裁定记录。</p>'''+''.join(blocks)+'</html>'
    (out/'review.html').write_text(page,encoding='utf-8')
    (out/'human_review_template.jsonl').write_text(''.join(json.dumps(f,ensure_ascii=False)+'\n' for f in forms),encoding='utf-8')
    save(out/'review_queue.json',queue)
    return len(forms)


def verify_document_cells(source_dir, doc):
    import pdfplumber
    source = doc['source']
    if file_sha256(source_dir/source['file']) != source['sha256']:
        raise ValueError('Original PDF changed during extraction')
    counts = 0
    used_pages = set()
    with pdfplumber.open(source_dir/source['file']) as pdf:
        for table in doc['tables']:
            for cell in table['cells']:
                verify_cell(pdf.pages[cell['page']-1],cell)
                used_pages.add(cell['page']);counts += 1
    return dict(stock_code=source['stock'],report_year=source['year'],pdf_sha256=source['sha256'],
                cells_reverified=counts,table_pages_reopened=sorted(used_pages),status='passed')


def compare_contexts(out, old_index, tables, adjacent):
    contexts, rows = [], []
    for path in sorted((SOURCE/'packets').glob('*.json')):
        packet = load(path);q=packet['question'];initial=packet['context']
        if _pack_context(old_index.search(q,q['query']),old_index.count,6000) != initial or answer_prompt(q,initial['context']) != packet['prompt']:
            raise ValueError('Initial retrieval or prompt does not reproduce')
        neighbor_hits,neighbor_audit=adjacent.select(q,initial,policy='continuation_first')
        for mode in MODES:
            context=copy.deepcopy(initial);traces=[]
            def extend(name,hits,selection):
                nonlocal context
                context,audit=extend_retained_context(q,context,hits,old_index.count,max_context_tokens=6000,max_new_sources=8)
                traces.append(dict(stage=name,selection=selection,packing=audit))
            if mode in ('table_bm25','table_balanced','table_then_adjacent'):
                balanced=mode!='table_bm25'
                hits=tables.search(q,q['query'],k=24,balanced=balanced)
                extend('table_retrieval',hits,dict(balanced_categories=balanced,query=q['query'],candidate_ids=[c.chunk_id for c,_ in hits],labels_used=False))
            if mode in ('adjacent_continuation','table_then_adjacent'):
                extend('same_page_continuation',neighbor_hits,neighbor_audit)
            n=len(initial['source_records'])
            if not context['context'].startswith(initial['context']) or context['source_records'][:n]!=initial['source_records'] or not context['reference_tokens']==old_index.count(context['context'])<=6000:
                raise ValueError('Context violates preservation or budget')
            case=dict(question=q,mode=mode,initial_context_sha256=initial['context_sha256'],final_context=context,trace=traces,
                      generated_answer=None,new_generated_answer_quality=None)
            destination=out/'contexts'/q['question_id']/(mode+'.json');save(destination,case);contexts.append(case)
            structured=[r for r in context['source_records'] if r['meta'].get('source_representation')=='table_field_view']
            rows.append(dict(question_id=q['question_id'],mode=mode,report_year=q['report_year'],tokens=context['reference_tokens'],
                             initial_retention=1.0,table_row_views=len(structured),
                             cross_page_row_views=sum(r['meta']['split_row_merged'] for r in structured)))
    save(out/'contexts_saved_before_labels.json',dict(contexts=len(contexts),new_model_calls=0,
         sha256={str(p.relative_to(out)):file_sha256(p) for p in sorted((out/'contexts').rglob('*.json'))}))
    return contexts,rows


def evaluate_after_save(out, contexts, rows, chunks):
    from scripts.score_heldout_validation_20261023 import setscore, names
    analyses = {}
    for version,filename in [('frozen','reference_labels.json'),('corrected','reference_labels_corrected.json')]:
        refs={r['question_id']:r for r in load(SOURCE/filename)['records']}
        parsed_rows=[]
        for qid,reference in refs.items():
            stock,year=qid.split('-')[1:3]
            selected=[c for c in chunks if c.meta['stock_code']==stock and c.meta['report_year']==int(year) and '审计' in c.meta['committee_labels']]
            members={n for c in selected for n in c.meta['structured_fields']['member_name_candidates']}
            dates={n for c in selected for n in c.meta['structured_fields']['meeting_date_candidates']}
            counts={n for c in selected for n in c.meta['structured_fields']['meeting_count_candidates']}
            count=next(iter(counts)) if len(counts)==1 else None
            ms=setscore(names(list(members)),names(reference['members']));ds=setscore(dates,set(reference['meeting_dates']))
            parsed_rows.append(dict(question_id=qid,members=sorted(members),meeting_dates=sorted(dates),
                                    explicit_meeting_count=count,count_candidates=sorted(counts),
                                    members_precision=ms['precision'],members_recall=ms['recall'],members_f1=ms['f1'],
                                    dates_precision=ds['precision'],dates_recall=ds['recall'],dates_f1=ds['f1'],
                                    count_accuracy=int(count==reference['meeting_count']),
                                    three_field_exact=ms['exact'] and ds['exact'] and count==reference['meeting_count']))
        keys=['members_precision','members_recall','members_f1','dates_precision','dates_recall','dates_f1','count_accuracy','three_field_exact']
        analyses[version]=dict(reference_sha256=file_sha256(SOURCE/filename),rows=parsed_rows,
                              macro={k:statistics.mean(r[k] for r in parsed_rows) for k in keys},
                              scope='Deterministic table-field parser only, on exposed development questions; not LLM/RAG answer scores. Missing prose fields remain empty/unknown. No count inferred from dates.')
        for row,case in zip(rows,contexts):
            pages=set()
            for record in case['final_context']['source_records']:
                meta=record['meta']
                if meta.get('corpus_type')=='annual_report':
                    pages.update(meta.get('physical_pdf_pages_1based',[meta['physical_pdf_page_1based']]))
            gold=set(refs[row['question_id']]['physical_pages'])
            row[version+'_reference_page_coverage']=len(pages&gold)/len(gold)
    save(out/'parser_field_diagnostics.json',analyses)
    return analyses


def run(out):
    ensure_local_pdf_libraries()
    out=out.resolve()
    if not out.is_relative_to((ROOT/'results/runs').resolve()):
        raise ValueError('Experiment output must remain inside project results/runs')
    if out.exists():
        raise FileExistsError('Choose a fresh output directory; completed or partial runs are preserved')
    code_files=[Path(__file__).resolve(), ROOT/'scripts/_table_runtime.py',ROOT/'scripts/extract_annual_tables.py',
                ROOT/'src/data/annual_tables.py',ROOT/'src/retrieval/annual_table_index.py',
                ROOT/'src/generation/evidence_retention.py',ROOT/'src/retrieval/adjacent_chunks.py']
    sources=load(SOURCE/'sources.json')
    inputs=[SOURCE/'sources.json',SOURCE/'index_pdfium.sqlite',SOURCE/'reference_labels.json',SOURCE/'reference_labels_corrected.json']
    inputs+=sorted((SOURCE/'packets').glob('*.json'))+sorted((SOURCE/'source_pages_pdfium').glob('*.json'))
    inputs+=[SOURCE/s['file'] for s in sources]
    receipt={str(p.relative_to(ROOT)):file_sha256(p) for p in inputs}
    protocol=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),parser_version=VERSION,
                  scope='Exposed development regression on four companies and two annual years; not independent validation',
                  new_model_calls=0,planned_contexts=40,modes=list(MODES),reference_token_cap=6000,
                  source_selection='governance keywords and one physical neighbor, no reference pages used',
                  continuation='consecutive physical pages, matching column geometry, page-boundary position and compatible headers',
                  row_merge='complementary calendar-date fragments, or blank leading keys and continued agenda at a verified boundary; no merging two full dates',
                  temporal_scope='exclude structured rows with a fully parsed date outside the report year; preserve them in raw/review materials',
                  input_sha256=receipt,code_sha256={str(p.relative_to(ROOT)):file_sha256(p) for p in code_files},
                  library_versions={n:importlib.metadata.version(n) for n in ('pdfplumber','pypdfium2','jieba','tokenizers')})
    out.mkdir(parents=True);save(out/'offline_protocol.json',protocol)
    documents=[];verification=[]
    for source in sources:
        pages=load(SOURCE/'source_pages_pdfium'/Path(source['file']).with_suffix('.json'))
        document=extract_document(SOURCE/source['file'],source,pages)
        save(out/'documents'/(Path(source['file']).stem+'.json'),document)
        documents.append(document)
        verification.append(verify_document_cells(SOURCE,document))
        _source_previews(SOURCE,out,document)
        print(source['file'],len(document['tables']),'tables',flush=True)
    chunks,queue=build_index(documents,out/'table_index.sqlite')
    with (out/'structured_chunks.jsonl').open('w',encoding='utf-8') as stream:
        from dataclasses import asdict
        for chunk in chunks:stream.write(json.dumps(asdict(chunk),ensure_ascii=False)+'\n')
    forms=review_materials(out,documents,queue)
    plan=load(ROOT/'results/runs/compact_final_execution_windows_20261020_01/execution_plan.json')
    original=load(SOURCE/'execution_protocol.json')
    old=FrozenAuditIndex(SOURCE/'index_pdfium.sqlite',plan['reference_tokenizer_file'],tokenizer_sha256=original['reference_tokenizer_sha256'])
    contexts,rows=compare_contexts(out,old,AnnualTableIndex(out/'table_index.sqlite'),FrozenAdjacentIndex(SOURCE/'index_pdfium.sqlite'))
    field_diagnostics=evaluate_after_save(out,contexts,rows,chunks)
    save(out/'source_verification.json',dict(status='passed',pdf_files=8,cell_receipts=verification,
         total_cells_reverified=sum(v['cells_reverified'] for v in verification),
         unique_table_pages_reopened=sum(len(v['table_pages_reopened']) for v in verification),independent_human_validation=False))
    for name,sha in receipt.items():
        if file_sha256(ROOT/name)!=sha:raise ValueError('Frozen source input changed: '+name)
    for name,sha in protocol['code_sha256'].items():
        if file_sha256(ROOT/name)!=sha:raise ValueError('Parsing code changed during run: '+name)
    groups=[]
    for mode in MODES:
        selected=[r for r in rows if r['mode']==mode]
        groups.append(dict(mode=mode,n=len(selected),**{k:statistics.mean(r[k] for r in selected)
                      for k in ('tokens','initial_retention','table_row_views','cross_page_row_views','frozen_reference_page_coverage','corrected_reference_page_coverage')}))
    summary=dict(status='passed',new_model_calls=0,generated_answers=0,documents=8,
                 selected_pages=sum(len(d['parsed_pages']) for d in documents),raw_tables=sum(len(d['tables']) for d in documents),
                 table_chains=sum(len(d['logical_tables']) for d in documents),
                 accepted_continuations=sum(a['accepted'] for d in documents for a in d['continuation_decisions']),
                 rejected_continuations=sum(not a['accepted'] for d in documents for a in d['continuation_decisions']),
                 split_rows_merged=sum(c['split_rows_merged'] for d in documents for c in d['logical_tables']),
                 indexed_row_views=len(chunks),human_review_rows=forms,unresolved_or_out_of_scope_rows=len(queue),
                 verified_source_cells=sum(v['cells_reverified'] for v in verification),
                 verified_table_pages=sum(len(v['table_pages_reopened']) for v in verification),
                 contexts=len(contexts),all_initial_evidence_preserved=True,all_contexts_within_6000=True,
                 new_generated_answer_precision=None,new_generated_answer_recall=None,new_generated_answer_f1=None,
                 new_generated_answer_accuracy=None,independent_human_validation=False,
                 parser_only_diagnostic_macro=field_diagnostics['corrected']['macro'],groups=groups,rows=rows,
                 limitations=['The eight exposed questions are development cases, not an independent test.',
                              'Parser-only field diagnostics are not generated-answer metrics or semantic retrieval recall.',
                              'Prose disclosures, scanned pages and unsupported layouts are not invented as table facts.',
                              'Unresolved rows and continuation rejections remain in the review materials; human review is pending.',
                              'Keyword-page mode covers governance candidates, not every table in each annual report; generic CLI supports --all-pages.'])
    save(out/'offline_analysis.json',summary)
    with (out/'retrieval_metrics.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('rows','limitations')},ensure_ascii=False,indent=2))
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir',type=Path,default=DEFAULT_OUT)
    run(parser.parse_args().out_dir)
