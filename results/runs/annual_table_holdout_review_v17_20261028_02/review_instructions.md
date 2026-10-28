# 留出复核标注说明

## 盲审顺序

1. 先只看 `blind_review.html` 的原始PDF页图，填写 `page_review_template.csv`，记录每页是否存在本项目范围内的治理表格及漏检数量。对有预测表格的页，`false_positive_table_ids` 必须明确填 `none` 或分号分隔的误检表格ID。
2. 用 `missed_table_template.csv` 为每页填写 `page_review_complete=yes`；每个漏检表格新增一行，填 `gold_table_id`（人工编号）、`gold_category`、`missed_by_parser=yes`、复核者和备注。确认本页没有漏检时，在原空白行填写 `missed_by_parser=no` 和复核者；不完整复核保持 `page_review_complete` 为空。
3. 再查看 `review.html` 和 `page_predictions.jsonl`。在 `table_review_template.csv` 中逐条预测填写 `match_status=matched` 或 `false_positive`；匹配项填 `gold_table_id` 和人工类别。分类只能按页面证据确定；证据不足填 `unclassified_table`，不要猜测。
4. 在 `continuation_review_template.csv` 中逐条填写 `gold_continuation=yes/no`。若为续表，补填人工确认的左右表编号。即使解析器没有接受连接，也要依据原页独立判断。
5. 每位复核者单独复制并填写整套模板；不要把多人意见先合并成一个标签。解决分歧后另存裁决版，保留原始复核表。

## 可计算范围

- 表格检测：逐表 TP/FP/FN、Precision、Recall、F1；页级有/无表格的 Precision、Recall、F1 另算。
- 类别：对匹配表格计算逐类 Precision、Recall、F1，并将漏检表计为对应类别 FN。
- 跨页连接：根据 `gold_continuation` 与解析器是否接受连接计算 TP/FP/FN、Precision、Recall、F1。
- 指标仅代表这三份事后选择的报告、治理关键词页及相邻页，不代表随机样本、全报告任意表格或端到端RAG效果。

`score_annual_table_review.py` 只在表级和边界级标签完整且包含复核者身份时计分。空白模板不是结果；模型或作者自检不能标记为独立人工复核。跨页指标限于模板枚举的相邻页预测区域组合。

