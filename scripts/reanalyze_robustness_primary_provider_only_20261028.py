"""Read-only audit of frozen human ratings. No generation, relabeling or imputation."""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone
import csv, hashlib, json, sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from scripts.score_minimal_paper_reviews import validate_submission, FIELDS

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def dumpcsv(name,rows):
    if not rows:return
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

SCORES=ROOT/'results/runs/two_reviewer_statistics_windows_20261023_01/per_output_scores.json'
STATS=ROOT/'results/runs/two_reviewer_statistics_windows_20261023_01/statistics.json'
SUPPLEMENTS=ROOT/'results/runs/compact_final_execution_windows_20261020_01/assistant_supplement_windows_20261020_01/answers_session_supplement.jsonl'
MAP=ROOT/'results/runs/paper_actual_output_review_windows_20261021_01/coordinator_private_mapping.json'
FREEZE=ROOT/'results/runs/paper_execution_freeze_windows_20261020_01/execution_freeze.json'
INTAKE=ROOT/'results/CURRENT_OUTPUT_REVIEW_INTAKE.json'
OUT=ROOT/'results/runs/primary_provider_only_robustness_20261028_01'
G1='merged_corpus_generic_cited_rag';G2='dual_source_generic_cited_rag';G3='dual_source_role_grounded_rag'
LABEL={G1:'G1',G2:'G2',G3:'G3','no_rerank':'No rerank','bm25_only':'BM25',
       'minus_annual':'No annual','minus_regulation':'No regulation',
       'k28__'+G1:'K2.8 G1','k28__'+G2:'K2.8 G2','k28__'+G3:'K2.8 G3'}

def summary(rows):
    if not rows:return {'questions':0,'companies':0,'answer_mean':None,'company_macro':None}
    b=defaultdict(list)
    for r in rows:b[r['company']].append(r['value'])
    return dict(questions=len(rows),companies=len(b),answer_mean=float(np.mean([r['value'] for r in rows])),company_macro=float(np.mean([np.mean(v) for v in b.values()])))

def contrast(rows,base,treat,rating='mean',allowed=None,primary=False):
    by={(r['question_id'],r['mode']):r for r in rows}
    full=[x for x in grouping if allowed is None or x['question_id'] in allowed]
    observed=[];missing=[];lower_sum=0.0;upper_sum=0.0
    for q in full:
        qid=q['question_id'];a=by.get((qid,base));b=by.get((qid,treat))
        a_known=a is not None and (not primary or not a['used_recovery'])
        b_known=b is not None and (not primary or not b['used_recovery'])
        av=a[rating]['total'] if a_known else None
        bv=b[rating]['total'] if b_known else None
        lower_sum+=(bv if b_known else 0)-(av if a_known else 8)
        upper_sum+=(bv if b_known else 8)-(av if a_known else 0)
        if a_known and b_known:
            observed.append(dict(question_id=qid,company=q['company_cluster'],topic=q['topic'],value=b[rating]['total']-a[rating]['total']))
        else:missing.append(qid)
    blocks=defaultdict(list)
    for r in observed:blocks[r['company']].append(r['value'])
    values=np.array([np.mean(v) for _,v in sorted(blocks.items())],float)
    ci=None
    if len(values)>1:
        rng=np.random.default_rng(20261023)
        ci=np.quantile(values[rng.integers(0,len(values),size=(20000,len(values)))].mean(axis=1),[.025,.975]).tolist()
    # Question-average finite-range bounds are explicit, not a missing-at-random estimate.
    total=sum(r['value'] for r in observed);n=len(full);m=n-len(observed)
    loco=[dict(company_omitted=c,value=float(np.mean([np.mean(v) for cc,v in blocks.items() if cc!=c]))) for c in sorted(blocks)] if len(blocks)>1 else []
    lo=[r['value'] for r in loco]
    return dict(baseline=LABEL[base],treatment=LABEL[treat],rating=rating,planned_questions=n,observed_pairs=len(observed),
        observed_companies=len(blocks),observed_pair_question_mean=float(total/len(observed)) if observed else None,
        observed_pair_company_macro=float(values.mean()) if len(values) else None,cluster_ci95_20000=ci,
        full_question_average_bounds=[(total-8*m)/n,(total+8*m)/n],
        full_question_average_bounds_using_available_counterparts=[lower_sum/n,upper_sum/n],
        missing_question_ids=missing,loco_range=[min(lo),max(lo)] if lo else None,
        positive_company_clusters=int((values>0).sum()),zero_company_clusters=int((values==0).sum()),negative_company_clusters=int((values<0).sum()),
        company_differences=[dict(company=c,value=float(np.mean(v)),observed_questions=len(v)) for c,v in sorted(blocks.items())],
        leave_one_company_out=loco)

