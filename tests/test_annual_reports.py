import json
from pathlib import Path

import pytest

from src.data.annual_reports import document_identity, is_full_report_title, recover_reports, select_report
from src.data.annual_facts import candidates_from_page, extract_candidates, validate_candidate

COMPANY = {'stock_code': '600318.SH', 'name': '新力金融', 'year': 2024}


def test_latest_complete_report_excludes_summary_wrong_year_and_company():
    rows = [{'secCode': '600318', 'announcementTitle': '新力金融2024年年度报告',
             'announcementTime': 100, 'adjunctUrl': 'original.pdf'},
            {'secCode': '600318', 'announcementTitle': '新力金融2024年年度报告（修订版）',
             'announcementTime': 200, 'adjunctUrl': 'revised.pdf'},
            {'secCode': '600318', 'announcementTitle': '新力金融2024年年度报告摘要',
             'announcementTime': 300, 'adjunctUrl': 'summary.pdf'},
            {'secCode': '600519', 'announcementTitle': '贵州茅台2024年年度报告',
             'announcementTime': 400, 'adjunctUrl': 'wrong_company.pdf'},
            {'secCode': '600318', 'announcementTitle': '新力金融2025年年度报告',
             'announcementTime': 500, 'adjunctUrl': 'wrong_year.pdf'}]
    assert select_report(rows, COMPANY, 2024)['adjunctUrl'] == 'revised.pdf'
    assert not is_full_report_title('关于2024年年度报告的更正公告', 2024)
    assert not is_full_report_title('2024年半年度报告', 2024)


def test_pdf_identity_rejects_summary_and_historical_year_only():
    assert document_identity('安徽新力金融股份有限公司 600318 2024 年年度报告', COMPANY, 2024)['verified']
    assert not document_identity('新力金融 600318 2024年年度报告摘要', COMPANY, 2024)['verified']
    assert not document_identity('新力金融 600318 2025年年度报告\n2024年净利润', COMPANY, 2024)['verified']
    assert not document_identity('新力金融 600318 2025年年度报告\n对比2024年年度报告', COMPANY, 2024)['verified']


def test_blocked_preflight_preserves_old_manifest_and_records_no_company_requests(tmp_path):
    historical = tmp_path / 'download_report.csv'
    historical.write_bytes(b'historical success must remain\r\n')

    class Blocked:
        calls = 0

        def get(self, url):
            self.calls += 1
            raise OSError('Tunnel connection failed: 403 Forbidden')

    api = Blocked()
    report = recover_reports([COMPANY], 2024, tmp_path / 'new', client=api)
    assert api.calls == 1
    assert historical.read_bytes() == b'historical success must remain\r\n'
    assert report['identity_verified_reports'] == 0
    assert report['status'] == 'blocked_source_preflight'
    assert report['rows'][0]['status'] == 'not_attempted_source_preflight_failed'
    with pytest.raises(FileExistsError):
        recover_reports([COMPANY], 2024, tmp_path / 'new', client=api)


def test_local_import_requires_unambiguous_version_without_using_network(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / '600318_2024_first.pdf').write_bytes(b'%PDF-')
    (source / '600318_2024_revision.pdf').write_bytes(b'%PDF-')

    class NoNetwork:
        def get(self, url):
            raise AssertionError('Local imports must not use the network')

    report = recover_reports([COMPANY], 2024, tmp_path / 'new', source, NoNetwork())
    assert report['rows'][0]['status'] == 'ambiguous_local_versions'
    assert len(list(source.glob('*.pdf'))) == 2


def test_quote_provenance_rejects_changed_source_quote_or_offsets():
    text = '公司于报告期内召开董事会会议十二次，全部会议留存了会议记录。\n'
    row = candidates_from_page(text, 5, 'original_pdf_hash', COMPANY)[0]
    validate_candidate(row, text, 'original_pdf_hash')
    assert row['review_status'] == 'needs_review' and not row['semantic_fact_verified']
    with pytest.raises(ValueError):
        validate_candidate(row, text, 'different_pdf_hash')
    with pytest.raises(ValueError):
        validate_candidate({**row, 'quote': '捏造的引句'}, text, 'original_pdf_hash')
    with pytest.raises(ValueError):
        validate_candidate({**row, 'page_text_end': 9999}, text, 'original_pdf_hash')


def test_unmentioned_dimensions_do_not_become_negative_facts():
    assert candidates_from_page('本页只提供目录和公司地址。', 1, 'hash', COMPANY) == []


def test_pdf_hash_mismatch_fails_before_any_extraction(tmp_path):
    pdf = tmp_path / 'changed.pdf'
    pdf.write_bytes(b'%PDF- changed source')
    with pytest.raises(ValueError, match='SHA256'):
        extract_candidates(pdf, COMPANY, 'incorrect_hash', tmp_path / 'output')
    assert not (tmp_path / 'output').exists()


def test_pdf_parser_saves_exact_page_text_and_flags_blank_pages_for_ocr(tmp_path):
    from pypdf import PdfWriter
    from src.data.annual_reports import sha256_file
    pdf = tmp_path / 'blank_scan_fixture.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    with pdf.open('wb') as f:
        writer.write(f)
    report = extract_candidates(pdf, COMPANY, sha256_file(pdf), tmp_path / 'output')
    assert report['status'] == 'needs_ocr'
    assert report['empty_text_pages'] == report['pdf_pages'] == 1
    assert report['candidate_count'] == report['verified_fact_count'] == 0
    assert (tmp_path / 'output/page_0001.txt').read_bytes() == b''
