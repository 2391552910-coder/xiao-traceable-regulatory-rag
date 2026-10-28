# 年报与法规双源检索增强生成

## 最新候选：来源页码记录边界澄清（2026-10-29）

- 当前主文候选：[页码分层核验修订稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_页码分层核验修订候选稿_待终审.docx)。修订第38段：检索索引使用PDF物理页序；人工核验时另记可见印刷页码，避免暗示运行索引普遍存储印刷页码。
- 主文仍为21页、12表。WPS重渲染后仅第5页变化并已检查。详见[修订审计](results/paper/condensed_candidate_20261028_01/page_provenance_revision_audit_20261029.md)和[哈希/渲染收据](results/paper/condensed_candidate_20261028_01/page_provenance_revision_receipt_20261029.json)。
- 本修订只处理来源定位表述，不代表整稿终审、期刊格式适配或二区录用结论。

## 历史父稿：引言检索表述收窄（2026-10-28）

- 引言表述收窄父版本：[引言检索表述收窄稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_引言检索表述收窄候选稿_待终审.docx)，SHA-256 `76bca23f53ffac54da086f908397cae56b94586e43c6cc142734c10d12fedf0a`。只收窄引言中对传统检索的泛化陈述；BM25文献更正保留。该次仅正文段落10变化，12张表、31条参考文献及其他段落不变；WPS渲染21页，仅第2页变化且已检查。
- 配套核查：[引言第9–14段审计](results/paper/condensed_candidate_20261028_01/introduction_claim_audit_paragraphs_9_14_20261028.md)、[方法与检索文献审计](results/paper/condensed_candidate_20261028_01/retrieval_method_claim_audit_paragraphs_23_24_20261028.md)、[评分量表审计](results/paper/condensed_candidate_20261028_01/rubric_claim_audit_current_candidate_20261028.md)及[版本/渲染收据](results/paper/condensed_candidate_20261028_01/intro_retrieval_framing_revision_receipt_20261028.json)。研究范围及已发表论文参照见[范围决策](docs/文献参照后的论文范围决策_20261028.md)。
- 本稿仍待整稿语义终审、作者/投稿信息和目标期刊格式适配；不表示达到二区录用水平。

## 2026-10-28 回放范围限定修订候选（历史父版本）

- 回放范围限定父版本：[回放范围限定修订稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_回放范围限定候选稿_待终审.docx)，SHA-256 `dd442f55b34faec6b31a330578ed55df66918e8c719aeec22304e49608c2be91`。将讨论段回放陈述限定为一个问题、8种检索配置、16次成功候选检索的通道候选/融合/最终排序算术核验，并明确其不验证语义相关性、主实验全量可回放性或人工复核效益。没有新增模型调用或人工标签。WPS渲染21页；仅第17页变化并完成视觉复核，其他20页与上一版像素一致。版本及渲染见[修订收据](results/paper/condensed_candidate_20261028_01/replay_scope_revision_receipt_20261028.json)。
- 来源删除配对分析、量表和检索诊断补充材料、英文工作译稿及其证据状态见下方历史候选条目和各自收据；当前稿仍需整稿终审及目标期刊模板适配，不代表已达到二区录用标准。
- [当前候选稿引文版本绑定核查](results/paper/condensed_candidate_20261028_01/current_candidate_citation_rebind_20261028.json)确认当前版44个引文段落、31条参考文献及其编号与已审计来源版本连续；这是版本与编号核验，继承分主题来源审计，不等于逐篇重读全部文献或全稿语义终审。
- [相关工作段落20来源核查](results/paper/condensed_candidate_20261028_01/related_work_claim_audit_paragraph_20_20261028.md)依据ACL Anthology和出版社正式记录核实ARQA、CFQA及CFinRAG的数据规模与方法概述；当前段落与来源相符，无需改稿。该核查不把它们当作本项目的直接基线。
- [相关工作段落19来源核查](results/paper/condensed_candidate_20261028_01/related_work_claim_audit_paragraph_19_20261028.md)依据ACL Anthology正式记录核实FinQA、TAT-QA与HiREC的任务定位；描述均有来源支持，未发现需要改稿的事实错误。

## 2026-10-28 评分量表修订前的统一主文候选稿（已被后续候选取代）

