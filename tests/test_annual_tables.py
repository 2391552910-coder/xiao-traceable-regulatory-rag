import copy
import json
from pathlib import Path

import pdfplumber
import pytest

from src.data.annual_tables import (
    compact, committee_labels, continuation_decision, extract_document,
    extract_page_tables, extract_pdfium_pages, file_sha256, parse_date,
    select_governance_pages, stitch_tables, verify_cell, row_scope, classify_headers,
)
from src.retrieval.annual_table_index import AnnualTableIndex, build_index, row_units,verify_field_views,_derive_fields

FIXTURE = Path(__file__).parent / 'fixtures/annual_tables_synthetic_v1.pdf'


@pytest.fixture(scope='module')
def parsed():
    source = dict(stock='000001', year=2024, company='合成测试公司', file=FIXTURE.name,
                  url='https://example.invalid/synthetic.pdf', sha256=file_sha256(FIXTURE), pages=9)
    pages = extract_pdfium_pages(FIXTURE)
    return extract_document(FIXTURE, source, pages,all_pages=True)


def chain_on(parsed, page):
    return next(c for c in parsed['logical_tables'] if c['pages'][0] == page)


def test_real_pdf_split_date_and_name_merge_preserves_two_page_parts(parsed):
    chain = chain_on(parsed, 1)
    assert chain['pages'] == [1, 2]
    assert chain['split_rows_merged'] == 1
    row = chain['rows'][0]
    assert compact(row['values'][0]) == '审计委员会'
    assert compact(row['values'][1]) == '姚兴田、于舒天'
    assert parse_date(row['values'][2]) == '2024-09-19'
    cells = {c['cell_id']: c for t in parsed['tables'] for c in t['cells']}
    assert {cells[c]['page'] for c in row['parts'][2]} == {1, 2}
    assert row['committee_labels'] == ['审计']
    assert len(chain['rows']) == 2


def test_repeated_header_does_not_become_data_or_merge_complete_dates(parsed):
    chain = chain_on(parsed, 3)
    assert chain['pages'] == [3, 4]
    assert chain['repeated_headers_removed_from_logical_rows'] == 1
    assert chain['split_rows_merged'] == 0
    assert [parse_date(r['values'][2]) for r in chain['rows']] == ['2024-03-21', '2024-04-19']


def test_borderless_alignment_excludes_other_committee_and_zero_expected_count(parsed):
    chain = chain_on(parsed, 5)
    assert chain['category'] == 'committee_attendance'
    audit_names = [compact(r['values'][0]) for r in chain['rows'] if '审计' in r['committee_labels']]
    assert audit_names == ['张一']
    assert len(chain['rows']) == 3


def test_slash_financial_matrix_is_not_attendance():
    with pdfplumber.open(FIXTURE) as pdf:
        assert extract_page_tables(pdf.pages[6], file_sha256(FIXTURE)) == []


def test_blank_text_page_is_explicit_ocr_gap(parsed):
    page = next(p for p in parsed['parsed_pages'] if p['page'] == 6)
    assert page['status'] == 'requires_ocr_no_text_layer'
    assert page['tables'] == 0


def test_every_cell_roundtrips_against_new_pdf_parse(parsed):
    with pdfplumber.open(FIXTURE) as pdf:
        for table in parsed['tables']:
            for cell in table['cells']:
                assert verify_cell(pdf.pages[cell['page'] - 1], cell)


@pytest.mark.parametrize('change', ['text', 'range', 'hash', 'page'])
def test_source_cell_tampering_is_rejected(parsed, change):
    cell = copy.deepcopy(next(c for t in parsed['tables'] for c in t['cells'] if c['char_count']))
    page = cell['page']
    if change == 'text': cell['text'] += ' fabricated'
    elif change == 'range': cell['char_index_ranges'] = [[0, 1]]
    elif change == 'hash': cell['raw_char_text_sha256'] = '0' * 64
    elif change == 'page': cell['page'] += 1
    with pdfplumber.open(FIXTURE) as pdf, pytest.raises(ValueError):
        verify_cell(pdf.pages[page - 1], cell)


