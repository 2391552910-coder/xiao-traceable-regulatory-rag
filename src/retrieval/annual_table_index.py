"""Offline FTS5 retrieval over source-bound governance table row views."""
from __future__ import annotations

import copy
import json
import re
import sqlite3
from dataclasses import asdict
from collections import defaultdict
from pathlib import Path

from src.data.annual_tables import VERSION, compact, digest, field_columns, committee_labels, parse_date
from src.data.clause_splitter import Chunk


def _member_names(text):
    text = re.sub(r'[（(][^）)]*[）)]', '', compact(text))
    return [part for part in (p.strip('。．.：:') for p in re.split(r'[、,，;；/]', text))
            if re.fullmatch(r'[\u3400-\u9fff·]{2,8}', part)]


def _render_views(labels,pages,views,category):
    text = ('结构化年报表格（布局重建字段，非PDF连续引文）\n'
            + '委员会范围：' + '、'.join(label+'委员会' for label in labels)
            + '\n物理页：' + '、'.join(map(str,pages)) + '\n')
    field_labels=dict(committee='委员会名称',members='成员情况',date='召开日期',count='召开会议次数',
                      name='董事姓名',position='职务',meeting_title='会议名称',
                      meeting_opinions='提出的重要意见和建议',
                      meeting_other_duties='其他履行职责情况',meeting_dissent='异议事项情况')
    for view in views:
        label=field_labels.get(view['field'])
        if view['field']=='date' and category!='committee_meetings':
            label='任职变动日期（不是会议日期）'
        if label is None:
            label='、'.join(committee_labels(view['column_header']))+'委员会出席次数/应出席次数'
        text+=label+'（原单元格布局文本）：'+view['text']+'\n'
    return text.rstrip()


def _derive_fields(views,category,report_year):
    structured=dict(member_name_candidates=[],meeting_date_candidates=[],meeting_count_candidates=[],out_of_period_date_candidates=[])
    date_values=[parse_date(v['text']) for v in views if v['field']=='date']
    outside=[d for d in date_values if d and int(d[:4])!=report_year]
    for view in views:
        if view['field'] in ('members','name') and not outside:
            structured['member_name_candidates'].extend(_member_names(view['text']))
        elif view['field']=='date' and category=='committee_meetings':
            value=parse_date(view['text'])
            if value and int(value[:4])==report_year:
                structured['meeting_date_candidates'].append(value)
        elif view['field']=='count' and not outside and re.fullmatch(r'\d{1,3}',compact(view['text'])):
            structured['meeting_count_candidates'].append(int(compact(view['text'])))
    structured['out_of_period_date_candidates']=outside
    return {key:sorted(set(value)) for key,value in structured.items()}


