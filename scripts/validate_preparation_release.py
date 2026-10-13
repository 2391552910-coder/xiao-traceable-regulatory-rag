"""Offline release integrity checks for all prepared datasets; no semantic certification."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_prepared_data import validate, verify_bundle
from scripts.audit_date_evidence import signed_date
from src.data.holdout_v2 import release_errors_v2


def main():
    summary = validate(ROOT/'data/processed/corpus_v2_20261013',
                       ROOT/'data/heldout/candidates_20261013',
                       ROOT/'data/processed/label_review_v2_20261013')
    directory = ROOT/'data/processed/date_evidence_20261013'
    manifest = json.loads((directory/'manifest.json').read_text())
    assert hashlib.sha256((ROOT/'scripts/audit_date_evidence.py').read_bytes()).hexdigest() == manifest['script_sha256']
    for name, expected in manifest['artifacts_sha256'].items():
        assert hashlib.sha256((directory/name).read_bytes()).hexdigest() == expected, name
    rows = [json.loads(line) for line in (directory/'date_evidence.jsonl').read_text().splitlines()]
    for row in rows:
        path = ROOT/row['source_file']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row['source_file_sha256']
        body = path.read_text().split('\n---\n', 1)[1].strip()
        assert signed_date(body) == row['evidence']
    family = ROOT/'data/heldout/family_review_final_20261013'
    verify_bundle(family)
    registry = json.loads((family/'development_registry.json').read_text())
    for name, expected in registry['input_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected, name
    candidates = [json.loads(line) for line in (family/'all_candidate_decisions.jsonl').read_text().splitlines()]
    errors = release_errors_v2(candidates, registry)
    recorded = json.loads((family/'release_gate.json').read_text())
    assert [list(error) for error in errors] == recorded['errors']
    assert recorded['passed'] is False
    summary.update(date_records_verified=len(rows),
                   locally_supported_signing_dates=sum(row['evidence'] is not None for row in rows),
                   final_candidate_release_gate='correctly_rejected')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
