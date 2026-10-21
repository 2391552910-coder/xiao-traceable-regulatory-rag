"""Recover originals into new directories, preserving historical inputs."""
from __future__ import annotations
import csv
import hashlib
import json
import re
import shutil
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STOCK_LIST_URL = 'https://www.cninfo.com.cn/new/data/szse_stock.json'
QUERY_URL = 'https://www.cninfo.com.cn/new/hisAnnouncement/query'
STATIC_URL = 'https://static.cninfo.com.cn/'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cninfo.com.cn/'}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def is_full_report_title(title: str, year: int) -> bool:
    clean = re.sub(r'<[^>]+>|\s+', '', title)
    if any(w in clean for w in ('摘要', '英文', '取消', '更正公告', '提示性公告', '半年度', '季度')):
        return False
    match = re.search(rf'{year}年?年度报告(.*)$', clean)
    return bool(match and (not match[1] or re.fullmatch(r'[（(].*(修订|更正|更新|修正).*[）)]', match[1])))


def select_report(announcements: list[dict], company: dict, year: int) -> dict | None:
    code = company['stock_code'].split('.')[0]
    candidates = [a for a in announcements if
                  code in re.split(r'[,;\s]+', str(a.get('secCode', code)))
                  and is_full_report_title(a.get('announcementTitle', ''), year)
                  and a.get('adjunctUrl')]
    return max(candidates, key=lambda a: int(a.get('announcementTime') or 0)) if candidates else None


def document_identity(front_text: str, company: dict, year: int) -> dict:
    text = re.sub(r'\s+', '', front_text)
    name = re.sub(r'^(?:\*?ST)', '', company['name'])
    main_title = re.search(r'(?P<year>20\d{2})年?年度报告(?P<summary>摘要)?', text)
    flags = {'company_name_matches': name in text,
             'stock_code_matches': bool(re.search(r'(?<!\d)' + company['stock_code'].split('.')[0] + r'(?!\d)', front_text)),
             'report_year_matches': bool(main_title and int(main_title['year']) == year),
             'summary_detected': bool(main_title and main_title['summary'])}
    flags['verified'] = all(flags[k] for k in ('company_name_matches', 'stock_code_matches',
                                             'report_year_matches')) and not flags['summary_detected']
    return flags


def inspect_pdf(path: Path, company: dict, year: int) -> dict:
    from pypdf import PdfReader
    with path.open('rb') as f:
        if f.read(5) != b'%PDF-':
            raise ValueError('Response is not a PDF')
    reader = PdfReader(path, strict=False)
    if reader.is_encrypted and not reader.decrypt(''):
        raise ValueError('PDF is encrypted and cannot be read')
    if not reader.pages:
        raise ValueError('PDF has no pages')
    text = '\n'.join(p.extract_text() or '' for p in reader.pages[:10])
    return {'sha256': sha256_file(path), 'bytes': path.stat().st_size,
            'page_count': len(reader.pages), 'identity': document_identity(text, company, year)}


class Client:
    """Keep inherited proxy and CA trust, delaying public requests by one second."""
    def __init__(self):
        self.last_request = 0.0

    def get(self, url: str, data: dict | None = None) -> bytes:
        delay = 1 - (time.monotonic() - self.last_request)
        if delay > 0:
            time.sleep(delay)
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        self.last_request = time.monotonic()
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=HEADERS), timeout=45) as r:
            raw = r.read(100 * 1024 * 1024 + 1)
        if len(raw) > 100 * 1024 * 1024:
            raise ValueError('Response exceeds the 100 MiB limit')
        return raw

    def announcements(self, company: dict, org_id: str, year: int) -> list[dict]:
        records = []
        for page in range(1, 11):
            data = {'pageNum': str(page), 'pageSize': '30',
                    'column': 'sse' if company['stock_code'].endswith('.SH') else 'szse',
                    'tabName': 'fulltext', 'stock': f"{company['stock_code'].split('.')[0]},{org_id}",
                    'category': 'category_ndbg_szsh',
                    'seDate': f'{year + 1}-01-01~{year + 1}-12-31', 'isHLtitle': 'true'}
            response = json.loads(self.get(QUERY_URL, data))
            items = response.get('announcements') or []
            records.extend(items)
            if not response.get('hasMore') or not items:
                return records
        raise ValueError('More than 10 announcement pages; source coverage is incomplete')


