"""Validate independent development reviews, preserve disagreements, and import only attested labels."""
import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil

EDITABLE = {'human_grade', 'reviewer', 'reviewed_at', 'rationale'}
KEY = ('query_id', 'chunk_id')


def read(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.utcoffset() is not None
    except (ValueError, AttributeError):
        return False


def keyed(rows):
    result = {}
    for row in rows:
        key = tuple(row.get(k, '') for k in KEY)
        if not all(key) or key in result:
            raise ValueError('Missing or duplicate query/chunk identity')
        result[key] = row
    return result


def validate_review(template, submitted):
    originals, rows = keyed(read(template)), keyed(read(submitted))
    if originals.keys() != rows.keys():
        raise ValueError('Submission must contain exactly the assigned candidate set')
    reviewer_ids = set()
    for key, row in rows.items():
        if row.keys() != originals[key].keys():
            raise ValueError('Submission columns differ from the template')
        for field in row.keys() - EDITABLE:
            if row[field] != originals[key][field]:
                raise ValueError(f'{key}: immutable field changed: {field}')
        grade = row['human_grade'].strip()
        row['human_grade'] = grade
        if not grade:
            if any(row[field].strip() for field in EDITABLE - {'human_grade'}):
                raise ValueError(f'{key}: partially filled review without a grade')
            continue
        if grade not in {'0', '1', '2', 'U'} or not timestamp(row['reviewed_at']):
            raise ValueError(f'{key}: invalid grade or timezone-aware review date')
        if not row['reviewer'].strip() or not row['rationale'].strip():
            raise ValueError(f'{key}: reviewer and rationale are required')
        reviewer_ids.add(row['reviewer'].strip())
    if len(reviewer_ids) > 1:
        raise ValueError('Each independently assigned form must have one reviewer identity')
    return rows, next(iter(reviewer_ids), None)


def agreement(pairs):
    numeric = [(int(a), int(b)) for a, b in pairs if a in {'0','1','2'} and b in {'0','1','2'}]
    n = len(numeric)
    if not n:
        return {'numeric_pairs': 0, 'exact_agreement': None, 'quadratic_weighted_kappa': None,
                'direct_support_kappa': None}
    ca, cb = Counter(a for a,b in numeric), Counter(b for a,b in numeric)
    observed = sum((a-b)**2/4 for a,b in numeric)/n
    expected = sum(ca[a]*cb[b]*(a-b)**2/4 for a in ca for b in cb)/(n*n)
    pa, pb = sum(a==2 for a,b in numeric)/n, sum(b==2 for a,b in numeric)/n
    chance = pa*pb+(1-pa)*(1-pb)
    direct = sum((a==2)==(b==2) for a,b in numeric)/n
    return {'numeric_pairs': n, 'exact_agreement': sum(a==b for a,b in numeric)/n,
            'quadratic_weighted_kappa': 1-observed/expected if expected else None,
            'direct_support_kappa': (direct-chance)/(1-chance) if chance<1 else None,
            'excluded_U_or_blank_pairs': len(pairs)-n}


def run(packet, a_path, b_path, out, adjudications=None, attestation=None):
    if out.exists():
        raise FileExistsError(out)
    manifest = json.loads((packet/'manifest.json').read_text(encoding='utf-8'))
    for tag in ['A','B']:
        filename = f'blind_review_{tag}.csv'
        if digest(packet/filename) != manifest['artifacts_sha256'][filename]:
            raise ValueError('Original packet changed; do not overwrite the blank templates')
    a, reviewer_a = validate_review(packet/'blind_review_A.csv', a_path)
    b, reviewer_b = validate_review(packet/'blind_review_B.csv', b_path)
    if a.keys() != b.keys():
        raise ValueError('A/B assignment differs')
    if reviewer_a and reviewer_a == reviewer_b:
        raise ValueError('A/B must be different reviewers')
    decisions = keyed(read(adjudications)) if adjudications else {}
    disagreements, accepted, unresolved = [], [], []
    conflict_keys = set()
    for key in sorted(a):
        left, right = a[key], b[key]
        ga, gb = left['human_grade'], right['human_grade']
        resolved = ga if ga == gb and ga in {'0','1','2'} else None
        needs_adjudication = bool(ga and gb and (ga != gb or ga == 'U'))
        if needs_adjudication:
            conflict_keys.add(key)
            decision = decisions.get(key)
            if decision:
                expected = {'query':left['query'], 'text':left['text'], 'a_grade':ga,
                            'b_grade':gb, 'a_rationale':left['rationale'], 'b_rationale':right['rationale']}
                if any(decision.get(field) != value for field,value in expected.items()):
                    raise ValueError(f'{key}: adjudication context differs from current submissions')
                if (decision.get('adjudicated_grade') not in {'0','1','2','U'}
                    or not decision.get('adjudicator','').strip()
                    or decision['adjudicator'].strip() in {reviewer_a,reviewer_b}
                    or not timestamp(decision.get('reviewed_at')) or not decision.get('rationale','').strip()):
                    raise ValueError(f'{key}: invalid independent adjudication')
                if decision['adjudicated_grade'] != 'U':
                    resolved = decision['adjudicated_grade']
            disagreements.append({'query_id':key[0], 'chunk_id':key[1], 'query':left['query'],
                'text':left['text'], 'a_grade':ga, 'a_rationale':left['rationale'],
                'b_grade':gb, 'b_rationale':right['rationale'], 'adjudicated_grade':'',
                'adjudicator':'', 'reviewed_at':'', 'rationale':''})
        if resolved is None:
            unresolved.append({'query_id':key[0], 'chunk_id':key[1],
                               'reason':'missing_review' if not ga or not gb else 'unresolved_or_U'})
        else:
            accepted.append({'query_id':key[0], 'chunk_id':key[1], 'grade':int(resolved),
                             'method':'third_reviewer_adjudication' if needs_adjudication else 'independent_agreement',
                             'text_sha256':left['text_sha256']})
    if decisions.keys() - conflict_keys:
        raise ValueError('Adjudication includes an unassigned or non-disputed pair')
    att = json.loads(Path(attestation).read_text(encoding='utf-8')) if attestation else {}
    attested = bool(reviewer_a and reviewer_b and att.get('reviewer_a') == reviewer_a
        and att.get('reviewer_b') == reviewer_b and att.get('independent_work_confirmed') is True
        and att.get('provenance_checked') is True and att.get('coordinator','').strip()
        and timestamp(att.get('declared_at')) and att.get('packet_manifest_sha256') == digest(packet/'manifest.json'))
    complete = not unresolved and len(accepted)==len(a) and attested
    out.mkdir(parents=True)
    for tag, path in [('A',a_path),('B',b_path)]: shutil.copyfile(path,out/f'submitted_{tag}.csv')
    for name,path in [('adjudications.csv',adjudications),('attestation.json',attestation)]:
        if path: shutil.copyfile(path,out/name)
    fields=['query_id','chunk_id','query','text','a_grade','a_rationale','b_grade','b_rationale',
            'adjudicated_grade','adjudicator','reviewed_at','rationale']
    with (out/'adjudication_needed.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(disagreements)
    if complete:
        with (out/'development_qrels.tsv').open('w',encoding='utf-8',newline='') as f:
            writer=csv.writer(f,delimiter='\t');writer.writerow(['query_id','chunk_id','grade'])
            writer.writerows((r['query_id'],r['chunk_id'],r['grade']) for r in accepted)
    pairs=[(a[k]['human_grade'],b[k]['human_grade']) for k in a]
    report={'status':'attested_development_labels_imported' if complete else 'pending_reviews_adjudication_or_attestation',
            'usage':'development_only', 'assigned_pairs':len(a), 'numeric_resolved_pairs':len(accepted),
            'unresolved_pairs':unresolved, 'disputed_or_U_pairs':len(disagreements),
            'attestation_valid':attested, 'reviewer_identity_authenticated_by_software':False,
            'formal_test_labels_created':0, 'qrels_written':complete,
            'agreement_before_adjudication':agreement(pairs),
            'agreement_by_dimension':{d:agreement([(a[k]['human_grade'],b[k]['human_grade']) for k in a if a[k]['dimension']==d])
                                       for d in sorted({r['dimension'] for r in a.values()})},
            'packet_manifest_sha256':digest(packet/'manifest.json'),
            'submitted_files_sha256':{p.name:digest(p) for p in out.iterdir() if p.is_file()},
            'limitations':['Submitted identities and independence declarations require coordinator verification.',
                           'U is unresolved, never a negative label. Grade 2 is direct support; grade 1 is auxiliary.',
                           'Imported V2 qrels do not alter the old gold or establish an independent final test set.']}
    (out/'import_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['packet-dir','a','b','out-dir']:p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--adjudications',type=Path);p.add_argument('--attestation',type=Path)
    args=p.parse_args()
    result=run(args.packet_dir,args.a,args.b,args.out_dir,args.adjudications,args.attestation)
    print(json.dumps({k:v for k,v in result.items() if k!='unresolved_pairs'},ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['qrels_written'] else 2)
