"""Post-hoc exact-reference versus source-agnostic lexical-overlap audit.

Source-agnostic character overlap cannot establish legal equivalence/applicability.
"""
from __future__ import annotations
import json
import sys
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.replay_cached_retrieval_diagnostics_20261023 import RUN,OUT,load,sha,write_csv,write_json,shingle,page_key,ref_key
from src.data.page_reference_release import load_page_reference_release


def main():
    plan=load(RUN/'execution_plan.json')
    release=load_page_reference_release(plan['reference_dir'],plan['reference_manifest_sha256'])
    index=Path(plan['index_dir'])
    chunks=[json.loads(line) for line in (index/'chunks.jsonl').read_text(encoding='utf-8').splitlines()]
    byid={c['chunk_id']:c for c in chunks}
    manifests=load(RUN/'prepared/comparison_manifest.json')
    allrows=[];pairs=[];doc_counts=Counter();doc_topic=defaultdict(Counter)
    for spec in manifests['question_files']:
        bundle=load(RUN/'prepared'/spec['path']);q=bundle['question'];qid=q['question_id'];topic=qid.split('-2024-')[-1]
        refs=[e for e in release.references_for(qid) if e['role']=='regulation']
        refshingles={e['evidence_id']:shingle(e['exact_quote']) for e in refs}
        for strategy in ['merged','dual']:
            context=bundle['contexts'][strategy]
            laws=[r for r in context['source_records'] if r['meta']['corpus_type']=='regulation']
            selected_shingles=set().union(*(shingle(r['text']) for r in laws))
            src_pages={page_key(r) for r in laws}
            strict=sum(ref_key(ev) in src_pages for ev in refs)/len(refs)
            relaxed=float(np.mean([len(s & selected_shingles)/len(s) if s else 0 for s in refshingles.values()]))
            allrows.append(dict(question_id=qid,topic=topic,strategy=strategy,n_law_chunks=len(laws),
                strict_reference_location_coverage=strict,source_agnostic_law_quote_12char_coverage=relaxed,
                note='Lexical overlap only; no legal equivalence or relevance judgment'))
            for r in laws:
                if strategy=='dual':
                    doc_counts[r['doc_id']]+=1;doc_topic[r['doc_id']][topic]+=1
                rs=shingle(r['text'])
                for ev in refs:
                    es=refshingles[ev['evidence_id']]
                    overlap=len(es&rs)/len(es) if es else 0
                    if overlap>0:
                        pairs.append(dict(question_id=qid,topic=topic,strategy=strategy,chunk_id=r['chunk_id'],
                            doc_id=r['doc_id'],document_title=r['document_title'],clause_no=r['clause_no'],
                            source_page_match=int(page_key(r)==ref_key(ev)),reference_evidence_id=ev['evidence_id'],
                            reference_quote_12char_coverage=overlap,shared_12char_shingles=len(es&rs)))
    summaries=[]
    for strategy in ['merged','dual']:
        for topic in ['ALL','AUDIT_COMMITTEE','DIVIDEND_DISCLOSURE','INTERNAL_CONTROL']:
            rows=[r for r in allrows if r['strategy']==strategy and (topic=='ALL' or r['topic']==topic)]
            summaries.append(dict(strategy=strategy,topic=topic,questions=len(rows),
                strict_reference_location_coverage_mean=float(np.mean([r['strict_reference_location_coverage'] for r in rows])),
                source_agnostic_law_quote_12char_coverage_mean=float(np.mean([r['source_agnostic_law_quote_12char_coverage'] for r in rows])),
                questions_with_any_source_agnostic_overlap=sum(r['source_agnostic_law_quote_12char_coverage']>0 for r in rows),
                questions_with_strict_miss_but_source_agnostic_overlap=sum(r['strict_reference_location_coverage']==0 and r['source_agnostic_law_quote_12char_coverage']>0 for r in rows)))
    docs=[]
    for docid,n in doc_counts.most_common():
        sample=next(c for c in chunks if c['doc_id']==docid)
        docs.append(dict(doc_id=docid,document_title=sample['doc_title'],retrieved_chunk_occurrences=n,
            audit_committee_occurrences=doc_topic[docid]['AUDIT_COMMITTEE'],
            dividend_occurrences=doc_topic[docid]['DIVIDEND_DISCLOSURE'],internal_control_occurrences=doc_topic[docid]['INTERNAL_CONTROL']))
    excluded=Counter(c['doc_id'] for c in chunks if c['doc_id'] in plan['excluded_superseded_doc_ids'])
    write_csv(OUT/'alternate_law_source_per_question.csv',allrows)
    write_csv(OUT/'alternate_law_source_overlap_pairs.csv',sorted(pairs,key=lambda r:-r['reference_quote_12char_coverage']))
    write_csv(OUT/'alternate_law_source_summary.csv',summaries)
    write_csv(OUT/'selected_law_document_distribution.csv',docs)
    write_json(OUT/'alternate_law_audit_receipt.json',dict(script_sha256=sha(Path(__file__)),
        reference_manifest_sha256=plan['reference_manifest_sha256'],frozen_prepared_manifest_sha256=sha(RUN/'prepared/comparison_manifest.json'),
        excluded_legacy_chunks=dict(excluded),full_index_chunks=len(chunks),eligible_index_chunks=len(chunks)-sum(excluded.values()),
        lexical_normalization='Remove Unicode whitespace; compare overlapping exact12character shingles; no stemming, paraphrase or embeddings.',
        limitations='Shared12character text may be boilerplate, cross-references or materially different versions. No new human equivalence/applicability judgments. Strict reference misses cannot prove semantic irrelevance.',
        summaries=summaries))
    print(json.dumps({'excluded':dict(excluded),'summary':summaries,'top_documents':docs[:6]},ensure_ascii=False))


if __name__=='__main__':main()
