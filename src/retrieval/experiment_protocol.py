"""Pre-model protocol checks; private review labels never become search inputs."""
from __future__ import annotations

import importlib.metadata
import json
import platform
from pathlib import Path

from src.data.evidence_sources import EvidenceSourceVerifier, local_path
from src.data.review_intake import file_sha256, read_csv
from src.data.retrieval_target_release import day, resolve_target_reviews
from src.data.evaluation_groups import normalize
from src.generation.comparison import canonical_sha256, public_question

IMPLEMENTATION_FILES = (
    'src/data/pdf_text_frames.py',
    'src/retrieval/search_trace.py',
    'src/retrieval/factorial.py', 'src/retrieval/router.py',
    'src/data/page_mapped_chunks.py', 'src/data/structural_splitter.py',
    'scripts/run_retrieval_method_comparison.py', 'src/retrieval/experiment_protocol.py',
    'src/retrieval/method_comparison.py', 'src/data/retrieved_source_spans.py',
    'src/pipeline.py', 'src/config.py', 'src/retrieval/index_artifact.py',
    'src/retrieval/hybrid.py', 'src/retrieval/bm25.py', 'src/retrieval/dense.py',
    'src/retrieval/reranker.py', 'src/retrieval/runtime.py', 'src/data/document_corpora.py',
    'src/data/evidence_sources.py', 'src/data/knowledge_loader.py', 'src/data/docx_text.py',
    'src/data/annual_reports.py', 'src/data/retrieval_target_release.py',
    'src/data/review_intake.py', 'src/data/evaluation_groups.py',
    'src/generation/comparison.py', 'src/metrics/span_retrieval.py')
FIXED_RUNTIME_FIELDS = ('questions_sha256', 'index_manifest_sha256', 'configuration_sha256', 'implementation_sha256',
    'methods', 'layouts', 'annual_top_k', 'regulation_top_k', 'randomization_seed',
    'maximum_search_calls', 'maximum_queries', 'max_consecutive_failures')


def implementation_hashes(root):
    return {name: file_sha256(Path(root) / name) for name in IMPLEMENTATION_FILES}


def hashed(path, expected):
    path = Path(path).resolve()
    if file_sha256(path) != expected: raise ValueError('Protocol-linked input SHA256 mismatch')
    return json.loads(path.read_bytes())


def guarded_json(reference, base, guards):
    path = local_path(reference['file'], base)
    value = hashed(path, reference['sha256'])
    guards.append({'file': str(path), 'sha256': reference['sha256']})
    return path, value


def recheck_protocol_guards(guards):
    for row in guards:
        if not Path(row['file']).is_file() or file_sha256(Path(row['file'])) != row['sha256']:
            raise ValueError('A protocol,review,exposure or implementation input changed during execution')


def check_exposure_crosswalk(history, audit, history_sha, questions, actual_ids, frozen_day):
    """Check recorded declarations, without claiming semantic or identity certification."""
    if history.get('schema_version') != 'registered-public-exposure-history-v1' or not history.get('records'):
        raise ValueError('A nonempty registered historical public-question inventory is required')
    if audit.get('schema_version') != 'final-question-exposure-review-v1' or \
            audit.get('historical_exposures_sha256') != history_sha:
        raise ValueError('Exposure crosswalk is not bound to registered history')
    seen_ids = {r['query_id'] for r in history['records']}
    seen_text = {normalize(r['query_text']) for r in history['records']}
    reviews = audit.get('questions', [])
    by_id = {r['query_id']: r for r in reviews}
    hashes = {q['question_id']: canonical_sha256(public_question(q)) for q in questions}
    if len(by_id) != len(reviews) or set(by_id) != set(hashes):
        raise ValueError('Exposure review does not cover every final question once')
    for q in questions:
        qid = q['question_id']; reviewed = by_id[qid]
        if qid in seen_ids or normalize(q['query']) in seen_text:
            raise ValueError('An already exposed ID or question text cannot enter the final test')
        if reviewed.get('question_sha256') != hashes[qid] or \
                reviewed.get('decision') != 'held_out_against_registered_history' or \
                set(reviewed.get('reviewer_ids', [])) != actual_ids or not reviewed.get('reason'):
            raise ValueError('Two recorded reviewers must explicitly confirm the historical/family crosswalk')
        if not reviewed.get('query_family_id') or not reviewed.get('event_or_evidence_group_id'):
            raise ValueError('Final family/event/evidence group registration is missing')
        if frozen_day and day(reviewed.get('reviewed_at', '')) > frozen_day:
            raise ValueError('Exposure review happened after protocol freeze')
    return len(history['records'])


