import csv
from pypdf import PdfWriter

from scripts.audit_data_preparation import annual_report_availability


def test_historical_download_success_is_not_file_availability(tmp_path):
    report = tmp_path / 'downloads.csv'
    rows = [{'stock_code': 'A', 'name': 'missing', 'year': '2024', 'status': 'ok', 'file': 'missing.pdf'},
            {'stock_code': 'B', 'name': 'wrong format', 'year': '2024', 'status': 'ok', 'file': 'bad.pdf'},
            {'stock_code': 'C', 'name': 'present', 'year': '2024', 'status': 'ok', 'file': 'good.pdf'},
            {'stock_code': 'D', 'name': 'unsafe', 'year': '2024', 'status': 'ok', 'file': '../outside.pdf'},
            {'stock_code': 'E', 'name': 'header only', 'year': '2024', 'status': 'ok', 'file': 'header.pdf'}]
    with report.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (tmp_path / 'bad.pdf').write_bytes(b'not a PDF')
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(tmp_path / 'good.pdf')
    (tmp_path / 'header.pdf').write_bytes(b'%PDF-1.7\n')
    results = annual_report_availability(tmp_path, report)
    assert [r['availability'] for r in results] == ['missing', 'invalid_pdf', 'present_pdf', 'unsafe_or_empty_path', 'invalid_pdf']
    assert all(r['historical_status'] == 'ok' for r in results)
    assert results[-1]['pdf_header_valid'] and not results[-1]['pdf_parse_valid']
    assert not any(r['company_year_verified'] for r in results)
