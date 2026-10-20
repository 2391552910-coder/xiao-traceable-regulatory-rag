# -*- coding: utf-8 -*-
import csv, os, sys
sys.stdout.reconfigure(encoding='utf-8')

RID = 'A-7402'
DATE = '2026-10-19'
BLIND = '自报盲态：独立填写；提交前未查看另一复核人表格或判断；未使用包外材料'

def fill(pkg, rows_fill, outdir):
    src = f'review_work/R1/{pkg}/review_form.csv'
    with open(src, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    header = rows[0]
    for i, rf in enumerate(rows_fill, start=1):
        assert rows[i][1] == rf['unit_type'] and rows[i][2] == rf['unit_id'], (pkg, i, rows[i][:3])
        for k, v in rf.items():
            if k in ('unit_type', 'unit_id'):
                continue
            j = header.index(k)
            assert rows[i][j] == '', f'cell not blank: {pkg} row{i} {k}'
            rows[i][j] = v
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, 'review_form.csv')
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        csv.writer(f, lineterminator='\n').writerows(rows)
    print('written', out)

base = dict(actual_reviewer_id=RID, blind_status=BLIND, reviewed_at=DATE)

# ============ 002264 ============
fill('002264', [
 dict(unit_type='question', unit_id='CASE-01', **base,
  source_identity_correct='yes', quote_and_location_correct='u', evidence_role_correct='u',
  target_quote_scope_correct='u', relevance_grade='u', answerability='answerable',
  source_version_identity='n/a（问题单元）', publication_date='', effective_from='', effective_to_exclusive='',
  event_date_status='unknown', event_date='', temporal_applicability='unknown',
  reason='问题元数据（新华都科技股份有限公司、002264.SZ、2024年报）与包内年报核对一致：封面载公司名与"2024年年度报告"，第二节（物理页6）载"股票代码002264"。问题限定两问——年报如何记载〔2023〕1号警示函、182号令第三条第一款及第四条原文——均可由包内年报PDF与官网快照完整作答。',
  uncertainty_reason='问题单元无引句可核，位置/角色/范围旗标及相关性填u；底层违规行为日期未在输入中披露，事件日期与时点适用性保持unknown。'),
 dict(unit_type='annual_evidence_candidate', unit_id='ANN-P42-CANDIDATE', **base,
  source_identity_correct='yes', quote_and_location_correct='yes', evidence_role_correct='yes',
  target_quote_scope_correct='yes', relevance_grade='2', answerability='answerable',
  source_version_identity='新华都科技股份有限公司2024年年度报告全文（封面：2025年03月）',
  publication_date='2025-03（封面记载到月，具体披露日PDF内未载）', effective_from='', effective_to_exclusive='',
  event_date_status='unknown', event_date='', temporal_applicability='unknown',
  reason='年报PDF物理页42（印刷页41）载候选引句全文：本人用pypdf独立提取该页文本，与包内annual_page_0042.txt[156:468)切片及线索CSV exact_quote逐字一致，引句SHA256（49ce8688…）与记录相符；PNG视觉复核一致。引句完整覆盖警示函记载要件：决定名称与〔2023〕1号文号、事由（财务报告信息披露不准确）、违反条款（第182号令第三条第一款、第四条）、对象（公司、倪国涛、陈文杰、张石保）、警示函措施、记入诚信档案及公告2023-001指引。',
  uncertainty_reason='candidate_annual_quote.txt与CSV exact_quote存在细微空白差异（两者SHA256不同，去空白后一致）；引句仅载收件日2023-01-13与公告日2023-01-14，底层违规行为日期未披露，事件日期/时点适用性保持unknown。'),
 dict(unit_type='regulation_evidence_candidate', unit_id='LAW-182-ARTICLE-3-P1', **base,
  source_identity_correct='yes', quote_and_location_correct='yes', evidence_role_correct='yes',
  target_quote_scope_correct='yes', relevance_grade='2', answerability='answerable',
  source_version_identity='《上市公司信息披露管理办法》（2007-01-30证监会令第40号公布；2021-03-18证监会令第182号修订）',
  publication_date='2007-01-30公布；2021-03-18修订公布', effective_from='2021-05-01', effective_to_exclusive='无法确认：快照未载废止信息',
  event_date_status='', event_date='', temporal_applicability='unknown',
  reason='官网快照可见文本order_182_visible_text.txt[326:394)与候选引句逐字一致，上下文确为第三条第一款全文。版本头"（2007年1月30日证监会令第40号公布 2021年3月18日证监会令第182号修订）"与第六十五条"本办法自2021年5月1日起施行"均在快照内核实。HTML快照无PDF物理页，位置以文本偏移核验。',
  uncertainty_reason='线索CSV的page_text_sha256（daa09831…）与包内visible_text实测SHA256（28bbc9…）不一致，但偏移内容核验通过；复核表unit_id（LAW-182-ARTICLE-3-P1）与线索CSV写法（LAW-182-第三条第一款）不同，判断为同一候选。底层事件日期未知，时点适用性保持unknown（2023-01决定作出时该版本现行有效）。'),
 dict(unit_type='regulation_evidence_candidate', unit_id='LAW-182-ARTICLE-4', **base,
  source_identity_correct='yes', quote_and_location_correct='yes', evidence_role_correct='yes',
  target_quote_scope_correct='yes', relevance_grade='2', answerability='answerable',
  source_version_identity='《上市公司信息披露管理办法》（2007-01-30证监会令第40号公布；2021-03-18证监会令第182号修订）',
  publication_date='2007-01-30公布；2021-03-18修订公布', effective_from='2021-05-01', effective_to_exclusive='无法确认：快照未载废止信息',
  event_date_status='', event_date='', temporal_applicability='unknown',
  reason='order_182_visible_text.txt[608:664)与候选引句逐字一致，上下文确为第四条全文（董事、监事、高级管理人员忠实勤勉义务）。版本与施行日期核验同上一法规单元。',
  uncertainty_reason='同上一法规单元：page_text_sha256与unit_id写法两点包装差异已记录；时点适用性保持unknown。'),
], 'submissions/reviewer_A-7402/002264')

