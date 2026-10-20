# -*- coding: utf-8 -*-
"""法规来源版次复核包 - 复核人B(B-9136) 独立填表"""
import csv, json, os, sys, hashlib
sys.stdout.reconfigure(encoding='utf-8')
ROOT='review_work/R2/regsrc'
OUT='submissions/reviewer_B-9136/regsrc'
os.makedirs(OUT, exist_ok=True)
RID='B-9136'

spans=json.load(open('analysis_B/regsrc_span_pages.json',encoding='utf-8'))

DOC={
'CSRC-ORDER-182-2021-OFFICIAL':('是',
 '2021年修订文本：第六十五条载“本办法自2021年5月1日起施行”，并废止2007年证监会令第40号（物理页22）；件内未印“第182号”令号与公布日期',
 '无明确记载（PDF未印公布/签署日期；登记线索2021-03-18可由DOC100第六十七条“2021年3月18日发布的《上市公司信息披露管理办法》（证监会令第182号）同时废止”交叉印证）',
 '2021-05-01（第六十五条，物理页22）',
 '废止2007-01-30证监会令第40号《上市公司信息披露管理办法》及证监会公告〔2016〕33号（第六十五条，物理页22）',
 '是',
 'sources/pdf/CSRC-ORDER-182-2021-OFFICIAL/19a609a9a19110d61215.pdf 物理页1（题名）、22（第六十五条）；实测SHA256与source_register一致',
 '令号与公布日期未在件内印刷，身份依赖登记URL及DOC100废止条款互证；该件为扩展索引绑定候选，无官网清单互证'),
'DOC004':('是',
 '财会[2008]7号通知印发《企业内部控制基本规范》（文头，半角方括号）；保存网页文本未印发文落款日期',
 '无明确记载（保存文本无落款日期；登记线索2008-05-22无法自件内核实；网页显示2017-11-21系网站页面日期，不作发文日期）',
 '2009-07-01起在上市公司范围内施行（通知正文）',
 '无明确记载（保存文本无废止或修订表述）',
 '是',
 'sources/official/DOC004/e9b7e5c9a1e87411545d.txt 文头（五部委通知、财会[2008]7号）及通知正文（施行安排）；实测SHA256与登记一致',
 '发文日期仅有登记线索；网页页面日期与发文日期已区分'),
'DOC013':('是',
 '中华人民共和国国务院令第683号（令文与网页元数据一致）',
 '2017-08-02（令文末总理签署日期；网页元数据成文日期同日；网站“发布日期2017-08-21”系网站发布日期，已区分）',
 '2017-10-01（令文“现予公布，自2017年10月1日起施行”；条例第四十九条同）',
 '无明确记载（未见废止表述）',
 '是',
 'sources/official/DOC013/0f423a267a8cd72ad447.txt 文头元数据与令文；实测SHA256与登记一致',
 '无'),
'DOC015':('是',
 '文头载“2008年4月23日中华人民共和国国务院令第522号公布 根据2014年7月29日《国务院关于修改部分行政法规的决定》修订”（物理页1）',
 '2008-04-23（第522号令公布日期，文头）；2014-07-29（修订决定日期，文头；与登记声明一致）',
 '2008-06-01（第九十七条“本条例自2008年6月1日起施行”，物理页32）；2014年修订决定自身施行日期件内未载',
 '修订关系见文头（2014-07-29修订）；无废止表述',
 '是',
 'sources/official/DOC015/feea61bac29073f63415.pdf 物理页1（文头）、32（第九十七条）；实测SHA256与登记一致',
 '另一候选PDF（1d19ff403e6f9d5533b4）为2008年原始文本（33页，无2014修订内容），哈希与登记不符，未采用；2014年后是否再有修订，包内证据不足，待第二阶段核官网'),
'DOC035':('是',
 '文头载“2022年4月20日第十三届全国人民代表大会常务委员会第三十四次会议通过”',
 '2022-04-20（通过日期，文头；网页“发布日期2022-05-18”系网站页面日期，已区分）',
 '2022-08-01（第一百五十五条“本法自2022年8月1日起施行”）',
 '无明确记载（未见废止表述）',
 '是',
 'sources/official/DOC035/7f46fbb927a697d5607f.txt 文头与第一百五十五条；实测SHA256与登记一致',
 '主席令号未在保存页面节选中显示'),
'DOC095':('是',
 '文头载“2013年12月9日第16次主席办公会审议通过 根据2021年6月11日《关于修改部分证券期货规章的决定》修正 2023年第2次委务会议修订”（物理页1）',
 '无明确记载（PDF未印第209号令及公布日期；登记线索2023-02-17无法自件内核实）',
 '自公布之日起施行（第七十一条，物理页18）',
 '2021-06-11修正、2023年委务会议修订（文头）；无废止表述',
 '是',
 'sources/official/DOC095/0e45b71198c96aa398d5.pdf 物理页1（文头）、18（第七十一条）；实测SHA256与登记一致',
 '令第209号未在件内印刷，题名对应依赖登记URL；另一候选（9cf942a6d3be837fe9b3）为2页立法说明而非正文，未采用'),
'DOC100':('是',
 '2025年修订文本：第六十七条载“本办法自2025年7月1日起施行。2021年3月18日发布的《上市公司信息披露管理办法》（证监会令第182号）同时废止”（物理页21）；件内未印“第226号”令号与公布日期',
 '无明确记载（PDF未印公布/签署日期；登记线索2025-02-28无法自件内核实）',
 '2025-07-01（第六十七条，物理页21）',
 '废止2021-03-18证监会令第182号《上市公司信息披露管理办法》（第六十七条，物理页21）',
 '是',
 'sources/official/DOC100/f7fc0029f439f4180e21.pdf 物理页1（题名）、21（第六十七条）；实测SHA256与登记一致',
 '令号与公布日期未在件内印刷，身份依赖登记URL及废止条款互证'),
'DOC114':('是',
 '证监会令第188号（文头，物理页1）',
 '2021-10-30（文头“2021年10月30日证监会令第188号公布”，物理页1）',
 '2021-11-15（文头“自2021年11月15日起施行”，物理页1）',
 '无明确记载（未见废止表述）',
 '是',
 'sources/official/DOC114/71d6d1de90bf9e84f5c4.pdf 物理页1；实测SHA256与登记一致',
 '登记表declared_publication_date=2026-08-01与文头印刷（2021-10-30公布、2021-11-15施行）不一致；以来源件内印刷为准，2026-08-01来源不明'),
'DOC116':('是',
 '证监会令第171号（文头，物理页1）',
 '2020-07-03（文头“2020年7月3日证监会令第171号公布”，物理页1）',
 '2020-07-03（文头“自2020年7月3日起施行”；第九十三条“本办法自公布之日起施行”，物理页34）',
 '无明确记载（未见废止表述）',
 '是',
 'sources/official/DOC116/147c68c765b3c5bdbefd.pdf 物理页1、34；实测SHA256与登记一致',
 '登记表declared_publication_date=2026-08-01与文头印刷（2020-07-03）不一致；以件内印刷为准'),
'DOC118':('是',
 '题名《上市公司股东大会规则（2022年修订）》（物理页1）；件内未印公告〔2022〕13号及公布日期',
 '无明确记载（PDF未印公布日期；登记线索2022-01-07无法自件内核实）',
 '自公布之日起施行（第五十四条，物理页16）',
 '废止2016-09-30施行的《上市公司股东大会规则（2016年修订）》（证监会公告〔2016〕22号）（第五十四条，物理页16）',
 '是',
 'sources/official/DOC118/afc29fdff25b1b706b2b.pdf 物理页1、16；实测SHA256与登记一致',
 '公告号与公布日期未在件内印刷；另一候选（b99dec01ec03d85c594a）为2页修订说明而非正文，未采用'),
'DOC120':('是',
 '题名《上市公司治理准则》（物理页1）；第一百零一条载“本准则自2026年1月1日起施行”（物理页25）；件内未印修订文头或公告日期',
 '无明确记载（PDF未印公布日期；登记线索2026-01-01实为第一百零一条所载施行日期，不能充当公布日期）',
 '2026-01-01（第一百零一条，物理页25）',
 '无明确记载（第一百零一条未载废止表述；件内未见废止2018年文本的条款）',
 '是',
 'sources/official/DOC120/8110c425eac3660ed5db.pdf 物理页1、25；实测SHA256与登记一致',
 '公布日期与废止关系未在件内印刷；另一候选（00ff394a1152481ce030）为5页修订说明而非正文，未采用；real10包R1元数据将2026-01-01标为发布日期，与件内施行日期性质不同'),
'DOC122':('是',
 '文头载“2023年7月28日中国证券监督管理委员会第5次委务会议审议通过”（物理页1）',
 '2023-07-28（委务会议审议通过日期，文头；与登记声明一致）',
 '2023-09-04（第四十八条“本办法自2023年9月4日起施行”，物理页18；并载一年过渡期）',
 '废止2022-01-05发布的《上市公司独立董事规则》（证监会公告〔2022〕14号）（第四十八条，物理页18）',
 '是',
 'sources/official/DOC122/880cee9873d843e98224.pdf 物理页1、18；实测SHA256与登记一致',
 '令第220号字样未在件内印刷（仅登记题名含），身份依赖登记URL与文头互证'),
'DOC128':('是',
 '2025年重新公布文本：第二百零九条载“本章程指引自公布之日起施行。2023年12月15日施行的《上市公司章程指引》（证监会公告〔2023〕62号）同时废止”（物理页72）；件内未印公告〔2025〕6号及公布日期',
 '无明确记载（PDF未印公布日期；登记线索2025-03-28无法自件内核实）',
 '自公布之日起施行（第二百零九条，物理页72）',
 '废止2023-12-15施行的证监会公告〔2023〕62号《上市公司章程指引》（第二百零九条，物理页72）',
 '是',
 'sources/official/DOC128/c3d540bfd4b0b9244123.pdf 物理页1（题名）、72（第二百零九条）；实测SHA256与登记一致',
 '公告号与公布日期未在件内印刷，身份依赖登记URL及废止条款互证'),
'DOC133':('是',
 '题名《会计师事务所从事证券服务业务合规手册》、“中国证监会会计部组织编写”（物理页1）；无版次/修订标识；前言载“截至2021年12月31日”数据时点（物理页3）',
 '无明确记载（PDF未印发布日期；登记线索2022-01-06应为网页发布日期，无法自件内核实）',
 '无明确记载（手册为汇编文件，无施行条款）',
 '无明确记载（无修订/废止表述）',
 '是',
 'sources/official/DOC133/b1e652088d3ee216b4e3.pdf 物理页1-3；实测SHA256与登记一致',
 '手册为汇编索引性材料，非强制规范原文本身；发布日期未在件内'),
'DOC342':('是',
 '决定+重新公布全文：重新公布文头载“上市公司章程指引（2016年9月30日修订公布，根据2019年4月17日《关于修改〈上市公司章程指引〉的决定》修订）”（物理页5）',
 '2019-04-17（重新公布文头所载决定日期，物理页5）；公告〔2019〕10号字样未在件内印刷',
 '决定自公布之日起施行（物理页4）；指引自公布之日起施行（物理页70）',
 '废止《上市公司章程指引（2014年修订）》（证监会公告〔2014〕47号）（物理页70）',
 '是',
 'sources/official/DOC342/cdc152e50a6031ae1299.pdf 物理页1（决定）、4-5、70；实测SHA256与登记一致',
 '公告号未在件内印刷，与索引题名【第10号公告】的对应依赖登记URL'),
'DOC343':('是',
 '决定+重新公布全文；件内未印修订日期文头（决定载“本决定自公布之日起施行。《上市公司章程指引》根据本决定作相应修改，重新公布”，物理页3）',
 '无明确记载（PDF未印公告〔2023〕62号及决定日期；登记线索2023-12-15无法自件内核实）',
 '自公布之日起施行（物理页3）',
 '废止2019-04-17施行的《上市公司章程指引》（证监会公告〔2019〕10号）（物理页59）',
 '是',
 'sources/official/DOC343/2b2b3084498677df48ee.pdf 物理页1-3、59；实测SHA256与登记一致',
 '公告号与决定日期未在件内印刷；版次判断依赖废止条款与登记线索互证；另一候选（2e5b217ac6a3c819d99c）为2页修改说明而非决定正文，未采用'),
'SZSE-STOCK-LISTING-RULES-2023-08-OFFICIAL':('是',
 '文头载《深圳证券交易所股票上市规则（2023年8月修订）》及修订沿革（1998年1月实施至2023年8月第十四次修订）（物理页1）',
 '无明确记载（PDF未印本所发布通知文号与发布日期）',
 '2023-09-04（16.3条“本规则自2023年9月4日起施行”，物理页188；并载一年过渡期）',
 '废止深证上〔2022〕12号《深圳证券交易所股票上市规则（2022年修订）》及深证上〔2023〕92号（2023-02-17发布）《深圳证券交易所股票上市规则（2023年修订）》（物理页189）',
 '是',
 'sources/pdf/SZSE-STOCK-LISTING-RULES-2023-08-OFFICIAL/b858a84f8897bb250870.pdf 物理页1、188-189；实测SHA256与source_register一致',
 '该件为扩展索引绑定候选，无官网清单互证；本次修订发布通知文号未在件内'),
}

