Warning: truncated output (original token count: 19126)
Total output lines: 402

# 年报与法规双源检索增强生成
> **当前执行约束（2026-10-29）：后续不新增、委托或回收人工标注/盲审。**已有评分与参考只按原始来源保留；空白模板归档、不作为待办或投稿门槛。旧方案若要求补标注，以本条为准：使用可复算既有数据、已有且任务适配的参考和明确标注局限的自动诊断；无兼容金标准时将相关指标记为未测，不以代理指标冒充语义质量。

## 双源生成的事项日期筛选（2026-10-29）

调用 `generate_dual_corpus_answer` 时，可显式传入 `temporal_filter=True`、`target_date="2024-12-31"` 和 `target_date_role="company_event_date"`；完整日期必须已出现在公开查询中。筛选在法规检索截断前进行，默认保留版本信息未知的来源，并在返回值 `temporal_filter_audit` 中记录处理过程；启用筛选时，逐来源时间关系及未验证法律适用性的提示也会传入生成上下文。默认不启用筛选，也不会从报告年份推断事项日期；声明区间匹配不证明法规法律适用性。

命令行入口 `scripts/dual_corpus_rag.py` 可在原有查询和索引参数之外加入 `--temporal-filter --target-date 2024-12-31 --target-date-role company_event_date`。日期必须出现在 `--query` 中；输出的 `answer_and_sources.json` 保存筛选审计。`--unknown-temporal exclude` 会排除日期未知的法规，需要显式选择，未知并不代表不适用。

已用一份真实年报的前两页和一份法规文本执行[离线流程冒烟检查](results/runs/temporal_cli_real_data_smoke_20261029_02/receipt.json)：TF-IDF 检索和模板输出成功，51 个法规片段的区间信息均未知并被保留。测试日期是人为设定的流程输入，不是已核实的公司事项日期；此检查不衡量回答质量或法律适用性。

同一资料的[提示捕获检查](results/runs/temporal_prompt_real_smoke_20261029_01/receipt.json)确认，5 条检出法规在模板生成器收到的提示中均标明时间关系未知及法律适用性未验证；这不证明真实模型会遵守该提示。

## 论文评测表述对齐（2026-10-29）

[中文候选稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_无新增人工标注候选稿_待终审.docx)与[英文工作稿](results/paper/english_translation_current_20261028_01/Controlled_Evaluation_Dual_Source_RAG_no_new_human_labels_20261029.docx)将结论中的后续评测表述调整为不新增人工标注，并说明缺少独立可信参考时自动匹配仅供诊断。已有人工评分及其历史来源保留，实验数据和结果未改变。变动页经 WPS 渲染检查。

## BM25 标题拼接开发对照（2026-10-29）

在相同 40 条 AI 参考开发查询上，仅向每个索引块正文前加入文档标题后重新运行 BM25。前 5 条平均参考覆盖由 0.241 降至 0.219，其中 2 题上升、31 题不变、7 题下降；前 10 条由 0.341 至 0.345。结果不支持直接启用该改动，默认检索配置未变。[逐题对照](results/runs/ai_development_bm25_title_20261029_01/comparison.json)和[脚本](scripts/compare_ai_development_bm25_title_20261029.py)已保存。该已暴露开发集的 AI 参考不完整且未经独立核验，覆盖不能当作标准语义 Recall；未新增标签或模型调用。

## AI 开发参考上的离线 BM25 诊断（2026-10-29）

在冻结的 7,899 个法规、处罚和公告条款块中，使用已有 40 条 AI 双通道与仲裁参考查询运行 BM25：前 5 个结果中有 23/40 题至少匹配一项参考，前 10 个结果为 29/40；逐题参考平均覆盖分别为 0.241 和 0.341。参考并非完整或经独立核验的相关性集合，未匹配不等于不相关，上述值不能当作标准语义 Recall 或 Precision。本次仅作暴露开发集的法规语料诊断，不评估年报、双源回答或法规时点适用。[逐题结果及输入哈希](results/runs/ai_development_bm25_20261029_02/result.json)；[复现脚本](scripts/run_ai_development_bm25_20261029.py)。无模型调用及新增人工标注。

