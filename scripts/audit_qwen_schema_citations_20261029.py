"""Audit saved extraction citations without interpreting semantic support."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.score_heldout_validation_20261023 import sha
from scripts.smoke_qwen_cuda_20261029 import frozen_packets
from scripts.score_qwen_cross_model_20261029 import inspect

FIELDS = ('members', 'meeting_count', 'meeting_dates')


def audit(answer, allowed):
    parsed, schema, _, _, _ = inspect(answer, allowed)
    citations = parsed.get('citations')
    fields = {}
    for key in FIELDS:
        raw = citations.get(key) if isinstance(citations, dict) else None
        list_valid = isinstance(raw, list) and all(isinstance(x, str) for x in raw)
        ids = raw if list_valid else []
        malformed = [x for x in ids if not re.fullmatch(r'[AR][1-9][0-9]*', x)]
        unknown = [x for x in ids if re.fullmatch(r'[AR][1-9][0-9]*', x) and x not in allowed]
        field_value = parsed.get(key)
        has_value = bool(field_value) if key != 'meeting_count' else type(field_value) is int
        fields[key] = {'citation_list_valid': list_valid, 'raw': raw,
                       'malformed': malformed, 'unknown': unknown,
                       'has_answer_value': has_value,
                       'has_resolved_citation': bool([x for x in ids if x in allowed])}
    return {'schema_valid': schema, 'fields': fields,
            'all_fields_nonempty_and_resolved': schema and all(
                x['has_resolved_citation'] and not x['malformed'] and not x['unknown']
                for x in fields.values()),
            'all_present_values_cited': schema and all(
                not x['has_answer_value'] or (x['has_resolved_citation'] and not x['malformed'] and not x['unknown'])
                for x in fields.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    base = ROOT/'results/runs/qwen_cuda_cross_model_20261029_01'
    variant = ROOT/'results/runs/qwen_schema_prompt_20261029_01'
    source_score = ROOT/'results/runs/qwen_schema_prompt_score_20261029_01/summary.json'
    scoring = json.loads(source_score.read_text(encoding='utf-8'))
    if scoring['baseline_protocol_sha256'] != sha(base/'protocol.json') or scoring['variant_protocol_sha256'] != sha(variant/'protocol.json'):
        raise ValueError('Protocol hashes differ from the saved comparison')
    rows = []
    for packet in frozen_packets():
        data = json.loads(packet.read_text(encoding='utf-8'))
        qid = data['question']['question_id']
        allowed = {record['evidence_id'] for record in data['context']['source_records']}
        for name, folder in [('baseline', base), ('schema_example', variant)]:
            path = folder/(qid+'.json')
            result = json.loads(path.read_text(encoding='utf-8'))
            if result['question']['question_id'] != qid or result['packet_sha256'] != sha(packet) or result['status'] != 'completed':
                raise ValueError('Result is not a completed answer bound to its packet')
            row = {'condition': name, 'question_id': qid, 'result_sha256': sha(path),
                   'supplied_ids': sorted(allowed), **audit(result.get('parsed'), allowed)}
            rows.append(row)
    summaries = []
    for name in ('baseline', 'schema_example'):
        rr = [r for r in rows if r['condition'] == name]
        summaries.append({'condition': name, 'answers': len(rr),
            'schema_valid': sum(r['schema_valid'] for r in rr),
            'all_fields_nonempty_and_resolved': sum(r['all_fields_nonempty_and_resolved'] for r in rr),
            'all_present_values_cited': sum(r['all_present_values_cited'] for r in rr),
            'answers_with_malformed_citation_values': sum(any(f['malformed'] for f in r['fields'].values()) for r in rr),
            'answers_with_unknown_ids': sum(any(f['unknown'] for f in r['fields'].values()) for r in rr)})
    payload = {'scope': 'Post-hoc mechanical ID audit only; neither correctness nor semantic citation support is evaluated.',
               'source_score_sha256': sha(source_score), 'script_sha256': sha(Path(__file__)),
               'summaries': summaries, 'per_answer': rows}
    args.out_dir.mkdir(parents=True, exist_ok=False)
    (args.out_dir/'citation_audit.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summaries, ensure_ascii=False))


if __name__ == '__main__':
    main()
