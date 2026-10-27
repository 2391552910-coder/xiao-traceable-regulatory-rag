"""Expanded evidence-grounded paper; renders and audit are separate explicit steps."""
from pathlib import Path
import sys,json,re,hashlib,subprocess,shutil
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import revise_journal_manuscript_20261023 as prior
from docx import Document
from docx.shared import Cm,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor,white
OUT=ROOT/'results/paper/substantial_revision_20261023_01'
FIG=OUT/'figures'; FIG.mkdir(parents=True,exist_ok=True)
old=Document(next((ROOT/'results/paper/draft_20261023_01').glob('*.docx')))
texts=[p.text for p in old.paragraphs]

def schematic(name,kind):
    f=FIG/(name+'.pdf'); c=canvas.Canvas(str(f),pagesize=(560,260))
    navy=HexColor('#193F55'); blue=HexColor('#E8F0F4'); gray=HexColor('#F3F4F5')
    def txt(x,y,s,size=9,bold=False):
        c.setFillColor(navy); c.setFont('Helvetica-Bold' if bold else 'Helvetica',size);c.drawCentredString(x,y,s)
    def box(x,y,w,h,title,lines=(),fill=blue):
        c.setStrokeColor(navy); c.setLineWidth(.7);c.setFillColor(fill);c.roundRect(x,y,w,h,4,fill=1,stroke=1)
        txt(x+w/2,y+h-17,title,10,True)
        for i,line in enumerate(lines):txt(x+w/2,y+h-34-i*13,line,8.5)
    def arrow(x1,y1,x2,y2,label=''):
        c.setStrokeColor(navy);c.line(x1,y1,x2,y2)
        import math
        a=math.atan2(y2-y1,x2-x1)
        for delta in [-.45,.45]:c.line(x2,y2,x2-5*math.cos(a+delta),y2-5*math.sin(a+delta))
        if label:txt((x1+x2)/2,(y1+y2)/2+5,label,8)
    if kind==1:
        box(5,173,120,70,'Annual reports',['Company / year scope','PDF + page + span'])
        box(5,73,120,70,'Regulatory documents',['Version metadata','Text / mapped PDF'])
        box(157,173,120,70,'Annual retrieval',['Dense + BM25','Rerank / fixed quota'])
        box(157,73,120,70,'Rule retrieval',['Dense + BM25','Rerank / fixed quota'])
        box(308,115,110,80,'Context packing',['Whole chunks','Reference-token cap','A / R source IDs'])
        box(448,115,108,80,'Cited response',['Disclosed facts','Rules / comparison','Evidence limitations'])
        arrow(125,208,157,208);arrow(125,108,157,108)
        arrow(277,208,308,171);arrow(277,108,308,140);arrow(418,155,448,155)
        box(157,4,399,43,'Replayable records',['Document hashes + context hashes + requests + human ratings'],gray)
        arrow(365,115,365,47)
        txt(65,34,'Public query x = (c, y, q)',8)
    elif kind==2:
        box(5,180,125,60,'G1  Merged retrieval',['Common candidate pool','Generic cited prompt'])
        box(165,180,125,60,'G2  Dual retrieval',['Separate source quotas','Generic cited prompt'])
        box(325,180,125,60,'G3  Role prompting',['Identical G2 evidence','Role-constrained prompt'])
        arrow(130,210,165,210,'RQ1');arrow(290,210,325,210,'RQ2')
        box(5,72,145,66,'Retrieval ablations',['No reranker / BM25 only','60 questions each'],gray)
        box(180,72,160,66,'Source removal',['Delete A / delete R','20 matched questions'],gray)
        box(370,72,180,66,'Service-version comparison',['K3 / K2.8 alias','20 questions; effort not matched'],gray)
        arrow(227,180,227,138);arrow(389,180,330,138);arrow(430,180,450,138)
        txt(280,35,'Outcome labels: two independent raters; company-clustered paired analysis',10,True)
        txt(280,17,'New replay analyses change context budgets, not the original human-rated outputs.',9)
    else:
        box(5,170,160,70,'Annual evidence A',['Document SHA256','Physical page / text span'])
        box(5,70,160,70,'Rule evidence R',['Document SHA256','Clause / version / text span'])
        box(205,170,150,70,'Disclosed-fact claim',['A-linked factual statement','Disclosure is not ground truth'])
        box(205,70,150,70,'Normative claim',['R-linked requirement','Time applicability separate'])
        box(399,115,155,82,'Comparative conclusion',['Needs relevant facts + rules','Missing chain: qualify / abstain','No automatic legal certification'])
        arrow(165,205,205,205);arrow(165,105,205,105)
        arrow(355,205,399,172);arrow(355,105,399,143)
        txt(280,29,'Resolvable citation IDs  !=  semantic support  !=  temporal applicability',11,True)
        txt(280,11,'Conceptual representation of the implemented source roles; not a new trained verifier.',9)
    c.showPage();c.save()
    pop=shutil.which('pdftoppm')
    if not pop:
        raise FileNotFoundError('pdftoppm is required to rasterize generated paper figures; install Poppler and add pdftoppm to PATH.')
    subprocess.run([pop,'-scale-to','2400','-png','-singlefile',str(f),str(f.with_suffix(''))],check=True)
    return f.with_suffix('.png')