## Windows 文件名兼容（2026-10-29）

仓库中的 DOC304 文件使用全角 `＊` 替代 Windows 不允许的半角 `*`，文件内容不变；既有语料哈希仍通过兼容映射使用历史名称。历史数据清单保留原始名称作为记录。Git 属性禁止冻结语料、历史参考、实验文件和代码检出时转换换行符，以维持字节哈希；已有工作区需在保留本地修改后重新检出对应文件才会应用。离线 CI 检查 Windows 路径和相关 Git 属性。

复现范围：本分支已验证保存的 Qwen 格式提示对照与 Agent 配对分析可重新计算。旧监管开发基准已补入加载模块和冻结清单，可校验 319 份文档、7,899 个文本块与 40 条查询的输入一致性；该基准使用既有 AI 双通道与仲裁参考，仅用于开发，不代表独立人工金标准或泛化性能。本次未新增标签。

## 表格解析代码同步（2026-10-29）

论文草稿分支同步表格解析分支的 v1.11 解析器、索引、命令行和测试夹具；相关功能的独立开发记录仍见 [表格解析 PR #4](https://github.com/2391552910-coder/xiao-traceable-regulatory-rag/pull/4)。本地定向联合回归 63 项通过；这不等于对年报表格解析准确率或泛化能力的独立验证。未新增模型调用或人工标注。

2026-10-29 对当前提交 `b59bcb4` 重新运行年报解析、表格证据、开发审计及补充检索四组测试：**92 项通过，0 失败**；仅有 jieba 的 `pkg_resources` 弃用警告。测试覆盖规则与接口回归，不提供独立标签，不能据此计算或宣称年报字段准确率、检索 Precision/Recall/F1 或生成回答质量。未新增模型调用或人工标注。

## 来源编号校验修正（2026-10-29）

双源生成主流程根据检索结果实际分配的来源编号进行引用解析，避免将证据正文中形如 `[A99]` 的普通文字误判为来源。诊断同时检查 `claims` 中的来源编号，标记无有效编号但自称有支持的论断。相关引用诊断和编号审计测试已纳入离线回归工作流。`citation_diagnostics.supplied_id_method` 标明校验方式；直接调用评价器且未传入编号清单时，为兼容旧调用仍使用文本扫描，该方式不能排除正文伪编号。编号存在不证明引用支持或法规适用；本次未新增模型调用或人工标注。

## 生成引用诊断更新（2026-10-29）

双源生成结果增加 `citation_diagnostics`，记录引用列表格式错误、无法解析的编号及正文中年报／法规标签与编号类型不一致。无检索模式不会将未放入提示词的检索材料标记为已提供；原始输出仍保留。编号解析仅表示编号出现在供应给模型的材料中，不证明语义支持或法规适用性。本次为代码与离线测试，未改变历史实验结果、未新增人工标注或模型调用。

## 当前主稿：引用编号审计（2026-10-29）

[中文候选稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_引用编号审计候选稿_待终审.docx)和[英文工作稿](results/paper/english_translation_current_20261028_01/Controlled_Evaluation_Dual_Source_RAG_citation_id_audit_20261029.docx)补充[机械引用编号审计](results/runs/qwen_schema_citation_audit_20261029_01/citation_audit.json)：格式示例条件下，结构类型合规为3/8，但只有2/8条回答的三个字段均含非空且属于输入材料的有效来源编号；另一条将日期写入引用列表。此检查不证明引用支持答案。未新增模型调用或人工标注；中文23页、英文25页，变动页经WPS渲染检查。

## 当前主稿：事后格式提示对照（2026-10-29）

[中文候选稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_格式提示补充候选稿_待终审.docx)和[英文工作稿](results/paper/english_translation_current_20261028_01/Controlled_Evaluation_Dual_Source_RAG_schema_prompt_development_20261029.docx)补充同一Qwen3-0.6B的8题格式提示开发试验。既有助手提取且事后勘误参考下，结构合规从0/8到3/8，成员宏F1从0.651到0.678，日期宏F1从0.600降至0.558，会议次数匹配从3/8到6/8，三字段全匹配均为1/8。[结果与逐题数据](results/runs/qwen_schema_prompt_score_20261029_01/summary.json)；[图11](results/runs/qwen_schema_prompt_figures_20261029_01/schema_prompt_development.png)。提示是观察原答案后设计，属于事后开发而非独立验证；每题各一次采样，输入长度不同，参考未经独立验证，结构合规不代表引用支持。未新增人工标注。WPS渲染并检查变动页，中文23页、英文25页。

## 前版候选：跨模型与 Agent 对照（2026-10-29）

[中文候选稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_跨模型与Agent对照候选稿_待终审.docx)与[英文工作稿](results/paper/english_translation_current_20261028_01/Controlled_Evaluation_Dual_Source_RAG_English_Working_Translation_cross_model_agent_20261029.docx)在8题跨模型补充之外，加入既有K3 Agent与三轮固定证据修订的[配对复算](results/runs/agent_pairs_reanalysis_20261029_01/agent_pair_comparison.json)及[图10](results/runs/agent_pairs_figures_20261029_01/agent_observed_pairs.png)。两条件各在不同题目失败，余下6对覆盖4家公司；按既有助手提取、事后勘误且未经独立裁定参考，三字段全匹配为4/6与5/6，成员宏F1为0.833与0.985，日期宏F1为0.786与0.952（Agent与修订）。两者各记录18次调用，但供应商token总量分别为102600与97441，最终证据亦不同；这不是完全预算匹配或因果实验。原参考和勘误版、失败、逐题配对及界均保留；未新增人工标注或模型调用。WPS渲染中文23页、英文25页，受影响页面已检查；结果不证明普遍效果或期刊录用。详见[审计](results/runs/agent_pairs_reanalysis_20261029_01/paper_update_audit.json)。

## 当前投稿主线：双源分路检索与合并检索（2026-10-29）

[21页主线候选稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_附录统计单位澄清候选稿_待终审.docx)聚焦双源分路检索与合并候选检索，含12张表和8幅图。更正BM25参考文献[7]后，稿件 SHA-256 为 `e928a70e0f3b2f44e01dd01bd43bd7bbed48ae851e207b308f8bf73367864b69`；[修订与版面收据](results/runs/core_candidate_reference_7_correction_20261029_01/core_candidate_reference_7_correction_receipt.json)记录只改了书目段落，Codex 渲染21页中仅第19页变化且已目视检查。本轮未使用WPS、未新增模型调用或人工标注。当前稿的段落和12张表已按范围收据重新绑定到当前 SHA，详见[当前稿审计覆盖桥](results/paper/condensed_candidate_20261028_01/core_candidate_scoped_audit_coverage_20261029.json)；其中表6–11与已通过数字复算的版本逐单元格一致，细目见[表格继承核验](results/paper/condensed_candidate_20261028_01/core_candidate_numeric_table_inheritance_20261029.json)。覆盖桥记录已恢复并校验的历史来源、未完成的全文语义审查和指标边界，不能视为整稿终审。下方跨模型/跨年/Agent材料是独立扩展候选，均为小样本探索结果，不并入主线泛化结论。

## 扩展候选：跨模型与 Agent 年度分层复算（2026-10-29）

[中文候选稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_跨模型与Agent年度分层复算候选稿_待终审.docx)补入既有8题 Qwen3-0.6B 与 K3 服务别名对照的年度分层结果。结果由[复算脚本](scripts/analyze_qwen_cross_model_year_20261029.py)从已保存输出生成，[稿件更新脚本](scripts/update_cross_model_manuscript_year_sensitivity_20261029.py)记录输入和输出哈希。

| 报告年度 | 成员宏 F1（Qwen/K3） | 日期宏 F1（Qwen/K3） | 会议次数精确匹配（Qwen/K3） | 三字段全匹配（Qwen/K3） | 严格结构及引用列表合规（Qwen/K3） | Qwen 格式异常引用项 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023（4题） | 0.663 / 1.000 | 0.672 / 1.000 | 2/4 vs 4/4 | 1/4 vs 4/4 | 0/4 vs 4/4 | 31 |
| 2024（4题） | 0.638 / 0.949 | 0.528 / 0.906 | 1/4 vs 4/4 | 0/4 vs 2/4 | 0/4 vs 4/4 | 35 |

计分采用既有助手提取参考及一次输出后的勘误版；参考未经独立裁定。两年度使用同一4家公司，每年仅4题，每题每模型生成一次；模型规模、计算量和输出预算也不同。因此该分层只作描述性复算，不能证明独立时间迁移或模型族泛化，也不据此作显著性推断。字段 F1 和结构合规不代表引用语义支持、检索 Precision/Recall 或答案 Accuracy。

本轮仅复用保存结果，无新增模型调用或人工标注。最新版中文稿为23页；Codex 使用 `render_docx.py`、LibreOffice 与 Poppler 重新生成23页 PNG，全程未使用 WPS。结论段现明确本项目不新增人工标注；无匹配且独立可信的既有参考时，相应检索或答案质量指标保持未测，不以位置覆盖或结构合规等代理量替代。此次仅第20页变化，已按原始分辨率检查；其余22页 PNG 与前版哈希一致，详见[版式 QA 收据](results/runs/qwen_cross_model_year_sensitivity_20261029_01/render_qa_receipt.json)。[论文数值、图形与政策一致性审计](results/runs/manuscript_claim_consistency_20261029_03/claim_audit.json)的25项检查通过，核对跨模型、年度分层、Agent 正文数字、图9/图10与源图哈希、来源版本绑定和无新增标注表述；不验证参考答案正确性、引用语义支持或期刊录用水平。结果文件：[年度分层摘要](results/runs/qwen_cross_model_year_sensitivity_20261029_01/year_stratified_summary.json)、[模型汇总](results/runs/qwen_cross_model_year_sensitivity_20261029_01/year_stratified_models.csv)、[配对结果](results/runs/qwen_cross_model_year_sensitivity_20261029_01/year_stratified_pairs.csv)、[稿件更新收据](results/runs/qwen_cross_model_year_sensitivity_20261029_01/manuscript_update_receipt.json)。该探索性结果不构成期刊分区或录用保证；英文工作稿尚未同步本次年度分层结果。

本轮还更正了参考文献[7]的卷期页码，并依据原论文首页与出版方推荐引文统一著录。[书目与引文范围审计](results/paper/condensed_candidate_20261028_01/candidate_bibliography_source_audit_20261029.md)和[版本绑定及 Codex 渲染复核收据](results/runs/citation_reference_correction_20261029_01/candidate_citation_rebind.json)记录了书目编号覆盖、当前稿哈希和23页渲染差异。该审计不等于355份回答的语义复核，也不证明期刊录用水平。

## 历史候选：跨模型实跑（2026-10-29）

[中文候选稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_跨模型实跑候选稿_待终审.docx)和[英文工作稿](results/paper/english_translation_current_20261028_01/Controlled_Evaluation_Dual_Source_RAG_English_Working_Translation_cross_model_20261029.docx)新增Qwen3-0.6B与K3服务别名的8题探索性对照及[图9](results/runs/qwen_cuda_cross_model_figures_20261029_02/cross_model_exploratory.png)。两者均完成8题；以既有助手提取、事后勘误且未经独立裁定的参考为准，成员宏F1分别为0.651和0.975，日期宏F1为0.600和0.953，严格结构合规为0/8和8/8。字段分数即使结构不合规也计算；不等于引用语义支持、法规适用或检索P/R。模型容量、采样和输出预算不匹配；四家公司、两年度、每题一次的结果不能支持跨模型或跨年普遍泛化。原参考和勘误版均已报告，无新增人工标注。[结果与限制](results/runs/qwen_cuda_cross_model_score_20261029_04/summary.json)；[稿件及输入审计](results/runs/qwen_cuda_cross_model_score_20261029_04/paper_update_audit.json)。WPS只读复核中文版22页、英文版24页；本稿仍待投稿前终审。

## 历史候选：历史法规来源更正（2026-10-29）

[中文主稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_历史法规来源更正候选稿_待终审.docx)与[英文工作稿](results/paper/english_translation_current_20261028_01/Controlled_Evaluation_Dual_Source_RAG_English_Working_Translation_historical_sources_20261029.docx)更正历史第182号令的范围：冻结索引含其官方PDF的22页，且该文档不在冻结排除清单；已保存的1200条候选排序未出现该文档。这不证明语义相关或具体法规适用。[索引审计](results/paper/condensed_candidate_20261028_01/historical_order_182_index_audit_20261029.json)。60题预处理记录显示该文档22个片段均被时间筛选保留，但目标日期均未提供；详见[时间筛选审计](results/paper/condensed_candidate_20261028_01/order_182_temporal_scope_manifest_verified_20261029.json)及[复核脚本](scripts/audit_frozen_temporal_source.py)。筛选保留不证明后续路由、语义相关性或法规适用性。不新增人工标注、模型调用或评分。

## 历史候选：DOC343 来源更正（2026-10-29）

[中文主稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_DOC343来源更正候选稿_待终审.docx)与[英文工作稿](results/paper/english_translation_current_20261028_01/Controlled_Evaluation_Dual_Source_RAG_English_Working_Translation_DOC343_correction_20261029.docx)更正DOC343来源描述：文本版含2023年修改决定及重新公布全文，冻结方案排除该文本版，但收录对应59页OFFICIAL-DOC343 PDF；G2冻结Top-10中7题检出PDF物理第2页。该计数不验证语义支持或个案适用性。详见[证据与修订审计](results/paper/condensed_candidate_20261028_01/doc343_correction_audit_20261029.json)。历史文档中“DOC343仅为修改决定”的说法已被更正。本轮未新增模型调用、人工标注或改变实验评分。

## 评测安排更新（2026-10-29）

遵照用户决定，后续不再新增人工标注；现有双人盲审空表不作为论文工作的前置条件。历史人工评分及参考证据保留真实来源。使用既有排序与参考定位开展离线分析；位置命中不等于语义相关，不能作为标准 Precision、Recall、F1、nDCG 或答案正确率。

在 6000 token 预算下，40 道法规 PDF 参考题共 120 次参考位置：缓存检索的合并/分路配置分别命中 0/120 和 7/120；新运行 BM25 两种配置均为 0/120。另 20 道使用整份 TXT 作为法规参考的题目，BM25 合并/分路分别匹配 18/20 和 20/20 个来源。两种参考粒度不能合并解释为页级检索效果。上述数字来自既有回放，没有新增实验。


在分路配置下，另有33/60题的严格法规参考位置覆盖为零，但检索文本与参考引文出现至少一处12字符连续重合。该词面诊断可能包含通用措辞或不同版本，不证明法规等价、语义支持或时点适用；见[诊断汇总](results/paper/substantial_revision_20261023_01/retrieval/alternate_law_audit_receipt.json)与[逐题数据](results/paper/substantial_revision_20261023_01/retrieval/alternate_law_source_per_question.csv)。逐题表可复算汇总计数；[原始诊断脚本](scripts/audit_alternate_law_sources_20261023.py)供方法审阅。完整重跑仍需冻结索引、参考材料及脚本依赖；该历史脚本使用固定输出目录并会覆盖同名结果，运行前应先保留原件。

## 历史英文工作稿对齐（2026-10-29）

[英文对齐稿](results/paper/english_translation_current_20261028_01/Controlled_Evaluation_Dual_Source_RAG_English_Working_Translation_evidence_units_20261029.docx)已同步其中文来源版本至当前稿之间的页码记录、引言、来源缺失配对及缺失界、回放范围、BM25文献和附录计数修订。WPS导出23页，变动页已检查；[修订收据](results/paper/english_translation_current_20261028_01/english_current_chinese_changes_receipt_20261029.json)。其后收紧评分者措辞并澄清缺失数据界的上下端点分别平均，见[评分措辞收据](results/paper/english_translation_current_20261028_01/english_rater_wording_receipt_20261029.json)和[缺失界措辞收据](results/paper/english_translation_current_20261028_01/english_bounds_wording_receipt_20261029.json)。已将123条去重参考证据统一表述为证据记录而非123份来源文档，见[证据计数收据](results/paper/english_translation_current_20261028_01/english_evidence_units_receipt_20261029.json)。中间稿和WPS预览保存在本地；[中英文结果表5–11数值核对](results/paper/english_translation_current_20261028_01/bilingual_numeric_tables_receipt_20261029.json)比较166个数据单元格，未发现数字差异；该检查不验证表头含义或原始实验数据。英文稿仍需全文语义终审及目标期刊格式适配。

## 历史候选：来源页码记录边界澄清（2026-10-29）

- 当前主文候选：[页码分层核验修订稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_页码分层核验修订候选稿_待终审.docx)。修订第38段：检索索引使用PDF物理页序；人工核验时另记可见印刷页码，避免暗示运行索引普遍存储印刷页码。
- 主文仍为21页、12表。WPS重渲染后仅第5页变化并已检查。详见[修订审计](results/paper/condensed_candidate_20261028_01/page_provenance_revision_audit_20261029.md)和[哈希/渲染收据](results/paper/condensed_candidate_20261028_01/page_provenance_revision_receipt_20261029.json)。
- 本修订只处理来源定位表述，不代表整稿终审、期刊格式适配或二区录用结论。

## 历史父稿：引言检索表述收窄（2026-10-28）

- 引言表述收窄父版本：[引言检索表述收窄稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_引言检索表述收窄候选稿_待终审.docx)，SHA-256 `76bca23f53ffac54da086f908397cae56b94586e43c6cc142734c10d12fedf0a`。只收窄引言中对传统检索的泛化陈述；BM25文献更正保留。该次仅正文段落10变化，12张表、31条参考文献及其他段落不变；WPS渲染21页，仅第2页变化且已检查。
- 配套核查：[引言第9–14段审计](results/paper/condensed_candidate_20261028_01/introduction_claim_audit_paragraphs_9_14_20261028.md)、[方法与检索文献审计](results/paper/condensed_candidate_20261028_01/retrieval_method_claim_audit_paragraphs_23_24_20261028.md)、[评分量表审计](results/paper/condensed_candidate_20261028_01/rubric_claim_audit_current_candidate_20261028.md)及[版本/渲染收据](results/paper/condensed_candidate_20261028_01/intro_retrieval_framing_revision_receipt_20261028.json)。研究范围及已发表论文参照见[范围决策](docs/文献参照后的论文范围决策_20261028.md)。
- 本稿仍待整稿语义终审、作者/投稿信息和目标期刊格式适配；不表示达到二区录用水平。

## 2026-10-28 回放范围限定修订候选（历史父版本）

- 回放范围限定父版本：[回放范围限定修订稿](results/paper/condensed_candidate_20261028_01/年报与法规双源RAG_统一主文_回放范围限定候选稿_待终审.docx)，SHA-256 `dd442f55b34faec6b31a330578ed55df66918e8c719aeec22304e49608c2be91`。将讨论段回放陈述限定为一个问题、8种检索配置、16次成功候选检索的通道候选/融合/最终排序算术核验，并明确其不验证语义相关性、主实…7126 tokens truncated… 可用[supplement_evidence_budget.py](scripts/supplement_evidence_budget.py)直接导出联合材料及提示，已实际导出5921-token packet，全程0模型调用。新的生成质量仍为空，独立人工复核仍未完成。

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


