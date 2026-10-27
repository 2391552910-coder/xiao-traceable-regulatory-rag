"""
端到端流水线：知识库构建 → 检索 → 评价生成 → 证据对齐 → 评测汇总
"""
from pathlib import Path

from src.config import load_config
from src.data.clause_splitter import split_document
from src.data.document_corpora import (DualCorpusRetriever,
                                       load_annual_report_chunks,
                                       load_regulation_file_chunks,
                                       load_regulation_chunks)
from src.data.knowledge_loader import load_documents
from src.generation.llm_client import LLMClient
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.index_artifact import (encoder_identity, expected_encoder_identity,
                                          load_index_artifact)
from src.retrieval.router import DimensionRoutedRetriever


def build_knowledge_index(cfg: dict, chunking: str | None = None):
    """加载语料并按指定策略切分，构建混合检索器"""
    kb_cfg = cfg["knowledge_base"]
    strategy = chunking or kb_cfg["chunking"]
    docs = load_documents(kb_cfg["path"])
    chunks = []
    for doc in docs:
        chunks.extend(split_document(doc, strategy=strategy,
                                     window_size=kb_cfg["window_size"],
                                     window_overlap=kb_cfg["window_overlap"]))
    ret_cfg = cfg["retrieval"]
    reranker = None
    rr_cfg = ret_cfg.get("reranker") or {}
    if rr_cfg.get("enabled"):
        if rr_cfg.get("url"):  # 远端重排服务（Xinference / vLLM / TEI 兼容）
            from src.retrieval.reranker import APIReranker
            reranker = APIReranker(base_url=rr_cfg["url"],
                                   model_name=rr_cfg.get("model", "Qwen3-Reranker-0.6B"),
                                   api_key=rr_cfg.get("api_key", ""),
                                   batch_size=rr_cfg.get("batch_size", 1))
        else:
            from src.retrieval.reranker import Reranker
            reranker = Reranker(model_name=rr_cfg.get("model", "Qwen/Qwen3-Reranker-0.6B"),
                                device=rr_cfg.get("device", "cuda"),
                                dtype=rr_cfg.get("dtype", "float16"),
                                max_length=rr_cfg.get("max_length", 3072),
                                batch_size=rr_cfg.get("batch_size", 1),
                                revision=rr_cfg.get("revision"),
                                instruction=rr_cfg.get("instruction"),
                                local_files_only=rr_cfg.get("local_files_only", False))
    retriever = HybridRetriever(
        chunks, vector_weight=ret_cfg["vector_weight"],
        reranker=reranker,
        rerank_pool_factor=rr_cfg.get("pool_factor", 4),
        fusion=ret_cfg.get("fusion", "weighted"),
        rrf_k=ret_cfg.get("rrf_k", 60),
        backend=ret_cfg["embedding_backend"],
        model_name=ret_cfg["embedding_model"],
        device=ret_cfg.get("embedding_device", "cuda"),
        dtype=ret_cfg.get("embedding_dtype"),
        base_url=ret_cfg.get("embedding_base_url", ""),
        api_key=ret_cfg.get("embedding_api_key", ""),
        batch_size=ret_cfg.get("embedding_batch_size", 32),
        query_prompt=ret_cfg.get("embedding_query_prompt", ""),
        max_seq_length=ret_cfg.get("embedding_max_seq_length"),
        revision=ret_cfg.get("embedding_revision"),
        local_files_only=ret_cfg.get("embedding_local_files_only", False),
    )
    return chunks, retriever


