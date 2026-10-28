# 实验产物说明

## 当前统一主文候选稿（2026-10-28）

- 当前主文：[交叉引用补全候选稿](paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_交叉引用补全候选稿_待终审.docx)，SHA-256 `ba0efb91daa7e37df86136a82e839e11c4a5fc8ec6265fe7b3f245f40d89ba6c`，21页、12表、8图。在推理预算口径校准版上补齐表6、表7、表9、表12及图4、图6的正文交叉引用，没有修改统计结果、表格内容或结论。
- [交叉引用审计收据](paper/condensed_candidate_20261028_01/cross_reference_audit_20261029.json)确认12张表与8幅图均有正文引用；[WPS渲染PDF](paper/condensed_candidate_20261028_01/render_wps_crossrefs_20261029/paper_native.pdf)及[只读渲染收据](paper/condensed_candidate_20261028_01/render_wps_crossrefs_20261029/native_render_receipt.json)绑定本版哈希。变化页11、13、16–18已检查，无裁切或错位。
- [推理预算论断审计收据](paper/condensed_candidate_20261028_01/reasoning_budget_claim_audit_20261029.json)记录同系列服务别名比较的解释边界；[前版主文](paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_推理预算口径校准候选稿_待终审.docx)保留作版本追溯。候选稿仍待整稿语义终审、作者元数据和投稿模板适配，不表示达到二区录用标准。

## 2026-10-27 相同预算下的联合材料分配

- `runs/evidence_budget_development_20261027_01/`：按先行规划完成8题×5策略、40份材料，输入候选池、6000-token上限和新增来源总上限16全部一致；源码/输入指纹、候选池、逐候选装入/省略原因、原/勘误页面覆盖及事后区间诊断均保存。
- `runs/evidence_budget_development_20261027_02/`：同代码重复运行，40份上下文文件与主批次逐字节一致；不重复计作80个独立样本。
- 截断优先在招商银行2024同时保留6/6个表格姓名候选及9/9个审计日期来源区间，5921 tokens；表格优先为6/6＋5/9，邻接优先为2/6＋9/9，交替分配为3/6＋9/9。所有对照都保留。
- `implementation_audit.json`确认240项测试通过、8份PDF指纹、74个原窗口精确区间和57页PDFium重解析；134份旧发布文件不变。表格单元格来源沿用已冻结并记录哈希的4326单元格核验，不伪称本轮重新检查了所有单元格。
- 表格姓名供给只统计新增结构化视图对候选池的保留；初始正文可能已经包含同名，不能把其比例当答案召回率。新回答Precision/Recall/F1/Accuracy全部为空；尚无独立人类标注或新测试集。

详见[预算分配结果说明](../docs/预算分配优化_结果与验收_20261027.txt)。

## 2026-10-27 年报表格与续表解析

- `runs/annual_table_development_20261027_03/`为最终v1.2离线批次：8份年报、142个治理候选页，77个表格区域、59条逻辑表、18组跨页连接、8处断行合并；120条字段视图，其中45条涉及审计委员会。
- `documents/`保留所有原表/单元格和逻辑连接；`structured_chunks.jsonl`、`table_index.sqlite`提供检索接口；`source_previews/`包含46页原图叠框，`review.html`展示表格及原页。329行人工复核模板尚未填写，512个未分类/非目标行另行保留并分流，不能将它们概括为512项解析失败。
- `source_verification.json`及`implementation_audit.json`确认4326个单元格重新与PDF绑定；`tests_passed.xml`记录212项测试通过。40份检索上下文保留初始原文/记录/ID，均≤6000参考tokens，无模型调用。
- `parser_field_diagnostics.json`对原冻结/勘误参考分别给出纯规则表格字段结果；8题勘误口径成员F1=1.00、日期F1=0.75、显式会议次数Accuracy=0.50、三字段Exact Match=0.50。此为已曝光开发题上的表格解析诊断，不是新的LLM/RAG回答指标，也未经独立人工裁定。招商银行日期为正文披露，未伪装成表格字段补入。
- 均衡表格检索参考页覆盖95.83%→100%；普通表格BM25仍95.83%。先表格后续片在招商银行2024中仍只供给5/9个日期区间，低于仅续片的9/9；完整负例保留于验收与对照图。
- `runs/annual_table_development_20261027_01/`、`..._02/`为保留的开发修订批次，附当时源码快照和修订说明，没有覆盖原始数据。最终批次为`..._03/`。