@pytest.mark.parametrize('change,reason', [
    ('page_gap', 'not_consecutive_physical_pages'), ('columns', 'different_column_count'),
    ('geometry', 'column_geometry_mismatch'), ('not_bottom', 'left_table_not_at_page_end'),
    ('not_top', 'right_table_not_at_page_start'), ('headers', 'different_repeated_headers'),
    ('method', 'unsupported_continuation_method'), ('category', 'table_category_changed'),
    ('new_section', 'new_committee_section_heading'),
])
def test_continuation_negative_controls(parsed, change, reason):
    left = copy.deepcopy(next(t for t in parsed['tables'] if t['page'] == 3))
    right = copy.deepcopy(next(t for t in parsed['tables'] if t['page'] == 4))
    left['caption'] = '（一）审计委员会'
    if change == 'page_gap': right['page'] += 1
    elif change == 'columns': right['column_bounds'].pop(1)
    elif change == 'geometry': right['column_bounds'][1] += 20
    elif change == 'not_bottom': left['bbox'][3] = 500
    elif change == 'not_top': right['bbox'][1] = 300
    elif change == 'headers': right['headers'] = ['项目', '数值', '币种', '说明']
    elif change == 'method': right['method'] = 'borderless_attendance_alignment'
    elif change == 'category': right['category'] = 'personnel_changes'
    elif change == 'new_section': right['caption'] = '（二）提名委员会'
    decision = continuation_decision(left, right)
    assert not decision['accepted'] and reason in decision['reasons']


def test_input_tables_are_not_mutated_by_stitch(parsed):
    before = copy.deepcopy(parsed['tables'])
    stitch_tables(parsed['tables'])
    assert parsed['tables'] == before


@pytest.mark.parametrize('value,expected', [('2024\n年9\n月19日','2024-09-19'),
                                         ('2024年2月30日',None), ('9月19日',None),
                                         ('2023年12月31日','2023-12-31'), ('2024年9',None)])
def test_calendar_parsing_does_not_invent_year_or_invalid_day(value, expected):
    assert parse_date(value) == expected


def test_selection_uses_public_terms_and_fixed_neighbors_not_labels():
    pages = [dict(page=i, text='审计委员会' if i == 3 else '其他文字') for i in range(1,6)]
    selection = select_governance_pages(pages)
    assert selection['seed_pages'] == [3] and selection['selected_pages'] == [2,3,4]
    assert selection['reference_labels_used'] is False
    with pytest.raises(ValueError): select_governance_pages(pages[::-1])


