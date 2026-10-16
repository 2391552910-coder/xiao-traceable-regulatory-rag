# Qwen3-Embedding-0.6B 部署测试

默认配置与实验 08 的模型参数已由 `Qwen/Qwen3-Embedding-4B` 改为
`Qwen/Qwen3-Embedding-0.6B`。默认 embedding 和 reranker 设备均为 `cpu`，适用于当前
无 GPU 的 Linux 云端环境；Apple Silicon 可改为 `mps`，NVIDIA GPU 可改为 `cuda`。
本次加载测试只针对 embedding，未测试 reranker。

## 当前测试结果（2026-10-13）

新实例续接记录见 [云实例续接_20261013.txt](云实例续接_20261013.txt)。
本轮恢复了全部 602 个快照文件，CPU 依赖、24 项回归和 57 个独立复核冻结产物校验通过。
新实例 `config.json` 下载返回 HTTP 200，但权重重定向到未生效放行的
`us.aws.cdn.hf.co`，仍返回代理 403；仅完成部分模型元数据下载，未执行真实推理。
本轮独立记录在 `results/runs/embedding_0_6b_resumed_20261013/`。
下表保留旧实例历史结果，避免覆盖原阻塞记录。

| 检查 | 结果 |
| --- | --- |
| CPU 推理依赖 | 已安装于项目 `.venv`，与系统 Python 隔离 |
| 依赖一致性 | `pip check` 通过 |
| Transformers 的 Qwen3 架构支持 | 通过 |
| 项目回归测试 | 24 项通过，2 条已有分词参数提示 |
| 模型配置下载 | 代理返回 `403 Forbidden` |
| 本地缓存加载 | 无可用模型缓存 |
| 模型权重加载、向量生成与真实检索 | 未完成；状态 `blocked_model_download` |

依赖版本为 PyTorch `2.7.1+cpu`、Transformers `4.51.3`、Sentence Transformers
`3.1.1`、NumPy `1.26.4`。没有因模型下载失败而切换到 TF-IDF；上述 24 项回归测试中的
离线检索也不能证明真实 embedding 的性能。

机器可读测试记录：
`results/runs/embedding_0_6b_20261013/deployment_test.json`。
该目录按项目约定不提交到 Git；记录在当前工作区内可读取，复跑会更新。

## 安装与复跑

从项目根目录运行。Linux CPU 环境先安装 CPU 版 PyTorch，避免默认下载 GPU 运行依赖：

```bash
python -m venv .venv
.venv/bin/python -m pip install --index-url https://download.pytorch.org/whl/cpu 'torch==2.7.1+cpu'
.venv/bin/python -m pip install -r requirements-models.txt
.venv/bin/python -m pip check
.venv/bin/python scripts/smoke_embedding_model.py
```

当前环境已完成依赖安装，只需解决模型下载访问后运行最后一条命令。
当前云环境的网络策略不允许 `huggingface.co`。需在云环境网络设置中允许该域名以及
模型下载实际使用的权重 CDN/Xet 域名；修改工作区内的网络策略文件不能授予网络访问。

也可以使用完整的本地模型仓库目录（包括权重、tokenizer、模型配置和 Sentence Transformers
模块配置），避免遗漏 Qwen embedding 的池化配置：

```bash
.venv/bin/python scripts/smoke_embedding_model.py --model /absolute/path/to/Qwen3-Embedding-0.6B
```

测试脚本先验证依赖与 Qwen3 架构，探测模型下载；网络失败时尝试已有缓存，缓存也不可用时
返回退出码 2 并记录阻塞原因。具备权重时会加载真实模型，使用知识库的 3 个片段验证向量
形状、有限数值、归一化、相同文本检索及自然语言查询，使用 `batch_size=1` 控制 CPU 测试
开销。成功返回 0，其他加载或推理错误返回 1。

这个小规模测试用于验证加载和检索链路，不构成完整 gold 评测、服务吞吐测试或性能结论。
本次也没有启动常驻 HTTP 服务。模型加载成功后，可继续运行真实检索实验：

```bash
.venv/bin/python experiments/02_retrieval_evaluation.py --backend qwen --device cpu
```

此命令在全知识库上运行，CPU 耗时需要实测；精排仍需单独验证并显式启用。
