"""Resolve recorded source reviews without authenticating people or freezing gold."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime

from src.generation.comparison import canonical_sha256, public_question
from src.metrics.span_retrieval import verify_location

FLAGS = ('source_identity_correct', 'quote_and_location_correct', 'evidence_role_correct',
         'target_quote_scope_correct')
FIELDS = FLAGS + ('relevance_grade',)
DECISION_FIELDS = ('query_id', 'target_id', *FIELDS, 'resolution_method',
                   'adjudicator_id', 'decision_reason', 'decided_at')
PURPOSES = ('development', 'final_test', 'engineering_control')
UNIT_ROLES = {'annual_evidence': 'annual_report', 'regulation_evidence': 'regulation'}


def day(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('An actual ISO calendar date is required')
    value = value.strip()
    result = datetime.fromisoformat(value.replace('Z', '+00:00')).date() if 'T' in value or ' ' in value else date.fromisoformat(value)
    if result > date.today():
        raise ValueError('A self-reported review date is in the future')
    return result


def label(value):
    return str(value or '').strip().casefold()


def resolve_target_reviews(packet, registrations, reviews, decisions, verifier):
    if packet.get('schema_version') != 'source-span-target-review-packet-v1' or packet.get('purpose') not in PURPOSES:
        raise ValueError('Unsupported source review packet or purpose')
    questions = [public_question(q) for q in packet['questions']]
    by_query = {q['question_id']: q for q in questions}
    if not questions or len(by_query) != len(questions):
        raise ValueError('Review packet questions must be nonempty and unique')
    candidates = {}
    for c in packet['candidates']:
        key = c['query_id'], c['target_id']
        if key in candidates or key[0] not in by_query or not isinstance(key[1], str) or not key[1].strip():
            raise ValueError('Duplicate or invalid review candidate identity')
        if c['unit_type'] not in UNIT_ROLES or c['source'].get('role') != UNIT_ROLES[c['unit_type']] or \
                c['source'].get('query_id') != key[0] or c['source'].get('evidence_id') != key[1]:
            raise ValueError('Review candidate source role and unit identity disagree')
        candidates[key] = c
    if not candidates:
        raise ValueError('An empty candidate packet cannot establish reviewed targets')
    issues, registry, people, indexed, resolutions = [], {}, [], {}, {}
    for row in registrations:
        role = row.get('reviewer_code', '').strip()
        person = row.get('actual_reviewer_id', '').strip()
        if role not in ('R1', 'R2') or role in registry or not person or person in ('R1', 'R2'):
            issues.append('Registration requires unique R1/R2 roles and non-placeholder actual IDs')
            continue
        try:
            registered = day(row.get('registered_at', ''))
        except ValueError as error:
            issues.append(str(error)); continue
        registry[role] = (person, registered)
        people.append(person)
    if set(registry) != {'R1', 'R2'} or len(set(people)) != 2:
        issues.append('Two different registered self-reported reviewer IDs are required')
    if set(reviews) != {'R1', 'R2'}:
        issues.append('Both raw source-review submissions are required')
    for role in ('R1', 'R2'):
        found = {}
        for row in reviews.get(role, []):
            unit_type = row.get('unit_type')
            if unit_type == 'question':
                if row.get('query_id') not in by_query or row.get('unit_id') != row.get('query_id'):
                    issues.append(f'{role}: unrelated question assessment in submission')
                continue
            key = row.get('query_id'), row.get('unit_id')
            if key not in candidates or key in found or unit_type != candidates[key]['unit_type']:
                issues.append(f'{role}: duplicate, changed or foreign source review unit'); continue
            found[key] = row
            if role not in registry or row.get('reviewer_id', '').strip() != registry[role][0]:
                issues.append(f'{role}: row reviewer differs from registration')
            for field in ('reason', 'blind_status', 'reviewed_at'):
                if not row.get(field, '').strip(): issues.append(f'{role}/{key}: blank {field}')
            try:
                reviewed = day(row.get('reviewed_at', ''))
                if role in registry and reviewed < registry[role][1]:
                    issues.append(f'{role}/{key}: review predates registration')
            except ValueError as error:
                issues.append(f'{role}/{key}: {error}')
            if any(label(row.get(f)) not in {'yes', 'no', 'u'} for f in FLAGS) or \
                    label(row.get('relevance_grade')) not in {'0', '1', '2', 'u'}:
                issues.append(f'{role}/{key}: missing or invalid source flags/grade')
            if any(label(row.get(f)) == 'u' for f in FIELDS) and not row.get('uncertainty_reason', '').strip():
                issues.append(f'{role}/{key}: unknown needs an uncertainty reason')
        if set(found) != set(candidates): issues.append(f'{role}: every candidate needs one independent row')
        indexed[role] = found
    for row in decisions:
        key = row.get('query_id'), row.get('target_id')
        if key not in candidates or key in resolutions:
            issues.append('Duplicate or foreign final resolution unit'); continue
        resolutions[key] = row
        if any(label(row.get(f)) not in {'yes', 'no', 'u'} for f in FLAGS) or \
                label(row.get('relevance_grade')) not in {'0', '1', '2', 'u'}:
            issues.append(f'{key}: missing or invalid resolved source flags/grade')
        method = row.get('resolution_method', '')
        if method not in {'agreement_confirmed', 'adjudicated'}:
            issues.append(f'{key}: an explicit resolution method is required')
        if not row.get('adjudicator_id', '').strip() or row.get('adjudicator_id', '').strip() in ('R1', 'R2') or \
                not row.get('decision_reason', '').strip():
            issues.append(f'{key}: actual resolver ID and reason are required')
        try:
            decided = day(row.get('decided_at', ''))
            for role in ('R1', 'R2'):
                if key in indexed[role] and decided < day(indexed[role][key].get('reviewed_at', '')):
                    issues.append(f'{key}: resolution predates a review')
        except ValueError as error:
            issues.append(f'{key}: {error}')
        if method == 'agreement_confirmed' and all(key in indexed[r] for r in ('R1', 'R2')):
            if any(label(indexed[r][key].get(f)) != label(row.get(f)) for r in ('R1', 'R2') for f in FIELDS):
                issues.append(f'{key}: agreement cannot erase a disagreement or unknown')
    if set(resolutions) != set(candidates):
        issues.append('Every candidate needs a final resolution; candidates cannot silently disappear')
    result = {'schema_version': 'resolved-source-span-targets-v1', 'purpose': packet['purpose'],
        'dataset_version': packet.get('dataset_version'), 'public_questions': questions,
        'question_sha256': {qid: canonical_sha256(q) for qid, q in by_query.items()},
        'candidate_count': len(candidates), 'issues': issues, 'resolved_records': [],
        'status': 'pending_reviews_or_resolution', 'unknown_or_unresolved_records': 0,
        'human_identity_authenticated': False, 'actual_blinding_verified': False,
        'independent_reviews_completed_by_tool': 0, 'accepted_as_gold': False,
        'formal_final_test_frozen': False, 'formal_metrics': None,
        'target_scope': 'explicitly reviewed supplied pool;not an exhaustive corpus relevance judgment',
        'target_boundary_confirmation_required': True,
        'a_relevant_chunk_is_not_automatically_a_suitable_target_quote': True,
        'rejected_source_records_are_not_negative_relevance_labels': True}
    if issues:
        return result
    seen_locations = set()
    for key, c in candidates.items():
        resolution = resolutions[key]
        values = {f: label(resolution[f]) for f in FIELDS}
        unknown = any(v == 'u' for v in values.values())
        usable = not unknown and all(values[f] == 'yes' for f in FLAGS)
        record = {'query_id': key[0], 'target_id': key[1], 'source': c['source'],
            'reviewer_ids_as_reported': people, 'review_record_values': {r: {f: indexed[r][key][f] for f in FIELDS} for r in ('R1', 'R2')},
            'resolved_values': values, 'resolution_record': resolution, 'usable_source_location': usable,
            'location': None, 'status': 'unresolved' if unknown else 'usable' if usable else 'not_usable_as_target'}
        if unknown:
            result['unknown_or_unresolved_records'] += 1
        if usable:
            location = verify_location(c['source'], verifier)
            if asdict(location) != c['location']:
                raise ValueError('Original review coordinate frame differs from freshly verified source')
            identity = key[0], location
            if identity in seen_locations:
                raise ValueError('Duplicate source target locations would inflate the recall denominator')
            seen_locations.add(identity)
            record['location'] = asdict(location)
        result['resolved_records'].append(record)
    result['source_files_rechecked'] = verifier.recheck_files()
    result['status'] = ('resolved_with_unknowns_not_scored' if result['unknown_or_unresolved_records'] else
                        'resolved_review_records_not_formal_freeze')
    return result