def test_actual_pdf_digest_must_match_source(parsed):
    source = copy.deepcopy(parsed['source']);source['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='digest'):
        extract_document(FIXTURE, source, extract_pdfium_pages(FIXTURE))


def test_row_views_keep_cross_page_source_and_do_not_modify_document(parsed):
    before = copy.deepcopy(parsed)
    chunks, _ = row_units(parsed)
    assert parsed == before
    split = next(c for c in chunks if c.meta['split_row_merged'])
    assert split.meta['physical_pdf_pages_1based'] == [1,2]
    assert split.meta['structured_fields']['member_name_candidates'] == ['于舒天','姚兴田']
    assert split.meta['structured_fields']['meeting_date_candidates'] == ['2024-09-19']
    assert split.meta['continuous_verbatim_quote'] is False
    assert split.meta['independent_human_validation'] is False


def test_personnel_date_not_misreported_as_meeting_and_name_is_included(parsed):
    d = copy.deepcopy(parsed)
    c = d['logical_tables'][0]
    c.update(headers=['姓名','职务','变动日期','变动类型'], category='personnel_changes')
    c['rows'] = [copy.deepcopy(c['rows'][0])]
    c['rows'][0].update(values=['刘俊勇','审计委员会主任委员','2024年2月2日','离任'], committee_labels=['审计'])
    cells = [dict(cell_id='E'+str(i),page=1,text=value) for i,value in enumerate(c['rows'][0]['values'])]
    header_cells = [dict(cell_id='H'+str(i),page=1,text=value) for i,value in enumerate(c['headers'])]
    c['rows'][0]['parts'] = [[cell['cell_id']] for cell in cells]
    c['header_cell_ids'] = [cell['cell_id'] for cell in header_cells]
    c['header_column_parts'] = [[cell['cell_id']] for cell in header_cells]
    d['tables'] = [dict(cells=cells+header_cells)]
    d['logical_tables'] = [c]
    chunks, _ = row_units(d)
    assert chunks[0].meta['structured_fields']['member_name_candidates'] == ['刘俊勇']
    assert chunks[0].meta['structured_fields']['meeting_date_candidates'] == []
    assert '不是会议日期' in chunks[0].text


def test_field_text_not_bound_to_cell_parts_is_rejected(parsed):
    d=copy.deepcopy(parsed)
    d['logical_tables'][0]['rows'][0]['values'][0] += ' fabricated'
    with pytest.raises(ValueError,match='source cell parts'):
        row_units(d)


def test_index_scope_year_committee_stable_order_and_no_overwrite(parsed, tmp_path):
    documents = [copy.deepcopy(parsed), copy.deepcopy(parsed)]
    documents[1]['source']['year'] = 2023
    path = tmp_path / 'tables.sqlite'
    chunks, _ = build_index(documents, path)
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    index = AnnualTableIndex(path)
    q = dict(stock_code='000001', report_year=2024)
    hits = index.search(q, '审计委员会 成员 会议 日期', balanced=True)
    assert hits and all(c.meta['report_year']==2024 and '审计' in c.meta['committee_labels'] for c,_ in hits)
    assert index.search(dict(stock_code='999999', report_year=2024), '审计委员会') == []
    assert [(c.chunk_id,s) for c,s in hits] == [(c.chunk_id,s) for c,s in index.search(q, '审计委员会 成员 会议 日期', balanced=True)]
    with pytest.raises(FileExistsError): build_index([parsed], path)


def test_compact_and_committee_matching_do_not_treat_agenda_audit_as_ownership():
    assert committee_labels('审\n计委员会') == ['审计']
    assert compact('審計委員會') == '审计委员会'


def test_other_entity_appointments_never_become_focal_company_membership():
    headers=['任职人员姓名','其他单位名称','在其他单位担任的职务','任期起始日期']
    category=classify_headers(headers)
    assert category=='external_entity_appointments'
    row=dict(values=['张三','其他公司','审计委员会主任','1996年1月1日'])
    labels,basis=row_scope(row,dict(headers=headers,category=category))
    assert labels==[] and 'not_focal_company' in basis
    assert parse_date('1996年1月1日')=='1996-01-01'


def test_blank_key_agenda_continuation_from_actual_pdf(parsed):
    chain=chain_on(parsed,8)
    assert chain['pages']==[8,9] and chain['split_rows_merged']==1
    assert len(chain['rows'])==2
    row=chain['rows'][0]
    assert row['split_row_merge_basis']=='blank_key_cells_with_continued_agenda_at_verified_page_boundary'
    assert '12.开展工作13.延续内容' in compact(row['values'][2])
    assert parse_date(row['values'][1])=='2024-09-19'


def test_fully_parsed_outside_year_dates_are_retained_as_gaps_not_current_facts():
    views=[dict(field='members',text='张三'),dict(field='date',text='2023年9月19日')]
    fields=_derive_fields(views,'committee_meetings',2024)
    assert fields['meeting_date_candidates']==[]
    assert fields['member_name_candidates']==[]
    assert fields['out_of_period_date_candidates']==['2023-09-19']
    fields=_derive_fields([dict(field='name',text='张三'),dict(field='date',text='2023年9月19日')],'personnel_changes',2024)
    assert fields['member_name_candidates']==[]


@pytest.mark.parametrize('change',['body','derived'])
def test_serialized_unit_body_and_derived_candidates_cannot_drift(parsed,change):
    chunks,_=row_units(parsed);chunk=copy.deepcopy(chunks[0])
    if change=='body':chunk.text+=' fabricated'
    else:chunk.meta['structured_fields']['member_name_candidates'].append('伪造名字')
    with pytest.raises(ValueError):verify_field_views(chunk)


def test_agenda_mention_of_audit_does_not_transfer_meeting_ownership():
    chain=dict(headers=['召开日期','会议内容'],category='committee_meetings',caption='')
    row=dict(values=['2024年9月19日','审议关于审计委员会第十次会议的报告'])
    labels,basis=row_scope(row,chain)
    assert labels==[]