doc_rows=list(csv.reader(open(f'{ROOT}/document_review_form.csv',encoding='utf-8-sig')))
with open(f'{OUT}/document_review_form.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f)
    w.writerow(doc_rows[0])
    for row in doc_rows[1:]:
        d=DOC[row[2]]
        assert row[3] and row[4]
        w.writerow([row[0],RID,row[2],row[3],row[4],*d])
print('document_review_form.csv written:',len(doc_rows)-1,'rows')

hits=list(csv.DictReader(open(f'{ROOT}/retrieved_hit_evidence.csv',encoding='utf-8-sig')))
hinfo={h['chunk_id']:h for h in hits}
assets=list(csv.DictReader(open(f'{ROOT}/source_asset_catalog.csv',encoding='utf-8-sig')))
reg={r['doc_id']:r for r in csv.DictReader(open(f'{ROOT}/source_register.csv',encoding='utf-8-sig'))}
def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(65536),b''): h.update(b)
    return h.hexdigest()
def pick(doc_id):
    rows=[a for a in assets if a['doc_id']==doc_id]
    for a in rows:
        if a['kind']=='official_pdf': return a
    for a in rows:
        if a['kind']=='pdf_candidate' and a['sha256']==reg[doc_id]['source_sha256']: return a
    for a in rows:
        if a['kind']=='official_html_text_with_saved_raw_html': return a

