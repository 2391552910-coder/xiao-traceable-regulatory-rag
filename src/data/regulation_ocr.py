"""Load explicitly hash-bound OCR page assets; never run OCR or accept labels."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from src.data.evidence_sources import local_path


def load_regulation_ocr_sidecar(path: str | Path, expected_sha256: str, *,
                                source_pdf_sha256: str, page_count: int,
                                selected_pages: set[int]) -> tuple[dict[int, dict], dict]:
    """Bind selected OCR frames to the whole original PDF and local assets.

    Paths in the JSON are relative to that JSON. UTF-8 text bytes, CRLF and BOM
    are preserved; supplied review declarations never certify transcription,
    image-to-PDF correspondence, document identity or legal applicability.
    """
    path = local_path(str(path), Path.cwd())
    files: dict[str, dict] = {}

    def bind(p: Path, expected: str, role: str) -> bytes:
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
            raise ValueError(f"OCR {role} requires a valid SHA256")
        raw = p.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected.lower():
            raise ValueError(f"OCR {role} SHA256 mismatch: {p}")
        old = files.get(str(p))
        if old is not None and old['sha256'] != actual:
            raise ValueError(f"OCR source changed while loading: {p}")
        if old is None:
            files[str(p)] = {'path': str(p), 'sha256': actual, 'roles': [role]}
        elif role not in old['roles']:
            old['roles'].append(role)
        return raw

    raw = bind(path, expected_sha256, 'regulation_ocr_manifest')
    manifest = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(manifest, dict) or manifest.get('format') != 'xiao-regulation-ocr-pages' \
            or type(manifest.get('format_version')) is not int or manifest['format_version'] != 1:
        raise ValueError('Unsupported regulation OCR manifest format/version')
    if not isinstance(manifest.get('source_pdf_sha256'), str) or \
            manifest['source_pdf_sha256'].lower() != source_pdf_sha256.lower():
        raise ValueError('OCR manifest source PDF SHA256 mismatch')
    if type(manifest.get('source_pdf_page_count')) is not int or manifest['source_pdf_page_count'] != page_count:
        raise ValueError('OCR manifest whole PDF page count mismatch')
    rows = manifest.get('pages')
    if not isinstance(rows, list) or not rows:
        raise ValueError('OCR manifest requires a nonempty pages list')
    seen = set()
    pages = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('OCR page registration must be an object')
        page = row.get('physical_pdf_page_1based')
        if type(page) is not int or not 1 <= page <= page_count:
            raise ValueError('OCR physical page outside original PDF')
        if page in seen:
            raise ValueError('Duplicate OCR original physical page')
        seen.add(page)
        if not isinstance(row.get('engine'), str) or not row['engine'].strip():
            raise ValueError('OCR page requires its recognition engine')
        if row.get('review_status') not in {'unreviewed', 'declared_reviewed'}:
            raise ValueError('OCR review_status must remain an explicit declaration')
        if type(row.get('rotation_degrees')) is not int or row['rotation_degrees'] not in {0,90,180,270}:
            raise ValueError('OCR rotation_degrees must be 0, 90, 180 or 270')
        if type(row.get('confidence_available')) is not bool:
            raise ValueError('OCR confidence_available must be a boolean')
        for key in ('text_file', 'image_file'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f'OCR page requires {key}')
        for key in ('text_sha256', 'image_sha256'):
            if not isinstance(row.get(key), str) or not re.fullmatch(r'[0-9a-fA-F]{64}', row[key]):
                raise ValueError(f'OCR page requires {key}')
        if page not in selected_pages:
            continue
        text_file = local_path(row['text_file'], path.parent)
        image_file = local_path(row['image_file'], path.parent)
        text_raw = bind(text_file, row['text_sha256'], 'regulation_ocr_text')
        bind(image_file, row['image_sha256'], 'regulation_ocr_page_image')
        text = text_raw.decode('utf-8')
        if not any(c.isalpha() for c in text):
            raise ValueError(f'OCR page has no linguistic text: {page}')
        pages[page] = {
            'text': text, 'text_file': str(text_file), 'image_file': str(image_file),
            'text_sha256': row['text_sha256'].lower(), 'image_sha256': row['image_sha256'].lower(),
            'engine': row['engine'], 'review_status': row['review_status'],
            'rotation_degrees': row['rotation_degrees'], 'confidence_available': row['confidence_available'],
            'source_pdf_sha256': source_pdf_sha256.lower(),
            'pdf_physical_page_1based': page,
        }
    for item in files.values():
        if hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError(f"OCR source changed during loading: {item['path']}")
    return pages, {
        'manifest_file': str(path), 'manifest_sha256': expected_sha256.lower(),
        'registered_page_count': len(rows), 'selected_ocr_pages': sorted(pages),
        'unselected_registered_pages': sorted(seen - selected_pages),
        'source_files': [files[key] for key in sorted(files)],
        'recognition_run_by_loader': False, 'transcription_accuracy_verified': False,
        'image_to_original_pdf_page_verified': False, 'accepted_as_gold': False,
    }