def inspect_protocol(path, expected_sha, actual, questions, root):
    """Return validation metadata only; no candidate quotes, grades or reasons."""
    path, root = Path(path).resolve(), Path(root).resolve()
    protocol = hashed(path, expected_sha)
    guards = [{'file': str(path), 'sha256': expected_sha}]
    issues = []
    control = protocol.get('protocol_kind') == 'engineering_control'
    report = {'status': 'protocol_rejected_before_models', 'protocol_sha256': expected_sha,
        'protocol_kind': protocol.get('protocol_kind'), 'issues': issues,
        'guards': guards, 'human_identity_authenticated': False,
        'actual_blinding_verified': False, 'semantic_holdout_certified_by_tool': False,
        'private_review_labels_in_search_inputs': False, 'formal_metrics': None,
        'validated_actual_human_reviews_by_tool': 0}
    if protocol.get('schema_version') != 'formal-source-span-protocol-v1':
        issues.append('Unsupported protocol schema')
    if protocol.get('protocol_kind') not in ('formal', 'engineering_control'):
        issues.append('Explicit formal/engineering-control protocol kind is required')
    if protocol.get('status') != ('engineering_control_frozen' if control else 'externally_frozen'):
        issues.append('Protocol is still a draft or lacks external freeze declaration')
    for field in FIXED_RUNTIME_FIELDS:
        if field not in protocol or field not in actual or protocol[field] != actual[field]:
            issues.append('Frozen runtime field differs: ' + field)
    if ('factorial_profile_policy' in protocol or 'factorial_profile_policy' in actual) and \
            protocol.get('factorial_profile_policy') != actual.get('factorial_profile_policy'):
        issues.append('Frozen factorial profile policy differs or is missing')
    if protocol.get('implementation_sha256') != implementation_hashes(root):
        issues.append('Current critical execution code differs from the protocol')
    if protocol.get('scorer_sha256') != file_sha256(root / 'scripts/score_source_span_run.py'):
        issues.append('Scorer implementation differs from the protocol')
    if protocol.get('python_version') != platform.python_version():
        issues.append('Python version differs from the protocol')
    packages = protocol.get('required_packages', {})
    mandatory = {'pypdf', 'numpy', 'jieba'}
    if any(m != 'bm25' for m in actual['methods']):
        mandatory |= {'torch', 'transformers', 'sentence-transformers'}
    if not mandatory <= set(packages): issues.append('Protocol lacks required local package versions')
    for name, version in packages.items():
        try:
            if importlib.metadata.version(name) != version: issues.append('Package version differs: ' + name)
        except importlib.metadata.PackageNotFoundError:
            issues.append('Required package is missing: ' + name)
    hashes = {q['question_id']: canonical_sha256(public_question(q)) for q in questions}
    if protocol.get('question_sha256') != hashes: issues.append('Public question inventory or text differs')
    if protocol.get('failure_policy') != 'retain_no_point_score_no_aggregate' or \
            protocol.get('budget_reporting') != 'equal-final-slots-role-coverage-v1':
        issues.append('Failure and equal-budget reporting policies must be explicit')
    thresholds, cutoffs = protocol.get('thresholds', []), protocol.get('cutoffs', [])
    if not thresholds or len(set(thresholds)) != len(thresholds) or any(type(t) is not int or t not in (1, 2) for t in thresholds):
        issues.append('Direct/inclusive grade thresholds must be fixed')
    cap = min(actual['annual_top_k'], actual['regulation_top_k']) if 'dual' in actual['layouts'] else actual['annual_top_k'] + actual['regulation_top_k']
    if not cutoffs or any(type(k) is not int or k < 1 or k > cap for k in cutoffs) or sorted(set(cutoffs)) != cutoffs:
        issues.append('Metric cutoffs exceed saved depths or are not fixed positive ascending ranks')
    try:
        frozen_day = day(protocol.get('frozen_at', ''))
    except ValueError as error:
        issues.append(str(error)); frozen_day = None
    if not protocol.get('coordinator_id') or protocol.get('coordinator_id') in ('R1', 'R2'):
        issues.append('Explicit actual coordinator/resolver declaration is missing')
    try:
        targets_path, targets = guarded_json(protocol['targets'], path.parent, guards)
        if protocol.get('targets_sha256') != protocol['targets']['sha256']:
            issues.append('Target release hashes disagree')
        if targets.get('status') != 'resolved_review_records_not_formal_freeze' or targets.get('issues'):
            issues.append('Target reviews or explicit resolutions are incomplete/unknown')
        elif targets.get('purpose') != ('engineering_control' if control else 'final_test') or \
                targets.get('validation_only') is not control:
            issues.append('Development/synthetic target data cannot be promoted to formal final-test data')
        else:
            copies = {}
            for row in targets['preserved_raw_inputs']:
                candidate = local_path(row['copy'], targets_path.parent)
                if not candidate.is_relative_to(targets_path.parent) or row['kind'] in copies or file_sha256(candidate) != row['sha256']:
                    raise ValueError('Preserved raw target-review input changed or escaped its release')
                copies[row['kind']] = candidate
                guards.append({'file': str(candidate), 'sha256': row['sha256']})
            if not {'packet', 'R1', 'R2', 'registration', 'decisions'} <= set(copies):
                raise ValueError('Both original review receipts and explicit resolutions are required')
            request = targets_path.parent / 'submitted_originals/request.json'
            if file_sha256(request) != targets['request_sha256']: raise ValueError('Original compilation request changed')
            guards.append({'file': str(request), 'sha256': targets['request_sha256']})
            source_map = {key: Path(value) for key, value in targets.get('source_map_for_scoring', {}).items()}
            frames = [dict(frame) for frame in targets.get('ocr_frames_for_scoring', [])]
            if protocol.get('source_map'):
                map_path, mapping = guarded_json(protocol['source_map'], path.parent, guards)
                keys = set()
                for row in mapping:
                    if row['sha256'] in keys: raise ValueError('Duplicate source-map hash')
                    keys.add(row['sha256']); source_map[row['sha256']] = local_path(row['file'], map_path.parent)
                for frame in frames:
                    for digest, dest in [('text_sha256', 'text_file'), ('image_sha256', 'image_file')]:
                        if frame[digest] in keys: frame[dest] = str(source_map[frame[digest]])
            verifier = EvidenceSourceVerifier(targets_path.parent, source_map=source_map, ocr_frames=frames)
            registrations = read_csv(copies['registration'])[1]
            actual_ids = {r['actual_reviewer_id'].strip() for r in registrations}
            recomputed = resolve_target_reviews(json.loads(copies['packet'].read_bytes()), registrations,
                {r: read_csv(copies[r])[1] for r in ('R1', 'R2')}, read_csv(copies['decisions'])[1], verifier)
            for field in ('status', 'purpose', 'dataset_version', 'question_sha256', 'candidate_count', 'resolved_records', 'unknown_or_unresolved_records'):
                if recomputed.get(field) != targets.get(field): raise ValueError('Resolved target data differ from the raw review chain')
            if recomputed['question_sha256'] != hashes: raise ValueError('Target questions differ from public run questions')
            if frozen_day and any(day(r['resolution_record']['decided_at']) > frozen_day for r in recomputed['resolved_records']):
                raise ValueError('Protocol freeze predates target-review resolution')
            guards.extend(verifier.recheck_files())
            report['reviewed_target_records_checked'] = len(recomputed['resolved_records'])
            if not control:
                history_path, history = guarded_json(protocol['historical_exposures'], path.parent, guards)
                audit_path, audit = guarded_json(protocol['exposure_review'], path.parent, guards)
                report['historical_records_checked'] = check_exposure_crosswalk(history, audit,
                    protocol['historical_exposures']['sha256'], questions, actual_ids, frozen_day)
    except (ValueError, KeyError, TypeError, OSError) as error:
        issues.append(str(error))
    guards.extend({'file': str(root / name), 'sha256': digest} for name, digest in actual['implementation_sha256'].items())
    report['targets_sha256'] = protocol.get('targets_sha256')
    if not issues:
        recheck_protocol_guards(guards)
        report['status'] = 'engineering_control_protocol_validated' if control else 'externally_frozen_protocol_validated'
    return protocol, report
