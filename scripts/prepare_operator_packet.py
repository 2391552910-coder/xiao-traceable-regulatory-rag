"""Reuse frozen materials; add missing-source diagnostics and independent screening forms."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.prepare_corpus_v2 import read_csv, write_json, write_jsonl


def write_csv(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def build(out):
    out.mkdir(parents=True,exist_ok=False)
    required=ROOT/'data/provenance/recovery_20261013/sources_required.json'
    historical=ROOT/'data/companies/download_report.csv'
    samples=ROOT/'data/companies/sampling_frame.csv'
    requested={r['stock_code']:r for r in json.loads(required.read_text(encoding='utf-8'))}
    old={r['stock_code']:r for r in read_csv(historical)}
    auxiliary=json.loads((ROOT/'results/runs/annual_report_recovery_20261013/alternative_sources.json').read_text(encoding='utf-8'))
    aux={r['stock_code']:next(iter(r['files'].values()))['url'] for r in auxiliary['converted_documents']}
    rows=[]
    for c in read_csv(samples):
        r=requested[c['stock_code']]
        rows.append({'stock_code':c['stock_code'],'company_name':c['name'],'report_year':r['year'],
                     'official_report_url_as_recorded':r['source_url'] or '',
                     'official_url_status':'recorded_not_reverified' if r['source_url'] else 'not_recorded_need_source',
                     'historical_expected_file':old[c['stock_code']]['file'],
                     'suggested_local_filename':f"{c['stock_code']}_{c['name']}_{r['year']}.pdf",
                     'identity_requirements':f"Full annual report, not summary; front matter contains {c['name']}, {c['stock_code'].split('.')[0]}, {r['year']}; one selected version",
                     'status':'missing_original_pdf','required_action':'Provide original PDF and actual publication URL/version; no inferred dates',
                     'auxiliary_reference_not_official_pdf':aux.get(c['stock_code'],''),
                     'provenance_input':'data/provenance/recovery_20261013/sources_required.json'})
    write_csv(out/'company_missing_materials.csv',rows)
    packet=ROOT/'data/processed/label_review_v2_20261013'
    write_json(out/'development_attestation_template.json',{
        'reviewer_a':'','reviewer_b':'','coordinator':'','declared_at':'',
        'independent_work_confirmed':False,'provenance_checked':False,
        'packet_manifest_sha256':hashlib.sha256((packet/'manifest.json').read_bytes()).hexdigest()})
    candidates=ROOT/'data/heldout/family_review_final_20261013/reserved_retrieval_candidates.jsonl'
    reserved=[json.loads(s) for s in candidates.read_text(encoding='utf-8').splitlines()]
    forms=[{'query_id':r['query_id'],'dimension':r['dimension'],'query':r['query'],
            'family_overlap':'','development_query_ids':'','source_verified':'','temporal_scope_verified':'',
            'evidence_ids':'','reviewer':'','reviewed_at':'','rationale':''} for r in reserved]
    write_csv(out/'test_screening_A.csv',forms);write_csv(out/'test_screening_B.csv',list(reversed(forms)))
    follow=json.loads((ROOT/'docs/review_20261013/heldout_source_followup.json').read_text(encoding='utf-8'))
    write_json(out/'test_source_context.json',follow)
    sources=[required,historical,samples,candidates,packet/'manifest.json',
             ROOT/'results/runs/annual_report_recovery_20261013/alternative_sources.json',
             ROOT/'docs/review_20261013/heldout_source_followup.json']
    manifest={'scope':'operator_handoff_not_new_gold','companies':len(rows),'missing_original_pdfs':len(rows),
              'official_report_urls_available':sum(bool(r['official_report_url_as_recorded']) for r in rows),
              'reserved_test_candidates':len(reserved),'formal_test_queries':0,'human_labels':0,
              'reuse_development_forms':'data/processed/label_review_v2_20261013/blind_review_{A,B}.csv',
              'reuse_development_registry':'data/heldout/family_review_final_20261013/development_registry.json',
              'inputs_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              'artifacts_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}}
    write_json(out/'manifest.json',manifest)
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out-dir',type=Path,required=True)
    print(json.dumps(build(p.parse_args().out_dir),ensure_ascii=False,indent=2))
