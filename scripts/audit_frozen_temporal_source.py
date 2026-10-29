"""Audit one source in saved temporal-filter records, without judging relevance."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--ranking', type=Path, required=True)
    parser.add_argument('--doc-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.prepared / 'comparison_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    files = sorted(args.prepared.glob('HOLDOUT*.json'))
    if len(files) != manifest['question_count']:
        raise ValueError('Prepared question-file count differs from manifest')
    entries = manifest['question_files']
    expected = {entry['path']: entry for entry in entries}
    if (len(entries) != manifest['question_count'] or len(expected) != len(entries)
            or set(expected) != {path.name for path in files}):
        raise ValueError('Prepared question files differ from manifest')
    results = []
    for path in files:
        entry = expected[path.name]
        file_hash = digest(path)
        if file_hash != entry['sha256']:
            raise ValueError(f'Prepared question-file hash mismatch: {path.name}')
        prepared = json.loads(path.read_text(encoding='utf-8'))
        if prepared['question']['question_id'] != entry['question_id']:
            raise ValueError(f'Prepared question ID differs from manifest: {path.name}')
        audit = prepared['temporal_scope_audit']
        rows = [row for row in audit['rows'] if row['doc_id'] == args.doc_id]
        results.append({
            'question_id': prepared['question']['question_id'],
            'prepared_file': path.name,
            'prepared_sha256': file_hash,
            'target_date': audit['target_date'],
            'unknown_policy': audit['unknown_policy'],
            'matching_chunks': len(rows),
            'retained_chunks': sum(row['retained'] is True for row in rows),
            'relations': sorted({row['relation'] for row in rows}),
            'semantic_support_verified': prepared['semantic_support_verified'],
            'legal_applicability_verified': prepared['legal_applicability_verified'],
        })
    if len({row['question_id'] for row in results}) != len(results):
        raise ValueError('Duplicate question IDs in prepared files')
    with args.ranking.open(encoding='utf-8-sig', newline='') as handle:
        ranking = list(csv.DictReader(handle))
    hits = [row for row in ranking if row['doc_id'] == args.doc_id]
    output = {
        'source_document_id': args.doc_id,
        'manifest_sha256': digest(manifest_path),
        'execution_plan_sha256_recorded_in_manifest': manifest['execution_plan_sha256'],
        'ranking_sha256': digest(args.ranking),
        'ranking_rows': len(ranking),
        'ranking_hits': len(hits),
        'questions': len(results),
        'prepared_files_match_manifest': True,
        'per_question': results,
        'scope': ('Saved pre-ranking temporal-filter records and saved candidate table only. '
                  'Retention does not prove later routing, relevance, or legal applicability.'),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'questions': len(results), 'ranking_hits': len(hits),
                      'output_sha256': digest(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