def row_units(document):
    """Return bounded field views with complete cell provenance, not free prose."""
    source = document['source']
    cells = {c['cell_id']: c for table in document['tables'] for c in table['cells']}
    chunks, review = [], []
    for chain in document['logical_tables']:
        columns = field_columns(chain['headers'])
        for row in chain['rows']:
            labels = row['committee_labels']
            if not labels:
                review.append(dict(row_id=row['row_id'], pages=sorted({cells[c]['page'] for ids in row['parts'] for c in ids}),
                                   reason='committee_scope_unresolved', category=chain['category']))
                continue
            selected = {}
            for field in ('committee', 'members', 'date', 'count', 'position'):
                if field in columns:
                    selected[field] = columns[field]
            if chain['category'] == 'personnel_changes' and 'name' in columns:
                selected['name'] = columns['name']
            if chain['category'] == 'committee_attendance':
                selected['name'] = columns.get('name', 0)
                for i, header in enumerate(chain['headers']):
                    if set(committee_labels(header)) & set(labels):
                        selected['attendance_' + str(i)] = i
            if 'meeting_content' in columns:
                selected['meeting_title'] = columns['meeting_content']
            if chain['category'] == 'committee_meetings':
                for field in ('meeting_opinions','meeting_other_duties','meeting_dissent'):
                    if field in columns:
                        selected[field] = columns[field]
            if not selected and row['values']:
                # Unknown layouts remain available to reviewers; never pretend
                # their fields were identified merely because a name matched.
                review.append(dict(row_id=row['row_id'], pages=[row['page']],
                                   reason='field_headers_unresolved', category=chain['category']))
                continue
            views = []
            for field, i in selected.items():
                if i >= len(row['values']) or not compact(row['values'][i]):
                    continue
                text = row['values'][i]
                end = len(text)
                if field == 'meeting_title':
                    # Keep agenda text even when the cell begins with “审议”.
                    # Truncating at the first marker erased the entire title in
                    # common annual-report rows such as “审议《季度报告》”.
                    end = min(len(text), 180)
                views.append(dict(field=field, text=text[:end], cell_ids=list(row['parts'][i]),
                                  column_header=chain['headers'][i] if i < len(chain['headers']) else '',
                                  column_header_cell_ids=chain.get('header_column_parts',[])[i] if i < len(chain.get('header_column_parts',[])) else [],
                                  layout_text_start=0, layout_text_end=end,
                                  cross_page_cell_parts=len({cells[c]['page'] for c in row['parts'][i]}) > 1))
            if not views:
                continue
            row_cell_ids = list(dict.fromkeys(c for v in views for c in v['cell_ids']))
            pages = sorted({cells[c]['page'] for c in row_cell_ids})
            text=_render_views(labels,pages,views,chain['category'])
            structured=_derive_fields(views,chain['category'],source['year'])
            cid = f"ATBL-{source['stock']}-{source['year']}-" + digest([VERSION, row['row_id'], views])[:20]
            meta = dict(corpus_type='annual_report', stock_code=source['stock'], report_year=source['year'],
                        company_name=source['company'], source_pdf_sha256=source['sha256'],
                        physical_pdf_page_1based=pages[0], physical_pdf_pages_1based=pages,
                        system_corpus_input=True, source_representation='table_field_view',
                        continuous_verbatim_quote=False, parser_version=VERSION,
                        table_chain_id=chain['chain_id'], table_ids=chain['table_ids'],
                        table_category=chain['category'], logical_row_id=row['row_id'],
                        committee_labels=labels, committee_scope_basis=row['scope_basis'],
                        split_row_merged=row['split_row_merged'], field_views=views,
                        source_cells=[copy.deepcopy(cells[c]) for c in row_cell_ids],
                        header_source_cells=[copy.deepcopy(cells[c]) for c in chain['header_cell_ids']],
                        structured_fields=structured, independent_human_validation=False)
            meta['temporal_scope']='outside_reporting_year' if structured['out_of_period_date_candidates'] else 'annual_report_scope_with_no_detected_date_conflict'
            chunk = Chunk(cid, f"HELD-{source['stock']}-{source['year']}",
                                f"{source['company']}{source['year']}年年度报告（表格字段）",
                                'annual_report', source['url'], None, text.rstrip(), meta=meta)
            verify_field_views(chunk)
            chunks.append(chunk)
    return chunks, review


def verify_field_views(chunk):
    """Reject field text not reproducible from its explicitly cited cell parts."""
    meta = chunk.meta
    cells = {c['cell_id']:c for c in meta['source_cells']+meta['header_source_cells']}
    for view in meta['field_views']:
        source_text = '\n'.join(cells[cid]['text'] for cid in view['cell_ids'])
        if source_text[view['layout_text_start']:view['layout_text_end']] != view['text']:
            raise ValueError('Field view does not reproduce from its source cell parts')
        if view['column_header_cell_ids']:
            header_text = '\n'.join(cells[cid]['text'] for cid in view['column_header_cell_ids'])
            if header_text != view['column_header']:
                raise ValueError('Column header is not bound to its original cells')
    if _render_views(meta['committee_labels'],meta['physical_pdf_pages_1based'],meta['field_views'],meta['table_category'])!=chunk.text:
        raise ValueError('Serialized evidence text differs from its source-bound field views')
    if _derive_fields(meta['field_views'],meta['table_category'],meta['report_year'])!=meta['structured_fields']:
        raise ValueError('Structured candidates differ from their source-bound field views')
    expected_scope='outside_reporting_year' if meta['structured_fields']['out_of_period_date_candidates'] else 'annual_report_scope_with_no_detected_date_conflict'
    if meta.get('temporal_scope')!=expected_scope:
        raise ValueError('Temporal scope differs from source-bound dates')
    return True