- [英文工作译稿](results/paper/english_translation_current_20261028_01/Controlled_Evaluation_Dual_Source_RAG_English_Working_Translation_copyedited_20261028.docx)由当前中文主稿（SHA-256 `072eac78ae934c17789e670b0a4864e095b87c350f9cbc4091d74dc31deaf18f`）翻译生成，保留12张表、8幅图和31条参考文献；[英文 Markdown 源稿](results/paper/english_translation_current_20261028_01/English_working_translation_current_20261028.md)、[本轮修订与逐页视觉核验收据](results/paper/english_translation_current_20261028_01/english_copyedit_receipt_20261028.json)、[近期文献元数据核查](results/paper/english_translation_current_20261028_01/recent_reference_metadata_audit_20261028.md)及[23页渲染 PDF](results/paper/english_translation_current_20261028_01/rendered_copyedited_20261028/paper_native.pdf)一并保存。已修整统计术语和少量语序，数字、表格、图片及实验结论未变；新候选版23页逐页检查通过。此轮语言润色不等同于母语编辑或逐条论断—引文终审。稿件仍需目标期刊格式适配及作者投稿信息，不能视为投稿定稿或二区录用证明。
- 当前主文为[工程价值措辞校准候选稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_工程价值措辞校准候选稿_待终审.docx)，SHA-256 `072eac78ae934c17789e670b0a4864e095b87c350f9cbc4091d74dc31deaf18f`，21页、12表、8图、31条参考文献。该版承接前一版的CFinRAG相关工作修订；本次只校准讨论段落131，将未实测的“独立工程价值”改为可追溯能力，并明确未测量复核正确率或成本。表格、图片、引文和实验数据未变。WPS重渲染仅第17页变化并已检查；其余20页与前版像素一致。[本次修订收据](results/paper/condensed_candidate_20261028_01/semantic_claim_revision_receipt_20261028.json)；[当前版本、引文编号和主要数字一致性复核](results/paper/condensed_candidate_20261028_01/current_candidate_integrity_rebind_20261028.json)确认该版只改段落131、31条参考文献均在正文中引用，旧主效应数字未残留。配套补充材料为[预算回放与BM25定位诊断稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_精简补充材料_预算与BM25检索诊断候选稿_待终审.docx)，SHA-256 `d6435f6ea5d787040012da0b3655040f3171443abc8bf592701ad53235882007`。 修订仅澄清补充表S3的分母：PDF页级覆盖为7/120个目标定位（5.83%），非7/40题；TXT来源命中按20题统计。分析值未变，三页WPS复渲染已检查；[补充材料修订收据](results/paper/condensed_candidate_20261028_01/supplement_denominator_revision_receipt_20261028.json)及[新渲染PDF](results/paper/condensed_candidate_20261028_01/render_supplement_denominator_revision_20261028/paper_native.pdf)。
- [交叉引用与摘要口径合并收据](results/paper/condensed_candidate_20261028_01/crossref_abstract_scope_merge_receipt_20261028.json)绑定源稿及候选稿哈希、WPS PDF和21页渲染；前三页已目视检查，第4–21页与新鲜重渲染源版像素一致。此前基于推理预算版生成的[摘要口径候选稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_推理预算与摘要口径修订候选稿_待终审.docx)未包含较新的正文交叉引用修订，已由收据标记为过时来源版本，保留追溯。
- [交叉引用补全候选稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_交叉引用补全候选稿_待终审.docx)是本次源稿；其[交叉引用审计收据](results/paper/condensed_candidate_20261028_01/cross_reference_audit_20261029.json)与[推理预算论断审计收据](results/paper/condensed_candidate_20261028_01/reasoning_budget_claim_audit_20261029.json)记录继承的正文修订和解释边界。整稿事实/引文语义终审、作者元数据及目标期刊格式仍未完成，不能声称达到二区录用标准。
- [检索与金融QA引文审计](results/paper/condensed_candidate_20261028_01/retrieval_corpus_citation_audit_20261028.md)、[年报QA基准引文审计](results/paper/condensed_candidate_20261028_01/annual_report_benchmark_citation_audit_20261028.md)和[RAG方法与评测引文审计](results/paper/condensed_candidate_20261028_01/rag_method_eval_citation_audit_20261028.md)分别覆盖其记录中的引文主张，但绑定较早稿件版本；[CFinRAG专项引文核查](results/paper/condensed_candidate_20261028_01/cfinrag_citation_audit_20261028.md)已补入新增的中文金融多源RAG研究；旧的[1]–[29]审计仍只覆盖各自记录的文献范围，不能代替对新候选的整稿语义终审。作者元数据及目标期刊格式仍未完成，不能声称达到二区录用标准。
- [当前主文法规版本来源核验](results/paper/condensed_candidate_20261028_01/current_candidate_regulatory_source_audit_20261028.md)绑定前一版CFinRAG相关工作候选稿；本次只改段落131，法规段落146保持不变，既有官方日期与版本风险核验继续适用。核验说明采集清单中DOC333仅有元数据、对应正文文件缺失。旧[官方来源审计](results/paper/condensed_candidate_20261028_01/official_source_claim_audit_20261028.md)对应更早的精简主文候选稿及保利发展案例，不是当前统一主文的收据。
- [交叉引用审计收据](results/paper/condensed_candidate_20261028_01/cross_reference_audit_20261029.json)记录源稿哈希、段落修订及渲染核查；WPS只读渲染21页，变化页11、13、16–18已复查，没有发现裁切、重叠或版面错位。整稿事实/引文语义终审、作者元数据及目标期刊格式仍未完成，不能声称达到二区录用标准。
- [参考文献[13]出版状态与排版复核](results/paper/condensed_candidate_20261028_01/reference_13_citation_render_audit_20261028.json)记录上一候选稿中的单项书目修订：主会日程为2026-11-06至2026-11-08，故标作待刊；ACL Anthology正式论文编号、页码和DOI尚未核实。该稿第19页排版已检查；其后G2方法段修订后的完整渲染见检索实现对照收据。
- [方法与冻结协议对照](results/paper/condensed_candidate_20261028_01/method_protocol_audit_20261028.json)核对了10项可机器判定的运行设置；[检索实现对照](results/paper/condensed_candidate_20261028_01/retrieval_implementation_audit_20261028.json)再将候选合并、整块预算跳过和G2/G3上下文关系与冻结代码核对。9项实现事实通过；这些检查不代表整篇方法和数据语义终审已完成。 [当前候选稿方法论断版本绑定收据](results/paper/condensed_candidate_20261028_01/current_candidate_method_claim_rebind_20261028.json)进一步确认上述审计涉及的9个方法/协议段落与当前候选稿逐段哈希一致；它是版本连续性核查，不等同于重跑代码审计或质量评测。
- [推理预算论断审计收据](results/paper/condensed_candidate_20261028_01/reasoning_budget_claim_audit_20261029.json)记录原始请求、供应商身份说明的哈希及限制：请求未发送 `reasoning_effort`，服务端实际档位及底层 checkpoint revision 无法独立验证，因此服务别名结果不解释为等预算权重比较或跨厂商泛化。
- [本版数字核对](results/paper/condensed_candidate_20261028_01/numeric_content_audit_20261028.json)、[叙述量化复核](results/paper/condensed_candidate_20261028_01/narrative_quantitative_audit_20261028.json)与[表12摘录及摘要复核](results/paper/primary_provider_candidate_20261028_01/current_candidate_claim_audit_20261028.json)对应继承的合并主文内容；完整审计边界及其原始候选稿哈希见各收据。前版[合并法规及非因果修订候选稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_合并法规及非因果修订候选稿_待终审.docx)保留作版本追溯。聚焦稿中的386/400和+0.250已被供应商重分析取代，不可作为当前结果。
- [统计复核](results/paper/condensed_candidate_20261028_01/numeric_content_audit_20261028.json)、[叙述量化复核](results/paper/condensed_candidate_20261028_01/narrative_quantitative_audit_20261028.json)与[表12摘录及摘要复核](results/paper/primary_provider_candidate_20261028_01/current_candidate_claim_audit_20261028.json)记录当前稿的主要数字与摘录来源。其前身[更正统计及摘要、表12修订候选稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_更正统计及摘要表12修订候选稿_20261028.docx)保留作版本追溯，不再标为当前稿。聚焦稿中的386/400和+0.250已被供应商重分析取代，不可作为当前结果。
- [正文数字与证据供给叙述审计](results/paper/condensed_candidate_20261028_01/narrative_numeric_claim_audit_20261028.json)将355/400范围、主要配对效应及缺失界、来源共现和位置覆盖对应到原分析文件；审计范围不含355条回答的完整语义复核或法规时点适用性验证。
- [当前法规来源核验](results/paper/condensed_candidate_20261028_01/current_candidate_regulatory_source_audit_20261028.md)原绑定于前一版CFinRAG候选稿；本次仅修改段落131，法规段落146未变，故沿用其限定范围内的官方日期与活动清单口径核查。
- [摘要版本差异审计](results/paper/condensed_candidate_20261028_01/current_candidate_delta_audit_20261028.json)记录摘要修订版相对其父稿仅正文段落3、6变动；其后方法段45单独修订，见上方方法修订审计。12张表格单元格与21个嵌入媒体资源哈希仍一致。该差异核对不替代全文语义审查。
- [当前摘要论断核验](results/paper/condensed_candidate_20261028_01/abstract_claim_alignment_current_candidate_20261028_v3.json)绑定当前主文哈希，核对中英文摘要的样本数、配对效应与区间、缺失界、来源同现、位置覆盖及G3上下文控制口径；6项检查通过。该收据不等于全稿语义审核，也不验证答案正确性或语义检索召回。 [当前版本绑定收据](results/paper/condensed_candidate_20261028_01/current_candidate_abstract_rebind_20261028.json)确认两段摘要文本哈希与该专项核对稿相同，并把计算输入哈希绑定到fa128候选稿；只覆盖摘要，不代替全稿审核。
- [当前主稿版本与引文连续性审计](results/paper/condensed_candidate_20261028_01/current_candidate_audit_bridge_20261028.json)确认表1–11与统计底稿逐格一致、表12与摘录核验底稿逐格一致；当前正文引用[1]–[31]均有对应条目且均被引用，参考文献编号完整性与已覆盖范围内的来源审计连续性通过。HiREC措辞、CRAG预印本书目、CFinRAG新增[30]和CNINFO年报[31]分别有专项核查。该审计不替代355条回答的逐条语义复核、法规历史适用性核验或整稿终审。
- [CFinRAG文献来源核查](results/paper/condensed_candidate_20261028_01/cfinrag_citation_audit_20261028.md)与[候选稿修订收据](results/paper/condensed_candidate_20261028_01/current_candidate_cfinrag_revision_receipt_20261028.json)记录新增来源、引用重编号、31条文献覆盖及WPS页面复核；它们不证明全领域检索穷尽或论文贡献新颖性。

