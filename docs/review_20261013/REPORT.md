# PR #1 审阅与数据准备交接（2026-10-13）

审阅对象：https://github.com/2391552910-coder/xiao-traceable-regulatory-rag/pull/1

初次核验时 PR 为 open/draft，base `f14a89c5c2e9c17b24e1d68a2ea343b282cef062`，head `2a7933783426d64f88fbe386050ac173fbd7a255`。之后检测到上游新增提交 `fba017153d0e2f8e955c29db503880b7c9125e93`，已重新获取并整合。最终交付工作区为 `/workspace/xiao-integrated`、分支 `review-pr1-integrated`，基于该最新提交；旧 `/workspace/xiao-review` 仅保留初轮快照。原工作区 `/workspace/xiao-traceable-regulatory-rag` 的 `work` 分支保持不变。未提交、推送、合并或发布 GitHub 评论。未发现本环境的额外 AGENTS.md、.agents/skills 或 xiaolun/PDF 文件。父线程随后确认 xiaolun 是另一 Codex 项目，并指定年报恢复交给任务 `01a1343a-d9db-77ac-9aef-029df5fa3033`；本任务已停止网络恢复工作。

## 审阅结论

查询/文档编码分离和冻结校验在现有离线测试范围内成立。建议继续保留草稿；不能据此认证正式实验或正式数据就绪。发现的两处具体缺陷已在本地修复，等待用户审查：

1. **P2，消融循环持有旧模型时加载新模型。** 原 `experiments/04_ablation_study.py:22–24,32` 在右侧 `build_knowledge_index` 执行期间，旧 `router/retriever` 仍然存活，重复加载可能产生两个 embedding 模型的内存峰值。新增索引构建前先解除两处引用并回收编码闭包循环。`tests/test_ablation_lifecycle.py` 用弱引用及模拟闭包回归检查加载顺序。此修复不代表已实测真实模型峰值内存。
2. **P2，PDF 文件头不等于有效 PDF。** 原 `scripts/audit_data_preparation.py:30–40` 将仅包含 `%PDF-1.7\n` 的文件计入 `present_pdf`，原测试也将该桩文件当作有效文件。现在要求 pypdf 严格解析且至少有一页，并区分文件头、解析结果和公司/年度核验。测试同时覆盖真实可解析空白 PDF、截断文件、非 PDF 和越界路径；可解析空白页仍不算经过公司/年度核验的年报。

正式实验仍受已有问题限制：`src/retrieval/reranker.py` 使用序列分类头，不能认定为正确 Qwen3 reranker；`src/pipeline.py` 启用本地重排时会同时持有 embedding 与 reranker；完整评测运行清单尚未记录实际解析的模型 revision 和编码元数据；当前路由是截断召回后过滤。以上未在本任务中宣称修复。后续应在独立模型任务中实现正确评分、分阶段缓存候选与顺序加载，保持双方 0.6B。此次没有下载或加载神经模型，没有微调或运行论文主实验。

## 已交付的数据与代码

| 产物 | 本轮可核验状态 |
| --- | --- |
| `data/processed/corpus_v2_20261013/` | 319 篇输入，3 篇显式节选隔离，7 份全文重复作为别名保留，309 篇进入 V2；5,410 个块保留全部正文字符 |
| `chunk_migration.jsonl` | 7,899 个旧块全部有映射记录；隔离块明确无新 ID；保留旧文本哈希、可见范围、截断前范围及新坐标 |
| `label_migration.jsonl` | 226 个旧 gold 正例对及 1,049 个单轮 AI 复核候选对，共 1,275 行；不自动继承新标签 |
| `data/processed/label_review_v2_20261013/` | 40 条开发问题、1,681 个候选对；648 对无迁移标签，来自补充 BM25/随机池审计；A/B 表含真实新文本、哈希和坐标，人工栏为空 |
| `date_review_queue.jsonl` | 94 篇缺日期仍保留未知；其余日期也仅标记“原记录未核验”，没有宣称法律有效期已验证 |
| `data/heldout/candidates_20261013/` | 24 条 AI 编写候选，四维度各 6 条；隔离、未评分、未用于调参；准入检查失败；正式独立测试题仍为 0/160 |
| `data/provenance/recovery_20261013/` | 39 家逐公司原始材料需求清单、实际网络失败日志及空材料接入结果；有效年报 0/39，真实事实 0 |
| 上游年报接入与事实抽取模块 | 原样保留 `src/data/annual_reports.py`、`annual_facts.py` 及入口脚本；撤下本轮重复的接入器，依赖统一保留上游 `pypdf==6.1.1` |

V2 坐标是 `load_documents` 去掉元数据并 `.strip()` 后正文中的 Unicode 字符偏移，不是原始文件字节偏移。每篇同时保留原始文件 SHA256，可回溯到冻结文件。V2 正文不做改写；只改变结构化切分、索引口径和重复映射。长条文按长度/换行继续分片而非截断；处罚文书中的引用不再伪装为法规条号。超长块分片不代表语义完整性已经核验。

