"""Extract source-linked review candidates only from identity-verified recovered PDFs."""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data.annual_facts import extract_candidates
from src.data.annual_reports import inspect_pdf


def extract_manifest(manifest: Path, out_dir: Path) -> dict:
    with manifest.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    out_dir.mkdir(parents=True, exist_ok=False)
    reports, unavailable = [], []
    for row in rows:
        if row['status'] not in {'downloaded', 'imported'} or row.get('identity_verified') != 'True':
            unavailable.append({'stock_code': row['stock_code'], 'source_status': row['status']})
            continue
        try:
            info = inspect_pdf(Path(row['file']), row, int(row['year']))
            if not info['identity']['verified']:
                raise ValueError('PDF company/year/full-report identity did not verify')
            reports.append(extract_candidates(Path(row['file']), row, row['sha256'],
                                               out_dir / row['stock_code']))
        except Exception as error:
            unavailable.append({'stock_code': row['stock_code'], 'error': f'{type(error).__name__}: {error}'})
    report = {'status': 'needs_review' if reports else 'blocked_no_verified_source_pdfs',
              'documents_processed': len(reports), 'candidate_count': sum(r['candidate_count'] for r in reports),
              'verified_fact_count': 0, 'formal_data_ready': False, 'unavailable': unavailable,
              'reports': reports}
    (out_dir / 'extraction_run.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    report = extract_manifest(args.manifest, args.out_dir)
    print(json.dumps({k:v for k,v in report.items() if k not in {'reports','unavailable'}}, ensure_ascii=False, indent=2))
    return 0 if report['reports'] and not report['unavailable'] else 2


if __name__ == '__main__':
    sys.exit(main())