命令、适用范围与输出定义见[实现验收说明](../docs/年报表格与跨页续表解析_实现验收_20261027.txt)。

## 2026-10-27 邻接片段离线实验

- `runs/adjacent_evidence_development_20261027_02/`：8个已曝光开发问题×6种固定策略，共48份完整上下文、逐阶段候选与打包审计、JSON/CSV指标、PNG/PDF图、170项测试及实现验收记录。全程0模型调用、0新回答，质量指标为null。
- 同页后继优先在招商银行2024的截断案例中供给9/9个审计日期的精确来源区间，原始材料为5/9；普通邻接、固定查询与先固定查询后邻接仍为5/9。8题勘误参考页覆盖率均为95.83%，不能据此声称答案召回率提升。
- 所有上下文保留初始原文和引用ID，均在6000参考tokens内；8份年报PDF指纹、65个重新解析的年报页面、82个唯一片段已核对。法规来源没有重新执行PDF解析核验。
- `runs/adjacent_evidence_development_20261027_01/`保存首次48份上下文及PDFium依赖缺失失败记录；02使用已有本机PDFium库完成，检索实现未变，两次48份上下文及轨迹完全一致。未下载依赖或重写历史输入。

详见[完整离线说明](../docs/相邻片段扩展与离线对照_20261027.txt)与[验收记录](runs/adjacent_evidence_development_20261027_02/implementation_audit.json)。

## 2026-10-26 证据保留离线验收

- `runs/evidence_retention_development_20261026_01/`：8题、16轨迹、32步历史上下文的原替换/保留策略离线回放；另保留32个TLS故障单元及终态。
- `runs/evidence_retention_development_20261026_02/`：正常TLS连接下的32个HTTP403单元，全部保留，无模型回答；运行源码和预检草案另存。
- `runs/evidence_retention_development_20261026_03/`：110项定向测试、重复回放和`implementation_audit.json`；只冻结后续32单元/64调用上限的协议，尚未派发。`extraction_analysis_frozen.json`与`extraction_analysis_corrected.json`均标为awaiting，质量值为null。

离线原Agent片段保留率58.75%→100%，固定扩展32.50%→100%，所有修复上下文不超过6000参考tokens。两批失败都没有产生回答，新增生成质量指标为未测得；不能将片段保留率或页面覆盖率报告为Precision、Recall或Accuracy。已有2026-10-23结果保持不变。

复算及恢复服务后的启动方式见[实现说明](../docs/证据保留修复与离线验收_20261026.txt)。

更新：2026-10-26；实验记录日期：2026-10-23。

## 最新公开结果

- [上游研究长稿与复现材料（历史底稿）](paper/substantial_revision_20261023_01/)：2026-10-27文献更新版，25页、13幅图、19张表、29条参考文献；相关工作纳入ARQA与CFQA并明确其与双源法规证据研究的区别。WPS只读渲染的25页逐页检查完成；正文引文1–29与参考文献逐项对应，无孤立引用或未引用文献；115项交付文件哈希均与清单一致，116项ZIP完整性检查通过。本次未增加模型调用或人工标签。阶段主张与延后实验见[论文阶段收敛计划](../docs/论文阶段收敛计划_20261027.md)。
- [交付入口](../deliverables/20261026/README.md)：中英文论文、指标表、代码和哈希清单。
- [新公司结果](paper/heldout_validation_20261023_01/heldout_analysis_corrected.json)：4家公司×2年度，40个计划单元，37个非空有效回答；失败保留。
- [逐题Precision Recall F1及精确匹配](paper/heldout_validation_20261023_01/heldout_metrics_corrected.csv)。字段提取指标不等于检索召回或引用语义准确率。
- [冻结参考](paper/heldout_validation_20261023_01/reference_labels.json)与[输出后勘误](paper/heldout_validation_20261023_01/reference_labels_corrected.json)均保留；新增标签未独立人工裁定。
- 运行 `python scripts/score_heldout_validation_20261023.py --corrected` 可离线重算，工作目录为仓库根目录，Python>=3.11，无API依赖。

原研究400个计划输出中386个有效回答有双人评分；新8题采用字段集合指标，评分来源和分母不同。原研究的无回答没有被赋予人工质量0分；新增端到端字段提取则将失败按0保留。两种口径不混合。

## 早期记录与规范

以下保留早期产物说明，其中“尚未提交”等状态仅对应当时日期，最新发布以上文及版本清单为准。

# 实验产物说明

核查版本：对齐前提交 b95aff7；说明更新于 2026-10-13。正式实验协议见[实验设计与流程](../docs/实验设计与流程.md)。

