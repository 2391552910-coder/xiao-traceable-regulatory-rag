"""Paired generation units and original independent challenge-review receipts."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from src.data.retrieval_target_release import day, label
from src.data.review_intake import file_sha256, read_csv
from src.generation.comparison import MODES, canonical_sha256, public_question, text_sha256
from src.generation.robustness import KINDS, record_chunk

SCHEMA = 'paired-robustness-generation-v1'
METHODS = MODES[2:]
FIELDS = ('expected_answerability', 'expected_company_support', 'expected_regulation_support',
          'expected_temporal_applicability', 'challenge_valid')
ALLOWED = {
    FIELDS[0]: {'answerable', 'partially_answerable', 'insufficient', 'conflicted', 'unresolved'},
    FIELDS[1]: {'supported', 'unsupported', 'mixed', 'unknown', 'na'},
    FIELDS[2]: {'supported', 'unsupported', 'mixed', 'unknown', 'na'},
    FIELDS[3]: {'applicable', 'not_applicable', 'unknown', 'na'},
    FIELDS[4]: {'yes', 'no', 'unknown'},
}


def execution_identity(bundle):
    q = public_question(bundle['question'])
    unit = bundle.get('_execution_unit')
    required = {'execution_unit_id', 'pair_id', 'case_id', 'proposed_kind'}
    if not isinstance(unit, dict) or set(unit) != required or unit['pair_id'] != q['question_id']:
        raise ValueError('Explicit robustness execution unit and original question identity are required')
    case = unit['case_id']
    if not isinstance(case, str) or not case or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in case):
        raise ValueError('Unsafe robustness case identifier')
    expected = 'RB_' + canonical_sha256([q['question_id'], case])[:24]
    if unit['execution_unit_id'] != expected:
        raise ValueError('Robustness unit ID differs from original question/case')
    if (case == 'unperturbed') != (unit['proposed_kind'] is None) or \
            (case != 'unperturbed' and unit['proposed_kind'] not in KINDS):
        raise ValueError('Baseline or proposed challenge-kind identity is inconsistent')
    return dict(unit)


def unit_inventory(bundles):
    result, seen, questions, baselines = [], set(), {}, set()
    for bundle in bundles:
        unit = execution_identity(bundle)
        q = public_question(bundle['question'])
        qid = q['question_id']
        if q != bundle['question'] or (qid in questions and questions[qid] != q):
            raise ValueError('A robustness pair must keep exactly the same public question')
        questions[qid] = q
        if unit['execution_unit_id'] in seen:
            raise ValueError('Duplicate robustness execution unit')
        seen.add(unit['execution_unit_id'])
        if unit['case_id'] == 'unperturbed':
            baselines.add(qid)
        if set(bundle['contexts']) != {'dual'} or set(bundle['modes']) != set(METHODS):
            raise ValueError('Robustness generation uses only the paired dual-source generic/role modes')
        result.append({**unit, 'question_id': qid, 'payload_sha256': canonical_sha256(bundle)})
    if not result or baselines != set(questions):
        raise ValueError('Each original question must retain an unperturbed baseline')
    if any(sum(r['question_id'] == qid for r in result) < 2 for qid in questions):
        raise ValueError('Each question needs a baseline and at least one variant')
    originals = {b['question']['question_id']: b['contexts']['dual']['source_records']
                 for b in bundles if b['_execution_unit']['case_id'] == 'unperturbed'}
    fingerprint = lambda r: canonical_sha256({key: value for key, value in r.items() if key != 'evidence_id'})
    for bundle in bundles:
        unit = bundle['_execution_unit']; current = bundle['contexts']['dual']['source_records']
        for record in current: record_chunk(record)
        if len({r['chunk_id'] for r in current}) != len(current):
            raise ValueError('A robustness context cannot repeat a source chunk')
        baseline = originals[unit['pair_id']]
        if {r['doc_type'] for r in baseline} != {'annual_report', 'regulation'}:
            raise ValueError('An unperturbed dual-source context requires both roles')
        before, after = list(map(fingerprint, baseline)), list(map(fingerprint, current))
        kind = unit['proposed_kind']
        if kind is None: continue
        if kind == KINDS[0]:
            valid = after == [fingerprint(r) for r in baseline if r['doc_type'] == 'regulation']
        elif kind == KINDS[1]:
            removed = [r for r, digest in zip(baseline, before) if digest not in after]
            valid = bool(removed) and all(r['doc_type'] == 'regulation' for r in removed) and \
                after == [digest for digest in before if digest in after]
        elif kind in KINDS[2:4]:
            changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
            valid = len(before) == len(after) and len(changed) == 1
            if valid:
                old, new = baseline[changed[0]], current[changed[0]]
                valid = old['doc_type'] == new['doc_type'] == 'regulation'
                if kind == KINDS[3]:
                    valid = valid and bool(old['clause_no']) and old['clause_no'] == new['clause_no'] and \
                        old['doc_id'] == new['doc_id'] and bool(old['meta'].get('source_document_sha256')) and \
                        bool(new['meta'].get('source_document_sha256')) and \
                        old['meta']['source_document_sha256'] != new['meta'].get('source_document_sha256')
        elif kind == KINDS[4]:
            valid = len(after) > len(before) and after[:len(before)] == before
        else:
            valid = not after
        if not valid:
            raise ValueError('Prepared robustness contents do not match the declared mechanical operation')
    return result


def compile_units(pairs):
    """Flatten source-verified pair outputs without renaming public questions."""
    result = []
    for pair in pairs:
        if pair.get('schema_version') != 'fixed-context-robustness-pairs-v1':
            raise ValueError('Unsupported paired source preparation')
        q = public_question(pair['question'])
        cases = [('unperturbed', None, pair['unperturbed'])] + [
            (v['case_id'], v['proposed_kind'], v) for v in pair['variants']]
        for case, kind, value in cases:
            payload = copy.deepcopy(value['payload'])
            if canonical_sha256(payload) != value['payload_sha256'] or payload['question'] != q:
                raise ValueError('Source-prepared payload changed or public question differs')
            payload['_execution_unit'] = {'execution_unit_id': 'RB_' + canonical_sha256([q['question_id'], case])[:24],
                'pair_id': q['question_id'], 'case_id': case, 'proposed_kind': kind}
            result.append(payload)
    unit_inventory(result)
    return result


def read_prepared(directory, expected):
    directory = Path(directory).resolve()
    path = directory / 'robustness_manifest.json'
    if file_sha256(path) != expected.lower():
        raise ValueError('Robustness manifest SHA256 mismatch')
    manifest = json.loads(path.read_bytes())
    if manifest.get('schema_version') != SCHEMA or manifest.get('status') != 'prepared_pending_independent_review' or \
            manifest.get('declared_input_purpose') not in {'development_engineering', 'final_test_candidate'}:
        raise ValueError('Unsupported or incomplete robustness generation preparation')
    bundles = []
    for row in manifest['question_files']:
        source = (directory / row['path']).resolve()
        if source.parent != directory or source.suffix != '.json' or file_sha256(source) != row['sha256']:
            raise ValueError('Robustness payload changed or path escaped its prepared directory')
        bundle = json.loads(source.read_bytes())
        unit = execution_identity(bundle)
        if row['question_id'] != bundle['question']['question_id'] or row['execution_unit_id'] != unit['execution_unit_id']:
            raise ValueError('Robustness manifest unit identity differs')
        for context in bundle['contexts'].values():
            if text_sha256(context['context']) != context['context_sha256'] or \
                    canonical_sha256(context['source_records']) != context['source_records_sha256']:
                raise ValueError('Robustness context hash differs')
        for mode in bundle['modes'].values():
            if mode['context_key'] != 'dual' or text_sha256(mode['prompt']) != mode['prompt_sha256']:
                raise ValueError('Robustness prompt hash or source scope differs')
        bundles.append(bundle)
    inventory = unit_inventory(bundles)
    if manifest['unit_inventory'] != inventory or manifest['case_count'] != len(bundles) or \
            manifest['question_count'] != len({b['question']['question_id'] for b in bundles}):
        raise ValueError('Robustness inventory/counts changed; variants are not independent questions')
    return manifest, bundles


def validate_challenge_receipts(binding, manifest, bundles, frozen):
    """Recompute recorded resolutions; this does not authenticate people or labels."""
    control = binding.control
    if manifest.get('declared_input_purpose') != ('development_engineering' if control else 'final_test_candidate'):
        raise ValueError('Development robustness inputs cannot be promoted to formal execution')
    refs = binding.protocol.get('challenge_reviews', {})
    if set(refs) != {'packet', 'registration', 'R1', 'R2', 'decisions'}:
        raise ValueError('Original challenge packet, two independent receipts, registration and resolutions are required')
    paths = {key: binding.linked_bytes(ref)[0] for key, ref in refs.items()}
    if len(set(paths.values())) != 5:
        raise ValueError('Challenge raw input files must be separately preserved')
    packet = json.loads(paths['packet'].read_bytes())
    if packet.get('schema_version') != 'paired-robustness-review-packet-v1' or \
            packet.get('purpose') != ('engineering_control' if control else 'final_test') or \
            packet.get('validation_only') is not control or packet.get('unit_inventory') != unit_inventory(bundles):
        raise ValueError('Challenge review packet purpose or exact case inventory differs')
    registry = {}
    for row in read_csv(paths['registration'])[1]:
        role, person = row.get('reviewer_code'), row.get('actual_reviewer_id', '').strip()
        if role not in ('R1', 'R2') or role in registry or not person or person in ('R1', 'R2'):
            raise ValueError('Actual challenge reviewer declarations are incomplete')
        registry[role] = (person, day(row.get('registered_at', '')))
    if set(registry) != {'R1', 'R2'} or {r[0] for r in registry.values()} != binding.reviewer_ids or len({r[0] for r in registry.values()}) != 2:
        raise ValueError('Challenge reviewers must match the two registered source reviewers')
    by_unit = {r['execution_unit_id']: r for r in unit_inventory(bundles)}
    judgments = {}
    def values(row):
        data = {field: label(row.get(field)) for field in FIELDS}
        if any(data[field] not in ALLOWED[field] for field in FIELDS):
            raise ValueError('Missing or invalid challenge review label')
        return data
    for role in ('R1', 'R2'):
        rows = {}
        for row in read_csv(paths[role])[1]:
            identity = row.get('execution_unit_id')
            if identity not in by_unit or identity in rows or row.get('reviewer_id', '').strip() != registry[role][0] or \
                    row.get('payload_sha256') != by_unit[identity]['payload_sha256']:
                raise ValueError('Challenge review unit or actual reviewer differs')
            if any(not row.get(key, '').strip() for key in ('reason', 'source_or_version_basis', 'blind_status', 'reviewed_at')):
                raise ValueError('Challenge review needs actual reasons, source basis, exposure and date')
            reviewed = day(row['reviewed_at'])
            if not registry[role][1] <= reviewed <= frozen:
                raise ValueError('Challenge review chronology differs from registration/freeze')
            data = values(row)
            if any(v in ('unknown', 'unresolved') for v in data.values()) and not row.get('uncertainty_reason', '').strip():
                raise ValueError('Unknown challenge judgments need an uncertainty reason')
            rows[identity] = (data, reviewed)
        if set(rows) != set(by_unit):
            raise ValueError('Every baseline and variant needs both original independent judgments')
        judgments[role] = rows
    resolutions = {}
    for row in read_csv(paths['decisions'])[1]:
        identity = row.get('execution_unit_id')
        if identity not in by_unit or identity in resolutions or not row.get('decision_reason', '').strip() or \
                row.get('payload_sha256') != by_unit[identity]['payload_sha256']:
            raise ValueError('Missing, duplicate or unexplained challenge resolution')
        data = values(row)
        decided = day(row.get('decided_at', ''))
        a, a_date = judgments['R1'][identity]
        b, b_date = judgments['R2'][identity]
        if not max(a_date, b_date) <= decided <= frozen:
            raise ValueError('Challenge resolution predates independent receipts or postdates freeze')
        if row.get('resolution_method') == 'agreement':
            if not a == b == data:
                raise ValueError('Claimed challenge agreement differs from original judgments')
        elif row.get('resolution_method') == 'adjudicated':
            person = row.get('adjudicator_id', '').strip()
            if not person or person in binding.reviewer_ids or person in ('R1', 'R2'):
                raise ValueError('Disputed challenge needs an actually declared separate adjudicator')
        else:
            raise ValueError('Challenge resolution method must retain agreement or adjudication')
        if data['challenge_valid'] != 'yes':
            raise ValueError('Unresolved or rejected challenge cases cannot enter a formal comparison')
        resolutions[identity] = data
    if set(resolutions) != set(by_unit):
        raise ValueError('Every original baseline/variant resolution is required')
    baselines = {r['question_id']: resolutions[r['execution_unit_id']] for r in by_unit.values() if r['case_id'] == 'unperturbed'}
    for data in baselines.values():
        if data['expected_answerability'] not in {'answerable', 'partially_answerable'} or \
                data['expected_company_support'] != 'supported' or data['expected_regulation_support'] != 'supported':
            raise ValueError('A paired clean baseline needs independently recorded dual-source support')
    questions = {b['question']['question_id']: b['question'] for b in bundles}
    for identity, row in by_unit.items():
        if row['proposed_kind'] == 'wrong_version_candidate':
            date = binding.runtime.get('declared_target_date')
            if not isinstance(date, str) or date not in questions[row['question_id']]['query'] or \
                    baselines[row['question_id']]['expected_temporal_applicability'] != 'applicable' or \
                    resolutions[identity]['expected_temporal_applicability'] != 'not_applicable':
                raise ValueError('Version challenge needs public target date and recorded baseline/variant applicability')
            day(date)
    binding.challenge_raw_paths = paths
    binding.report.update(challenge_units_with_recorded_resolutions=len(resolutions),
        original_question_count=len(questions), robustness_variants_are_not_independent_questions=True,
        challenge_semantics_independently_authenticated=False)
    return resolutions