# ============ 002169 ============
fill('002169', [
 dict(unit_type='question', unit_id='CASE-01', **base,
  source_identity_correct='yes', quote_and_location_correct='u', evidence_role_correct='u',
  target_quote_scope_correct='u', relevance_grade='u', answerability='answerable',
  source_version_identity='n/a（问题单元）', publication_date='', effective_from='', effective_to_exclusive='',
  event_date_status='unknown', event_date='', temporal_applicability='partial（两法规对2023年度业绩预告义务窗口均现行有效；迟披露确切日期未知）',
  reason='问题元数据（广州智光电气股份有限公司、002169.SZ、2024年报）与年报一致（物理页9第二节载"股票代码002169"）。问题三部分可按包内三份输入作答：①年报披露的警示事实（物理页57）；②深交所5.1.1条（会计年度结束之日起一个月内预告，列七项触发情形）与182号令第十七条（预计亏损或大幅变动应及时预告）的触发条件与时限原文；③"能否确定具体触发事实/单一行为日期/时点适用性"——答案为无法确定触发情形（属5.1.1哪一款未知）与单一行为日期，此限定结论本身即为问题要求的完整回答。',
  uncertainty_reason='年报未披露2023年业绩预告的实际披露日期、警示函文号与决定日期；触发情形（5.1.1哪一款）无证据。'),
 dict(unit_type='annual_evidence_candidate', unit_id='ANN-P57-CANDIDATE', **base,
  source_identity_correct='yes', quote_and_location_correct='yes', evidence_role_correct='yes',
  target_quote_scope_correct='yes', relevance_grade='2', answerability='answerable',
  source_version_identity='广州智光电气股份有限公司2024年年度报告全文',
  publication_date='无法确认：封面仅印"【披露时间】"占位符，未载日期', effective_from='', effective_to_exclusive='',
  event_date_status='unknown', event_date='', temporal_applicability='unknown',
  reason='年报PDF物理页57（印刷页57）载候选引句：pypdf独立提取文本与包内annual_report_physical_page_0057.txt[759:823)切片逐字一致，页文本与引句SHA256均与线索记录相符；PNG视觉复核一致。引句记载因2023年业绩预告晚于法规规定时间披露，公司及李永喜、吴文忠、熊坦被广东证监局出具警示函，同时被深交所通报批评处分。',
  uncertainty_reason='引句未载警示函文号、决定日期、实际预告披露日期及具体违规情形；年报封面披露日期为占位符，无法确认。'),
 dict(unit_type='regulation_evidence_candidate', unit_id='LAW-SZSE-5-1-1', **base,
  source_identity_correct='yes', quote_and_location_correct='yes', evidence_role_correct='yes',
  target_quote_scope_correct='yes', relevance_grade='2', answerability='answerable',
  source_version_identity='深圳证券交易所股票上市规则（2023年8月修订，第十四次修订）',
  publication_date='无明确记载（PDF为附件1正文，未印发布通知日期）', effective_from='2023-09-04（16.3条）', effective_to_exclusive='无法确认：PDF仅载废止2022年修订版与2023年2月修订版，未载本版废止',
  event_date_status='', event_date='', temporal_applicability='yes（对2023年度业绩预告义务窗口：规则自2023-09-04施行，预告法定期限于2024年1月末，窗口内本版现行有效）',
  reason='规则PDF物理页55（印刷页55，页眉"— 55 —"）载5.1.1条全文，pypdf独立提取与包内页文本[30:434)切片逐字一致，SHA256相符。封面载"深圳证券交易所股票上市规则（2023年8月修订）"及十四次修订沿革；16.3条载自2023年9月4日起施行并废止2022年1月及2023年2月旧版。',
  uncertainty_reason='发布日期PDF内无明确记载；迟披露行为确切日期未知，但义务时点适用性可由施行日推定。'),
 dict(unit_type='regulation_evidence_candidate', unit_id='LAW-CSRC-182-17', **base,
  source_identity_correct='yes', quote_and_location_correct='yes', evidence_role_correct='yes',
  target_quote_scope_correct='yes', relevance_grade='2', answerability='answerable',
  source_version_identity='上市公司信息披露管理办法（包内标识为证监会令第182号，2021年修订）',
  publication_date='无法确认：PDF为文字版正文，未印公布/修订日期与令号', effective_from='2021-05-01（第六十五条）', effective_to_exclusive='无法确认：未载废止',
  event_date_status='', event_date='', temporal_applicability='yes（2021-05-01施行，2023年度业绩预告义务窗口内现行有效）',
  reason='PDF物理页6（印刷页6）载"第十七条 上市公司预计经营业绩发生亏损或者发生大幅变动的，应当及时进行业绩预告。"与候选引句逐字一致（页文本[266:307)，SHA256相符）；pypdf独立提取一致。全文至第六十五条，载自2021年5月1日起施行并废止证监会令第40号旧办法及2016年季度报告编报规则。',
  uncertainty_reason='该PDF未印"证监会令第182号"及"2021年3月18日修订"版本头，令号与修订日期依据包文件名/包说明；内容版本（2021年修订）由条文结构（共65条）与第六十五条施行/废止条款佐证。'),
], 'submissions/reviewer_A-7402/002169')

