"""Bind saved generation inputs before constructing API or CUDA clients."""
from __future__ import annotations

import importlib.metadata
import json
import platform
from pathlib import Path

from src.data.clause_splitter import Chunk
from src.data.evidence_sources import EvidenceSourceVerifier, local_path
from src.data.retrieval_target_release import day, resolve_target_reviews
from src.data.review_intake import file_sha256, read_csv
from src.data.retrieved_source_spans import RetrievedSourceBinder
from src.generation.comparison import (MODES, COMMON_PROMPT, NO_RAG_CONSTRAINT,
    GENERIC_CONSTRAINT, ROLE_CONSTRAINT, _pack_context, canonical_sha256, public_question, text_sha256)
from src.generation.strong_baselines import BASELINES
from src.retrieval.experiment_protocol import (check_exposure_crosswalk,
    recheck_protocol_guards)

FILES = ('scripts/run_generation_comparison.py', 'scripts/run_fixed_context_baselines.py',
    'scripts/run_robustness_generation.py', 'src/generation/robustness_execution.py',
    'src/generation/robustness.py',
    'src/data/pdf_text_frames.py',
    'src/data/declared_time.py',
    'src/metrics/span_retrieval.py',
    'src/retrieval/temporal.py',
    'src/retrieval/search_trace.py',
    'src/data/page_mapped_chunks.py', 'src/data/structural_splitter.py',
    'scripts/run_bounded_joint_rag.py', 'src/generation/experiment_protocol.py',
    'src/generation/comparison.py', 'src/generation/strong_baselines.py',
    'src/generation/shared_drafts.py', 'src/generation/joint_verification.py',
    'src/generation/supplementary_retrieval.py', 'src/generation/llm_client.py',
    'src/config.py', 'src/data/retrieved_source_spans.py', 'src/data/document_corpora.py',
    'src/data/evidence_sources.py', 'src/data/retrieval_target_release.py',
    'src/data/review_intake.py', 'src/retrieval/experiment_protocol.py',
    'src/retrieval/index_artifact.py', 'src/pipeline.py', 'src/retrieval/dense.py',
    'src/retrieval/reranker.py', 'src/retrieval/hybrid.py', 'src/retrieval/bm25.py')


class ProtocolViolation(ValueError):
    pass


def implementation_hashes(root):
    return {name: file_sha256(Path(root) / name) for name in FILES}


def runtime_fields(entrypoint, args, cfg, temperature, modes, bundles, shared):
    units = len(bundles) * args.repeats
    worst = units * sum(1 if entrypoint in ('comparison', 'robustness') or mode == BASELINES[0]
                        else 2 if shared is not None else 3 for mode in modes)
    return {'entrypoint': entrypoint, 'prepared_manifest_sha256': args.expected_manifest_sha256.lower(),
        'prepared_payloads_sha256': canonical_sha256(bundles),
        'requested_generation_model': cfg['model'], 'endpoint_sha256': text_sha256(cfg['base_url'].rstrip('/')),
        'temperature': temperature, 'max_output_tokens': args.max_output_tokens,
        'request_timeout_seconds': args.request_timeout_seconds, 'automatic_sdk_retries': 0,
        'methods': list(modes), 'repeats': args.repeats, 'randomization_seed': args.seed,
        'maximum_client_calls': args.max_calls, 'worst_case_client_calls': worst,
        'max_observed_tokens': args.max_observed_tokens,
        'max_consecutive_failures': getattr(args, 'max_consecutive_failures', 1),
        'declared_target_date': getattr(args, 'declared_target_date', None),
        'declared_target_date_role': getattr(args, 'declared_target_date_role', None),
        'shared_drafts_manifest_sha256': getattr(args, 'expected_shared_drafts_manifest_sha256', None),
        'supplemental_index_manifest_sha256': getattr(args, 'expected_index_manifest_sha256', None),
        'supplemental_tokenizer_sha256': getattr(args, 'expected_tokenizer_sha256', None),
        'maximum_supplemental_calls': getattr(args, 'max_supplemental_calls', None),
        'maximum_new_sources': getattr(args, 'max_new_sources', None)}


