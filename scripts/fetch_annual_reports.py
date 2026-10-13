"""Recover originals from CNINFO or a local PDF folder into a new directory."""
import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data.annual_reports import recover_reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--code', nargs='+', help='Stock codes, such as 600519.SH')
    parser.add_argument('--year', type=int, default=2024)
    parser.add_argument('--source-dir', type=Path, help='Existing local PDF folder; makes no network requests')
    parser.add_argument('--out-dir', type=Path, help='New output; historical download_report.csv is never changed')
    args = parser.parse_args()
    with (ROOT / 'data/companies/sampling_frame.csv').open(encoding='utf-8-sig', newline='') as f:
        frame = list(csv.DictReader(f))
    if args.code:
        unknown = set(args.code) - {r['stock_code'] for r in frame}
        if unknown:
            parser.error(f'Unknown stock codes: {sorted(unknown)}')
        frame = [r for r in frame if r['stock_code'] in args.code]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = args.out_dir or ROOT / 'data/companies/annual_reports' / f'recovered_{stamp}'
    report = recover_reports(frame, args.year, out, args.source_dir)
    print(f"Actual recovery: {report['identity_verified_reports']}/{len(frame)}, status={report['status']}, output={out}")
    return 0 if report['status'] == 'completed' else 2 if report['status'] == 'blocked_source_preflight' else 1


if __name__ == '__main__':
    sys.exit(main())
