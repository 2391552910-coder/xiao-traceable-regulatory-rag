# 聚焦主问题候选稿

当前稿件：`年报与法规双源RAG_聚焦主问题候选稿_待终审.docx`。它由2026-10-28完整扩展候选稿派生，保留原文件不变。

## 研究范围

主问题限定为：在上市公司年报与法规问答中，双源分路检索相较合并检索是否改善回答评分及证据供给。主稿保留20家公司、60题、386条有效双人评分以及原有检索、来源缺失、预算回放和误差分析。扩展稿中的跨年度/Agent生成、交互式聊天案例、自动评分校准和Agent提示修复章节已从该主稿副本移出；这些已运行结果仍保存在原合并扩展稿，不会被当作主实验或删除。

## 参考发表论文的设计

- KBS：Siddharth & Luo, “Retrieval augmented generation using engineering design knowledge,” *Knowledge-Based Systems* 303 (2024), 112410. 聚焦领域知识抽取及其RAG应用。
- Information Sciences：Alier et al., “Closing the acronym gap in educational retrieval with ontology-guided augmentation,” *Information Sciences* 740 (2026), 123181. 聚焦缩写导致的检索失效，以少量干预和对应检索指标比较。
- Neurocomputing：Wang et al., “Learning to break: Knowledge-enhanced reasoning in multi-agent debate system,” *Neurocomputing* 618 (2025), 129063. 以多智能体方法创新为核心，在多个数据集上比较。

这些论文用于确定研究问题和实验结构，不作为篇幅、图表数量或录用保证的标准。

## 本地验收

- WPS只读PDF渲染25页；全部页面完成视觉检查。
- 19张Word表格、13个内嵌图形；参考文献连续编号1–30，正文引用均可映射到参考文献。
- 该稿仍待全文内容终审、作者/基金/披露信息确认及目标期刊模板适配。没有新增模型调用、自动标签或人工标签。
- 法规日期口径已补充复核：DOC100索引日期为审议通过日，DOC128为公布日，DOC120为施行日；稿中将“晚于报告年度”限定为索引时间风险，不作适用判断。DOC343是2023年修改决定，不等于合并历史全文。
- 2026-10-28措辞审计：将“降低复核成本/证据支持可审计设计必要性”改为可回放记录的用途说明和受限设计建议；明确未实测决策风险、复核成本或人员工时。WPS只读渲染仍为25页，变更涉及第21–24页，均已检查。未新增模型调用或人工标签。
- 校验详情：`focused_candidate_audit.json`；最新WPS渲染回执位于`render_qa_focused_final_v5/native_render_receipt.json`；页面图和PDF作为本地排版检查材料保留。
