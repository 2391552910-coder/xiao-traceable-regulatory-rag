# 留出集双阶段盲审与计分说明

## 阶段一：只做盲标，不查看解析预测

只打开同目录 `blind_review.html`，不要打开 `review.html`、`page_predictions.jsonl`、`prediction_gold_match_template.csv` 或 `accepted_continuation_predictions.jsonl`。

1. 在 `gold_table_blind_template.csv` 为每页登记所有实际表格区域（包括治理关键词页邻页上出现的其他主题表格）。填写唯一人工 `gold_table_id`、人工类别及归一化框 `[x0,y0,x1,y1]`（范围0–1，按整页宽高归一化）。每页无表时将原行 `gold_table_id` 填 `NONE`、`review_complete=yes` 和复核者。若有表格，原行填写一个表格；每多一个表格复制一行并填写另一个ID。类别按可见表头/内容填写；无明确领域类别的真实表格标为 `other_table`，不要遗漏。
2. 在 `gold_continuation_blind_template.csv` 检查每个相邻物理页边界。无续表时填 `gold_continuation=no`；有一组续表时填 `yes` 并填写左右人工表格ID；同一边界有多组续表时复制行。每个边界必须有 `review_complete=yes` 和复核者。若某一页没有列入复核包，不能推断跨该页没有续表；本指标只覆盖模板中的相邻页边界。
3. 保存第一阶段副本并记录复核者、日期及文件哈希。第二位复核者应独立复制原始空模板完成同样工作。先合并/裁决盲标分歧，再查看预测。

## 阶段二：揭示预测并做一对一匹配

完成并封存阶段一后，才查看 `review.html` 和 `page_predictions.jsonl`。在 `prediction_gold_match_template.csv` 为每个预测表格填 `match_status=matched` 或 `false_positive`。匹配项填阶段一的 `gold_table_id`；误检不填金表ID。每个人工金表最多匹配一个预测表。类别使用阶段一封存的金表类别，不能因为解析器输出而改写。

## 计分与边界

`score_annual_table_review.py` 要求三张标签表完整、引用的金表ID有效且逐页误检/漏检清楚，然后计算页级和表级Precision、Recall、F1，逐类指标，以及跨页连接指标。跨页指标以预测器实际接受的边作为预测，和阶段一金续表边集合匹配；被漏检的表或边将计为FN。

每位复核者应在独立副本上分别计分并保留原表；分歧需另存裁决表。复核者字段只记录身份，不能由脚本证明其独立性。样本是事后选择的三份2024报告，仅覆盖治理关键词页及包内相邻页；不能代表随机样本、完整年报、跨年度泛化或端到端RAG效果。空白模板、作者/AI自查都不是独立人工指标。

