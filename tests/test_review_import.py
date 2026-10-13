import csv
import hashlib
import json
import pytest
from scripts.import_human_reviews import run, agreement


def write_csv(path, rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def setup(tmp_path, ga='2', gb='2'):
    packet=tmp_path/'packet';packet.mkdir()
    base={'query_id':'FIXTURE-Q','chunk_id':'FIXTURE-C','dimension':'D1','query':'synthetic question',
          'text':'synthetic evidence','text_sha256':hashlib.sha256(b'synthetic evidence').hexdigest(),
          'human_grade':'','reviewer':'','reviewed_at':'','rationale':''}
    files={}
    for tag in ['A','B']:
        path=packet/f'blind_review_{tag}.csv';write_csv(path,[base]);files[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    (packet/'manifest.json').write_text(json.dumps({'artifacts_sha256':files}))
    for tag,grade in [('A',ga),('B',gb)]:
        row=base.copy()
        if grade:row.update(human_grade=grade,reviewer='SYNTHETIC-'+tag,reviewed_at='2026-10-13T00:00:00+00:00',rationale='Synthetic fixture only')
        write_csv(tmp_path/f'{tag}.csv',[row])
    att={'reviewer_a':'SYNTHETIC-A','reviewer_b':'SYNTHETIC-B','independent_work_confirmed':True,
         'provenance_checked':True,'coordinator':'SYNTHETIC-C','declared_at':'2026-10-13T00:00:00+00:00',
         'packet_manifest_sha256':hashlib.sha256((packet/'manifest.json').read_bytes()).hexdigest()}
    (tmp_path/'att.json').write_text(json.dumps(att))
    return packet


def test_blank_forms_and_missing_attestation_never_export(tmp_path):
    packet=setup(tmp_path,'','')
    report=run(packet,tmp_path/'A.csv',tmp_path/'B.csv',tmp_path/'out')
    assert not report['qrels_written'] and report['numeric_resolved_pairs']==0
    assert not (tmp_path/'out/development_qrels.tsv').exists()


def test_attested_agreement_exports_only_development_qrels(tmp_path):
    packet=setup(tmp_path)
    report=run(packet,tmp_path/'A.csv',tmp_path/'B.csv',tmp_path/'out',attestation=tmp_path/'att.json')
    assert report['qrels_written'] and report['formal_test_labels_created']==0
    assert report['agreement_before_adjudication']['quadratic_weighted_kappa'] is None
    with pytest.raises(FileExistsError):run(packet,tmp_path/'A.csv',tmp_path/'B.csv',tmp_path/'out')


def test_U_and_disagreement_require_third_reviewer_and_preserve_votes(tmp_path):
    packet=setup(tmp_path,'U','2')
    first=run(packet,tmp_path/'A.csv',tmp_path/'B.csv',tmp_path/'first',attestation=tmp_path/'att.json')
    assert not first['qrels_written']
    rows=list(csv.DictReader((tmp_path/'first/adjudication_needed.csv').open(encoding='utf-8-sig')))
    rows[0].update(adjudicated_grade='1',adjudicator='SYNTHETIC-C',reviewed_at='2026-10-13T01:00:00+00:00',rationale='Synthetic adjudication')
    write_csv(tmp_path/'adjudicate.csv',rows)
    result=run(packet,tmp_path/'A.csv',tmp_path/'B.csv',tmp_path/'second',tmp_path/'adjudicate.csv',tmp_path/'att.json')
    assert result['qrels_written'] and result['agreement_before_adjudication']['numeric_pairs']==0


def test_changed_evidence_same_reviewer_and_missing_assignment_are_rejected(tmp_path):
    packet=setup(tmp_path)
    rows=list(csv.DictReader((tmp_path/'B.csv').open(encoding='utf-8-sig')))
    rows[0]['reviewer']='SYNTHETIC-A';write_csv(tmp_path/'B.csv',rows)
    with pytest.raises(ValueError,match='different reviewers'):run(packet,tmp_path/'A.csv',tmp_path/'B.csv',tmp_path/'out')
    rows[0]['reviewer']='SYNTHETIC-B';rows[0]['text']='changed';write_csv(tmp_path/'B.csv',rows)
    with pytest.raises(ValueError,match='immutable'):run(packet,tmp_path/'A.csv',tmp_path/'B.csv',tmp_path/'out')


def test_numeric_disagreement_statistics_use_pre_adjudication_values():
    result=agreement([('0','2'),('2','0'),('U','2')])
    assert result['quadratic_weighted_kappa']==-1 and result['direct_support_kappa']==-1
    assert result['excluded_U_or_blank_pairs']==1
