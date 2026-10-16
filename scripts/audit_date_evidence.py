"""Recover typed signing-date evidence from preserved text, without editing frozen dates."""
import argparse
import datetime
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data.benchmark import sha256_file
from scripts.prepare_corpus_v2 import write_json, write_jsonl

DIGITS = dict(zip('零〇○ＯO一二三四五六七八九', [0,0,0,0,0,1,2,3,4,5,6,7,8,9]))
DATE = r'([0-9零〇○ＯO一二三四五六七八九]{4})年([0-9一二三四五六七八九十]{1,3})月([0-9一二三四五六七八九十]{1,3})日'
FOOTER = re.compile(r'(?P<issuer>中国证券监督管理委员会(?:[ \u3000]*中华人民共和国司法部)?)\s*\n[ \u3000]*(?P<date>'+DATE+r')\s*\Z')


def number(text):
    if text.isdecimal():
        return int(text)
    if '十' in text:
        left, right = text.split('十')
        return (DIGITS[left] if left else 1) * 10 + (DIGITS[right] if right else 0)
    return int(''.join(str(DIGITS[c]) for c in text))


def signed_date(text):
    match = FOOTER.search(text)
    if not match:
        return None
    parsed = re.fullmatch(DATE, match['date'])
    date = datetime.date(*(number(v) for v in parsed.groups())).isoformat()
    return {'value': date, 'date_type': 'decision_signing_date', 'quote': match.group(),
            'source_start': match.start(), 'source_end': match.end(),
            'date_literal': match['date'], 'issuer': match['issuer']}


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    corpus = ROOT / 'data/processed/corpus_v2_20261013'
    queue = [json.loads(s) for s in (corpus / 'date_review_queue.jsonl').read_text().splitlines()]
    collected_path = ROOT / 'data/knowledge_base/collection_manifest_penalty.json'
    collected = {r['doc_id']: r for r in json.loads(collected_path.read_text())}
    old_manifest = ROOT / 'data/knowledge_base/manifest.json'
    old = {r['doc_id']: r for r in json.loads(old_manifest.read_text())}
    rows = []
    for entry in queue:
        path = ROOT / entry['source_file']
        text = path.read_text().split('\n---\n', 1)[1].strip()
        evidence = signed_date(text)
        row = {'doc_id': entry['old_doc_id'], 'source_file': entry['source_file'],
               'source_file_sha256': sha256_file(path),
               'official_url_as_collected': collected.get(entry['old_doc_id'], {}).get('url'),
               'collection_manifest_sha256': sha256_file(collected_path),
               'publication_date': None, 'effective_date': None, 'remote_original_verified': False,
               'original_DATE_field_modified': False, 'human_verified': False}
        if evidence:
            assert text[evidence['source_start']:evidence['source_end']] == evidence['quote']
            row.update(status='supported_by_cached_official_text_footer', evidence=evidence,
                       required_input='For authoritative certification: official original capture or human source verification; do not relabel signing date as publication date.')
        else:
            alias = entry['canonical_doc_id']
            recorded = old.get(alias, {}).get('date')
            row.update(status='external_evidence_required', evidence=None,
                       duplicate_metadata_hint={'doc_id': alias, 'date_as_recorded': recorded,
                                                'metadata_sha256': sha256_file(old_manifest),
                                                'date_type': 'unspecified_unverified'} if recorded else None,
                       required_input='Official page publication metadata or original signed decision; duplicate metadata alone is not date-type evidence.')
        rows.append(row)
    write_jsonl(out / 'date_evidence.jsonl', rows)
    write_jsonl(out / 'typed_date_overlay.jsonl', [{'doc_id': r['doc_id'],
                 'decision_signing_date': r['evidence']['value'],
                 'provenance_status': r['status'], 'publication_date': None, 'effective_date': None,
                 'source_file_sha256': r['source_file_sha256'],
                 'evidence_file': 'date_evidence.jsonl'} for r in rows if r['evidence']])
    write_jsonl(out / 'external_evidence_queue.jsonl', [r for r in rows if not r['evidence']])
    summary = {'missing_DATE_fields_audited': len(rows), 'status_counts': dict(Counter(r['status'] for r in rows)),
               'publication_dates_certified': 0, 'effective_dates_certified': 0,
               'frozen_inputs_modified': False, 'script_sha256': sha256_file(Path(__file__)),
               'artifacts_sha256': {p.name: sha256_file(p) for p in sorted(out.iterdir())}}
    write_json(out / 'manifest.json', summary)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir', required=True, type=Path)
    print(json.dumps(build(p.parse_args().out_dir), ensure_ascii=False, indent=2))