## 2026-10-28 法规日期与因果措辞复核（历史候选）

- 法规日期与因果措辞版本为[非因果表述修订稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_精简主文_非因果摘要修订候选稿_20261028.docx)，21页、12表、8图；补充材料仍为3页、3表、1图。摘要将双路/合并条件下的来源共现及评分差改成观察性描述，讨论同步说明来源删除消融同时改变证据内容和上下文长度。

- 第7.6节仍依据证监会官方公告区分第226号令（2025-03-26公布、2025-07-01施行）、第6号公告（2025-03-28公布并施行）和第18号公告（2025-10-16公布、2026-01-01施行）。该历史候选的WPS只读渲染为21页；相对其法规日期复核稿，Poppler 120 dpi对比仅第1、17页变化，均已目视检查，其余18页像素一致；12张表单元格文本未变。

- [法规日期核验收据](results/paper/condensed_candidate_20261028_01/legal_date_claim_audit_20261028.json)、[非因果表述与渲染审计](results/paper/condensed_candidate_20261028_01/manuscript_claim_revision_audit_20261028.json)、[本版数字继承核对](results/paper/condensed_candidate_20261028_01/numeric_content_audit_20261028_noncausal_revision.json)和[本版SHA-256清单](results/paper/condensed_candidate_20261028_01/SHA256_manifest_20261028_noncausal_revision.json)记录来源与版本。该修改不证明2024年事项的历史法规适用性；稿件仍待全文语义终审、作者元数据和目标期刊格式适配。

## 2026-10-28 供应商输出重分析更正

- 最新口径以[仅供应商真实生成输出的重分析](results/runs/primary_generation_only_reanalysis_windows_20261028_01/analysis.json)及[2026-10-28随机种子复核](results/runs/primary_provider_only_robustness_20261028_02/robustness_audit_primary_provider_only.json)为准：主实验G1/G2/G3为147/180个有效API生成（52/60、47/60、48/60）；所有条件为355/400个可评分供应商回答。旧候选稿的178/180、386/400包含33条当前助手会话补写，其中31条曾被评分，不能作为供应商实验结果；补写未调用API，已从正式分析中排除。
- 最新统计显示G2−G1公司宏均分差为+0.228/8（41个配对问题，20,000次公司聚类bootstrap区间[0.110, 0.355]）；但基于缺失评分端点的全题代数界为[-1.508, 1.292]，跨零，故不能推广为计划题集上的确定优势。G3−G2为+0.013/8（38对），同样仅作探索性观察。缺失界、筛选子集和协议限制见重分析文件及候选稿。
- 最新[供应商输出重分析候选稿](results/paper/primary_provider_candidate_20261028_01/年报与法规双源RAG_供应商输出重分析候选稿_摘要证据供给措辞修订_20261028.docx)为21页；表12节选和评分映射已有专项复核，摘要的区间与来源供给数字也已绑定重分析及回放源文件。按355份评分记录复算后，已统一表5“No rerank”“BM25”两行的逐回答均分口径，并将表8公司事实评分差修正为0.115；表5–9与重分析数据复算一致。表5–9统计修订版本的版面核查仅第10、13页变化；随后表12和摘要复核版本重新渲染为21页，第1–3页已复核，第4–21页与前版像素一致。详细复算与边界见[候选稿审计记录](results/paper/substantial_revision_20261023_01/audit/table_figure_alignment_20261028.md)。统一主文的段落124现对一个事后选取案例完成全文核查，但355条回答尚未逐条进行人工语义复核；该稿仍是内容候选稿，不是投稿终稿或二区录用证明。跨模型族实验尚未完成；跨年度/Agent结果仍是小样本探索性运行。
- GitHub同步状态：当前统一主文候选、修订收据、README与阶段计划已同步到草稿PR #3；本地集成分支仍落后远端85个提交且工作区混有其他改动，未将本地混合改动整体推送。

## 2026-10-28 精简主文与补充材料候选稿

- 此前的主文版本保留为历史快照：[供应商口径同步精简主文](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_精简主文_供应商口径同步_补充编号对齐_bootstrap20261028候选稿_待终审.docx)，21页、12表、8图；配套[精简补充材料](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_精简补充材料_预算与BM25检索诊断候选稿_待终审.docx)为3页、3表、1图，仅保留主文引用的预算回放与BM25定位诊断。主稿已同步20,000次公司聚类bootstrap的2026-10-28种子区间；最近一次渲染中第11、15页已复查无裁切或重叠，其余页面与已检查版本逐像素一致。补充材料3页也已检查。主文表6–11已按355份评分、种子20261028重分析JSON及检索汇总CSV复算；[数字核对收据](results/paper/condensed_candidate_20261028_01/numeric_content_audit_20261028.json)记录通过项目和输入哈希。渲染证据见[补充编号收据](results/paper/condensed_candidate_20261028_01/aligned_candidate_receipt_20261028.json)和[bootstrap同步收据](results/paper/condensed_candidate_20261028_01/bootstrap_sync_receipt_20261028.json)。
- 较早的[未同步精简主文](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_精简主文候选稿_待终审.docx)仍是历史快照，原有178/180、386/400已被供应商输出重分析更正，不能引用为现行结果。原完整补充材料也保留为历史版本；旧文件没有覆盖。
- 当前工作稿仍待作者/单位/基金等元数据确认、全文内容终审和目标期刊模板适配，不是投稿终稿，也不能据此声称达到二区录用水平。原聚焦稿、扩展稿及运行材料均保留。
- 跨年与Agent实验并非尚未运行：已有2家公司、2023/2024两个报告年度、12题的小样本探索批次；因公司少、年份与切分混杂、同生态自动评分及预算未完全匹配，不能据此声称独立跨年度泛化、跨模型族效果或Agent普遍增益。实验细节和边界见[交付说明](results/paper/generalization_extension_20261023_01/交付说明.txt)及[阶段收敛计划](docs/论文阶段收敛计划_20261027.md)。当前优先收口主稿与复现材料；追加实验须针对尚未支持的明确主张，不重复已做运行。

