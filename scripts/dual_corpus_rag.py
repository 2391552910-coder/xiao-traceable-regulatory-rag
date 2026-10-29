"""Run a source-addressable RAG query over uploaded annual and law documents.

The annual and regulation manifests describe files already imported by the
operator. No network retrieval is performed by this command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import ROOT, load_config
from src.pipeline import (build_dual_corpus_index, generate_dual_corpus_answer,
                          load_dual_corpus_index, make_llm)
from src.retrieval.index_artifact import save_index_artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annual-manifest",
                        help="Identity-checked source_manifest.csv from annual PDF import")
    parser.add_argument("--regulation-dir", default="data/knowledge_base",
                        help="Directory containing metadata-prefixed regulation .txt files")
    parser.add_argument("--regulation-manifest",
                        help="Optional hash-bound source manifest for regulation PDF/DOCX files")
    parser.add_argument("--regulation-manifest-only", action="store_true",
                        help="Use only the supplied regulation manifest, excluding the legacy TXT directory")
    parser.add_argument("--annual-ocr-run-dir",
                        help="Optional hash-sealed OCR sidecar run for pages without a PDF text layer")
    parser.add_argument("--query", required=True, help="User's evaluation question")
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--report-year", type=int, required=True)
    parser.add_argument("--dimension", default="主体自律评价")
    parser.add_argument("--annual-top-k", type=int, default=5)
    parser.add_argument("--regulation-top-k", type=int, default=5)
    parser.add_argument("--temporal-filter", action="store_true",
                        help="Apply declared-interval filtering before regulation top-k")
    parser.add_argument("--target-date", help="Explicit event date already in the query, YYYY-MM-DD")
    parser.add_argument("--target-date-role", choices=("company_event_date",),
                        help="Declare the date as the company event date")
    parser.add_argument("--unknown-temporal", choices=("retain", "exclude"), default="retain",
                        help="Treatment of unknown intervals when filtering; default retain")
    parser.add_argument("--annual-limit", type=int,
                        help="Optional small pilot cap; omit for the complete manifest")
    parser.add_argument("--annual-pages",
                        help="Optional comma-separated 1-based physical PDF pages to scan (e.g. 2,9)")
    parser.add_argument("--chunk-chars", type=int, default=1200)
    parser.add_argument("--overlap-chars", type=int, default=160)
    parser.add_argument('--regulation-file-strategy', choices=('page_window', 'mapped_structure', 'mapped_window'),
                        default='page_window')
    parser.add_argument("--config", help="YAML config path; defaults to configs/default.yaml")
    parser.add_argument("--require-cuda", action="store_true",
                        help="Reject local neural-model CPU configurations before parsing inputs")
    generation_mode = parser.add_mutually_exclusive_group()
    generation_mode.add_argument("--mock", action="store_true",
                                 help="Use the clearly labeled deterministic mock generator")
    generation_mode.add_argument("--real-llm", action="store_true",
                                 help="Use the configured real generation API")
    parser.add_argument("--no-reranker", action="store_true")
    parser.add_argument("--save-index-dir",
                        help="Save verified chunks and document vectors to a new reusable directory")
    parser.add_argument("--load-index-dir",
                        help="Reuse a hash-verified index without reading source PDFs or re-embedding")
    parser.add_argument("--expected-index-manifest-sha256",
                        help="Optional trusted SHA256 of index_manifest.json; checked before parsing it")
    parser.add_argument("--out-dir", required=True, help="New, non-existing results directory")
    args = parser.parse_args()

    if not args.temporal_filter and (args.target_date is not None or args.target_date_role is not None
                                     or args.unknown_temporal != 'retain'):
        parser.error('Date and unknown-interval options require --temporal-filter')
    if args.temporal_filter:
        from src.data.declared_time import bind_public_target_date
        try:
            bind_public_target_date({'question': {'query': args.query}}, args.target_date,
                                    role=args.target_date_role)
        except ValueError as error:
            parser.error(str(error))

    if args.load_index_dir and args.save_index_dir:
        parser.error("--load-index-dir and --save-index-dir cannot be used together")
    if args.regulation_file_strategy != 'page_window' and (args.load_index_dir or not args.regulation_manifest):
        parser.error('A mapped file strategy requires a new build and a regulation file manifest')
    if args.expected_index_manifest_sha256 and not args.load_index_dir:
        parser.error("--expected-index-manifest-sha256 requires --load-index-dir")
    if args.load_index_dir and (args.annual_manifest or args.regulation_manifest
                                or args.annual_ocr_run_dir):
        parser.error("--load-index-dir cannot be combined with source manifests or OCR inputs")
    if not args.load_index_dir and not args.annual_manifest:
        parser.error("--annual-manifest is required when building an index")
    if args.regulation_manifest_only and (not args.regulation_manifest or args.load_index_dir):
        parser.error("--regulation-manifest-only requires a source regulation manifest and a new index build")

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=False)

    cfg = load_config(args.config)
    if args.require_cuda:
        ret_cfg = cfg["retrieval"]
        rr_cfg = ret_cfg.get("reranker") or {}
        if ret_cfg["embedding_backend"] in ("qwen", "bge"):
            from src.retrieval.runtime import model_load_options
            if not str(ret_cfg.get("embedding_device", "cuda")).startswith("cuda"):
                raise ValueError("GPU entry point rejects a CPU embedding configuration")
            model_load_options(ret_cfg.get("embedding_device", "cuda"))
        if rr_cfg.get("enabled") and not args.no_reranker and not rr_cfg.get("url"):
            if not str(rr_cfg.get("device", "cuda")).startswith("cuda"):
                raise ValueError("GPU entry point rejects a CPU reranker configuration")
    page_numbers = ({int(value.strip()) for value in args.annual_pages.split(",") if value.strip()}
                    if args.annual_pages else None)
    cfg["retrieval"]["reranker"]["enabled"] = (
        cfg["retrieval"].get("reranker", {}).get("enabled", False)
        and not args.no_reranker
    )
    if args.load_index_dir:
        chunks, dual, provenance = load_dual_corpus_index(
            cfg, args.load_index_dir,
            include_reranker=not args.no_reranker,
            expected_manifest_sha256=args.expected_index_manifest_sha256)
    else:
        chunks, dual, provenance = build_dual_corpus_index(
            cfg, args.annual_manifest, args.regulation_dir,
            regulation_manifest=args.regulation_manifest,
            include_legacy_regulations=not args.regulation_manifest_only,
            annual_ocr_run_dir=args.annual_ocr_run_dir,
            annual_limit=args.annual_limit,
            annual_page_numbers=page_numbers,
            annual_chunk_chars=args.chunk_chars,
            annual_overlap_chars=args.overlap_chars,
            include_reranker=not args.no_reranker,
            regulation_file_strategy=args.regulation_file_strategy,
        )
        if args.save_index_dir:
            saved = save_index_artifact(
                args.save_index_dir, chunks, dual.retriever.dense._matrix,
                dual.retriever.dense.encoding_metadata, provenance)
            provenance["index_artifact"] = {
                "directory": str((ROOT / args.save_index_dir).resolve())
                if not Path(args.save_index_dir).is_absolute()
                else str(Path(args.save_index_dir).resolve()),
                "manifest_sha256": saved["manifest_sha256"],
                "format_version": saved["format_version"],
                "index_reused": False,
            }
    mock_override = True if args.mock else False if args.real_llm else None
    llm = make_llm(cfg, mock=mock_override)
    if not llm.mock and not cfg["llm"].get("api_key"):
        raise ValueError("Real generation requires LLM_API_KEY; no request was made")
    from src.generation.evaluator import Evaluator
    result = generate_dual_corpus_answer(
        dual, Evaluator(llm), query=args.query, stock_name=args.company_name,
        stock_code=args.stock_code, report_year=args.report_year,
        dimension_name=args.dimension, annual_top_k=args.annual_top_k,
        regulation_top_k=args.regulation_top_k, temporal_filter=args.temporal_filter,
        target_date=args.target_date, target_date_role=args.target_date_role,
        unknown_temporal=args.unknown_temporal)
    result["generator"] = {"model": llm.model, "mock": llm.mock,
                           "temperature": llm.temperature}
    result_path = out_dir / "answer_and_sources.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    output_sha = hashlib.sha256(result_path.read_bytes()).hexdigest()
    run = {
        "status": "completed_mock" if llm.mock else "completed_real_generation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "query": args.query,
        "stock_code": args.stock_code,
        "report_year": args.report_year,
        "retrieval_model_backend": cfg["retrieval"]["embedding_backend"],
        "reranker_enabled": bool(cfg["retrieval"]["reranker"].get("enabled")),
        "generation_model": llm.model,
        "generation_temperature": llm.temperature,
        "generation_mock": llm.mock,
        "index_provenance": provenance,
        "indexed_chunk_count": len(chunks),
        "annual_hit_count": len(result["retrieved_evidence"]["annual_reports"]),
        "regulation_hit_count": len(result["retrieved_evidence"]["regulations"]),
        "output_file": result_path.name,
        "output_sha256": output_sha,
        "semantic_support_verified": False,
        "legal_applicability_verified": False,
    }
    (out_dir / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
    print(json.dumps(run, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