已核对上游 `results/runs/annual_report_recovery_20261013/run_summary.json`：其登记 5 份第三方转换文本、500 条辅助候选，但没有原始 PDF 页码映射，正式事实仍为 0。本轮保留这些上游记录，未将辅助材料合并为已验证公司事实。

旧语料、旧切分器、旧 gold、原标注轮次和原独立复核文件保持字节不变。默认实验仍使用原冻结开发集；未将 V2 的待审标签接入正式评测。

## 测试集隔离方案及限制

已扫描旧标注，包括 base64 压缩的 rerank 合成输入，记录 578 个不同历史查询文本及 245 个出现过的文档 ID。候选同时附上最近历史查询供人工做语义族比较。该清单只覆盖仓库登记输入，不能证明外部训练或其他工作区的完整暴露史。

24 个候选的新措辞不证明独立性。例如业绩预告更正可能落入已有临时披露族，内部控制应用问题可能与已有五要素/控制目标族交叉。因此全部保持隔离，不能把词面去重通过当作独立测试成立。D4 的证据不足题还需要不同于当前“必须有正例”检索评测器的 answerability 协议。

`src/data/holdout.py` 明确拒绝空集、重复查询、已登记开发问题族/公司、未完成人工语义隔离审查、缺少两位不同人工复核者、未解决标签、未验证证据和已用于调参的样本。此函数不是人工身份真实性的认证服务。最终冻结前须由资料保管者提供可核验的人工记录、问题族及公司分组，完成来源核验后再构建正式 manifest；不能自行填入“人工已审”。

下一步由两名独立人工标注者填写 A/B 表，分歧交第三方或明确记录的仲裁流程；开发标签与测试标签分别保存。正式目标仍为 160 条独立测试查询，本轮没有用重复模板充数。

## 验证证据

- 原 PR 基线：28 项测试通过，57 个冻结产物及原输入哈希一致。
- 初轮修改后：36 项测试通过，见 `pytest.txt`。
- 整合最新 PR 后：42 项测试通过、2 条已有 sklearn tokenizer 提示，详见 `pytest_integrated.txt`；使用上游 pypdf 6.1.1。
- `frozen_check_integrated.txt`：整合后原冻结产物检查再次通过。
- `prepared_validation_integrated.json`：309 篇、5,410 块的哈希、完整正文重构、重复别名、旧块覆盖、盲审表一致性通过；隔离候选按预期不获正式准入。
- `reproduction.json`：V2 在另一个输出目录重跑，各文件逐字节一致。
- `data_readiness_integrated.json`：整合后的原开发数据的更新审计；该脚本仍审计旧冻结版本，新版本状态以本报告和 V2 manifest 为准。

这些检查验证工程结构与可复现性，不证明相关性标签、公司事实、法规适用性或检索质量。

## 复跑和交接

在最终工作区根目录新建虚拟环境，执行 `pip install -r requirements-eval.txt -r requirements-data.txt`，再运行：

```bash
python -m pytest -q
python scripts/compile_independent_review.py --check
python scripts/validate_prepared_data.py --corpus-dir data/processed/corpus_v2_20261013 --heldout-dir data/heldout/candidates_20261013 --labels-dir data/processed/label_review_v2_20261013
```

所有生成器拒绝覆盖输出目录。重新生成时使用新的目录名：

```bash
python scripts/prepare_corpus_v2.py --out-dir /tmp/corpus_v2_new
python scripts/prepare_label_review.py --corpus-dir /tmp/corpus_v2_new --out-dir /tmp/label_review_new
python scripts/prepare_holdout.py --out-dir /tmp/holdout_new
python scripts/recover_and_extract_annual_reports.py --source-dir /path/to/authorized/pdfs --out-dir /tmp/annual_ingest_new
```

`sources_required.json` 是本轮逐公司材料需求清单，不是上游入口脚本的输入格式。年报任务沿用上游 `--source-dir` 接入授权 PDF，并在其 source_manifest 中保留真实来源 URL、文件哈希和有证据的公告日期（未知留空）；本地 file URI 不等于已验证的公开发布来源。不要覆盖历史下载清单。接入器先进行机器核验，再由 AI/人工检查页面与语义；实际恢复到的文件不得仅凭先前成功日志登记。本轮空材料试运行 `data/provenance/.../ingestion/` 仅是早期历史记录，不替代上游恢复结果。网络请求返回代理隧道 403，未绕过白名单，也未访问用户未授权电脑。

尚需外部材料/人工完成：39 家原始年报与公司事实；94 篇日期和全部法规版本的来源核验；1,681 对开发候选双人复核；最终 160 条测试集的语义族隔离和标签；真实 0.6B 模型顺序加载及 reranker 接口验证。本轮没有作出这些事项已完成的承诺。