# ============ 002008 ============
fill('002008', [
 dict(unit_type='question', unit_id='Q-002008-DEV-01', **base,
  source_identity_correct='yes', quote_and_location_correct='u', evidence_role_correct='u',
  target_quote_scope_correct='u', relevance_grade='u', answerability='answerable',
  source_version_identity='n/a（问题单元）', publication_date='', effective_from='', effective_to_exclusive='',
  event_date_status='unknown', event_date='', temporal_applicability='unknown',
  reason='问题元数据（大族激光科技产业集团股份有限公司、002008.SZ、2024年报）与年报封面（"股票代码：002008"）及物理页6公司信息一致。问题限定三问：年报对王磊其父短线交易警示的披露、证券法第四十四条主体范围/六个月条件/收益处理、可陈述与不可确认项——均可由两份输入完整作答；不可确认项的如实回答即为问题第三问的限定答案。',
  uncertainty_reason='底层短线交易的买入/卖出日期、六个月窗口满足与否、收益数额均无输入证据；事件日期与时点适用性保持unknown。'),
 dict(unit_type='annual_evidence_candidate', unit_id='ANN-002008-P043', **base,
  source_identity_correct='yes', quote_and_location_correct='yes', evidence_role_correct='yes',
  target_quote_scope_correct='yes', relevance_grade='2', answerability='answerable',
  source_version_identity='大族激光科技产业集团股份有限公司2024年年度报告',
  publication_date='无法确认：封面仅载"2024年"，未载披露月日', effective_from='', effective_to_exclusive='',
  event_date_status='unknown', event_date='', temporal_applicability='unknown',
  reason='年报PDF物理页43（印刷页43）载候选引句：包内annual_physical_page_43.txt[1370:1440)切片与引句逐字一致，pypdf独立提取一致，PNG视觉复核一致。引句记载2023年10月29日公司现任监事王磊因其父短线交易大族激光股票，被深圳证监局处以出具警示函（〔2023〕194号）的监管措施。',
  uncertainty_reason='年报仅载警示措施日期2023-10-29（该日期角色为监管措施日期，非底层交易日期）；底层交易日期、成交金额未披露。'),
 dict(unit_type='regulation_evidence_candidate', unit_id='LAW-SECURITIES-2019-ART44', **base,
  source_identity_correct='yes', quote_and_location_correct='yes', evidence_role_correct='yes',
  target_quote_scope_correct='yes', relevance_grade='2', answerability='answerable',
  source_version_identity='中华人民共和国证券法（2019年修订）',
  publication_date='2019-12-28（第十三届全国人大常委会第十五次会议修订通过并公布，主席签署页）', effective_from='2020-03-01（公布页及第二百二十六条）', effective_to_exclusive='无法确认：PDF内未载废止信息',
  event_date_status='', event_date='', temporal_applicability='unknown',
  reason='PDF封面载"中华人民共和国证券法（2019修订）"，扉页载2019年12月28日修订通过、现予公布、自2020年3月1日起施行（第二百二十六条同）。物理页10载第四十四条全文四款，候选引句去空白后与PDF文本层及包内law_physical_page_10.txt完全一致。引句范围完整：主体（5%以上股东、董监高）、六个月双向交易条件、收益归公司并由董事会收回、配偶父母子女及利用他人账户纳入、股东三十日要求与代位诉讼、负有责任董事连带责任。',
  uncertainty_reason='线索CSV偏移[199:610)与包内页文本实际匹配区间[196:607)存在3字符偏移、空白布局亦有差异，精确偏移量未复现（引句内容与物理页无误）。第四十四条要件对王磊父亲具体交易的适用（交易日期、窗口、账户）无输入证据，时点适用性保持unknown（该版本自2020-03-01施行，2023-10-29警示措施时点现行有效）。'),
 dict(unit_type='joint_answerability', unit_id='DUAL-SUFFICIENCY-002008-01', **base,
  source_identity_correct='u', quote_and_location_correct='u', evidence_role_correct='u',
  target_quote_scope_correct='u', relevance_grade='u', answerability='answerable',
  source_version_identity='n/a（联合可回答性单元）', publication_date='', effective_from='', effective_to_exclusive='',
  event_date_status='unknown', event_date='', temporal_applicability='unknown',
  reason='两份输入联合足以按问题限定完整作答：年报披露句（物理页43）与证券法第四十四条全文（物理页10）均可完整准确定位引用；可陈述事项=年报记载的警示事实+条文要件原文；无法确认事项=具体交易日期、六个月窗口满足、收益数额、账户细节。包说明已声明监管警示决定未放入包，故行为要件/法律适用保留待核符合材料现状。',
  uncertainty_reason='联合单元无单一来源/引句可核，四项旗标与相关性填u；底层事件日期与时点适用性保持unknown。'),
], 'submissions/reviewer_A-7402/002008')
print('ALL DUAL-SOURCE A FORMS WRITTEN')