INTRO=[
'上市公司评价中的证据具有明确的角色差异。年报记录企业对治理安排、内控事项和分红政策的公开披露，法规文件规定相关主体应当履行的要求。回答“公司披露了什么”与回答“披露是否满足规范要求”所需要的证据并不相同。前者不能仅凭法规推断，后者也不能仅凭公司描述完成。将二者组织为可核查的回答，是面向专业文档问答的一个具体信息处理问题。',
'传统检索往往把片段按问题相关性放入同一个排序列表，但语义相似度并不编码证据在论证中的角色。某类法规因为包含与问题高度一致的术语而占据前列时，公司特有披露可能被排出上下文；反之，年报中的政策复述也可能挤占规范原文。有限上下文进一步放大了候选竞争。即使最终答案同时出现公司名称和法规名称，也不能据此确认模型取得并正确使用了两类原文。',
'RAG把外部检索与语言生成结合，为知识密集任务提供了可更新的证据接口[1]。然而，检索相关、上下文可用、论断获支持和法规适用是不同层次的问题。增加重排器、提示模型逐条引用或引入多个角色，都可能改变回答，但这些组件各自是否有价值，仍需在相同问题与可比较条件下检验。本文因此将来源分离和角色提示作为两个不同的干预因素。',
'研究设置三个主要问题。RQ1考察按来源独立检索，相对于合并检索能否改善当前任务的回答质量；RQ2在逐字相同的检索上下文下，考察来源角色提示的增量作用；RQ3考察配置简化、材料缺失和同系列服务版本变化对观察结果的影响。为解释结果，本文新增预算与候选配额回放、检索位置代理、评分维度拆解、逐公司敏感性和运行开销分析。',
'本文的工作包括：实现保留文档身份、物理位置及实际提示记录的双源RAG原型；用受控比较拆分检索组织与生成提示的作用；在20家公司60题和两位人员评分上报告正向、零增益及反向差异；通过不改变历史回答的新回放实验检查来源供给机制。本文不把现成模型的组合宣称为新基础算法，也不以引用编号有效替代语义质量。',
'在已观测配对中，双路检索相对合并检索呈现正向差异，而同上下文的角色提示没有稳定额外收益；去重排和仅BM25的描述性高分提醒我们，增加检索复杂度并不自动改善专业问答。本文因此采用实证研究定位：说明何种证据组织有帮助、哪些组件未显示收益，以及现有测量还能支持多大范围的结论。该定位也决定了后续分析保留负结果和失败记录。'
]
RELATED=[
('2.1 金融文档问答与领域证据','''FinQA聚焦金融数据中的数值推理[2]，TAT-QA研究表格与文本混合内容上的问答[3]。二者表明，财务报告中的证据结构与一般开放域文本不同，但其任务目标并不等同于公司披露与规范依据的联合评价。HiREC通过层级检索和证据整理处理标准化金融文件[4]，直接说明年报检索、长文档组织与补充查询本身已有先行研究。
近期年报问答基准进一步检验了表格、正文与答案证据的联合组织。ARQA覆盖十个财年汽车企业年报，提供约2,500条查找、计算与洞察类问答；题目经过确定性校验与重算，并由领域专家审核[28]。中文CFQA以50家上市公司2023—2025年年报构建500题，人工标注并绑定原文，再比较RAG与无检索基线，同时区分答案匹配与证据支持/编造[29]。这些工作聚焦年报内部问答基准；本文研究的是公司披露与独立法规证据的联合评价，并在已有20家公司60题的双人评分上区分来源分路与提示约束。本文不将金融文档检索或年报QA基准构建本身宣称为独立创新。
Siddharth与Luo从工程文档中提取显式事实供生成使用[5]，Yang等梳理了语言模型与知识方法的结合[6]。本文选择直接以文档及其坐标作为运行输入，避免要求先建立穷尽的公司事实库。参考事实与证据用于离线评价，而非先把答案编码进运行时知识库。此差异使检索误差、解析误差和生成误差能够分别检查。'''),
('2.2 稀疏稠密检索与领域增强','BM25以词项匹配提供稀疏检索信号[7]，DPR等方法学习稠密表示以缓解词面差异[8]，Qwen3 Embedding系列进一步提供嵌入与重排模型[9]。不同检索信号的互补性不等于其在所有领域都能提升端到端质量。混合分数的尺度、候选组成及下游生成器都会影响结果，因此本文同时保留仅BM25与去重排条件。RRF提供基于名次的融合思路[10]，但本轮主配置使用固定加权融合，不把未运行的RRF写成实验结果。\nAlier等针对教育语料中的缩写检索困难，分别研究查询时与入库时增强，并分析组件、误差和部署成本[11]。这类领域化研究提示，应先识别真实检索失败，再验证干预环节。本文的领域因素是两类资料承担不同证据角色，新增回放用于测量材料供给的变化，而不直接把位置命中解释为完整语义支持。'),
('2.3 迭代检索与智能体协作','Self-RAG通过检索和自反思机制改进证据使用[12]，CRAG引入对检索质量的纠正处理[13]，Adaptive-RAG根据问题复杂度选择检索策略[14]。AIR-RAG研究迭代检索与生成器对齐[15]。这些方法提供了更强的自适应基线方向，但其中的训练目标、控制器或推理流程不能用一句“请反思”替代。本文没有复现这些训练型方法，因此在相关工作中讨论，在实测表中不填写其性能。\nReAct把推理与外部动作交错组织[16]；CoLE借鉴法律专家的分工构造提示流程[17]；MADKE通过共享外部知识辅助多智能体辩论[18]。本文当前实现是固定的双源检索与生成编排，来源角色提示也只是提示干预，不具备自主工具规划或多智能体通信。区分这些实现边界，能够防止把模块数量、来源数量和智能体数量混为一谈。'),
('2.4 引用评价与专业任务有效性','ALCE将生成与引用质量纳入评价[19]；RAGAs提供自动化评价方法[20]；RAGChecker进一步分解检索和生成环节[21]。这些研究共同说明，答案表面质量和引用可解析性不足以解释完整RAG表现。本文将请求成功、结构有效、来源可回放、人员质量评分和法规适用性分开报告，且不把模型自报的支持状态用于替代人员判断。\nLegalBench-RAG强调在法律文档中定位相关证据片段[22]，长上下文研究则显示信息的长度和位置可能影响模型利用能力[23]。本文现有参考标签主要在页面与要点层次，不是穷尽的最小片段相关性标注，因此新增检索分析使用严格来源与页码位置代理，避免套用标签条件不成立的标准Recall或nDCG。法规时点适用需要事项时间和规范版本证据，仍不能仅靠检索相关来确认。')
]
METHOD=[
('3.1 输入输出与研究对象','设公司标识为c，报告年度为y，评价问题为q，公开输入为x=(c,y,q)。文档库由年报集合D_A和法规集合D_R组成，来源函数τ(d)取A或R。输出包含回答a、实质论断集合C、论断与实际证据编号之间的关联，以及材料不足或冲突说明。本文的评价单位是给定问题的文档依据回答，不是对公司真实治理水平的无条件评级。\n年报对公司事实提供披露层面的依据。某项事项未被解析到、没有被检索到或没有在给定片段中出现，都不能推出事项本身不存在。规范性论断需要核对法规原文，将公司披露与规范要求比较时还需确认两者的实体、主题和时间条件可比。资料不齐时允许保留未知，不能强制输出合规结论。'),
('3.2 文档身份与位置表示','每份文档首先登记来源、公司及年度、全文或摘要身份、版本信息和文件SHA256。年报PDF按物理页建立文本帧，片段保存文件哈希、页面文本哈希、从1开始的物理页序及字符起止区间。印刷页码和阅读器物理页序分别处理，不通过文件名推测页码。OCR文字保留其解析来源及未核实状态，原PDF保持不变。\n法规来源按其真实文件形式定位。文本法规保留原文件哈希与字符区间；可映射到PDF的来源另保留物理页及页内位置。跨页条款需要逐段位置，而不能为整个条款编造一个“正确页码”。发布日期、生效日期、失效日期和事项日期是不同字段，缺失值不以本地修改时间或报告年度补齐。\n位置记录解决“模型看到了哪段材料”的回放问题，并不自动解决该段是否支持论断。本文把来源解析视为语义审计的前提条件，而非替代条件。哈希相同只能证明字节身份一致；即使原文可靠，同一句话也可能因主体、时间或例外条件不同而不适合用于当前评价。'),
('3.3 双作用域检索与固定融合','年报作用域D_A(c,y)由公司和报告年度限定；法规作用域D_R(q)由文档类型及实际配置允许的时间元数据处理限定。两种策略使用相同的可用来源范围，避免将“多了一份正确资料”与“换了排序方法”混为一谈。默认检索模型为Qwen3-Embedding-0.6B，重排模型为Qwen3-Reranker-0.6B，文档编码不混入查询提示，查询使用固定任务指令。\n稠密与BM25信号使用固定配置融合，主配置稠密权重为0.7、稀疏权重为0.3。该数值是原型参数，不是通过本轮测试集证明的最优权重。候选重排后进入上下文组装。本文后续不根据测试结果回调这些参数，也不将未检验的权重变化写成改进。\nG1把两类资料的合格片段放在共同候选池，取总候选上限10；G2在年报和法规作用域各取最多5个候选，再按现有确定性规则合并与组装；G3直接复用G2组装后的上下文。双路并不保证所有问题都取得足量年报证据，原因包括上游召回不足、片段过长和总预算裁剪。新增回放实验直接测量这些条件。'),
('3.4 上下文组装与可比较性','设候选序列H=(h₁,…,h_K)，T为冻结的参考分词器，B为上下文上限。组装器按既定顺序访问候选：若加入完整片段后|T(E⊕hᵢ)|≤B，则保留，否则跳过该片段继续检查后续候选。重复片段ID被拒绝，片段文本不截断；最终记录实际保留、跳过原因和上下文哈希。\n这种whole-chunk策略避免把引用位置与截断后的残句混淆，但会带来预算未完全填满和来源数量变化。候选配额是进入组装器的上限，不是最后上下文中两类来源的保证。某个长年报片段被跳过后，后续短法规可能仍能进入，这种供给变化需要通过实际tokens、片段数量和位置覆盖共同描述。\n主对照使用总计6000参考tokens上限。相同上限不等于相同实际token数，也不等于同等服务端费用；参考分词器与API供应商分词器未验证一致。本文因此将“预算匹配”限定为共同的参考上限，并在新分析中报告实际用量与延迟，不把上限相同表述为计算量完全相等。'),
('3.5 引用约束与来源角色','G1和G2都要求实质论断给出实际提供的证据ID、claims及citations，并共同包含不得凭记忆补充事实和法规、材料不足时说明限制等要求。因此，G2相对G1的差异主要对应检索组织变化，不能表述为“无引用”到“有引用”。G3增加事实论断用年报、规范论断用法规以及比较性评价需要相应证据链的要求。\nG2与G3的上下文和来源记录逐字一致，隔离的是提示约束的增量作用。模型返回的claims和evidence_status仍属于模型输出。结构检查只检验必需字段、证据编号可解析与数据类型，不将模型写出的supported视为经核验的支持标签。真正的质量分析以两位人员对原文的独立评分为依据。\n来源角色可表示为论断—证据二部关系。事实论断与A类片段相连，规范论断与R类片段相连，比较性论断可以连接两类片段，但仅有两条连线并不能证明比较成立。还必须检查原文是否相互匹配、是否支持同一事项，以及事项日期与规范版本是否具备足够依据。本文没有训练一个能够自动认证这些关系的判别器。'),
('3.6 复杂度与运行记录','令两个作用域候选数量分别为N_A、N_R，查询向量维数为d。对缓存向量直接计算相似度的矩阵运算与(N_A+N_R)d成正比；BM25评分和重排开销另计。G1和G2的候选池组织不同，可能产生不同的上游召回与重排调用量，不能仅因最终候选上限相同就认为检索成本相等。本文的实测运行开销来自保存日志，回放时间不作为神经检索时间。\n实现保存文档、索引清单、输入上下文、请求参数及响应的分层记录，使数据变化与推理变化可以分别追踪。完整原始响应、结构失败与一次恢复视图均保留；API密钥不进入论文或材料包。新增分析使用新的目录和脚本，不覆盖先前评分、运行或论文版本。')
]
DISCUSSION=[
('7.1 正向效应对应的研究结论','双路检索相对合并检索的正向差异，应与新增来源供给分析一起理解：如果上下文中的公司材料减少，事实性问题就可能缺少公司特有细节；如果法规材料缺失，规范性比较则缺少明确依据。但“哪类片段更多”只是中间机制，仍不能由统计关联直接证明它就是总分变化的因果中介。本文不把候选数量、页位置命中与语义支持率互相替代。\n对一个面向实际文件的系统而言，原文可回放和来源组织清晰有独立的工程价值。它们降低事后复核时查找材料的成本，也使错误能定位到解析、检索、上下文组装或生成环节。然而，这种工程价值不能抵消回答质量上的负结果；如果简化配置更好，应保留该现象，而不是只展示符合预期的比较。'),
('7.2 提示约束为何不能预设有益','G3与G2之间没有稳定增量，首先说明在当前上下文和量表条件下，增加来源角色措辞没有显示可辨别的额外收益。G2的共同提示已经要求引用并限定证据来源，强生成器也可能自行区分事实与规范；这是一种解释，而非已被独立实验验证的原因。另一种可能是评分量表接近天花板，不能分辨细粒度的引用完整性差异。\n因此，本文不把零增益改写为“同样证明了角色提示有效”，也不把它解释为在任何任务中都无效。更合适的下一步是预先定义逐论断的必要来源角色、保留未知和冲突类型，在独立问题上测量提示是否改变了具体证据使用，而不是继续用一个接近满分的总分期待更大差距。'),
('7.3 简化基线与组件解释','重排器通常针对相关性训练，但当前任务的回答质量同时取决于公司身份、披露细节、法规主题和材料可用性。高相关性片段不一定包含完整判断所需的互补信息。稠密融合也可能增加语义相近却不支持特定事项的内容。上述机制能够提出错误分析方向，但在没有逐片段语义复核之前，不能直接断言重排器因为某一机制而有害。\n人员间对BM25比较的方向差异进一步说明，平均结果掩盖了评分尺度与维度的作用。实务选择应同时看效应、费用、失败率和复核难度，而不是默认复杂方案更先进。本研究据此保留BM25和去重排作为有竞争力的对照，并将结论限定在所用实现、问题与评分范围。'),
('7.4 专业任务中的不确定性','删除一类来源后的降分表明材料具有互补性，但合理的证据不足回答仍可在不确定性维度得分。一个“谨慎而未回答完整”的输出可能保留较高总分。这不一定是量表错误，因为拒绝越界本来就是专业问答的重要行为；但如果目标是同时评价答案完成度，就必须把完成度与保守性拆开。\n同样，引用支持维度的高分并不意味着实现了逐规则完整归因。页面上的文字可能只支持一个复合论断的一部分；法规在语义上相关，也可能因生效时间和主体范围而不适用。本文把这些层次明确分开，以避免读者把系统的专业措辞误当作法律判断认证。'),
('7.5 内部有效性','主对照不是在完全未见结果之前设计的确认性实验。原主输出曾被查看，简化评分与均分汇总方案也在不同阶段制定，新增诊断属于事后探索。保留冻结哈希和历史记录能够说明实际执行边界，但不能回溯消除暴露。本文报告点对点区间，不把多个探索性比较当作一组经过家族错误率控制的确认性检验。\n失败输出不被记为质量0分，因此可用输出上的差异属于条件性结论。最坏有界范围反映未观察质量可能改变方向的程度；逐公司删除检验的是是否被某一个公司簇主导，并不能解决共有法规造成的跨公司相关。两种敏感性针对不同假设，均不替代新增样本。'),
('7.6 外部有效性与资源限制','本轮公司样本和报告年度有限，三个主题也不能代表全部公司自律评价问题。共享法规使公司簇之间可能存在相关，不同年份的披露模板和规范版本变化还可能改变结果。新预算回放使用既有候选，不重新发现候选池外的证据，因此反映的是保存排序下的组装敏感性，而不是任意预算下重新执行检索的完整系统性能。\n补充的法规版本审计发现，本研究问题均以2024年报告为背景，而当前知识库中的DOC100《上市公司信息披露管理办法》、DOC128《上市公司章程指引》和DOC120《上市公司治理准则》分别对应2025年第226号令、2025年第6号公告版和自2026年起施行的2025年第18号公告版；较早的第182号令、2023年修订文本和2018年版未作为相应历史版本独立纳入索引[25–27]。按清单日期检查冻结的法规top-10候选，G1合库检索的73条法规候选中有64条晚于报告年度，涉及42/60题；G2双路检索的300条中有156条晚于报告年度，涉及60/60题。日期字段只提示版本时间风险，不单独证明某条规范对具体事项不适用。因此，涉及这些文件的检索与评分只反映当前语料快照，不能解释为2024年历史法规版本命中率或时点合规性验证。\n此外，截至2026年10月27日，两份法规来源版本复核提交已通过结构校验，但92项字段差异仍待仲裁，接受标签为0；审阅人身份未认证，盲审状态未获验证。这些提交未用于更新知识库版本元数据，也不构成法规时点适用性的独立验证证据。\n同系列K3与K2.8服务别名具有不同的默认思考预算和未核实底层revision，所测差异不能归因于模型权重，也不能称为跨模型族泛化。每单元一次生成还不足以估计采样波动。本研究不利用这些限制回避负结果，而是用它们约束研究结论，明确哪些观察可以支持，哪些还需新的独立试验。'),
('7.7 后续研究与部署含义','现有新增回放和统计诊断已经改善了对系统行为的解释，但尚未提供新的跨模型族、跨年度或多智能体语义质量结果。若进一步比较Agent，应固定总调用或token预算、上下文权限、最大工具步数和停止条件，并设置等调用数的单模型自检对照；否则额外费用与协作机制的作用仍混杂。仅将两个固定检索分支命名为智能体，不会形成这样的证据。\n部署时可优先采用能够保留身份、版本和定位记录的简单配置，明确区分材料缺失、检索未命中与实际不存在。对于涉及法规适用的事项，界面应展示可获得的事项时间与版本依据以及未知状态。本文的证据支持这种可审计设计的必要性，但尚不能量化其对真实决策风险或人员工作效率的全部影响。')
]