## 已被更正统计取代的聚焦稿历史快照

- 该稿仍保存用于追溯，但包含已被供应商重分析取代的386/400、+0.250旧口径，不是当前工作稿。当前稿见上方“统一主文候选稿”。
- 历史[聚焦主问题候选稿](results/paper/focused_candidate_20261028_01/年报与法规双源RAG_聚焦主问题候选稿_待终审.docx)，从完整跨年/Agent扩展候选稿派生，保留主实验与相关检索诊断，移出跨年度/Agent、聊天助手和自动评分校准等探索性章节；原扩展稿和实验材料均保留。聚焦稿为26页、19表、13图，WPS只读渲染与逐页视觉核查完成；详见[版本说明](results/paper/focused_candidate_20261028_01/README.md)及[审计收据](results/paper/focused_candidate_20261028_01/focused_candidate_audit.json)。它仍待内容终审、作者元数据和目标期刊模板适配，不是投稿终稿。2026-10-28进一步收窄了可审计性相关表述，明确没有实测复核成本、决策风险或人员工时，并在结论中说明来源缺失消融同时改变了证据内容和上下文长度；WPS复核为26页，新增检索指标口径说明并完成全页复核，详见聚焦稿审计收据。
- 检索指标核查：主实验另保存60题×两策略×Top-10排序（1,200行）；现有40题、1,049条开发集相关判断与主实验题目ID无交集，因此不报告主实验标准Precision/Recall/nDCG。
- 2026-10-28已为这60题准备主实验Top-10候选池的双人盲审表：排序行与冻结索引中的片段、来源哈希、文档类型和页码全部匹配；合并去重后833个“题目—片段”项，A/B各833行，协调密钥单独保存。判断栏均为空，**人工qrels和检索指标仍未完成**；后续Recall只能解释为冻结候选池内Recall，不能解释为全库召回率。范围和校验记录见[盲审包说明](docs/主实验检索相关性双人盲审包_20261028.md)。
- 已增加盲审结果离线评分入口`scripts/score_primary_retrieval_qrels_20261028.py`：校验盲审表、协调密钥和冻结问题集；标签未完成时停止指标计算；分歧须仲裁后才计算P@k、候选池Recall@k、graded nDCG@k和公司聚类配对bootstrap区间。空表演练返回`awaiting_reviews`、1666个空标签、0个配对判断，未产生检索质量结论；另以临时合成标签走通“一致评分—待仲裁—完成仲裁”路径，不作为实验结果。收回标注后的命令与输出说明见[盲审包说明](docs/主实验检索相关性双人盲审包_20261028.md)。

## 2026-10-28 当前研究稿与计划

- [双源RAG实证长稿](results/paper/substantial_revision_20261023_01/年报与法规双源RAG_大幅修订研究长稿.docx)是精简主文的上游研究稿，含20家公司、60个问题的既有双人评分研究及后验检索、预算、主题和缺失敏感性分析。当前实际编辑对象以本页上方的统一主文候选稿及配套补充材料为准。
- 文献更新加入年报问答基准ARQA、CFQA；主稿的29条参考文献均能对应正文引文。WPS只读渲染为25页，版面复核记录见[交付与实验复现说明](results/paper/substantial_revision_20261023_01/交付与实验复现说明.txt)。
- 当前结论只适用于现有样本和评分口径：分路检索相对合并候选池呈正向观察，同上下文角色提示无稳定增益；严格法规位置覆盖有限。法规版本时点、论断级语义支持、真人独立复核与跨模型族泛化均未得到验证，不将结构化引用、页码命中或新增上下文材料称作答案准确率/召回率。
- 已从主实验制备40题、120条回答的论断—证据盲审包（每家公司2题，含G1/G2/G3）；两名复核者的标注文件目前各有120行空白记录、0条新判断。它补充检查既有回答的论断支持，不是独立新公司测试集。当前主稿已明确不声称论断级语义支持或历史法规适用性验证，因此该盲审包暂不阻塞主稿冻结；如将来提出上述主张，再由真人独立复核。来源副本约101 MB，包留在本地，未推送GitHub。
- 当前主稿阶段计划收敛为：核对统计与主张、明确法规版本风险边界、完成论文与复现材料一致性检查。论断级盲审包是补充工作，不是主稿冻结门槛；跨模型、跨年度、Agent和表格解析均属于独立研究问题，不作为当前主稿的默认加做项。92条法规版次字段差异仍待仲裁，不是已确认的实质冲突；接受标签为0，审阅人身份和盲审均未验证。详见[阶段收敛计划](docs/论文阶段收敛计划_20261027.md)与[表格解析验收记录](docs/年报表格与跨页续表解析_实现验收_20261027.txt)。
- [历史主稿表图对齐核查](results/paper/substantial_revision_20261023_01/audit/table_figure_alignment_20261028.md)：该记录核对了当时版本的统计表、检索回放、案例和图表；其386条评分中包含31条助手会话补写，因此“与当时稿件一致”不代表供应商统计有效。现行统计以本页顶部的供应商输出重分析为准。

### 已有跨年度与 Agent 补充运行（探索性）