def build_index(documents, path):
    import jieba
    path = Path(path)
    if path.exists():
        raise FileExistsError('Do not overwrite a table index')
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks, review = [], []
    for document in documents:
        units, pending = row_units(document)
        chunks.extend(units)
        review.extend(dict(stock_code=document['source']['stock'], report_year=document['source']['year'], **r) for r in pending)
    ids = [c.chunk_id for c in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate structured row chunk IDs')
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE chunks(position INTEGER PRIMARY KEY,payload TEXT)')
        db.execute('CREATE VIRTUAL TABLE evidence USING fts5(tokens,scope UNINDEXED,committee UNINDEXED,category UNINDEXED,chunk_index UNINDEXED)')
        for i, chunk in enumerate(chunks):
            db.execute('INSERT INTO chunks VALUES (?,?)', (i, json.dumps(asdict(chunk), ensure_ascii=False)))
            tokens = ' '.join(t for t in jieba.cut(chunk.text) if t.strip())
            for label in chunk.meta['committee_labels']:
                db.execute('INSERT INTO evidence VALUES (?,?,?,?,?)',
                           (tokens, f"{chunk.meta['stock_code']}-{chunk.meta['report_year']}",
                            label, chunk.meta['table_category'], i))
    return chunks, review


class AnnualTableIndex:
    def __init__(self, path):
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise FileNotFoundError(self.path)

    def search(self, question, query, *, k=24, committee='审计', balanced=False):
        import jieba
        if type(k) is not int or not 1 <= k <= 100:
            raise ValueError('k must be in [1,100]')
        if not re.fullmatch(r'\d{6}', question.get('stock_code', '')) or type(question.get('report_year')) is not int:
            raise ValueError('Exact company/year is required')
        terms = [t.strip() for t in jieba.cut(query) if t.strip() and any(c.isalnum() for c in t)][:60]
        if not terms:
            return []
        match = ' OR '.join('"' + t.replace('"', '""') + '"' for t in terms)
        with sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True) as db:
            records = db.execute(
                'SELECT chunk_index,bm25(evidence),category FROM evidence WHERE evidence MATCH ? '
                'AND scope=? AND committee=? ORDER BY bm25(evidence),CAST(chunk_index AS INTEGER) LIMIT 100',
                (match, f"{question['stock_code']}-{question['report_year']}", committee)).fetchall()
            if balanced:
                groups = defaultdict(list)
                for record in records:
                    groups[record[2]].append(record)
                order = ['personnel_changes', 'committee_roster', 'committee_meetings', 'committee_attendance']
                order += sorted(set(groups) - set(order))
                records = [groups[g][i] for i in range(max(map(len, groups.values()), default=0))
                           for g in order if i < len(groups[g])]
            results, seen = [], set()
            for position, score, _ in records:
                if position in seen:
                    continue
                seen.add(position)
                chunk = Chunk(**json.loads(db.execute('SELECT payload FROM chunks WHERE position=?', (position,)).fetchone()[0]))
                verify_field_views(chunk)
                if chunk.meta.get('temporal_scope')=='outside_reporting_year':
                    continue
                results.append((chunk, -float(score)))
                if len(results) == k:
                    break
        return results