def build_dual_corpus_index(cfg: dict, annual_manifest: str,
                            regulation_dir: str | None = None, *,
                            regulation_manifest: str | None = None,
                            include_legacy_regulations: bool = True,
                            annual_ocr_run_dir: str | None = None,
                            annual_limit: int | None = None,
                            annual_page_numbers: set[int] | None = None,
                            annual_chunk_chars: int = 1200,
                            annual_overlap_chars: int = 160,
                            chunking: str | None = None,
                            include_reranker: bool = True,
                            document_vectors=None,
                            regulation_file_strategy: str = 'page_window'):
    """Build one shared vector index and two independently scoped corpora.

    ``annual_manifest`` is the verified source manifest produced by the
    recovery/import flow. ``regulation_dir`` defaults to the configured
    knowledge-base directory and only TYPE=regulation documents are included.
    Keeping a shared encoder/index avoids loading a second embedding model,
    while every query is still ranked independently inside each corpus pool.
    """
    from src.data.page_mapped_chunks import STRATEGIES
    if regulation_file_strategy not in STRATEGIES or (regulation_file_strategy != 'page_window' and not regulation_manifest):
        raise ValueError('Mapped regulation strategy requires a regulation file manifest')
    kb_cfg = cfg["knowledge_base"]
    regulation_dir = regulation_dir or kb_cfg["path"]
    annual_chunks, annual_report = load_annual_report_chunks(
        annual_manifest, chunk_chars=annual_chunk_chars,
        overlap_chars=annual_overlap_chars, page_numbers=annual_page_numbers,
        ocr_run_dir=annual_ocr_run_dir,
        limit=annual_limit)
    legal_chunks, legal_report = [], {"document_count": 0, "chunk_count": 0,
                                      "source_directory": str(regulation_dir)}
    if include_legacy_regulations and any(Path(regulation_dir).glob("*.txt")):
        legal_chunks, legal_report = load_regulation_chunks(
            regulation_dir, strategy=chunking or kb_cfg["chunking"],
            window_size=kb_cfg["window_size"],
            window_overlap=kb_cfg["window_overlap"])
    if regulation_manifest:
        if regulation_file_strategy == 'page_window':
            file_chunks, file_report = load_regulation_file_chunks(regulation_manifest)
        else:
            from src.data.page_mapped_chunks import load_mapped_regulation_file_chunks
            file_chunks, file_report = load_mapped_regulation_file_chunks(regulation_manifest,
                strategy=regulation_file_strategy)
        legal_chunks.extend(file_chunks)
        report_key = ("uploaded_pdf_manifest" if file_report["source_formats"] == ["pdf"]
                      else "uploaded_file_manifest")
        legal_report[report_key] = file_report
        legal_report["document_count"] += file_report["document_count"]
        legal_report["chunk_count"] += file_report["chunk_count"]
    legal_report["legacy_directory_included"] = include_legacy_regulations
    if not legal_chunks:
        raise ValueError("No searchable regulation text, PDFs or DOCX files were supplied")
    chunks = annual_chunks + legal_chunks

    ret_cfg = cfg["retrieval"]
    rr_cfg = ret_cfg.get("reranker") or {}
    reranker = None
    if include_reranker and rr_cfg.get("enabled"):
        if rr_cfg.get("url"):
            from src.retrieval.reranker import APIReranker
            reranker = APIReranker(base_url=rr_cfg["url"],
                                   model_name=rr_cfg.get("model", "Qwen3-Reranker-0.6B"),
                                   api_key=rr_cfg.get("api_key", ""),
                                   batch_size=rr_cfg.get("batch_size", 1))
        else:
            from src.retrieval.reranker import Reranker
            reranker = Reranker(model_name=rr_cfg.get("model", "Qwen/Qwen3-Reranker-0.6B"),
                                device=rr_cfg.get("device", "cuda"),
                                dtype=rr_cfg.get("dtype", "float16"),
                                max_length=rr_cfg.get("max_length", 3072),
                                batch_size=rr_cfg.get("batch_size", 1),
                                revision=rr_cfg.get("revision"),
                                instruction=rr_cfg.get("instruction"),
                                local_files_only=rr_cfg.get("local_files_only", False))

    retriever = HybridRetriever(
        chunks, vector_weight=ret_cfg["vector_weight"], reranker=reranker,
        rerank_pool_factor=rr_cfg.get("pool_factor", 4),
        fusion=ret_cfg.get("fusion", "weighted"), rrf_k=ret_cfg.get("rrf_k", 60),
        backend=ret_cfg["embedding_backend"], model_name=ret_cfg["embedding_model"],
        device=ret_cfg.get("embedding_device", "cuda"),
        dtype=ret_cfg.get("embedding_dtype"),
        base_url=ret_cfg.get("embedding_base_url", ""),
        api_key=ret_cfg.get("embedding_api_key", ""),
        batch_size=ret_cfg.get("embedding_batch_size", 32),
        query_prompt=ret_cfg.get("embedding_query_prompt", ""),
        max_seq_length=ret_cfg.get("embedding_max_seq_length"),
        revision=ret_cfg.get("embedding_revision"),
        local_files_only=ret_cfg.get("embedding_local_files_only", False),
        document_vectors=document_vectors)
    dual = DualCorpusRetriever(retriever, chunks)
    provenance = {"annual_reports": annual_report, "annual_ocr_run_dir": annual_ocr_run_dir,
                  "regulations": legal_report,
                  "index_chunk_count": len(chunks),
                  "retrieval_scopes": ["annual_report", "regulation"],
                  "embedding": retriever.dense.encoding_metadata,
                  "chunking": {"annual_report": {"strategy": "page_window",
                                                  "chunk_chars": annual_chunk_chars,
                                                  "overlap_chars": annual_overlap_chars,
                                                  "selected_physical_pages": sorted(annual_page_numbers)
                                                  if annual_page_numbers is not None else "all"},
                               "regulations": {"strategy": chunking or kb_cfg["chunking"],
                                               "window_size": kb_cfg["window_size"],
                                               "window_overlap": kb_cfg["window_overlap"]}}}
    return chunks, dual, provenance


