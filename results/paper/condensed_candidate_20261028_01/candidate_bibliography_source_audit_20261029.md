# 当前主稿参考文献与引文范围核查

核查日期：2026-10-29
候选稿：`年报与法规双源RAG_统一主文_跨模型与Agent年度分层复算候选稿_待终审.docx`
本轮书目修订后 SHA-256：`ae92ac0ad0e150ec52366ef9bddc93622a9e6efc6db825d67777f71b3b553d9a`

## 核查范围与结论

从 DOCX 正文和文末参考文献逐项抽取并核对：书目编号为连续的 `[1]`–`[31]`，正文出现全部 31 个书目编号，未发现未引用条目或无对应书目的编号。涉及年份、作者、刊名/会议、卷期、页码或文章号及 DOI 的学术条目，按出版方、会议论文集、ACL Anthology、NeurIPS、arXiv 或论文官方项目页核对；法规和公司年报使用证监会及巨潮资讯网原始来源。

本审计核对了书目身份及当前正文中与其相连的有限描述，不是对 31 篇论文全文逐句重读，也不是对本文全部方法、实验数据或 355 份回答的事实审查。没有新增模型调用或人工标注；没有独立金标准的质量指标仍保持未测。

## 参考文献来源核查

| 编号 | 原始来源 | 核对内容及正文对应范围 |
|---|---|---|
| [1] | [NeurIPS 2020](https://proceedings.neurips.cc/paper/2020/hash/6b493230-Abstract.html) | RAG 将参数记忆与非参数检索记忆结合；支持知识密集任务背景，不支持本文具体效果。 |
| [2] | [ACL Anthology: FinQA](https://aclanthology.org/2021.emnlp-main.300/) | 金融报表数值推理数据集及其专家编写问答、推理程序；本文只称其聚焦金融数值推理。 |
| [3] | [ACL Anthology: TAT-QA](https://aclanthology.org/2021.acl-long.254/) | 金融表格与文本混合问答任务；与本文联合披露/法规评价的任务边界区分合理。 |
| [4] | [ACL Anthology: HiREC](https://aclanthology.org/2025.findings-acl.855/) | 分层检索、证据整理、补充查询及 LOFin 数据规模与问答数；正文仅概括其标准化金融文档检索贡献。 |
| [5] | [Knowledge-Based Systems 出版页](https://www.sciencedirect.com/science/article/pii/S095070512401044X) | 工程设计知识 RAG：从专利描述提取显式事实并构建可检索知识；正文概述与摘要及结论一致。 |
| [6] | [Knowledge-Based Systems 出版页](https://www.sciencedirect.com/science/article/pii/S0950705125005490) | LLM 与知识方法综述；书目刊年、卷号和文章号与出版页一致。 |
| [7] | [Now Publishers 原始 PDF](https://www.nowpublishers.com/article/DownloadEBook/INR-019)；[DOI 出版页](https://doi.org/10.1561/1500000019) | **本轮更正。** 原始论文 PDF 首页及出版方推荐引文写作 *Foundations and Trends in Information Retrieval*, 3(4), 2009, 333–389。DOI 着陆页另显示 4(1–2), 1–174；为避免把着陆页的替代编目与原论文首页混成一个书目，本稿按原文首页/推荐引文改为 3(4), 333–389。DOI 不变。正文关于 BM25 的概述范围有限。 |
| [8] | [ACL Anthology: Dense Passage Retrieval](https://aclanthology.org/2020.emnlp-main.550/) | 稠密双编码器检索及论文元数据；支持正文将 DPR 作为稠密检索代表。 |
| [9] | [arXiv: Qwen3 Embedding](https://arxiv.org/abs/2506.05176) | 论文题名、作者、年份以及嵌入/重排任务与预印本一致；正文没有把其公开基准结果当作本项目结果。 |
| [10] | [ACM DOI 记录](https://doi.org/10.1145/1571941.1572114) | RRF 论文题名、SIGIR 2009、页码 758–759 与 DOI；正文仅称其为基于名次的融合思路，并明确本轮未运行 RRF。 |
| [11] | [Information Sciences 出版页](https://www.sciencedirect.com/science/article/pii/S002002552600112X) | 2026 年文章号 123181；摘要涉及查询时增强与入库时增强、教育语料缩写检索。正文未将该领域结果外推为本文结果。 |
| [12] | [ICLR 2024 正式论文集](https://proceedings.iclr.cc/paper_files/paper/2024/hash/25f7be9694d7b32d5cc670927b8091e1-Abstract-Conference.html)；[arXiv 预印本](https://arxiv.org/abs/2310.11511) | 自适应检索与自反思机制；书目以 2024 ICLR 形式引用，摘要和出版身份相符。 |
| [13] | [arXiv: Corrective Retrieval Augmented Generation](https://arxiv.org/abs/2401.15884) | 检索质量评估、纠错路由和补充检索描述与预印本摘要相符；书目保守标为 arXiv。 |
| [14] | [ACL Anthology: Adaptive-RAG](https://aclanthology.org/2024.naacl-long.389/) | 按问题复杂度自适应选择检索策略；会议、年份、页码、DOI 已核对。 |
| [15] | [Neurocomputing 出版页](https://www.sciencedirect.com/science/article/pii/S0925231225029443) | AIR-RAG 文章号 132272、卷 666、2026 年正式出版信息；正文仅概括其迭代检索研究。 |
| [16] | [arXiv: ReAct](https://arxiv.org/abs/2210.03629) | 交错组织推理与动作的概述；v3 标为 ICLR camera-ready，支持正文的实现边界对照。 |
| [17] | [Knowledge-Based Systems 出版页](https://www.sciencedirect.com/science/article/pii/S0950705125000991) | CoLE 的法律专家提示框架与刊载信息；正文没有将其误称为本文已实现的多智能体基线。 |
| [18] | [Neurocomputing 出版页](https://www.sciencedirect.com/science/article/pii/S0925231224018344) | MADKE 通过共享知识池支持多智能体辩论的描述与摘要一致；卷号、年份及文章号已核对。 |
| [19] | [ACL Anthology: ALCE](https://aclanthology.org/2023.emnlp-main.398/) | 自动引文评测的流畅度、正确性及引用质量维度；正文对“答案与引用质量”的概括有据。 |
| [20] | [ACL Anthology: RAGAs](https://aclanthology.org/2024.eacl-demo.16/) | RAGAs 描述检索上下文、忠实利用与生成质量，并提供自动化指标；正文概括为自动化评价方法。 |
| [21] | [NeurIPS 2024 RAGChecker](https://proceedings.neurips.cc/paper_files/paper/2024/hash/27245589131d17368cccdfa990cbf16e-Abstract-Datasets_and_Benchmarks_Track.html) | 检索与生成两侧的细粒度诊断框架；正文表述与论文摘要相符。 |
| [22] | [arXiv: LegalBench-RAG](https://arxiv.org/abs/2408.10343) | 法律 RAG 检索基准强调精确、最小文本片段；书目保持预印本身份，没有将其描述为答案生成评价。 |
| [23] | [ACL Anthology: Lost in the Middle](https://aclanthology.org/2024.tacl-1.9/) | 长上下文中证据位置影响模型利用能力；TACL 卷 12、页 157–173、DOI 已核对。 |
| [24] | [Kimi Code 模型配置](https://www.kimi.com/help/kimi-code/models) | 2026-10-29 当前页面列出 `k3`、`k3-256k`、`kimi-for-coding` 和高速版；其中 `kimi-for-coding` 对应 K2.8 Preview，默认档位为 `max`，K3 默认 `high`。这确认当前文档状态；历史 2026-10-20/23 页面快照不可由当前网页独立重建。已有请求记录仍不包含 `reasoning_effort`，响应也没有独立可核验的服务端档位或 checkpoint revision。 |
| [25] | [中国证监会：第182号令](https://www.csrc.gov.cn/csrc/c101864/c2ee1a791fddc4f5ebeeb70aa8e2399cf/content.shtml)；[第226号令](https://www.csrc.gov.cn/csrc/c101953/c7547359/content.shtml) | 法规身份、公告与施行日期按官方文件核对；“历史索引/候选”结论另由仓库中带哈希的冻结索引审计支持，不表示法律适用性。 |
| [26] | [中国证监会：第62号公告](https://www.csrc.gov.cn/csrc/c101954/c7449659/content.shtml)；[第6号公告](https://www.csrc.gov.cn/csrc/c101954/c7547791/content.shtml) | 文号、标题、公布/施行日期按官方公告核对；不得据此单独判断某事项适用版本。 |
| [27] | [中国证监会：第29号公告](https://www.csrc.gov.cn/csrc/c101864/c1024585/content.shtml)；[第18号公告](https://www.csrc.gov.cn/csrc/c101954/c7589726/content.shtml) | 2018 与 2025《上市公司治理准则》的官方身份与时间信息；索引范围结论仍受正文中明确的检索边界限制。 |
| [28] | [ACL Anthology: ARQA](https://aclanthology.org/2026.eacl-industry.63/) | EACL Industry Track 元数据、页码 847–868、约 2.5K 年报问答、专家审阅及确定性核验信息；正文摘要与官方条目一致。 |
| [29] | [LREC Proceedings: CFQA](https://lrec.elra.info/lrec2026-ws-fnp-03)；[ACL Anthology](https://aclanthology.org/2026.fnp-1.3/) | 50 家公司、2023–2025 年报、500 题、人工标注与原文依据、RAG/无检索对照及页码 28–38；正文概括与正式条目一致。 |
| [30] | [Engineering Applications of Artificial Intelligence 出版页](https://www.sciencedirect.com/science/article/abs/pii/S0952197626009528) | 中文金融事件知识图谱 RAG 的题名、卷 175、文章号 114670 及方法概述；专项全文/出版元数据结论见同目录 CFinRAG 审计。 |
| [31] | [巨潮资讯网原始年报 PDF](https://static.cninfo.com.cn/finalpage/2025-04-26/1223326862.PDF) | 公司名称、报告年度及公开日期；案例段的会议记录冲突按整份年报审计处理，不据该案例作合规判断。 |

## 正文引文主张核对

- 相关工作段的 [19]–[21] 已在当前版本重新核对：ALCE 评答案及引用，RAGAs 分别涉及检索上下文、忠实度和生成，RAGChecker 诊断检索与生成。当前稿将跨框架综合限定为“提示”，没有宣称任一框架验证了本文指标。
- 法规段的 [25]–[27] 结合官方公告与本地审计：历史第182号令 PDF 在冻结索引内但未出现在保存的候选排序；DOC343 的官方 PDF 含修改决定与后续重新公布文本，保存的 G2 七条命中均在物理第2页。正文已把这些写成索引/候选观察，不解释为语义支持或法律适用。
- Agent 段的 `[0,1]` 是未观测结果的数值界，不是参考文献 `[1]`。正文其他位置已正常引用 [1]。
- 其余引文概述均按表中来源身份和摘要/官方公告范围核对；本核对不把论文摘要等同于完整方法复现。

## [7] 更正和版面核验

当前稿将 [7] 改回原论文首页及出版方推荐引文所示 `3(4), 2009: 333–389`。出版方 DOI 着陆页另列 `4(1–2): 1–174`；本次采用原文首页的期刊卷期与页码，避免混合两种编目呈现。仅 `word/document.xml` 中该条书目文字变化；重渲染保持 23 页，只有第 21 页图像不同，其余 22 页 PNG 与修改前候选逐字节一致。修改页已在原始分辨率目视检查；渲染使用 Codex `render_docx.py`、LibreOffice 和 Poppler，未使用 WPS。

重绑定与页面哈希见同运行目录 `candidate_citation_rebind.json`。该收据确认当前稿文件哈希、31 条书目、正文编号覆盖、修订差异和渲染范围。

## 边界

这项核查没有独立评定 355 份回答的事实正确性、引用是否语义蕴含答案或法规的具体时点适用，也没有重新验证全部实验代码、作者信息或目标期刊模板。它不能证明二区录用水平。项目不新增人工标注；缺少匹配且独立可信参考时，相关质量指标继续保持未测。
