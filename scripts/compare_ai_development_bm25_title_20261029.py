"""Compare title-augmented BM25 with a saved exposed-set baseline."""
from __future__ import annotations

import argparse
from dataclasses import replace
import importlib.metadata
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data.benchmark import load_benchmark, sha256_file
from src.retrieval.bm25 import BM25Retriever, _HAS_JIEBA


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', required=True, type=Path)
    p.add_argument('--out-dir', required=True, type=Path)
    a = p.parse_args()
    if a.out_dir.exists():
        raise FileExistsError('Refusing to overwrite an existing run')
    if not _HAS_JIEBA:
        raise RuntimeError('This protocol requires jieba; no fallback is permitted')
    baseline = json.loads(a.baseline.read_text(encoding='utf-8'))
    benchmark = load_benchmark({'knowledge_base': {'path': 'data/knowledge_base'},
        'evaluation': {'queries_path': 'data/annotation/retrieval_queries_gold.csv',
                       'manifest_path': 'data/annotation/benchmark_manifest.json'}})
    settings = baseline['settings']
    if (baseline['benchmark_hashes'] != benchmark.hashes or
        baseline['manifest_sha256'] != sha256_file(ROOT/'data/annotation/benchmark_manifest.json') or
        baseline['retriever_sha256'] != sha256_file(ROOT/'src/retrieval/bm25.py') or
        settings['jieba_version'] != importlib.metadata.version('jieba') or
        settings['k1'] != 1.5 or settings['b'] != .75 or settings['top_k'] != 10 or
        settings['chunk_order'] != 'lexicographic chunk_id; stable tie ordering'):
        raise ValueError('Baseline inputs or retrieval settings differ')
    base_rows = {row['query_id']: row for row in baseline['per_query']}
    queries = sorted(benchmark.queries, key=lambda q: q.query_id)
    if len(base_rows) != len(queries) or set(base_rows) != {q.query_id for q in queries}:
        raise ValueError('Baseline query inventory differs')
    chunks = [benchmark.chunks[key] for key in sorted(benchmark.chunks)]
    retriever = BM25Retriever([replace(c, text=c.doc_title+'\n'+c.text) for c in chunks], k1=1.5, b=.75)
    rows = []
    for q in queries:
        old = base_rows[q.query_id]
        if old['reference_ids'] != sorted(q.relevant):
            raise ValueError('Baseline reference IDs differ')
        hits = [{'chunk_id': c.chunk_id, 'doc_id': c.doc_id, 'score': score}
                for c, score in retriever.search(q.query, top_k=10)]
        at = {}
        for k in (5, 10):
            matched = set(x['chunk_id'] for x in hits[:k]) & q.relevant
            current = {'reference_match_fraction': len(matched)/k,
                       'reference_coverage': len(matched)/len(q.relevant),
                       'any_reference_hit': bool(matched), 'matched_ids': sorted(matched)}
            at[str(k)] = {'baseline': old['at'][str(k)], 'title_augmented': current}
        rows.append({'query_id': q.query_id, 'dimension': q.dimension,
                     'reference_ids': old['reference_ids'], 'baseline_hits': old['hits'],
                     'title_augmented_hits': hits, 'at': at})
    summary = {}
    for k in (5, 10):
        fields = {}
        for metric in ('reference_match_fraction', 'reference_coverage', 'any_reference_hit'):
            before = [float(row['at'][str(k)]['baseline'][metric]) for row in rows]
            after = [float(row['at'][str(k)]['title_augmented'][metric]) for row in rows]
            fields[metric] = {'baseline': statistics.mean(before), 'title_augmented': statistics.mean(after),
                              'paired_delta': statistics.mean(y-x for x,y in zip(before,after)),
                              'improved_queries': sum(y>x for x,y in zip(before,after)),
                              'unchanged_queries': sum(y==x for x,y in zip(before,after)),
                              'worse_queries': sum(y<x for x,y in zip(before,after))}
        summary[str(k)] = fields
    result = {'classification': 'post-hoc comparison on exposed AI-reference development set; not independent validation',
              'baseline_sha256': sha256_file(a.baseline), 'script_sha256': sha256_file(Path(__file__)),
              'benchmark_hashes': benchmark.hashes, 'n_questions': len(rows), 'n_chunks': len(chunks),
              'change': 'prepend each chunk’s existing document title to its body for BM25 indexing only',
              'settings': settings, 'summary': summary, 'per_query': rows,
              'limitations': ['Marked AI references are incomplete and not independently validated; unmatched results are not necessarily irrelevant.',
                              'This exposed development sample cannot establish generalization or standard semantic precision and recall.',
                              'Only a single lexical method and title-indexing change were compared; no model calls or new labels.',
                              'All corpus types are included; no annual-report question answering, dual-source generation or legal applicability is evaluated.']}
    a.out_dir.mkdir(parents=True, exist_ok=False)
    (a.out_dir/'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
