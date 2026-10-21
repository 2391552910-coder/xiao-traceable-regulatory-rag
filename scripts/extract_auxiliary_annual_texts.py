"""Save review candidates from converted archive texts, keeping them outside PDF fact data."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data.annual_facts import PATTERNS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-dir', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--max-candidates', type=int, default=100)
    args = parser.parse_args()
    if args.max_candidates < 1:
        parser.error('max-candidates must be positive')
    manifest = json.loads((args.archive_dir / 'archive_manifest.json').read_text(encoding='utf-8'))
    args.out_dir.mkdir(parents=True, exist_ok=False)
    documents = []
    for document in manifest['converted_documents']:
        name = next(n for n in document['files'] if n.endswith('.md'))
        raw = (args.archive_dir / name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != document['files'][name]['sha256']:
            raise ValueError(f'Converted source hash mismatch: {name}')
        text = raw.decode('utf-8')
        rows = []
        for match in re.finditer(r'[^。！？\n]+[。！？\n]?', text):
            quote = match.group(0)
            dimensions = [d for d, p in PATTERNS.items() if p.search(quote)]
            if dimensions and len(quote.strip()) >= 15:
                rows.append({'candidate_id': hashlib.sha256(f'{digest}:{match.start()}:{match.end()}'.encode()).hexdigest()[:24],
                             'stock_code': document['stock_code'], 'dimension_candidates': dimensions,
                             'source_kind': 'third_party_converted_markdown',
                             'source_text_sha256': digest, 'source_url': document['files'][name]['url'],
                             'source_text_start': match.start(), 'source_text_end': match.end(),
                             'quote': quote, 'pdf_page': None, 'original_pdf_sha256': None,
                             'review_status': 'needs_original_pdf_and_review', 'semantic_fact_verified': False})
        selected = rows[:args.max_candidates]
        (args.out_dir / f"{document['stock_code']}_candidates.json").write_text(
            json.dumps(selected, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        documents.append({'stock_code': document['stock_code'], 'name': document['name'],
                          'source_text_sha256': digest, 'matched_sentences': len(rows),
                          'saved_candidates': len(selected), 'candidate_cap_reached': len(rows) > len(selected),
                          'front_text_contains_2024_full_report_title': bool(re.search(r'2024\s*年?\s*年度报告(?!摘要)', text[:2500])),
                          'original_pdf_recovered': False})
    report = {'status': 'auxiliary_candidates_need_original_pdf_and_review',
              'source_kind': 'third_party_converted_markdown', 'documents_processed': len(documents),
              'candidate_count': sum(d['saved_candidates'] for d in documents),
              'verified_fact_count': 0, 'formal_data_ready': False, 'original_pdf_count': 0,
              'coordinate_system': 'character offsets in downloaded Markdown; no physical PDF page mapping',
              'selection': f'first {args.max_candidates} keyword-matching sentences per document',
              'documents': documents}
    (args.out_dir / 'auxiliary_extraction.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