- 仓库已有[跨年与 Agent 实跑修订稿及复现材料](results/paper/generalization_extension_20261023_01/交付说明.txt)，不能把这批实验说成“尚未运行”：2家公司×2023/2024×3主题，共12题；48个主要回答、12个Agent v2修复单元，保存132次生成调用，60个单元中59个非空。Agent相对三次固定证据修订的自动评分配对均差为2023年−0.333/8（n=6）、2024年0.000/8（n=6）。
- 结果只作探索性报告：两家公司样本、年份与切分方式混杂；评分由同生态K2.8服务自动完成、没有新增人工评分；Agent与固定修订预算也未完全匹配。K3与K2.8不是跨模型族对照；两条GPT界面案例未独立验证模型身份且带有任务历史，不能计作跨模型验证。
- 完整扩展稿[年报与法规双源RAG_跨年与Agent实跑修订稿.docx](results/paper/generalization_extension_20261023_01/年报与法规双源RAG_跨年与Agent实跑修订稿.docx)已将补充运行写入第6.7–6.12节，含17图、24表；较新的[核心主稿](results/paper/substantial_revision_20261023_01/年报与法规双源RAG_大幅修订研究长稿.docx)含13图、19表、29项参考文献，扩展稿清单为25项参考文献。两者是不同修订快照：前者含跨年/Agent正文，后者保留较新的文献和编辑修订。合并实验章节已在下方候选稿完成；冻结前仍需复核引文、表图编号、统计数据与结论边界，不能把两份来源快照中的任一份单独称为统一版本。详见[论文阶段收敛计划](docs/论文阶段收敛计划_20261027.md)。
- 当前本地[跨年/Agent合并候选稿（待内容终审）](results/paper/integrated_candidate_20261028_01/年报与法规双源RAG_跨年Agent合并候选稿_待渲染验收.docx)含24表、17图和31条参考文献；正文图表引用已核对，补充实验48条主回答、12条修复单元和132次调用已复核。2026-10-28针对保利发展分红案例补入官方实施公告，末页参考文献间距修正后WPS重渲染为30页，[最近渲染记录](results/paper/integrated_candidate_20261028_01/render_qa_crossyear_score_audit_20261028/native_render_receipt.json)确认源文件未被渲染过程改写。该稿仍待整稿内容终审、作者/投稿元数据确认和期刊模板适配，不代表已达到二区录用标准；GitHub同步另需处理分支落后和本地未跟踪文件筛选。

## 2026-10-27 预算竞争修复：已按规划实施并离线验证

