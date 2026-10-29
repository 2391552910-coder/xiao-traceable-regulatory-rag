"""Extract source-bound tables from a local annual report, entirely offline."""
from pathlib import Path
from collections import Counter
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts._table_runtime import ensure_local_pdf_libraries
from src.data.annual_tables import extract_document, extract_pdfium_pages, file_sha256
from src.retrieval.annual_table_index import build_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--stock', required=True)
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--company', required=True)
    parser.add_argument('--source-url', default='')
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--all-pages', action='store_true', help='Parse every page instead of governance keyword pages and their neighbors')
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'\d{6}', args.stock) or not 1900 <= args.year <= 2100 or not args.company.strip():
        raise ValueError('Supply a six-digit stock code, report year and company name')
    if not args.pdf.is_file():
        raise FileNotFoundError(args.pdf)
    if args.out_dir.exists():
        raise FileExistsError('Choose a new extraction output directory')
    ensure_local_pdf_libraries()
    pages = extract_pdfium_pages(args.pdf)
    source = dict(stock=args.stock, year=args.year, company=args.company, file=args.pdf.name,
                  url=args.source_url or str(args.pdf.resolve()), sha256=file_sha256(args.pdf), pages=len(pages),
                  company_year_identity='caller_supplied_metadata_not_independently_verified')
    document = extract_document(args.pdf, source, pages, all_pages=args.all_pages)
    args.out_dir.mkdir(parents=True)
    (args.out_dir/'document.json').write_text(json.dumps(document, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    chunks, review = build_index([document], args.out_dir/'table_index.sqlite')
    (args.out_dir/'review_queue.json').write_text(json.dumps(review, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    page_counts = Counter(page['status'] for page in document['parsed_pages'])
    print(json.dumps(dict(status='completed_offline', tables=len(document['tables']),
                         table_chains=len(document['logical_tables']), indexed_rows=len(chunks),
                         parser_version=document['parser_version'], total_pdf_pages=len(pages),
                         inspected_pages=len(document['parsed_pages']),
                         page_selection_scope=document['selection']['scope'],
                         page_status_counts=dict(page_counts),
                         undecoded_pages=[page['page'] for page in document['parsed_pages']
                                          if page['status'] == 'text_layer_contains_undecoded_glyphs'],
                         text_layer_check_limit='Only inspected pages and known undecoded markers; no accuracy guarantee.',
                         model_calls=0, output=str(args.out_dir.resolve())), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
