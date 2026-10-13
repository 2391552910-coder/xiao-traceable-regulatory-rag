"""Import independent family/source screening only; never emit final-test qrels."""
import argparse
import csv
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.import_human_reviews import read, digest, timestamp

FIELDS={'family_overlap','development_query_ids','source_verified','temporal_scope_verified',
        'evidence_ids','reviewer','reviewed_at','rationale'}


def validate(template,submission):
    original={r['query_id']:r for r in read(template)}
    rows=read(submission)
    if len(rows)!=len(original) or {r['query_id'] for r in rows}!=original.keys():
        raise ValueError('Changed or duplicate screening assignment')
    reviewers=set()
    for row in rows:
        if row.keys()!=original[row['query_id']].keys():raise ValueError('Changed screening columns')
        if any(row[k]!=original[row['query_id']][k] for k in row.keys()-FIELDS):raise ValueError('Changed query identity')
        for field in ['family_overlap','source_verified','temporal_scope_verified']:
            if row[field] not in {'','yes','no','U'}:raise ValueError('Screening values must be yes/no/U or blank')
        if any(row[k] for k in FIELDS):
            if (not all(row[k] for k in ['family_overlap','source_verified','temporal_scope_verified','reviewer','rationale'])
                or not timestamp(row['reviewed_at'])):raise ValueError('Partially completed screening')
            if row['source_verified']=='yes' and not row['evidence_ids'].strip():raise ValueError('Verified source needs evidence IDs')
            if row['family_overlap']=='yes' and not row['development_query_ids'].strip():raise ValueError('Overlap needs development query IDs')
            reviewers.add(row['reviewer'].strip())
    if len(reviewers)>1:raise ValueError('One reviewer per independent form')
    return {r['query_id']:r for r in rows},next(iter(reviewers),None)


def run(packet,a,b,out,decisions=None):
    if out.exists():raise FileExistsError(out)
    m=json.loads((packet/'manifest.json').read_text(encoding='utf-8'))
    for tag in ['A','B']:
        name=f'test_screening_{tag}.csv'
        if digest(packet/name)!=m['artifacts_sha256'][name]:raise ValueError('Blank screening template changed')
    left,ra=validate(packet/'test_screening_A.csv',a);right,rb=validate(packet/'test_screening_B.csv',b)
    if ra and ra==rb:raise ValueError('Screeners must be different people')
    context_path=packet/'test_source_context.json'
    if digest(context_path)!=m['artifacts_sha256']['test_source_context.json']:
        raise ValueError('Source context changed')
    context=json.loads(context_path.read_text(encoding='utf-8'))
    for submitted in [left,right]:
        for qid,row in submitted.items():
            if row['source_verified']=='yes':
                allowed={context.get(qid,{}).get('chunk',{}).get('chunk_id')} - {None}
                if not allowed or set(row['evidence_ids'].split(';'))-allowed:
                    raise ValueError('Evidence not in frozen source packet; prepare a new version first')
    rows=[]
    for qid,r in left.items():
        other=right[qid]
        if not r['reviewer'] or not other['reviewer']:status='pending_two_screeners'
        elif 'yes' in [r['family_overlap'],other['family_overlap']]:status='blocked_possible_development_overlap'
        elif any(r[k]!=other[k] for k in ['family_overlap','source_verified','temporal_scope_verified']):status='needs_independent_arbitration'
        elif r['family_overlap']=='no' and r['source_verified']==r['temporal_scope_verified']=='yes':status='screening_agreement_needs_evidence_labels_and_coordinator_verification'
        else:status='blocked_unknown_or_unverified_source'
        rows.append({'query_id':qid,'status':status,'review_a':r,'review_b':other,
                     'coordinator_decision':'','coordinator':'','decided_at':'','reason':''})
    if decisions is not None:
        supplied=json.loads(Path(decisions).read_text(encoding='utf-8'))
        if supplied.get('input_sha256')!={'A':digest(a),'B':digest(b),'packet':digest(packet/'manifest.json')}:
            raise ValueError('Coordinator decisions refer to different inputs')
        answers={r['query_id']:r for r in supplied['decisions']}
        if len(answers)!=len(rows) or len(supplied['decisions'])!=len(rows) or answers.keys()!=left.keys():
            raise ValueError('Changed coordinator assignment')
        editable={'coordinator_decision','coordinator','decided_at','reason'}
        for row in rows:
            answer=answers[row['query_id']]
            if answer.keys()!=row.keys() or any(answer[k]!=row[k] for k in row.keys()-editable):
                raise ValueError('Coordinator changed submitted evidence or screening status')
            action=answer['coordinator_decision']
            if not action and not any(answer[k] for k in editable):continue
            if action not in {'reject','request_more_evidence','proceed_to_evidence_labeling'}:
                raise ValueError('Invalid coordinator decision')
            if (not answer['coordinator'].strip() or answer['coordinator'].strip() in {ra,rb}
                or not timestamp(answer['decided_at']) or not answer['reason'].strip()):
                raise ValueError('Independent coordinator identity, timestamp and reason required')
            if action=='proceed_to_evidence_labeling' and row['status']!='screening_agreement_needs_evidence_labels_and_coordinator_verification':
                raise ValueError('Cannot advance overlap, disagreement, or unverified evidence')
            row.update({k:answer[k] for k in editable})
    out.mkdir(parents=True)
    report={'usage':'test_candidate_screening_only','formal_test_labels_created':0,
            'identity_or_independence_authenticated':False,'qrels_written':False,
            'input_sha256':{'A':digest(a),'B':digest(b),'packet':digest(packet/'manifest.json')},'decisions':rows}
    (out/'screening_decisions.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['packet-dir','a','b','out-dir']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--decisions',type=Path)
    args=p.parse_args();print(json.dumps(run(args.packet_dir,args.a,args.b,args.out_dir,args.decisions),ensure_ascii=False,indent=2))
