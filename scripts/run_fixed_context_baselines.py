"""Run supplemental development baselines against a hash-pinned saved context.

No neural retrieval, source downloads, automatic retries or final-test acceptance.
The CLI uses the configured generation model for its own generic check; this is
a self-check baseline, not an independent judge or an independent review.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.run_generation_comparison import file_sha256, read_prepared, save_run, safe_error
from src.config import ROOT, load_config
from src.generation.comparison import canonical_sha256, text_sha256
from src.generation.llm_client import LLMClient, parse_json
from src.generation.strong_baselines import (BASELINES, prepare_supplement,
    revision_prompt, validate_attribution, validate_generation, validate_verification,
    verification_prompt)
from src.generation.joint_verification import (JOINT_MODE, JOINT_TEMPLATE, JOINT_REVISION_NOTE,
    bind_public_target_date, joint_verification_prompt, joint_revision_prompt, validate_joint_verification)
from src.generation.supplementary_retrieval import (RETRIEVAL_METHODS, JOINT_RETRIEVE_MODE,
    extend_context, plan_supplement, reference_count, validate_context)
from src.generation.shared_drafts import VERIFICATION_MODES, read_saved_draft, read_shared_drafts
from src.generation.experiment_protocol import bind_generation_protocol, ProtocolViolation

API_ONLY_METHODS = BASELINES + (JOINT_MODE,)
AVAILABLE_METHODS = API_ONLY_METHODS + RETRIEVAL_METHODS


def now():
    return datetime.now(timezone.utc).isoformat()


def redact(value, secrets):
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, '[REDACTED]')
        return value
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: redact(item, secrets) for key, item in value.items()}
    return value


class ControlStop(RuntimeError):
    pass


class StageFailed(RuntimeError):
    pass


def execute_baselines(bundles, generator, verifier, out_dir: Path, *, max_calls: int,
                      repeats: int = 1, modes=None, seed: int = 42,
                      max_observed_tokens: int | None = None,
                      max_consecutive_failures: int = 1, secrets=(), metadata=None,
                      declared_target_date: str | None = None,
                      declared_target_date_role: str | None = None, supplemental_retriever=None,
                      reference_counter=None, max_new_sources: int = 2,
                      max_supplemental_calls: int | None = None, shared_drafts=None,
                      protocol_binding=None):
    selected = list(BASELINES if modes is None else modes)
    if not selected or len(selected) != len(set(selected)) or any(mode not in AVAILABLE_METHODS for mode in selected):
        raise ValueError('Select a nonempty unique subset of supplemental baselines')
    for name, value in [('max_calls', max_calls), ('repeats', repeats),
                        ('max_consecutive_failures', max_consecutive_failures)]:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(name + ' must be a positive integer')
    if max_observed_tokens is not None and (not isinstance(max_observed_tokens, int)
            or isinstance(max_observed_tokens, bool) or max_observed_tokens < 1):
        raise ValueError('max_observed_tokens must be a positive integer')
    payloads = [prepare_supplement(bundle) for bundle in bundles]
    for payload in payloads:
        bind_public_target_date(payload, declared_target_date, role=declared_target_date_role)
    if JOINT_MODE in selected or JOINT_RETRIEVE_MODE in selected:
        for payload in payloads:
            payload['template_sha256'].update(joint_verification=text_sha256(JOINT_TEMPLATE),
                joint_revision=text_sha256(JOINT_REVISION_NOTE))
    supplemental_bound = len(payloads) * repeats * sum(mode in RETRIEVAL_METHODS for mode in selected)
    if supplemental_bound:
        if not callable(supplemental_retriever) or not callable(reference_counter):
            raise ValueError('Retrieval methods need an explicit retriever and reference counter')
        if not isinstance(max_supplemental_calls, int) or isinstance(max_supplemental_calls, bool) \
                or max_supplemental_calls < supplemental_bound:
            raise ValueError('Worst-case supplemental searches exceed explicit retrieval budget')
        if not isinstance(max_new_sources, int) or isinstance(max_new_sources, bool) or not 1 <= max_new_sources <= 8:
            raise ValueError('max_new_sources must be in [1,8]')
        for payload, bundle in zip(payloads, bundles):
            validate_context(payload['context'])
            cap = bundle.get('budget', {}).get('max_reference_context_tokens')
            if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1 \
                    or reference_count(reference_counter, payload['context']['context']) > cap:
                raise ValueError('Retrieval requires the original valid reference-token budget')
            payload['supplement_budget'] = {'max_context_tokens': cap, 'max_new_sources': max_new_sources}
    ids = [item['question']['question_id'] for item in payloads]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Questions must be nonempty and unique')
    saved = {}
    if shared_drafts is not None:
        expected = {(qid, repeat) for qid in ids for repeat in range(1, repeats + 1)}
        if any(mode not in VERIFICATION_MODES for mode in selected) or set(shared_drafts) != expected:
            raise ValueError('Shared drafts require verification modes and exact question/repeat coverage')
        for payload in payloads:
            for repeat in range(1, repeats + 1):
                key = payload['question']['question_id'], repeat
                saved[key] = read_saved_draft(shared_drafts[key], payload, repeat)
    bound = len(payloads) * repeats * sum(1 if mode == BASELINES[0] else 2 if shared_drafts is not None else 3 for mode in selected)
    if bound > max_calls:
        raise ValueError('Worst-case stage calls exceed explicit budget')
    if protocol_binding:
        protocol_binding.check_execution('bounded_retrieval' if supplemental_bound else 'fixed_baselines',
            bundles, selected, repeats, max_calls, seed, max_observed_tokens, max_consecutive_failures,
            declared_target_date, max_supplemental_calls, max_new_sources,
            declared_target_date_role=declared_target_date_role)
    schedule = [(payload, mode, repeat) for payload in payloads for mode in selected
                for repeat in range(1, repeats + 1)]
    random.Random(seed).shuffle(schedule)
    out_dir.mkdir(parents=True, exist_ok=False)
    if protocol_binding:
        protocol_binding.persist(out_dir)
        metadata = {**(metadata or {}), **protocol_binding.metadata()}
    (out_dir / 'stages').mkdir()
    (out_dir / 'journals').mkdir()
    if supplemental_bound:
        (out_dir / 'supplemental').mkdir()
    shared_index = {}
    if saved:
        (out_dir / 'shared_drafts').mkdir()
        for (qid, repeat), (raw, checked) in saved.items():
            draft_path = out_dir / 'shared_drafts' / f'{qid}__draft_{repeat:03d}.json'
            draft_path.write_bytes(raw)
            shared_index[qid, repeat] = {'question_id': qid, 'repeat_id': repeat,
                'path': draft_path.relative_to(out_dir).as_posix(), 'sha256': file_sha256(draft_path),
                'body_sha256': checked['body_sha256'], 'upstream_model': checked['upstream_model'],
                'upstream_observed_total_tokens': checked['upstream_observed_total_tokens'],
                'upstream_mock_declared': checked['upstream_mock_declared'],
                'provenance': {name: shared_drafts[qid, repeat].get(name) for name in (
                    'package_manifest_sha256', 'source_run_sha256', 'origin_entry_path', 'source_mode')}}
    inputs = out_dir / 'inputs.json'
    input_record = {'payloads': payloads, 'payloads_sha256': canonical_sha256(payloads)}
    if shared_index:
        input_record['shared_drafts'] = list(shared_index.values())
    save_run(inputs, input_record)
    run = {**(metadata or {}), 'schema_version': 'fixed-context-baselines-run-v1',
        'status': 'running', 'purpose': (metadata or {}).get('purpose', 'development engineering; not frozen evaluation'),
        'input_file': inputs.name, 'input_sha256': file_sha256(inputs), 'selected_baselines': selected,
        'repeats': repeats, 'seed': seed, 'max_client_calls': max_calls,
        'worst_case_client_calls': bound, 'client_calls_attempted': 0, 'client_calls_returned': 0,
        'sdk_responses_saved': 0, 'active_request': None, 'stage_records': [], 'pipelines': [],
        'active_retrieval': None, 'supplemental_searches_attempted': 0, 'supplemental_searches_returned': 0,
        'supplemental_search_upper_bound': supplemental_bound, 'max_supplemental_calls': max_supplemental_calls,
        'supplemental_records': [], 'context_variants': [],
        'observed_total_tokens': 0, 'responses_with_unknown_usage': 0,
        'max_observed_tokens': max_observed_tokens, 'consecutive_failures': 0,
        'token_limit_scope': 'checked after each return; may overshoot; not a monetary cap',
        'revision_limit_per_pipeline': 1, 'verification_after_revision': False,
        'retrieval_or_model_loading_calls': None if supplemental_bound else 0,
        'retrieval_resource_scope': 'caller-supplied callback; see backend trace' if supplemental_bound else 'API-only',
        'concurrency': 1,
        'generator_and_verifier_same_client': generator is verifier,
        'different_generation_model_family_verified': False,
        'independent_human_review_completed': False, 'semantic_support_verified': False,
        'draft_policy': 'paired_saved_draft' if shared_index else 'independent_draft_calls',
        'shared_drafts': list(shared_index.values()),
        'upstream_draft_usage_included_in_observed_total_tokens': False,
        'upstream_draft_usage_scope': ('one saved initial draft per question/repeat; report once separately; no new draft API call'
                                     if shared_index else 'draft calls and usage observed within this run'),
        'legal_applicability_verified': False, 'accepted_as_gold': False, 'formal_metrics': None,
        'started_at_utc': now()}
    path = out_dir / 'baseline_run.json'
    save_run(path, redact(run, secrets))

    def stage(payload, pipeline, stage_name, prompt, client, validator, upstream=None):
        if run.get('stop_reason'):
            raise ControlStop(run['stop_reason'])
        if protocol_binding:
            try: protocol_binding.check('before', client)
            except ProtocolViolation as error: raise ControlStop(str(error)) from error
        if not inputs.is_file() or file_sha256(inputs) != run['input_sha256']:
            raise ControlStop('input_changed_before_stage')
        shared = pipeline.get('shared_draft')
        if shared and (not (out_dir / shared['path']).is_file() or file_sha256(out_dir / shared['path']) != shared['sha256']):
            raise ControlStop('shared_draft_changed_before_stage')
        variant = pipeline.get('supplemental_context')
        if variant and (not (out_dir / variant['path']).is_file() or file_sha256(out_dir / variant['path']) != variant['sha256']):
            raise ControlStop('supplemental_context_changed_before_stage')
        if run['client_calls_attempted'] >= max_calls:
            raise ControlStop('logical_call_budget_reached')
        stem = f"{pipeline['question_id']}__{pipeline['mode']}__{pipeline['repeat_id']:03d}__{stage_name}"
        record_path = out_dir / 'stages' / (stem + '.json')
        journal_path = out_dir / 'journals' / (stem + '.json')
        record = {'question_id': pipeline['question_id'], 'mode': pipeline['mode'],
            'repeat_id': pipeline['repeat_id'], 'stage': stage_name, 'prompt': prompt,
            'prompt_sha256': text_sha256(prompt), 'context_sha256': payload['context']['context_sha256'],
            'source_records_sha256': payload['context']['source_records_sha256'],
            'supplemental_context_variant': variant,
            'upstream_stage_sha256': upstream, 'started_at_utc': now()}
        run['client_calls_attempted'] += 1
        journal = {'status': 'logical_call_started', 'sequence_1based': run['client_calls_attempted'],
            **{key: record[key] for key in ('question_id', 'mode', 'repeat_id', 'stage',
                'prompt_sha256', 'context_sha256', 'source_records_sha256', 'upstream_stage_sha256')},
            'started_at_utc': record['started_at_utc'], 'provider_receipt_confirmed': False}
        # Persist the full exact prompt and logical boundary before entering the client.
        save_run(record_path, redact({**record, 'status': 'logical_call_started'}, secrets))
        save_run(journal_path, journal)
        run['active_request'] = {'journal': journal_path.relative_to(out_dir).as_posix(),
            'stage_file': record_path.relative_to(out_dir).as_posix()}
        save_run(path, redact(run, secrets))
        client.last_response_metadata = {'mock': bool(client.mock)}
        client.last_response_text = client.last_raw_response = client.last_request = None
        started = time.perf_counter()
        try:
            raw = client.chat(prompt)
            record['raw_response'] = raw
            if protocol_binding: protocol_binding.check('after', client, prompt)
            reason = (client.last_response_metadata or {}).get('finish_reason')
            if (not client.mock and reason != 'stop') or reason in {'length', 'content_filter', 'tool_calls', 'function_call'}:
                raise ValueError('Response did not finish with an answer: ' + str(reason))
            request = client.last_request
            if not client.mock and (not isinstance(request, dict)
                    or request.get('messages') != [{'role': 'user', 'content': prompt}]
                    or client.last_raw_response is None):
                raise ValueError('Exact local SDK request/response trace is missing')
            result = parse_json(raw)
            record['response'] = result
            record['validated'] = validator(result)
            record['status'] = 'completed'
        except Exception as exc:
            if isinstance(exc, ProtocolViolation): run['stop_reason'] = 'generation_protocol_response_or_inputs_mismatch'
            record['status'] = 'failed'
            record['raw_response'] = record.get('raw_response', client.last_response_text)
            record.update(safe_error(exc, ''))
        record['elapsed_seconds'] = time.perf_counter() - started
        record['response_metadata'] = dict(client.last_response_metadata or {})
        record['raw_sdk_response'] = client.last_raw_response
        request = client.last_request
        record['request_parameters'] = ({key: request[key] for key in
            ('model', 'messages', 'temperature', 'max_tokens') if key in request} if isinstance(request, dict) else None)
        record['original_record_sha256'] = canonical_sha256(record)
        cleaned = redact(record, secrets)
        cleaned['redaction_applied'] = cleaned != record
        save_run(record_path, cleaned)
        entry = {'path': record_path.relative_to(out_dir).as_posix(), 'sha256': file_sha256(record_path),
            'stage': stage_name, 'status': record['status'], 'question_id': pipeline['question_id'],
            'mode': pipeline['mode'], 'repeat_id': pipeline['repeat_id']}
        run['stage_records'].append(entry)
        pipeline['stages'].append(entry)
        run['client_calls_returned'] += 1
        run['sdk_responses_saved'] += client.last_raw_response is not None
        journal.update(status='logical_call_returned', stage_file=entry['path'],
            stage_sha256=entry['sha256'], response_status=record['status'], returned_at_utc=now())
        save_run(journal_path, journal)
        run['active_request'] = None
        usage = record['response_metadata'].get('total_tokens')
        if isinstance(usage, int) and not isinstance(usage, bool) and usage >= 0:
            run['observed_total_tokens'] += usage
        else:
            run['responses_with_unknown_usage'] += 1
        run['consecutive_failures'] = run['consecutive_failures'] + 1 if record['status'] == 'failed' else 0
        if max_observed_tokens is not None:
            if run['responses_with_unknown_usage']:
                run['stop_reason'] = 'usage_unavailable_with_token_limit'
            elif run['observed_total_tokens'] >= max_observed_tokens:
                run['stop_reason'] = 'observed_token_limit_reached'
        if run['consecutive_failures'] >= max_consecutive_failures:
            run.setdefault('stop_reason', 'consecutive_failure_limit_reached')
        save_run(path, redact(run, secrets))
        if record['status'] != 'completed':
            raise StageFailed(stage_name)
        return record, entry['sha256']

    def supplement(payload, pipeline, checks):
        if protocol_binding:
            try: protocol_binding.check('before')
            except ProtocolViolation as error: raise ControlStop(str(error)) from error
        plan = plan_supplement(payload, checks, joint=pipeline['mode'] == JOINT_RETRIEVE_MODE)
        pipeline['supplemental_plan'] = plan
        if not plan['search_needed']:
            return payload
        if len(plan['roles']) > max_new_sources:
            pipeline['supplemental_plan'] = {**plan, 'search_needed': False,
                'reason': 'source_quota_insufficient_for_requested_roles'}
            return payload
        if run.get('stop_reason'):
            raise ControlStop(run['stop_reason'])
        if run['supplemental_searches_attempted'] >= max_supplemental_calls:
            raise ControlStop('supplemental_call_budget_reached')
        request = {**plan, 'max_new_sources': max_new_sources}
        stem = f"{pipeline['question_id']}__{pipeline['mode']}__{pipeline['repeat_id']:03d}"
        record_path = out_dir / 'supplemental' / (stem + '_retrieval.json')
        record = {'status': 'supplemental_search_started', 'request': request,
            'started_at_utc': now(), 'parent_context_sha256': payload['context']['context_sha256']}
        save_run(record_path, redact(record, secrets))
        run['supplemental_searches_attempted'] += 1
        run['active_retrieval'] = {'path': record_path.relative_to(out_dir).as_posix()}
        save_run(path, redact(run, secrets))
        started = time.perf_counter()
        try:
            hits = supplemental_retriever(dict(request))
            if not isinstance(hits, list) or len(hits) > max_new_sources:
                raise ValueError('Supplemental callback must return a list within its source quota')
            record['returned_chunk_ids'] = [chunk.chunk_id for chunk, _ in hits]
            updated, extension = extend_context(payload, hits, reference_counter,
                max_context_tokens=payload['supplement_budget']['max_context_tokens'], max_new_sources=max_new_sources)
            context_path = out_dir / 'supplemental' / (stem + '_context.json')
            save_run(context_path, redact({'payload': updated, 'extension': extension}, secrets))
            variant = {'path': context_path.relative_to(out_dir).as_posix(), 'sha256': file_sha256(context_path)}
            pipeline['supplemental_context'] = variant
            run['context_variants'].append(variant)
            record.update(status='completed', context_variant=variant, extension=extension)
        except Exception as exc:
            record.update(status='failed', **safe_error(exc, ''))
            run['stop_reason'] = 'supplemental_retrieval_failed_no_retry'
        record.update(elapsed_seconds=time.perf_counter() - started, returned_at_utc=now())
        save_run(record_path, redact(record, secrets))
        run['supplemental_searches_returned'] += 1
        run['supplemental_records'].append({'path': record_path.relative_to(out_dir).as_posix(),
            'sha256': file_sha256(record_path), 'status': record['status']})
        run['active_retrieval'] = None
        save_run(path, redact(run, secrets))
        if record['status'] != 'completed':
            raise StageFailed('supplemental_retrieval')
        return updated

    for payload, mode, repeat in schedule:
        if run.get('stop_reason'):
            break
        pipeline = {'question_id': payload['question']['question_id'], 'mode': mode,
            'repeat_id': repeat, 'status': 'running', 'stages': [], 'revision_performed': False,
            'final_answer_reverified': False}
        run['pipelines'].append(pipeline)
        try:
            if mode == BASELINES[0]:
                output, _ = stage(payload, pipeline, 'attribution', payload['attribution_prompt'],
                    generator, lambda value: validate_attribution(value, payload))
            else:
                if shared_index:
                    shared = shared_index[payload['question']['question_id'], repeat]
                    pipeline['shared_draft'] = shared
                    shared_path = out_dir / shared['path']
                    if not shared_path.is_file() or file_sha256(shared_path) != shared['sha256']:
                        raise ControlStop('shared_draft_changed_before_stage')
                    draft = saved[payload['question']['question_id'], repeat][1]
                    draft_sha = shared['sha256']
                else:
                    draft, draft_sha = stage(payload, pipeline, 'draft', payload['generic_prompt'],
                        generator, lambda value: validate_generation(value, payload))
                body = draft['validated']['evaluation']
                is_joint = mode in (JOINT_MODE, JOINT_RETRIEVE_MODE)
                check_prompt = joint_verification_prompt(payload, body) if is_joint else verification_prompt(payload, body)
                check_validator = validate_joint_verification if is_joint else validate_verification
                check, check_sha = stage(payload, pipeline, 'verification', check_prompt,
                    verifier, lambda value: check_validator(value, payload, body), upstream=draft_sha)
                pipeline['model_check_summary'] = check['validated']
                if check['validated']['revision_needed']:
                    working = supplement(payload, pipeline, check['validated']) if mode in RETRIEVAL_METHODS else payload
                    revise_prompt = joint_revision_prompt if is_joint else revision_prompt
                    output, _ = stage(working, pipeline, 'revision', revise_prompt(working, body, check['validated']),
                        generator, lambda value: validate_generation(value, working), upstream=check_sha)
                    pipeline['revision_performed'] = True
                else:
                    output = draft
                    pipeline['revision_skip_reason'] = ('model_extracted_no_substantive_claims_not_verified' if
                        check['validated']['no_substantive_claims'] else 'all_extracted_claims_model_supported_not_verified')
            pipeline['final_evaluation'] = output['validated']['evaluation']
            pipeline['final_evaluation_sha256'] = text_sha256(pipeline['final_evaluation'])
            pipeline['status'] = 'completed'
        except ControlStop as exc:
            pipeline.update(status='stopped_by_control', stop_reason=str(exc))
            run.setdefault('stop_reason', str(exc))
        except StageFailed as exc:
            pipeline.update(status='failed', failed_stage=str(exc))
        save_run(path, redact(run, secrets))
    run['unattempted_pipelines'] = len(schedule) - len(run['pipelines'])
    run['status'] = ('stopped_by_control' if run.get('stop_reason') and
        (run['unattempted_pipelines'] or any(p['status'] != 'completed' for p in run['pipelines'])) else
        'completed' if all(p['status'] == 'completed' for p in run['pipelines']) else 'completed_with_failures')
    run['finished_at_utc'] = now()
    run['unused_client_call_budget'] = max_calls - run['client_calls_attempted']
    run['observed_token_limit_overshoot'] = max(0, run['observed_total_tokens'] - max_observed_tokens) if max_observed_tokens else None
    if not inputs.is_file() or file_sha256(inputs) != run['input_sha256']:
        run['status'] = 'input_changed_during_run'
    if any(not (out_dir / row['path']).is_file() or file_sha256(out_dir / row['path']) != row['sha256'] for row in run['context_variants']):
        run['status'] = 'supplemental_context_changed_during_run'
    if any(not (out_dir / row['path']).is_file() or file_sha256(out_dir / row['path']) != row['sha256'] for row in shared_index.values()):
        run['status'] = 'shared_draft_changed_during_run'
    if protocol_binding:
        try: protocol_binding.check('before')
        except ProtocolViolation as error:
            run.update(status='protocol_inputs_changed_during_run', protocol_error=str(error))
    save_run(path, redact(run, secrets))
    return run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-dir', required=True)
    parser.add_argument('--expected-manifest-sha256', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--max-calls', required=True, type=int)
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--modes', nargs='+', choices=API_ONLY_METHODS)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--max-output-tokens', type=int, default=4096)
    parser.add_argument('--max-observed-tokens', type=int)
    parser.add_argument('--request-timeout-seconds', type=float, default=120)
    parser.add_argument('--temperature', type=float)
    parser.add_argument('--declared-target-date', help='Full ISO date already present in every public question; not report year')
    parser.add_argument('--declared-target-date-role', choices=('company_event_date',),
                        help='Explicitly declare the public-query date as the underlying company event date')
    parser.add_argument('--shared-drafts-dir')
    parser.add_argument('--expected-shared-drafts-manifest-sha256')
    parser.add_argument('--frozen-protocol')
    parser.add_argument('--frozen-protocol-sha256')
    args = parser.parse_args(argv)
    if Path(args.out_dir).exists():
        parser.error('Output directory already exists')
    manifest, bundles = read_prepared(Path(args.prepared_dir), args.expected_manifest_sha256)
    if bool(args.shared_drafts_dir) != bool(args.expected_shared_drafts_manifest_sha256):
        parser.error('Shared draft path and trusted manifest SHA256 must be supplied together')
    if args.shared_drafts_dir and (not args.modes or any(m not in VERIFICATION_MODES for m in args.modes)):
        parser.error('Shared drafts need explicit verification modes')
    shared = read_shared_drafts(args.shared_drafts_dir, args.expected_shared_drafts_manifest_sha256,
        bundles, args.expected_manifest_sha256, args.repeats) if args.shared_drafts_dir else None
    cfg = load_config()['llm']
    temperature = cfg['temperature'] if args.temperature is None else args.temperature
    if args.max_output_tokens < 1 or not math.isfinite(args.request_timeout_seconds) or args.request_timeout_seconds <= 0 \
            or not math.isfinite(temperature) or not 0 <= temperature <= 2:
        parser.error('Invalid output-token, timeout or temperature control')
    binding = bind_generation_protocol(args, 'fixed_baselines', cfg, temperature,
        list(BASELINES) if args.modes is None else args.modes, manifest, bundles, ROOT, shared)
    if binding is False:
        print(json.dumps({'status': 'protocol_rejected_before_models_or_api', 'client_calls_attempted': 0}))
        return 1
    client = LLMClient(cfg['base_url'], cfg['api_key'], cfg['model'], temperature=temperature,
                       mock=False, max_output_tokens=args.max_output_tokens)
    client._client = client._client.with_options(max_retries=0, timeout=args.request_timeout_seconds)
    metadata = {'parent_prepared_manifest_sha256': args.expected_manifest_sha256.lower(),
        'shared_draft_package_manifest_sha256': args.expected_shared_drafts_manifest_sha256,
        'reference_tokenizer': manifest['reference_tokenizer'], 'generation_model': cfg['model'],
        'checker_model': cfg['model'], 'checker_relationship': 'same_model_self_check_not_independent_judge',
        'temperature': temperature, 'max_output_tokens': args.max_output_tokens,
        'request_timeout_seconds': args.request_timeout_seconds, 'automatic_sdk_retries': 0,
        'openai_sdk_version': importlib.metadata.version('openai'),
        'implementation_sha256': {name: file_sha256(ROOT / name) for name in [
            'scripts/run_fixed_context_baselines.py', 'src/generation/strong_baselines.py',
            'src/generation/joint_verification.py',
            'src/generation/supplementary_retrieval.py',
            'src/generation/shared_drafts.py',
            'scripts/run_generation_comparison.py', 'src/generation/comparison.py', 'src/generation/llm_client.py']}}
    run = execute_baselines(bundles, client, client, Path(args.out_dir).resolve(),
        max_calls=args.max_calls, repeats=args.repeats, modes=args.modes, seed=args.seed,
        max_observed_tokens=args.max_observed_tokens, secrets=(cfg['api_key'], cfg['base_url']), metadata=metadata,
        declared_target_date=args.declared_target_date,
        declared_target_date_role=args.declared_target_date_role,
        shared_drafts=shared, protocol_binding=binding)
    print(json.dumps({'status': run['status'], 'client_calls_attempted': run['client_calls_attempted'],
        'sdk_responses_saved': run['sdk_responses_saved'], 'formal_metrics': None}, ensure_ascii=False))
    return 0 if run['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
