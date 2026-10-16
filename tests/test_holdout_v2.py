from src.data.holdout_v2 import release_errors_v2


def test_inventory_cannot_be_omitted_and_query_id_cannot_be_reused():
    rows=[{'query_id':'H1','query':q} for q in ['第一题','第二题']]
    errors=release_errors_v2(rows,None)
    assert ('','development_inventory_required') in errors
    assert ('H1','duplicate_query_id') in errors


def test_ai_family_collision_and_wrong_task_cannot_be_released():
    row={'query_id':'H1','query':'新措辞','development_family_matches':['Q13'],
         'task_type':'evidence_verification_probe','status':'human_reviewed_release_candidate'}
    errors=release_errors_v2([row],{'queries':['开发题'],'input_sha256':{'example':'hash'}})
    assert ('H1','documented_development_family_overlap') in errors
    assert ('H1','separate_task_protocol_required') in errors
    assert ('H1','auditable_human_review_record_required') in errors