def recover_reports(frame: list[dict], year: int, out: Path, source_dir: Path | None = None,
                    client: Client | None = None) -> dict:
    if not frame:
        raise ValueError('No companies selected')
    if source_dir is not None and not source_dir.is_dir():
        raise ValueError(f'Local PDF directory is unavailable: {source_dir}')
    out.mkdir(parents=True, exist_ok=False)
    (out / 'pdf').mkdir()
    report = {'schema_version': 1, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'report_year': year, 'requested_companies': len(frame), 'formal_data_ready': False,
              'mode': 'local_import' if source_dir else 'cninfo', 'historical_manifest_updated': False,
              'source_candidates': {}, 'publication_window': [f'{year+1}-01-01', f'{year+1}-12-31']}
    api, org_ids, preflight_error = client or Client(), {}, None
    if source_dir is None:
        try:
            org_ids = {s['code']: s['orgId'] for s in json.loads(api.get(STOCK_LIST_URL))['stockList']}
        except Exception as error:
            preflight_error = f'{type(error).__name__}: {error}'
            report['preflight_error'] = {'url': STOCK_LIST_URL, 'error': preflight_error}
    local_files = sorted(source_dir.rglob('*.pdf')) + sorted(source_dir.rglob('*.PDF')) if source_dir else []
    rows = []
    for company in frame:
        row = {'stock_code': company['stock_code'], 'name': company['name'], 'year': year,
               'status': 'not_attempted', 'file': '', 'source_url': '', 'publication_date': '',
               'source_title': '', 'sha256': '', 'bytes': 0, 'page_count': 0,
               'identity_verified': False, 'error': ''}
        if preflight_error:
            row.update(status='not_attempted_source_preflight_failed', error=preflight_error)
            rows.append(row)
            continue
        filename = re.sub(r'[\\/:*?"<>|]', '_', f"{company['stock_code']}_{company['name']}_{year}.pdf")
        target = out / 'pdf' / filename
        try:
            code = company['stock_code'].split('.')[0]
            if source_dir:
                matches = [p for p in local_files if code in p.stem and str(year) in p.stem]
                if len(matches) != 1:
                    row.update(status='missing_local_pdf' if not matches else 'ambiguous_local_versions',
                               error=f'Expected one code/year PDF, found {len(matches)}')
                    rows.append(row)
                    continue
                shutil.copy2(matches[0], target)
                row.update(source_url=matches[0].resolve().as_uri(), source_title=matches[0].name)
            else:
                announcements = api.announcements(company, org_ids[code], year)
                report['source_candidates'][company['stock_code']] = announcements
                selected = select_report(announcements, company, year)
                if selected is None:
                    row['status'] = 'full_report_not_found'
                    rows.append(row)
                    continue
                url = urllib.parse.urljoin(STATIC_URL, selected['adjunctUrl'])
                if urllib.parse.urlparse(url).hostname != 'static.cninfo.com.cn':
                    raise ValueError('File is outside the recorded official host')
                target.write_bytes(api.get(url))
                row.update(source_url=url, source_title=re.sub(r'<[^>]+>', '', selected['announcementTitle']))
                if selected.get('announcementTime'):
                    from datetime import timedelta
                    row['publication_date'] = datetime.fromtimestamp(int(selected['announcementTime']) / 1000,
                                                                     timezone(timedelta(hours=8))).date().isoformat()
            info = inspect_pdf(target, company, year)
            row.update(file=str(target.resolve()), sha256=info['sha256'], bytes=info['bytes'],
                       page_count=info['page_count'], identity_verified=info['identity']['verified'])
            report.setdefault('identity_checks', {})[company['stock_code']] = info['identity']
            row['status'] = ('imported' if source_dir else 'downloaded') if row['identity_verified'] else 'pdf_identity_needs_review'
        except Exception as error:
            row.update(status='failed', error=f'{type(error).__name__}: {error}')
        rows.append(row)
        print(f"{row['stock_code']} {row['status']}", flush=True)
    accepted = sum(r['status'] in {'downloaded', 'imported'} for r in rows)
    report.update(completed_at_utc=datetime.now(timezone.utc).isoformat(), rows=rows,
                  available_pdf_files=sum(bool(r['file']) for r in rows), identity_verified_reports=accepted,
                  status='completed' if accepted == len(frame) else 'blocked_source_preflight' if preflight_error else 'incomplete')
    with (out / 'download_report.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out / 'recovery_run.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report