## 1. 已提交历史结果

| 文件 | 可确认内容 | 解释限制 |
| --- | --- | --- |
| retrieval_eval.csv | BM25、Dense、Hybrid、Hybrid+Routing 四配置汇总 | 未记录实际 backend、模型 revision、数据哈希及运行元数据，不能确认为正式神经模型测试 |
| embed_rerank_eval_summary.csv | 600 条查询，embedding_only，实际 backend=tfidf | model 字段虽写 Qwen3-Embedding-4B，实际没有运行该模型；无真实 Reranker 结果 |

历史检索表 Recall@5：BM25 约 0.164，Hybrid+Routing 约 0.117。此表不支持“本方法已优于基线”的结论，也不能因负结果而删掉。当前代码默认读取弱标签，但历史表没有足够元数据确认其精确运行配置。

目前没有已提交的正式生成明细、完整消融、人工语义核验、领域微调或完整统计/图表产物。脚本存在与成果完成须分别记录。

## 2. 正式运行产物规范（待实现）

每次运行使用独立 run_id 目录，区分 smoke、dev 与 final_test，不覆盖旧结果。推荐以下产物；现有脚本尚未自动输出全部文件。

- run_metadata.json：代码 SHA、运行时间、数据/划分/标注哈希、模型名称与 revision、实际 backend、mock、设备、量化、依赖版本、seed、prompt 哈希、指令、截断、融合、路由、候选深度和补检索上限。
- retrieval_detail.csv / retrieval_summary.csv：逐查询排名、相关性、证据区间、各维度汇总与置信区间。
- generation_records.jsonl：company_id、report_year、event_date、dimension、mode、repeat_id、事实和检索证据、原始响应、论断、引用、核验状态、调用成本、失败/重试。
- annotation_records.csv：实际人工标签、匿名标注者、独立标签与仲裁结果；人工未完成时不得生成虚假的完成记录。
- statistical_results.csv：聚类单位、重复聚合方式、差值、效应量、置信区间、原始/校正 p 值和样本数。
- figures/ 与 error_analysis.md：主实验、消融、覆盖率/风险、成本与失败案例。

无引用指标保留 NA，格式/调用失败另记失败状态，不能静默填零。正文和 JSON 的相同引用去重，但不同论断—引用边分别保留。mock/TF-IDF 不进入真实 Qwen3 成果表。

## 3. 归档与公开

