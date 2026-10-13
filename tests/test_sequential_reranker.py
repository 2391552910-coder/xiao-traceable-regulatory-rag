"""Offline protocol and lifecycle regression; no downloaded weights or quality claims."""
from contextlib import nullcontext
from types import SimpleNamespace
import sys
import weakref

import numpy as np
import pytest

from src.data.clause_splitter import Chunk
from src.retrieval.dense import DenseRetriever
from src.retrieval.reranker import Reranker
from src.retrieval.model_runtime import SequentialModelRuntime


class Tensor:
    def __init__(self, value): self.value = np.asarray(value)
    def __getitem__(self, key): return Tensor(self.value[key])
    def to(self, device): return self
    def float(self): return self
    def cpu(self): return self
    def numpy(self): return self.value


def chunks():
    return [Chunk(str(i), 'D', 'rule', 'regulation', 'test', None, text)
            for i, text in enumerate(['good evidence', 'bad evidence'])]


@pytest.fixture
def fake_models(monkeypatch):
    events, weights, token_calls = [], [], []

    def allocated(obj, kind):
        assert not any(ref() is not None for ref in weights), 'two weight models overlap'
        weights.append(weakref.ref(obj))
        events.append(kind)

    class Embedding:
        max_seq_length = 32768
        device = 'cpu'
        def __init__(self, *a, **kw): allocated(self, 'embedding')
        def parameters(self): return iter([SimpleNamespace(dtype='float32')])
        def encode(self, texts, **kw):
            token_calls.append(('embedding', texts, kw))
            return np.asarray([[1., 0.] for t in texts])

    class Tokenizer:
        pad_token_id = 0
        unk_token_id = 99
        padding_side = 'left'
        def encode(self, text, **kw): return [10] if text.startswith('<|im_start|>system') else [11]
        def convert_tokens_to_ids(self, text): return {'no':0,'yes':1}[text]
        def __call__(self, texts, **kw):
            token_calls.append(('reranker', texts, kw))
            assert kw['max_length'] == 30
            return {'input_ids':[[20] if 'good evidence' in t else [30,30] for t in texts]}
        def pad(self, tokens, **kw):
            assert self.padding_side == 'left'
            ids = tokens['input_ids']; length=max(map(len, ids))
            assert all(r[0]==10 and r[-1]==11 for r in ids)
            return {'input_ids':Tensor([[0]*(length-len(r))+r for r in ids]),
                    'attention_mask':Tensor([[0]*(length-len(r))+[1]*len(r) for r in ids])}

    class Causal:
        device = 'cpu'
        config = SimpleNamespace(_commit_hash='fixture-revision')
        def __init__(self): allocated(self, 'reranker')
        def parameters(self): return iter([SimpleNamespace(dtype='float32')])
        def to(self, device): return self
        def eval(self): return self
        def __call__(self, input_ids, attention_mask, logits_to_keep, use_cache):
            assert logits_to_keep == 1 and use_cache is False
            ids=input_ids.value
            assert (ids[:,-1]==11).all()
            logits=np.zeros((*ids.shape,3))
            logits[:,-1,1]=[2 if 20 in row else -2 for row in ids]
            logits[:,-1,2]=100  # Unrelated vocab token must not enter binary normalization.
            return SimpleNamespace(logits=Tensor(logits))

    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(inference_mode=nullcontext))
    monkeypatch.setitem(sys.modules,'sentence_transformers',SimpleNamespace(SentenceTransformer=Embedding))
    monkeypatch.setitem(sys.modules,'transformers',SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a,**kw: Tokenizer()),
        AutoModelForCausalLM=SimpleNamespace(from_pretrained=lambda *a,**kw: Causal())))
    return events, token_calls


def test_causal_yes_no_protocol_and_lazy_loading(fake_models):
    events,calls=fake_models
    reranker=Reranker(max_length=32,batch_size=2)
    assert not events and reranker.score('q',[])==[]
    scores=reranker.score('question',chunks())
    assert scores == pytest.approx([1/(1+np.exp(-2)),1/(1+np.exp(2))])
    assert calls[0][1][0].endswith('<Query>: question\n<Document>: good evidence')
    assert events==['reranker']
    assert reranker.encoding_metadata['resolved_revision']=='fixture-revision'


def test_weights_alternate_without_overlap_and_query_cache_is_prompt_aware(fake_models):
    events,_=fake_models
    runtime=SequentialModelRuntime()
    dense=DenseRetriever(chunks(),backend='qwen',model_runtime=runtime,query_prompt='p1')
    dense.search('question')
    rr=Reranker(max_length=32,batch_size=2,model_runtime=runtime)
    rr.score('question',chunks())
    assert dense._model is None
    dense.search('question')  # Cache avoids a reload without changing scores.
    assert events==['embedding','reranker']
    dense.query_prompt='p2'
    dense.search('question')
    assert rr._model is None and events==['embedding','reranker','embedding']
    rr.score('question',chunks())
    assert events==['embedding','reranker','embedding','reranker']
    runtime.release()
    assert dense._model is rr._model is None


def test_failed_load_does_not_poison_runtime():
    runtime=SequentialModelRuntime()
    class Broken:
        def _load_weights(self): raise ValueError('fixture load failure')
        def _unload_weights(self): self.cleaned=True
    owner=Broken()
    with pytest.raises(ValueError): runtime.acquire(owner)
    assert runtime.owner is None and owner.cleaned


def test_pipeline_shares_runtime_and_repeated_search_switches_weights(fake_models, monkeypatch):
    from src import pipeline
    from src.config import load_config
    cfg=load_config()
    cfg['retrieval']['reranker'].update(enabled=True,device='cpu',max_length=32,batch_size=2)
    monkeypatch.setattr(pipeline,'load_documents',lambda path:[{
        'doc_id':'D','title':'fixture','doc_type':'regulation','source':'fixture',
        'text':'第一条 good evidence\n第二条 bad evidence'}])
    _,retriever=pipeline.build_knowledge_index(cfg)
    assert retriever.dense._runtime is retriever.reranker._runtime
    assert fake_models[0]==['embedding']
    hits=retriever.search('first question',2)
    assert 'good evidence' in hits[0][0].text
    assert retriever.dense._model is None
    retriever.search('different question',2)
    assert fake_models[0]==['embedding','reranker','embedding','reranker']
    retriever.dense._runtime.release()


@pytest.mark.parametrize('kw',[{'batch_size':0},{'max_length':0},{'model_name':'Qwen/Qwen3-Reranker-4B'}])
def test_invalid_resources_fail_before_loading(kw):
    with pytest.raises(ValueError): Reranker(**kw)
