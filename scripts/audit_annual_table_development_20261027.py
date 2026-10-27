"""Verify persisted table sources, field views, retrieval and historical invariants."""
from pathlib import Path
import datetime
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts._table_runtime import ensure_local_pdf_libraries
from scripts.run_annual_table_development_20261027 import verify_document_cells
from src.data.annual_tables import file_sha256
from src.retrieval.annual_table_index import AnnualTableIndex,verify_field_views
from src.data.clause_splitter import Chunk

OUT=ROOT/'results/runs/annual_table_development_20261027_03'
SOURCE=ROOT/'results/paper/heldout_validation_20261023_01'


def load(path):return json.loads(path.read_bytes())


def audit():
    ensure_local_pdf_libraries()
    errors=[];protocol=load(OUT/'offline_protocol.json');analysis=load(OUT/'offline_analysis.json')
    for key in ('input_sha256','code_sha256'):
        for relative,sha in protocol[key].items():
            if file_sha256(ROOT/relative)!=sha:errors.append('Changed runtime/input: '+relative)
    docs=[load(p) for p in sorted((OUT/'documents').glob('*.json'))]
    cell_map={};receipts=[]
    for d in docs:
        receipts.append(verify_document_cells(SOURCE,d))
        for table in d['tables']:
            for cell in table['cells']:cell_map[(d['source_pdf_sha256'],cell['cell_id'])]=cell
    units=[Chunk(**json.loads(line)) for line in (OUT/'structured_chunks.jsonl').read_text(encoding='utf-8').splitlines()]
    for chunk in units:
        verify_field_views(chunk)
        for cell in chunk.meta['source_cells']+chunk.meta['header_source_cells']:
            if cell_map.get((chunk.meta['source_pdf_sha256'],cell['cell_id']))!=cell:
                errors.append('Structured source cell differs from the verified raw table')
    contexts=[];receipt=load(OUT/'contexts_saved_before_labels.json')
    for relative,sha in receipt['sha256'].items():
        path=OUT/relative
        if file_sha256(path)!=sha:errors.append('Context receipt mismatch')
        c=load(path);contexts.append(c)
        initial=load(SOURCE/'packets'/(c['question']['question_id']+'.json'))['context'];final=c['final_context']
        if not final['context'].startswith(initial['context']) or final['source_records'][:len(initial['source_records'])]!=initial['source_records']:
            errors.append('Initial evidence or IDs changed')
        if final['reference_tokens']>6000 or c['generated_answer'] is not None or c['new_generated_answer_quality'] is not None:
            errors.append('Budget or offline-only output violation')
        if c['mode'].startswith('table'):
            stage=c['trace'][0]
            hits=AnnualTableIndex(OUT/'table_index.sqlite').search(c['question'],c['question']['query'],k=24,balanced=c['mode']!='table_bm25')
            if [u.chunk_id for u,_ in hits]!=stage['selection']['candidate_ids']:
                errors.append('Saved table retrieval does not reproduce')
    # Exact CMB audit-date supply, counting only verified original window spans.
    targets=load(ROOT/'docs/adjacent_source_diagnostic_20261026.json')['targets']
    dates=[t for t in targets if t['kind']=='audit_meeting_date'];case_rows=[]
    for case in contexts:
        if case['question']['question_id']!='NEW-600036-2024-AUDIT':continue
        intervals=defaultdict(list)
        for r in case['final_context']['source_records']:
            m=re.fullmatch(r'HELD-600036-2024-P(\d+)-S(\d+)',r['chunk_id'])
            if m:intervals[int(m[1])].append((int(m[2]),int(m[2])+len(r['text'])))
        supplied=sum(any(a<=t['start'] and b>=t['end'] for a,b in intervals[t['page']]) for t in dates)
        case_rows.append(dict(mode=case['mode'],date_source_spans_supplied=supplied,total=9,tokens=case['final_context']['reference_tokens']))
    old=ROOT/'results/runs/evidence_retention_development_20261026_03'
    for name,sha in load(old/'generation_protocol.json')['code_and_replay_sha256'].items():
        if file_sha256(ROOT/name)!=sha:errors.append('Earlier prepared generation runtime changed')
    if list(old.glob('calls/*/*/call[123].json')) or (old/'generation_start.json').exists():errors.append('Unexpected model dispatch')
    original=load(ROOT.parent/'github_delivery_20261026_01/upload_manifest.json')
    published=[r for r in original if r['path'].startswith('results/paper/heldout_validation_20261023_01/')]
    for row in published:
        if file_sha256(ROOT/row['path'])!=row['sha256']:errors.append('Historical publication modified')
    preserved=[]
    for number in ('01','02'):
        prior=ROOT/'results/runs'/('annual_table_development_20261027_'+number)
        for name,sha in load(prior/'offline_protocol.json')['code_sha256'].items():
            if file_sha256(prior/'runtime_source_snapshot'/name)!=sha:errors.append('Earlier table runtime snapshot mismatch')
        preserved.append(number)
    suites=list(ET.parse(OUT/'tests_passed.xml').getroot().iter('testsuite'))
    tests={k:sum(int(s.get(k,'0')) for s in suites) for k in ('tests','failures','errors','skipped')}
    if tests!=dict(tests=212,failures=0,errors=0,skipped=0):errors.append('Expected 212 passing tests')
    forms=[json.loads(line) for line in (OUT/'human_review_template.jsonl').read_text(encoding='utf-8').splitlines()]
    if any(f['reviewer_id'] is not None or f['independent_human_validation'] for f in forms):errors.append('Template incorrectly claims human validation')
    if len(contexts)!=40 or len(units)!=120:errors.append('Incomplete context or row-view inventory')
    triage=[]
    row_lookup={r['row_id']:(chain,r) for d in docs for chain in d['logical_tables'] for r in chain['rows']}
    for item in load(OUT/'review_queue.json'):
        chain,row=row_lookup[item['row_id']]
        category=chain['category']
        if category=='external_entity_appointments':tag='excluded_other_entity'
        elif category=='unclassified_table':tag='unclassified_layout_or_nontarget_table'
        elif category=='committee_meetings' and not any('委员' in v for v in row['values'][:1]):tag='general_board_or_scope_unresolved'
        else:tag='no_explicit_target_committee_or_unresolved_fields'
        triage.append(dict(**item,triage=tag,human_confirmed=False))
    (OUT/'review_queue_triage.json').write_text(json.dumps(triage,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    packet=load(ROOT/'results/runs/annual_table_context_cli_smoke_20261027_01/augmented_packet.json')
    if packet['table_index_sha256']!=file_sha256(OUT/'table_index.sqlite') or packet['model_calls']!=0 or packet['context']['reference_tokens']>6000:
        errors.append('Reusable context CLI smoke result failed')
    result=dict(status='passed' if not errors else 'failed',checked_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                table_runtime=protocol['parser_version'],new_model_calls=0,generated_answers=0,
                tests=tests,pdf_files_reverified=len(receipts),raw_cells_reverified=sum(r['cells_reverified'] for r in receipts),
                structured_row_views_verified=len(units),contexts_checked=len(contexts),table_retrieval_reproduced=True,
                historical_published_files_unchanged=len(published),prior_generation_batch_unchanged_and_not_dispatched=True,
                earlier_table_runtime_snapshots_preserved=preserved,all_initial_text_records_ids_preserved=True,
                all_contexts_within_6000=True,source_preview_pages=len(list((OUT/'source_previews').rglob('*.png'))),
                empty_human_review_forms=len(forms),independent_human_validation=False,
                reusable_cli_export_tokens=packet['context']['reference_tokens'],cmb_date_source_case=case_rows,
                parser_only_diagnostic_macro=analysis['parser_only_diagnostic_macro'],new_generated_answer_quality=None,
                github_updated=False,errors=errors)
    (OUT/'implementation_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)
    return result


if __name__=='__main__':audit()
