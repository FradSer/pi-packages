# DeepSeek 4.1 Flash：E2E 替代模型 review 的配对评估

日期：2026-10-10。结论：**不足以确认代码质量、任务完成度或成本收益。** 本轮按冻结停止规则，在唯一一次付费预检失败后停止；没有启动正式任务推理，没有有效配对样本。这不是 E2E 效果为零，也不是 E2E 败给模型 review。

全部本轮证据位于 `runs/paired-fresh-20261010/`；机器结果见 `outcome.json`。没有发布、远程提交或删除其他项目资源，也没有修改产品代码。实验目录保留完整失败记录。

## 配对结果与统计边界

| 固定任务 | 插件关闭的共同初稿 | A：模型 review → fix | B：E2E review → fix | 救回 / 回归 | 状态 |
|---|---|---|---|---|---|
| google__adk-python-c_61adfcd | 未生成 | 未执行 | 未执行 | 不适用 | 预检停止 |
| stanfordnlp__dspy-9047 | 未生成 | 未执行 | 未执行 | 不适用 | 预检停止 |

初稿完成率、A/B 最终完成率、救回率、回归率、平均质量差和增量成本收益均**不可计算，分母为零**，不能写作 0%。有效配对数 0；正式流程启动数 0。没有最终任务补丁，因此不存在独立最终评分或发现到修复的任务证据链。没有效应估计，也没有可解释的效果置信区间。

选择预先固定为两道小型真实公开问题，各一次，顺序 A/B、B/A；这是便利可行性样本。即使两题全部完成并同向胜出，两个不一致对的双侧精确符号检验 p=0.5，仍不足以建立一般收益。旧实验、已见题、合成离线夹具、参考补丁和负例控制均不计入新效果。

## 为什么停止

付费预检在隔离 Docker 中运行真实 Pi 1.0.4，实际加载本轮快照的 `@fradser/pi-e2e` 0.1.0，返回 DeepSeek 模型标识 `deepseek-v4.1-flash` 和语义模型 `jev-1.13.0`。

原始事件顺序：

1. DeepSeek 仅调用一次 `e2e_verify`，固定参数合法，没有追加源码 review 或修改。
2. 插件启动 fresh runner，公开命令成功；Jev 完成语义判断且返回使用量。
3. DeepSeek 正常完成报告，`stopReason=stop`，原始 `paid-preflight/native/events.jsonl:234`。
4. Pi 自动 followup 被代理以预期 HTTP 409 拦截，未转发上游，原始事件第 241 行。
5. 控制器虽将报告后事件排除出 review packet，却从完整事件流计算 `modelErrors`，误将预期拦截记作阶段内错误。`phase_valid` 因此失败。

独立审查者核对原始事件、控制器、总账及完整响应后确认上述因果。离线反事实只统计报告边界内错误时可通过语义预检门槛；这不是修改结果或补跑授权。冻结 receipt 保持 `valid=false`。

Jev 对夹具的语义条款返回 0.69，低于固定 0.80 clause gate，原生结果为 `needs_review`。预检允许已经完成且有使用量的 met/unmet 判断，所以这**不是启动门槛失败原因**；没有降低阈值。夹具只打印 42，其笼统语义条款不能推断真实代码缺陷或修复价值。

| 失败类别 | 本轮事实 |
|---|---|
| 阶段未完成 | 模型报告已正常完成；正式任务未启动 |
| 基础设施 / 控制器失败 | 报告后预期 409 被错误统计，触发停止 |
| 协议偏离 | 未因失败追加重试、换题、修改冻结协议或增加额度 |
| 代码错误 | 未生成任务代码，不能评价 |
| 服务失败 | 3 次上游调用都有完整响应和使用量；无传输错误 |

准备工作预设最多 60 分钟、两轮控制器修订；付费预检最多 8 次请求 / $1 预留，只允许一次，任何失败停止。两轮修订已用完。本轮没有第三轮修改，也没有利用剩余预算继续试到通过。

## 费用、时间与干预

| 项目 | 数量 | 按记录用量估算 USD |
|---|---:|---:|
| DeepSeek 预检 | 2 次上游请求 | 0.001203324 |
| Jev 预检 | 1 次上游请求，907 input tokens | 0.000038094 |
| 合计 | 3 次 | **0.001241418** |
| 保守总预留 | 每次 $0.125，3 次 | **0.375** |
| 正式任务、失败调用重试 | 0 次 | 0 |

两次 DeepSeek 原始 SSE 均含 usage 和 `[DONE]`，Jev 为完整 JSON + usage。报告后 409 没有转发，未重复计作上游请求。缺失用量请求数为 0；失败预检本身全部计费且未返还预留。实际账单未核验，估算不等于发票金额。

