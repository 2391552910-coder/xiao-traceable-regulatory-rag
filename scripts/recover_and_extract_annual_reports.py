"""Import local originals first; optionally download missing reports; save review candidates."""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data.annual_reports import recover_reports, sha256_file
from scripts.extract_annual_facts import extract_manifest


def run(source_dir: Path | None, out: Path, allow_download: bool, year: int = 2024) -> dict:
    with (ROOT / 'data/companies/sampling_frame.csv').open(encoding='utf-8-sig', newline='') as f:
        frame = list(csv.DictReader(f))
    historical = ROOT / 'data/companies/download_report.csv'
    historical_hash = sha256_file(historical) if historical.exists() else None
    if not allow_download and (source_dir is None or not source_dir.is_dir()):
        raise ValueError('A readable local source folder is required unless --allow-download is selected')
    out.mkdir(parents=True, exist_ok=False)
    rows, runs = {}, []
    if source_dir is not None and source_dir.is_dir():
        imported = recover_reports(frame, year, out / 'local_import', source_dir)
        rows.update({r['stock_code']: r for r in imported['rows']})
        runs.append({'mode': 'local_import', 'status': imported['status'],
                     'identity_verified_reports': imported['identity_verified_reports']})
    missing = [r for r in frame if rows.get(r['stock_code'], {}).get('status') not in {'imported','downloaded'}]
    if missing and allow_download:
        downloaded = recover_reports(missing, year, out / 'download_missing')
        rows.update({r['stock_code']: r for r in downloaded['rows']})
        runs.append({'mode': 'download_missing', 'status': downloaded['status'],
                     'identity_verified_reports': downloaded['identity_verified_reports']})
    merged = [rows[r['stock_code']] for r in frame]
    manifest = out / 'source_manifest.csv'
    with manifest.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(merged[0]))
        writer.writeheader()
        writer.writerows(merged)
    extraction = extract_manifest(manifest, out / 'fact_candidates')
    if historical_hash is not None and sha256_file(historical) != historical_hash:
        raise ValueError('Historical download manifest changed')
    report = {'status': 'sources_recovered_candidates_need_review'
              if extraction['documents_processed'] == len(frame) else 'incomplete_sources',
              'requested_companies': len(frame), 'pdf_documents_processed': extraction['documents_processed'],
              'candidate_count': extraction['candidate_count'], 'verified_fact_count': 0,
              'formal_data_ready': False, 'historical_manifest_unchanged': True,
              'historical_manifest_sha256': historical_hash, 'source_runs': runs,
              'network_download_allowed': allow_download}
    (out / 'pipeline_run.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--allow-download', action='store_true', help='Download only companies absent from the local import')
    parser.add_argument('--year', type=int, default=2024)
    args = parser.parse_args()
    report = run(args.source_dir, args.out_dir, args.allow_download, args.year)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['pdf_documents_processed'] == report['requested_companies'] else 2


if __name__ == '__main__':
    sys.exit(main())