results/*.csv 和 results/*.json 默认被 gitignore 排除，历史追踪文件仍可更新；新增结果不会自动入库。审查后显式追踪轻量汇总、元数据和复现所需明细；大型产物使用带 URL、版本及 SHA-256 的归档。API 密钥、身份凭据、模型缓存和公司年报 PDF 不写入此目录的公开产物。

结果必须能反查当时冻结的数据与模型设置；因接口、标签或统计错误产生的旧结果保留“已失效/探索性”原因，不与校正后正式结果混算。

## 4. 2026-10-14 Windows 本机组件联调

新增运行目录均为独立、未覆盖历史结果的组件检查：

- `runs/embedding_runtime_windows_20261014_01/`：本机 CPU 加载固定 revision 的 Qwen3-Embedding-0.6B，校验 3×1024 归一化向量及查询指令。
- `runs/reranker_runtime_windows_20261014_01/`、`_02/`：本机 CPU 加载固定 revision 的 Qwen3-Reranker-0.6B，记录官方 yes/no logits 路径的中文相关/不相关样例分数；`_02` 为本地缓存离线复跑。
- `runs/qwen_development_local_smoke_windows_20261014_01/`：12 个开发样本块、四维各一个开发查询的 Dense/BM25/Hybrid 联调，保留向量、样本文本、查询和逐项输出。
- `runs/regression_windows_20261014_04/`：本机完整回归记录，51 项通过。

上述 Qwen 运行只证明模型加载和联调路径可执行，不是完整检索基准、独立最终测试或正式生成评测。运行元数据和边界说明见[本机模型与检索联调进度](../docs/本机模型与检索联调进度_20261014.md)。RRF 已作为单独融合实现并通过单元测试，但尚无完整数据集对比结果。

## 5. 2026-10-14 年报事实复核增量

- `runs/annual_d2_remaining_raw_only_independent_review_windows_20261014_02/`：逐页复核 7 家公司的原 PDF 董事出席表，共 64 条报告期汇总事实；所有事件日期留空，运行清单 SHA256 为 `8e880f7a6f43fe4aa31f947af07e69e99b56e557e9fb7221740230caffe01ff8`。
- `runs/annual_d1_002008_wanglei_warning_independent_review_windows_20261014_01/`：在原 PDF 和深圳证监局来源封存件上独立复核大族激光一条事实；年报物理页 43，原 PDF SHA256 `cdd6a6642387b2620298e6c0fa9ad6288eb74b29c762663ed17bf929fed48469`。原候选状态未改，交易日期作为区间记录且 `event_date` 留空。
- `runs/annual_d1_601519_measures_independent_review_windows_20261014_01/`：独立核对大智慧年报原页、两份上海证监局决定和上交所监管警示 PDF，分列三个监管动作与三份原文坐标/哈希；事件期仅确定为 2022 年，`event_date` 留空。
- `runs/annual_d1_601377_subsidiary_measure_independent_review_windows_20261014_01/`：独立核对兴业证券年报物理页 107/印刷页 106与福建证监局决定〔2024〕123号；直接对象为关联资管公司，发行人未误列为直接监管对象。
- `runs/annual_fact_independent_review_overlay_windows_20261014_07/`：在保留的 `_06` 上追加上述兴业证券事实，累计 96 条复核事实、91 个唯一来源候选、13 家公司的选定批次交叉表，保留全部 39 家公司行。仍未覆盖 39 家公司全部事实，也不作真人专家认证。
- `runs/annual_d1_000802_beijing_penalty_independent_review_windows_20261014_01/`：复核北京文化原 2024 年报物理第 48 页，并重新访问北京证监局两份官方决定。分别记录对发行人的行政处罚与对个人娄晓曦的三年市场禁入；底层事实日期留空。发布清单 SHA256 `dce8da446f2e6c40ea794494d95084846c1f1617b0d0f1d980bc59c14ecc1632`。
- `runs/annual_fact_independent_review_overlay_windows_20261014_08/`：保留 `_07` 并追加上述两项事实，累计 98 条复核事实、92 个唯一来源候选、14 家公司的选定批次交叉表，仍保留全部 39 家公司行。发布清单 SHA256 `14cd39b68a2831e514e8ca9da23d57bad0f58a7ac36e130d3b5e3a9aedf7b0d7`；不代表事实穷尽或真人专家认证。
- `runs/annual_d3_002352_issuer_disclosure_independent_review_windows_20261014_01/`：复核顺丰控股原 2024 年报物理第 89 页（印刷页 088），原 PDF SHA256 `e17ec642bafcdade70524523a6fdda031d75accf57c034d96a3595933645025d`、250 页；保留 pypdf 页文、引句区间 `[59,268)`、页图及哈希。厦门生态环境局官方行政处罚目录和站内 API 按主体名、地址、行为日期及噪声处罚词查询，仍未找到决定原件；新事实仅确认年报披露，罚款金额及整改均只记作发行人自述，处罚决定日期留空。发布清单 SHA256 `c705026fa9286af4812d9e1a083ba0f054f3b76ce8bdb3f2c7847f41070f3e05`。
- `runs/annual_fact_independent_review_overlay_windows_20261014_09/`：保留 `_08` 并追加上述一条发行人披露事实，累计 99 条复核记录、93 个唯一来源候选、15 家公司，仍保留全部 39 家公司行。发布清单 SHA256 `278e9f12635cd24789a8c8e92b2fe4b8ee0171b8cb61cf532b2a6b9ac7c8e4d7`；原候选仍为 pending/正式接纳 false，新增复核范围不等于监管决定核实，也不代表事实穷尽或真人专家认证。
- `runs/annual_d1_000802_szse_disclosure_independent_review_windows_20261014_01/`：复核北京文化 2024 年报原 PDF 物理第 30 页与官方发行人 2022 年报更正公告原 PDF 物理第 1 页；分别保存报告和公告的原文、物理页图、引句、字符区间及 SHA256。两份发行人文件均记载 2022-01-13 收到深交所纪律处分决定、董事杜扬被通报批评；该日仅为发行人披露的收件日。深交所决定原件未定位，未推断发行人本身受处分，决定日和底层行为日留空。旧来源包中的字符区间未能在其 Windows 换行写入后的页文中复现；新运行基于源 PDF 重新抽取并保存可复现区间，原包未改。发布清单 SHA256 `f75e919873014cbbf55a87d010a1d6fd25a6de99b569aced09b7a4f11050d1b5`。
- `runs/annual_fact_independent_review_overlay_windows_20261014_10/`：保留 `_09` 并追加一条发行人披露事实，累计 100 条复核记录、94 个唯一来源候选、15 家公司，仍保留全部 39 家公司行。发布清单 SHA256 `214d04ba89cf1ab0a81429e15ee45322f80bf42e8311cb48f80c74dada320a9f`；该计数不代表事实穷尽或真人专家认证。

详细复核过程、物理页码/引句区间和失败尝试说明见[年报原文恢复与事实提取进度](../docs/年报原文恢复与事实提取进度_20261014_续.md)。
- `runs/annual_d4_auditor_opinion_independent_review_windows_20261014_01/`：逐条核对 39 家 2024 年报的财务报表审计意见，复算原 PDF 身份/SHA256/页数、页文和引句区间、页图与裁剪图哈希。16 条意见类型字段明确写明标准无保留意见，23 条意见段写明财务报表在所有重大方面公允反映；公告日期有来源，事件日期留空。上游 D3/formal false 保留，AI 独立复核不是真人专家认证；发布清单 SHA256 `fcd95cebcd545b2fb784ad773b9c4223f0947d4cff4e0b9d7f23e3de8b42443a`。
- `runs/annual_fact_independent_review_overlay_windows_20261014_11/`：在 `_10` 上追加上述 39 条，累计 139 条选定批次复核记录、133 个唯一来源候选、39 家公司、14 个复核运行；保留此前记录及全部公司基线行。发布清单 SHA256 `95cd8a0f29b13f5331268d834a1357ca6c6c25e8fed0a2b51805ca15adb324e3`。不代表公司事实穷尽或完整 D4 声誉覆盖。
- `runs/annual_d2_31_company_visual_review_windows_20261014_01/`：将 31 家公司的所选 D2 董事出席候选逐条回到原年报 PDF；31 个候选页及 3 个上下文页共视觉检查 34 页，原 PDF/页文/字符区间/引句哈希均匹配。发布清单 SHA256 `dd22449fcc422f557d2cde6327babe6e4b6f518fa436230df3fc027824a25b44`。
- `runs/annual_d2_31_company_attendance_independent_review_windows_20261014_01/`：31/31 所选记录通过原页独立复核；事件日期留空，逐公司每条仅代表选定事实，不表示穷尽或真人专家认证。发布清单 SHA256 `9f7520beeb4c2d0e6dca3d84589abe31a647aa6b00995eb2a4d3943ce7ebf879`。
- `runs/annual_fact_independent_review_overlay_windows_20261014_12/`：保留 `_11` 后追加 31 条，累计 170 条复核事实记录、164 个唯一候选、39 家公司；每家公司至少一条所选 D2 记录。上游正式接纳标签保持原样，事实范围仍不完整。发布清单 SHA256 `7aa8f7f82d2c08fcbb14b9eb50a5862818a663494cb8355d20775f2fb78cdd19`。
- `runs/annual_d2_review_backlog_windows_20261014_01/`：从 378 条 D2 候选索引中按候选 ID 与 overlay `_12` 匹配出 275 条待核验候选（31 家公司、31 份原 PDF、37 个物理页）；每条源 PDF/页文哈希及引句坐标复算通过。仅为待办候选清单，正式事实接纳数为 0。发布清单 SHA256 `53d5bdb16eff7d34436a01cc1162688ffdaf356904d2dc34522f5517b0f8fc44`。- `runs/annual_d2_pending_candidates_visual_review_windows_20261014_01/`：为 275 条未匹配的 D2 候选准备并渲染 37 个原 PDF 物理页（31 份报告），页面图与 PDF 哈希验证通过；发布清单 SHA256 `d858390a22deedd8b0a66634c1405450abdfb93464712756b5c802d70c996483`。
- `runs/annual_d2_pending_candidates_independent_review_windows_20261014_01/`：275/275 条候选逐页对照原报告表格，保存原文引句和坐标、页面图及 SHA256，事件日期留空；不是真人专家认证。发布清单 SHA256 `50c297ea3b3350ff68f9d366ef12e1fcb09300821fe43e01fb32ca127bcd4a89`。
- `runs/annual_fact_independent_review_overlay_windows_20261014_13/`：保留 `_12` 并追加 275 条；累计 445 条选定批次复核记录、439 个唯一候选、39 家公司。当前 378 条 D2 候选索引全部有复核记录，但候选索引穷尽性未知，公司事实范围未完成。发布清单 SHA256 `90c6afe199f69dc06a5dda1e569bb7825249455a953eccaec81a080c174aa701`。
