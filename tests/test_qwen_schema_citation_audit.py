from scripts.audit_qwen_schema_citations_20261029 import audit


def response():
    return {'members': ['甲'], 'meeting_count': 1, 'meeting_dates': ['2024-01-01'],
            'citations': {x: ['A1'] for x in ('members', 'meeting_count', 'meeting_dates')},
            'limitations': []}


def test_valid_types_do_not_prove_valid_citation_ids():
    value = response()
    value['citations']['members'] = ['2024-01-01']
    result = audit(value, {'A1'})
    assert result['schema_valid']
    assert result['fields']['members']['malformed'] == ['2024-01-01']
    assert not result['all_present_values_cited']


def test_unknown_and_missing_citations_are_not_resolved():
    value = response()
    value['citations']['meeting_count'] = ['A2']
    value['citations']['meeting_dates'] = []
    result = audit(value, {'A1'})
    assert result['fields']['meeting_count']['unknown'] == ['A2']
    assert not result['all_fields_nonempty_and_resolved']
    assert not result['all_present_values_cited']
    value['meeting_count'] = None
    value['meeting_dates'] = []
    value['citations']['meeting_count'] = []
    result = audit(value, {'A1'})
    assert result['all_present_values_cited']
    assert not result['all_fields_nonempty_and_resolved']


def test_bad_citation_structure_is_not_silently_repaired():
    value = response()
    value['citations']['members'] = 1
    result = audit(value, {'A1'})
    assert not result['schema_valid']
    assert result['fields']['members']['raw'] == 1
    assert not result['all_present_values_cited']
