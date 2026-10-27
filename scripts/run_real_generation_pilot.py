"""Run a small real-generation pilot over an existing or newly built dual index."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import ROOT, load_config
from src.generation.evaluator import Evaluator
from src.pipeline import (build_dual_corpus_index, generate_dual_corpus_answer,
                          load_dual_corpus_index, make_llm)
from src.retrieval.index_artifact import save_index_artifact
from src.retrieval.runtime import model_load_options


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_error(error: Exception, api_key: str) -> dict:
    message = str(error)
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    message = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[REDACTED]", message)
    return {"error_type": type(error).__name__, "error": message}


def write_run(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def load_questions(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    required = {"question_id", "company_name", "stock_code", "report_year",
                "dimension", "query"}
    if not rows or any(not required.issubset(row) for row in rows):
        raise ValueError(f"Pilot questions must contain: {', '.join(sorted(required))}")
    ids = [str(row["question_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Pilot question_id values must be unique")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]+", question_id) for question_id in ids):
        raise ValueError("question_id may contain only letters, digits, underscore, and hyphen")
    return rows


def check_runtime(config: dict, no_reranker: bool) -> dict:
    """Fail closed if configured local model inference cannot use CUDA."""
    retrieval = config["retrieval"]
    reranker_cfg = retrieval.get("reranker") or {}
    needs_cuda = retrieval["embedding_backend"] in {"qwen", "bge"}
    needs_cuda = needs_cuda or bool(
        reranker_cfg.get("enabled") and not no_reranker and not reranker_cfg.get("url"))
    info = {
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "cuda_required": needs_cuda,
    }
    if not needs_cuda:
        return info

    import torch

    info["torch_version"] = torch.__version__
    info["torch_cuda_build"] = torch.version.cuda
    info["cuda_available"] = torch.cuda.is_available()
    if not info["cuda_available"]:
        raise RuntimeError(
            "CUDA is required for configured local embedding/reranker inference; "
            f"Python {sys.executable} has torch={torch.__version__}, "
            f"torch CUDA build={torch.version.cuda}, but CUDA is unavailable")

    configured_models = []
    if retrieval["embedding_backend"] in {"qwen", "bge"}:
        configured_models.append((retrieval.get("embedding_device", "cuda"),
                                  retrieval.get("embedding_dtype")))
    if (reranker_cfg.get("enabled") and not no_reranker
            and not reranker_cfg.get("url")):
        configured_models.append((reranker_cfg.get("device", "cuda"),
                                   reranker_cfg.get("dtype")))
    for device_name, dtype in configured_models:
        if not str(device_name).startswith("cuda"):
            raise ValueError(f"Local model inference is configured for non-CUDA device: {device_name}")
        model_load_options(device_name, dtype)

    device = torch.device(configured_models[0][0])
    device_index = device.index if device.index is not None else torch.cuda.current_device()
    info["cuda_device_index"] = device_index
    info["cuda_device_name"] = torch.cuda.get_device_name(device_index)
    info["cuda_device_count"] = torch.cuda.device_count()
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", required=True, help="UTF-8 JSONL pilot question file")
    parser.add_argument("--out-dir", required=True,
                        help="New output directory; existing paths are never overwritten")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--build-and-save-index",
                       help="Build from local source manifests and save vectors to this new artifact dir")
    group.add_argument("--load-index-dir", help="Reuse a verified persistent dense index")
    parser.add_argument("--expected-index-manifest-sha256",
                        help="Optional trusted SHA256 of index_manifest.json; checked before parsing it")
    parser.add_argument("--annual-manifest")
    parser.add_argument("--annual-ocr-run-dir")
    parser.add_argument("--regulation-dir", default="data/knowledge_base")
    parser.add_argument("--regulation-manifest")
    parser.add_argument("--annual-chunk-chars", type=int, default=1200)
    parser.add_argument("--annual-overlap-chars", type=int, default=160)
    parser.add_argument("--no-reranker", action="store_true")
    args = parser.parse_args()

    questions_path = Path(args.questions)
    if not questions_path.is_absolute():
        questions_path = ROOT / questions_path
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    if out_dir.exists():
        raise FileExistsError(f"Pilot output directory already exists: {out_dir}")
    questions = load_questions(questions_path)
    cfg = load_config()
    if not cfg["llm"].get("api_key"):
        raise ValueError("LLM_API_KEY is empty; pilot did not start")
    if args.build_and_save_index and not args.annual_manifest:
        parser.error("--annual-manifest is required with --build-and-save-index")
    if args.load_index_dir and any((args.annual_manifest, args.annual_ocr_run_dir,
                                    args.regulation_manifest)):
        parser.error("Source manifests cannot be combined with --load-index-dir")
    if args.expected_index_manifest_sha256 and not args.load_index_dir:
        parser.error("--expected-index-manifest-sha256 requires --load-index-dir")

    retrieval = cfg["retrieval"]
    reranker_cfg = retrieval.get("reranker") or {}
    runtime_info = check_runtime(cfg, args.no_reranker)

    out_dir.mkdir(parents=True, exist_ok=False)
    cases_dir = out_dir / "cases"
    cases_dir.mkdir()
    started_at = datetime.now(timezone.utc)
    run = {
        "status": "running",
        "purpose": "engineering pilot; not a frozen or independently reviewed evaluation set",
        "created_at_utc": started_at.isoformat(),
        "questions_file": str(questions_path.resolve()),
        "questions_sha256": sha256(questions_path),
        "question_count": len(questions),
        "completed_count": 0,
        "generation_model": cfg["llm"]["model"],
        "generation_temperature": cfg["llm"]["temperature"],
        "generation_mock": False,
        "runtime": runtime_info,
        "embedding_model": retrieval["embedding_model"],
        "embedding_revision": retrieval.get("embedding_revision"),
        "embedding_dtype": retrieval.get("embedding_dtype"),
        "embedding_device": retrieval.get("embedding_device"),
        "reranker_enabled": bool(reranker_cfg.get("enabled") and not args.no_reranker),
        "annual_manifest": str((ROOT / args.annual_manifest).resolve())
        if args.annual_manifest and not Path(args.annual_manifest).is_absolute()
        else str(Path(args.annual_manifest).resolve()) if args.annual_manifest else None,
        "annual_ocr_run_dir": args.annual_ocr_run_dir,
        "errors": [],
        "cases": [],
    }
    run_path = out_dir / "pilot_run.json"
    write_run(run_path, run)
    wall_started = time.perf_counter()
    try:
        if args.load_index_dir:
            chunks, dual, provenance = load_dual_corpus_index(
                cfg, args.load_index_dir, include_reranker=not args.no_reranker,
                expected_manifest_sha256=args.expected_index_manifest_sha256)
            run["index_reused"] = True
        else:
            chunks, dual, provenance = build_dual_corpus_index(
                cfg, args.annual_manifest, args.regulation_dir,
                regulation_manifest=args.regulation_manifest,
                annual_ocr_run_dir=args.annual_ocr_run_dir,
                annual_chunk_chars=args.annual_chunk_chars,
                annual_overlap_chars=args.annual_overlap_chars,
                include_reranker=not args.no_reranker)
            saved = save_index_artifact(
                args.build_and_save_index, chunks, dual.retriever.dense._matrix,
                dual.retriever.dense.encoding_metadata, provenance)
            index_path = Path(args.build_and_save_index)
            if not index_path.is_absolute():
                index_path = ROOT / index_path
            run["index_reused"] = False
            run["index_artifact"] = {
                "directory": str(index_path.resolve()),
                "manifest_sha256": saved["manifest_sha256"],
                "format_version": saved["format_version"],
            }
        run["index_provenance"] = provenance
        run["indexed_chunk_count"] = len(chunks)
        write_run(run_path, run)

        llm = make_llm(cfg, mock=False)
        evaluator = Evaluator(llm)
        for question in questions:
            case_started = time.perf_counter()
            case_id = str(question["question_id"])
            try:
                result = generate_dual_corpus_answer(
                    dual, evaluator,
                    query=question["query"],
                    stock_name=question["company_name"],
                    stock_code=question["stock_code"],
                    report_year=int(question["report_year"]),
                    dimension_name=question["dimension"],
                    mode="ours")
                result["pilot_question"] = question
                case_path = cases_dir / f"{case_id}.json"
                write_run(case_path, result)
                summary = {
                    "question_id": case_id,
                    "status": "completed",
                    "elapsed_seconds": round(time.perf_counter() - case_started, 3),
                    "prompt_tokens": result["llm_response_metadata"].get("prompt_tokens"),
                    "completion_tokens": result["llm_response_metadata"].get("completion_tokens"),
                    "total_tokens": result["llm_response_metadata"].get("total_tokens"),
                    "output_file": str(case_path.relative_to(out_dir)).replace("\\", "/"),
                    "output_sha256": sha256(case_path),
                    "citation_id_audit": result.get("citation_id_audit", []),
                    "semantic_support_verified": False,
                    "legal_applicability_verified": False,
                }
            except Exception as exc:
                metadata = dict(getattr(llm, "last_response_metadata", {}) or {})
                failed_case = {
                    "pilot_question": question,
                    "llm_response_metadata": metadata,
                    "raw_response": getattr(llm, "last_response_text", None),
                    **safe_error(exc, str(cfg["llm"].get("api_key") or "")),
                }
                case_path = cases_dir / f"{case_id}.json"
                write_run(case_path, failed_case)
                summary = {
                    "question_id": case_id,
                    "status": "failed",
                    "elapsed_seconds": round(time.perf_counter() - case_started, 3),
                    "output_file": str(case_path.relative_to(out_dir)).replace("\\", "/"),
                    "output_sha256": sha256(case_path),
                    **safe_error(exc, str(cfg["llm"].get("api_key") or "")),
                }
            run["cases"].append(summary)
            run["completed_count"] = len(run["cases"])
            run["prompt_tokens_observed"] = sum(
                row.get("prompt_tokens") or 0 for row in run["cases"])
            run["completion_tokens_observed"] = sum(
                row.get("completion_tokens") or 0 for row in run["cases"])
            run["total_tokens_observed"] = sum(
                row.get("total_tokens") or 0 for row in run["cases"])
            write_run(run_path, run)

        run["status"] = ("completed_real_generation" if all(
            row["status"] == "completed" for row in run["cases"])
            else "completed_with_case_failures")
    except Exception as exc:
        run["status"] = "failed_before_all_questions_completed"
        run["failure"] = safe_error(exc, str(cfg["llm"].get("api_key") or ""))
    run["elapsed_seconds"] = round(time.perf_counter() - wall_started, 3)
    run["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_run(run_path, run)
    print(json.dumps({"status": run["status"], "question_count": len(questions),
                      "completed_count": run["completed_count"],
                      "indexed_chunk_count": run.get("indexed_chunk_count"),
                      "elapsed_seconds": run["elapsed_seconds"],
                      "out_dir": str(out_dir.resolve())}, ensure_ascii=False))
    return 0 if run["status"] == "completed_real_generation" else 1


if __name__ == "__main__":
    raise SystemExit(main())
