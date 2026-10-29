"""Recompute observed-pair Agent contrasts without new model calls or labels."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.score_heldout_validation_20261023 import dates, names, setscore, sha
from scripts.smoke_qwen_cuda_20261029 import PACKETS, frozen_packets

SOURCE = ROOT / 'results/paper/heldout_validation_20261023_01'
MODES = ('k3_single', 'k3_fixed_expand', 'k3_refine3', 'k3_agent3_v2')
METRICS = ('members_f1', 'dates_f1', 'count_exact', 'three_field_exact')


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    packets = frozen_packets()
    qids = [load(p)['question']['question_id'] for p in packets]
    if len(qids) != len(set(qids)):
        raise ValueError('Question IDs must be unique')
    original = SOURCE / 'reference_labels.json'
    corrected = SOURCE / 'reference_labels_corrected.json'
    if sha(original) != load(SOURCE / 'generation_start.json')['reference_labels_sha256']:
        raise ValueError('Original reference differs from generation-start record')
    if load(corrected)['parent_sha256'] != sha(original):
        raise ValueError('Corrected reference is not bound to the original reference')
    comparisons = []
    for version, ref_path, details_path in [
        ('before_generation', original, SOURCE / 'heldout_scoring_details.json'),
        ('post_output_erratum', corrected, SOURCE / 'heldout_scoring_details_corrected.json'),
    ]:
        references = {x['question_id']: x for x in load(ref_path)['records']}
        details = {(x['question_id'], x['mode']): x for x in load(details_path)}
        checked = {}
        for qid in qids:
            packet = load(PACKETS / (qid + '.json'))
            ref = references[qid]
            for mode in MODES:
                row = details[qid, mode]
                folder = SOURCE / 'calls' / qid / mode
                result_path = folder / 'result.json'
                result = load(result_path)
                if (sha(result_path) != row['result_sha256'] or result['status'] != row['status'] or
                        result['initial_context']['context_sha256'] != packet['context']['context_sha256'] or
                        result['initial_context']['context_sha256'] != row['initial_context_sha256'] or
                        result['final_context']['context_sha256'] != row['final_context_sha256']):
                    raise ValueError(f'Saved result or context differs: {qid} {mode}')
                pred = result.get('parsed') if isinstance(result.get('parsed'), dict) else {}
                if pred != row['predicted'] or bool(result.get('text', '').strip()) != row['nonempty']:
                    raise ValueError(f'Saved answer differs: {qid} {mode}')
                m = setscore(names(pred.get('members')), names(ref['members']))
                d = setscore(dates(pred.get('meeting_dates')), set(ref['meeting_dates']))
                count = type(pred.get('meeting_count')) is int and pred['meeting_count'] == ref['meeting_count']
                recalculated = {'members_f1': m['f1'], 'dates_f1': d['f1'],
                                'count_exact': count, 'three_field_exact': m['exact'] and d['exact'] and count}
                if any(abs(float(row[k]) - float(recalculated[k])) > 1e-12 for k in METRICS):
                    raise ValueError(f'Saved field metrics differ: {qid} {mode}')
                calls = [load(p) for p in folder.glob('call*.json') if '_request' not in p.stem]
                tokens = sum(c.get('usage', c.get('response', {}).get('usage', {})).get('total_tokens', 0) for c in calls)
                if len(calls) != row['calls'] or tokens != row['tokens']:
                    raise ValueError(f'Saved call inventory differs: {qid} {mode}')
                checked[qid, mode] = row
        for base in ('k3_single', 'k3_fixed_expand', 'k3_refine3'):
            pair_rows = []
            excluded = []
            for qid in qids:
                agent, other = checked[qid, 'k3_agent3_v2'], checked[qid, base]
                if agent['status'] == other['status'] == 'completed' and agent['nonempty'] and other['nonempty']:
                    pair_rows.append((agent, other))
                else:
                    excluded.append({'question_id': qid, 'agent_status': agent['status'],
                                     'baseline_status': other['status']})
            means = {key: {'agent': statistics.mean(float(a[key]) for a, b in pair_rows),
                           'baseline': statistics.mean(float(b[key]) for a, b in pair_rows),
                           'paired_delta': statistics.mean(float(a[key]) - float(b[key]) for a, b in pair_rows)}
                     for key in METRICS}
            bounds = {}
            for key in METRICS:
                low = high = 0.0
                for qid in qids:
                    a, b = checked[qid, 'k3_agent3_v2'], checked[qid, base]
                    av = float(a[key]) if a['status'] == 'completed' and a['nonempty'] else None
                    bv = float(b[key]) if b['status'] == 'completed' and b['nonempty'] else None
                    low += (av if av is not None else 0) - (bv if bv is not None else 1)
                    high += (av if av is not None else 1) - (bv if bv is not None else 0)
                bounds[key] = [low / len(qids), high / len(qids)]
            comparisons.append({'reference_version': version, 'baseline': base, 'planned_questions': len(qids),
                'observed_pairs': len(pair_rows), 'observed_companies': len({a['stock'] for a, b in pair_rows}),
                'excluded_pairs': excluded, 'means': means, 'full_question_mean_delta_bounds': bounds,
                'agent_recorded_calls': sum(a['calls'] for a, b in pair_rows),
                'baseline_recorded_calls': sum(b['calls'] for a, b in pair_rows),
                'agent_provider_total_tokens': sum(a['tokens'] for a, b in pair_rows),
                'baseline_provider_total_tokens': sum(b['tokens'] for a, b in pair_rows),
                'paired_question_ids': [a['question_id'] for a, b in pair_rows]})
    out = {'script_sha256': sha(Path(__file__)), 'comparisons': comparisons,
        'input_hashes': {str(p.relative_to(ROOT)): sha(p) for p in
            [original, corrected, SOURCE / 'generation_start.json', SOURCE / 'heldout_scoring_details.json',
             SOURCE / 'heldout_scoring_details_corrected.json']},
        'scope': ['Saved outputs only; no new calls or human annotation.',
                  'Assistant-extracted references were not independently validated; correction followed prior outputs.',
                  'Observed pairs are conditional on both outputs completing; bounded outcomes do not identify missing values.',
                  'Four companies and one output per condition; no significance or generalization inference.',
                  'Equal call counts do not imply equal tokens, latency, context, or reasoning compute.',
                  'Field matching does not establish semantic citation support or legal applicability.']}
    args.out_dir.mkdir(parents=True, exist_ok=False)
    (args.out_dir / 'agent_pair_comparison.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for row in comparisons:
        print(row['reference_version'], row['baseline'], 'pairs', row['observed_pairs'],
              'three_exact_delta', round(row['means']['three_field_exact']['paired_delta'], 4),
              'bounds', row['full_question_mean_delta_bounds']['three_field_exact'])


if __name__ == '__main__':
    main()
