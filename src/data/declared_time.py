"""Arithmetic on explicitly supplied date/version declarations; no legal acceptance."""
from __future__ import annotations

import datetime
import re


def parse_iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def bind_public_target_date(payload: dict, value: str | None, *, role: str | None = None) -> None:
    """Bind an explicitly declared company-event date already stated in the query.

    A date string alone is insufficient: report publication and assessment dates
    do not automatically identify when the underlying company conduct occurred.
    """
    if value is None:
        if role is not None:
            raise ValueError('A target-date role requires an explicit target date')
        return
    if role != 'company_event_date':
        raise ValueError('Temporal filtering requires an explicit company_event_date role')
    existing = payload.get('declared_target_date')
    if existing is not None and existing != value:
        raise ValueError('Declared target date conflicts with the already prepared retrieval date')
    existing_role = payload.get('declared_target_date_role')
    if existing_role is not None and existing_role != role:
        raise ValueError('Declared target-date role conflicts with the already prepared retrieval date')
    parsed = parse_iso_date(value)
    if parsed is None:
        raise ValueError('Declared target date must be a full ISO calendar date')
    year, month, day = parsed.year, parsed.month, parsed.day
    month_token = f'0?{month}' if month < 10 else str(month)
    day_token = f'0?{day}' if day < 10 else str(day)
    pattern = (rf'(?<!\d){year}(?:\s*[-/.]\s*{month_token}\s*[-/.]\s*{day_token}(?!\d)|'
               rf'\s*年\s*{month_token}\s*月\s*{day_token}\s*日)')
    if not re.search(pattern, payload['question']['query']):
        raise ValueError('Target date must already be explicit in the public query, not inferred from report year')
    payload['declared_target_date'] = value
    payload['declared_target_date_role'] = role
    payload['target_date_basis'] = ('caller_declared_company_event_date_already_explicit_in_public_query; '
                                    'not independent event verification; not independently event_verified')


def declared_interval_relation(record: dict, target_date) -> dict:
    """Compare an explicit date with a declared [start,end) interval, not law."""
    result = {'relation': 'unknown', 'reason': '', 'legal_applicability_verified': False,
              'upstream_metadata_reverified_here': False}
    target = parse_iso_date(target_date)
    if target is None:
        return {**result, 'reason': 'explicit_target_date_missing_or_invalid'}
    meta = record.get('meta', {})
    if meta.get('applicability_status') != 'version_interval_confirmed':
        return {**result, 'reason': 'version_interval_not_confirmed_in_input_metadata'}
    if not isinstance(meta.get('version_id'), str) or not meta['version_id'].strip():
        return {**result, 'reason': 'version_identity_missing'}
    start = parse_iso_date(meta.get('effective_from'))
    if start is None:
        return {**result, 'reason': 'interval_start_missing_or_invalid'}
    raw_end = meta.get('effective_to_exclusive')
    if raw_end is not None:
        end = parse_iso_date(raw_end)
        if end is None or end <= start:
            return {**result, 'reason': 'exclusive_interval_end_invalid'}
        if target < start or target >= end:
            return {**result, 'relation': 'outside_declared_interval', 'reason': 'date_outside_start_inclusive_end_exclusive'}
        return {**result, 'relation': 'within_declared_interval', 'reason': 'arithmetic_only_given_declared_metadata'}
    snapshot = parse_iso_date(meta.get('metadata_as_of_date'))
    if meta.get('interval_end_status') != 'open_as_of_snapshot' or snapshot is None or snapshot < start:
        return {**result, 'reason': 'interval_end_unknown_not_assumed_open_forever'}
    if target < start:
        return {**result, 'relation': 'outside_declared_interval', 'reason': 'date_before_declared_start'}
    if target > snapshot:
        return {**result, 'reason': 'target_after_metadata_snapshot'}
    return {**result, 'relation': 'within_declared_interval', 'reason': 'arithmetic_only_through_declared_snapshot'}
