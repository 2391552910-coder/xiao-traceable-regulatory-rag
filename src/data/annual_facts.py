"""Extract review candidates with exact PDF-page text coordinates; never certify facts."""
from __future__ import annotations
import hashlib
import csv
import json
import re
from pathlib import Path

PATTERNS = {
    'D1': re.compile(r'信息披露|披露时间|披露日期|定期报告|年度报告|业绩预告'),
    'D2': re.compile(r'董事会|独立董事|审计委员会|监事会'),
    'D3': re.compile(r'内部控制|内控|合规|审计意见|审计报告|重大缺陷|违规'),
    'D4': re.compile(r'ESG|社会责任|声誉|舆情|行政处罚|罚款|环保处罚', re.I),
}


def validate_candidate(candidate: dict, page_text: str, source_sha256: str) -> None:
    start, end = candidate['page_text_start'], candidate['page_text_end']
    if not 0 <= start < end <= len(page_text):
        raise ValueError('Candidate has invalid page-text coordinates')
    if candidate['source_document_sha256'] != source_sha256:
        raise ValueError('Candidate points to a different PDF')
    if page_text[start:end] != candidate['quote']:
        raise ValueError('Candidate quote does not match its page-text coordinates')
    if hashlib.sha256(candidate['quote'].encode()).hexdigest() != candidate['quote_sha256']:
        raise ValueError('Candidate quote SHA256 does not match')


def candidates_from_page(text: str, page: int, source_sha256: str, company: dict) -> list[dict]:
    candidates = []
    # Preserve extracted text byte-for-byte; offsets address this saved page text.
    for match in re.finditer(r'[^。！？\n]+[。！？\n]?', text):
        quote = match.group(0)
        dimensions = [dimension for dimension, pattern in PATTERNS.items() if pattern.search(quote)]
        if not dimensions or len(quote.strip()) < 15:
            continue
        key = f'{source_sha256}:{page}:{match.start()}:{match.end()}'
        candidate = {'candidate_id': hashlib.sha256(key.encode()).hexdigest()[:24],
                     'stock_code': company['stock_code'], 'company_name': company['name'],
                     'report_year': int(company['year']), 'dimension_candidates': dimensions,
                     'pdf_page': page, 'page_text_start': match.start(), 'page_text_end': match.end(),
                     'quote': quote, 'quote_sha256': hashlib.sha256(quote.encode()).hexdigest(),
                     'source_document_sha256': source_sha256, 'event_date': None,
                     'review_status': 'needs_review', 'semantic_fact_verified': False}
        assert text[candidate['page_text_start']:candidate['page_text_end']] == quote
        candidates.append(candidate)
    return candidates


def extract_candidates(pdf: Path, company: dict, expected_sha256: str, out: Path) -> dict:
    import importlib.metadata
    from pypdf import PdfReader
    from src.data.annual_reports import sha256_file
    if sha256_file(pdf) != expected_sha256:
        raise ValueError('PDF differs from the recorded source SHA256')
    out.mkdir(parents=True, exist_ok=False)
    reader = PdfReader(pdf, strict=False)
    if reader.is_encrypted and not reader.decrypt(''):
        raise ValueError('PDF cannot be read without a password')
    candidates = []
    pages = []
    for page_number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ''
        filename = f'page_{page_number:04d}.txt'
        (out / filename).write_bytes(text.encode('utf-8'))
        rows = candidates_from_page(text, page_number, expected_sha256, company)
        for row in rows:
            row.update(page_text_file=filename, source_url=company.get('source_url', ''),
                       publication_date=company.get('publication_date') or None)
            validate_candidate(row, (out / filename).read_bytes().decode('utf-8'), expected_sha256)
        candidates.extend(rows)
        pages.append({'pdf_page': page_number, 'file': filename, 'characters': len(text),
                      'page_text_sha256': hashlib.sha256(text.encode()).hexdigest()})
    report = {'schema_version': 1, 'stock_code': company['stock_code'], 'report_year': int(company['year']),
              'parser': {'name': 'pypdf', 'version': importlib.metadata.version('pypdf')},
              'source_url': company.get('source_url', ''),
              'publication_date': company.get('publication_date') or None,
              'source_document_sha256': expected_sha256, 'pdf_pages': len(pages),
              'empty_text_pages': sum(not p['characters'] for p in pages), 'pages': pages,
              'candidate_count': len(candidates), 'verified_fact_count': 0, 'formal_data_ready': False,
              'status': 'needs_ocr' if not any(p['characters'] for p in pages) else 'needs_review',
              'coordinate_system': '1-based physical PDF page; offsets in saved pypdf page text',
              'candidate_selection': 'keyword-matching extracted sentences; no numeric or semantic inference',
              'limitations': ['Candidates may be headings, historical comparisons or policy descriptions.',
                              'Missing candidates do not establish absence of a fact.',
                              'D4 external ratings and media coverage require separate sources.']}
    (out / 'candidates.json').write_text(json.dumps(candidates, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (out / 'extraction.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with (out / 'fact_review.csv').open('w', encoding='utf-8-sig', newline='') as f:
        fields = ['candidate_id', 'stock_code', 'report_year', 'dimension_candidates', 'pdf_page',
                  'page_text_start', 'page_text_end', 'quote', 'source_document_sha256',
                  'review_status', 'reviewed_fact', 'event_date', 'review_reason', 'annotator_id']
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for c in candidates:
            row = {k: c.get(k, '') for k in fields}
            row['dimension_candidates'] = ';'.join(c['dimension_candidates'])
            row['event_date'] = ''
            writer.writerow(row)
    return report
