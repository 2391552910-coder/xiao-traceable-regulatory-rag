import copy
from pathlib import Path
import pytest
from scripts._table_runtime import ensure_local_pdf_libraries
ensure_local_pdf_libraries()
from src.data.annual_tables import extract_document,extract_pdfium_pages,file_sha256
from src.data.clause_splitter import Chunk
from src.retrieval.annual_table_index import row_units
from src.generation.comparison import _pack_context
from src.generation.evidence_budget import POLICIES,allocate_evidence_budget,boundary_cues

Q=dict(stock_code='000001',report_year=2024,query='提取审计委员会成员和会议日期')


@pytest.fixture(scope='module')
def tables():
    path=Path(__file__).parent/'fixtures/annual_tables_synthetic_v1.pdf'
    source=dict(stock='000001',year=2024,company='测试',file=path.name,url='https://example.invalid/synthetic.pdf',sha256=file_sha256(path),pages=9)
    doc=extract_document(path,source,extract_pdfium_pages(path),all_pages=True)
    return [(c,1.) for c in row_units(doc)[0] if '审计' in c.meta['committee_labels']][:4]


def window(cid,text,sha,page=1):
    return Chunk(cid,'HELD-000001-2024','测试2024年报','annual_report','https://example.invalid/synthetic.pdf',None,text,
                 meta=dict(corpus_type='annual_report',stock_code='000001',report_year=2024,company_name='测试',
                           physical_pdf_page_1based=page,source_pdf_sha256=sha,system_corpus_input=True))


def packet(tables):
    sha=tables[0][0].meta['source_pdf_sha256']
    seed=window('HELD-000001-2024-P1-S0','背景'*1600+'第十六次会议（5月14日',sha)
    neighbor=window('HELD-000001-2024-P1-S1000','会议续片：5月23日、8月22日。'*8,sha)
    initial=_pack_context([(seed,1.)],len,6000)
    proposal=dict(chunk_id=neighbor.chunk_id,seed_chunk_id=seed.chunk_id,adjacent_hop=1,direction='successor',
                  same_page=True,page=1,start=1000,seed_page=1,seed_start=0)
    audit=dict(selected_candidates=[proposal],recursive_expansion=False,reference_labels_read=False,query_terms_used=False)
    return initial,[(neighbor,0.)],audit


@pytest.mark.parametrize('text,flag',[
    ('第十六次会议（5月14日',True),('2024\n年05\n月1',True),('2024-05-',True),
    ('2024年05月14日',False),('第十六次会议（5月14日）',False),('2024-05-14',False),
    ('普通完整文本。',False),('2024年第六次会议',False),
])
def test_boundary_heuristic_uses_suffix_without_a_complete_closed_date(text,flag):
    assert bool(boundary_cues(text)) is flag


@pytest.mark.parametrize('policy',POLICIES)
def test_all_policies_preserve_initial_inputs_ids_and_budget(tables,policy):
    initial,hits,audit=packet(tables);before=copy.deepcopy((initial,hits,audit,tables))
    final,trace=allocate_evidence_budget(Q,initial,tables,hits,audit,len,policy=policy)
    assert (initial,hits,audit,tables)==before
    assert final['context'].startswith(initial['context']) and final['source_records'][0]==initial['source_records'][0]
    assert final['reference_tokens']<=6000 and trace['accepted_count']<=16
    assert trace['labels_read'] is False and trace['boundary_cues_are_relevance_proof'] is False


def test_boundary_priority_really_changes_a_budget_conflict_without_eviction(tables):
    initial,hits,audit=packet(tables)
    table_context,_=allocate_evidence_budget(Q,initial,tables,[],dict(selected_candidates=[],recursive_expansion=False,reference_labels_read=False,query_terms_used=False),len,policy='table_first')
    cap=table_context['reference_tokens']
    baseline,_=allocate_evidence_budget(Q,initial,tables,hits,audit,len,policy='table_first',max_context_tokens=cap)
    repaired,trace=allocate_evidence_budget(Q,initial,tables,hits,audit,len,policy='boundary_first',max_context_tokens=cap)
    cid=hits[0][0].chunk_id
    assert cid not in {r['chunk_id'] for r in baseline['source_records']}
    assert cid in {r['chunk_id'] for r in repaired['source_records']}
    assert trace['attempts'][0]['lane']=='boundary_successor'


def test_global_source_cap_shared_across_lanes(tables):
    initial,hits,audit=packet(tables)
    final,trace=allocate_evidence_budget(Q,initial,tables,hits,audit,len,max_new_sources=1)
    assert len(final['source_records'])==2 and trace['accepted_count']==1
    assert any(t['reason']=='global_new_source_cap' for t in trace['attempts'])


@pytest.mark.parametrize('change',['company','year','pdf','audit_id','hop','direction','same_page','seed','query','score','table_text'])
def test_bad_scope_or_provenance_rejected_even_if_candidate_would_not_fit(tables,change):
    initial,hits,audit=packet(tables);tab=copy.deepcopy(tables);hits=copy.deepcopy(hits)
    if change=='company':hits[0][0].meta['stock_code']='000002'
    elif change=='year':hits[0][0].meta['report_year']=2023
    elif change=='pdf':hits[0][0].meta['source_pdf_sha256']='0'*64
    elif change=='audit_id':audit['selected_candidates'][0]['chunk_id']='forged'
    elif change=='hop':audit['selected_candidates'][0]['adjacent_hop']=2
    elif change=='direction':audit['selected_candidates'][0]['direction']='predecessor'
    elif change=='same_page':audit['selected_candidates'][0]['same_page']=False
    elif change=='seed':audit['selected_candidates'][0]['seed_chunk_id']='newly_retrieved_seed'
    elif change=='query':audit['query_terms_used']=True
    elif change=='score':hits[0]=(hits[0][0],float('nan'))
    elif change=='table_text':tab[0][0].text+=' invented'
    with pytest.raises(ValueError):
        allocate_evidence_budget(Q,initial,tab,hits,audit,len,max_context_tokens=initial['reference_tokens'])


def test_same_id_conflicting_content_cannot_hide_behind_deduplication(tables):
    initial,hits,audit=packet(tables);other=copy.deepcopy(hits[0][0]);other.text+=' changed'
    audit['selected_candidates'].append(copy.deepcopy(audit['selected_candidates'][0]))
    with pytest.raises(ValueError,match='conflicting'):
        allocate_evidence_budget(Q,initial,tables,hits+[(other,0.)],audit,len)


def test_repeat_policy_is_deterministic(tables):
    initial,hits,audit=packet(tables)
    assert allocate_evidence_budget(Q,initial,tables,hits,audit,len)==allocate_evidence_budget(Q,initial,tables,hits,audit,len)
