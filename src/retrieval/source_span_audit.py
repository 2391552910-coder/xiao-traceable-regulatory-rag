"""Verify frozen annual-report windows against local PDF bytes and page text.

Coordinates are Unicode code-point offsets in the frozen PDFium extraction,
not PDF geometric coordinates. No labels, search queries or model calls occur.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


WINDOW_ID = re.compile(r"HELD-(\d{6})-(\d{4})-P([1-9]\d*)-S(0|[1-9]\d*)\Z")


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def merge_intervals(intervals):
    """Union half-open source intervals without counting window overlap twice."""
    merged = []
    for start, end in sorted(intervals):
        if type(start) is not int or type(end) is not int or not 0 <= start <= end:
            raise ValueError('Source intervals require nonnegative integer bounds')
        if start == end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def covered_characters(intervals, start, end):
    """Count source characters of [start,end) supplied by verified windows."""
    if type(start) is not int or type(end) is not int or not 0 <= start <= end:
        raise ValueError('Target interval bounds are invalid')
    return sum(max(0, min(right, end) - max(left, start))
               for left, right in merge_intervals(intervals))


class FrozenAnnualSourceVerifier:
    def __init__(self, source_dir):
        self.root = Path(source_dir).resolve()
        self.sources = {}
        self.receipt = []
        self.reparsed_pages = set()
        for row in json.loads((self.root / 'sources.json').read_bytes()):
            name = row['file']
            if Path(name).name != name or '/' in name or '\\' in name:
                raise ValueError('Source file must be a local basename')
            key = (row['stock'], row['year'])
            if key in self.sources:
                raise ValueError('Duplicate company/year source')
            pdf_path = self.root / name
            digest = sha256(pdf_path)
            if digest != row['sha256']:
                raise ValueError('Local PDF bytes differ from frozen source digest')
            pages_path = self.root / 'source_pages_pdfium' / Path(name).with_suffix('.json')
            page_rows = json.loads(pages_path.read_bytes())
            if (len(page_rows) != row['pages'] or
                    [p['page'] for p in page_rows] != list(range(1, row['pages'] + 1)) or
                    not all(isinstance(p['text'], str) for p in page_rows)):
                raise ValueError('Frozen page extraction has invalid page coordinates')
            self.sources[key] = dict(source=row, pdf=pdf_path,
                                     pages={p['page']: p['text'] for p in page_rows})
            self.receipt.append(dict(stock_code=key[0], report_year=key[1],
                                     pdf_file=name, pdf_sha256=digest,
                                     page_text_file=pages_path.name,
                                     page_text_sha256=sha256(pages_path), pages=len(page_rows)))

    def verify_record(self, record, question):
        """Return exact source span; reject scope, identity or text mismatches."""
        meta = record.get('meta', {})
        if meta.get('corpus_type') != 'annual_report':
            raise ValueError('Only annual-report windows have this coordinate policy')
        match = WINDOW_ID.fullmatch(record.get('chunk_id', ''))
        if not match:
            raise ValueError('Unsupported frozen annual window ID')
        stock, year, page, start = match.groups()
        year, page, start = int(year), int(page), int(start)
        if (stock != question['stock_code'] or year != question['report_year'] or
                meta.get('stock_code') != stock or type(meta.get('report_year')) is not int or
                meta['report_year'] != year or
                type(meta.get('physical_pdf_page_1based')) is not int or
                meta['physical_pdf_page_1based'] != page or
                record.get('doc_id') != f'HELD-{stock}-{year}'):
            raise ValueError('Source window coordinates or company/year disagree')
        entry = self.sources.get((stock, year))
        if entry is None:
            raise ValueError('Source company/year is not in the frozen manifest')
        source, pages = entry['source'], entry['pages']
        if (meta.get('source_pdf_sha256') != source['sha256'] or
                record.get('source') != source['url'] or
                meta.get('system_corpus_input') is not True):
            raise ValueError('Window source identity differs from verified manifest')
        if page not in pages or start % 1000 or start >= len(pages[page]):
            raise ValueError('Window page/start is outside the frozen stride policy')
        expected = pages[page][start:start + 1200]
        if not expected.strip() or record.get('text') != expected:
            raise ValueError('Window text is not the exact frozen page slice')
        return dict(chunk_id=record['chunk_id'], source_pdf_sha256=source['sha256'],
                    physical_pdf_page_1based=page, source_start=start,
                    source_end=start + len(expected), coordinate_unit='unicode_code_point',
                    text_sha256=hashlib.sha256(expected.encode('utf-8')).hexdigest())

    def reparse_pages(self, spans):
        """Re-extract used pages from verified PDF bytes, without writing sources."""
        import pypdfium2 as pdfium
        wanted = {(s['source_pdf_sha256'], s['physical_pdf_page_1based']) for s in spans}
        checked = []
        for entry in self.sources.values():
            digest = entry['source']['sha256']
            page_ids = sorted(page for sha, page in wanted if sha == digest)
            if not page_ids:
                continue
            pdf = pdfium.PdfDocument(entry['pdf'])
            try:
                for page_id in page_ids:
                    page = pdf[page_id - 1]
                    try:
                        textpage = page.get_textpage()
                        try:
                            text = textpage.get_text_range().replace('\r\n', '\n').replace('\r', '\n')
                        finally:
                            textpage.close()
                    finally:
                        page.close()
                    if text != entry['pages'][page_id]:
                        raise ValueError('Reparsed PDF page differs from frozen PDFium text')
                    self.reparsed_pages.add((digest, page_id))
                    checked.append(dict(source_pdf_sha256=digest,
                                        physical_pdf_page_1based=page_id,
                                        page_text_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest()))
            finally:
                pdf.close()
        if self.reparsed_pages.intersection(wanted) != wanted:
            raise ValueError('Some supplied spans have no reparsed PDF page')
        return checked
