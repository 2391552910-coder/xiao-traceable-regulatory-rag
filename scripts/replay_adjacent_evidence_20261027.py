"""Offline adjacent-window development comparison; no generation or network path."""
from __future__ import annotations

import argparse
import copy
import csv
import datetime
import importlib.metadata
import json
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generation.annual_audit_development import (
    FIXED_QUERIES, FrozenAuditIndex, answer_prompt, file_sha256,
)
from src.generation.comparison import _pack_context, canonical_sha256
from src.generation.evidence_retention import extend_retained_context
from src.retrieval.adjacent_chunks import FrozenAdjacentIndex
from src.retrieval.source_span_audit import (
    FrozenAnnualSourceVerifier, covered_characters, merge_intervals,
)

SOURCE = ROOT / 'results/paper/heldout_validation_20261023_01'
DEFAULT_OUT = ROOT / 'results/runs/adjacent_evidence_development_20261027_01'
MODES = (
    'initial', 'fixed_preserve', 'adjacent_rank', 'adjacent_continuation',
    'fixed_then_adjacent', 'adjacent_then_fixed',
)
QUALITY = {key: None for key in (
    'answer_precision', 'answer_recall', 'answer_f1', 'answer_accuracy',
    'semantic_citation_accuracy', 'semantic_retrieval_recall',
)}