- [实施规划](docs/预算分配优化实施规划_20261027.txt)先行保存；解析与邻接成果已在提交[`c416a61`](https://github.com/2391552910-coder/xiao-traceable-regulatory-rag/commit/c416a6166066bb3990c3f18e7ed2912ab1036055)发布，[该提交的GitHub离线测试已通过](https://github.com/2391552910-coder/xiao-traceable-regulatory-rag/actions/runs/40442726192)。
- 新增“截断线索优先”的完整片段分配器：仅根据初始片段末尾未闭合的日期/括号线索，优先安排直接同页后继，再安排表格和其余邻接候选；不读参考答案、不改写查询、不调用模型。
- **8题×5策略，40份材料；重复运行的40份上下文文件逐字节一致，240项本地测试通过。** 所有方案共用同一候选池、6000-token上限和16个新增来源上限，初始文本/记录/引用ID全部保留。[结果与验收说明](docs/预算分配优化_结果与验收_20261027.txt)。
- 招商银行2024：表格优先为6/6个表格姓名候选＋5/9个日期来源区间；新策略在**5921 tokens**内同时提供6/6和9/9。交替分配仍只保留3/6个表格姓名候选，负例没有删除。[对照图](results/runs/evidence_budget_development_20261027_01/figures/joint_source_supply.png)。
- 新策略在8个已曝光开发问题上保留全部提供给算法的表格姓名候选，勘误参考页覆盖为100%。这不是回答Precision/Recall，原始正文可能本来就包含这些姓名；不能据此声称未见数据泛化或独立验证成功。
- 可用[supplement_evidence_budget.py](scripts/supplement_evidence_budget.py)直接导出联合材料及提示，已实际导出5921-token packet，全程0模型调用。新的生成质量仍为空，独立人工复核仍未完成。

## 2026-10-27 同步范围与下一步

本次GitHub同步包含已验收的表格解析、邻接扩展、证据保留代码、必要依赖、测试与离线材料。相同6000-token预算下的截断线索、表格优先、邻接优先与交替策略比较已完成，详见上方材料分配结果和对应验收说明；该8题开发集没有独立人工验证，不作为最终性能结论。下面各批次报告中的“尚未推送”是其验收时状态；最新发布以本节和提交历史为准。

新增离线测试工作流只安装`requirements-offline-evidence.txt`，不需要API凭证、模型权重或原始年报PDF。完整来源重验与离线实验重跑仍需按官方地址/哈希取得对应PDF与索引，测试通过不能替代独立人工标注。

## 2026-10-27 年报表格与跨页续表解析已实现

- 已完成有网格表格、无框线出席矩阵、独立落页表头、重复表头、跨页姓名/日期及议案续行的处理；单元格保留PDF物理页、版面坐标、原始字符索引及指纹。[实现、结果与使用说明](docs/年报表格与跨页续表解析_实现验收_20261027.txt)。
- **8份年报、142个治理关键词及相邻页**中，检测77个表格区域，连接18组相邻页表格，合并8处断行；生成120条表格字段检索记录，其中45条明确涉及审计委员会。不是对全部财务报表版式的通用正确性保证；单PDF入口支持`--all-pages`。
- **212项测试通过**；4326个单元格在重新打开的PDF上核验，46页原文预览已生成。[离线验收](results/runs/annual_table_development_20261027_03/implementation_audit.json)确认134份历史发布文件不变，全程0模型调用。
- 后续代码复查发现同页混合版式边界：页面含有框线表时，旧逻辑会跳过同页的无框线出席矩阵。v1.3已修正；10页合成夹具的`tests/test_annual_tables.py`为39/39通过。修复已提交至[草稿PR #4](https://github.com/2391552910-coder/xiao-traceable-regulatory-rag/pull/4)，PR离线CI通过。
- 2026-10-28在新目录重跑原8份年报后，142页、77个表格、18组续表、8处断行、4326个单元格与v1.2结果一致；8份解析文档除版本字段外完全相同，离线分析文件哈希也一致。该结果是同一开发批次的非回归检查，不是新增准确率或独立验证。[对照收据](results/runs/annual_table_development_v13_regression_20261027_01/v13_nonregression_audit.json)。
- 2026-10-28用立讯精密2024年报第60–61页发现并修复两处实际漏项（v1.4）：跨页意见续句从“伪表头”并回上一条会议记录；结构化检索保留以“审议”开头的议题及意见/履职说明字段。单案由4条审计委员会记录补足为8条可检索委员会记录；41项定向测试通过，原8份年报离线批次通过回归。此为事后案例修复，不是独立泛化或答案质量指标。[单案证据与回归收据](results/runs/luxshare_case_table_audit_20261028_06/cross_page_case_audit.json)。
- 留出报告发现类别误判后，当前解析器升至v1.7：股东大会/董事会表不再仅因含“会议”和“日期”就归入委员会会议；委员会表需要明确列或章节证据。美的2024第70页、北京文化第25页和第30–31页的错误类别已纠正，对应真正专门委员会表仍保留。42项定向测试和原8份年报回归通过。[55页留出盲审页](results/runs/annual_table_holdout_review_v17_20261028_02/blind_review.html) / [空白标注表](results/runs/annual_table_holdout_review_v17_20261028_02/page_review_template.csv) / [机器可读审计](results/runs/annual_table_holdout_review_v17_20261028_02/holdout_audit.json)。人工标签仍为空，未报告留出准确率、精确率或召回率。
- 2026-10-28并发测试复核后，将“至少8个工作线程重叠”的时序假设改为8线程屏障同步；相关并发用例连续5轮（50项）通过。随后当前本地工作区完整`pytest`为**1256项通过**，耗时80.44秒；有3条弃用/参数提示。测试使用项目虚拟环境中锁定的NumPy 1.26.4，并临时复用本地现成的PDF解析依赖。由于当前本地分支有未提交改动且落后远端，以上全量结果尚未由GitHub CI复核，不能视作远端提交已验收。
- 当前v1.7完整本地`pytest`为**1263项通过、0失败**，耗时88.67秒，含4条弃用/依赖参数警告。v1.7解析代码已同步至仍开放的草稿PR #4；其对应离线工作流[#152通过](https://github.com/2391552910-coder/xiao-traceable-regulatory-rag/actions/runs/40643942017)，覆盖离线回归测试清单（包括年报表格和证据接入测试），不是全量`pytest`。CI通过不替代独立人工标注或生成回答质量评价。
- 表格FTS5检索与按表格类型均衡检索已接入保留原证据的RAG接口；完成8题×5方案的40份上下文对照，均≤6000参考tokens。均衡表格补充的勘误参考页覆盖为100%，原始材料为95.83%；页面覆盖不等于语义召回。
- **同时保留负例**：招商银行2024中，邻接续片独立补充可供给9/9个审计日期来源区间，而先表格后邻接仅5/9，存在预算竞争。[完整对照图](results/runs/annual_table_development_20261027_03/figures/table_retrieval_comparison.png)。
- [本地表格/续表复核页面](results/runs/annual_table_development_20261027_03/review.html)提供原页链接、委员会归属及跨页标记；329行复核模板均未填写，独立人工验证尚未完成。规则解析器的开发集字段指标另存，不能替代LLM生成质量；代码与离线材料已由提交 [c416a61](https://github.com/2391552910-coder/xiao-traceable-regulatory-rag/commit/c416a6166066bb3990c3f18e7ed2912ab1036055) 发布；本轮未替换Word论文。

## 2026-10-27 同文档邻接扩展：已完成本地离线比较

- **0次大模型调用，8题×6方案共48个上下文，170项测试通过。** 原文、来源记录和引用编号全部保留，所有方案均不超过6000参考tokens；[完整说明与复算方法](docs/相邻片段扩展与离线对照_20261027.txt)。
- 同一份PDF内按页码和片段起点确定直接前后邻居，比较普通顺序、同页后继优先，以及与固定查询的先后顺序；不读取答案标签来选片段、不递归扩展、不截断新片段。
- 招商银行2024年的具体截断案例中，同页后继优先将**审计会议日期的对应来源区间从5/9补至9/9**，使用5787 tokens；普通邻接、固定查询和先固定查询后邻接仍为5/9。这是材料补全，尚未生成新的回答。
- 8题勘误参考页覆盖率在全部6方案下均为95.83%，没有整体页面覆盖增益；新增字符数量也不代表内容正确或相关。[逐题指标](results/runs/adjacent_evidence_development_20261027_02/offline_metrics.csv)完整保留成功与未补全的对照。
- 已重新核对8份年报PDF字节指纹、重新解析65个用到的年报页面，验证82个唯一年报片段的精确位置；134份已发布历史文件保持不变。[离线验收记录](results/runs/adjacent_evidence_development_20261027_02/implementation_audit.json)。法规未重新执行PDF核验。
- [对照图PNG](results/runs/adjacent_evidence_development_20261027_02/figures/adjacent_evidence_comparison.png) / [矢量PDF](results/runs/adjacent_evidence_development_20261027_02/figures/adjacent_evidence_comparison.pdf)。本轮仅本地更新；新Precision、Recall、F1和Accuracy仍为未测得，独立人工验证尚未完成。

## 2026-10-26 本地离线实现进展

- 已将开发实验接入已有的证据保留机制，并补齐原子请求日志、异常恢复及401/403/429停止保护；[实现与使用说明](docs/证据保留修复与离线验收_20261026.txt)。
- **110项定向测试通过**（96项核心与14项评分测试）。8个初始上下文、32步历史上下文全部复现；16条离线轨迹中，原Agent初始片段保留率由58.75%变为100%，固定扩展由32.50%变为100%，均未超过6000参考tokens。保留率不是回答准确率。
- [离线验收记录](results/runs/evidence_retention_development_20261026_03/implementation_audit.json)确认原已发布134份结果/输入/调用记录未改变，重复回放指标一致。
- 实跑未取得回答：先遇到curl TLS故障，改用系统默认TLS校验客户端后服务返回403权限错误。用户选择先完成离线工作。03批次只冻结协议、尚未派发；恢复服务后的真实生成需显式启动。
- 下文Precision、Recall、F1和Accuracy仍是2026-10-23历史回答的结果；本次修复的生成质量尚未测得，没有更新为更高分数。新增独立人工复核也尚未完成。
- [新批次离线评分入口](scripts/score_evidence_retention_development_20261026.py)同时保留原/勘误口径；尚未开始、尚未结束或全为服务失败的条件均保留空质量值。

研究上市公司年报与法规文件中的证据检索、来源分配及带引用回答。投稿目标为计算机相关期刊；当前结果支持有边界的实证结论，不代表录用或分区达标。

**以下GitHub发布结果来自2026-10-23实验；文档发布于2026-10-26。上方本地修复及失败尝试另行记账。**

## 最新入口

- [最新论文与材料说明](deliverables/20261026/README.md)
- [英文全文](deliverables/20261026/Dual_source_RAG_new_company_validation_EN.docx) / [中文版修订稿](deliverables/20261026/年报与法规双源RAG_新公司留出与标签勘误修订稿.docx)
- [汇总指标CSV](deliverables/20261026/metrics_summary.csv) / [逐题指标CSV](results/paper/heldout_validation_20261023_01/heldout_metrics_corrected.csv)
- [原冻结标签](results/paper/heldout_validation_20261023_01/reference_labels.json) / [输出后勘误标签](results/paper/heldout_validation_20261023_01/reference_labels_corrected.json)
- [离线评分脚本](scripts/score_heldout_validation_20261023.py) / [结果与复算说明](results/README.md)
- [下一步优化与验收](deliverables/20261026/NEXT_STEPS.md)

## 已完成的实验与适用范围

| 研究层次 | 实际范围 | 已有结果 | 边界 |
| --- | --- | --- | --- |
| 供应商真实输出重分析 | 20家公司、60题；主G1/G2/G3为147/180，全部条件355/400 | G2−G1公司宏均分差+0.228/8（41对；聚类区间[0.110,0.355]） | 全题缺失界[-1.508,1.292]跨零；旧386条双人评分统计已被纠正，不作现行供应商结果 |
| 上下文诊断 | 1,800个缓存回放、600个新稀疏检索上下文 | 保留来源供给、预算及参考位置诊断 | 不是2,400个新生成回答；页面覆盖不是语义召回 |
| 新公司跨年度字段提取 | 原20家之外4家公司，2023/2024两年度，共8题×5条件 | 40个计划单元；38项最终响应成功，37项非空且结构合格；保存71条调用记录 | 标签由AI助手提取核查，尚无新增独立人工裁定；仅测试披露提取，未测试法规适用结论 |
| 跨模型族 | 官方Qwen固定权重及量化文件哈希匹配；CPU FP16模型加载成功 | cu126安装请求超时；CPU单题4,323-token输入的单token冒烟未在观察窗口内完成，未保存答案；跨模型性能仍未完成 | K3与K2.8为同家族服务比较；聊天案例不计独立跨族验证；运行环境复核见[记录](docs/Qwen3本地推理环境复核_20261027.md) |

## 精确率、召回率、F1与准确率

下表为8题、勘误标签版本的**逐题宏平均百分比**。每种方法均保留8个计划单元，失败和空回答在这些指标中按既定规则计0；空预测的Precision也按0约定。F1先逐题计算再平均，不是对表中平均Precision和Recall重新求调和均值。

| 方法 | 成员Precision | 成员Recall | 成员F1 | 会议次数Accuracy | 三字段Exact Match |
| --- | ---: | ---: | ---: | ---: | ---: |
| K3单次 | 100.00 | 95.42 | 97.47 | 100.00 | 75.00 |
| K2.8单次 | 87.50 | 85.42 | 86.36 | 87.50 | 75.00 |
| K3三轮修订 | 87.50 | 85.42 | 86.36 | 87.50 | 75.00 |
| K3 Agent | 75.00 | 72.50 | 73.61 | 75.00 | 50.00 |
| K3固定扩展 | 87.50 | 83.33 | 85.00 | 87.50 | 62.50 |

| 方法 | 日期Precision | 日期Recall | 日期F1 |
| --- | ---: | ---: | ---: |
| K3单次 | 100.00 | 92.36 | 95.29 |
| K2.8单次 | 87.50 | 81.94 | 83.93 |
| K3三轮修订 | 87.50 | 81.94 | 83.93 |
| K3 Agent | 75.00 | 69.44 | 71.43 |
| K3固定扩展 | 100.00 | 92.36 | 95.29 |

- Precision：正确提取项数/全部提取项数；Recall：正确提取项数/参考项数；F1综合两者。
- 会议次数Accuracy按整数精确匹配；三字段Exact Match要求全年成员集合、会议总次数、不同日期集合全部匹配。会议次数不以去重日期数倒推。
- 这些是回答字段指标。原主实验0–8分人工评分、检索页面覆盖、引用ID可解析率分别属于不同指标，不混为语义准确率。
- 勘误后三字段全对：K3单次6/8、三轮修订6/8、Agent 4/8、固定扩展5/8；本批结果不支持Agent总体优于单次基线。

## 标签勘误、失败与可验证边界

华润三九2024参考成员漏记年初离任的刘俊勇。原始年报物理第44页和第94页明确支持其报告期内任职。原冻结标签及哈希保持不变，另存看过输出后的勘误版本，并对相同保存回答重新评分。它不是预先固定或独立人工裁定的标签。

三项缺少可见最终答案的情况分别是：Gree 2024 Agent最终调用HTTP 502；CR Sanjiu 2024 K2.8耗尽输出额度；该题三轮修订的最后请求缺少响应记录，远端执行与用量未知。失败没有选择性重试，历史记录没有被成功视图覆盖。

当前8题已用于诊断，后续控制器开发应将其作为开发回归集；新方法的独立验证需另建冻结测试集。来源存在或引用编号有效均不自动证明该片段支持论断。

## 离线复算

Python 3.11及以上，在仓库根目录运行以下命令。脚本仅依赖标准库，读取保存回答，不访问生成API、不需要密钥。

```bash
python scripts/score_heldout_validation_20261023.py
python scripts/score_heldout_validation_20261023.py --corrected
```

第一条产生原冻结标签分析；第二条产生勘误分析。原始计划、初始输入、40个最终单元、71条调用记录以及一条缺少响应的请求均在本次轻量发布范围内。原PDF只提供官方地址与哈希，模型权重、缓存、API配置及大ZIP未上传。

本次同步范围是文档、两版既有论文、结果和离线复算材料；不把本地尚未审查的整套运行时改动视为已发布功能。正文作者、单位、基金、贡献和利益冲突声明仍须作者据实定稿。

<details>
<summary>早期项目说明与历史状态（保留原文，最新进展以上文为准）</summary>

# 面向上市公司主体自律评价的可追溯检索增强生成

本仓库用于完成《面向上市公司主体自律评价的可追溯检索增强生成方法》小论文的算法与实验，以**中科院二区计算机类期刊**为投稿目标。小论文的方法与实测结论将作为大论文的一个支撑。

研究对象是以年报 PDF 和法规文件为双来源输入的可追溯 RAG：系统接收文件后解析、切分并建立索引；用户提出上市公司主体自律评价问题后，分别检索年报中的公司证据和适用法规，再生成带来源引用的内容。评测关注检索是否命中支持段落、法规版本与适用时点是否正确、生成论断是否受引用证据支持，以及证据不足时是否如实说明。年报事实抽取候选可辅助定位或构造评测样例，但不构成系统运行所必需的完整事实库。

任务对齐版本：2026-10-13。

## 项目说明入口

- [年报文档输入验收与问题级双源标注操作交接](docs/review_20261013/NEXT_INPUT_HANDOFF.md)：39 家缺件清单、Windows 操作、仲裁导回和测试集隔离。

- [2026-10-13 PR 审阅、数据准备与模型接口验证报告](docs/review_20261013/FINAL_REPORT.md)：清理版本、标签迁移、日期证据、测试隔离、双 0.6B 有限验证及剩余缺口。

- [项目任务与验收](docs/项目任务与验收.md)：目标、范围、数据规模、优先级和完成标准。
- [实验设计与流程](docs/实验设计与流程.md)：研究问题、对照、指标、统计和复现规范。
- [标注规范](docs/标注规范.md)：检索证据、生成论断与引用的人工复核。
- [知识库采集说明](docs/知识库采集说明.md)：语料口径、历史版本和数据来源。
- [研究依据与微调决策](docs/研究依据与微调决策.md)：Qwen3 使用策略和相关工作。
- [实验产物说明](results/README.md)：已有结果的解释及正式运行记录要求。
- [GitHub 同步与交接](PUSH_GUIDE.md)：当前仓库和后续提交约定。

## 方法与模型

评价覆盖四个维度：D1 信息披露质量、D2 董事会治理有效性、D3 内部控制与合规性、D4 第三方声誉。

已有研究原型包含条款切分、BM25＋向量混合检索、维度路由、引用约束与法规名/条款号对齐。Qwen3 用于 **Embedding 和 Reranker**，生成模型单独配置。主机约束已确认：Embedding 固定为 Qwen3-Embedding-0.6B，Reranker 固定为 Qwen3-Reranker-0.6B；主实验不要求本机加载 4B/8B 检索模型。BGE-M3 等可行的小规模模型作为对照，按次序加载并实测内存。

**微调是条件性扩展。** 先校正官方推理接口，用冻结权重完成可靠基线，再依据开发集诊断决定是否进行领域适配。常规微调和组件组合不直接作为论文原创贡献。0.6B 主干可以用于本项目的投稿研究，是否达到目标取决于方法差异、可靠标注、强基线和实测证据；参数量不是录用保证。主实验固定检索骨干，另报告内存、延迟、吞吐及调用成本，研究效果与开销的权衡。生成和 judge 模型独立配置，当前真实调用路径为 API，不要求在主机另载大模型。

目标端到端流程：年报 PDF 与法规文件分别上传/导入 → 文档身份与版本登记 → 解析及 OCR（需要时）→ 保留来源坐标的切分 → 分库索引 → 同一评价问题分别检索公司证据与法规证据 → 生成逐项引用的评价内容及证据不足状态。当前代码已有批处理语料、检索与引用原型；交互式上传、双库统一编排和完整端到端评测是否就绪，须以实际实现和运行记录验收，不能由目标描述推定已完成。

数据策略以可追溯的双语料库为系统输入，以人工核验的问题—年报支持段落—适用法规条款—生成引用关系作为评测参照。评测标注验证系统是否找对并正确使用原文，不要求预先把每份年报穷尽转成结构化公司事实库。公开文本证据基准只用于其任务标签实际支持的外部验证，不替代中国公司自律评价任务。

## 当前状态

下表为对齐前提交 `b95aff7` 的数据与代码核查，不代表正式论文成果。

| 项目 | 已有基础 | 待完成 |
| --- | --- | --- |
| 知识库 | manifest 315 篇：法规 84、处罚 212、通报 19；对应 7,840 块 | 目录实际加载 319 篇、7,899 块，含清单外的早期文件；冻结口径、版本与适用日期 |
| 检索标注 | 弱标签 40 条；AI 双通道仲裁候选 40 条、226 个相关块 | 人工复核、候选池审计、扩充并隔离开发/测试查询；02/04 仍默认读弱标签 |
| 公司材料 | 39 家 2024 年报作为先导文档；后续 Windows 本地运行已在独立新目录恢复原 PDF 并核验身份 | 将年报作为可检索文档库输入；建立问题级年报证据与法规证据评测标签，不要求穷尽式事实库 |
| 模型接口 | 本地/远端 Embedding 和重排接口已有原型 | Qwen3 本地重排评分、查询指令和依赖兼容性须按官方实现校正 |
| 合成数据 | Embedding 600 条模板查询；Rerank 3,600 对 | 清洗假负例和同源条款跨 split 泄漏；只用于联调/探索，尚无微调成果 |
| 实验产物 | 检索汇总表和 TF-IDF 合成集测评表 | 正式模型对比、语义核验、消融、聚类统计、鲁棒性、跨模型和完整图表 |

已有检索表中路由配置并未优于 BM25；合成集测评表的实际 backend 为 `tfidf`，不能当作 Qwen3 实测结果。当前 `citation_accuracy` 只是检索内引用匹配比例，不能等同于语义正确性或完整幻觉率。

## 目录

```text
src/data/         知识库加载、条款/滑窗切分、样本加载
src/retrieval/    BM25、向量、混合、维度路由、重排
src/generation/   no_rag / naive_rag / ours 提示词、生成与引用抽取
src/alignment/    当前法规名和条款号对齐原型
src/metrics/      检索、judge 与统计指标
experiments/      01 构库 02 检索 03 生成 04 消融 05 统计 06 出图
                  07 合成数据 08 Embedding/重排选型
scripts/          法规、处罚、年报采集和标注辅助脚本
data/             语料、抽样/下载清单、标签与演示事实
docs/             对齐后的任务和研究规范
results/          历史结果与实验产物说明
tests/            离线冒烟测试
```

## 可运行入口

本机自 2026-10-15 起使用隔离 CUDA 环境进行本地神经模型推理。默认 Embedding 与 Reranker 均为 `cuda`、`float16`、`batch_size=1`；CUDA 不可用时直接报错，不自动回退 CPU。已有 CPU 运行与冻结结果作为历史记录保留。PDF 解析、文件读写、BM25 和向量矩阵的普通检索运算仍使用主机 CPU；真实生成由配置的 LLM API 执行。

Windows 双语料入口使用 `scripts/run_rag_gpu.ps1`，参数与 `scripts/dual_corpus_rag.py` 相同；它固定调用本机已经验证的隔离 CUDA Python，避免误用系统 CPU 版 PyTorch。小规模双模型显存检查使用 `scripts/verify_gpu_model_pair.py`，输出只能说明运行可行性。半精度配置与此前 float32 全量运行属于不同设置，不能直接复用其数值一致性或质量结论。

生成 API 配置放在项目根目录 `.env`，可参考 `.env.example`，支持 `LLM_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL`。程序从固定的项目路径读取该文件，已有进程环境变量优先；`.env` 已被 Git 忽略。填写配置后，调用双语料入口时还需显式传 `--real-llm`，才会执行真实生成；仅填写密钥不会关闭 mock。

安装依赖后，离线联调使用已有冒烟测试；该测试主动关闭重排和真实 LLM 调用。

```bash
pip install -r requirements.txt
python tests/test_smoke.py
```

已有合成集可用于 TF-IDF 联调：

```bash
python experiments/08_eval_embedding_rerank.py --backend tfidf --no-rerank --out-dir results/smoke
```

正式运行前须完成任务文档中的 P0 校正、年报/法规双库输入与检索链路、问题级双源证据标注和生成核验集。当前默认配置采用 Qwen3、启用重排，LLM 为 `mock: true`；仅向 02/03/04 传 `--backend tfidf` 不会自动关闭重排。正式生成须显式关闭 mock，配置真实生成模型，API 密钥通过环境变量注入。

优先顺序是：明确并实现年报/法规双库的解析、切分、索引与来源坐标 → 建立双源检索和逐论断引用生成 → 制作小规模人工核验评测集 → 冻结基线并完成对照、消融和统计 → 再决定微调与论文交付。实际结果不支持假设时，应记录负结果并修正方法。


</details>