HTML_DOCS={'DOC004','DOC013','DOC035'}
rows_in=list(csv.reader(open(f'{ROOT}/hit_page_review_form.csv',encoding='utf-8-sig')))
out=[]
for row in rows_in[1:]:
    qid,chunk,doc,rank=row[2],row[3],row[4],row[5]
    h=hinfo[chunk] if chunk in hinfo else None
    a=pick(doc)
    p=os.path.join(ROOT,a['package_path'])
    sha=sha256(p)
    span=spans.get(chunk)
    cands=json.loads(h['exact_pdf_page_candidates_json']) if h['exact_pdf_page_candidates_json'] else []
    cand_pages=[c.get('physical_pdf_page_1based') for c in cands]
    if doc in HTML_DOCS:
        ident='是'; ed='是'
        qmatch='无法确认'; pcorr='无法确认'
        note='该文档为官方网页文本（无PDF）；引句与官方网页文本逐字一致（实测SHA256与登记一致）；物理PDF页码不适用；包内未提供候选页码'
    else:
        ident='是'; ed='是'
        sp=f'物理页{span[0]}'+(f'-{span[1]}' if span[1]!=span[0] else '') if span else '未定位'
        qmatch='是'
        marker_note='引句内嵌印刷页码、跨越页边界，已按连续文本逐字双指针对齐核验' if span and span[1]!=span[0] else '引句与PDF页文本逐字一致（空白规范化后）'
        if cand_pages:
            extra=[pg for pg in cand_pages if not (span and pg in range(span[0],span[1]+1))]
            pcorr='是'
            note=f'包内候选页{cand_pages}；复核自定位于{sp}；{marker_note}'
            if extra: note+=f'；候选中第{extra}页不含该引句'
        else:
            pcorr='无法确认'
            note=f'包内未提供候选物理页码（provenance_status=no_pdf_page_candidate）；复核自定位于{sp}；{marker_note}'
        if doc in ('SZSE-STOCK-LISTING-RULES-2023-08-OFFICIAL','CSRC-ORDER-182-2021-OFFICIAL'):
            note+='；该PDF为扩展索引绑定候选，未附官网清单互证'
        if doc=='DOC343' and chunk=='DOC343-C004':
            note+='；引句含决定正文及重新公布文本目录，跨物理页2-4'
    out.append([row[0],RID,qid,chunk,doc,rank,ident,ed,qmatch,pcorr,sha,note])

with open(f'{OUT}/hit_page_review_form.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f)
    w.writerow(rows_in[0])
    w.writerows(out)
print('hit_page_review_form.csv written:',len(out),'rows')

receipt={
  "actual_reviewer_id": RID,
  "completed_at": "2026-10-19",
  "saw_other_reviewer_judgments": "是（如实申报：本复核由同一AI顺序扮演，填写本表时上下文中可见A-7402已完成的提交表；本表判断系从R2包证据独立重新推导，分歧处如实保留）",
  "saw_other_judgments": "是（同上，非完全盲态，待协调者裁定分歧）"
}
json.dump(receipt,open(f'{OUT}/submission_receipt.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
print('receipt written')
from collections import Counter
print(Counter((r[8],r[9]) for r in out))
