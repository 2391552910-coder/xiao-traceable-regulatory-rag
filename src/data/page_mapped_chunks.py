"""Optional PDF segmentation over adjacent pages with exact per-page mappings."""
import hashlib
import re
from collections import OrderedDict

from src.data.clause_splitter import Chunk
from src.data.structural_splitter import split_by_structure, STRUCTURAL_HEADING_PATTERN
from src.data.pdf_text_frames import LAYOUT, metadata_parser

JOINER = '\n\f\n'
STRATEGIES = ('page_window', 'mapped_structure', 'mapped_window')
PAGE_KEYS = {'physical_pdf_page_1based', 'page_text_char_start', 'page_text_char_end',
             'page_text_sha256', 'page_text_origin', 'page_text_parser', 'native_pdf_text_policy'}


def mapped_segments(chunk):
    """Reject unaccounted text, nested maps or mismatched source identities."""
    meta = chunk.meta
    rows = meta.get('mapped_page_segments')
    if not isinstance(rows, list) or not rows or meta.get('mapped_joiner') != JOINER:
        raise ValueError('Mapped PDF chunk lacks explicit per-page segments/joiner')
    if meta.get('corpus_type') != 'regulation' or meta.get('source_format') != 'pdf' or PAGE_KEYS & set(meta):
        raise ValueError('Mapped PDF chunk cannot claim one physical page/text frame')
    previous_end, previous_page = 0, None
    for i, row in enumerate(rows):
        start, end, source = row.get('chunk_char_start'), row.get('chunk_char_end'), row.get('meta')
        if not isinstance(source, dict) or 'mapped_page_segments' in source:
            raise ValueError('Nested or missing mapped source metadata')
        metadata_parser(source)
        page = source.get('physical_pdf_page_1based')
        if type(page) is not int or page < 1 or (previous_page is not None and page != previous_page + 1):
            raise ValueError('Mapped chunks may join only consecutive original physical pages')
        if any(type(v) is not int for v in (start, end)) or not 0 <= start < end <= len(chunk.text):
            raise ValueError('Mapped chunk-local offsets are invalid')
        if (i == 0 and start != 0) or (i and chunk.text[previous_end:start] != JOINER):
            raise ValueError('Mapped chunk has unaccounted or changed join text')
        for key in ('corpus_type', 'source_format', 'source_pdf_sha256', 'source_document_sha256', 'version_id'):
            if source.get(key) != meta.get(key): raise ValueError('Mapped pages disagree on source/version/role')
        quote = chunk.text[start:end]
        if hashlib.sha256(quote.encode('utf-8')).hexdigest() != row.get('text_sha256'):
            raise ValueError('Mapped page fragment text hash differs')
        coordinates = (source.get('page_text_char_start'), source.get('page_text_char_end'))
        if any(type(v) is not int for v in coordinates) or not 0 <= coordinates[0] < coordinates[1] or coordinates[1] - coordinates[0] != len(quote):
            raise ValueError('Mapped PDF character ranges differ from fragment length')
        previous_end, previous_page = end, page
    if previous_end != len(chunk.text): raise ValueError('Mapped chunk has unaccounted trailing text')
    return rows


def source_metas(chunk):
    meta = chunk.meta or {}
    return [r['meta'] for r in mapped_segments(chunk)] if 'mapped_page_segments' in meta else [meta]