def load_dual_corpus_index(cfg: dict, artifact_dir: str, *,
                           include_reranker: bool = True,
                           expected_manifest_sha256: str | None = None):
    """Load a hash-verified index without parsing PDFs or re-embedding documents."""
    chunks, vectors, artifact = load_index_artifact(
        artifact_dir, expected_encoder=expected_encoder_identity(cfg),
        expected_manifest_sha256=expected_manifest_sha256)
    retrieval = cfg["retrieval"]
    reranker_cfg = retrieval.get("reranker") or {}
    reranker = None
    if include_reranker and reranker_cfg.get("enabled"):
        if reranker_cfg.get("url"):
            from src.retrieval.reranker import APIReranker
            reranker = APIReranker(
                base_url=reranker_cfg["url"],
                model_name=reranker_cfg.get("model", "Qwen3-Reranker-0.6B"),
                api_key=reranker_cfg.get("api_key", ""),
                batch_size=reranker_cfg.get("batch_size", 1))
        else:
            from src.retrieval.reranker import Reranker
            reranker = Reranker(
                model_name=reranker_cfg.get("model", "Qwen/Qwen3-Reranker-0.6B"),
                device=reranker_cfg.get("device", "cuda"),
                dtype=reranker_cfg.get("dtype", "float16"),
                max_length=reranker_cfg.get("max_length", 3072),
                batch_size=reranker_cfg.get("batch_size", 1),
                revision=reranker_cfg.get("revision"),
                instruction=reranker_cfg.get("instruction"),
                local_files_only=reranker_cfg.get("local_files_only", False))
    retriever = HybridRetriever(
        chunks, vector_weight=retrieval["vector_weight"], reranker=reranker,
        rerank_pool_factor=reranker_cfg.get("pool_factor", 4),
        fusion=retrieval.get("fusion", "weighted"), rrf_k=retrieval.get("rrf_k", 60),
        backend=retrieval["embedding_backend"], model_name=retrieval["embedding_model"],
        device=retrieval.get("embedding_device", "cuda"),
        dtype=retrieval.get("embedding_dtype"),
        base_url=retrieval.get("embedding_base_url", ""),
        api_key=retrieval.get("embedding_api_key", ""),
        batch_size=retrieval.get("embedding_batch_size", 32),
        query_prompt=retrieval.get("embedding_query_prompt", ""),
        max_seq_length=retrieval.get("embedding_max_seq_length"),
        revision=retrieval.get("embedding_revision"),
        local_files_only=retrieval.get("embedding_local_files_only", False),
        document_vectors=vectors)
    loaded_identity = encoder_identity(retriever.dense.encoding_metadata)
    stored_identity = artifact["encoder_identity"]
    mismatches = [key for key, value in stored_identity.items()
                  if loaded_identity.get(key) != value]
    if mismatches:
        raise ValueError("Loaded model does not match saved document vectors: "
                         + ", ".join(sorted(mismatches)))
    dual = DualCorpusRetriever(retriever, chunks)
    provenance = dict(artifact.get("provenance", {}))
    provenance["index_artifact"] = {
        "directory": artifact["directory"],
        "manifest_sha256": artifact["manifest_sha256"],
        "format_version": artifact["format_version"],
        "index_reused": True,
        "source_inventory": artifact.get("source_inventory", []),
        "source_inventory_sha256": artifact.get("source_inventory_sha256"),
    }
    return chunks, dual, provenance


