"""Append source-bound table retrieval to an existing packed RAG context."""
from src.generation.evidence_retention import extend_retained_context


def augment_with_table_evidence(question, context, table_index, counter, *,
                                balanced=True, max_context_tokens=6000, max_new_sources=8):
    hits = table_index.search(question, question['query'], k=24, committee='审计', balanced=balanced)
    updated, audit = extend_retained_context(question, context, hits, counter,
        max_context_tokens=max_context_tokens, max_new_sources=max_new_sources)
    audit['table_retrieval'] = dict(balanced_categories=balanced,
        committee='审计', company=question['stock_code'], report_year=question['report_year'],
        candidate_ids=[c.chunk_id for c,_ in hits], model_calls=0,
        candidate_scores='FTS5 BM25, with optional fixed category round-robin ordering')
    return updated, audit
