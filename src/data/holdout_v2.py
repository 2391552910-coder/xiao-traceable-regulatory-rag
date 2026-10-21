"""Release checks requiring an explicit development inventory and scoped task protocol."""
import re
from src.data.holdout import release_errors, normalized_query


def release_errors_v2(rows, registry):
    errors = []
    if not registry or not registry.get('queries') or not registry.get('input_sha256'):
        errors.append(('', 'development_inventory_required'))
        registry = registry or {}
    if any(not re.fullmatch(r'[0-9a-f]{64}', h) for h in registry.get('input_sha256', {}).values()):
        errors.append(('', 'invalid_development_inventory_hash'))
    errors.extend(release_errors(rows, registry.get('queries', []),
                                 registry.get('family_ids', []), registry.get('company_ids', [])))
    seen = set()
    for row in rows:
        qid = row.get('query_id', '')
        if qid in seen:
            errors.append((qid, 'duplicate_query_id'))
        seen.add(qid)
        if row.get('dimension') not in {'D1', 'D2', 'D3', 'D4'}:
            errors.append((qid, 'invalid_dimension'))
        if row.get('development_family_matches'):
            errors.append((qid, 'documented_development_family_overlap'))
        if row.get('task_type') != 'regulatory_retrieval':
            errors.append((qid, 'separate_task_protocol_required'))
        if row.get('status') != 'human_reviewed_release_candidate':
            errors.append((qid, 'candidate_not_release_ready'))
        fingerprints = row.get('evidence_sha256', {})
        if not row.get('evidence_ids') or any(not re.fullmatch(r'[0-9a-f]{64}', fingerprints.get(cid, ''))
                                               for cid in row.get('evidence_ids', [])):
            errors.append((qid, 'evidence_hashes_required'))
        if not row.get('human_review_record_sha256') or not re.fullmatch(r'[0-9a-f]{64}', row['human_review_record_sha256']):
            errors.append((qid, 'auditable_human_review_record_required'))
    return errors
