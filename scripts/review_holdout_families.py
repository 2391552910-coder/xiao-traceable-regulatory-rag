"""Single AI family triage; not independent human review or relevance annotation."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_corpus_v2 import read_csv, write_json, write_jsonl
from src.data.benchmark import sha256_file
from src.data.holdout_v2 import release_errors_v2

# Explicit semantic triage by the current AI reviewer, with development question IDs.
TRIAGE = {
 'H001': (['Q03','Q05'], '业绩预告更正属于临时/定期披露问题族，不能仅因细化情境认定独立。'),
 'H002': (['Q02'], '自愿披露连续性与已开发的信息披露义务族交叉。'),
 'H003': (['Q02','Q03'], '暂缓豁免是已有披露义务及临时报告族的例外情境。'),
 'H004': (['Q02'], '投资者调研信息公开属于已开发信息披露义务的应用。'),
 'H005': ([], '强制可持续发展报告适用主体可暂留为新问题族候选；适用规则版本和证据未核实。'),
 'H006': (['Q23','Q26'], '差错更正与财务报告真实完整、财务造假族相交，需要留在开发范围。'),
 'H007': (['Q13','Q14'], '累积投票仍是股东会及董事选举议事程序问题族。'),
 'H008': (['Q14','Q16'], '职工董事构成与董事会/章程制度族相交。'),
 'H009': ([], '董事责任保险报告对象暂留为单独候选；仍需人工确认与忠实勤勉责任族的边界。'),
 'H010': (['Q14','Q19'], '关联回避和不足人数审议属于董事会议事、控制人行为族。'),
 'H011': (['Q13'], '临时提案属于股东会程序族，加入时间限定并不产生新族。'),
 'H012': (['Q14','Q18'], '辞任过渡职责与董事职责/忠实勤勉问题族相交。'),
 'H013': (['Q21','Q22'], '举报机制是内部监督和控制要素的应用，保守归入开发族。'),
 'H014': (['Q21','Q22'], '不相容职责分离是控制活动应用，归入已有内控族。'),
 'H015': (['Q21','Q22'], '系统权限是控制活动应用，归入已有内控族。'),
 'H016': (['Q21','Q22'], '应急响应是风险评估及控制活动应用，归入已有内控族。'),
 'H017': (['Q21','Q22'], '外包监督是控制活动应用，归入已有内控族。'),
 'H018': (['Q21','Q22'], '合同授权审批是控制活动应用，归入已有内控族。'),
 'H019': ([], '历史处罚能否推断当期属于时间外推/证据不足探针，不混入法规检索测试。'),
 'H020': ([], '检索无结果推断无违规属于负证据不足探针，需要独立答复判定协议。'),
 'H021': ([], '评级分歧需要第三方评级材料与事实核验协议，不属于当前法规检索任务。'),
 'H022': (['Q24'], '审计意见的保证范围与已开发注册会计师审计责任族相交。'),
 'H023': ([], '整改核实是事实证据补全探针，需要公司整改及独立核验材料。'),
 'H024': ([], '简称重名是实体归属核验探针，需要公司及新闻实体证据。'),
}


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'data/heldout/candidates_20261013/candidate_queries.jsonl'
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    old_manifest = json.loads((source.parent/'manifest.json').read_text())
    dev = read_csv(ROOT/'data/annotation/retrieval_queries_gold.csv')
    # Full query text inventory is read from the registered CSV inputs, including the synthetic set.
    import csv, io, gzip, base64
    historical = set()
    for name in old_manifest['input_sha256']:
        p = ROOT/name
        if p.suffix not in {'.csv','.base64'}:
            continue
        text = p.read_text(encoding='utf-8-sig')
        if p.suffix == '.base64':
            text = gzip.decompress(base64.b64decode(text)).decode('utf-8-sig')
        historical.update(r['query'] for r in csv.DictReader(io.StringIO(text)) if r.get('query'))
    registry = {'scope': 'repository_registered_development_inputs_only',
                'queries': sorted(historical), 'family_ids': [r['query_id'] for r in dev],
                'company_ids': [], 'company_inventory_status': 'not_applicable_to_current_non_company_retrieval_candidates',
                'input_sha256': old_manifest['input_sha256']}
    for row in rows:
        matches, reason = TRIAGE[row['query_id']]
        probe = row['query_id'] in {'H019','H020','H021','H023','H024'}
        row.update(development_family_matches=matches, family_review_reason=reason,
                   family_review_origin='single_ai_semantic_triage',
                   ai_review='single_ai_family_review_no_relevance_grade',
                   status='rejected_development_family_overlap' if matches else
                          'separate_research_probe' if probe else 'pending_source_and_human_family_review',
                   task_type='evidence_verification_probe' if probe else 'regulatory_retrieval',
                   evidence_sha256={}, human_review_record_sha256=None)
    write_jsonl(out/'all_candidate_decisions.jsonl', rows)
    retained = [r for r in rows if r['status']=='pending_source_and_human_family_review']
    write_jsonl(out/'reserved_retrieval_candidates.jsonl', retained)
    write_jsonl(out/'research_probes.jsonl', [r for r in rows if r['task_type']!='regulatory_retrieval'])
    write_json(out/'development_registry.json', registry)
    errors = release_errors_v2(rows, registry)
    write_json(out/'release_gate.json', {'passed':not errors, 'errors':errors,
                                       'error_counts':dict(Counter(e for _,e in errors))})
    summary = {'status':'family_triaged_not_formal_test', 'status_counts':dict(Counter(r['status'] for r in rows)),
               'formal_test_queries':0, 'human_labels':0,
               'query_texts_rewritten':False, 'queries_used_for_tuning':0,
               'source_candidates_sha256':sha256_file(source),
               'code_sha256':{p:sha256_file(ROOT/p) for p in ['scripts/review_holdout_families.py','src/data/holdout_v2.py']},
               'artifacts_sha256':{p.name:sha256_file(p) for p in sorted(out.iterdir())}}
    write_json(out/'manifest.json', summary)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir',required=True,type=Path)
    print(json.dumps(build(p.parse_args().out_dir),ensure_ascii=False,indent=2))
