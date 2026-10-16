"""Bounded real 0.6B interface check, not a regulatory quality benchmark."""
import argparse
import gc
import hashlib
import importlib.metadata
import json
import resource
import sys
import time
import weakref
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run(out, embedding_revision=None, reranker_revision=None):
    out.mkdir(parents=True,exist_ok=False)
    report={'status':'started','quality_benchmark':False,'real_weights_loaded':False,
            'scope':'2 synthetic interface documents / 2 queries', 'device':'cpu'}
    started=time.perf_counter()
    try:
        import torch
        import numpy as np
        from src.retrieval.dense import DenseRetriever
        from src.retrieval.reranker import Reranker
        from src.retrieval.model_runtime import SequentialModelRuntime
        from src.data.clause_splitter import Chunk
        torch.set_num_threads(2)
        runtime=SequentialModelRuntime()
        samples=['The capital of China is Beijing.', 'Gravity attracts objects with mass toward one another.']
        queries=['What is the capital of China?', 'What does gravity do?']
        docs=[Chunk(f'FIXTURE-{i}','FIXTURE','Synthetic interface fixture','regulation','synthetic',None,t)
              for i,t in enumerate(samples)]
        prompt='Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:'
        dense=DenseRetriever(docs,backend='qwen',model_name='Qwen/Qwen3-Embedding-0.6B',
                             device='cpu',batch_size=1,query_prompt=prompt,max_seq_length=256,
                             model_runtime=runtime,revision=embedding_revision)
        report['real_weights_loaded']=True
        doc_vectors=dense._matrix.copy()
        q_vectors=dense.encode_queries(queries)
        assert doc_vectors.shape==q_vectors.shape==(2,1024)
        assert np.isfinite(q_vectors).all() and np.isfinite(doc_vectors).all()
        assert np.allclose(np.linalg.norm(q_vectors,axis=1),1,atol=1e-4)
        old_embedding=weakref.ref(dense._model)
        rr=Reranker(device='cpu',max_length=256,batch_size=1,model_runtime=runtime,revision=reranker_revision)
        actual=rr.score(queries[0],docs)
        assert dense._model is None and old_embedding() is None
        assert len(actual)==2 and all(0<=x<=1 for x in actual)
        # Independent direct forward following the official Transformers reference;
        # uses torch binary log_softmax, whereas the wrapper uses NumPy logaddexp.
        tok, model=rr._tok,rr._model
        prefix='<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
        suffix='<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
        p=tok.encode(prefix,add_special_tokens=False); s=tok.encode(suffix,add_special_tokens=False)
        reference=[]
        for document in samples:
            text=f'<Instruct>: {rr.instruction}\n<Query>: {queries[0]}\n<Document>: {document}'
            tokens=tok([text],padding=False,truncation='longest_first',return_attention_mask=False,
                       max_length=256-len(p)-len(s))
            tokens['input_ids']=[p+ids+s for ids in tokens['input_ids']]
            inputs=tok.pad(tokens,padding=True,return_tensors='pt',max_length=256)
            with torch.inference_mode():
                logits=model(**inputs,logits_to_keep=1,use_cache=False).logits[:,-1,:]
                pair=logits[:,[tok.convert_tokens_to_ids('no'),tok.convert_tokens_to_ids('yes')]].float()
                reference.extend(torch.log_softmax(pair,dim=1)[:,1].exp().tolist())
        assert np.allclose(actual,reference,atol=1e-6,rtol=1e-5)
        old_reranker=weakref.ref(model)
        del model,tok,logits,pair,inputs,tokens
        # Changing the prompt forces a cache miss and a genuine embedding reload.
        dense.query_prompt=''
        plain=dense.encode_queries([queries[0]])
        assert old_reranker() is None and rr._model is None
        assert np.linalg.norm(plain[0]-q_vectors[0])>1e-4
        rerank_second=rr.score(queries[1],docs)
        assert dense._model is None
        metadata={'embedding':dict(dense.encoding_metadata),'reranker':dict(rr.encoding_metadata)}
        runtime.release()
        assert rr._model is None and runtime.owner is None
        for name,array in [('document_vectors',doc_vectors),('query_vectors',q_vectors),('plain_query_vector',plain)]:
            np.save(out/(name+'.npy'),array,allow_pickle=False)
        report.update(status='passed',reference_scores=reference,wrapper_scores=actual,
                      second_query_scores=rerank_second,documents=samples,queries=queries,
                      model_metadata=metadata,lifecycle=runtime.events,
                      both_weight_owners_released=True,reference_probability_agreement=True)
    except Exception as error:
        report.update(status='failed',error=f'{type(error).__name__}: {error}')
    report.update(elapsed_seconds=time.perf_counter()-started,
                  process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  packages={p:importlib.metadata.version(p) for p in ['torch','transformers','sentence-transformers','numpy']},
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  artifacts_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())})
    (out/'run.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir',required=True,type=Path)
    p.add_argument('--embedding-revision')
    p.add_argument('--reranker-revision')
    args=p.parse_args()
    sys.exit(run(args.out_dir,args.embedding_revision,args.reranker_revision))
