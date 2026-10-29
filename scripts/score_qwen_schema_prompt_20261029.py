"""Compare baseline and post-hoc Qwen schema prompt on the same eight packets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.score_heldout_validation_20261023 import dates, names, setscore, sha
from scripts.score_qwen_cross_model_20261029 import inspect
from scripts.smoke_qwen_cuda_20261029 import PACKETS, frozen_packets
from scripts.run_qwen_schema_prompt_20261029 import PROMPT_SUFFIX


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-dir', required=True, type=Path)
    parser.add_argument('--variant-dir', required=True, type=Path)
    parser.add_argument('--out-dir', required=True, type=Path)
    args = parser.parse_args()
    packets = frozen_packets()
    baseline_path = args.baseline_dir / 'protocol.json'
    variant_path = args.variant_dir / 'protocol.json'
    a, b = load(baseline_path), load(variant_path)
    packet_hashes = {p.name: sha(p) for p in packets}
    if (a['packet_sha256'] != packet_hashes or b['packet_sha256'] != packet_hashes or
            b['baseline_protocol_sha256'] != sha(baseline_path) or b['prompt_suffix'] != PROMPT_SUFFIX or
            b['prompt_suffix_sha256'] != hashlib.sha256(PROMPT_SUFFIX.encode('utf-8')).hexdigest()):
        raise ValueError('Protocol does not bind the original packets and exact prompt change')
    equal_settings = ('model', 'revision', 'checkpoint_sha256', 'dtype', 'device', 'enable_thinking',
                      'do_sample', 'temperature', 'top_p', 'top_k', 'max_new_tokens', 'seed_base')
    if any(a.get(k) != b.get(k) for k in equal_settings):
        raise ValueError('Baseline and prompt variant settings differ')
    original = PACKETS.parent / 'reference_labels.json'
    corrected = PACKETS.parent / 'reference_labels_corrected.json'
    if (sha(original) != load(PACKETS.parent / 'generation_start.json')['reference_labels_sha256'] or
            load(corrected)['parent_sha256'] != sha(original)):
        raise ValueError('Reference correction is not bound to the original')
    references = {'before_generation': {r['question_id']: r for r in load(original)['records']},
                  'post_output_erratum': {r['question_id']: r for r in load(corrected)['records']}}
    rows = []
    for packet in packets:
        source = load(packet); qid = source['question']['question_id']; allowed = {x['evidence_id'] for x in source['context']['source_records']}
        for condition, folder in [('baseline', args.baseline_dir), ('schema_example', args.variant_dir)]:
            path = folder / (qid + '.json')
            if not path.is_file():
                rows.append({'question_id': qid, 'condition': condition, 'status': 'missing'})
                continue
            result = load(path)
            if result['question']['question_id'] != qid or result['packet_sha256'] != sha(packet):
                raise ValueError('Saved answer is not bound to its expected packet')
            parsed, valid, lists_valid, unknown, malformed = inspect(result.get('parsed'), allowed)
            for version, refset in references.items():
                ref = refset[qid]
                if not ref['members'] or not ref['meeting_dates']:
                    raise ValueError('Empty reference sets need an explicit scoring rule')
                member = setscore(names(parsed.get('members')), names(ref['members']))
                date = setscore(dates(parsed.get('meeting_dates')), set(ref['meeting_dates']))
                count = type(parsed.get('meeting_count')) is int and parsed['meeting_count'] == ref['meeting_count']
                rows.append({'question_id': qid, 'condition': condition, 'reference': version,
                    'status': result['status'], 'nonempty': bool(result.get('text', '').strip()),
                    'schema_valid': valid, 'citation_lists_valid': lists_valid,
                    'unknown_citation_ids': unknown, 'malformed_citation_values': malformed,
                    'members_precision': member['precision'], 'members_recall': member['recall'],
                    'members_f1': member['f1'], 'dates_precision': date['precision'],
                    'dates_recall': date['recall'], 'dates_f1': date['f1'], 'count_exact': count,
                    'all_three_exact': member['exact'] and date['exact'] and count,
                    'prompt_tokens': result.get('prompt_tokens'), 'completion_tokens': result.get('completion_tokens'),
                    'finish_reason': result.get('finish_reason'), 'result_sha256': sha(path)})
    summaries = []
    metrics = ('schema_valid', 'citation_lists_valid', 'members_precision', 'members_recall', 'members_f1',
               'dates_precision', 'dates_recall', 'dates_f1', 'count_exact', 'all_three_exact')
    for version in references:
        index = {(r['question_id'], r['condition']): r for r in rows if r.get('reference') == version}
        valid = [(index[q, 'baseline'], index[q, 'schema_example']) for q in [p.stem for p in packets]
                 if (q, 'baseline') in index and (q, 'schema_example') in index and
                 all(r['status'] == 'completed' and r['nonempty'] for r in (index[q, 'baseline'], index[q, 'schema_example']))]
        summaries.append({'reference': version, 'planned_pairs': len(packets), 'observed_pairs': len(valid),
            'metrics': {m: {'baseline': statistics.mean(float(a[m]) for a, b in valid) if valid else None,
                            'schema_example': statistics.mean(float(b[m]) for a, b in valid) if valid else None,
                            'paired_delta': statistics.mean(float(b[m]) - float(a[m]) for a, b in valid) if valid else None}
                        for m in metrics},
            'baseline_prompt_tokens': sum(a['prompt_tokens'] for a, b in valid),
            'variant_prompt_tokens': sum(b['prompt_tokens'] for a, b in valid),
            'baseline_completion_tokens': sum(a['completion_tokens'] for a, b in valid),
            'variant_completion_tokens': sum(b['completion_tokens'] for a, b in valid)})
    result = {'baseline_protocol_sha256': sha(baseline_path), 'variant_protocol_sha256': sha(variant_path),
        'reference_hashes': {'before_generation': sha(original), 'post_output_erratum': sha(corrected)},
        'script_sha256': sha(Path(__file__)), 'summaries': summaries, 'per_answer': rows,
        'limitations': ['Prompt change designed after seeing baseline errors; this is development, not independent testing.',
                        'One generation per condition on eight questions from four companies; same seed does not eliminate sampling variance.',
                        'Existing assistant-extracted references are not independently validated; corrected version followed earlier K3 outputs.',
                        'Schema compliance and citation ID syntax do not establish semantic citation support or legal applicability.',
                        'Same generation limit and sampling settings but different prompt lengths and realized compute; no new human labels.']}
    args.out_dir.mkdir(parents=True, exist_ok=False)
    (args.out_dir / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summaries, ensure_ascii=False))


if __name__ == '__main__':
    main()
