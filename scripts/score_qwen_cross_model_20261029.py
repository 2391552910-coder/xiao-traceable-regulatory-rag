"""Score completed local and saved Kimi answers against existing references only."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.score_heldout_validation_20261023 import dates, names, setscore, sha
from scripts.smoke_qwen_cuda_20261029 import PACKETS, frozen_packets

SOURCE = PACKETS.parent


def inspect(parsed, allowed):
    valid = isinstance(parsed, dict)
    p = parsed if valid else {}
    cites = p.get('citations')
    citation_lists = isinstance(cites, dict) and all(
        isinstance(cites.get(k), list) and all(isinstance(x, str) for x in cites[k])
        for k in ('members', 'meeting_count', 'meeting_dates'))
    schema = (valid and isinstance(p.get('members'), list)
              and all(isinstance(x, str) for x in p['members'])
              and 'meeting_count' in p and (p['meeting_count'] is None or type(p['meeting_count']) is int)
              and isinstance(p.get('meeting_dates'), list)
              and all(isinstance(x, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', x) for x in p['meeting_dates'])
              and citation_lists and isinstance(p.get('limitations'), list)
              and all(isinstance(x, str) for x in p['limitations']))
    cited = {x.strip('[] ') for values in cites.values() if isinstance(values, list)
             for x in values if isinstance(x, str)} if isinstance(cites, dict) else set()
    valid_ids = {value for value in cited if re.fullmatch(r'[AR][1-9][0-9]*', value)}
    malformed = cited - valid_ids
    return p, bool(schema), bool(citation_lists), sorted(valid_ids - allowed), sorted(malformed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    packets = frozen_packets()
    protocol_path = args.run_dir / 'protocol.json'
    protocol = json.loads(protocol_path.read_text(encoding='utf-8'))
    if protocol['packet_sha256'] != {p.name: sha(p) for p in packets}:
        raise ValueError('Qwen protocol and saved packet hashes differ')
    original = SOURCE / 'reference_labels.json'
    corrected = SOURCE / 'reference_labels_corrected.json'
    start = json.loads((SOURCE / 'generation_start.json').read_text(encoding='utf-8'))
    refsets = {'before_generation': json.loads(original.read_text(encoding='utf-8')),
               'post_output_erratum': json.loads(corrected.read_text(encoding='utf-8'))}
    if sha(original) != start['reference_labels_sha256'] or refsets['post_output_erratum']['parent_sha256'] != sha(original):
        raise ValueError('Reference chain does not match its original release')
    refs = {name: {r['question_id']: r for r in data['records']} for name, data in refsets.items()}
    detail = []
    for packet in packets:
        item = json.loads(packet.read_text(encoding='utf-8'))
        qid = item['question']['question_id']
        qwen = args.run_dir / (qid + '.json')
        kimi_dir = SOURCE / 'calls' / qid / 'k3_single'
        kimi = kimi_dir / 'result.json'
        for mode, path in [('qwen06', qwen), ('k3_single', kimi)]:
            if not path.is_file():
                detail.append({'question_id': qid, 'mode': mode, 'status': 'missing', 'reference': None})
                continue
            result = json.loads(path.read_text(encoding='utf-8'))
            if result['question']['question_id'] != qid:
                raise ValueError('Answer question does not match packet')
            if mode == 'qwen06' and result['packet_sha256'] != sha(packet):
                raise ValueError('Qwen result is not bound to the saved packet')
            if mode == 'k3_single':
                call = json.loads((kimi_dir / 'call1.json').read_text(encoding='utf-8'))
                if (result['initial_context']['context_sha256'] != item['context']['context_sha256'] or
                        call['request']['messages'] != [{'role': 'user', 'content': item['prompt']}]):
                    raise ValueError('Kimi initial context or prompt differs from the packet')
            status = result['status']
            allowed = {record['evidence_id'] for record in item['context']['source_records']}
            pred, schema, cite_lists, unknown, malformed = inspect(result.get('parsed'), allowed)
            for version in refs:
                ref = refs[version][qid]
                if not ref['members'] or not ref['meeting_dates']:
                    raise ValueError('Empty references need an explicit metric policy')
                members = setscore(names(pred.get('members')), names(ref['members']))
                meeting_dates = setscore(dates(pred.get('meeting_dates')), set(ref['meeting_dates']))
                count_ok = type(pred.get('meeting_count')) is int and pred['meeting_count'] == ref['meeting_count']
                detail.append({'question_id': qid, 'mode': mode, 'status': status, 'reference': version,
                    'nonempty': bool(result.get('text', '').strip()), 'schema_valid': schema,
                    'citation_lists_valid': cite_lists, 'unknown_citation_ids': unknown,
                    'malformed_citation_values': malformed,
                    'members_precision': members['precision'], 'members_recall': members['recall'],
                    'members_f1': members['f1'], 'meeting_count_exact': count_ok,
                    'dates_precision': meeting_dates['precision'], 'dates_recall': meeting_dates['recall'],
                    'dates_f1': meeting_dates['f1'],
                    'all_three_exact': members['exact'] and meeting_dates['exact'] and count_ok,
                    'answer_sha256': sha(path), 'packet_sha256': sha(packet)})
    summary = []
    metrics = ('schema_valid', 'citation_lists_valid', 'members_precision', 'members_recall', 'members_f1',
               'meeting_count_exact', 'dates_precision', 'dates_recall', 'dates_f1', 'all_three_exact')
    for version in refs:
        for mode in ('qwen06', 'k3_single'):
            rows = [r for r in detail if r['reference'] == version and r['mode'] == mode]
            successful = [r for r in rows if r['status'] == 'completed' and r['nonempty']]
            summary.append({'reference': version, 'mode': mode, 'planned': len(packets),
                'observed': len(rows), 'successful_nonempty': len(successful),
                'macro_successful': {k: statistics.mean(r[k] for r in successful) if successful else None for k in metrics},
                'unknown_citation_ids_across_answers': sum(len(r['unknown_citation_ids']) for r in successful),
                'malformed_citation_values_across_answers': sum(len(r['malformed_citation_values']) for r in successful)})
    args.out_dir.mkdir(parents=True, exist_ok=False)
    out = {'reference_origin': refsets['before_generation']['annotator'],
           'reference_hashes': {'before_generation': sha(original), 'post_output_erratum': sha(corrected)},
           'run_protocol_sha256': sha(protocol_path), 'script_sha256': sha(Path(__file__)),
           'summaries': summary, 'details': detail,
           'limitations': ['Reference answers were assistant-extracted, not independently validated gold.',
               'One draw per model and eight questions from four companies; no significance or generalization claim.',
               'Erratum was made after prior model output; both reference versions are shown.',
               'Temperature, output budgets, model capacity and compute differ across models.',
               'Unknown and malformed citation-value counts cover string entries inside lists only; scalar citation values are reported by the schema check, not counted as IDs.',
               'Field overlap and valid citation IDs do not establish semantic citation support or legal applicability.',
               'Evaluation is post hoc and adds no human annotation.']}
    (args.out_dir / 'summary.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
