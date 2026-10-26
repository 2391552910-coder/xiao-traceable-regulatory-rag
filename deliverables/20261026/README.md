# 2026年10月26日研究更新

本次发布2026-10-23已执行的研究记录，无新生成模型调用。

- [英文全文](Dual_source_RAG_new_company_validation_EN.docx)与[中文修订稿](年报与法规双源RAG_新公司留出与标签勘误修订稿.docx)，分别18页和32页，已渲染逐页核查。原稿字节未更改。
- [汇总指标](metrics_summary.csv)、[逐题指标](../../results/paper/heldout_validation_20261023_01/heldout_metrics_corrected.csv)、[原研究有效输出评分记录](primary_quality_per_output.csv)。原研究和新公司指标口径分开。
- [新公司原始记录与标签](../../results/paper/heldout_validation_20261023_01/)包含40个最终单元、71条保存调用、一条响应缺失请求、两版参考与分析、冻结协议和来源地址。公开记录不含密钥，原PDF不上传。
- [离线评分脚本](../../scripts/score_heldout_validation_20261023.py)：Python>=3.11标准库，分别不加参数或加`--corrected`复算两套结果。
- [下一步](NEXT_STEPS.md)、[SHA256清单](FILE_MANIFEST.json)。清单不包含自身与仓库说明文件，记录各交付文件字节身份。

新增参考由AI助手提取并核查；尚未经独立人员裁定。勘误在看过回答后发现，未重新生成回答。Agent三字段全对4/8，K3单次6/8，未证实Agent优势。Qwen本地推理无输出，跨模型族性能未完成。保留HTTP失败、输出额度空答案与远端执行未知，不虚构用量。

论文作者、单位、基金及其他投稿声明须据实定稿。GitHub发布不等于正式同行评审或期刊录用。
