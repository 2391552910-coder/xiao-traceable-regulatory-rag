"""Compare plain and official query prompts using real weights on frozen selected samples."""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--reference-dir', required=True)
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    report = {'tested_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'started',
              'model_loaded': False, 'inference_executed': False,
              'quality_benchmark': False, 'scope': '12 selected chunks / 4 development queries',
              'reranker_tested': False}
    try:
        import numpy as np
        import torch
        from src.config import load_config
        from src.data.benchmark import load_benchmark
        from src.retrieval.hybrid import HybridRetriever
        from scripts.compile_independent_review import check_artifacts

        torch.set_num_threads(4)
        torch.manual_seed(42)
        check_artifacts()
        cfg = load_config()
        benchmark = load_benchmark(cfg)
        reference = Path(args.reference_dir)
        previous = json.loads((reference / 'retrieval_test.json').read_text())
        assert previous['status'] == 'passed' and previous['inference_executed']
        for name, digest in previous['artifacts_sha256'].items():
            assert hashlib.sha256((reference / name).read_bytes()).hexdigest() == digest
        sample = json.loads((reference / 'sample.json').read_text())
        chunks = [benchmark.chunks[r['chunk_id']] for r in sample['chunks']]
        assert all(c.text == row['text'] for c, row in zip(chunks, sample['chunks']))
        official = json.loads((Path(args.model) / 'config_sentence_transformers.json').read_text())['prompts']['query']
        assert cfg['retrieval']['embedding_query_prompt'] == official
        retriever = HybridRetriever(chunks, backend='qwen', model_name=args.model,
                                    device='cpu', batch_size=1, query_prompt=official,
                                    vector_weight=0.7)
        report['model_loaded'] = True
        matrix = retriever.dense._matrix
        prior_docs = np.load(reference / 'document_vectors.npy', allow_pickle=False)
        assert np.allclose(matrix, prior_docs, atol=1e-6, rtol=1e-5)
        queries = [q['text'] for q in sample['queries']]
        vectors = {}
        rows = []
        for name, prompt in [('plain', ''), ('official_query', official)]:
            retriever.dense.query_prompt = prompt
            vectors[name] = retriever.dense.encode_queries(queries)
            assert vectors[name].shape == (4, 1024)
            assert np.isfinite(vectors[name]).all()
            assert np.allclose(np.linalg.norm(vectors[name], axis=1), 1, atol=1e-4)
            for i, q in enumerate(sample['queries']):
                positives = set(q['selected_direct_positive_ids'])
                for method, search in [('dense', retriever.dense.search),
                                       ('bm25', retriever.bm25.search), ('hybrid', retriever.search)]:
                    hits = search(q['text'], top_k=3)
                    assert len(hits) == 3 and len({c.chunk_id for c, _ in hits}) == 3
                    if method == 'dense':
                        ids = [chunks[j].chunk_id for j in np.argsort(-(matrix @ vectors[name][i]))[:3]]
                        assert ids == [c.chunk_id for c, _ in hits]
                    rows.append({'prompt_variant': name, 'query_id': q['query_id'],
                                 'method': method, 'top_k': 3,
                                 'hits': [{'chunk_id': c.chunk_id, 'score': float(score),
                                           'selected_direct_positive': c.chunk_id in positives}
                                          for c, score in hits]})
        assert np.allclose(vectors['plain'], np.load(reference / 'query_vectors.npy', allow_pickle=False),
                           atol=1e-6, rtol=1e-5)
        differences = np.linalg.norm(vectors['plain'] - vectors['official_query'], axis=1)
        assert np.all(differences > 1e-3)
        np.save(out / 'document_vectors.npy', matrix, allow_pickle=False)
        for name, value in vectors.items():
            np.save(out / f'query_vectors_{name}.npy', value, allow_pickle=False)
        (out / 'sample.json').write_text(json.dumps(sample, ensure_ascii=False, indent=2) + '\n')
        # Load persisted files again before checking the recorded dense rankings.
        saved_docs = np.load(out / 'document_vectors.npy', allow_pickle=False)
        for row in rows:
            if row['method'] == 'dense':
                saved_queries = np.load(out / f"query_vectors_{row['prompt_variant']}.npy", allow_pickle=False)
                i = next(i for i, q in enumerate(sample['queries']) if q['query_id'] == row['query_id'])
                ids = [chunks[j].chunk_id for j in np.argsort(-(saved_docs @ saved_queries[i]))[:3]]
                assert ids == [h['chunk_id'] for h in row['hits']]
        tokenizer = retriever.dense._model.tokenizer
        lengths = [len(tokenizer.encode(c.text)) for c in chunks]
        query_lengths = [len(tokenizer.encode(official + q)) for q in queries]
        report.update(status='passed', inference_executed=True,
                      document_vector_shape=list(matrix.shape), query_vector_shape=[4, 1024],
                      document_vectors_match_plain_reference=True, plain_queries_match_reference=True,
                      official_prompt_changes_all_query_vectors=True, query_vector_difference_l2=differences.tolist(),
                      persisted_dense_rankings_reproduced=8, results=rows,
                      encoding= retriever.dense.encoding_metadata,
                      baseline_hashes=benchmark.hashes, sample_document_token_lengths=lengths,
                      instructed_query_token_lengths=query_lengths,
                      sample_model_truncation_count=sum(n > retriever.dense._model.max_seq_length
                                                        for n in lengths + query_lengths),
                      selected_sample_summary=[{'prompt_variant': variant, 'method': method,
                                               'top1_selected_direct_positive': sum(x['hits'][0]['selected_direct_positive'] for x in rows if x['method'] == method and x['prompt_variant'] == variant),
                                               'n_queries': 4}
                                              for variant in vectors for method in ['dense', 'bm25', 'hybrid']],
                      limitations=['Selected positives only; this is not a full-corpus or held-out quality evaluation.',
                                   'Unselected chunks are not asserted irrelevant.'])
        report['artifacts_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in out.iterdir() if p.is_file()}
    except Exception as error:
        report.update(status='failed', error_type=type(error).__name__, error=str(error))
    finally:
        report['elapsed_seconds'] = round(time.perf_counter() - started, 3)
        report['peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        (out / 'prompt_comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({k: v for k, v in report.items() if k != 'results'}, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
