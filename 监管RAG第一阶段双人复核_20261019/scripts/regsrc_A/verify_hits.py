# -*- coding: utf-8 -*-
"""法规来源版次复核包 - 复核人A 证据核验：逐命中验证引句与物理页"""
import csv, json, os, re, sys, hashlib
sys.stdout.reconfigure(encoding='utf-8')
from pypdf import PdfReader

ROOT='review_work/R1/regsrc'
def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(65536),b''): h.update(b)
    return h.hexdigest()
def norm(s): return re.sub(r'\s+','',s or '')

# 资产目录
assets=list(csv.DictReader(open(f'{ROOT}/source_asset_catalog.csv',encoding='utf-8-sig')))
reg={r['doc_id']:r for r in csv.DictReader(open(f'{ROOT}/source_register.csv',encoding='utf-8-sig'))}

# 每文档选定复核文件：优先 official_pdf；否则 pdf_candidate 且 sha==register.source_sha256；否则 official txt
def pick(doc_id):
    rows=[a for a in assets if a['doc_id']==doc_id]
    for a in rows:
        if a['kind']=='official_pdf': return a
    for a in rows:
        if a['kind']=='pdf_candidate' and a['sha256']==reg[doc_id]['source_sha256']: return a
    for a in rows:
        if a['kind']=='official_html_text_with_saved_raw_html': return a
    return None

# 预载 PDF 页文本缓存
cache={}
def page_text(path, page1):
    if path not in cache:
        rd=PdfReader(path)
        cache[path]=[norm(p.extract_text()) for p in rd.pages]
    pages=cache[path]
    return pages[page1-1] if 1<=page1<=len(pages) else None

hits=list(csv.DictReader(open(f'{ROOT}/retrieved_hit_evidence.csv',encoding='utf-8-sig')))
results=[]
for h in hits:
    doc=h['doc_id']; chunk=h['chunk_id']; quote=h['retrieved_chunk_text']
    a=pick(doc)
    cands=json.loads(h['exact_pdf_page_candidates_json']) if h['exact_pdf_page_candidates_json'] else []
    res={'query_id':h['query_id'],'chunk_id':chunk,'doc_id':doc,'rank':h['rank']}
    # 1) 索引快照含该引句？
    idx_path=f'{ROOT}/sources/indexed_text/{doc}.txt'
    if os.path.exists(idx_path):
        idx=norm(open(idx_path,encoding='utf-8').read())
        res['quote_in_indexed_text']= norm(quote) in idx
    else:
        res['quote_in_indexed_text']=None
    # 2) 复核文件 sha
    if a:
        p=os.path.join(ROOT,a['package_path'])
        res['file']=a['package_path']
        res['file_sha_actual']=sha256(p)
        res['sha_matches_catalog']= res['file_sha_actual']==a['sha256']
        res['sha_matches_register']= res['file_sha_actual']==reg[doc]['source_sha256'] if reg[doc]['source_sha256'] else None
        if p.lower().endswith('.pdf'):
            res['pdf_pages']=len(cache.get(p) or PdfReader(p).pages)
            if p not in cache: cache[p]=[norm(pg.extract_text()) for pg in PdfReader(p).pages]
            # 3) 候选页含引句？
            pc=[]
            for c in cands:
                pg=c.get('physical_pdf_page_1based')
                t=page_text(p,pg)
                pc.append({'page':pg,'sha':c.get('pdf_sha256'),'contains': (norm(quote) in t) if t else False,
                           'sha_match': c.get('pdf_sha256')==res['file_sha_actual']})
            res['candidates']=pc
            # 4) 全文中找引句所在页
            found=[i+1 for i,t in enumerate(cache[p]) if norm(quote) in t]
            res['quote_found_pages']=found[:5]
        else:
            txt=norm(open(p,encoding='utf-8').read())
            res['quote_in_official_txt']= norm(quote) in txt
            res['candidates']=[{'page':c.get('physical_pdf_page_1based'),'sha':c.get('pdf_sha256')} for c in cands]
    else:
        res['file']=None
    results.append(res)

json.dump(results,open('analysis_A/regsrc_hits.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
# 汇总
bad=[r for r in results if r.get('quote_in_indexed_text') is False]
print('quote NOT in indexed text:',[(r['chunk_id']) for r in bad])
for r in results:
    flag=''
    if r.get('candidates'):
        ok=[c for c in r['candidates'] if c.get('contains')]
        if not ok: flag='CANDIDATE_PAGE_MISS'
    elif r.get('quote_in_official_txt') is False: flag='TXT_MISS'
    elif not r.get('candidates') and r.get('quote_found_pages')==[]: flag='NOT_IN_PDF'
    print(r['query_id'],r['chunk_id'],'rank',r['rank'],'| idx:',r.get('quote_in_indexed_text'),'| cand:',[(c.get('page'),c.get('contains')) for c in r.get('candidates',[])],'| found:',r.get('quote_found_pages'),'| sha_ok:',r.get('sha_matches_catalog'),flag)
