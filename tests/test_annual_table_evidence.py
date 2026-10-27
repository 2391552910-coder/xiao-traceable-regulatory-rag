import copy
import pytest
from src.data.clause_splitter import Chunk
from src.generation.comparison import _pack_context
from src.generation.annual_table_evidence import augment_with_table_evidence


Q=dict(stock_code='000001',report_year=2024,query='提取审计委员会成员')


def chunk(cid,stock='000001',year=2024,text='原始字段'):
    return Chunk(cid,'report','测试年报','annual_report','https://example.invalid/report',None,text,
                 meta=dict(corpus_type='annual_report',stock_code=stock,report_year=year,
                           company_name='测试',physical_pdf_page_1based=1,source_pdf_sha256='a'*64,
                           system_corpus_input=True))


class Index:
    def __init__(self,hits):self.hits=hits
    def search(self,q,query,**kwargs):
        assert q==Q and query==Q['query'] and kwargs['committee']=='审计'
        return self.hits


def test_adapter_preserves_ids_and_exports_query_scope():
    initial=_pack_context([(chunk('seed'),1)],len,6000);before=copy.deepcopy(initial)
    final,audit=augment_with_table_evidence(Q,initial,Index([(chunk('table'),1)]),len)
    assert initial==before and final['source_records'][0]==initial['source_records'][0]
    assert audit['accepted_count']==1 and audit['table_retrieval']['model_calls']==0
    assert audit['table_retrieval']['candidate_ids']==['table']


def test_adapter_does_not_evict_when_complete_table_row_exceeds_budget():
    initial=_pack_context([(chunk('seed'),1)],len,6000)
    final,audit=augment_with_table_evidence(Q,initial,Index([(chunk('table',text='X'*1000),1)]),len,max_context_tokens=initial['reference_tokens'])
    assert final==initial and audit['budget_blocked']


@pytest.mark.parametrize('stock,year',[('000002',2024),('000001',2023)])
def test_adapter_rejects_cross_company_or_year_from_bad_index(stock,year):
    initial=_pack_context([(chunk('seed'),1)],len,6000)
    with pytest.raises(ValueError,match='company/year'):
        augment_with_table_evidence(Q,initial,Index([(chunk('wrong',stock,year),1)]),len)
