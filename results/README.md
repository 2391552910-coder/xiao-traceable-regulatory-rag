# 实验产物说明

更新：2026-10-26；实验记录日期：2026-10-23。

## 最新公开结果

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