def split_mapped_pages(page_chunks, *, strategy='mapped_structure', size=1200, overlap=160):
    if strategy not in STRATEGIES[1:]: raise ValueError('Select mapped_structure or mapped_window')
    if any(type(v) is not int for v in (size, overlap)) or size < 1 or not 0 <= overlap < size:
        raise ValueError('Mapped window size/overlap are invalid')
    grouped = OrderedDict()
    for chunk in page_chunks:
        if chunk.meta.get('source_format') != 'pdf' or chunk.meta.get('corpus_type') != 'regulation':
            raise ValueError('Page-mapped strategy currently requires original regulation PDFs')
        grouped.setdefault(chunk.doc_id, []).append(chunk)
    result = []
    for doc_id, pages in grouped.items():
        pages.sort(key=lambda c: c.meta['physical_pdf_page_1based'])
        numbers = [c.meta['physical_pdf_page_1based'] for c in pages]
        if len(numbers) != len(set(numbers)): raise ValueError('A full-page frame is required once per physical page')
        runs = []
        for page in pages:
            if not runs or page.meta['physical_pdf_page_1based'] != runs[-1][-1].meta['physical_pdf_page_1based'] + 1:
                runs.append([])
            runs[-1].append(page)
        for run_number, run in enumerate(runs, 1):
            spans, texts, offset = [], [], 0
            for page in run:
                spans.append((offset, offset + len(page.text), page)); texts.append(page.text)
                offset += len(page.text) + len(JOINER)
            text = JOINER.join(texts)
            starts = {}
            if strategy == 'mapped_structure':
                # Keep an isolated page-label prefix with its own page's first
                # heading;do not attach only that label to the previous clause.
                for heading in STRUCTURAL_HEADING_PATTERN.finditer(text):
                    for left, right, page in spans:
                        if left <= heading.start() < right and re.fullmatch(
                                r'\s*[-—–−－]\s*[0-9]+\s*[-—–−－]\s*', text[left:heading.start()]):
                            starts[heading.start()] = left
                pieces = split_by_structure(doc_id, run[0].doc_title, 'regulation', run[0].source,
                    text, size=size, overlap=overlap, boundary_starts=starts)
            else:
                from src.data.document_corpora import _split_page
                pieces = [Chunk(str(i), doc_id, run[0].doc_title, 'regulation', run[0].source, None,
                    excerpt, meta={'source_start': a, 'source_end': b}) for i, (a, b, excerpt) in
                    enumerate(_split_page(text, size, overlap), 1)]
            for ordinal, piece in enumerate(pieces, 1):
                a, b = piece.meta['source_start'], piece.meta['source_end']
                mapped = []
                for left, right, page in spans:
                    start, end = max(a, left), min(b, right)
                    if start >= end: continue
                    original_start = page.meta['page_text_char_start'] + start - left
                    source = {**page.meta, 'page_text_char_start': original_start,
                        'page_text_char_end': original_start + end - start}
                    mapped.append({'chunk_char_start': start - a, 'chunk_char_end': end - a,
                        'text_sha256': hashlib.sha256(text[start:end].encode('utf-8')).hexdigest(), 'meta': source})
                common = {k: v for k, v in run[0].meta.items() if k not in PAGE_KEYS and not k.startswith('ocr_')}
                head = {k: v for k, v in piece.meta.items() if k not in {'source_start', 'source_end', 'raw_end'}}
                parser_tag = 'LAYOUT-' if any(metadata_parser(p.meta) == LAYOUT for p in run) else ''
                candidate = Chunk(f'{doc_id}-MAP-{parser_tag}{strategy}-G{run_number:03d}-C{ordinal:04d}', doc_id,
                    piece.doc_title, 'regulation', piece.source, piece.clause_no, piece.text,
                    dimension=piece.dimension, meta={**common, **head, 'mapped_page_segments': mapped,
                        'mapped_joiner': JOINER, 'mapped_strategy': strategy,
                        'virtual_text_start': a, 'virtual_text_end': b,
                        'page_headers_or_footers_removed': False,
                        'page_label_prefix_boundary_grouping': bool(starts),
                        'structural_identity_status': 'heading_candidate_not_independently_reviewed'})
                mapped_segments(candidate)
                result.append(candidate)
    return result


def load_mapped_regulation_file_chunks(manifest_path, *, strategy='mapped_structure', chunk_chars=1200,
                                     overlap_chars=160, limit=None):
    from src.data.document_corpora import load_regulation_file_chunks
    pages, report = load_regulation_file_chunks(manifest_path, chunk_chars=10**9, overlap_chars=0, limit=limit)
    chunks = split_mapped_pages(pages, strategy=strategy, size=chunk_chars, overlap=overlap_chars)
    counts = {d['doc_id']: sum(c.doc_id == d['doc_id'] for c in chunks) for d in report['documents']}
    report = {**report, 'chunk_count': len(chunks), 'file_chunk_strategy': strategy,
        'whole_page_frames_supplied': len(pages),
        'multi_page_chunks': sum(len(c.meta['mapped_page_segments']) > 1 for c in chunks),
        'page_headers_or_footers_removed': False,
        'coverage_scope': 'supplied searchable page text;not skipped/empty/unselected pages',
        'documents': [{**d, 'base_page_frame_count': d['chunk_count'], 'chunk_count': counts[d['doc_id']]} for d in report['documents']]}
    return chunks, report