REFS=[
('Lewis P, et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. NeurIPS 33, 2020: 9459–9474.','https://arxiv.org/abs/2005.11401'),
('Chen Z, et al. FinQA: A Dataset of Numerical Reasoning over Financial Data. EMNLP, 2021: 3697–3711.','https://doi.org/10.18653/v1/2021.emnlp-main.300'),
('Zhu F, et al. TAT-QA: A Question Answering Benchmark on a Hybrid of Tabular and Textual Content in Finance. ACL-IJCNLP, 2021: 3277–3287.','https://doi.org/10.18653/v1/2021.acl-long.254'),
('Choe J, Kim J, Jung W. Hierarchical Retrieval with Evidence Curation for Open-Domain Financial Question Answering on Standardized Documents. Findings of ACL, 2025: 16663–16681.','https://doi.org/10.18653/v1/2025.findings-acl.855'),
('Siddharth L, Luo J. Retrieval augmented generation using engineering design knowledge. Knowledge-Based Systems 303, 2024: 112410.','https://doi.org/10.1016/j.knosys.2024.112410'),
('Yang W, Some L, Bain M, Kang B. A comprehensive survey on integrating large language models with knowledge-based methods. Knowledge-Based Systems 318, 2025: 113503.','https://doi.org/10.1016/j.knosys.2025.113503'),
('Robertson S, Zaragoza H. The Probabilistic Relevance Framework: BM25 and Beyond. Foundations and Trends in Information Retrieval 3(4), 2009: 333–389.','https://doi.org/10.1561/1500000019'),
('Karpukhin V, et al. Dense Passage Retrieval for Open-Domain Question Answering. EMNLP, 2020: 6769–6781.','https://doi.org/10.18653/v1/2020.emnlp-main.550'),
('Zhang Y, et al. Qwen3 Embedding: Advancing Text Embedding and Reranking Through Foundation Models. arXiv, 2025.','https://arxiv.org/abs/2506.05176'),
('Cormack G V, Clarke C L A, Buettcher S. Reciprocal rank fusion outperforms condorcet and individual rank learning methods. SIGIR, 2009: 758–759.','https://doi.org/10.1145/1571941.1572114'),
('Alier M, García-Peñalvo F J, Casañ M J, Pereira J, Granados A. Closing the acronym gap in educational retrieval with ontology-guided augmentation. Information Sciences 740, 2026: 123181.','https://doi.org/10.1016/j.ins.2026.123181'),
('Asai A, Wu Z, Wang Y, Sil A, Hajishirzi H. Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection. ICLR, 2024.','https://arxiv.org/abs/2310.11511'),
('Yan S Q, Gu J C, Zhu Y, Ling Z H. Corrective Retrieval Augmented Generation. arXiv, 2024.','https://arxiv.org/abs/2401.15884'),
('Jeong S, Baek J, Cho S, Hwang S J, Park J. Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models through Question Complexity. NAACL, 2024: 7036–7050.','https://doi.org/10.18653/v1/2024.naacl-long.389'),
('Han W, Xiao X, Li Y, Wang J, Pechenizkiy M, Fang M. Adaptive iterative retrieval for enhanced retrieval-augmented generation. Neurocomputing 666, 2026: 132272.','https://doi.org/10.1016/j.neucom.2025.132272'),
('Yao S, et al. ReAct: Synergizing Reasoning and Acting in Language Models. ICLR, 2023.','https://arxiv.org/abs/2210.03629'),
('Li B, Fan S, Zhu S, Wen L. CoLE: A collaborative legal expert prompting framework for large language models in law. Knowledge-Based Systems 311, 2025: 113052.','https://doi.org/10.1016/j.knosys.2025.113052'),
('Wang H, et al. Learning to break: Knowledge-enhanced reasoning in multi-agent debate system. Neurocomputing 618, 2025: 129063.','https://doi.org/10.1016/j.neucom.2024.129063'),
('Gao T, Yen H, Yu J, Chen D. Enabling Large Language Models to Generate Text with Citations. EMNLP, 2023: 6465–6488.','https://doi.org/10.18653/v1/2023.emnlp-main.398'),
('Es S, James J, Espinosa Anke L, Schockaert S. RAGAs: Automated Evaluation of Retrieval Augmented Generation. EACL System Demonstrations, 2024: 150–158.','https://doi.org/10.18653/v1/2024.eacl-demo.16'),
('Ru D, et al. RAGChecker: A Fine-grained Framework for Diagnosing Retrieval-Augmented Generation. NeurIPS Datasets and Benchmarks, 2024.','https://arxiv.org/abs/2408.08067'),
('Pipitone N, Alami G H. LegalBench-RAG: A Benchmark for Retrieval-Augmented Generation in the Legal Domain. arXiv, 2024.','https://arxiv.org/abs/2408.10343'),
('Liu N F, et al. Lost in the Middle: How Language Models Use Long Contexts. TACL 12, 2024: 157–173.','https://doi.org/10.1162/tacl_a_00638'),
('Kimi. 模型配置. 服务别名说明；底层revision未核实，核对日期2026-10-20。','https://www.kimi.com/help/kimi-code/models')
 ,('中国证监会. 第182号令《上市公司信息披露管理办法》（2021）及第226号令《上市公司信息披露管理办法》（2025）。','https://www.csrc.gov.cn/csrc/c101864/c2ee1a791fddc4f5ebeeb70aa8e2399cf/content.shtml; https://www.csrc.gov.cn/csrc/c101953/c7547359/content.shtml')
 ,('中国证监会. 第62号公告《关于修改〈上市公司章程指引〉的决定》（2023）及第6号公告《上市公司章程指引》（2025）。','https://www.csrc.gov.cn/csrc/c101954/c7449659/content.shtml; https://www.csrc.gov.cn/csrc/c101954/c7547791/content.shtml')
 ,('中国证监会. 第29号公告《上市公司治理准则》（2018）及第18号公告《上市公司治理准则》（2025）。','https://www.csrc.gov.cn/csrc/c101864/c1024585/content.shtml; https://www.csrc.gov.cn/csrc/c101954/c7589726/content.shtml')
 ,('Wang R, Balloccu S. ARQA: A Benchmark for Grounded Table–Text QA in Enterprise Annual Reports. Proceedings of the 19th Conference of the European Chapter of the Association for Computational Linguistics, Industry Track, 2026: 847–868.','https://doi.org/10.18653/v1/2026.eacl-industry.63')
 ,('Zhu T, Liu M, Kurfali M. CFQA: A Chinese Financial Question Answering Benchmark from Corporate Annual Reports. Proceedings of the 7th Financial Narrative Processing Workshop, 2026: 28–38.','https://doi.org/10.63317/4e6fhrncfrbu')
]