def load(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def annual_spans(context, question, verifier):
    return [verifier.verify_record(row, question) for row in context['source_records']
            if row['meta'].get('corpus_type') == 'annual_report']


def span_map(spans):
    result = defaultdict(list)
    for row in spans:
        result[(row['source_pdf_sha256'], row['physical_pdf_page_1based'])].append(
            (row['source_start'], row['source_end']))
    return result


def source_characters(spans):
    return sum(right - left for intervals in span_map(spans).values()
               for left, right in merge_intervals(intervals))


def check_preservation(initial, context, count):
    n = len(initial['source_records'])
    if not context['context'].startswith(initial['context']):
        raise ValueError('Initial evidence text prefix changed')
    if context['source_records'][:n] != initial['source_records']:
        raise ValueError('Initial evidence source records or stable IDs changed')
    if not context['reference_tokens'] == count(context['context']) <= 6000:
        raise ValueError('Context reference token budget failed')


def construct_context(mode, question, initial, index, adjacent):
    """Predefined policies use original seeds; never read labels or recurse."""
    context = copy.deepcopy(initial)
    traces = []

    def append_hits(name, hits, selection=None):
        nonlocal context
        context, packing = extend_retained_context(
            question, context, hits, index.count, max_context_tokens=6000, max_new_sources=8)
        traces.append(dict(stage=name, selection=selection, packing=packing))

    def fixed():
        for i, queries in enumerate(FIXED_QUERIES, 1):
            append_hits(f'fixed_round_{i}', index.fresh_hits(question, queries),
                        dict(queries=list(queries), learned_planning=False))

    def neighbors(policy):
        # Always select from the original context, including in the combined modes.
        hits, selection = adjacent.select(question, initial, policy=policy)
        append_hits('adjacent_' + policy, hits, selection)

    if mode == 'initial':
        pass
    elif mode == 'fixed_preserve':
        fixed()
    elif mode == 'adjacent_rank':
        neighbors('direction_round_robin')
    elif mode == 'adjacent_continuation':
        neighbors('continuation_first')
    elif mode == 'fixed_then_adjacent':
        fixed()
        neighbors('continuation_first')
    elif mode == 'adjacent_then_fixed':
        neighbors('continuation_first')
        fixed()
    else:
        raise ValueError('Unknown predefined development mode')
    check_preservation(initial, context, index.count)
    return context, traces


def verify_original_publication():
    manifest = ROOT.parent / 'github_delivery_20261026_01/upload_manifest.json'
    if not manifest.is_file():
        return dict(status='unavailable', files_verified=None)
    selected = [row for row in load(manifest)
                if row['path'].startswith('results/paper/heldout_validation_20261023_01/')]
    for row in selected:
        if file_sha256(ROOT / row['path']) != row['sha256']:
            raise ValueError('Historical published result changed: ' + row['path'])
    return dict(status='passed', files_verified=len(selected), manifest_sha256=file_sha256(manifest))


def evaluate_source_targets(contexts, verifier, targets_path):
    """Post-retrieval case diagnosis; exact audit-context source spans, not predictions."""
    diagnostic = load(targets_path)
    targets = diagnostic['targets']
    rows = []
    for case in contexts:
        relevant = [target for target in targets if target['question_id'] == case['question']['question_id']]
        if not relevant:
            continue
        spans = span_map(case['verified_annual_spans'])
        for target in relevant:
            page = target['page']
            key = (target['source_pdf_sha256'], page)
            entry = verifier.sources[(case['question']['stock_code'], case['question']['report_year'])]
            if (target['source_pdf_sha256'] != entry['source']['sha256'] or
                    entry['pages'][page][target['start']:target['end']] != target['text']):
                raise ValueError('Post-retrieval diagnostic target has incorrect source coordinates')
            present = covered_characters(spans.get(key, []), target['start'], target['end'])
            rows.append(dict(question_id=case['question']['question_id'], mode=case['mode'],
                             label=target['label'], kind=target['kind'],
                             source_pdf_sha256=key[0], physical_pdf_page_1based=page,
                             start=target['start'], end=target['end'], text=target['text'],
                             covered_characters=present,
                             full_span_supplied=present == target['end'] - target['start']))
    return dict(status='case_diagnostic_only', independent_human_validation=False,
                source_diagnostic_file=str(targets_path.relative_to(ROOT)),
                source_diagnostic_sha256=file_sha256(targets_path), rows=rows,
                limitation='Exact source-span supply in an assistant-audited, post-output case; not generated answer recall or independent semantic entailment.')


def replay(out):
    out = Path(out).resolve()
    if not out.is_relative_to((ROOT / 'results/runs').resolve()):
        raise ValueError('Output must remain in project results/runs')
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('Preserve existing artifacts; choose a fresh output directory')
    out.mkdir(parents=True, exist_ok=True)
    packet_paths = sorted((SOURCE / 'packets').glob('*.json'))
    if len(packet_paths) != 8:
        raise ValueError('Expected exactly the eight exposed development questions')
    paths = packet_paths + [SOURCE / name for name in (
        'sources.json', 'execution_protocol.json', 'reference_labels.json',
        'reference_labels_corrected.json', 'index_pdfium.sqlite',
    )] + sorted((SOURCE / 'source_pages_pdfium').glob('*.json'))
    code_paths = [Path(__file__), ROOT / 'src/retrieval/adjacent_chunks.py',
                  ROOT / 'src/retrieval/source_span_audit.py',
                  ROOT / 'src/generation/annual_audit_development.py',
                  ROOT / 'src/generation/evidence_retention.py',
                  ROOT / 'src/generation/supplementary_retrieval.py',
                  ROOT / 'src/generation/comparison.py']
    receipt = {str(path.relative_to(ROOT)): file_sha256(path) for path in paths}
    protocol = dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    classification='exposed development regression; not an independent holdout',
                    new_model_calls=0, model_transport_available=False,
                    modes=list(MODES), questions=8, planned_contexts=48,
                    reference_token_cap=6000, maximum_new_sources_per_stage=8,
                    fixed_queries=[list(q) for q in FIXED_QUERIES],
                    adjacent_policy='Direct successor/predecessor of original annual seeds only; same document/company/year/PDF; no recursive expansion; whole existing chunks.',
                    ordering_comparison='direction_round_robin versus continuation_first, plus fixed-query stage ordering; all six policies reported',
                    labels_read_during_candidate_selection=False,
                    design_note='Developed after the historical failure was inspected; no preregistration or blind validation claim.',
                    source_inputs_sha256=receipt,
                    code_sha256={str(path.relative_to(ROOT)): file_sha256(path) for path in code_paths})
    save(out / 'offline_protocol.json', protocol)
    verifier = FrozenAnnualSourceVerifier(SOURCE)
    plan = load(ROOT / 'results/runs/compact_final_execution_windows_20261020_01/execution_plan.json')
    old_protocol = load(SOURCE / 'execution_protocol.json')
    index = FrozenAuditIndex(SOURCE / 'index_pdfium.sqlite', plan['reference_tokenizer_file'],
                             tokenizer_sha256=old_protocol['reference_tokenizer_sha256'])
    adjacent = FrozenAdjacentIndex(SOURCE / 'index_pdfium.sqlite')
    contexts, rows, all_spans = [], [], []
    reproduced = 0
    for packet_path in packet_paths:
        packet = load(packet_path)
        question, initial = packet['question'], packet['context']
        if _pack_context(index.search(question, question['query']), index.count, 6000) != initial:
            raise ValueError('Historical initial context did not reproduce')
        if answer_prompt(question, initial['context']) != packet['prompt']:
            raise ValueError('Historical initial prompt changed')
        reproduced += 1
        initial_spans = annual_spans(initial, question, verifier)
        for mode in MODES:
            context, trace = construct_context(mode, question, initial, index, adjacent)
            verified = annual_spans(context, question, verifier)
            all_spans.extend(verified)
            case = dict(question=question, mode=mode, initial_context_sha256=initial['context_sha256'],
                        final_context=context, trace=trace, verified_annual_spans=verified,
                        generated_answer=None, answer_quality=QUALITY)
            save(out / 'contexts' / question['question_id'] / (mode + '.json'), case)
            contexts.append(case)
            reasons = Counter()
            for stage in trace:
                reasons.update(stage['packing']['omitted_reason_counts'])
            rows.append(dict(question_id=question['question_id'], company=question['company_name'],
                             report_year=question['report_year'], mode=mode,
                             initial_tokens=initial['reference_tokens'], final_tokens=context['reference_tokens'],
                             initial_source_retention=1.0, initial_text_prefix_preserved=True,
                             new_chunks=len(context['source_records']) - len(initial['source_records']),
                             initial_unique_annual_characters=source_characters(initial_spans),
                             final_unique_annual_characters=source_characters(verified),
                             new_unique_annual_characters=source_characters(verified)-source_characters(initial_spans),
                             budget_omissions=reasons.get('reference_token_cap_no_truncation', 0),
                             stage_count=len(trace)))
    # Finish and receipt every context before opening any label/diagnostic content.
    context_files = sorted((out / 'contexts').rglob('*.json'))
    save(out / 'contexts_saved_before_reference_analysis.json', dict(
        status='complete', contexts=len(context_files), new_model_calls=0,
        context_files_sha256={str(path.relative_to(out)): file_sha256(path) for path in context_files},
        context_list_sha256=canonical_sha256([c['final_context']['context_sha256'] for c in contexts])))
    reparsed = verifier.reparse_pages(all_spans)
    save(out / 'source_verification.json', dict(
        status='passed', local_pdf_bytes_rehashed=True, pdf_files=len(verifier.receipt),
        source_receipt=verifier.receipt, unique_chunk_spans=len({s['chunk_id'] for s in all_spans}),
        exact_slice_checks=len(all_spans), used_pages_reparsed=len(reparsed),
        reparsed_pages=reparsed, parser_version=importlib.metadata.version('pypdfium2'),
        coordinate_policy='Unicode code-point offsets in PDFium text; 1200-character windows, stride1000',
        semantic_support_verified=False))
    frozen = load(SOURCE / 'reference_labels.json')
    corrected = load(SOURCE / 'reference_labels_corrected.json')
    if corrected['parent_sha256'] != file_sha256(SOURCE / 'reference_labels.json'):
        raise ValueError('Corrected reference parent digest changed')
    for version, labels in [('frozen', frozen), ('corrected', corrected)]:
        references = {r['question_id']: r for r in labels['records']}
        for row, case in zip(rows, contexts):
            gold_pages = set(references[row['question_id']]['physical_pages'])
            supplied_pages = {s['physical_pdf_page_1based'] for s in case['verified_annual_spans']}
            row[version + '_reference_page_coverage'] = len(gold_pages & supplied_pages) / len(gold_pages)
    diagnostic = evaluate_source_targets(
        contexts, verifier, ROOT / 'docs/adjacent_source_diagnostic_20261026.json')
    save(out / 'case_source_span_diagnostic.json', diagnostic)
    for row in rows:
        date_rows = [target for target in diagnostic['rows']
                     if target['question_id'] == row['question_id'] and target['mode'] == row['mode']
                     and target['kind'] == 'audit_meeting_date']
        row['case_audit_date_spans_total'] = len(date_rows) if date_rows else None
        row['case_audit_date_spans_supplied'] = sum(t['full_span_supplied'] for t in date_rows) if date_rows else None
    for path, digest in receipt.items():
        if file_sha256(ROOT / path) != digest:
            raise ValueError('Frozen source input changed during replay: ' + path)
    for path, digest in protocol['code_sha256'].items():
        if file_sha256(ROOT / path) != digest:
            raise ValueError('Runtime code changed during replay: ' + path)
    publication = verify_original_publication()
    groups = []
    numeric = ['final_tokens', 'initial_source_retention', 'new_chunks',
               'new_unique_annual_characters', 'budget_omissions',
               'frozen_reference_page_coverage', 'corrected_reference_page_coverage']
    for mode in MODES:
        selected = [r for r in rows if r['mode'] == mode]
        groups.append(dict(mode=mode, n=len(selected), **{
            key: statistics.mean(r[key] for r in selected) for key in numeric}))
    summary = dict(status='passed', new_model_calls=0, generated_answers=0,
                   contexts=len(contexts), historical_initial_contexts_reproduced=reproduced,
                   all_initial_text_and_source_ids_preserved=True,
                   all_contexts_within_6000_reference_tokens=True,
                   labels_loaded_only_after_contexts_saved=True,
                   independent_human_validation=False, answer_quality=QUALITY,
                   source_verification=dict(pdf_files=8, unique_chunk_spans=len({s['chunk_id'] for s in all_spans}),
                                            used_pages_reparsed=len(reparsed)),
                   original_publication=publication, groups=groups, rows=rows,
                   limitations=[
                       'Eight questions already exposed; purposive development regression, not independent validation.',
                       'Page coverage measures reference locations, not semantic retrieval recall or answer quality.',
                       'CMB2024 case targets were assistant-audited after historical output inspection; exact span supply only.',
                       'Appending whole neighbors can fail under the fixed token cap; every policy, omission and order is retained.',
                       'No generated answer, new precision, recall, F1, accuracy or Agent superiority is established.',
                   ])
    save(out / 'offline_analysis.json', summary)
    with (out / 'offline_metrics.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({k: v for k, v in summary.items() if k not in ('rows', 'limitations')}, ensure_ascii=False, indent=2))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, default=DEFAULT_OUT)
    replay(parser.parse_args().out_dir)
