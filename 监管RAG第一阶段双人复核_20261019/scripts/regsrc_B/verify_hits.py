# -*- coding: utf-8 -*-
"""法规来源版次复核包 - 复核人B(B-9136) 独立核验：引句、SHA256、物理页定位（含跨页双指针对齐）"""
import csv, json, os, re, sys, hashlib
sys.stdout.reconfigure(encoding='utf-8')
from pypdf import PdfReader

ROOT='review_work/R2/regsrc'
os.makedirs('analysis_B',exist_ok=True)
def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(65536),b''): h.update(b)
    return h.hexdigest()
def norm(s): return re.sub(r'\s+','',s or '')

assets=list(csv.DictReader(open(f'{ROOT}/source_asset_catalog.csv',encoding='utf-8-sig')))
reg={r['doc_id']:r for r in csv.DictReader(open(f'{ROOT}/source_register.csv',encoding='utf-8-sig'))}

def pick(doc_id):
    rows=[a for a in assets if a['doc_id']==doc_id]
    for a in rows:
        if a['kind']=='official_pdf': return a
    for a in rows:
        if a['kind']=='pdf_candidate' and a['sha256']==reg[doc_id]['source_sha256']: return a
    for a in rows:
        if a['kind']=='official_html_text_with_saved_raw_html': return a
    return None

cache={}
def pages_of(path):
    if path not in cache:
        cache[path]=[norm(p.extract_text()) for p in PdfReader(path).pages]
    return cache[path]

def two_pointer_span(pages, q):
    """锚点定位起始页后双指针对齐：文本侧允许跳过刊头（≤80字），引句侧仅允许跳过数字/短横类内嵌页码（≤12字）。"""
    n=len(pages)
    anchors=[q[k:k+18] for k in (0,2,4,6)]
    MARK=set('—-－–0123456789 ')
    for i in range(n):
        start=None
        for anc in anchors:
            pos=pages[i].find(anc)
            if pos>=0: start=pos; break
        if start is None: continue
        # 拼接页 i..i+7，记录每页起始偏移
        offs=[]; acc=''
        for j in range(i,min(n,i+8)):
            offs.append(len(acc)); acc+=pages[j]
        qi=0; ti=start; skip_t=0; skip_q=0
        while qi<len(q) and ti<len(acc):
            if q[qi]==acc[ti]:
                qi+=1; ti+=1; skip_t=0; skip_q=0
            elif q[qi] in MARK and skip_q<12:
                qi+=1; skip_q+=1
            else:
                ti+=1; skip_t+=1
                if skip_t>80: break
        if qi==len(q):
            end=i+1
            for k,off in enumerate(offs):
                if off<=ti-1: end=i+1+k
            return [i+1,end]
    return None

hits=list(csv.DictReader(open(f'{ROOT}/retrieved_hit_evidence.csv',encoding='utf-8-sig')))
results=[]; spans={}
for h in hits:
    doc=h['doc_id']; chunk=h['chunk_id']; quote=h['retrieved_chunk_text']
    a=pick(doc)
    cands=json.loads(h['exact_pdf_page_candidates_json']) if h['exact_pdf_page_candidates_json'] else []
    res={'query_id':h['query_id'],'chunk_id':chunk,'doc_id':doc,'rank':h['rank']}
    idx_path=f'{ROOT}/sources/indexed_text/{doc}.txt'
    if os.path.exists(idx_path):
        idx=norm(open(idx_path,encoding='utf-8').read())
        res['quote_in_indexed_text']= norm(quote) in idx
    else:
        res['quote_in_indexed_text']=None
    if a:
        p=os.path.join(ROOT,a['package_path'])
        res['file']=a['package_path']
        res['file_sha_actual']=sha256(p)
        res['sha_matches_catalog']= res['file_sha_actual']==a['sha256']
        res['sha_matches_register']= res['file_sha_actual']==reg[doc]['source_sha256'] if reg[doc]['source_sha256'] else None
        if p.lower().endswith('.pdf'):
            pages=pages_of(p)
            res['pdf_pages']=len(pages)
            pc=[]
            for c in cands:
                pg=c.get('physical_pdf_page_1based')
                t=pages[pg-1] if 1<=pg<=len(pages) else None
                pc.append({'page':pg,'contains': (norm(quote) in t) if t else False,
                           'sha_match': c.get('pdf_sha256')==res['file_sha_actual']})
            res['candidates']=pc
            qn=norm(quote)
            found=[i+1 for i,t in enumerate(pages) if qn in t]
            if found:
                res['quote_found_pages']=found[:5]; spans[chunk]=[found[0],found[0]]
            else:
                sp=two_pointer_span(pages,qn)
                res['quote_span']=sp
                if sp: spans[chunk]=sp
        else:
            txt=norm(open(p,encoding='utf-8').read())
            res['quote_in_official_txt']= norm(quote) in txt
            res['candidates']=[{'page':c.get('physical_pdf_page_1based')} for c in cands]
    else:
        res['file']=None
    results.append(res)

json.dump(results,open('analysis_B/regsrc_hits.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
json.dump(spans,open('analysis_B/regsrc_span_pages.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print('hits:',len(results),'| spans:',len(spans))
bad=[r for r in results if r.get('quote_in_indexed_text') is False]
print('quote NOT in indexed text:',[r['chunk_id'] for r in bad])
nopage=[r for r in results if r['file'] and str(r['file']).lower().endswith('.pdf') and r['chunk_id'] not in spans]
print('PDF hits without located page:',[r['chunk_id'] for r in nopage])
shabad=[r for r in results if r.get('sha_matches_catalog') is False]
print('sha mismatch:',[r['chunk_id'] for r in shabad])
for r in results:
    cand_miss = r.get('candidates') and not any(c.get('contains') for c in r['candidates'])
    print(r['chunk_id'],'| idx:',r.get('quote_in_indexed_text'),'| cand:',[(c.get('page'),c.get('contains')) for c in r.get('candidates',[])],'| span:',spans.get(r['chunk_id']),'| CAND_MISS' if cand_miss else '')
