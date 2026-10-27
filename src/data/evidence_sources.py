"""Offline source-byte and quote checks, without accepting relevance or facts."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from src.data.annual_reports import sha256_file
from src.data.docx_text import extract_docx_body
from src.data.knowledge_loader import load_document
from src.data.pdf_text_frames import LAYOUT, extract_native_text, parser_policy, record_parser


class SourceVerificationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def local_path(value: str, base: Path) -> Path:
    """Resolve local paths/file URIs; never fetch web URLs or UNC shares."""
    value = str(value)
    if value.startswith(('\\\\', '//')):
        raise SourceVerificationError('nonlocal_source', 'UNC/network shares are not offline source files')
    if not re.match(r'^[A-Za-z]:[\\/]', value):
        parsed = urlsplit(value)
        if parsed.scheme == 'file':
            if parsed.netloc not in ('', 'localhost'):
                raise SourceVerificationError('nonlocal_source', 'Only local file URIs are supported')
            value = unquote(parsed.path)
            if re.match(r'^/[A-Za-z]:/', value):
                value = value[1:]
            if value.startswith(('\\\\', '//')):
                raise SourceVerificationError('nonlocal_source', 'Network file URIs are not offline sources')
        elif parsed.scheme:
            raise SourceVerificationError('nonlocal_source', 'URL requires an explicit local SHA256 source map')
    path = Path(value)
    return (path if path.is_absolute() else base / path).resolve()


class EvidenceSourceVerifier:
    """Verify native PDF/DOCX/legacy TXT spans and declared OCR asset bytes.

    source_map maps expected source hashes to explicit local paths. OCR frames
    are caller-provided registrations keyed by PDF hash, original physical page
    and text hash. OCR-to-image/PDF semantics remain unverified after these checks.
    """
    def __init__(self, bundle_dir: str | Path, *, source_map: dict[str, Path] | None = None,
                 ocr_frames: list[dict] | None = None):
        self.bundle_dir = Path(bundle_dir).resolve()
        self.source_map = {key.lower(): Path(value) for key, value in (source_map or {}).items()}
        self.ocr_frames = {}
        for frame in ocr_frames or []:
            key = (frame['source_pdf_sha256'].lower(), int(frame['pdf_physical_page_1based']),
                   frame['text_sha256'].lower())
            if key in self.ocr_frames:
                raise SourceVerificationError('duplicate_ocr_frame', 'OCR frame registrations must be unique')
            self.ocr_frames[key] = dict(frame)
        self.files: dict[Path, str] = {}
        self.readers = {}
        self.text_frames = {}

    def _bound_file(self, path: Path, expected: str) -> str:
        if not path.is_file():
            raise SourceVerificationError('source_file_missing', f'Local source is missing: {path}')
        if path not in self.files:
            self.files[path] = sha256_file(path)
        if self.files[path] != expected.lower():
            raise SourceVerificationError('source_sha256_mismatch', f'Source SHA256 mismatch: {path}')
        return self.files[path]

    def _pdf(self, path: Path):
        if path not in self.readers:
            from pypdf import PdfReader
            reader = PdfReader(path, strict=False)
            if reader.is_encrypted and not reader.decrypt(''):
                raise SourceVerificationError('encrypted_pdf', 'PDF cannot be read with an empty password')
            self.readers[path] = reader
        return self.readers[path]

    @staticmethod
    def _page(row: dict, count: int) -> int:
        try:
            page = int(row.get('pdf_physical_page_1based', ''))
        except (TypeError, ValueError) as exc:
            raise SourceVerificationError('invalid_physical_page', 'PDF requires an original physical page') from exc
        if not 1 <= page <= count:
            raise SourceVerificationError('physical_page_out_of_bounds', 'Physical page is outside the full original PDF')
        return page

    def verify(self, row: dict, role: str) -> dict:
        if role not in {'annual_report', 'regulation'}:
            raise SourceVerificationError('unsupported_role', 'Unknown evidence source role')
        digest = str(row.get('source_pdf_sha256' if role == 'annual_report' else 'source_document_sha256', '')).lower()
        if not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise SourceVerificationError('invalid_source_sha256', 'Source must have an expected SHA256')
        if digest in self.source_map:
            path = local_path(str(self.source_map[digest]), self.bundle_dir)
            resolution = 'explicit_sha256_source_map'
        else:
            path = local_path(str(row.get('source_uri', '')), self.bundle_dir)
            resolution = 'source_uri_local_path'
        suffix = path.suffix.lower()
        if suffix not in {'.pdf', '.docx', '.txt'} or (role == 'annual_report' and suffix != '.pdf'):
            raise SourceVerificationError('unsupported_source_format', 'Expected an annual PDF or regulation PDF/DOCX/legacy TXT')
        self._bound_file(path, digest)
        page = None
        status = 'native_source_span_verified'
        extra = {}
        if suffix == '.pdf':
            reader = self._pdf(path)
            page = self._page(row, len(reader.pages))
            origin = row.get('text_origin') if role == 'annual_report' else row.get('text_origin') or 'pdf_text_layer'
            expected_text = str(row.get('page_text_sha256' if role == 'annual_report' else 'source_text_sha256', '')).lower()
            if origin in {'ocr_reviewed', 'ocr_unreviewed'}:
                if any(row.get(k) not in (None, '', 'declared_ocr_utf8_frame') for k in ('pdf_text_parser', 'frame_parser')):
                    raise SourceVerificationError('conflicting_pdf_parser', 'OCR evidence cannot declare a native PDF frame parser')
                key = (digest, page, expected_text)
                frame = self.ocr_frames.get(key)
                if frame is None:
                    raise SourceVerificationError('ocr_frame_registration_missing', 'OCR row needs an explicit text/image registration')
                text_file = local_path(str(frame['text_file']), self.bundle_dir)
                image_file = local_path(str(frame['image_file']), self.bundle_dir)
                self._bound_file(text_file, frame['text_sha256'])
                self._bound_file(image_file, frame['image_sha256'])
                if row.get('ocr_text_sha256') and row['ocr_text_sha256'].lower() != frame['text_sha256'].lower():
                    raise SourceVerificationError('ocr_text_hash_conflict', 'Row OCR text hash disagrees with registration')
                if row.get('page_image_sha256') and row['page_image_sha256'].lower() != frame['image_sha256'].lower():
                    raise SourceVerificationError('ocr_image_hash_conflict', 'Row image hash disagrees with registration')
                text = text_file.read_bytes().decode('utf-8')
                status = 'ocr_assets_bound_transcription_unverified'
                extra = {'ocr_text_file': str(text_file), 'ocr_image_file': str(image_file),
                    'ocr_transcription_semantically_verified': False,
                    'image_to_original_pdf_page_visually_verified': False,
                    'ocr_review_status_as_declared': row.get('ocr_visual_review_status')}
            elif origin != 'pdf_text_layer':
                raise SourceVerificationError('unsupported_text_origin', 'PDF text origin must be explicit native text or registered OCR')
            else:
                try:
                    parser = record_parser(row)
                except ValueError as error:
                    raise SourceVerificationError('unsupported_pdf_parser', str(error)) from error
                key = (str(path), page, parser)
                if key not in self.text_frames:
                    self.text_frames[key] = extract_native_text(reader.pages[page - 1], parser)
                text = self.text_frames[key]
            if status.startswith('ocr_'):
                parser = 'declared_ocr_utf8_frame'
            elif parser == LAYOUT:
                extra['native_pdf_text_policy'] = parser_policy(parser)
            extra['source_pdf_page_count'] = len(reader.pages)
        else:
            if row.get('pdf_physical_page_1based'):
                raise SourceVerificationError('non_pdf_has_physical_page', 'DOCX/TXT cannot declare a physical PDF page')
            expected_text = str(row.get('source_text_sha256', '')).lower()
            text_parser = row.get('source_text_parser') or 'legacy-metadata-body-v1'
            if suffix == '.txt' and text_parser not in {'raw-utf8-file-v1', 'legacy-metadata-body-v1'}:
                raise SourceVerificationError('unsupported_text_parser', 'Unknown TXT coordinate frame')
            key = (str(path), None, text_parser)
            if key not in self.text_frames:
                if suffix == '.docx':
                    text, extraction = extract_docx_body(path)
                    self.text_frames[key] = (text, extraction)
                elif text_parser == 'raw-utf8-file-v1':
                    self.text_frames[key] = (path.read_bytes().decode('utf-8'),
                        {'parser': text_parser, 'newline_normalization': 'none'})
                else:
                    document = load_document(path)
                    self.text_frames[key] = (document['text'], {'parser': 'legacy-metadata-body-v1',
                        'newline_normalization': document['source_text_newline_normalization']})
            text, extraction = self.text_frames[key]
            parser = 'ooxml-main-body-v1' if suffix == '.docx' else text_parser
            extra['extraction'] = extraction
        actual_text = hashlib.sha256(text.encode('utf-8')).hexdigest()
        if actual_text != expected_text:
            raise SourceVerificationError('source_text_sha256_mismatch', 'Extracted source frame does not match the recorded text SHA256')
        try:
            start, end = int(row.get('source_char_start', '')), int(row.get('source_char_end', ''))
        except (TypeError, ValueError) as exc:
            raise SourceVerificationError('invalid_character_span', 'Original character coordinates must be integers') from exc
        if not 0 <= start < end <= len(text):
            raise SourceVerificationError('character_span_out_of_bounds', 'Character range is outside the exact source frame')
        if row.get('exact_quote') != text[start:end]:
            raise SourceVerificationError('quote_mismatch', 'Exact quote differs from the original source character range')
        return {'query_id': row.get('query_id'), 'evidence_id': row.get('evidence_id'), 'role': role,
            'status': status, 'source_file': str(path), 'source_sha256': digest, 'source_resolution': resolution,
            'source_format': suffix.lstrip('.'), 'physical_pdf_page_1based': page, 'frame_parser': parser,
            'text_frame_sha256': actual_text, 'source_char_start': start, 'source_char_end': end,
            'accepted_as_gold': False, 'source_identity_or_version_verified': False,
            'semantic_support_or_temporal_applicability_verified': False, **extra}

    def recheck_files(self) -> list[dict]:
        """Detect source/sidecar changes during a cached verification run."""
        result = []
        for path, expected in sorted(self.files.items()):
            if not path.is_file() or sha256_file(path) != expected:
                raise SourceVerificationError('source_changed_during_verification', f'Source changed during verification: {path}')
            result.append({'file': str(path), 'sha256': expected})
        return result
