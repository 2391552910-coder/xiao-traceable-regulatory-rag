from src.generation.annual_audit_development import valid_answer,parse_planning


def answer():
    return dict(members=['甲'],meeting_count=4,meeting_dates=['2024-04-29'],citations={k:['A1'] for k in ['members','meeting_count','meeting_dates']},limitations=[])


def test_extraction_schema_distinguishes_boolean_count_and_integer():
    value=answer();assert valid_answer(value)
    value['meeting_count']=True;assert not valid_answer(value)
    value['meeting_count']=None;assert valid_answer(value)
    value['citations'].pop('members');assert not valid_answer(value)


def test_planning_rejects_wrong_query_type_without_repairing_model_output():
    assert parse_planning({'queries':['一','二','三']})==(['一','二'],True)
    assert parse_planning({'queries':[' ', '有效']})==(['有效'],True)
    assert parse_planning({'queries':'错误'})==([],False)
    assert parse_planning([])==([],False)
