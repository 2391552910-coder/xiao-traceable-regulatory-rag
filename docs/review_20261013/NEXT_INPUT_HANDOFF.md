# 年报验收与双人标注操作交接（2026-10-13 增量）

本轮新增的是材料验收、标签导回和分歧处理入口，不代表新增真实年报或人工金标准。审阅基线及此前修复见 [FINAL_REPORT.md](FINAL_REPORT.md)。所有输出目录必须不存在，避免覆盖历史版本。

## 当前覆盖与角色

| 项目 | 可复核现状 | 下一输入 |
| --- | --- | --- |
| 39 家 2024 年原始年报 | 当前可用原始 PDF 0/39；历史成功记录不能替代文件 | 原始完整 PDF、真实发布地址与版本 |
| 官方报告直链 | 当前来源清单记录 0/39 | 不能将站点首页、历史文件名或辅助转载伪装为直链 |
| 公司事实 | 已有 5 家辅助转换文本，500 个候选；正式核实事实 0 | PDF 哈希、实际 PDF 页码、引句及人工语义确认 |
| 开发标注 | 40 道开发题、1,681 个候选对；A/B 表已准备 | 两位独立标注者、第三位分歧仲裁者、协调者声明 |
| 最终测试集 | 正式 0/160；仅 H005、H009 两道保留候选 | 独立题族和来源复核、证据标签、隔离冻结 |

[39 家逐项缺件表](../../data/operator_handoff/20261013/company_missing_materials.csv) 保留历史路径、公司/年份核验要求和辅助来源身份，不补造发布日期。已有源数据保持不变。39 家不是本轮新增样本。

## 1. Windows 本地原始 PDF 导入及验收

在本仓库根目录执行；只访问操作者明确提供的本地目录。此云端没有访问个人电脑。先将原始文件放入专用目录，每家公司选择一个完整年度报告版本，保留不同修订版而不要混放；文件名包含证券代码和年份。无需下载模型、微调或重新跑主实验。

```powershell
.\scripts\recover_annual_reports_local.ps1 -SourceDir "D:\annual_reports_2024"
```

该脚本创建 `.venv-data`、安装 `requirements-data.txt`，输出到新的 `results/runs/annual_local_<时间戳>`。本交接不使用 `-AllowDownload`，不重试已拒绝的网络地址。完整导入退出码 0，材料不足退出码 2；先读 `pipeline_run.json`、`source_manifest.csv` 和 `fact_candidates/extraction_run.json`，不能以退出码 2 推断所有文件无效。

每份成功提取的文件另做独立验收。下面路径和公司名是占位符，替换为本次 source_manifest.csv 对应值；PDF 参数应指向清单中实际被提取的原件：

```powershell
.\.venv-data\Scripts\python.exe -X utf8 scripts/accept_annual_extraction.py --pdf "<原件路径.pdf>" --extraction-dir "results/runs/annual_local_<时间戳>/fact_candidates/<证券代码>" --code "<证券代码>" --name "<公司简称>" --year 2024 --output "results/runs/accept_<证券代码>_<新时间戳>.json"
```

验收重新读取 PDF，核对原文件哈希、公司及年份、逐页文本、页码与页文本哈希、候选引句偏移和哈希。`traceability_passed_semantics_pending` 仅说明来源链通过；`verified_facts` 仍为 0。PDF 页码按实际文件从 1 起算，不冒充报告印刷页码。表格单位、跨页表头、主语、期间和否定范围仍须对照原页人工核实。扫描件需另建 OCR 版本并保留原件，不将 OCR 文字当原始 PDF 文本。

| 诊断 | 处理 |
| --- | --- |
| 缺少本地 PDF | 按缺件表补对应公司/年份，历史下载成功不豁免 |
| 多个候选版本 | 人工选择并记录发布版本；用新的输入目录保留选择记录 |
| 公司/年份/完整报告身份失败 | 检查封面及代码，排除摘要、其他年份；扫描件转独立 OCR 流程 |
| `source_pdf_hash_mismatch` | 原件与提取版本不同；保留两版，重新提取到新目录 |
| `page_text_hash_mismatch` / `page_text_not_reproducible_from_pdf` | 禁止编辑已提取页面；确认 pypdf 版本后重新提取，不重写旧哈希 |
| 候选页码、引句、数量不匹配 | 重新从已验原件提取；不能手工改哈希让其通过 |
| 空文本或 OCR 提示 | 对照原页确认扫描/解析缺失；有文字也不代表表格语义正确 |

## 2. 开发集：独立 A/B → 分歧仲裁 → 声明导入

复用 [A 表](../../data/processed/label_review_v2_20261013/blind_review_A.csv) 和 [B 表](../../data/processed/label_review_v2_20261013/blind_review_B.csv)，各 1,681 对。协调者分别发给两位真实标注者，标注期间不互看答案，也不暴露旧 AI 标签；协调者自行核实身份和独立性。软件只能检查提交声明，不能认证真实人类或防止同一人冒用身份。

