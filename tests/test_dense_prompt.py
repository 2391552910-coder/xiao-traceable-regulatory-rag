"""Query instructions must never enter document embeddings."""
import sys
import types

import numpy as np
import pytest

from src.data.clause_splitter import Chunk
from src.retrieval.dense import DenseRetriever


def chunks():
    return [Chunk('D-C1', 'D', 'rule', 'regulation', 'test', None, 'annual report')]


def test_query_prompt_does_not_change_document_input(monkeypatch):
    calls = []

    class Model:
        max_seq_length = 32768
        device = 'cpu'

        def __init__(self, *args, **kwargs):
            pass

        def parameters(self):
            return iter([types.SimpleNamespace(dtype='float32')])

        def encode(self, texts, **kwargs):
            calls.append((texts, kwargs))
            return np.ones((len(texts), 1024), dtype=np.float32) / 32

    monkeypatch.setitem(sys.modules, 'sentence_transformers',
                        types.SimpleNamespace(SentenceTransformer=Model))
    prompt = 'Instruct: retrieve evidence\nQuery:'
    dense = DenseRetriever(chunks(), backend='qwen', batch_size=1,
                           query_prompt=prompt, max_seq_length=8192)
    dense.search('disclosure deadline')
    assert calls[0][0] == ['annual report']
    assert calls[0][1]['prompt'] == ''
    assert calls[1][0] == ['disclosure deadline']
    assert calls[1][1]['prompt'] == prompt
    assert all(call[1]['batch_size'] == 1 for call in calls)
    assert dense.encoding_metadata['max_seq_length'] == 8192


@pytest.mark.parametrize('options', [{'batch_size': 0}, {'max_seq_length': 0}])
def test_invalid_encoding_limits_fail_before_loading(options):
    with pytest.raises(ValueError):
        DenseRetriever(chunks(), backend='qwen', **options)
