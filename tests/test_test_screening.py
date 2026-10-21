import csv
import json
from pathlib import Path
import pytest
from scripts.import_test_screening import run
from scripts.import_human_reviews import digest

ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'data/operator_handoff/20261013'


def forms(tmp_path, source='yes'):
    for tag in ['A','B']:
        with (PACKET/f'test_screening_{tag}.csv').open(encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f))
        for r in rows:
            r.update(family_overlap='no',source_verified=source if r['query_id']=='H009' else 'U',
                     temporal_scope_verified='yes',evidence_ids='DOC005-V2-0194' if r['query_id']=='H009' else '',
                     reviewer='SYNTHETIC-'+tag,reviewed_at='2026-10-13T00:00:00Z',rationale='Synthetic fixture only')
        with (tmp_path/f'{tag}.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def test_operator_packet_hashes_and_blank_screening(tmp_path):
    m=json.loads((PACKET/'manifest.json').read_text())
    for name,value in m['artifacts_sha256'].items():assert digest(PACKET/name)==value
    for name,value in m['inputs_sha256'].items():assert digest(ROOT/name)==value
    report=run(PACKET,PACKET/'test_screening_A.csv',PACKET/'test_screening_B.csv',tmp_path/'out')
    assert all(r['status']=='pending_two_screeners' for r in report['decisions'])
    assert report['formal_test_labels_created']==0 and not report['qrels_written']


def test_coordinator_cannot_promote_unknown_sources_or_make_test_gold(tmp_path):
    forms(tmp_path)
    report=run(PACKET,tmp_path/'A.csv',tmp_path/'B.csv',tmp_path/'out')
    for r in report['decisions']:
        r.update(coordinator_decision='proceed_to_evidence_labeling',coordinator='SYNTHETIC-C',
                 decided_at='2026-10-13T01:00:00Z',reason='Synthetic decision only')
    file=tmp_path/'decisions.json';file.write_text(json.dumps(report))
    with pytest.raises(ValueError,match='Cannot advance'):run(PACKET,tmp_path/'A.csv',tmp_path/'B.csv',tmp_path/'bad',file)
    for r in report['decisions']:
        if r['query_id']=='H005':r['coordinator_decision']='request_more_evidence'
    file.write_text(json.dumps(report))
    accepted=run(PACKET,tmp_path/'A.csv',tmp_path/'B.csv',tmp_path/'accepted',file)
    assert accepted['formal_test_labels_created']==0 and not accepted['qrels_written']


def test_unregistered_source_is_rejected(tmp_path):
    forms(tmp_path)
    file=tmp_path/'A.csv';file.write_text(file.read_text(encoding='utf-8-sig').replace('DOC005-V2-0194','MADE-UP'),encoding='utf-8-sig')
    with pytest.raises(ValueError,match='frozen source'):run(PACKET,file,tmp_path/'B.csv',tmp_path/'out')