def paras(d,text):
    for s in text.split('\n'):prior.p(d,s)
def section(d,title,text):prior.h(d,title,2);paras(d,text)
def fig(d,path,caption,width=16.3):
    pp=d.add_paragraph(); pp.paragraph_format.keep_with_next=True
    pp.add_run().add_picture(str(path),width=Cm(width))
    prior.p(d,caption,'Caption')
def table(d,cap,headers,rows):
    pp=prior.p(d,cap,'Caption');pp.paragraph_format.keep_with_next=True
    t=prior.table(d,headers,rows)
    # Keep only compact tables together; large comparison tables can span pages.
    for i,row in enumerate(t.rows):
        for cell in row.cells:
            for p in cell.paragraphs:p.paragraph_format.keep_with_next=(i==0 or (len(t.rows)<=7 and i<len(t.rows)-1))
    return t

def load(p):return json.loads((OUT/p).read_text(encoding='utf-8-sig'))
def csvrows(p):
    import csv
    return list(csv.DictReader((OUT/p).open(encoding='utf-8-sig')))
def num(v,n=3):return f'{float(v):.{n}f}'
def interval(v):return '['+num(v[0])+', '+num(v[1])+']'
def pct(v):return f'{float(v)*100:.1f}%'

def build():
    q=load('quality/quality_extensions.json'); audit=load('audit/robustness_audit.json')
    replay=csvrows('retrieval/replay_summary.csv')
    d=prior.base('年报与法规双源检索增强生成的受控评价与证据覆盖分析')
    d.styles['Normal'].paragraph_format.line_spacing=1.2
    d.styles['Normal'].paragraph_format.space_after=Pt(6)
    d.styles['Normal'].font.size=Pt(10.5)
    d.core_properties.subject='大幅扩展研究稿 真实回放实验与评分诊断 2026年10月23日'
    nt=nf=0
    def tab(title,heads,rows):
        nonlocal nt;nt+=1
        return table(d,f'表{nt} {title}',heads,rows)
    def pic(path,caption):
        nonlocal nf;nf+=1;fig(d,path,f'图{nf} {caption}')
    def op(i):prior.p(d,texts[i])
    prior.p(d,d.core_properties.title,'Title')
    prior.p(d,'Controlled Evaluation and Evidence-Coverage Analysis of Dual-source Retrieval-Augmented Generation over Annual Reports and Regulations')
    prior.h(d,'摘要')
    prior.p(d,'公司披露与规范依据在上市公司评价中承担不同证据角色，但来源分离、提示约束与检索质量的作用容易混淆。本文构建保留文档身份及原文坐标的双源检索增强生成流程，在20家公司2024年年报的60个问题上比较合并检索、双路检索和相同上下文下的来源角色提示，并设置检索简化、来源缺失及同系列服务版本比较。400个计划回答中386个有效输出经两位人员独立核对原文评分。新增实验完成1800个预算与配额上下文回放，120个原配置上下文逐字复现，并补充维度、主题、缺失和运行开销诊断。已观测配对中，双路较合并检索的0至8分公司宏均分提高0.250，95%公司聚类bootstrap区间为[0.167,0.333]；同证据下角色提示增量为−0.008，区间跨0。双路的两类来源同现率从68.3%增至100%，但严格来源哈希与页面覆盖均值未提高，法规参考页面覆盖仍有限。质量收益主要出现在法规评分与审计委员会主题，引用及不确定性评分存在明显天花板。结果支持在本任务中区分来源角色的供给价值，同时揭示来源平衡、目标证据定位和回答质量之间不能相互替代。本文保留反向与零增益结果，结论限于探索性样本及所用指标。')
    prior.p(d,'关键词：检索增强生成；年度报告；法规证据；来源追溯；预算回放；人工评价')
    prior.h(d,'Abstract')
    prior.p(d,'Corporate evaluation requires both company disclosures and regulatory evidence, yet the effects of source separation, prompting, and retrieval quality are easily conflated. We develop a traceable dual-source retrieval-augmented generation pipeline and evaluate merged retrieval, dual retrieval, and role-constrained prompting with identical evidence. The study covers 60 questions about 20 companies’ annual reports for 2024. Two reviewers independently assessed 386 valid outputs from 400 planned responses across main comparisons, retrieval ablations, source-removal tests, and a same-family service-version comparison. Additional experiments replay 1,800 context configurations over token caps and candidate quotas, reproducing all 120 original contexts exactly. On observed pairs, dual retrieval improves the company-macro quality score by 0.250 points on a 0–8 scale, with a company-clustered 95% bootstrap interval of [0.167, 0.333]. Role prompting yields no stable additional benefit. Dual retrieval increases two-source presence from 68.3% to 100%, while average exact source-and-page coverage does not improve and regulatory reference-page coverage remains limited. Quality gains concentrate in the regulation dimension and audit-committee questions; citation and uncertainty scores exhibit substantial ceiling effects. These exploratory results separate source availability from target-evidence coverage and answer quality, exposing both the benefits and limitations of source-aware retrieval organization.')
    prior.p(d,'Keywords: retrieval-augmented generation; annual reports; regulatory evidence; provenance; context-budget replay; human evaluation')
    prior.h(d,'1 引言')
    for s in INTRO:prior.p(d,s)
    pic(FIG/'fig01_schematic.png','系统流程与可回放记录。年报和法规独立限定作用域，经检索、重排与整块预算组装形成实际上下文；来源坐标不等于语义支持。')
    prior.h(d,'2 相关工作与研究定位')
    for title,text in RELATED:section(d,title,text)
    tab('代表性研究与本研究的区别', ['研究','主要处理对象','本文采用或比较的边界'],[
      ['FinQA / TAT-QA [2,3]','金融报告数值与混合内容问答','任务相关；本研究聚焦披露与规范联合依据'],
      ['ARQA / CFQA [28,29]','年报表格—文本QA基准与答案证据评估','聚焦年报内部问答；本文补充法规来源角色与来源组织对照'],
      ['HiREC [4]','金融文件层级检索与证据整理','不将金融检索本身宣称为新方法'],
      ['领域知识RAG [5,6,11]','领域知识表示与检索增强','借鉴组件控制；不复制本体或知识图谱'],
      ['Self-RAG / CRAG [12,13]','自反思或纠正检索','未忠实复现；不填入性能对照表'],
      ['Adaptive-RAG / AIR-RAG [14,15]','自适应与迭代检索','作为后续强基线，当前仅固定检索'],
      ['CoLE / MADKE [17,18]','法律专家提示与知识增强辩论','当前系统不称为多智能体'],
      ['ALCE / RAGAs / RAGChecker [19–21]','引用与细粒度质量评价','区分结构、语义和实际人员评分'],
      ['LegalBench-RAG [22]','法律片段证据定位','本研究页级标签不冒称穷尽片段qrels']])
    prior.h(d,'3 双源检索与可追溯生成方法')
    for i,(title,text) in enumerate(METHOD):
        section(d,title,text)
        if i==0:
            tab('符号与含义',['符号','定义'],[['x=(c,y,q)','公司、报告年度和评价问题'],['D_A(c,y), D_R(q)','年报和法规的合格检索作用域'],['H_A,H_R,H_M','两类独立候选与合并候选序列'],['K_A,K_R,K','来源候选配额及总上限'],['B,T(E)','上下文参考token上限及计数'],['E_M,E_D','合并检索与双路检索实际上下文'],['C,L','实质论断集合及论断—证据关联'],['Q_i,Δ_c','回答探索性质量总分及公司内配对差']])
        if i==1:
            tab('来源记录与各检查层次',['记录或检查','保存内容','能够说明的范围'],[['文件身份','来源、版本、SHA256','文件字节与声明身份的关联'],['PDF位置','物理页、文本帧哈希、字符区间','片段可以回到实际页面'],['文本法规','文件哈希、条号与字符区间','不伪造PDF页码'],['上下文回放','实际片段ID、prompt/context哈希','实际提供给模型的材料'],['引用ID校验','引用是否来自提供的ID集合','仅结构可解析'],['人员原文评分','事实、法规、引用和不确定性','探索性质量判断'],['时点适用','事项日期、有效期间及版本','需独立证据；本轮未全面验证']])
        if i==3:
            prior.p(d,'G1: E_M=Pack_B(Top_K(D_A(c,y)∪D_R(q)));   G2: E_D=Pack_B(Merge(Top_KA(D_A), Top_KR(D_R)))。')
            prior.p(d,'G3: E_role=E_D；a_generic=LLM(P_generic,E_D)，a_role=LLM(P_role,E_D)。')
            prior.p(d,'上述等式描述实现中的条件控制关系，不是额外训练目标。候选排序、片段长度和访问顺序共同决定最终E，因而即使K_A=K_R，也须检查Pack后的来源数量。')
        if i==4:pic(FIG/'fig03_schematic.png','论断—来源关系与核验层次。比较性结论需要相应事实与规范，但编号连线本身不证明语义支持或时点适用。')
    prior.h(d,'4 数据与实验协议')
    section(d,'4.1 文档库与问题集合','本文区分系统可检索文档库与用于评分的问题集。新增检索审计在冻结索引中识别到39份年报的13038个片段，以及87份法规来源的5994个片段，合计19032个合格片段。它们是按类型和系统输入标记筛选后的实际作用域，不与早期先导运行中的其他文档数或片段数混用。87份法规来源中可能包含文本与PDF形式，物理页字段的可用性也不同。\n人员评价使用20家公司2024年年报对应的60题，每家公司三个主题：审计委员会、内部控制与分红披露。该组合使同公司题目相关，不能将60题当作60个独立公司。题目有180个参考要点、123条去重参考证据及256次问题—证据关联。参考证据不是穷尽的所有支持材料，而是已复核的目标原文。')
    tab('语料与标注范围',['对象','数量','解释'],[['合格年报库','39份 / 13038片段','39个来源哈希，全部有物理页'],['合格法规库','87份 / 5994片段','87个来源哈希；289个片段有物理页字段'],['质量问题集','20公司 / 60题','2024年；3主题各20题'],['参考要点','180','问题级评分依据，非穷尽公司事实库'],['参考证据','123条 / 256次关联','123/123目标来源哈希和页面在索引中存在'],['独立评分','386回答 × 2人 × 4维','共3088个0/1/2数值；没有U']])
    section(d,'4.2 比较条件与变量隔离','主对照在60题上执行G1、G2、G3，共180个计划单元。G2与G3共享完全相同的证据，隔离提示约束；G1与G2的合格来源范围、总候选配额和参考上限一致，但实际候选组成和token长度可能不同。去重排和仅BM25各60个单元，保留角色约束作为检索配置对照。\n来源缺失在预先确定的每公司一题上分别删除全部年报或全部法规片段，共40个单元。保留剩余片段的文字与编号，不重新检索。删除同时改变信息内容与实际长度，因此它测量的是当前输入中一类资料的缺失反应，不是纯角色标签效应，也不等价于一般噪声鲁棒性。\n同系列服务版本比较在同一20题上各执行三条件，共60个单元。kimi-for-coding别名在供应商说明中对应K2.8 Preview [24]，与主模型k3的底层checkpoint均未独立验证。两者默认思考预算不同，比较属于服务版本敏感性，不是严格等计算预算的权重比较，更不是跨厂商模型族泛化。')
    tab('实际比较与新增分析的范围',['分析','计划规模','主要控制与边界'],[['主对照','60×3=180回答','G1/G2组织差异；G2/G3同上下文'],['检索消融','60×2=120回答','去重排、仅BM25；非所有配置全面因子设计'],['来源缺失','20×2=40回答','删来源不重检索；信息与长度同时变化'],['服务版本','20×3=60回答','同系列别名；默认思考预算不同'],['新预算回放','60×2×3×5=1800上下文','固定候选排序；非1800条新生成回答'],['新统计诊断','386输出 / 400单元清单','复算既有评分，不新增人工标签'],['新稀疏检索','60题×2策略','完整合格作用域CPU BM25；与缓存神经候选分开解释']])
    pic(FIG/'fig02_schematic.png','变量隔离与扩展实验设计。回放改变候选配额和组装预算，不改变历史评分输出。')
    section(d,'4.3 实现参数与执行失败','检索Embedding revision固定为97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3，Reranker revision固定为e61197ed45024b0ed8a2d74b80b4d909f1255473。默认本地CUDA、float16、batch size为1，硬件为GTX 1660 Ti；文件、哈希、BM25与统计使用普通CPU处理。生成由远程API完成，本机GPU配置不决定服务端生成速度。\n主生成temperature为1，最大输出16384 tokens，请求超时600秒，SDK自动重试为0，每个题目—条件运行一次。调度随机种子42没有发送为生成随机种子，不能据此宣称可精确复现采样。准备阶段因供应商参数限制或截断发生的请求设置修订及错误回执均保存。主对照首轮147/180有效，一次失败恢复后178/180；不以恢复视图覆盖首轮。')
    section(d,'4.4 双人评分与可测量内容','两位人员分别对实际回答核对原文，评分包含公司事实、法规依据、引用支持和不确定性处理，每维0、1、2或U。只有两人四维均为数值时计算均分总量Q_i=(1/2)∑_r∑_j s_irj，范围0至8。本轮没有U，失败与未运行不填质量0分。均分是分析指标，不是分歧裁定或一致金标。\n每个分数表示对该回答在所用简化量表下的判断，不对应公司治理分数，也不是经过概率校准的合规准确率。引用项是回答层面的粗量表，不能推导逐论断完整归因或原H1/H2定义的联合成功率。原始评分、复核说明与分歧保留，新增分析没有更改任一人的分值。\n输出评分与题目标注的复核是不同过程。参考材料的两名既有复核人员与最终两份输出评分分别登记。项目负责人已更正早期AI辅助身份标识并确认两份评分由人员核对原文，本文沿用验收记录而不添加不存在的裁定过程。两人均分和评分者敏感性方案在评分可见后决定，因此属于探索性分析。')
    section(d,'4.5 配对估计与缺失敏感性','对相同问题匹配两个条件，先计算每家公司内已观测配对差值，再对公司等权平均。原主结果采用2000次公司聚类bootstrap、种子42；新增维度和主题诊断采用10000次、种子20261023。区间均为探索性点对点百分位区间，不进行多重比较校正。不同分析的抽样次数明确区分，保留原主区间便于历史对照。\n公司聚类考虑了同公司三题相关，但不能消除共有法规造成的跨公司依赖。新增逐公司删一分析检查观察差异是否依赖单个公司，完整题和完整公司分析检查在共同成功子集上的方向。它们都不等同于处理了所有缺失偏差，也不使原问题变成未见测试。\n缺失敏感性另报告全计划问题均差的代数界。若同题两侧均已知，贡献为q_t−q_b；若只有处理侧缺失，贡献区间为[−q_b,8−q_b]；若只有基线缺失，则为[q_t−8,q_t]；两侧均缺失时为[−8,8]。将各题区间端点求均值获得保留已知单侧的锐界。该量是问题加权，不是公司宏均值的置信区间，不能与bootstrap区间混称。')
    section(d,'4.6 新回放与检索诊断指标','新增回放使用保存的最终候选排序，不调用生成器、不重新编码文本。候选总数取2、6、10，双路对应每侧1、3、5；预算取1000、2000、4000、6000、8000参考tokens，共1800个上下文。所有条件均通过同一个完整片段组装器和冻结参考分词器，并验证默认10候选、6000上限的120个原上下文逐字复现。\n位置指标首先按源文件SHA256与物理页序匹配参考证据，分别计算年报和法规的目标页面覆盖比例，再取两角色均值。双角色出现率仅检查至少一个A和一个R片段，双参考角色可用率要求两类至少各命中一条目标页面。前者是类型供给代理，后者仍是位置代理；二者都不等于逐论断语义正确率。\n来源哈希严格相等不会自动合并同一法规的文本版本、PDF版本或其他等价支持材料。因此，低位置覆盖既可能意味着目标原文未检索，也可能未计入替代来源。新增12字符连续片段覆盖仅作词面补充，同样不能确认语义等价。解释结果时必须同时保留严格命中的可审计性和非穷尽参考带来的漏计可能。')
    prior.h(d,'5 主实验与评分诊断')
    section(d,'5.1 运行覆盖与质量分布','400个计划回答中，主对照恢复视图178个、消融109个、来源缺失40个、第二版本59个，共386个结构有效输出。最终14个单元无有效回答。有效表示返回且通过结构检查，不表示事实、引用或适用性已经正确。失败包括服务端504、JSON解析及连接问题，消融全部120条均已派发返回。')
    tab('可用输出与双人公司宏均分',['条件','可用/计划','双人均分','人员1','人员2'],[[c.text for c in r.cells] for r in old.tables[3].rows[1:]])
    prior.p(d,'表中各条件使用的问题子集和缺失不同，不能按非配对均分排序推断方法优劣。尤其是模型版本比较与来源缺失只使用20题，和60题总体条件不构成直接可比的全样本排名。BM25条件中人员2对全部54条输出给出满分，提示尺度分辨能力与评分者差异必须单独检查。')
    section(d,'5.2 双路检索与角色提示的增量','主对照G2−G1的公司宏差值为0.250，原95%区间[0.167,0.333]；两位人员分别为0.267和0.233，方向一致。G3−G1为0.267，但G3−G2为−0.008，区间[−0.050,0.025]，说明额外的来源角色措辞并未产生稳定增量。G3与G2在58个已知配对中只有1胜、56平、1负，粗量表下多数题目无法区分。')
    tab('主比较及原分析的点对点95%公司聚类区间',['比较','已知/计划','公司宏差值','原95%区间'],[[c.text for c in r.cells] for r in old.tables[5].rows[1:]])
    blob=old.inline_shapes[0]._inline.graphic.graphicData.pic.blipFill.blip.embed
    f=FIG/'original_paired_effects.png';f.write_bytes(old.part.related_parts[blob].blob)
    pic(f,'原主结果与人员敏感性。保留历史2000次bootstrap区间，新增诊断不覆盖原记录。')
    pe=[r for r in q['paired_effects'] if r['rating']=='mean']
    def effect(name,dim):return next(r for r in pe if r['contrast']==name and r['dimension']==dim)
    dims=['company_facts','regulation','citations','uncertainty','total']
    section(d,'5.3 新增逐维度分析','总分变化主要来自哪些维度，决定了结果应如何表述。新增分解显示，G2−G1在公司事实维度为−0.017、法规维度为+0.267，引用和不确定性均为0。因而总分正差不能改写为“各方面质量普遍提高”，更不能把法规评分提升解释为自动判对法规时点。\nG3−G2的总分接近0，也不意味着所有题目上行为相同：提示可以增加或改变模型的论断与引用结构，却未必改变人员的粗粒度评分。新增分析将这种表述变化与语义质量分开，避免把更多引用或更长回答当作更准确。')
    tab('新增双人均分的维度配对效应 每维0至2 总分0至8',['比较','配对数','事实Δ','法规Δ','引用Δ','未知处理Δ','总分Δ'],[[name,str(effect(name,'total')['known'])]+[num(effect(name,dim)['macro_delta']) for dim in dims] for name in ['G2-G1','G3-G2','G3-NoRerank','G3-BM25','NoAnnual-G3','NoRegulation-G3']])
    pic(OUT/'quality/quality_dimension_effects.png','新增维度效应。10000次公司聚类bootstrap；四维度均使用0至2量尺，误差线为点对点95%区间。')
    section(d,'5.4 新增主题异质性','G2−G1的差异集中在审计委员会主题D2，已知19个配对的均差约0.684；分红披露D1为0.100，内部控制D3为0。每个主题仍只有20家公司各一题，主题分析属于事后分层，不足以说明该领域所有审计委员会问题都有相同收益。\n该分布使总体结论更具体：观察到的收益并不平均分布于三个主题。它可能与问题对规范依据的需求及实际候选组成有关，但本研究没有通过独立中介实验排除题目措辞、参考要点与评分分辨率的影响。报告分层结果的目的，是给出可进一步检验的失败与收益范围。')
    tr=[r for r in q['topic_effects'] if r['dimension']=='total' and r['contrast'] in ['G2-G1','G3-G2','G3-NoRerank','G3-BM25']]
    tab('新增主题分层配对差异',['比较','主题','已知/计划','公司宏差值','95%区间'],[[r['contrast'],r['topic'],f"{r['known']}/{r['planned']}",num(r['macro_delta']),interval(r['ci95'])] for r in tr])
    pic(OUT/'quality/quality_topic_effects.png','新增主题异质性。D1为分红披露，D2为审计委员会，D3为内部控制；分层区间未经多重比较校正。')
    section(d,'5.5 评分者差异与量表天花板','386条回答共1544对逐维度评分，1312对一致，精确一致率84.97%。法规项一致率仅55.96%，二次加权κ约0.201。人员2的法规分相对人员1平均低0.435，显示法规评分存在明显尺度或判断差异。均分能够对称保留两人的信息，但不能将这种差异自动变成共识。\n引用与不确定性精确一致率分别为97.67%和99.74%，但由于一侧分值恒定，κ均为0。高一致率在这里伴随近满分分布，不能据此宣称测量高度可靠。若大量回答在同一档位，统计上小的差异既可能表示方法接近，也可能表示量表缺乏分辨率；本文不选择其中一种作为已证实解释。')
    ag=[r for r in q['agreement'] if r['mode']=='ALL']
    dn={'company_facts':'公司事实','regulation':'法规依据','citations':'引用支持','uncertainty':'不确定性'}
    tab('新增评分者尺度诊断',['维度','精确一致率','加权κ','R2−R1均差','R1满分率','R2满分率'],[[dn[r['dimension']],pct(r['exact_agreement_including_unknown']),num(r['quadratic_weighted_kappa_on_numeric_judgments']),num(r['reviewer2_minus_1']),pct(r['r1_ceiling_fraction']),pct(r['r2_ceiling_fraction'])] for r in ag])
    pic(OUT/'quality/quality_ceiling_diagnostics.png','评分天花板与人员满分率。近满分维度不能据其高一致率推导逐论断可靠性。')
    section(d,'5.6 消融来源与服务版本','G3在已观测配对上低于去重排与仅BM25，差值分别为−0.300和−0.325。人员间对BM25比较方向不同，相关缺失敏感性界限也跨0，因此结论不能写成重排必然有害或稠密检索普遍失败。更合理的观察是，在当前任务和量表下，完整配置未显示普遍优势。\n预选20题的来源缺失配对完整，删除年报下降0.900，删除法规下降0.650。该结果与来源互补一致，但不提供来源角色标签的纯因果效应，因为删除改变内容与实际上下文长度。缺失后保留高不确定性分也不表示问题已被完整回答。\n三个K2.8减K3比较的原点对点区间均包含或接触0，评分者方向也不一致。不同服务默认思考预算使版本比较存在计算条件混杂。即使将来增加重复生成，也需要控制调用参数和服务身份，不能仅增加样本就把它升级为严格的跨模型族验证。')
    tab('同系列服务版本差异 保留原分析',['条件','已知/计划','K2.8减K3','95%区间'],[[c.text for c in r.cells] for r in old.tables[6].rows[1:]])
    section(d,'5.7 新增完整样本与缺失敏感性','逐公司删一分析中，G2−G1仍保持正向，范围[0.237,0.263]；G3−G2范围[−0.018,0.009]跨0。五方法都有输出的49题子集中，G2−G1为+0.213，G3−G2为−0.038；在12个完整公司36题上分别为+0.208和0。这些结果说明当前方向不完全依赖某一个公司或某一对缺失题，但共同成功子集仍有选择偏差。\n新增锐界保留了缺失配对中的已知一侧，通常比将整对当作[−8,8]更窄。G2−G1全60题的问题加权均差锐界为[0.133,0.267]，仍为正；G3−G2为[−0.133,0.133]。G3对两个简化配置的锐界均跨0，因而不能将观察到的简化配置优势称为对全计划题目缺失稳健。锐界是代数可行范围，不是置信区间，不以其跨度衡量统计精度。')
    tab('新增删一与已知单侧缺失界 量尺与估计对象分别说明',['比较','删一公司宏差范围','全清单题均差锐界','胜/平/负题数'],[[name,interval(effect(name,'total')['leave_one_company_out_range']),interval(effect(name,'total')['full_inventory_question_mean_sharp_bounds']),f"{effect(name,'total')['win']}/{effect(name,'total')['tie']}/{effect(name,'total')['loss']}"] for name in ['G2-G1','G3-G2','G3-NoRerank','G3-BM25']])
    pic(OUT/'audit/missingness_and_loco_sensitivity.png','新增缺失与逐公司删一敏感性。本图观测均差区间以20000次公司聚类bootstrap补算，种子20261023，与维度、主题图的10000次不同。公司宏均差区间与完整题均差的代数界是不同估计对象，不能将后者读作置信区间。')
    prior.h(d,'6 新增检索实验与运行分析')
    section(d,'6.1 来源供给与目标页面覆盖','新增回放在原配置下显示，G1平均保留8.183个年报与1.183个法规片段，双角色出现率为68.3%；G2保留5+5片段，出现率为100%。G1的6000上限下实际参考tokens均值约4945，G2约4032，说明相同上限下的实际上下文并不等长。此处观察到的主要竞争是年报占据更多候选，而非预设某一种来源必然主导。\n但来源平衡没有转化为目标页面总体覆盖优势。G1与G2的年报页面覆盖均值分别为79.67%与74.33%，法规页面分别为0与3.89%，两角色平均39.83%与39.11%。同时至少命中两类参考页面的题目从0增至6/60。由于严格来源哈希不合并等价法规形式，这些数值不代表“只有3.89%的法规相关”，也不代表穷尽相关证据召回率。')
    rr=[r for r in replay if r['topic']=='ALL' and r['quota']=='10' and r['budget_tokens']=='6000']
    tab('新增原配置回放来源供给与严格目标页面代理',['策略','A/R片段均值','实际tokens','双角色出现','A页覆盖','R页覆盖','角色宏覆盖'],[[r['strategy'],num(r['annual_chunks_mean'],2)+' / '+num(r['regulation_chunks_mean'],2),num(r['reference_tokens_mean'],0),pct(r['has_both_roles_mean']),pct(r['annual_page_coverage_mean']),pct(r['law_page_coverage_mean']),pct(r['macro_page_coverage_mean'])] for r in rr])
    pic(OUT/'retrieval/figures/R3_context_allocation.png','新增来源分配回放。类型同时存在是供给指标，不能替代参考页面覆盖或语义支持。')
    section(d,'6.2 预算配额回放与阶段损失','1800个上下文覆盖五个token上限和三个候选配额，使用与历史相同的候选顺序。原配置120/120逐字复现，说明后续变化来自本轮指定的候选截取与组装，而不是另一个实现。预算增加允许更多整片段进入，但如果目标原文不在保存候选中，仅增加上下文长度不能恢复它。\n在原6000配置中，G2十个候选全部装入，最终法规目标页面仍在53/60题缺失；G1在60/60题中都没有严格命中法规参考页面。因此，至少对这些目标来源—页面键而言，主要差距发生在候选选择阶段，而非默认G2的token组装阶段。若另有等价文本来源获检索，此指标不会计入，需通过独立语义对齐确认。\n这项实验不重新搜索候选池之外的片段，也不生成1800条答案。它能验证同一保存排序的预算敏感性，不能说明改变top-k后重新执行神经检索或重排的端到端效果。高预算回放中的质量推断应停留在证据供给层面；任何回答质量收益仍需要实际生成与独立评分。')
    selected=[r for r in replay if r['topic']=='ALL' and r['quota']=='10' and r['budget_tokens'] in ['1000','2000','4000','6000','8000']]
    tab('新增预算回放 总候选上限10',['策略','参考上限','保留片段','实际tokens','双角色出现','角色宏页覆盖'],[[r['strategy'],r['budget_tokens'],num(r['selected_chunks_mean'],2),num(r['reference_tokens_mean'],0),pct(r['has_both_roles_mean']),pct(r['macro_page_coverage_mean'])] for r in selected])
    pic(OUT/'retrieval/figures/R1_budget_sensitivity.png','新增预算敏感性，总候选上限10。曲线为缓存候选回放，不包含重检索、生成或新人工评分。')
    pic(OUT/'retrieval/figures/R2_topic_page_coverage.png','新增主题分层目标页面覆盖。严格来源哈希匹配不自动合并替代法规文本；数值不是标准片段Recall。')
    # The independently re-executed sparse baseline is added only if completed.
    add_sparse(d,tab,pic)
    section(d,'6.4 结构引用与真实质量的分离','新增结构解析统计G1、G2、G3分别产生868、913、1051条模型自报claims，平均每回答约14.47、15.47、17.81条。带有A和R两类ID的模型论断比例从约2.30%、4.38%增至11.23%。这表明角色提示改变了输出组织，但不能证明新增论断或新增双源连线受到原文支持。\n三条件均未出现无法解析到输入集合的来源ID，说明编号检查能够通过；这与引用语义正确并不是一回事。更多claims还可能来自复合论断拆分粒度不同，或回答更长。本文因此将结构图放在证据使用诊断中，不把它作为角色提示优于G2的质量证据，也不拿supported字段统计“真实性”。')
    tab('新增引用结构代理 仅模型输出结构',['条件','回答数','模型claims数','每回答claims','双角色ID论断比例','未知ID数'],[[r['label'],r['completed'],r['claims'],num(r['claims_per_output'],2),pct(r['dual_role_id_claim_fraction']),r['unresolved_id_n']] for r in q['structural_proxies'][:5]])
    pic(OUT/'quality/citation_structure_proxies.png','新增模型输出结构诊断。claims、支持标签与来源ID同现均为模型自报或语法属性，不是人员语义标签。')
    section(d,'6.5 请求token与延迟','保存日志允许报告最终选取成功调用的prompt、completion、总token及请求延迟，但不包含此前失败请求、检索建库和全部恢复消耗，也不含真实供应商单价。因此本节使用资源用量描述，不报告货币成本优势或端到端响应速度。不同条件运行时的并发、网络和服务负载不相同，不能把延迟差直接归因于模型算法。\n例如，G2的参考上下文比G1短，不等于总生成token按同比例减少，因为推理与回答长度也可能变化。角色提示增加结构化论断后，输出用量可能上升，而量表又未显示稳定增益。对于部署选择，这种开销与可测收益应共同报告，而不是只展示输入token节省。')
    resources=q['selected_attempt_cost'][:5]
    tab('最终选取成功调用的资源均值 非端到端成本',['条件','样本','输入token','输出token','总token','请求秒数中位'],[[r['label'],r['completed'],num(r['prompt_tokens_mean'],0),num(r['completion_tokens_mean'],0),num(r['total_tokens_mean'],0),num(r['elapsed_seconds_median'],1)] for r in resources])
    pic(OUT/'quality/selected_attempt_resource_profile.png','新增选取成功调用的资源剖面。点为中位数，线为四分位区间，并非95%置信区间；邻表token列为均值。失败调用与检索建库不计入，跨条件并发不可完全控制。')
    section(d,'6.6 真实案例与分歧分析','案例按已观察分差事后选择，不具有随机代表性。正向案例为科大讯飞审计委员会题，两人均将法规项由1提高到2，对应G1=7、G2=8、G3=8；复核说明指出G1没有R类法规原文。该案例与来源供给不足的解释一致，但不是对全部题目因果机制的证明。\n保利发展分红题则体现角色提示的风险与评分分歧。G3的原文含“□适用 √不适用”到“报告期内未形成并实施”的扩展表述，人员1认为把预案项目不适用推成未实施，给事实0及不确定性1；人员2维持事实2及法规1。这里必须保留分歧，不能把人员1的说明写成全体一致的错误裁定。\n美的审计委员会题三个条件均8分，两人四维全满，示范的是量表持平而非所有论断完全等价；恒瑞内控题G3小幅改善来自人员1引用项变化，事实项仍不满分，人员2总分不变。案例说明为什么总分、人员差异和原文支持需要一起阅读。')
    cases=load('quality/qualitative_cases.json')['cases']
    case_rows=[]
    for case in cases:
        chosen=case['outputs'][-1]
        case_rows.append([case['question_id'].replace('HOLDOUT-',''),f"{case['total_mean_G1']}/{case['total_mean_G2']}/{case['total_mean_G3']}",chosen['excerpt_verbatim'][:90].replace('\n',' '),','.join(chosen['source_ids'][:8])])
    case_table=tab('事后真实案例 G1/G2/G3均分与G3正文逐字节选',['问题','三条件分数','G3正文节选','G3引用ID节选'],case_rows)
    case_table.autofit=False
    for j,width in enumerate([3.7,1.9,7.7,3.5]):
        case_table.columns[j].width=Cm(width)
        for row in case_table.rows:row.cells[j].width=Cm(width)
    prior.p(d,'完整120字符节选、两位人员分项分值、原始响应文件与SHA256及复核说明字段保存在随稿案例清单。此表引文为实际response.evaluation的前段，不补写省略的结论；引用ID列仅列出实际引用的部分ID。')
    prior.h(d,'7 讨论与有效性限制')
    for title,text in DISCUSSION:section(d,title,text)
    prior.h(d,'8 结论')
    prior.p(d,'本文完成年报与法规双源RAG的受控比较，并在原有双人评分基础上新增1800个预算配额回放、严格来源页面诊断、维度与主题分解、评分者尺度检查以及完整样本与缺失敏感性。结果支持当前任务中按来源组织证据的价值：G2相对G1的已观测配对质量分差为正，两类资料缺失都会降分。但相同上下文下来源角色提示没有稳定增益，完整配置未普遍优于简单基线。')
    prior.p(d,'新增分析同时揭示，来源类型更平衡并不意味着目标证据覆盖全面改善；法规参考页面的可审计定位仍是明显短板，且人员评分在法规尺度与满分维度上存在限制。这些发现将方法结论限定为探索性任务内结果。本文不据此宣称解决法规时点适用、获得跨模型族泛化或验证公司真实治理质量，也不将固定双路流程改称多智能体系统。')
    prior.h(d,'数据与代码可用性')
    prior.p(d,'可复现分析脚本、聚合结果、回放明细、图表原始数据及输入哈希清单保存于项目材料。论文公开仓库地址与原文件再分发范围尚未确定，不虚构公开链接。原始文件、评分与运行记录保留，公开时应按其真实授权处理。')
    prior.h(d,'参考文献')
    for i,(s,u) in enumerate(REFS,1):prior.p(d,f'[{i}] {s} {u}')
    prior.h(d,'附录A 回放与审计复现说明')
    prior.p(d,'历史设置冻结文件为results/runs/paper_execution_freeze_windows_20261020_01/execution_freeze.json，SHA256为f0eecd3e4f7f129364311b2daa86d0e2ca6aad6af57ac269a14c210be3ffc2c7。原始主结果不因本次新增分析覆盖。新增回放、稀疏检索与评分诊断分别保存在本稿目录下retrieval、quality和audit中，运行脚本及输入哈希列入交付清单。')
    prior.p(d,'执行核验包括：400个计划源文件身份、386条评分输出的3088个原始字段、原配置120个上下文逐字一致、参考证据123个来源哈希—页面键的索引可用性，以及图表数据与生成脚本。评分者在正文仅以人员1、人员2表示；案例保留分歧，不新增裁定。新增后验分析不回溯称为预注册。')
    prior.h(d,'附录B 写作与投稿状态')
    prior.p(d,'本稿为中文研究长稿，含英文题名与摘要。作者、单位、基金、利益冲突、CRediT与AI辅助写作披露须按真实情况补齐。采用可编辑单栏版式，不复制期刊刊头；分区及录用取决于贡献与评审，篇幅和图表数量不能保证接收。')
    # Consistently distinguish the mixed PDF-page / whole-TXT source-location proxy.
    replacements={
      'average exact source-and-page coverage':'average reference-location coverage',
      '两者默认思考预算不同':'两者未显式统一思考预算，默认值未核实',
      '不同服务默认思考预算使版本比较存在计算条件混杂':'未统一的服务思考预算使版本比较存在潜在计算条件混杂',
      '默认思考预算和未核实底层revision':'未显式统一的思考预算和未核实底层revision',
      '默认思考预算不同':'思考预算未显式统一',
      '默认思考预算未显式统一':'思考预算未显式统一',
      '同系列K3与K2.8服务别名具有不同的未显式统一的思考预算和未核实底层revision':'同系列K3与K2.8服务别名未显式统一思考预算，且底层revision未核实',
      'R页覆盖':'R定位覆盖',
      '法规参考页面':'法规参考位置','法规目标页面':'法规目标位置','法规页面':'法规定位',
      '目标页面覆盖':'目标定位覆盖','目标页面':'目标位置','严格来源页面诊断':'严格来源定位诊断',
      '严格来源哈希与页面覆盖':'严格来源定位覆盖','角色宏页覆盖':'角色宏定位覆盖',
      '123/123目标来源哈希和页面在索引中存在':'122条PDF参考与1条TXT参考的定位均在索引中存在',
      '123个来源哈希—页面键':'123条参考来源位置',
      '新增实验完成1800个预算与配额上下文回放':'新增实验完成1800个缓存预算配额回放与600个新BM25上下文',
      'Additional experiments replay 1,800 context configurations over token caps and candidate quotas':'Additional experiments replay 1,800 cached configurations and execute 60 fresh BM25 queries over 600 context configurations',
    }
    for pp in d.paragraphs:
        if pp.text.startswith('年报作用域D_A(c,y)'):
            pp.text+='本轮60题均没有提供独立事项日期，系统不从2024报告年度推断日期，全部5994个法规片段按unknown=retain保留，时点排除数为0。因此不能把本轮结果归因于有效时点过滤。'
        if pp.text.startswith('稠密与BM25信号使用固定配置融合'):
            pp.text+='具体实现先各召回2×top-k，在各通道返回集合中除以该通道最大分数（最大值为0时以1代替），对并集用0.7/0.3加权，再取最多4×top-k进入重排，重排max_length为3072。实际候选数受通道并集大小限制；此处为最大值归一化而非min-max归一化。'
        if pp.text.startswith('位置指标首先'):
            pp.text='定位指标按参考来源的真实形式计算：122条PDF参考使用文件SHA256与物理页序，1条LAW-DOC004-TEXT参考没有物理页，按整个TXT来源哈希定位，并在20个内控问题中复用。分别计算每题两类来源的参考位置覆盖，再取角色均值。双角色出现率只检查A/R片段同时存在；双参考角色可用率要求两类各至少命中一条参考位置。这些均是非语义代理。法规汇总混合了页级和整来源粒度，本文另报告PDF-only与TXT-only结果，避免把粗粒度命中解释成更精准的法规检索。'
        for a,b in replacements.items():
            if a in pp.text:pp.text=pp.text.replace(a,b)
    for tt in d.tables:
        for row in tt.rows:
            for cell in row.cells:
                for pp in cell.paragraphs:
                    for a,b in replacements.items():
                        if a in pp.text:pp.text=pp.text.replace(a,b)
    dest=OUT/'年报与法规双源RAG_大幅修订研究长稿.docx';d.save(dest)
    alltext='\n'.join(p.text for p in d.paragraphs)
    stats={'docx':str(dest),'paragraphs':len(d.paragraphs),'tables':len(d.tables),'figures':len(d.inline_shapes),'references':len(REFS),'cjk_characters_in_body_paragraphs':len(re.findall(r'[\u4e00-\u9fff]',alltext)),'nonspace_characters_in_body_paragraphs':len(re.sub(r'\s','',alltext)),'word_count_not_equivalent_to_english':True,'new_context_replays':1800}
    (OUT/'manuscript_inventory.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(stats,ensure_ascii=False))
    return d

def add_sparse(d,tab,pic):
    section(d,'6.3 新执行的BM25基线与定位粒度敏感性','为避免只对已有结果重画图，本文新增运行同范围的CPU BM25检索。使用项目原BM25与jieba实现，k1=1.5、b=0.75；IDF在完整19367片段上拟合，与原混合检索组件一致。返回候选仍排除335个旧版本片段，只在19032个合格片段中选择，年报按公司与年度约束。公开问题直接用作查询，排名ID在读取参考答案之前落盘，防止以参考引文构造有利查询。\n60条问题均完成merged与dual两种检索，每个排序在五种预算下组装，产生600个新上下文。此处是新执行的稀疏检索，不是缓存神经排序的再截取；同样没有调用生成器，因此不能拿它替代先前人工评分的BM25生成条件，也不能把两套BM25条件的数据直接拼成一次端到端实验。')
    rows=[r for r in csvrows('retrieval/baseline_vs_cached_at6k.csv') if r['topic']=='ALL']
    tab('新BM25与缓存混合重排在6000上限的来源定位代理',['检索来源','策略','A定位覆盖','R定位覆盖','双参考角色','实际tokens'],[[('新BM25' if r['method']!='cached_hybrid_rerank' else '缓存混合重排'),r['strategy'],pct(r['annual_reference_location_coverage']),pct(r['law_reference_location_coverage']),pct(r['both_reference_roles_available_fraction']),num(r['mean_reference_tokens'],0)] for r in rows])
    paras(d,'表面上，新BM25的法规位置覆盖达到30.00%和33.33%，高于缓存混合重排。但逐粒度拆分后，这一改善完全来自整份TXT来源匹配：内控20题中，BM25合并和双路分别命中18/20和20/20个来源；而在40个PDF法规参考问题上，两个BM25策略的页级覆盖均为0，缓存双路为5.83%。因此，汇总代理的提高主要反映定位粒度与文档身份，不是BM25已经实现更精确的法律段落检索。\n这一敏感性实验说明，在混合文档形态的RAG评测中，页级与源文件级标注不能无说明地放在一个“检索准确率”中。整份法规文件被检索到，比没有该文件更有利，但不保证返回片段位于相关条文，也不能证明适用版本正确。对于来源单位不同的指标，应保持拆分结果，以免系统因命中较粗的标签而显得更优。')
    tab('法规定位粒度拆分 不同分母不得直接比较',['方法','策略','PDF-only 40题页覆盖','TXT-only 20题来源命中'],[['缓存混合重排','merged','0.00%','0 / 20'],['缓存混合重排','dual','5.83%','0 / 20'],['新BM25','merged','0.00%','18 / 20'],['新BM25','dual','0.00%','20 / 20']])
    paras(d,'作为替代来源敏感性补充，去除来源身份限制后的法规参考引文12字符词面覆盖，在缓存G1/G2中分别为0.59%与11.88%；G2有33题虽然严格参考位置未命中，但在其他来源或页面出现部分参考措辞。例如规范复述、修订决定与正文重复，都可能导致这种现象。词面重叠不证明法规等价、版本相同或具体论断受支持，因此它只提示严格定位可能漏计替代材料，不能把两种指标加总成语义正确率。\n本次对照仍受组件条件限制：缓存混合结果来自已保存神经候选，而新BM25重新执行稀疏检索；没有同时重跑完整神经链。已有模型revision与原始查询保持记录，供未来在相同机器和同次执行中复核。当前实验的作用是揭示指标、定位粒度与来源供给的关系，不据此宣称一种完整系统胜出。')

if __name__=='__main__':
    if '--build' in sys.argv:build()
    else:
        for i in range(1,4):schematic(f'fig{i:02d}_schematic',i)
        print('Static sections and schematic figures prepared; run final builder after analysis outputs are complete.')
