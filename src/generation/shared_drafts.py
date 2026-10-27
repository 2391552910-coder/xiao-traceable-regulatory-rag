"""Hash-bound saved drafts for paired verifier controls, without model calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.generation.comparison import MODES, canonical_sha256, text_sha256
from src.generation.llm_client import parse_json
from src.generation.strong_baselines import prepare_supplement, validate_generation

VERIFICATION_MODES = ('generic_verify_revise_v1', 'joint_role_verify_revise_v1',
                      'generic_verify_retrieve_revise_v1', 'joint_role_verify_retrieve_revise_v1')
DRAFT_SOURCE_MODES = (MODES[2],) + VERIFICATION_MODES


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_hashed(path, expected):
    raw = Path(path).read_bytes()
    if not isinstance(expected, str) or len(expected) != 64 or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Saved draft input SHA256 mismatch')
    return raw, json.loads(raw)


def positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_saved_draft(unit, payload, repeat):
    if unit.get('status') != 'completed' or unit.get('question_id') != payload['question']['question_id'] \
            or not positive_integer(unit.get('repeat_id')) or unit['repeat_id'] != repeat:
        raise ValueError('Saved draft must be a completed matching question and repeat')
    mode = unit.get('mode')
    if not (mode == MODES[2] and unit.get('stage') is None) and not (
            mode in VERIFICATION_MODES and unit.get('stage') == 'draft'):
        raise ValueError('Only generic-context generation or an initial draft stage may be reused')
    if unit.get('prompt') != payload['generic_prompt'] or \
            unit.get('prompt_sha256') != payload['generic_prompt_sha256'] or \
            text_sha256(unit['prompt']) != unit['prompt_sha256']:
        raise ValueError('Saved draft generic prompt is not byte-identical')
    for name in ('context_sha256', 'source_records_sha256'):
        if unit.get(name) != payload['context'][name]:
            raise ValueError('Saved draft context or supplied sources differ')
    if unit.get('redaction_applied', False):
        raise ValueError('A transformed draft cannot establish exact original-body reuse')
    response = unit.get('response')
    if not isinstance(unit.get('raw_response'), str) or \
            canonical_sha256(parse_json(unit['raw_response'])) != canonical_sha256(response):
        raise ValueError('Saved draft raw response and parsed response differ')
    metadata = unit.get('response_metadata', {})
    if metadata.get('finish_reason') != 'stop':
        raise ValueError('Saved draft must have finished with stop')
    request = unit.get('request_parameters')
    if not isinstance(request, dict) or request.get('messages') != [{'role': 'user', 'content': unit['prompt']}]:
        raise ValueError('Saved draft exact request trace is missing or differs')
    if not isinstance(unit.get('raw_sdk_response'), dict):
        raise ValueError('Saved draft original SDK response is missing')
    validated = validate_generation(response, payload)
    tokens = metadata.get('total_tokens')
    return {'validated': validated, 'response': response,
            'body_sha256': text_sha256(validated['evaluation']),
            'upstream_model': request.get('model'),
            'upstream_observed_total_tokens': tokens if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0 else None,
            'upstream_mock_declared': metadata.get('mock'),
            'semantic_support_verified': False, 'accepted_as_gold': False}


def read_saved_draft(reference, payload, repeat):
    raw, unit = read_hashed(reference['source_file'], reference['sha256'])
    return raw, validate_saved_draft(unit, payload, repeat)


def source_entries(run, mode):
    if run.get('status') not in {'completed', 'completed_with_failures', 'stopped_by_control'} \
            or run.get('active_request') or run.get('active_retrieval'):
        raise ValueError('Source run is not terminal or still has an active operation')
    if mode == MODES[2]:
        rows = run.get('units', [])
    else:
        rows = [r for r in run.get('stage_records', []) if r.get('stage') == 'draft']
    chosen = [r for r in rows if r.get('mode') == mode]
    keys = [(r.get('question_id'), r.get('repeat_id')) for r in chosen]
    if len(keys) != len(set(keys)) or any(not positive_integer(k[1]) for k in keys):
        raise ValueError('Source run contains duplicate or invalid draft identities')
    return dict(zip(keys, chosen))


def _inside(directory, name, *, flat=False):
    path = (directory / name).resolve()
    if not path.is_relative_to(directory.resolve()) or flat and path.parent != directory.resolve():
        raise ValueError('Saved draft path escapes its package')
    return path


def prepare_shared_drafts(bundles, prepared_sha, source_run_path, source_run_sha, source_mode, repeats, out):
    if source_mode not in DRAFT_SOURCE_MODES or not positive_integer(repeats):
        raise ValueError('Select a supported source mode and positive repeats')
    out, source_run_path = Path(out), Path(source_run_path).resolve()
    if out.exists():
        raise FileExistsError(out)
    run_raw, run = read_hashed(source_run_path, source_run_sha)
    parent = run.get('parent_prepared_manifest_sha256', run.get('prepared_manifest_sha256'))
    if parent != prepared_sha:
        raise ValueError('Source run does not bind the requested prepared manifest')
    entries = source_entries(run, source_mode)
    payloads = [prepare_supplement(b) for b in bundles]
    ids = [p['question']['question_id'] for p in payloads]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Prepared questions must be nonempty and unique')
    expected = {(p['question']['question_id'], r) for p in payloads for r in range(1, repeats + 1)}
    if not expected or set(entries) != expected:
        raise ValueError('Source drafts must cover every requested question and repeat exactly')
    prepared = []
    for payload in payloads:
        qid = payload['question']['question_id']
        for repeat in range(1, repeats + 1):
            entry = entries[qid, repeat]
            if entry['status'] != 'completed':
                raise ValueError('A failed source draft cannot be repaired or accepted by this adapter')
            path = _inside(source_run_path.parent, entry['path'])
            raw, validated = read_saved_draft({'source_file': path, 'sha256': entry['sha256']}, payload, repeat)
            row = {'question_id': qid, 'repeat_id': repeat, 'path': f'{qid}__draft_{repeat:03d}.json',
                   'sha256': entry['sha256'], 'origin_entry_path': entry['path'],
                   'body_sha256': validated['body_sha256'], 'upstream_model': validated['upstream_model'],
                   'upstream_observed_total_tokens': validated['upstream_observed_total_tokens'],
                   'upstream_mock_declared': validated['upstream_mock_declared']}
            prepared.append((row, raw))
    # Check the original index of units once more before creating any output.
    read_hashed(source_run_path, source_run_sha)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'source_run.json').write_bytes(run_raw)
    for row, raw in prepared:
        (out / row['path']).write_bytes(raw)
    manifest = {'schema_version': 'paired-saved-drafts-v1', 'status': 'prepared',
                'purpose': 'development_shared_drafts', 'prepared_manifest_sha256': prepared_sha,
                'source_run': {'path': 'source_run.json', 'sha256': source_run_sha},
                'source_mode': source_mode, 'repeats': repeats, 'records': [r for r, _ in prepared],
                'original_draft_bytes_preserved': True, 'new_generation_API_calls': 0,
                'formal_final_test_frozen': False, 'formal_metrics': None}
    (out / 'shared_draft_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def read_shared_drafts(directory, expected_sha, bundles, prepared_sha, repeats):
    if not positive_integer(repeats):
        raise ValueError('Repeats must be a positive integer')
    directory = Path(directory).resolve()
    _, manifest = read_hashed(directory / 'shared_draft_manifest.json', expected_sha)
    if manifest.get('schema_version') != 'paired-saved-drafts-v1' or manifest.get('status') != 'prepared' \
            or manifest.get('purpose') != 'development_shared_drafts' \
            or manifest.get('prepared_manifest_sha256') != prepared_sha or manifest.get('repeats') != repeats:
        raise ValueError('Unsupported or mismatched shared draft package')
    parent = manifest['source_run']
    _, source_run = read_hashed(_inside(directory, parent['path'], flat=True), parent['sha256'])
    if source_run.get('parent_prepared_manifest_sha256', source_run.get('prepared_manifest_sha256')) != prepared_sha:
        raise ValueError('Shared draft source run changed its prepared parent')
    entries = source_entries(source_run, manifest['source_mode'])
    prepared = [prepare_supplement(b) for b in bundles]
    payloads = {p['question']['question_id']: p for p in prepared}
    if not prepared or len(payloads) != len(prepared):
        raise ValueError('Prepared questions must be nonempty and unique')
    expected = {(qid, repeat) for qid in payloads for repeat in range(1, repeats + 1)}
    result = {}
    for row in manifest['records']:
        key = row['question_id'], row['repeat_id']
        if key not in expected or key in result or key not in entries:
            raise ValueError('Shared draft question/repeat inventory differs')
        origin = entries[key]
        if origin['status'] != 'completed' or origin['path'] != row['origin_entry_path'] or origin['sha256'] != row['sha256']:
            raise ValueError('Shared draft is not bound to its original run entry')
        reference = {'source_file': _inside(directory, row['path'], flat=True), 'sha256': row['sha256'],
                     'package_manifest_sha256': expected_sha, 'source_run_sha256': parent['sha256'],
                     'origin_entry_path': row['origin_entry_path'], 'source_mode': manifest['source_mode']}
        _, checked = read_saved_draft(reference, payloads[key[0]], key[1])
        if checked['body_sha256'] != row['body_sha256']:
            raise ValueError('Shared draft body SHA256 mismatch')
        result[key] = reference
    if set(result) != expected or set(entries) != expected:
        raise ValueError('Shared drafts cannot silently omit or reuse repeats')
    return result