def make_llm(cfg: dict, mock: bool | None = None) -> LLMClient:
    llm_cfg = cfg["llm"]
    return LLMClient(base_url=llm_cfg["base_url"], api_key=llm_cfg["api_key"],
                     model=llm_cfg["model"], temperature=llm_cfg["temperature"],
                     mock=mock if mock is not None else llm_cfg["mock"])


def make_router(retriever: HybridRetriever) -> DimensionRoutedRetriever:
    return DimensionRoutedRetriever(retriever)


def generate_dual_corpus_answer(dual: DualCorpusRetriever, evaluator, *,
                               query: str, stock_name: str, stock_code: str,
                               report_year: int, dimension_name: str,
                               mode: str = "ours", annual_top_k: int = 5,
                               regulation_top_k: int = 5) -> dict:
    """Retrieve independently from both corpora, generate, and retain citations.

    Citation-ID resolution only confirms that an ID was actually supplied to
    the model. It does not certify semantic support or legal applicability.
    """
    hits = dual.search(query, annual_top_k=annual_top_k,
                       regulation_top_k=regulation_top_k,
                       stock_code=stock_code, report_year=report_year)
    annual_evidence = DualCorpusRetriever.format_evidence(
        hits["company_evidence"], prefix="A")
    regulation_evidence = DualCorpusRetriever.format_evidence(
        hits["regulation_evidence"], prefix="R")
    result = evaluator.evaluate(
        mode, stock_name, stock_code, report_year, dimension_name,
        regulations=regulation_evidence, annual_evidence=annual_evidence,
        query=query)
    result["llm_response_metadata"] = dict(
        getattr(evaluator.llm, "last_response_metadata", {}) or {})

    def source_record(evidence_id, chunk, score):
        return {
            "evidence_id": evidence_id,
            "corpus_type": chunk.meta.get("corpus_type"),
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.doc_id,
            "document_title": chunk.doc_title,
            "source": chunk.source,
            "score": float(score),
            "text": chunk.text,
            "source_pdf_sha256": chunk.meta.get("source_pdf_sha256"),
            "source_document_sha256": chunk.meta.get("source_document_sha256"),
            "source_file": chunk.meta.get("source_file"),
            "source_pdf_file": chunk.meta.get("source_pdf_file"),
            "source_start": chunk.meta.get("source_start"),
            "source_end": chunk.meta.get("source_end"),
            "raw_end": chunk.meta.get("raw_end"),
            "version_id": chunk.meta.get("version_id"),
            "page_text_sha256": chunk.meta.get("page_text_sha256"),
            "physical_pdf_page_1based": chunk.meta.get("physical_pdf_page_1based"),
            "page_text_char_start": chunk.meta.get("page_text_char_start"),
            "page_text_char_end": chunk.meta.get("page_text_char_end"),
            "report_year": chunk.meta.get("report_year"),
            "stock_code": chunk.meta.get("stock_code"),
            "publication_date": chunk.meta.get("publication_date"),
            "clause_no": chunk.clause_no,
            "effective_from": chunk.meta.get("effective_from"),
            "effective_to": chunk.meta.get("effective_to"),
            "applicability_status": chunk.meta.get("applicability_status"),
            # Preserve the full coordinate/OCR frame outside the model prompt.
            "meta": dict(chunk.meta),
        }

    records = {}
    for prefix, key in (("A", "company_evidence"), ("R", "regulation_evidence")):
        for index, (chunk, score) in enumerate(hits[key], start=1):
            evidence_id = f"{prefix}{index}"
            records[evidence_id] = source_record(evidence_id, chunk, score)
    result["query"] = query
    result["retrieved_evidence"] = {
        "annual_reports": [value for key, value in records.items() if key.startswith("A")],
        "regulations": [value for key, value in records.items() if key.startswith("R")],
    }
    result["resolved_citations"] = [
        {**audit, "source_record": records.get(audit["evidence_id"])}
        for audit in result.get("citation_id_audit", [])
        if audit.get("resolves_to_supplied_evidence")
    ]
    result["inline_resolved_citations"] = [
        {**audit, "source_record": records.get(audit["evidence_id"])}
        for audit in result.get("inline_citation_id_audit", [])
        if audit.get("resolves_to_supplied_evidence")
    ]
    result["semantic_support_verified"] = False
    result["legal_applicability_verified"] = False
    return result