class GenerationBinding:
    def __init__(self, path, expected, runtime, manifest, bundles, args, root, shared):
        self.path, self.expected, self.root = Path(path).resolve(), expected, Path(root).resolve()
        self.raw = self.path.read_bytes()
        self.protocol = {}
        self.guards = [{'file': str(self.path), 'sha256': expected}]
        self.source_bindings = []
        self.report = {'status': 'protocol_rejected_before_models_or_api', 'issues': [],
            'protocol_sha256': expected, 'guards': self.guards, 'formal_metrics': None,
            'human_identity_authenticated': False, 'semantic_holdout_certified': False,
            'provider_model_identity_authenticated': False, 'monetary_spending_cap_enforced': False,
            'raw_review_labels_entered_model_inputs': False}
        self.runtime = runtime
        try:
            if file_sha256(self.path) != expected: raise ValueError('Generation protocol SHA256 mismatch')
            p = self.protocol = json.loads(self.raw)
            if not isinstance(p, dict): raise ValueError('Generation protocol must be a JSON object')
            self.control = p.get('protocol_kind') == 'engineering_control'
            if p.get('schema_version') != 'frozen-generation-protocol-v1' or p.get('protocol_kind') not in ('formal', 'engineering_control'):
                raise ValueError('Explicit generation protocol schema and kind are required')
            if p.get('status') != ('engineering_control_frozen' if self.control else 'externally_frozen'):
                raise ValueError('Generation protocol is still a draft or lacks external freeze declaration')
            if p.get('runtime') != runtime: raise ValueError('Generation runtime or call budgets differ from the protocol')
            if p.get('implementation_sha256') != implementation_hashes(root): raise ValueError('Generation implementation changed')
            if p.get('python_version') != platform.python_version(): raise ValueError('Python version differs')
            if runtime['maximum_client_calls'] < runtime['worst_case_client_calls']:
                raise ValueError('Worst-case logical requests exceed the registered call bound')
            packages = p.get('required_packages', {})
            required = {'pypdf', 'numpy', 'tokenizers'}
            if not self.control: required.add('openai')
            if runtime['entrypoint'] == 'bounded_retrieval': required |= {'torch', 'transformers', 'sentence-transformers'}
            if not required <= set(packages): raise ValueError('Required package versions are missing')
            for name, version in packages.items():
                if importlib.metadata.version(name) != version: raise ValueError('Package version differs: ' + name)
            self.guards.extend({'file': str(self.root / name), 'sha256': digest}
                               for name, digest in p['implementation_sha256'].items())
            frozen = day(p.get('frozen_at', ''))
            if not p.get('coordinator_id') or p['coordinator_id'] in ('R1', 'R2'):
                raise ValueError('Actual coordinator declaration is missing')
            if p.get('failure_policy') != 'retain_failed_unknown_and_unattempted_no_silent_retry':
                raise ValueError('Failure policy is not fixed')
            public = [public_question(b['question']) for b in bundles]
            if any(q != b['question'] for q, b in zip(public, bundles)):
                raise ValueError('Prepared questions contain nonpublic labels')
            hashes = {q['question_id']: canonical_sha256(q) for q in public}
            if p.get('question_sha256') != hashes: raise ValueError('Public question inventory differs')
            prepared = Path(args.prepared_dir).resolve()
            robustness = runtime['entrypoint'] == 'robustness'
            self.guards.append({'file': str(prepared / ('robustness_manifest.json' if robustness else 'comparison_manifest.json')),
                                'sha256': runtime['prepared_manifest_sha256']})
            for row in manifest['question_files']:
                self.guards.append({'file': str(prepared / row['path']), 'sha256': row['sha256']})
            tok_path, _ = self.linked_bytes(p['reference_tokenizer'])
            if p['reference_tokenizer']['sha256'] != manifest['reference_tokenizer']['tokenizer_json_sha256']:
                raise ValueError('Reference tokenizer differs from the prepared bundle')
            from tokenizers import Tokenizer
            tokenizer = Tokenizer.from_file(str(tok_path)); tokenizer.no_truncation(); tokenizer.no_padding()
            counter = lambda text: len(tokenizer.encode(text, add_special_tokens=False).ids)
            _, source_manifest = self.linked(p['context_source_manifest'])
            chunks = [self.chunk(r) for b in bundles for c in b['contexts'].values() for r in c['source_records']]
            binder = RetrievedSourceBinder(source_manifest['source_inventory'], chunks, self.root)
            for b, q in zip(bundles, public):
                if set(b['contexts']) != ({'dual'} if robustness else {'none', 'merged', 'dual'}):
                    raise ValueError('Unsupported prepared context layout')
                for name, context in b['contexts'].items():
                    hits = [(self.chunk(r), r['score']) for r in context['source_records']]
                    for r, (chunk, _) in zip(context['source_records'], hits):
                        if chunk.meta.get('corpus_type') == 'annual_report' and (
                                chunk.meta.get('stock_code') != q['stock_code'] or str(chunk.meta.get('report_year')) != str(q['report_year'])):
                            raise ValueError('Context annual evidence escaped the public company/year scope')
                        self.source_bindings.append(binder.bind(chunk, q['question_id'], r['evidence_id']))
                    rebuilt = _pack_context(hits, counter, b['budget']['max_reference_context_tokens'])
                    for key in ('context', 'context_sha256', 'reference_tokens', 'source_records', 'source_records_sha256'):
                        if rebuilt[key] != context[key]: raise ValueError('Prepared context cannot be rebuilt from original source records')
                    if name == 'none' and context['source_records']: raise ValueError('No-RAG context contains sources')
                if robustness and (not runtime['methods'] or not set(runtime['methods']) <= set(MODES[2:])):
                    raise ValueError('Paired robustness uses only generic/role dual-source methods')
                for i, mode in enumerate(MODES):
                    if robustness and i < 2: continue
                    key = 'none' if i == 0 else 'merged' if i == 1 else 'dual'
                    constraint = NO_RAG_CONSTRAINT if i == 0 else ROLE_CONSTRAINT if i == 3 else GENERIC_CONSTRAINT
                    prompt = COMMON_PROMPT.format(**q, context=b['contexts'][key]['context'], constraint=constraint)
                    mode_record = b['modes'][mode]
                    if mode_record['context_key'] != key or mode_record['prompt'] != prompt or mode_record['prompt_reference_tokens'] != counter(prompt):
                        raise ValueError('Prepared prompt differs from public question/context and frozen template')
            self.guards.extend(binder.recheck_files())
            identity = p['model_identity']
            _, identity_doc = self.linked(identity['evidence'])
            for field in ('requested_model', 'declared_family', 'revision_or_snapshot', 'expected_response_model'):
                if not identity.get(field) or identity.get(field) != identity_doc.get(field):
                    raise ValueError('Model identity declaration or its source record is incomplete')
            if identity['requested_model'] != runtime['requested_generation_model']:
                raise ValueError('Requested model differs from the identity declaration')
            _, budget = self.linked(p['registered_budget'])
            if budget.get('schema_version') != 'generation-call-budget-v1' or any(
                    budget.get(k) != runtime[k] for k in ('requested_generation_model', 'maximum_client_calls',
                        'max_output_tokens', 'max_observed_tokens', 'maximum_supplemental_calls')):
                raise ValueError('Generation call-budget registration differs')
            self.check_targets(p, hashes, frozen, binder)
            if robustness:
                from src.generation.robustness_execution import validate_challenge_receipts
                validate_challenge_receipts(self, manifest, bundles, frozen)
            if not self.control:
                _, history = self.linked(p['historical_exposures']); _, audit = self.linked(p['exposure_review'])
                check_exposure_crosswalk(history, audit, p['historical_exposures']['sha256'], public, self.reviewer_ids, frozen)
            if shared is not None:
                self.guards.append({'file': str(Path(args.shared_drafts_dir).resolve() / 'shared_draft_manifest.json'),
                    'sha256': runtime['shared_drafts_manifest_sha256']})
                self.guards.extend({'file': str(r['source_file']), 'sha256': r['sha256']} for r in shared.values())
            if runtime['entrypoint'] == 'bounded_retrieval':
                self.guards.extend([
                    {'file': str((Path(args.index_dir) / 'index_manifest.json').resolve()), 'sha256': runtime['supplemental_index_manifest_sha256']},
                    {'file': str(Path(args.tokenizer_json).resolve()), 'sha256': runtime['supplemental_tokenizer_sha256']}])
            self.check('before')
            self.report.update(status='engineering_control_protocol_validated' if self.control else 'externally_frozen_generation_protocol_validated',
                source_bindings_checked=len(self.source_bindings))
        except (ValueError, KeyError, TypeError, OSError, importlib.metadata.PackageNotFoundError) as error:
            self.report['issues'].append(str(error))

    @staticmethod
    def chunk(r):
        return Chunk(r['chunk_id'], r['doc_id'], r['document_title'], r['doc_type'], r['source'],
                     r['clause_no'], r['text'], None, r['meta'])

    def linked_bytes(self, ref):
        path = local_path(ref['file'], self.path.parent)
        if file_sha256(path) != ref['sha256']: raise ValueError('Protocol-linked file SHA256 mismatch')
        self.guards.append({'file': str(path), 'sha256': ref['sha256']})
        return path, path.read_bytes()

    def linked(self, ref):
        path, raw = self.linked_bytes(ref)
        return path, json.loads(raw)

    def check_targets(self, protocol, hashes, frozen, binder):
        path, targets = self.linked(protocol['targets'])
        if targets.get('status') != 'resolved_review_records_not_formal_freeze' or targets.get('issues'):
            raise ValueError('Actual target review receipts/resolutions are incomplete')
        if targets.get('purpose') != ('engineering_control' if self.control else 'final_test') or targets.get('validation_only') is not self.control:
            raise ValueError('Development/synthetic targets cannot be promoted to formal generation')
        copies = {}
        for row in targets['preserved_raw_inputs']:
            p = local_path(row['copy'], path.parent)
            if not p.is_relative_to(path.parent) or row['kind'] in copies or file_sha256(p) != row['sha256']:
                raise ValueError('Original target-review copy changed or escaped its release')
            copies[row['kind']] = p; self.guards.append({'file': str(p), 'sha256': row['sha256']})
        if set(copies) != {'packet', 'R1', 'R2', 'registration', 'decisions'}:
            raise ValueError('Two original review receipts and explicit resolutions are required')
        self.guards.append({'file': str(path.parent / 'submitted_originals/request.json'), 'sha256': targets['request_sha256']})
        registrations = read_csv(copies['registration'])[1]
        self.reviewer_ids = {r['actual_reviewer_id'].strip() for r in registrations}
        source_map = {digest: binder._file(digest, {'.pdf', '.docx', '.txt'}) for digest, paths in binder.inventory.items()
                      if any(p.suffix.lower() in {'.pdf', '.docx', '.txt'} for p in paths)}
        verifier = EvidenceSourceVerifier(path.parent, source_map=source_map, ocr_frames=list(binder.ocr.values()))
        resolved = resolve_target_reviews(json.loads(copies['packet'].read_bytes()), registrations,
            {r: read_csv(copies[r])[1] for r in ('R1', 'R2')}, read_csv(copies['decisions'])[1], verifier)
        for key in ('status', 'purpose', 'dataset_version', 'question_sha256', 'resolved_records', 'unknown_or_unresolved_records'):
            if resolved.get(key) != targets.get(key): raise ValueError('Resolved targets differ from original review receipts')
        if resolved['question_sha256'] != hashes or any(day(r['resolution_record']['decided_at']) > frozen for r in resolved['resolved_records']):
            raise ValueError('Question inventory or review/freeze chronology differs')
        self.guards.extend(verifier.recheck_files())

    def check(self, phase, client=None, prompt=None):
        try:
            recheck_protocol_guards(self.guards)
            if client is not None:
                if bool(client.mock) != self.control: raise ValueError('Formal API execution and synthetic client kind differ')
                if any(getattr(client, attr, None) != self.runtime[key] for attr, key in (
                        ('model', 'requested_generation_model'), ('temperature', 'temperature'), ('max_output_tokens', 'max_output_tokens'))):
                    raise ValueError('Client model or generation parameters changed')
                if phase == 'after' and not self.control:
                    request = client.last_request or {}
                    expected = {'model': client.model, 'temperature': client.temperature,
                        'max_tokens': client.max_output_tokens, 'messages': [{'role': 'user', 'content': prompt}]}
                    if request != expected or client.last_raw_response is None:
                        raise ValueError('Exact SDK request/response binding is missing')
                    if client.last_response_metadata.get('response_model') != self.protocol['model_identity']['expected_response_model']:
                        raise ValueError('Provider response model differs from its registered declaration')
        except (ValueError, OSError) as error:
            raise ProtocolViolation(str(error)) from error

    def check_execution(self, entrypoint, bundles, modes, repeats, max_calls, seed,
                        max_observed_tokens, max_consecutive_failures,
                        declared_target_date=None, max_supplemental_calls=None, max_new_sources=None,
                        declared_target_date_role=None):
        actual = {'entrypoint': entrypoint, 'prepared_payloads_sha256': canonical_sha256(bundles),
            'methods': list(modes), 'repeats': repeats, 'maximum_client_calls': max_calls,
            'randomization_seed': seed, 'max_observed_tokens': max_observed_tokens,
            'max_consecutive_failures': max_consecutive_failures,
            'declared_target_date': declared_target_date,
            'declared_target_date_role': declared_target_date_role}
        if entrypoint == 'bounded_retrieval':
            actual.update(maximum_supplemental_calls=max_supplemental_calls, maximum_new_sources=max_new_sources)
        if any(value != self.runtime[key] for key, value in actual.items()):
            raise ProtocolViolation('Execution modes,prepared inputs or call budgets changed after protocol validation')
        self.check('before')

    def persist(self, out):
        self.check('before')
        directory = Path(out) / 'generation_protocol'; directory.mkdir()
        (directory / 'frozen_protocol.json').write_bytes(self.raw)
        for name, value in [('inspection.json', self.report), ('source_bindings.json', self.source_bindings)]:
            (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if hasattr(self, 'challenge_raw_paths'):
            originals = directory / 'challenge_originals'; originals.mkdir()
            for name, source in self.challenge_raw_paths.items():
                (originals / (name + source.suffix)).write_bytes(source.read_bytes())

    def metadata(self):
        return {'purpose': 'engineering_control_generation' if self.control else 'formal_generation_evaluation',
            'frozen_generation_protocol_sha256': self.expected, 'generation_protocol_runtime': self.runtime,
            'validation_only': self.control, 'protocol_kind': self.protocol['protocol_kind'],
            'externally_declared_final_freeze_bound': not self.control,
            'human_identity_authenticated': False, 'provider_model_identity_authenticated': False}


def bind_generation_protocol(args, entrypoint, cfg, temperature, modes, manifest, bundles, root, shared=None):
    path, expected = getattr(args, 'frozen_protocol', None), getattr(args, 'frozen_protocol_sha256', None)
    if not path and not expected: return None
    binding = None
    try:
        if not path or not expected: raise ValueError('Generation protocol path and trusted SHA256 must be supplied together')
        runtime = runtime_fields(entrypoint, args, cfg, temperature, modes, bundles, shared)
        binding = GenerationBinding(path, expected, runtime, manifest, bundles, args, root, shared)
        if not binding.report['issues'] and not binding.control: return binding
        if not binding.report['issues']:
            binding.report.update(status='protocol_rejected_before_models_or_api')
            binding.report['issues'].append('Engineering controls require an explicitly supplied offline client;API CLI cannot execute them')
        report = binding.report
    except (ValueError, OSError) as error:
        report = {'status': 'protocol_rejected_before_models_or_api', 'issues': [str(error)]}
    report.update(model_loading_calls=0, generation_API_calls=0, formal_metrics=None)
    out = Path(args.out_dir).resolve(); out.mkdir(parents=True, exist_ok=False)
    (out / 'generation_protocol_rejection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return False
