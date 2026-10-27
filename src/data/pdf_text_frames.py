"""Explicit native PDF coordinate frames; never fall back between parsers."""
from __future__ import annotations

PLAIN = 'pypdf-default-plain'
LAYOUT = 'pypdf-layout-v1'
NATIVE_PDF_PARSERS = frozenset({PLAIN, LAYOUT})
OCR_ORIGINS = frozenset({'ocr_reviewed', 'ocr_unreviewed', 'ocr_sidecar_unreviewed'})
_LAYOUT_KWARGS = {
    'extraction_mode': 'layout', 'layout_mode_space_vertically': True,
    'layout_mode_scale_weight': 1.25, 'layout_mode_strip_rotated': True,
    'layout_mode_font_height_weight': 1,
}


def parser_for_mode(mode=None):
    if mode in (None, '', 'plain'):
        return PLAIN
    if mode == 'layout':
        return LAYOUT
    raise ValueError('pdf_text_mode must be plain or layout')


def canonical_parser(value=None):
    if value in (None, '', 'pypdf', PLAIN):
        return PLAIN
    if value == LAYOUT:
        return LAYOUT
    raise ValueError('Unsupported native PDF coordinate-frame parser')


def parser_policy(parser):
    parser = canonical_parser(parser)
    return {'parser': parser, 'extract_text_kwargs': dict(_LAYOUT_KWARGS) if parser == LAYOUT else {},
            'coordinate_unit': 'Unicode code points;zero-based;right endpoint excluded',
            'covers': 'selected searchable text layer;not all graphics or rotated/scanned content'}


def extract_native_text(page, parser=PLAIN):
    parser = canonical_parser(parser)
    # Preserve the historical no-keyword call for existing plain frames.
    return (page.extract_text(**_LAYOUT_KWARGS) if parser == LAYOUT else page.extract_text()) or ''


def metadata_parser(meta):
    origin = meta.get('page_text_origin', meta.get('text_origin', 'pdf_text_layer')) or 'pdf_text_layer'
    if origin in OCR_ORIGINS:
        return None
    if origin != 'pdf_text_layer':
        raise ValueError('Unsupported PDF text origin')
    parser = canonical_parser(meta.get('page_text_parser'))
    declared = meta.get('native_pdf_text_policy')
    if parser == LAYOUT and declared != parser_policy(LAYOUT):
        raise ValueError('Layout PDF frame policy is missing or differs')
    if parser == PLAIN and declared is not None and declared != parser_policy(PLAIN):
        raise ValueError('Plain PDF frame policy differs')
    return parser


def record_parser(record):
    values = [canonical_parser(record[key]) for key in ('pdf_text_parser', 'page_text_parser', 'frame_parser')
              if record.get(key) not in (None, '')]
    if len(set(values)) > 1:
        raise ValueError('Conflicting declared PDF frame parsers')
    parser = values[0] if values else PLAIN
    if parser == LAYOUT and record.get('native_pdf_text_policy') != parser_policy(LAYOUT):
        raise ValueError('Layout PDF frame policy is missing or differs')
    if record.get('native_pdf_text_policy') is not None and record['native_pdf_text_policy'] != parser_policy(parser):
        raise ValueError('Declared PDF frame policy differs')
    return parser
