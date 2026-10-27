"""Bind actual retrieved chunks to exact local source frames; accept no labels."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, replace
from pathlib import Path

from src.data.annual_reports import sha256_file
from src.data.docx_text import extract_docx_body
from src.data.evidence_sources import EvidenceSourceVerifier, local_path
from src.data.knowledge_loader import load_document
from src.metrics.span_retrieval import verify_location
from src.data.page_mapped_chunks import mapped_segments, source_metas
from src.data.pdf_text_frames import LAYOUT, extract_native_text, metadata_parser, parser_policy

OCR_ORIGINS = {'ocr_unreviewed', 'ocr_reviewed', 'ocr_sidecar_unreviewed'}


class RetrievedSourceBinder:
    def __init__(self, source_inventory, chunks, project_root):
        self.root = Path(project_root).resolve()
        self.inventory = {}
        self.path_hashes = {}
        for row in source_inventory:
            digest = row['sha256']
            if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError('Source inventory needs lowercase SHA256 digests')
            value = row['path']
            if value.startswith('$PROJECT_ROOT/'):
                value = str(self.root / value[len('$PROJECT_ROOT/'):])
            path = local_path(value, self.root)
            if path in self.path_hashes and self.path_hashes[path] != digest:
                raise ValueError('Source inventory declares conflicting hashes for a file')
            self.path_hashes[path] = digest
            self.inventory.setdefault(digest, set()).add(path)
        self.readers, self.frames, self.ocr = {}, {}, {}
        for m in (m for chunk in chunks for m in source_metas(chunk)):
            if m.get('page_text_origin', m.get('text_origin')) not in OCR_ORIGINS:
                continue
            digest = m.get('source_pdf_sha256') or m.get('source_document_sha256')
            page, text_sha, image_sha = m['physical_pdf_page_1based'], m['page_text_sha256'], m['ocr_image_sha256']
            if m.get('ocr_text_sha256') != text_sha:
                raise ValueError('Indexed OCR frame and OCR asset hash differ')
            frame = {'source_pdf_sha256': digest, 'pdf_physical_page_1based': page,
                     'text_sha256': text_sha, 'image_sha256': image_sha,
                     'text_file': str(self._file(text_sha, {'.txt'})),
                     'image_file': str(self._file(image_sha, {'.png', '.jpg', '.jpeg'}))}
            key = digest, page, text_sha
            if key in self.ocr and self.ocr[key] != frame:
                raise ValueError('Conflicting OCR assets for one indexed coordinate frame')
            self.ocr[key] = frame
        source_map = {digest: self._file(digest, {'.pdf', '.docx', '.txt'})
                      for digest, paths in self.inventory.items()
                      if any(p.suffix.lower() in {'.pdf', '.docx', '.txt'} for p in paths)}
        self.verifier = EvidenceSourceVerifier(self.root, source_map=source_map, ocr_frames=list(self.ocr.values()))

    def _file(self, digest, suffixes):
        matches = sorted(p for p in self.inventory.get(digest, ()) if p.suffix.lower() in suffixes)
        if not matches:
            raise ValueError('Required source or OCR asset is not in the hash-bound index inventory')
        return matches[0]

    def bind(self, chunk, query_id, evidence_id):
        if 'mapped_page_segments' in chunk.meta:
            parts = mapped_segments(chunk)
            bound = [self.bind(replace(chunk, text=chunk.text[r['chunk_char_start']:r['chunk_char_end']],
                meta=r['meta']), query_id, evidence_id) for r in parts]
            if any(r['quote_alignment'] != 'exact' for r in bound):
                raise ValueError('Mapped PDF fragments must match their original frames exactly')
            return {'chunk_id': chunk.chunk_id, 'hit_id': chunk.chunk_id,
                'source_spans': [s for r in bound for s in r['source_spans']],
                'locations': [s for r in bound for s in r['locations']],
                'retrieved_text': chunk.text,
                'retrieved_text_sha256': hashlib.sha256(chunk.text.encode('utf-8')).hexdigest(),
                'quote_alignment': 'page_mapped_exact_segments',
                'frame_binding': 'per_page_hash_bound_frames_with_explicit_non_source_joiner',
                'source_identity_or_version_verified': False, 'semantic_support_verified': False}
        m, role = chunk.meta, chunk.meta.get('corpus_type')
        if role not in {'annual_report', 'regulation'} or str(m.get('system_corpus_input', '')).lower() == 'false':
            raise ValueError('Retrieved source is not an allowed system input role')
        digest = m.get('source_pdf_sha256') if role == 'annual_report' else m.get('source_document_sha256')
        path = self._file(digest, {'.pdf'} if role == 'annual_report' else {'.pdf', '.docx', '.txt'})
        if sha256_file(path) != digest:
            raise ValueError('Original retrieved source SHA256 changed')
        pdf = path.suffix.lower() == '.pdf'
        page = m.get('physical_pdf_page_1based') if pdf else None
        origin = (m.get('page_text_origin', m.get('text_origin', 'pdf_text_layer')) or 'pdf_text_layer') if pdf else m.get('source_text_parser', 'source_text_body')
        native_parser = metadata_parser(m) if pdf and origin not in OCR_ORIGINS else None
        key = digest, page, origin, native_parser
        if key not in self.frames:
            if pdf:
                if isinstance(page, bool) or not isinstance(page, int) or page < 1:
                    raise ValueError('Retrieved PDF needs an original physical page')
                if digest not in self.readers:
                    from pypdf import PdfReader
                    self.readers[digest] = PdfReader(path, strict=False)
                reader = self.readers[digest]
                if reader.is_encrypted and not reader.decrypt(''):
                    raise ValueError('Retrieved PDF cannot be opened with an empty password')
                if page > len(reader.pages):
                    raise ValueError('Retrieved PDF physical page is out of range')
                if origin in OCR_ORIGINS:
                    frame = self.ocr.get((digest, page, m.get('page_text_sha256')))
                    if frame is None:
                        raise ValueError('Retrieved OCR frame lacks a matching registration')
                    text_path = Path(frame['text_file'])
                    if sha256_file(text_path) != frame['text_sha256']:
                        raise ValueError('Retrieved OCR text asset changed')
                    text = text_path.read_bytes().decode('utf-8')
                elif origin == 'pdf_text_layer':
                    text = extract_native_text(reader.pages[page - 1], native_parser)
                else:
                    raise ValueError('Unsupported indexed PDF text origin')
            elif path.suffix.lower() == '.docx':
                text, _ = extract_docx_body(path)
            elif origin == 'raw-utf8-file-v1':
                text = path.read_bytes().decode('utf-8')
            else:
                text = load_document(path)['text']
            self.frames[key] = text
        text = self.frames[key]
        text_sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
        expected_text = m.get('page_text_sha256' if pdf else 'source_text_sha256')
        if (pdf or path.suffix.lower() == '.docx') and not expected_text:
            raise ValueError('Indexed PDF/DOCX must retain its expected source text frame SHA256')
        if expected_text and text_sha != expected_text:
            raise ValueError('Indexed source text frame differs from the current exact parser frame')
        coord = ('page_text_char_start', 'page_text_char_end') if pdf else (
            ('source_text_char_start', 'source_text_char_end') if 'source_text_char_start' in m else ('source_start', 'source_end'))
        start, end = (m.get(name) for name in coord)
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (start, end)) or not 0 <= start < end <= len(text):
            raise ValueError('Indexed source coordinates are invalid')
        quote = text[start:end]
        if not isinstance(chunk.text, str) or not chunk.text.strip() or ''.join(quote.split()) != ''.join(chunk.text.split()):
            raise ValueError('Retrieved chunk differs from its exact source span beyond whitespace')
        row = {'query_id': query_id, 'evidence_id': evidence_id, 'role': role, 'source_uri': str(path),
               'source_char_start': start, 'source_char_end': end, 'exact_quote': quote,
               'pdf_physical_page_1based': page, 'source_text_sha256': text_sha,
               'indexed_text_origin': origin,
               'text_origin': ('ocr_unreviewed' if origin == 'ocr_sidecar_unreviewed' else origin) if pdf else None,
               'source_text_parser': m.get('source_text_parser') if not pdf else None,
               'ocr_visual_review_status': m.get('ocr_visual_review_status'),
               'source_pdf_sha256': digest if role == 'annual_report' else None,
               'source_document_sha256': digest if role == 'regulation' else None,
               'page_text_sha256': text_sha if pdf else None,
               'ocr_text_sha256': m.get('ocr_text_sha256'), 'page_image_sha256': m.get('ocr_image_sha256'),
               'relevance_grade_gold': None, 'temporal_applicability_gold': None}
        if native_parser == LAYOUT:
            row.update(pdf_text_parser=LAYOUT, native_pdf_text_policy=parser_policy(LAYOUT))
        location = verify_location(row, self.verifier)
        return {'chunk_id': chunk.chunk_id, 'hit_id': chunk.chunk_id, 'source_spans': [row],
                'locations': [asdict(location)], 'retrieved_text': chunk.text,
                'retrieved_text_sha256': hashlib.sha256(chunk.text.encode('utf-8')).hexdigest(),
                'quote_alignment': 'exact' if quote == chunk.text else 'whitespace_only_difference_originals_retained',
                'indexed_text_frame_sha256': expected_text,
                'frame_binding': 'matched_indexed_frame' if expected_text else 'derived_from_hash_bound_legacy_body',
                'source_identity_or_version_verified': False, 'semantic_support_verified': False}

    def recheck_files(self):
        return self.verifier.recheck_files()
