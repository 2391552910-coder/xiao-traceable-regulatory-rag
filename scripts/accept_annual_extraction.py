"""Independently verify PDF -> saved page -> quote provenance; never certify factual meaning."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data.annual_reports import inspect_pdf
from src.data.annual_facts import validate_candidate


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inside(root, name):
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()): raise ValueError('page_path_outside_extraction')
    return path


def verify(pdf, company, extraction):
    from pypdf import PdfReader
    pdf, extraction = Path(pdf), Path(extraction)
    report=json.loads((extraction/'extraction.json').read_text(encoding='utf-8'))
    if sha(pdf)!=report['source_document_sha256']: raise ValueError('source_pdf_hash_mismatch')
    identity=inspect_pdf(pdf,company,int(company['year']))
    if not identity['identity']['verified']: raise ValueError('company_year_or_full_report_identity_failed')
    if report['stock_code']!=company['stock_code'] or int(report['report_year'])!=int(company['year']):
        raise ValueError('extraction_company_year_mismatch')
    reader=PdfReader(pdf,strict=False)
    if reader.is_encrypted and not reader.decrypt(''):raise ValueError('encrypted_pdf')
    if len(reader.pages)!=report['pdf_pages'] or len(report['pages'])!=report['pdf_pages']:
        raise ValueError('page_count_mismatch')
    pages={}
    for i, row in enumerate(report['pages'],1):
        if row['pdf_page']!=i:raise ValueError('nonsequential_page_numbers')
        path=inside(extraction,row['file'])
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['page_text_sha256']:raise ValueError('page_text_hash_mismatch')
        text=raw.decode('utf-8')
        if text!=(reader.pages[i-1].extract_text() or ''):raise ValueError('page_text_not_reproducible_from_pdf')
        pages[i]=(row['file'],text)
    candidates=json.loads((extraction/'candidates.json').read_text(encoding='utf-8'))
    if len(candidates)!=report['candidate_count']:raise ValueError('candidate_count_mismatch')
    seen=set()
    for c in candidates:
        if c['candidate_id'] in seen:raise ValueError('duplicate_candidate_id')
        seen.add(c['candidate_id'])
        if c['stock_code']!=company['stock_code'] or int(c['report_year'])!=int(company['year']):
            raise ValueError('candidate_company_year_mismatch')
        if c['pdf_page'] not in pages:raise ValueError('candidate_page_out_of_range')
        filename,text=pages[c['pdf_page']]
        if c['page_text_file']!=filename:raise ValueError('candidate_page_file_mismatch')
        validate_candidate(c,text,report['source_document_sha256'])
        if c.get('semantic_fact_verified') is not False:raise ValueError('automatic_candidate_must_not_claim_verified_fact')
    return {'stock_code':company['stock_code'], 'year':int(company['year']),
            'status':'traceability_passed_semantics_pending', 'pages':len(pages), 'candidates':len(candidates),
            'source_pdf_sha256':sha(pdf), 'extraction_json_sha256':sha(extraction/'extraction.json'),
            'candidates_json_sha256':sha(extraction/'candidates.json'), 'verified_facts':0,
            'ocr_needed':not any(text for _,text in pages.values()),
            'limitations':['Machine identity check requires visual confirmation; extracted table semantics are not certified.',
                           'Use the same parser version for byte-exact page reproduction; a parser change requires a new version.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pdf',required=True,type=Path);p.add_argument('--extraction-dir',required=True,type=Path)
    p.add_argument('--code',required=True);p.add_argument('--name',required=True);p.add_argument('--year',type=int,default=2024)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    try:
        result=verify(args.pdf,{'stock_code':args.code,'name':args.name,'year':args.year},args.extraction_dir)
        ok=True
    except Exception as error:
        result={'status':'failed_traceability_check','error':f'{type(error).__name__}: {error}',
                'verified_facts':0,'action':'Preserve inputs, correct the identified file or metadata, rerun extraction into a new directory.'};ok=False
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if ok else 2


if __name__=='__main__':sys.exit(main())
