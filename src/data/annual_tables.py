"""Source-bound governance tables and conservative physical-page continuation.

No model, network or reference-label access. Cell text is reconstructed layout
text; raw PDF character indices and hashes remain the auditable source. Inference
about a reporting-period membership union still requires source adjudication.
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path

VERSION = 'annual_governance_tables_v1_4'
COMMITTEES = ('审计', '提名', '薪酬', '战略', '风险', '关联交易', '消费者权益', '可持续发展')
HEADER_WORDS = ('委员会名称', '委员会类别', '成员情况', '成员姓名', '召开日期',
                '会议内容', '会议次数', '召开会议', '姓名', '职务', '变动类型')


def compact(text):
    return re.sub(r'\s+', '', text or '').translate(str.maketrans('審計員會議開員職務', '审计员会议开员职务'))


def digest(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def committee_labels(text):
    text = compact(text)
    return [name for name in COMMITTEES
            if re.search(re.escape(name) + r'.{0,12}委员会', text)]


def select_governance_pages(pages, *, neighbor_radius=1):
    """Public text selection, not question/reference-page selection."""
    if type(neighbor_radius) is not int or not 0 <= neighbor_radius <= 2:
        raise ValueError('Page neighborhood must be 0, 1 or 2')
    numbers = [p['page'] for p in pages]
    if numbers != list(range(1, len(pages) + 1)):
        raise ValueError('Page text must be in complete physical-page order')
    seeds, reasons = [], {}
    for page in pages:
        text = compact(page['text'])
        hits = [label for label, pattern in [
            ('audit_committee', r'审计委员会'),
            ('special_committee', r'专门委员会'),
            ('personnel_changes', r'(?:董事|监事|高级管理人员|董监高).{0,18}(?:变动情况|变更情况|离任情况)'),
        ] if re.search(pattern, text)]
        if hits:
            seeds.append(page['page'])
            reasons[page['page']] = hits
    selected = sorted({n for p in seeds for n in range(max(1, p - neighbor_radius), min(len(pages), p + neighbor_radius) + 1)})
    return dict(seed_pages=seeds, selected_pages=selected, seed_reasons=reasons,
                neighbor_radius=neighbor_radius, reference_labels_used=False,
                scope='governance keyword pages and fixed physical neighbors; not every table in the PDF')


def _ranges(indices):
    result = []
    for index in sorted(set(indices)):
        if result and index == result[-1][1]:
            result[-1][1] += 1
        else:
            result.append([index, index + 1])
    return result


def _layout_text(chars):
    lines = []
    for char in sorted(chars, key=lambda c: (c['top'], c['x0'])):
        center = (char['top'] + char['bottom']) / 2
        if lines and abs(center - lines[-1][0]) <= max(2.5, char.get('size', 9) * .28):
            lines[-1][1].append(char)
        else:
            lines.append([center, [char]])
    rendered = []
    for _, items in lines:
        items.sort(key=lambda c: c['x0'])
        text, right = '', None
        for c in items:
            if right is not None and c['x0'] - right > max(2, c.get('size', 9) * .4) and not text.endswith(' '):
                text += ' '
            text += c['text']
            right = c['x1']
        rendered.append(text.rstrip())
    return '\n'.join(rendered).strip()


def _cell(page, bbox, table_id, *, kind='body'):
    x0, top, x1, bottom = map(float, bbox)
    if not all(math.isfinite(v) for v in bbox) or not (0 <= x0 < x1 <= page.width + .1 and 0 <= top < bottom <= page.height + .1):
        raise ValueError('Cell box is outside the source page')
    selected = [(i, c) for i, c in enumerate(page.chars)
                if x0 - .01 <= (c['x0'] + c['x1']) / 2 < x1 + .01
                and top - .01 <= (c['top'] + c['bottom']) / 2 < bottom + .01]
    char_indices = [i for i, _ in selected]
    raw = ''.join(c['text'] for _, c in selected)
    box = [round(v, 4) for v in bbox]
    return dict(cell_id=table_id + '-C' + digest(box)[:12], page=page.page_number,
                bbox=box, coordinate_system='pdf_points_top_left', kind=kind,
                text=_layout_text([c for _, c in selected]),
                text_origin='PDF characters plus reconstructed layout whitespace',
                char_index_ranges=_ranges(char_indices), char_count=len(char_indices),
                raw_char_text_sha256=hashlib.sha256(raw.encode('utf-8')).hexdigest())


def verify_cell(page, cell):
    """Re-bind stored geometry/character references against a freshly opened page."""
    if cell['page'] != page.page_number:
        raise ValueError('Cell belongs to another physical page')
    rebuilt = _cell(page, cell['bbox'], cell['cell_id'].split('-C')[0], kind=cell['kind'])
    for key in ('char_index_ranges', 'char_count', 'raw_char_text_sha256', 'text'):
        if rebuilt[key] != cell[key]:
            raise ValueError('Cell character source or reconstructed text changed')
    return True


def _union_length(intervals):
    merged = []
    for left, right in sorted(intervals):
        if merged and left <= merged[-1][1] + 2:
            merged[-1][1] = max(merged[-1][1], right)
        else:
            merged.append([left, right])
    return sum(b - a for a, b in merged)


def _dominant_columns(page, bbox):
    groups = []
    for edge in sorted((e for e in page.edges if e['orientation'] == 'v'), key=lambda e: e['x0']):
        x = edge['x0']
        if not bbox[0] - 2 <= x <= bbox[2] + 2:
            continue
        a, b = max(edge['top'], bbox[1]), min(edge['bottom'], bbox[3])
        if b <= a:
            continue
        if groups and abs(x - groups[-1]['center']) <= 2:
            groups[-1]['xs'].append(x)
            groups[-1]['intervals'].append((a, b))
            groups[-1]['center'] = sum(groups[-1]['xs']) / len(groups[-1]['xs'])
        else:
            groups.append(dict(center=x, xs=[x], intervals=[(a, b)]))
    internal = [g['center'] for g in groups
                if bbox[0] + 3 < g['center'] < bbox[2] - 3
                and _union_length(g['intervals']) >= (bbox[3] - bbox[1]) * .4]
    return [bbox[0]] + internal + [bbox[2]]


def _table_rows(page, table, table_id, caption):
    boxes = sorted({tuple(cell) for row in table.rows for cell in row.cells if cell})
    cells = [_cell(page, box, table_id) for box in boxes]
    x_edges = sorted({round(v, 3) for box in boxes for v in (box[0], box[2])})
    y_edges = sorted({round(v, 3) for box in boxes for v in (box[1], box[3])})
    raw_rows = []
    for top, bottom in zip(y_edges, y_edges[1:]):
        if bottom - top < 1:
            continue
        mid = (top + bottom) / 2
        row = []
        for left, right in zip(x_edges, x_edges[1:]):
            cx = (left + right) / 2
            found = [c for c in cells if c['bbox'][0] - .01 <= cx < c['bbox'][2] + .01
                     and c['bbox'][1] - .01 <= mid < c['bbox'][3] + .01]
            row.append(min(found, key=lambda c: (c['bbox'][2] - c['bbox'][0]) * (c['bbox'][3] - c['bbox'][1])) if found else None)
        raw_rows.append(dict(top=top, bottom=bottom, cells=row))
    # First unmistakable data row establishes the end of multi-line headers.
    body_start = None
    for row in raw_rows:
        text = compact(' '.join(c['text'] for c in row['cells'] if c))
        date_fragment = any(re.fullmatch(r'(?:年\d{1,2}月\d{1,2}日|月\d{1,2}日|\d{1,2}日)', compact(c['text']))
                            for c in row['cells'] if c)
        agenda_fragment = (all(c is None or not compact(c['text']) for c in row['cells'][:2]) and
                           any(re.match(r'^\d{1,2}[.、．]',compact(c['text'])) for c in row['cells'][2:] if c))
        if (committee_labels(text) or re.search(r'(?:19|20)\d{2}年?\d{0,2}月?\d{0,2}日?', text) or date_fragment or agenda_fragment) and not any(
                token in text for token in ('委员会名称', '成员情况', '成员姓名', '召开日期')):
            body_start = row['top']
            break
    if body_start is None:
        first_text = compact(' '.join(c['text'] for c in raw_rows[0]['cells'] if c)) if raw_rows else ''
        body_start = raw_rows[0]['bottom'] if any(t in first_text for t in HEADER_WORDS) else table.bbox[1]
    headers = []
    if body_start - table.bbox[1] > 1:
        for left, right in zip(x_edges, x_edges[1:]):
            headers.append(_cell(page, (left, table.bbox[1], right, body_start), table_id, kind='header'))
    header_text = [c['text'] for c in headers]
    rows = []
    for row in raw_rows:
        if row['top'] < body_start - .1:
            continue
        values = [c['text'] if c else '' for c in row['cells']]
        if not any(compact(v) for v in values):
            continue
        # Preserve spanning-cell references; do not invent empty-cell fill-down.
        rows.append(dict(row_id=f'{table_id}-R{len(rows)+1:03d}', page=page.page_number,
                         top=row['top'], bottom=row['bottom'], values=values,
                         parts=[[c['cell_id']] if c else [] for c in row['cells']],
                         split_row_merged=False))
    all_cells = {c['cell_id']: c for c in cells + headers}
    return dict(table_id=table_id, page=page.page_number, bbox=list(table.bbox),
                page_width=page.width, page_height=page.height,
                method='ruled_grid', column_bounds=x_edges,
                headers=header_text, header_cell_ids=[c['cell_id'] for c in headers],
                caption=caption, cells=list(all_cells.values()), rows=rows,
                header_status='detected' if headers else 'absent_or_ambiguous',
                category=classify_headers(header_text), warnings=[])


def classify_headers(headers):
    joined = compact(' '.join(headers))
    if any(token in joined for token in ('其他单位', '股东单位', '任职单位名称')):
        return 'external_entity_appointments'
    if ('日期' in joined or '时间' in joined) and ('会议' in joined or '职责' in joined):
        return 'committee_meetings'
    if '成员' in joined and '委员会' in joined:
        return 'committee_roster'
    if '姓名' in joined and any(w in joined for w in ('职务', '变动', '离任')):
        return 'personnel_changes'
    return 'unclassified_table'


def _word_lines(words):
    lines = []
    for word in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if lines and abs(word['top'] - lines[-1][0]) <= 3:
            lines[-1][1].append(word)
        else:
            lines.append([word['top'], [word]])
    return lines


def _attendance_table(page, prefix, *, excluded_bboxes=()):
    """Borderless numeric matrix; require repeated aligned attendance columns."""
    words = page.extract_words(x_tolerance=2, y_tolerance=3)
    if excluded_bboxes:
        def belongs_to_ruled_table(word):
            cx = (word['x0'] + word['x1']) / 2
            cy = (word['top'] + word['bottom']) / 2
            return any(x0 - 2 <= cx <= x1 + 2 and top - 1 <= cy <= bottom + 1
                       for x0, top, x1, bottom in excluded_bboxes)
        words = [word for word in words if not belongs_to_ruled_table(word)]
    lines = _word_lines(words)
    candidates = []
    for top, items in lines:
        numeric = [w for w in items if re.fullmatch(r'\d+/\d+|[/／]', compact(w['text']))]
        if len(numeric) >= 3 and any(re.fullmatch(r'\d+/\d+', compact(w['text'])) for w in numeric):
            candidates.append((top, items, numeric))
    if len(candidates) < 3:
        return []
    counts = defaultdict(int)
    for _, _, numeric in candidates:
        counts[len(numeric)] += 1
    columns = max(counts, key=lambda n: (counts[n], n))
    candidates = [r for r in candidates if len(r[2]) == columns]
    if len(candidates) < 3:
        return []
    anchors = [sum(sorted(n, key=lambda w: w['x0'])[i]['x1'] for _, _, n in candidates) / len(candidates)
               for i in range(columns)]
    for _, _, numeric in candidates:
        if any(abs(w['x1'] - anchor) > 4 for w, anchor in zip(sorted(numeric, key=lambda w: w['x0']), anchors)):
            return []
    left = min(w['x0'] for _, items, _ in candidates for w in items)
    first_boundary = anchors[0] - (anchors[1] - anchors[0]) / 2
    if first_boundary <= left:
        return []
    bounds = [left, first_boundary] + [(a + b) / 2 for a, b in zip(anchors, anchors[1:])] + [min(page.width, anchors[-1] + (anchors[-1] - anchors[-2]) / 2)]
    first_top = candidates[0][0]
    header_top = max(0, first_top - 110)
    table_id = prefix + '-B01'
    headers = [_cell(page, (a, header_top, b, first_top - 2), table_id, kind='header')
               for a, b in zip(bounds, bounds[1:])]
    # Do not label a financial fraction matrix as an attendance table merely
    # because its values contain slashes; committee headers must be geometric.
    if not any('审计' in compact(c['text']) and '委员会' in compact(c['text']) for c in headers):
        return []
    cells = list(headers)
    rows = []
    for i, (top, items, _) in enumerate(candidates):
        bottom = max(w['bottom'] for w in items) + 1
        row_cells = [_cell(page, (a, top - .5, b, bottom), table_id)
                     for a, b in zip(bounds, bounds[1:])]
        cells.extend(row_cells)
        rows.append(dict(row_id=f'{table_id}-R{i+1:03d}', page=page.page_number,
                         top=top, bottom=bottom, values=[c['text'] for c in row_cells],
                         parts=[[c['cell_id']] for c in row_cells], split_row_merged=False))
    return [dict(table_id=table_id, page=page.page_number,
                 bbox=[left, header_top, bounds[-1], rows[-1]['bottom']],
                 page_width=page.width, page_height=page.height,
                 method='borderless_attendance_alignment', column_bounds=bounds,
                 headers=[c['text'] for c in headers], header_cell_ids=[c['cell_id'] for c in headers],
                 caption='出席次数/应出席次数（按版面列对齐）', cells=cells, rows=rows,
                 header_status='geometric_multilevel_headers', category='committee_attendance',
                 warnings=['Inferred column geometry; requires source review before treating attendance as membership gold.'])]


def extract_page_tables(page, source_sha256):
    prefix = f'TAB-{source_sha256[:16]}-P{page.page_number:04d}'
    tables = []
    detected = sorted(page.find_tables(), key=lambda t: (t.bbox[1], t.bbox[0]))
    for i, original in enumerate(detected, 1):
        table = original
        if len(table.columns) < 2 or len(table.rows) < 2:
            continue
        dominant = _dominant_columns(page, table.bbox)
        if 3 <= len(dominant) < len(table.columns) + 1:
            refined = page.crop(table.bbox).find_tables(dict(
                vertical_strategy='explicit', explicit_vertical_lines=dominant,
                horizontal_strategy='lines', snap_tolerance=3, intersection_tolerance=5))
            if refined:
                table = max(refined, key=lambda t: (t.bbox[2]-t.bbox[0])*(t.bbox[3]-t.bbox[1]))
        tid = prefix + f'-G{i:02d}'
        above = [c for c in page.chars if max(0, table.bbox[1] - 90) <= c['top'] < table.bbox[1] - 1]
        caption = _layout_text(above)
        parsed = _table_rows(page, table, tid, caption)
        parsed['raw_detected_column_count'] = len(original.columns)
        tables.append(parsed)
    # Ruled and borderless tables may coexist on one physical page. Exclude
    # words already covered by accepted grids, but still search the remainder
    # for a separately headed attendance matrix.
    tables.extend(_attendance_table(
        page, prefix, excluded_bboxes=[table['bbox'] for table in tables]))
    return sorted(tables, key=lambda table: (table['bbox'][1], table['bbox'][0]))


def _header_signature(headers):
    return [compact(h) for h in headers]


def reconcile_boundary_headers(tables, pdf):
    """Recover a short orphan header using the adjacent full grid's geometry.

    Word-style PDFs can draw padding rectangles inside header cells, creating
    false columns. Only header-only page-end fragments may borrow a matching
    adjacent page-start grid; data tables never change their geometry this way.
    """
    by_page = defaultdict(list)
    for table in sorted(tables, key=lambda t: (t['page'], t['bbox'][1])):
        by_page[table['page']].append(table)
    for page, items in by_page.items():
        if page + 1 not in by_page:
            continue
        left, right = items[-1], by_page[page + 1][0]
        text = compact(' '.join(c['text'] for c in left['cells']))
        if (left['method'] != 'ruled_grid' or right['method'] != 'ruled_grid' or
                left['bbox'][3] - left['bbox'][1] > 80 or
                left['bbox'][3] < left['page_height'] * .83 or
                right['bbox'][1] > right['page_height'] * .19 or
                committee_labels(text) or re.search(r'20\d{2}', text) or
                not any(token in text for token in HEADER_WORDS)):
            continue
        if (abs(left['bbox'][0]/left['page_width'] - right['bbox'][0]/right['page_width']) > .008 or
                abs(left['bbox'][2]/left['page_width'] - right['bbox'][2]/right['page_width']) > .008):
            continue
        bounds = [x * left['page_width'] / right['page_width'] for x in right['column_bounds']]
        bounds[0], bounds[-1] = left['bbox'][0], left['bbox'][2]
        source_page = pdf.pages[page - 1]
        headers = [_cell(source_page, (a, left['bbox'][1], b, left['bbox'][3]),
                         left['table_id'], kind='header') for a, b in zip(bounds, bounds[1:])]
        cells = {c['cell_id']: c for c in left['cells'] + headers}
        left.update(column_bounds=bounds, headers=[c['text'] for c in headers],
                    header_cell_ids=[c['cell_id'] for c in headers], cells=list(cells.values()),
                    rows=[], category=classify_headers([c['text'] for c in headers]),
                    header_status='orphan_header_reconciled_from_adjacent_grid')
        left['warnings'].append('Header-only geometry borrowed from the next physical page; raw cells retained.')


def _partial_header(headers):
    nonempty = [compact(h) for h in headers if compact(h)]
    fragments = {'建议', '的情况', '情况', '（如有）', '(如有)', '如有', '具体情况',
                 '行职责', '履行职责', '议次数', '次数', '议', '称'}
    return bool(nonempty) and all(h in fragments for h in nonempty)


def continuation_decision(left, right):
    """All gates explicit; a rejected match remains in the audit."""
    reasons = []
    if right['page'] != left['page'] + 1:
        reasons.append('not_consecutive_physical_pages')
    if left['method'] != 'ruled_grid' or right['method'] != 'ruled_grid':
        reasons.append('unsupported_continuation_method')
    a, b = left['column_bounds'], right['column_bounds']
    if len(a) != len(b) or len(a) < 3:
        reasons.append('different_column_count')
    elif max(abs(x / left['page_width'] - y / right['page_width']) for x, y in zip(a, b)) > .008:
        reasons.append('column_geometry_mismatch')
    if left['bbox'][3] < left['page_height'] * .83:
        reasons.append('left_table_not_at_page_end')
    if right['bbox'][1] > right['page_height'] * .19:
        reasons.append('right_table_not_at_page_start')
    orphan_payload = _orphan_page_start_payload(left, right)
    ah, bh = _header_signature(left['headers']), _header_signature(right['headers'])
    if ah and bh and ah != bh and not _partial_header(right['headers']) and not orphan_payload:
        # Header layout whitespace may differ, but altered column semantics must reject.
        reasons.append('different_repeated_headers')
    if right['category'] != 'unclassified_table' and left['category'] != 'unclassified_table' and right['category'] != left['category']:
        reasons.append('table_category_changed')
    caption = compact(right.get('caption', ''))
    last_heading = re.findall(r'(?:[（(][一二三四五六七八九十\d]+[）)]|[一二三四五六七八九十\d]+[、.．])[^。]{0,25}委员会', caption)
    if last_heading and committee_labels(left.get('caption', '')) and committee_labels(caption):
        if set(committee_labels(left.get('caption', ''))) != set(committee_labels(caption)):
            reasons.append('new_committee_section_heading')
    if orphan_payload:
        reasons.append('single_nonheader_cell_at_page_start_continues_prior_row')
    decision = dict(accepted=not reasons or bool(orphan_payload and all(
        reason == 'single_nonheader_cell_at_page_start_continues_prior_row' for reason in reasons)),
                reasons=reasons or ['same_geometry_adjacent_boundary_and_compatible_headers'],
                left_table_id=left['table_id'], right_table_id=right['table_id'],
                physical_pages=[left['page'], right['page']], independent_semantic_validation=False)
    if orphan_payload:
        decision['boundary_payload'] = orphan_payload
    return decision


def _orphan_page_start_payload(left, right):
    """Recognize one text-cell fragment misdetected as a page-start header.

    This narrow case is limited to a complete committee-meeting row followed
    by a ruled, geometry-matched page-start grid whose sole nonempty header
    cell is continuation prose in the previous row's opinion/remarks column.
    """
    if (left.get('category') != 'committee_meetings' or
            right.get('category') != 'unclassified_table' or
            left.get('method') != 'ruled_grid' or right.get('method') != 'ruled_grid' or
            not left.get('rows') or not right.get('rows')):
        return None
    nonempty = [(i, compact(value)) for i, value in enumerate(right.get('headers', [])) if compact(value)]
    if len(nonempty) != 1:
        return None
    column, text = nonempty[0]
    if column >= len(left.get('headers', [])) or column >= len(left['rows'][-1].get('values', [])):
        return None
    prior_header = compact(left['headers'][column])
    if not any(term in prior_header for term in ('意见', '建议', '履行职责', '其他情况')):
        return None
    if any(term in text for term in HEADER_WORDS) or len(text) < 6:
        return None
    prior_row = left['rows'][-1]
    columns = field_columns(left['headers'])
    date_column = columns.get('date')
    if date_column is None or not parse_date(prior_row['values'][date_column]):
        return None
    # The following page must resume with a structured committee row; this
    # prevents a free-standing page title or narrative from being absorbed.
    first_values = right['rows'][0].get('values', [])
    if not first_values or not committee_labels(first_values[0]):
        return None
    # Identifying fields in the prior row must be complete; the orphan cell is
    # only allowed to continue its trailing remarks field.
    if any(not compact(prior_row['values'][i]) for i in range(min(column, len(prior_row['values'])))):
        return None
    if (len(left['column_bounds']) != len(right['column_bounds']) or
            max(abs(a / left['page_width'] - b / right['page_width'])
                for a, b in zip(left['column_bounds'], right['column_bounds'])) > .008):
        return None
    if (left['bbox'][3] < left['page_height'] * .83 or
            right['bbox'][1] > right['page_height'] * .19):
        return None
    cells = {cell['cell_id']: cell for cell in right.get('cells', [])}
    header_ids = right.get('header_cell_ids', [])
    if column >= len(header_ids):
        return None
    cell_id = header_ids[column]
    if cell_id not in cells or compact(cells[cell_id].get('text', '')) != text:
        return None
    return dict(column_index=column, cell_id=cell_id, text=cells[cell_id]['text'],
                merge_basis='orphan_page_start_header_cell_continuation')


def field_columns(headers):
    result = {}
    for i, text in enumerate(headers):
        text = compact(text)
        if '成员' in text:
            result.setdefault('members', i)
        if '姓名' in text or text == '董事':
            result.setdefault('name', i)
        if '日期' in text or '时间' in text:
            result.setdefault('date', i)
        if '次' in text and ('召开' in text or '会议' in text):
            result.setdefault('count', i)
        if '委员会' in text and ('名称' in text or '类别' in text):
            result.setdefault('committee', i)
        if '会议内容' in text:
            result.setdefault('meeting_content', i)
        if ('意见' in text or '建议' in text) and ('提出' in text or '重要' in text):
            result.setdefault('meeting_opinions', i)
        if '履行职责' in text and '情况' in text:
            result.setdefault('meeting_other_duties', i)
        if '异议事项' in text:
            result.setdefault('meeting_dissent', i)
        if '会议决议' in text:
            result.setdefault('agenda', i)
        if '职务' in text:
            result.setdefault('position', i)
    return result


def parse_date(text):
    match = re.fullmatch(r'((?:19|20)\d{2})年(\d{1,2})月(\d{1,2})日', compact(text))
    if not match:
        return None
    try:
        return datetime.date(*map(int, match.groups())).isoformat()
    except ValueError:
        return None


def _merge_split_row(left, right, headers):
    columns = field_columns(headers)
    date_column = columns.get('date')
    if date_column is None or date_column >= min(len(left['values']), len(right['values'])):
        return None
    a, b = compact(left['values'][date_column]), compact(right['values'][date_column])
    basis = None
    if a and b and not parse_date(a) and not parse_date(b) and parse_date(a+b) and re.match(r'^(?:年|月|日|\d{1,2}日)',b):
        basis = 'complementary_calendar_date_fragments'
    content_column = columns.get('agenda', columns.get('meeting_content'))
    if (basis is None and parse_date(a) and not b and content_column is not None and
            not compact(right['values'][0]) and compact(right['values'][content_column]) and
            all(not compact(right['values'][i]) for i in range(min(date_column+1,len(right['values']))))):
        basis = 'blank_key_cells_with_continued_agenda_at_verified_page_boundary'
    if basis is None:
        return None
    merged = copy.deepcopy(left)
    merged['row_id'] = left['row_id'] + '+continuation'
    merged['values'] = [a + ('\n' if pa and pb else '') + b
                        for a, b, pa, pb in zip(left['values'], right['values'], left['parts'], right['parts'])]
    merged['parts'] = [a + b for a, b in zip(left['parts'], right['parts'])]
    merged['split_row_merged'] = True
    merged['split_row_merge_basis'] = basis
    merged['split_row_source_ids'] = [left['row_id'], right['row_id']]
    return merged


def stitch_tables(tables):
    """Logical chains preserve every raw table/cell and rejected join decision."""
    tables = sorted(tables, key=lambda t: (t['page'], t['bbox'][1]))
    by_page = defaultdict(list)
    for table in tables:
        by_page[table['page']].append(table)
    links, link_decisions, attempts = {}, {}, []
    for page, left_tables in sorted(by_page.items()):
        if page + 1 not in by_page:
            continue
        left, right = left_tables[-1], by_page[page + 1][0]
        decision = continuation_decision(left, right)
        attempts.append(decision)
        if decision['accepted']:
            links[left['table_id']] = right['table_id']
            link_decisions[left['table_id']] = decision
    lookup = {t['table_id']: t for t in tables}
    incoming = set(links.values())
    chains = []
    for table in tables:
        if table['table_id'] in incoming:
            continue
        current = table
        chain = dict(chain_id=table['table_id'] + '-CHAIN', table_ids=[table['table_id']],
                     headers=copy.deepcopy(table['headers']), header_cell_ids=list(table['header_cell_ids']),
                     header_column_parts=[[cid] for cid in table['header_cell_ids']],
                     category=table['category'], method=table['method'], caption=table['caption'],
                     rows=copy.deepcopy(table['rows']), pages=[table['page']],
                     repeated_headers_removed_from_logical_rows=0, split_rows_merged=0,
                     boundary_payloads_absorbed=0)
        while current['table_id'] in links:
            following = lookup[links[current['table_id']]]
            decision = link_decisions[current['table_id']]
            payload = decision.get('boundary_payload')
            if payload and chain['rows']:
                row = chain['rows'][-1]
                column = payload['column_index']
                row['values'][column] = row['values'][column] + '\n' + payload['text']
                row['parts'][column].append(payload['cell_id'])
                row['split_row_merged'] = True
                row['split_row_merge_basis'] = payload['merge_basis']
                chain['split_rows_merged'] += 1
                chain['boundary_payloads_absorbed'] += 1
            if chain['headers'] and following['headers'] and _partial_header(following['headers']):
                chain['headers'] = [a + '\n' + b for a, b in zip(chain['headers'], following['headers'])]
                chain['header_cell_ids'].extend(following['header_cell_ids'])
                chain['header_column_parts'] = [a + [b] for a,b in zip(chain['header_column_parts'],following['header_cell_ids'])]
            if not chain['headers'] and following['headers']:
                chain['headers'] = copy.deepcopy(following['headers'])
                chain['header_cell_ids'] = list(following['header_cell_ids'])
                chain['header_column_parts'] = [[cid] for cid in following['header_cell_ids']]
                chain['category'] = following['category']
            next_rows = copy.deepcopy(following['rows'])
            if chain['rows'] and next_rows:
                merged = _merge_split_row(chain['rows'][-1], next_rows[0], chain['headers'])
                if merged:
                    chain['rows'][-1] = merged
                    next_rows = next_rows[1:]
                    chain['split_rows_merged'] += 1
            if following['headers'] and not payload:
                chain['repeated_headers_removed_from_logical_rows'] += 1
            chain['rows'].extend(next_rows)
            chain['table_ids'].append(following['table_id'])
            chain['pages'].append(following['page'])
            current = following
        if chain['category'] == 'unclassified_table' and chain['headers']:
            chain['category'] = classify_headers(chain['headers'])
        for row in chain['rows']:
            row['committee_labels'], row['scope_basis'] = row_scope(row, chain)
        chains.append(chain)
    return chains, attempts


def row_scope(row, chain):
    columns = field_columns(chain['headers'])
    if chain['category'] == 'external_entity_appointments':
        return [], 'other_entity_appointment_not_focal_company_membership'
    if chain['category'] == 'committee_attendance':
        active = []
        for i, header in enumerate(chain['headers']):
            labels = committee_labels(header)
            value = compact(row['values'][i])
            match = re.fullmatch(r'(\d+)/(\d+)', value)
            if labels and match and int(match[2]) > 0:
                active.extend(labels)
        return sorted(set(active)), 'geometrically_aligned_attendance_column_with_positive_expected_count'
    for key in ['committee', 'position']:
        if key in columns:
            return committee_labels(row['values'][columns[key]]), key + '_cell'
    if 'meeting_content' in columns:
        # Only the beginning is a potential meeting title. Agenda references
        # later in the cell must not switch committee ownership.
        leading = compact(row['values'][columns['meeting_content']])[:65]
        labels = committee_labels(leading)
        if labels and not re.match(r'^(?:审议|议案|关于)', leading) and re.search(r'委员会.{0,18}(?:次会议|会议)', leading):
            return labels, 'meeting_title_prefix'
    if row['values']:
        labels = committee_labels(row['values'][0])
        if labels:
            return labels, 'first_column_explicit_committee'
    caption_labels = committee_labels(chain.get('caption', ''))
    explicit_heading = re.search(r'(?:[（(][一二三四五六七八九十\d]+[）)]|[一二三四五六七八九十\d]+[、.．]).{0,20}委员会',compact(chain.get('caption','')))
    if len(caption_labels) == 1 and explicit_heading:
        return caption_labels, 'single_explicit_table_caption_requires_review'
    return [], 'unresolved_no_fill_down'


def extract_pdfium_pages(pdf_path):
    """Uniform local text discovery; no OCR and no remote service fallback."""
    import pypdfium2 as pdfium
    result = []
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            try:
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_range().replace('\r\n', '\n').replace('\r', '\n')
                finally:
                    textpage.close()
            finally:
                page.close()
            result.append(dict(page=i + 1, text=text))
    finally:
        pdf.close()
    return result


def extract_document(pdf_path, source, page_texts, *, progress=None, all_pages=False):
    """Parse selected governance pages of one verified local annual PDF."""
    import pdfplumber
    pdf_path = Path(pdf_path)
    actual_sha = file_sha256(pdf_path)
    if actual_sha != source['sha256']:
        raise ValueError('Local annual PDF digest differs from the source manifest')
    selection = select_governance_pages(page_texts)
    if all_pages:
        selection['selected_pages'] = list(range(1, len(page_texts) + 1))
        selection['scope'] = 'all physical pages explicitly requested'
    tables, page_records = [], []
    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) != len(page_texts):
            raise ValueError('Frozen page text/PDF page counts differ')
        for number in selection['selected_pages']:
            page = pdf.pages[number - 1]
            parsed = extract_page_tables(page, actual_sha)
            tables.extend(parsed)
            page_records.append(dict(page=number, width=page.width, height=page.height,
                                     chars=len(page.chars), tables=len(parsed),
                                     page_character_fingerprint=digest([
                                         [c['text'], round(c['x0'],4), round(c['top'],4), round(c['x1'],4), round(c['bottom'],4)]
                                         for c in page.chars]),
                                     status='text_layer_parsed' if page.chars else 'requires_ocr_no_text_layer'))
            if progress:
                progress(number, len(parsed))
            page.close()
        reconcile_boundary_headers(tables, pdf)
    chains, decisions = stitch_tables(tables)
    return dict(schema_version=1, parser_version=VERSION, source=copy.deepcopy(source),
                selection=selection, parsed_pages=page_records, tables=tables,
                logical_tables=chains, continuation_decisions=decisions,
                source_pdf_sha256=actual_sha, model_calls=0,
                independent_human_validation=False,
                limitations=['Governance-page selection only; unsupported or scanned layouts remain explicit review items.',
                             'Geometry and rule-based scope do not certify complete reporting-period membership.'])