冻结价格依据：[OpenCode Zen](https://opencode.ai/docs/zen/) 的输入 $0.30/M、输出 $1.20/M、缓存读取 $0.006/M；[TypeSafe 模型文档](https://docs.typesafe.ai/models) 的 Jev 输入 $0.042/M、输出免费。费率和假设保存在 `pricing.json`。预算账本在网络转发前持久化预留，152 次请求最多 $19；单次输入字节及输出 token 有硬上限，预留不因失败或缺失用量解除。

环境准备从约 10:00 到 10:43 Asia/Shanghai，约 43 分钟；付费预检阶段 28.32 秒，随后进行离线独立核验与报告。包括 Docker 镜像下载、运行时准备、离线控制、两轮修订和测试；没有精确的人工有效工时记录，因此不编造人力成本。代理自主操作，无中途人工修改任务结果。Codex 平台编排及内部独立审查的计费收据不可观测，不能宣称其成本为零；上述硬上限证明覆盖本实验自行转发的所有新增模型与语义服务 API 调用。Docker 下载、主机资源和人工费用另列，不伪装为模型费用。

## 已完成的准备与评分校准

复用了已有小型 stage/proxy/adapter/controller，先检查历史框架和失败记录。历史结果只用于调试。没有重建大型基准系统。

完整需求覆盖在 `COVERAGE.md`：ADK 的值真值表、默认值、命名隔离和三个真实消费者；DSPy 的直接/嵌套 History、Example 递归、合并和实际 Evaluate 导出路径。最终评分原计划要求所有独立需求检查及 pristine 原始回归通过，baseline、fresh proof 和插件通过均不替代评分。

| 离线控制（修订 2） | ADK | DSPy |
|---|---|---|
| 空补丁 | 失败，符合预期 | 失败，符合预期 |
| 完整参考补丁 | 完整需求及公开回归通过 | 完整需求及公开回归通过 |
| 故意不完整的参考补丁 | helper 正确，三个集成失败 | 递归正确，merge/export 失败 |

所有当前控制均绑定 scorer、任务、公开检查、镜像及数据哈希，输入前后未变化。保留此前失败和修订记录：DSPy 评分器错误地将 Example 的 `items` 字段当作方法属性，改为索引访问；未降低需求。参考和隐藏 scorer 只在 host，不进入模型容器。

离线实际 Pi 夹具证明：请求耗尽时保存部分补丁，新容器原样接续；真实插件调用；报告后转发阻断；阶段输入固定。预算单元检查覆盖并发、重启、损坏总账拒绝及请求大小。该夹具没有覆盖付费路径中最终汇总错误计数的缺陷，独立审查也未在启动前发现它；这是准备验证的明确局限。

校验结果：新增 harness 12 项通过；E2E 包 176 项通过（仅排除旧实验 runs 的重复测试模块）；包 TypeScript 检查和 pack dry-run 通过。根 typecheck 存在预先已有的 `continual-learning/src/inject-memory.ts:2461` TS2322，与本轮无关，未跨范围修复。首次 pnpm 自动安装因非交互环境中止，后续禁用自动依赖核查保留原依赖再运行；记录保留。

## 复现记录与使用建议

冻结入口：`manifest.json`，包含协议、选择、数据、运行时文件及 symlink、scorer、公开测试、镜像和插件内容哈希。模型 API 标识只能证明服务报告的名称，不能独立证明托管权重哈希。

数据来自 [SWE-Bench-ProMax](https://huggingface.co/datasets/swe-bench-promax/SWE-Bench-ProMax)，revision `014a4113c86327beacee3b85e567d32afd56ba56`。数据、选择规则、参考控制均保留；同一任务再次运行必须记作已见题 / 新协议，不得当成新的盲测效果样本。

重要证据：`PROTOCOL.md`、`selection.json`、`COVERAGE.md`、`controls/*/*/receipt.json`、`offline-fixture-final/receipt.json`、`independent-review.json`、`independent-stop-review.json`、`paid-preflight/receipt.json`、`paid-preflight/native/events.jsonl`、`cost-ledger.json`、`cost-ledger-requests/*`、`outcome.json`。真实凭证没有进入模型挂载或证据；转发使用临时 bearer，持久证据经脱敏。

离线检查可运行：

```bash
uv run --no-project --with pytest python -m pytest packages/e2e/tests/quality-pilot/runs/paired-fresh-20261010/harness/test_fresh.py packages/e2e/tests/quality-pilot/runs/paired-fresh-20261010/harness/test_launch_contracts.py packages/e2e/tests/quality-pilot/runs/paired-fresh-20261010/harness/test_orchestration.py -q
```

`driver.py freeze/preflight/run` 是冻结入口及阶段记录；已有 manifest 和失败 receipt 会阻止覆盖重跑。**本轮不要再次执行付费入口。** 本地报告核验不需要付费调用。

当前不能建议为了代码质量普遍用 B 替代 A，也不能断言 B 不值得成本。已有证据只支持真实 E2E 调用和语义服务可连通，未支持真实任务的“发现 → 修复 → 独立验证”。如未来另行授权研究，应先离线修正报告边界计数并增加同路径回归，以新协议、新未见题重新冻结；任务需要预先可验证的实际修复空间，保留所有结果。原始插件调用次数、needs_review 或此次控制器失败都不能充当质量收益指标。
