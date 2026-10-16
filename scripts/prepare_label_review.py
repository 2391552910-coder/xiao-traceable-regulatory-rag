"""Expand the development review pool on V2 text; export blind, unfilled human forms."""
import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data.clause_splitter import Chunk
from src.data.benchmark import sha256_file
from src.retrieval.bm25 import BM25Retriever
from scripts.prepare_corpus_v2 import read_csv, write_json, write_jsonl


def build(corpus, out):
    out.mkdir(parents=True, exist_ok=False)
    read = lambda name: [json.loads(line) for line in (corpus / name).read_text().splitlines()]
    docs = {d['doc_id']: d for d in read('documents.jsonl')}
    chunks = {c['chunk_id']: c for c in read('chunks.jsonl')}
    index = BM25Retriever([Chunk(c['chunk_id'], c['doc_id'], docs[c['doc_id']]['title'],
                                docs[c['doc_id']]['doc_type'], docs[c['doc_id']]['source'],
                                c['clause_no'], c['text']) for c in chunks.values()])
    origins = defaultdict(set)
    for r in read('label_migration.jsonl'):
        for cid in r['new_chunk_ids']:
            origins[(r['query_id'], cid)].add('coordinate_migration')
    queries = read_csv(ROOT / 'data/annotation/retrieval_queries_gold.csv')
    rng = random.Random(20261013)
    for q in queries:
        for c, _ in index.search(q['query'], top_k=20):
            origins[(q['query_id'], c.chunk_id)].add('bm25_top20')
        for cid in rng.sample(sorted(chunks), min(5, len(chunks))):
            origins[(q['query_id'], cid)].add('random_pool_audit')
    by_query = {q['query_id']: q for q in queries}
    rows, provenance = [], []
    for (qid, cid), methods in sorted(origins.items()):
        c, q = chunks[cid], by_query[qid]
        doc = docs[c['doc_id']]
        rows.append({'query_id': qid, 'dimension': q['dimension'], 'query': q['query'],
                     'chunk_id': cid, 'doc_id': c['doc_id'], 'title': doc['title'],
                     'date_as_recorded': doc['date'], 'source': doc['source'],
                     'source_text_sha256': c['source_text_sha256'],
                     'source_start': c['source_start'], 'source_end': c['source_end'],
                     'text_sha256': c['text_sha256'], 'text': c['text'],
                     'human_grade': '', 'reviewer': '', 'reviewed_at': '', 'rationale': ''})
        provenance.append({'query_id': qid, 'chunk_id': cid, 'pool_methods': sorted(methods),
                           'label_inferred': False})
    # Same rows in different deterministic orders; no previous grade or method shown.
    for tag, seed in [('A', 101), ('B', 202)]:
        shuffled = rows.copy()
        random.Random(seed).shuffle(shuffled)
        with (out / f'blind_review_{tag}.csv').open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(shuffled)
    write_jsonl(out / 'pool_provenance.jsonl', provenance)
    summary = {'status': 'pending_two_human_reviews', 'usage': 'development_only',
               'n_queries': len(queries), 'candidate_pairs': len(rows), 'human_labels': 0,
               'candidate_pool_exhaustive': False,
               'new_pairs_without_migrated_labels': sum('coordinate_migration' not in m for m in origins.values()),
               'methods': ['coordinate migration union', 'BM25 top20', 'seeded random5'],
               'random_seed': 20261013, 'corpus_manifest_sha256': sha256_file(corpus / 'manifest.json'),
               'script_sha256': sha256_file(Path(__file__)),
               'artifacts_sha256': {p.name: sha256_file(p) for p in sorted(out.iterdir())}}
    write_json(out / 'manifest.json', summary)
    return summary


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--corpus-dir', required=True, type=Path)
    ap.add_argument('--out-dir', required=True, type=Path)
    args = ap.parse_args()
    print(json.dumps(build(args.corpus_dir, args.out_dir), ensure_ascii=False, indent=2))
