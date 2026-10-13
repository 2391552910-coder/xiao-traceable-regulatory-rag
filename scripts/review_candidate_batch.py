"""展示指定问题的完整证据；导入逐条显式判断并校验覆盖，不自动预测标签。"""
import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / 'data/annotation/reviews/independent_20261013'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('query_id')
    parser.add_argument('--decisions', help='逐条复核的决策 JSON；每个候选必须显式出现')
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--reuse-seen', action='store_true')
    args = parser.parse_args()
    rows = [r for r in csv.DictReader((REVIEW / 'input_blind.csv').open(encoding='utf-8-sig'))
            if r['query_id'] == args.query_id]
    if not rows:
        raise ValueError('query_id 不存在')
    if args.decisions:
        decisions = json.loads(Path(args.decisions).read_text())
        if set(decisions) != {r['chunk_id'] for r in rows}:
            raise ValueError('必须为本问题全部候选显式提供判断，不能默认把未列出的行判为负例')
        for cid, value in decisions.items():
            if len(value) != 3 or value[0] not in [-1, 0, 1, 2] or value[1] not in ['high', 'medium', 'low'] or not value[2].strip():
                raise ValueError(f'判断格式错误: {cid}')
        (REVIEW / (args.query_id + '.json')).write_text(json.dumps(decisions, ensure_ascii=False, indent=2)+'\n')
        print(f'{args.query_id}: recorded {len(rows)} explicit decisions')
        return
    seen = set()
    for path in REVIEW.glob('Q*.json'):
        seen.update(json.loads(path.read_text()))
    print(f'{args.query_id} {rows[0]["query"]} ({len(rows)} candidates)')
    for i, r in enumerate(rows[args.start:args.start+args.limit], args.start):
        print(f'\n[{i}] {r["chunk_id"]} | {r["doc_title"]} | {r["doc_date"]} | stored={r["stored_clause_no"]},owner={r["owner_clause_no"]},heading={r["is_clause_heading"]},truncated={r["truncated"]}')
        if args.reuse_seen and r['chunk_id'] in seen:
            print('[已在已完成问题中阅读过全文] ' + r['text'][:100])
        else:
            print(r['text'])


if __name__ == '__main__':
    main()
