import hashlib
import json
from copy import deepcopy

import pytest

from src.retrieval.source_span_audit import (
    FrozenAnnualSourceVerifier, covered_characters, merge_intervals,
)


@pytest.fixture
def bundle(tmp_path):
    pdf = tmp_path / 'report.pdf'
    pdf.write_bytes(b'local PDF fixture; not parsed in unit tests')
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    text = '甲' * 1000 + '乙' * 300
    row = dict(stock='000001', year=2024, file=pdf.name, sha256=digest,
               url='https://example.invalid/report.pdf', pages=1)
    (tmp_path / 'sources.json').write_text(json.dumps([row]), encoding='utf-8')
    pages = tmp_path / 'source_pages_pdfium'
    pages.mkdir()
    (pages / 'report.json').write_text(json.dumps([dict(page=1, text=text)]), encoding='utf-8')
    record = dict(chunk_id='HELD-000001-2024-P1-S1000', doc_id='HELD-000001-2024',
                  source=row['url'], text=text[1000:2200], meta=dict(
                      corpus_type='annual_report', stock_code='000001', report_year=2024,
                      source_pdf_sha256=digest, physical_pdf_page_1based=1,
                      system_corpus_input=True))
    return tmp_path, record, dict(stock_code='000001', report_year=2024)


def test_exact_codepoint_span_and_no_input_mutation(bundle):
    root, record, question = bundle
    before = deepcopy(record)
    verifier = FrozenAnnualSourceVerifier(root)
    span = verifier.verify_record(record, question)
    assert (span['source_start'], span['source_end']) == (1000, 1300)
    assert span['coordinate_unit'] == 'unicode_code_point'
    assert record == before
    assert verifier.receipt[0]['pdf_sha256'] == record['meta']['source_pdf_sha256']


@pytest.mark.parametrize('change', ['text', 'stock', 'year', 'page', 'digest', 'doc', 'url', 'stride', 'outside', 'role', 'bool_page'])
def test_rejects_source_identity_or_coordinate_changes(bundle, change):
    root, record, question = bundle
    verifier = FrozenAnnualSourceVerifier(root)
    if change == 'text': record['text'] += ' forged'
    elif change == 'stock': record['meta']['stock_code'] = '000002'
    elif change == 'year': question['report_year'] = 2023
    elif change == 'page': record['meta']['physical_pdf_page_1based'] = 2
    elif change == 'bool_page': record['meta']['physical_pdf_page_1based'] = True
    elif change == 'digest': record['meta']['source_pdf_sha256'] = '0' * 64
    elif change == 'doc': record['doc_id'] = 'another-document'
    elif change == 'url': record['source'] = 'https://example.invalid/other.pdf'
    elif change == 'stride': record['chunk_id'] = 'HELD-000001-2024-P1-S1001'
    elif change == 'outside': record['chunk_id'] = 'HELD-000001-2024-P1-S2000'
    elif change == 'role': record['meta']['corpus_type'] = 'regulation'
    with pytest.raises(ValueError): verifier.verify_record(record, question)


def test_changed_local_pdf_is_rejected(bundle):
    root, _, _ = bundle
    (root / 'report.pdf').write_bytes(b'changed PDF')
    with pytest.raises(ValueError, match='Local PDF bytes'):
        FrozenAnnualSourceVerifier(root)


def test_manifest_path_traversal_is_rejected(bundle):
    root, _, _ = bundle
    rows = json.loads((root / 'sources.json').read_bytes())
    rows[0]['file'] = '../report.pdf'
    (root / 'sources.json').write_text(json.dumps(rows), encoding='utf-8')
    with pytest.raises(ValueError, match='basename'):
        FrozenAnnualSourceVerifier(root)


def test_duplicate_manifest_pair_is_rejected(bundle):
    root, _, _ = bundle
    rows = json.loads((root / 'sources.json').read_bytes())
    (root / 'sources.json').write_text(json.dumps(rows * 2), encoding='utf-8')
    with pytest.raises(ValueError, match='Duplicate'):
        FrozenAnnualSourceVerifier(root)


def test_union_counts_overlap_once_and_partial_target():
    intervals = [(0, 1200), (1000, 1706), (2400, 2500)]
    assert merge_intervals(intervals) == [[0, 1706], [2400, 2500]]
    assert covered_characters(intervals, 1100, 2000) == 606
    assert covered_characters(intervals, 1209, 1214) == 5
    assert covered_characters([(0, 1200)], 1209, 1214) == 0


@pytest.mark.parametrize('interval', [(-1, 1), (2, 1), (True, 3), (0, 1.5)])
def test_bad_span_cannot_silently_enter_coverage(interval):
    with pytest.raises(ValueError): merge_intervals([interval])
