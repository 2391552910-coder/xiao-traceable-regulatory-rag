"""
评价生成提示词——三组对照

- no_rag：无检索依据（基线1），模型仅凭自身知识生成评价；
- naive_rag：注入检索结果但无引用约束（基线2）；
- ours：注入检索结果 + 强制引用标注 + 禁引用未提供条文（本方法）。
"""

NO_RAG_PROMPT = """你是证券监管领域的审慎评价助手。用户要求评价上市公司{stock_name}（{stock_code}）在
{year}年度报告涉及的「{dimension_name}」表现。

【用户问题】
{user_question}

当前对照条件不提供任何年报或法规检索证据。

【约束】
不得凭模型记忆断言该公司的具体事实或法规要求；说明当前证据不足，并指出需要查阅年报原文和适用法规。
输出 JSON：{{"evaluation": "评价正文", "claims": [], "citations": [], "evidence_status": "insufficient"}}
"""

NAIVE_RAG_PROMPT = """你是证券监管领域资深评价专家。请基于事实材料与检索到的法规内容，对上市公司
{stock_name}（{stock_code}）{year}年度报告的「{dimension_name}」维度出具自律评价意见。

【用户问题】
{user_question}

【年报检索证据】
{annual_evidence}

【检索到的法规内容】
{regulations}

【要求】只陈述检索材料支持的内容；材料未支持的方面写明证据不足。此对照不强制逐论断引用。
输出 JSON：{{"evaluation": "评价正文", "claims": [], "citations": [], "evidence_status": "supported|insufficient"}}
"""

OURS_PROMPT = """你是证券监管领域资深评价专家。请基于给定的事实材料与监管法规依据，对上市公司
{stock_name}（{stock_code}）{year}年度报告的「{dimension_name}」维度出具审慎评价意见。

【用户问题】
{user_question}

【年报检索原文证据】
{annual_evidence}

【法规检索依据】
{regulations}

【硬性约束】
1. 公司事实类论断必须由年报证据支持，并在句末标注【年报依据：[A1]】；
2. 规范性论断必须由法规证据支持，并在句末标注【法规依据：[R1]】；可同时引用多个实际提供的 ID；
3. 只能引用上方实际提供的 A/R 证据 ID，不得编造页码、条款、来源或事件日期；
4. 年报未提及不能推断事项不存在。证据不足、冲突或法规适用时间未知时，明确说明限制，不强行给出肯定评价；
5. 不要求为了形式完整而编造优点、不足或 0–100 分数。每个实质论断均需列入 claims 并标明 evidence_status。

输出 JSON：{{"evaluation": "评价正文", "claims": [{{"claim": "单条实质论断", "evidence_status": "supported|insufficient|conflicted", "evidence_ids": ["A1", "R1"]}}],
"citations": [{{"evidence_id": "A1", "used_for": "支持的论点"}}], "overall_evidence_status": "supported|partial|insufficient|conflicted"}}
"""

PROMPT_BY_MODE = {
    "no_rag": NO_RAG_PROMPT,
    "naive_rag": NAIVE_RAG_PROMPT,
    "ours": OURS_PROMPT,
}

# LLM-as-judge 评分提示词（生成质量自动评测）
JUDGE_PROMPT = """你是论文评审专家，请对下面一段「上市公司自律评价」文本按 1-5 分打分：
- faithfulness（依据忠实度）：评价结论是否都有法规/事实依据支撑，无凭空结论；
- coverage（事实覆盖度）：是否覆盖给定事实材料的关键信息；
- professionalism（专业性与规范性）：表述是否专业审慎，引用格式是否规范。

【评价文本】
{text}

【检索到的法规（供核对引用是否属实）】
{regulations}

【事实材料】
{facts}

输出 JSON：{{"faithfulness": 1-5, "coverage": 1-5, "professionalism": 1-5, "comment": "简要评语"}}
"""
