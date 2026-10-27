"""Prepare matched evidence once, then run API-only generation on any computer.

The commands are development tools, not a final-test freeze or quality approval.
Preparing reuses an existing index; generating never rebuilds or embeds documents.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import ROOT, load_config
from src.generation.comparison import (MODES, ContextBudget, audit_response_ids,
                                       canonical_sha256, prepare_comparison,
                                       public_question, text_sha256,
                                       validate_response_structure)
from src.generation.llm_client import LLMClient, parse_json
from src.generation.experiment_protocol import bind_generation_protocol, ProtocolViolation


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def save_run(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".tmp")
    write_json(temporary, payload)
    temporary.replace(path)


def safe_error(error: Exception, api_key: str) -> dict:
    message = str(error)
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    message = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[REDACTED]", message)
    return {"error_type": type(error).__name__, "error": message}


def read_questions(path: Path) -> list[dict]:
    rows = [public_question(json.loads(line)) for line in
            path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    ids = [row["question_id"] for row in rows]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Questions must be non-empty and question IDs unique")
    return rows


def prepare(args) -> dict:
    # Imports that may involve CUDA are confined to this command.
    from tokenizers import Tokenizer
    from src.pipeline import load_dual_corpus_index
    from scripts.run_real_generation_pilot import check_runtime

    cfg = load_config()
    runtime = check_runtime(cfg, args.no_reranker)
    questions = read_questions(Path(args.questions))
    tokenizer_path = Path(args.tokenizer_json).resolve()
    tokenizer_sha = file_sha256(tokenizer_path)
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    # Ignore any stored truncation/padding policy: reference budget counts full
    # rendered contexts, independent of model-inference sequence limits.
    tokenizer.no_truncation()
    tokenizer.no_padding()
    count_tokens = lambda value: len(tokenizer.encode(value, add_special_tokens=False).ids)
    out_dir = Path(args.out_dir).resolve()
    if out_dir.exists():
        raise FileExistsError(out_dir)
    _, dual, provenance = load_dual_corpus_index(
        cfg, args.index_dir, include_reranker=not args.no_reranker,
        expected_manifest_sha256=args.expected_index_manifest_sha256)
    budget = ContextBudget(args.annual_top_k, args.regulation_top_k,
                           args.max_context_tokens)
    out_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": "matched-generation-bundle-v1",
        "purpose": "engineering/development only; not frozen final-test supervision",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "questions_sha256": file_sha256(Path(args.questions)),
        "index_provenance": provenance,
        "declared_target_date": getattr(args, "declared_target_date", None),
        "declared_target_date_role": getattr(args, "declared_target_date_role", None),
        "runtime": runtime, "index_reused": True, "index_rebuilt": False,
        "reference_tokenizer": {"tokenizer_json_sha256": tokenizer_sha,
            "tokenizers_version": importlib.metadata.version("tokenizers"),
            "add_special_tokens": False, "truncation": False, "padding": False,
            "provider_tokenizer_verified": False},
        "implementation_sha256": {
            path.relative_to(ROOT).as_posix(): file_sha256(path)
            for path in (Path(__file__).resolve(), ROOT / "src/generation/comparison.py")},
        "question_files": [], "status": "preparing",
    }
    manifest_path = out_dir / "comparison_manifest.json"
    save_run(manifest_path, manifest)
    for question in questions:
        started = time.perf_counter()
        payload = prepare_comparison(dual, question, count_tokens, budget=budget,
                                    declared_target_date=getattr(args, "declared_target_date", None),
                                    declared_target_date_role=getattr(args, "declared_target_date_role", None))
        payload["retrieval_preparation_elapsed_seconds"] = time.perf_counter() - started
        path = out_dir / f"{question['question_id']}.json"
        write_json(path, payload)
        manifest["question_files"].append({"path": path.name,
            "sha256": file_sha256(path), "question_id": question["question_id"]})
        save_run(manifest_path, manifest)
    manifest["status"] = "prepared"
    manifest["question_count"] = len(questions)
    save_run(manifest_path, manifest)
    return {"status": "prepared", "out_dir": str(out_dir),
            "question_count": len(questions),
            "manifest_sha256": file_sha256(manifest_path)}


def read_prepared(directory: Path, expected_manifest_sha256: str) -> tuple[dict, list[dict]]:
    manifest_path = directory / "comparison_manifest.json"
    if file_sha256(manifest_path) != expected_manifest_sha256.lower():
        raise ValueError("Prepared bundle manifest SHA256 mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "matched-generation-bundle-v1" or \
            manifest.get("status") != "prepared":
        raise ValueError("Prepared comparison bundle is incomplete or unsupported")
    bundles, ids = [], set()
    for entry in manifest["question_files"]:
        path = (directory / entry["path"]).resolve()
        if path.parent != directory.resolve() or path.suffix != ".json":
            raise ValueError("Question path escapes the prepared bundle")
        if file_sha256(path) != entry["sha256"]:
            raise ValueError("Prepared question file SHA256 mismatch")
        bundle = json.loads(path.read_text(encoding="utf-8"))
        public = public_question(bundle["question"])
        query_id = public["question_id"]
        if query_id != entry["question_id"] or query_id in ids:
            raise ValueError("Prepared question ID mismatch or duplicate")
        ids.add(query_id)
        if set(bundle["modes"]) != set(MODES):
            raise ValueError("Comparison must include all four modes")
        for context in bundle["contexts"].values():
            if text_sha256(context["context"]) != context["context_sha256"] or \
                    canonical_sha256(context["source_records"]) != context["source_records_sha256"]:
                raise ValueError("Prepared context or source record hash mismatch")
        for mode in bundle["modes"].values():
            if text_sha256(mode["prompt"]) != mode["prompt_sha256"]:
                raise ValueError("Prepared prompt hash mismatch")
        if any(bundle["modes"][mode]["context_key"] != "dual" for mode in MODES[2:]):
            raise ValueError("Generic and role modes must reuse the same dual context")
        bundles.append(bundle)
    if not bundles or len(bundles) != manifest["question_count"]:
        raise ValueError("Prepared bundle question count mismatch")
    return manifest, bundles


def execute_units(bundles: list[dict], llm, out_dir: Path, *, repeats: int,
                  max_calls: int, seed: int = 42, api_key: str = "",
                  run_metadata: dict | None = None,
                  max_observed_tokens: int | None = None,
                  max_consecutive_failures: int = 3,
                  modes: list[str] | None = None, protocol_binding=None,
                  experiment_kind: str = 'comparison', declared_target_date: str | None = None,
                  declared_target_date_role: str | None = None) -> dict:
    """One recorded request per unit; preserve failed raw text and continue.

    Caller must disable SDK automatic retries. Provider-side upstream attempts
    and billing remain unobservable from this client-side call counter.
    No judge is called. ID resolution alone is not a support-quality score.
    """
    if repeats < 1:
        raise ValueError("repeats must be positive")
    if max_observed_tokens is not None and max_observed_tokens < 1:
        raise ValueError("max_observed_tokens must be positive")
    if max_consecutive_failures < 1:
        raise ValueError("max_consecutive_failures must be positive")
    selected_modes = list(MODES) if modes is None else list(modes)
    if (not selected_modes or any(mode not in MODES for mode in selected_modes)
            or len(selected_modes) != len(set(selected_modes))):
        raise ValueError("modes must be a non-empty, unique subset of supported comparison modes")
    if any(mode not in bundle.get("modes", {}) for bundle in bundles for mode in selected_modes):
        raise ValueError("Selected mode is missing from a prepared bundle")
    if experiment_kind not in ('comparison', 'robustness'):
        raise ValueError('Unsupported generation execution kind')
    if experiment_kind == 'robustness':
        from src.generation.robustness_execution import unit_inventory, execution_identity
        unit_inventory(bundles)
        if not set(selected_modes) <= set(MODES[2:]):
            raise ValueError('Robustness requires paired dual-source generic/role modes')
        def unit_metadata(bundle):
            return execution_identity(bundle)
    else:
        if any('_execution_unit' in b for b in bundles) or len({b['question']['question_id'] for b in bundles}) != len(bundles):
            raise ValueError('Ordinary comparison requires unique public questions without robustness unit metadata')
        def unit_metadata(bundle):
            return {}
    units = [(bundle, mode, repeat_id)
             for bundle in bundles for mode in selected_modes for repeat_id in range(1, repeats + 1)]
    if not units or len(units) > max_calls:
        raise ValueError(f"Planned requests {len(units)} exceed explicit budget {max_calls}")
    if protocol_binding:
        protocol_binding.check_execution(experiment_kind, bundles, selected_modes, repeats, max_calls,
            seed, max_observed_tokens, max_consecutive_failures, declared_target_date=declared_target_date,
            declared_target_date_role=declared_target_date_role)
    random.Random(seed).shuffle(units)
    out_dir.mkdir(parents=True, exist_ok=False)
    if protocol_binding:
        protocol_binding.persist(out_dir)
        run_metadata = {**(run_metadata or {}), **protocol_binding.metadata()}
    run = {**(run_metadata or {}),
           "status": "running", "purpose": (run_metadata or {}).get("purpose", "engineering/development comparison only"),
           "mock": bool(llm.mock), "randomization_seed": seed, "repeats": repeats,
           "selected_comparison_modes": selected_modes,
           "complete_four_mode_design": set(selected_modes) == set(MODES),
           "execution_kind": experiment_kind,
           "unique_public_question_count": len({b['question']['question_id'] for b in bundles}),
           "variants_are_not_independent_questions": experiment_kind == 'robustness',
           "client_calls_planned": len(units), "client_calls_attempted": 0,
           "max_client_calls": max_calls,
           "client_calls_returned": 0, "active_request": None,
           "request_journals": [],
           "observed_total_tokens": 0, "responses_with_unknown_usage": 0,
           "max_observed_tokens": max_observed_tokens,
           "token_budget_check": "after each response; last call can overshoot; not a monetary cap",
           "max_consecutive_failures": max_consecutive_failures,
           "concurrency": 1,
           "call_budget_scope": "client logical calls; provider-side attempts/billing unverified",
           "schedule": [{"question_id": bundle["question"]["question_id"],
                         "mode": mode, "repeat_id": repeat_id, **unit_metadata(bundle)}
                        for bundle, mode, repeat_id in units],
           "units": [], "semantic_support_verified": False,
           "legal_applicability_verified": False}
    run_path = out_dir / "comparison_run.json"
    journal_dir = out_dir / "request_journals"
    journal_dir.mkdir()
    save_run(run_path, run)
    consecutive_failures = 0
    for bundle, mode, repeat_id in units:
        if protocol_binding:
            try:
                protocol_binding.check('before', llm)
            except ProtocolViolation as error:
                run.update(stop_reason='generation_protocol_changed_before_request', protocol_error=str(error))
                break
        query_id = bundle["question"]["question_id"]
        execution = unit_metadata(bundle)
        output_id = execution.get('execution_unit_id', query_id)
        source = bundle["modes"][mode]
        context = bundle["contexts"][source["context_key"]]
        unit = {"question_id": query_id, "mode": mode, "repeat_id": repeat_id, **execution,
                "prompt": source["prompt"], "prompt_sha256": source["prompt_sha256"],
                "context_sha256": context["context_sha256"],
                "source_records_sha256": context["source_records_sha256"],
                "prompt_reference_tokens": source["prompt_reference_tokens"],
                "context_reference_tokens": context["reference_tokens"],
                "request_started_at_utc": datetime.now(timezone.utc).isoformat()}
        llm.last_response_metadata = {"mock": bool(llm.mock)}
        llm.last_response_text = None
        llm.last_raw_response = None
        llm.last_request = None
        started = time.perf_counter()
        run["client_calls_attempted"] += 1
        # Persist the logical-call boundary before entering the client. An
        # interrupted active request is not evidence of server receipt and must
        # never be silently retried or counted as a returned response.
        journal = {"status": "logical_call_started",
                   "sequence_1based": run["client_calls_attempted"],
                   "question_id": query_id, "mode": mode, "repeat_id": repeat_id, **execution,
                   "prompt_sha256": unit["prompt_sha256"],
                   "context_sha256": unit["context_sha256"],
                   "source_records_sha256": unit["source_records_sha256"],
                   "started_at_utc": unit["request_started_at_utc"],
                   "provider_receipt_confirmed": False,
                   "scope": "logical client call; upstream attempts/billing unknown"}
        journal_path = journal_dir / f"{output_id}__{mode}__repeat_{repeat_id:03d}.json"
        save_run(journal_path, journal)
        journal_entry = {"path": journal_path.relative_to(out_dir).as_posix(),
                         "sha256": file_sha256(journal_path),
                         "sequence_1based": run["client_calls_attempted"]}
        run["request_journals"].append(journal_entry)
        run["active_request"] = dict(journal_entry)
        save_run(run_path, run)
        try:
            raw = llm.chat(source["prompt"])
            unit["raw_response"] = raw
            if protocol_binding: protocol_binding.check('after', llm, source['prompt'])
            reason = (llm.last_response_metadata or {}).get("finish_reason")
            if (not llm.mock and reason != "stop") or reason in {"length", "content_filter", "tool_calls", "function_call"}:
                raise ValueError(f"Generation did not finish as an answer: {reason}")
            result = parse_json(raw)
            validate_response_structure(result)
            unit["response"] = result
            unit["citation_id_audit"] = audit_response_ids(result, context["source_records"])
            unit["status"] = "completed"
        except Exception as exc:
            if isinstance(exc, ProtocolViolation):
                run['stop_reason'] = 'generation_protocol_response_or_inputs_mismatch'
            unit["status"] = "failed"
            unit["raw_response"] = unit.get("raw_response", getattr(llm, "last_response_text", None))
            unit.update(safe_error(exc, api_key))
        unit["elapsed_seconds"] = time.perf_counter() - started
        unit["response_metadata"] = dict(llm.last_response_metadata or {})
        unit["raw_sdk_response"] = getattr(llm, "last_raw_response", None)
        unit["request_parameters"] = getattr(llm, "last_request", None)
        original = json.dumps(unit, ensure_ascii=False, sort_keys=True)
        redacted = original.replace(api_key, "[REDACTED]") if api_key else original
        redacted = re.sub(r"(?i)(bearer\s+)[^\s,;\"\\]+", r"\1[REDACTED]", redacted)
        unit = json.loads(redacted)
        unit["redaction_applied"] = redacted != original
        unit["original_record_sha256"] = hashlib.sha256(original.encode("utf-8")).hexdigest()
        path = out_dir / f"{output_id}__{mode}__repeat_{repeat_id:03d}.json"
        write_json(path, unit)
        run["units"].append({"question_id": query_id, "mode": mode, **execution,
            "repeat_id": repeat_id, "status": unit["status"],
            "path": path.name, "sha256": file_sha256(path)})
        run["client_calls_returned"] += 1
        journal.update(status="logical_call_returned",
                       returned_at_utc=datetime.now(timezone.utc).isoformat(),
                       response_file=path.name, response_sha256=file_sha256(path),
                       response_unit_status=unit["status"])
        save_run(journal_path, journal)
        journal_entry["sha256"] = file_sha256(journal_path)
        run["active_request"] = None
        observed = unit["response_metadata"].get("total_tokens")
        if isinstance(observed, int) and not isinstance(observed, bool) and observed >= 0:
            run["observed_total_tokens"] += observed
        else:
            run["responses_with_unknown_usage"] += 1
        consecutive_failures = consecutive_failures + 1 if unit["status"] == "failed" else 0
        stop_reason = run.get('stop_reason')
        if max_observed_tokens is not None:
            if run["responses_with_unknown_usage"]:
                stop_reason = "usage_unavailable_with_token_budget"
            elif run["observed_total_tokens"] >= max_observed_tokens:
                stop_reason = "observed_token_budget_reached"
        if consecutive_failures >= max_consecutive_failures:
            stop_reason = stop_reason or "consecutive_failure_limit_reached"
        if stop_reason and len(run["units"]) < len(units):
            run["stop_reason"] = stop_reason
            run["unattempted_units"] = len(units)-len(run["units"])
            break
        save_run(run_path, run)
    if protocol_binding:
        try: protocol_binding.check('before')
        except ProtocolViolation as error:
            run.update(stop_reason='generation_protocol_changed_during_run', protocol_error=str(error))
    run['unattempted_units'] = len(units) - len(run['units'])
    run["status"] = ("stopped_by_control" if run.get("stop_reason") else
                     "completed" if all(row["status"] == "completed" for row in run["units"])
                     else "completed_with_failures")
    run["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    run["observed_token_budget_overshoot"] = (max(run["observed_total_tokens"]-max_observed_tokens, 0)
                                              if max_observed_tokens is not None else None)
    save_run(run_path, run)
    return run


def generate(args) -> dict:
    manifest, bundles = read_prepared(Path(args.prepared_dir), args.expected_manifest_sha256)
    cfg = load_config()["llm"]
    temperature = cfg["temperature"] if args.temperature is None else args.temperature
    if (args.max_output_tokens < 1 or not math.isfinite(args.request_timeout_seconds)
            or args.request_timeout_seconds <= 0):
        raise ValueError("Output token limit and request timeout must be positive")
    if not math.isfinite(temperature) or not 0 <= temperature <= 2:
        raise ValueError("temperature must be finite and in [0, 2]")
    out_dir = Path(args.out_dir).resolve()
    binding = bind_generation_protocol(args, 'comparison', cfg, temperature,
        list(MODES) if getattr(args, 'modes', None) is None else args.modes,
        manifest, bundles, ROOT)
    if binding is False:
        return {'status': 'protocol_rejected_before_models_or_api', 'out_dir': str(out_dir), 'client_calls_attempted': 0}
    # The generation phase uses only the real API, and loads no embedding or
    # reranker model. No silent CPU inference fallback or mock fallback exists.
    llm = LLMClient(cfg["base_url"], cfg["api_key"], cfg["model"],
                    temperature=temperature, mock=False,
                    max_output_tokens=args.max_output_tokens)
    llm._client = llm._client.with_options(max_retries=0, timeout=args.request_timeout_seconds)
    metadata = {"prepared_manifest_sha256": args.expected_manifest_sha256.lower(),
                "reference_tokenizer": manifest["reference_tokenizer"],
                "generation_model": cfg["model"], "temperature": temperature,
                "max_output_tokens": args.max_output_tokens,
                "request_timeout_seconds": args.request_timeout_seconds,
                "full_sdk_responses_recorded": True,
                "generation_implementation_sha256": {
                    path.relative_to(ROOT).as_posix(): file_sha256(path)
                    for path in (Path(__file__).resolve(), ROOT / "src/generation/llm_client.py",
                                 ROOT / "src/generation/comparison.py")},
                "openai_sdk_version": importlib.metadata.version("openai"),
                "automatic_sdk_retries": 0}
    run = execute_units(bundles, llm, out_dir, repeats=args.repeats,
                        max_calls=args.max_calls, seed=args.seed, api_key=cfg["api_key"],
                        run_metadata=metadata, max_observed_tokens=args.max_observed_tokens,
                        max_consecutive_failures=args.max_consecutive_failures,
                        modes=getattr(args, "modes", None), protocol_binding=binding)
    return {"status": run["status"], "out_dir": str(out_dir),
            "client_calls_attempted": run["client_calls_attempted"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="GPU retrieval using a saved verified index")
    prep.add_argument("--questions", required=True)
    prep.add_argument("--index-dir", required=True)
    prep.add_argument("--expected-index-manifest-sha256", required=True)
    prep.add_argument("--tokenizer-json", required=True)
    prep.add_argument("--out-dir", required=True)
    prep.add_argument("--annual-top-k", type=int, default=5)
    prep.add_argument("--regulation-top-k", type=int, default=5)
    prep.add_argument("--max-context-tokens", type=int, default=6000)
    prep.add_argument("--no-reranker", action="store_true")
    prep.add_argument("--declared-target-date",
                      help="Use a full company event date already stated in every public query; filters only confirmed-out-of-interval rules")
    prep.add_argument("--declared-target-date-role", choices=("company_event_date",),
                      help="Explicitly declare that the query date is the underlying company event date")
    gen = commands.add_parser("generate", help="Real API calls from sealed evidence; no re-indexing")
    gen.add_argument("--prepared-dir", required=True)
    gen.add_argument("--expected-manifest-sha256", required=True)
    gen.add_argument("--out-dir", required=True)
    gen.add_argument("--repeats", type=int, default=3)
    gen.add_argument("--max-calls", type=int, required=True)
    gen.add_argument("--modes", nargs="+", choices=MODES,
                     help="Explicit mode subset for a limited development diagnostic; default runs all four")
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--temperature", type=float,
                     help="Explicit temperature override; recorded without changing .env")
    gen.add_argument("--max-output-tokens", type=int, default=4096)
    gen.add_argument("--request-timeout-seconds", type=float, default=120.0)
    gen.add_argument("--max-observed-tokens", type=int,
                     help="Stop between units after this observed usage; last call may overshoot")
    gen.add_argument("--max-consecutive-failures", type=int, default=3)
    gen.add_argument('--frozen-protocol')
    gen.add_argument('--frozen-protocol-sha256')
    args = parser.parse_args()
    result = prepare(args) if args.command == "prepare" else generate(args)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in {"prepared", "completed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