复制到 `submissions/A.csv`、`submissions/B.csv` 后填写，保留 UTF-8 CSV 和原列。只编辑 `human_grade, reviewer, reviewed_at, rationale`。2=直接支持、1=辅助相关、0=不支持、U=无法判定；证据不足、适用日期不明不能自动标 0。时间填真实带时区 ISO 8601；理由需说明引句支持/不支持关系。完全未开始的行四栏留空，不预填全表身份。不可删行、改 query/chunk ID、改引句或哈希。

```powershell
.\.venv-data\Scripts\python.exe -X utf8 scripts/import_human_reviews.py --packet-dir data/processed/label_review_v2_20261013 --a submissions/A.csv --b submissions/B.csv --out-dir results/runs/review_round1
```

未完成时退出码 2 是预期结果，不输出 qrels。`import_report.json` 报告未判定项、原始双人一致率和 kappa；U/空值不参与数值一致率，单类别 kappa 无定义时为 null。`adjudication_needed.csv` 保留双方原票及理由。第三位真实仲裁者只填写 `adjudicated_grade, adjudicator, reviewed_at, rationale`，U 仍待处理。A/B 缺交不能由仲裁跳过。

完成后复制 [协调声明模板](../../data/operator_handoff/20261013/development_attestation_template.json)，填写真实身份/时间；实际确认独立工作及来源后才将两个布尔值改为 true。不得代填虚构人名或声明。再次运行到新目录：

```powershell
.\.venv-data\Scripts\python.exe -X utf8 scripts/import_human_reviews.py --packet-dir data/processed/label_review_v2_20261013 --a submissions/A.csv --b submissions/B.csv --adjudications submissions/adjudications.csv --attestation submissions/attestation.json --out-dir results/runs/review_round2
```

仅全量数值判定、分歧解决且声明匹配时输出 `development_qrels.tsv`。无分歧可省略 `--adjudications`。该文件仍是开发集新版本，不自动改写旧 gold、模型默认路径或正式测试集；原始提交、声明及哈希随输出保留。

## 3. 独立测试题：题族和来源筛查，不复用开发题

17 道与开发题族重叠的候选已排除；5 道属于其他研究任务，保持单独探针。40 道旧题已经开发曝光，不能通过重新命名成为最终测试。复用冻结 development_registry.json 中的 578 条历史查询文本和 245 个文档曝光记录。

分别复制 [测试筛查 A](../../data/operator_handoff/20261013/test_screening_A.csv)、[测试筛查 B](../../data/operator_handoff/20261013/test_screening_B.csv)，两位独立审阅者填写 family_overlap、source_verified、temporal_scope_verified 为 yes/no/U，并记录实际身份、时间、理由。重叠 yes 必填 development_query_ids；来源 yes 必填 evidence_ids（多个用分号分隔）。不可修改题目。参考 [来源上下文](../../data/operator_handoff/20261013/test_source_context.json)：H005 尚缺来源，不能确认 yes；H009 唯一现存候选证据为 DOC005-V2-0194，且整个 DOC005 已开发曝光，需评估题族泄漏。来源 ID 在冻结包中存在也不代表自动核实。

```powershell
.\.venv-data\Scripts\python.exe -X utf8 scripts/import_test_screening.py --packet-dir data/operator_handoff/20261013 --a submissions/test_A.csv --b submissions/test_B.csv --out-dir results/runs/test_screen1
```

协调者在输出 `screening_decisions.json` 的副本中只填写每题 `coordinator_decision, coordinator, decided_at, reason`。决策可为 reject、request_more_evidence、proceed_to_evidence_labeling。协调者必须不同于两位审阅者。将副本导回：

```powershell
.\.venv-data\Scripts\python.exe -X utf8 scripts/import_test_screening.py --packet-dir data/operator_handoff/20261013 --a submissions/test_A.csv --b submissions/test_B.csv --decisions submissions/screening_decisions.json --out-dir results/runs/test_screen2
```

重叠、分歧、未知来源不能直接推进；应补证或独立重审后建立新版本。即使一致且获协调者确认，也仅进入证据标注阶段，工具始终不产出测试 qrels、正式题目或模型成绩。新增外部来源需先保存原文/原件、公开来源、版本日期和哈希，再生成新冻结来源包，不编辑本包的哈希“放行”。正式集仍需独立证据标签、日期适用性、题族隔离和发布门禁；在完成前禁止用候选调参后又称独立最终测试。

## 验证及范围

新增测试使用明确标记 SYNTHETIC 的临时 PDF 和虚构标注身份，不进入上述覆盖率。测试涵盖原件至页面引句的来源链、篡改拒绝、U/空表阻断、第三人仲裁、协调声明、kappa 边界、测试来源登记和禁止越过发布门禁。Windows 命令按已有 PowerShell 脚本整理，本云环境未实际执行 Windows。

此增量不重新加载模型，不扩大论文实验结论，不自动合并或发布 PR。缺件和真实人工工作必须由实际材料/真实独立审阅补齐，自动生成与 AI 辅助不能替代。