if __name__=='__main__':
    if OUT.exists():raise ValueError(f'Preserve existing analysis; use a new run: {OUT}')
    all_scores=read(SCORES);stats=read(STATS);mapping=read(MAP);freeze=read(FREEZE);intake=read(INTAKE)
    supplements=[json.loads(line) for line in SUPPLEMENTS.read_text(encoding='utf-8').splitlines() if line.strip()]
    supplement_keys={(r['question_id'],r['original_condition']) for r in supplements}
    supplemented_scored=[r for r in all_scores if (r['question_id'],r['mode']) in supplement_keys]
    grouping=freeze['grouping'];qlookup={r['question_id']:r for r in grouping}
    expected={r['output_id']:r for r in mapping if r['status']=='completed'}
    paths=[Path(r['file']) for r in intake['accepted_reviews']]
    for r,p in zip(intake['accepted_reviews'],paths):assert sha(p)==r['sha256']
    a,b=[validate_submission(read(p),expected) for p in paths]
    checked=[]
    for r in all_scores:
        key=r['output_id'];m=expected[key]
        for f in FIELDS:
            assert r['R1'][f]==a[key][f] and r['R2'][f]==b[key][f]
            assert r['mean'][f]==(a[key][f]+b[key][f])/2
        assert r['mean']['total']==sum(r['mean'][f] for f in FIELDS)
        r['used_recovery']=m.get('used_recovery',False);r['topic']=qlookup[r['question_id']]['topic']
        assert sha(m['source_file'])==m['source_sha256']
        checked.append(m['source_file'])
    assert len(all_scores)==386 and len(supplements)==33 and len(supplemented_scored)==31
    scores=[r for r in all_scores if (r['question_id'],r['mode']) not in supplement_keys]
    assert len(scores)==355 and len(mapping)==400 and len(checked)==386
    supplement_counts=Counter(r['mode'] for r in supplemented_scored)
    inventory=[]
    for mode,label in LABEL.items():
        planned=[r for r in mapping if r['mode']==mode];available=[r for r in scores if r['mode']==mode]
        inventory.append(dict(mode=mode,label=label,planned=len(planned),available=len(available),missing=len(planned)-len(available),
            primary_completed=sum(r.get('primary_status')=='completed' for r in planned),used_recovery=sum(r['used_recovery'] for r in available),
            missing_by_topic={t:sum(qlookup[r['question_id']]['topic']==t for r in planned if r['status']!='completed') for t in ['D1','D2','D3']}))
    fullset={r['question_id'] for r in grouping};small={r['question_id'] for r in freeze['robustness']['selection']}
    contrasts={}
    defs=[('G2-G1',G1,G2,fullset),('G3-G2',G2,G3,fullset),('G3-G1',G1,G3,fullset),
          ('G3-NoRerank','no_rerank',G3,fullset),('G3-BM25','bm25_only',G3,fullset),
          ('NoAnnual-G3',G3,'minus_annual',small),('NoRegulation-G3',G3,'minus_regulation',small)]
    for name,base,treat,qs in defs:
        contrasts[name]={rating:contrast(scores,base,treat,rating,qs) for rating in ['mean','R1','R2']}
    primary={name:contrast(scores,base,treat,'mean',qs,True) for name,base,treat,qs in defs[:3]}
    sets={'three_main':[G1,G2,G3],'five_main_and_retrieval':[G1,G2,G3,'no_rerank','bm25_only']}
    complete={}
    by={(r['question_id'],r['mode']):r for r in scores}
    for name,modes in sets.items():
        qs={q for q in fullset if all((q,m) in by for m in modes)}
        complete[name]=dict(question_ids=sorted(qs),questions=len(qs),companies=len({qlookup[q]['company_cluster'] for q in qs}),
            method_means={LABEL[m]:summary([dict(company=by[q,m]['company'],value=by[q,m]['mean']['total']) for q in qs]) for m in modes},
            contrasts={d:contrast(scores,base,treat,'mean',qs) for d,base,treat,_ in defs[:5] if base in modes and treat in modes})
    # Whole-company complete-case views retain all three topics within a company.
    company_sets={}
    for name,modes in sets.items():
        companies={r['company_cluster'] for r in grouping if all((q['question_id'],m) in by for q in grouping if q['company_cluster']==r['company_cluster'] for m in modes)}
        qs={r['question_id'] for r in grouping if r['company_cluster'] in companies}
        company_sets[name]=dict(questions=len(qs),companies=len(companies),company_ids=sorted(companies),contrasts={d:contrast(scores,base,treat,'mean',qs) for d,base,treat,_ in defs[:5] if base in modes and treat in modes})
    # Per-method quality score bounds on every planned slot; no zeros actually imputed.
    bounds=[]
    for mode,label in LABEL.items():
        group=[r for r in scores if r['mode']==mode];n=sum(r['mode']==mode for r in mapping);total=sum(r['mean']['total'] for r in group);m=n-len(group)
        bounds.append(dict(mode=mode,label=label,observed=len(group),planned=n,observed_answer_mean=total/len(group),full_planned_mean_lower=total/n,full_planned_mean_upper=(total+8*m)/n))
    failures=[dict(output_id=r['output_id'],question_id=r['question_id'],company=r['company'],mode=r['mode'],topic=qlookup[r['question_id']]['topic'],status=r['status'],primary_status=r.get('primary_status')) for r in mapping if r['status']!='completed']
    constraints=[
        'Four 0/1/2 ratings measure exploratory answer quality, not governance quality or calibrated legal-accuracy probability.',
        'No adjudication was performed. Mean-of-two aggregation was chosen after reviewing ratings by project-owner instruction; disclose timing.',
        'Intervals are exploratory pointwise company bootstrap summaries, not preregistered H1/H2, and do not solve unknown outcome bias.',
        'Page references are human-adjudicated physical pages; chunk/page overlap is not semantic support or exhaustive retrieval recall.',
        '20 companies with three templated topics and shared law documents do not establish generalization to unseen laws, sectors, languages or years.',
        'The main alias k3 has no independently verified provider model revision; temperature=1, one repeat per condition.',
        'API recovery outputs are explicitly merged first valid outputs, not extra samples; first-attempt and recovered results must remain separate.',
        'Thirty-three answers were authored in the current assistant session; 31 were independently scored, but the original prompt was not executed and there were zero additional provider API calls. All 31 are excluded from controlled provider comparisons.',
        'Only 355 two-reviewer-scored outputs from the recorded provider-generation runs enter this filtered analysis; the original 386-score analysis remains preserved as a superseded historical artifact.',
        'Source-removal conditions reduce available context information and token count jointly; they establish necessity under this setup, not a purely role-label causal effect.',
        'NoRerank and BM25 observed quality exceed G3, so claims that dense retrieval, reranking or role constraints are uniformly superior are unsupported.',
        'BM25 reviewer 2 assigned 8/8 to every observed answer; ceiling and reviewer dependence prevent treating it as verified near-perfect reasoning.',
        'Do not label this implemented pipeline as a multi-agent system without actual planning/tool-use/revision execution and matched evaluation.'
    ]
    report=dict(created_at_utc=datetime.now(timezone.utc).isoformat(),kind='posthoc_primary_provider_only_robustness_reanalysis',
        independent_unit='company',bootstrap_draws=20000,seed=20261023,no_paid_calls=True,originals_modified=False,
        arithmetic_and_source_hash_crosscheck=dict(original_score_rows=386,session_authored_supplements=33,scored_supplements_excluded=31,
            remaining_provider_output_rows=355,reviewer_score_fields_validated_before_filter=386*4*2,
            provider_files_hash_verified_for_included_rows=355,passed=True),
        supplement_exclusion=dict(generation_origin='current_assistant_session',additional_api_calls=0,original_prompt_executed=False,
            identical_api_protocol=False,blind_generation=False,scored_units_excluded=31,unscored_units=2,
            excluded_scored_by_mode=dict(supplement_counts)),
        inventory=inventory,contrasts=contrasts,primary_only_sensitivity=primary,question_complete_case=complete,
        whole_company_complete_case=company_sets,planned_score_bounds=bounds,failures=failures,validity_constraints=constraints,
        input_hashes=[dict(file=str(p),sha256=sha(p)) for p in [SCORES,STATS,SUPPLEMENTS,MAP,FREEZE,INTAKE,*paths]])
    OUT.mkdir(parents=True)
    write('robustness_audit_primary_provider_only.json',report)
    write('per_output_scores_primary_provider_only.json',scores)
    dumpcsv('planned_score_bounds_primary_provider_only.csv',bounds);dumpcsv('failure_inventory_primary_provider_only.csv',failures)
    flat=[]
    for name,ratings in contrasts.items():
        for rating,x in ratings.items():
            flat.append(dict(contrast=name,rating=rating,pairs=x['observed_pairs'],companies=x['observed_companies'],company_macro=x['observed_pair_company_macro'],ci_lower=x['cluster_ci95_20000'][0],ci_upper=x['cluster_ci95_20000'][1],loco_min=x['loco_range'][0],loco_max=x['loco_range'][1],full_lower=x['full_question_average_bounds_using_available_counterparts'][0],full_upper=x['full_question_average_bounds_using_available_counterparts'][1],positive_clusters=x['positive_company_clusters'],ties=x['zero_company_clusters'],negative_clusters=x['negative_company_clusters']))
    dumpcsv('paired_loco_missingness_primary_provider_only.csv',flat)
    lines=['排除会话补充回答后的证据与稳健性复核（2026-10-28）','',
        '原始 386 条评分中，有 31 条对应当前助手会话撰写的补充答案：33条补充记录仅来自会话、没有新增API调用，31条进入双人评分，2条未评分。它们未执行冻结的Kimi提示和API协议，故全部排除。',
        '过滤后保留355条供应商生成输出的双人评分；逐条核验的原评分字段仍为386条记录的全部3,088个双人逐维字段。没有改写原始记录，也未发起模型调用。',
        '重算内容：20,000次公司聚类bootstrap、逐公司删一、完整题/公司配对、主首轮提供方输出子集、缺失界及各条件可用数。','',
        '比较 | 已观测配对 | 公司宏差值 | 95%区间 | 删一范围 | 全计划题均差保守界']
    for name,v in contrasts.items():
        x=v['mean'];lines.append(f"{name} | {x['observed_pairs']}/{x['planned_questions']} | {x['observed_pair_company_macro']:.4f} | {x['cluster_ci95_20000']} | {x['loco_range']} | {x['full_question_average_bounds_using_available_counterparts']}")
    lines+=['','完整样本敏感性：']
    for name,s in complete.items():
        lines.append(f"按题完整 {name}: {s['questions']} 题，{s['companies']} 公司；"+'; '.join(f"{d}={x['observed_pair_company_macro']:.4f}" for d,x in s['contrasts'].items()))
    for name,s in company_sets.items():
        lines.append(f"按公司完整 {name}: {s['questions']} 题，{s['companies']} 公司；"+'; '.join(f"{d}={x['observed_pair_company_macro']:.4f}" for d,x in s['contrasts'].items()))
    lines+=['','首轮回答共同成功子集（受选择偏差影响）：']+[f"{name}: {v['observed_pairs']} 题，宏差值={v['observed_pair_company_macro']:.4f}" for name,v in primary.items()]
    lines+=['','论断约束：']+[f'{i+1}. {s}' for i,s in enumerate(constraints)]
    (OUT/'审计结论_primary_provider_only.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8-sig')
    print('\n'.join(lines[:19]))
