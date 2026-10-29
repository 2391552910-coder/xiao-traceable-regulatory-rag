"""Run a transparent BM25 diagnostic on the frozen AI development benchmark."""
from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', required=True, type=Path)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError('Refusing to overwrite an existing run')
    if not _HAS_JIEBA:
        raise RuntimeError('This protocol requires jieba; no fallback is permitted')
    benchmark = load_benchmark({'knowledge_base': {'path': 'data/knowledge_base'},
        'evaluation': {'queries_path': 'data/annotation/retrieval_queries_gold.csv',
                       'manifest_path': 'data/annotation/benchmark_manifest.json'}})
    if benchmark.manifest.get('label_origin') != 'ai_dual_pass_adjudicated' or benchmark.manifest.get('usage') != 'development_only':
        raise ValueError('Expected the existing frozen AI development benchmark')
    chunks = [benchmark.chunks[key] for key in sorted(benchmark.chunks)]
    retriever = BM25Retriever(chunks, k1=1.5, b=.75)
    rows = []
    for query in sorted(benchmark.queries, key=lambda q: q.query_id):
        hits = retriever.search(query.query, top_k=10)
        top = [{'chunk_id': chunk.chunk_id, 'doc_id': chunk.doc_id, 'score': score}
               for chunk, score in hits]
        references = sorted(query.relevant)
        at = {}
        for k in (5, 10):
            ids = [x['chunk_id'] for x in top[:k]]
            matched = set(ids) & query.relevant
            at[str(k)] = {'reference_match_fraction': len(matched)/k,
                          'reference_coverage': len(matched)/len(references),
                          'any_reference_hit': bool(matched),
                          'matched_ids': sorted(matched)}
        first = next((index+1 for index, x in enumerate(top) if x['chunk_id'] in query.relevant), None)
        rows.append({'query_id': query.query_id, 'dimension': query.dimension,
                     'reference_ids': references, 'hits': top, 'at': at,
                     'first_reference_rank_within_10': first})
    summary = {}
    for k in (5, 10):
        summary[str(k)] = {name: statistics.mean(float(row['at'][str(k)][name]) for row in rows)
                           for name in ('reference_match_fraction', 'reference_coverage', 'any_reference_hit')}
    summary['mrr_within_10'] = statistics.mean(1/row['first_reference_rank_within_10']
        if row['first_reference_rank_within_10'] else 0 for row in rows)
    result = {'classification': 'exposed AI-reference development diagnostic; not an independent test',
        'n_questions': len(rows), 'n_chunks': len(chunks), 'benchmark_hashes': benchmark.hashes,
        'manifest_sha256': sha256_file(ROOT/'data/annotation/benchmark_manifest.json'),
        'script_sha256': sha256_file(Path(__file__)),
        'retriever_sha256': sha256_file(ROOT/'src/retrieval/bm25.py'),
        'settings': {'corpus': 'all frozen clause chunks, including all document types',
                     'k1': 1.5, 'b': .75, 'tokenizer': 'jieba',
                     'jieba_version': importlib.metadata.version('jieba'),
                     'chunk_order': 'lexicographic chunk_id; stable tie ordering', 'top_k': 10},
        'summary': summary, 'per_query': rows,
        'limitations': ['AI-generated references are incomplete and not independently verified; nonmatches are not confirmed irrelevant.',
                        'This is an exposed development set, not a representative or independent final test.',
                        'Reference overlap is not standard semantic precision or recall; absence of a marked chunk does not establish irrelevance.',
                        'All corpus types are searched without temporal applicability filtering; no annual-report or dual-source performance is measured.',
                        'No new labels or model calls.']}
    args.out_dir.mkdir(parents=True, exist_ok=False)
    (args.out_dir/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps({'n_questions': len(rows), 'n_chunks': len(chunks), 'summary': summary}, ensure_ascii=False))


if __name__ == '__main__':
    main()
