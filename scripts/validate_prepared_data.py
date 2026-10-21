"""Read-only structural integrity checks; does not certify legal or semantic correctness."""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data.benchmark import sha256_file, corpus_hash
from src.data.corpus_v2 import digest
from src.data.knowledge_loader import load_documents
from src.data.holdout import release_errors
from scripts.prepare_corpus_v2 import read_csv


def verify_bundle(directory):
    manifest = json.loads((directory / 'manifest.json').read_text())
    for name, expected in manifest['artifacts_sha256'].items():
        assert sha256_file(directory / name) == expected, (directory, name)
    for key in ('tools_sha256', 'code_sha256', 'input_sha256'):
        for name, expected in manifest.get(key, {}).items():
            assert sha256_file(ROOT / name) == expected, name
    return manifest


def validate(corpus, heldout, labels):
    cm, hm, lm = map(verify_bundle, [corpus, heldout, labels])
    read = lambda folder, name: [json.loads(s) for s in (folder / name).read_text().splitlines()]
    assert cm['source_corpus_sha256'] == corpus_hash(ROOT / 'data/knowledge_base')
    assert lm['corpus_manifest_sha256'] == sha256_file(corpus / 'manifest.json')
    assert lm['script_sha256'] == sha256_file(ROOT / 'scripts/prepare_label_review.py')
    docs = {d['doc_id']: d for d in read(corpus, 'documents.jsonl')}
    original = {d['doc_id']: d for d in load_documents(ROOT / 'data/knowledge_base')}
    chunks = read(corpus, 'chunks.jsonl')
    assert len({c['chunk_id'] for c in chunks}) == len(chunks)
    groups, by_chunk = defaultdict(list), {c['chunk_id']: c for c in chunks}
    for c in chunks:
        text = docs[c['doc_id']]['text']
        assert c['text'] == text[c['source_start']:c['source_end']]
        assert c['text_sha256'] == digest(c['text']) and c['source_text_sha256'] == digest(text)
        groups[c['doc_id']].append(c)
    for did, doc in docs.items():
        assert ''.join(c['text'] for c in groups[did]) == doc['text']
    for row in read(corpus, 'document_manifest.jsonl'):
        assert sha256_file(ROOT / row['source_file']) == row['source_file_sha256']
        if row['canonical_doc_id']:
            assert original[row['old_doc_id']]['text'] == docs[row['canonical_doc_id']]['text']
    for row in read(corpus, 'chunk_migration.jsonl'):
        assert row['semantic_label_inherited'] is False
        if row['canonical_doc_id']:
            mapped = [by_chunk[cid] for cid in row['new_chunk_ids']]
            assert mapped and mapped[0]['source_start'] <= row['old_source_start']
            assert mapped[-1]['source_end'] >= row['old_source_end']
    candidates = read(heldout, 'candidate_queries.jsonl')
    assert release_errors(candidates) and hm['final_test_count'] == 0
    forms = [read_csv(labels / f'blind_review_{tag}.csv') for tag in ['A', 'B']]
    assert {(r['query_id'], r['chunk_id']) for r in forms[0]} == {(r['query_id'], r['chunk_id']) for r in forms[1]}
    for rows in forms:
        assert len(rows) == lm['candidate_pairs']
        assert all(not r['human_grade'] and not r['reviewer'] for r in rows)
        assert all(r['text_sha256'] == digest(r['text']) for r in rows)
    return {'structural_integrity': 'passed', 'semantic_or_temporal_certification': False,
            'documents': len(docs), 'chunks': len(chunks), 'blind_review_pairs': lm['candidate_pairs'],
            'heldout_candidates': len(candidates), 'approved_final_test_queries': 0}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['corpus', 'heldout', 'labels']:
        ap.add_argument(f'--{name}-dir', required=True, type=Path)
    args = ap.parse_args()
    print(json.dumps(validate(args.corpus_dir, args.heldout_dir, args.labels_dir), indent=2))
