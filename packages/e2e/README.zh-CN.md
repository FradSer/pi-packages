# pi-e2e

通过一次测试运行的客观证据，判断 Gherkin `.feature` 端到端场景是否达成。

代码裁决你能够精确比对的条款；TypeSafe **Jev** 决策模型仅回答那些需要理解证据语义的条款。最终结论在代码层通过概率门限组合，未达到置信度的结论将转为人工复核，绝不冒充通过。

## 为什么这样做

BDD / 端到端验收测试条款通常分为两种不同性质：

- **明确的事实断言**（例如 "工作区计划为 Pro"）：属于代码比对范畴。调用模型只会徒增成本与延迟，且存在误判风险。
- **业务意图条款**（例如 "账单页面显示的金额仅覆盖当前计费周期的剩余天数"）：需要将条款语义与真实账单数值结合理解。这是判断而非简单的字符串匹配。

本包将第一类留在代码中裁决，仅将第二类交给 Jev。

## 安装

```bash
pnpm add -D @fradser/pi-e2e
```

设置环境变量 `TYPESAFE_API_KEY` 以便 Jev 评测未声明代码检查的条款。本包不支持通过命令行参数传入密钥，防止密钥泄露至上下文。

## 命令行使用

通过 `pnpm exec tsx`、`npx tsx` 或 `bun` 运行（Node.js 原生去类型机制默认跳过 `node_modules`）：

```bash
pnpm exec tsx node_modules/@fradser/pi-e2e/src/cli.ts verify \
  --feature examples/billing.feature \
  --evidence examples/billing-evidence.json \
  --offline --report-html report.html
```

或直接在源码目录运行：

```bash
node src/cli.ts verify \
  --feature examples/billing.feature \
  --evidence examples/billing-evidence.json \
  --offline --report-html report.html
```

参数说明：`--scenario <名称>`、`--clause-gate <0..1>`、`--verdict-gate <0..1>`、`--report-md <路径>`、`--report-html <路径>`、`--json`。

退出码对 CI 稳定友好：`0` 达成，`1` 未达成，`2` 需要复核。

## 在 Pi 中使用

插件注册了一个斜杠命令：

```
/e2e <feature.feature> <evidence.json> [场景名称]
```

或显式带有 `verify` 子命令：

```
/e2e verify <feature.feature> <evidence.json> [场景名称]
```

## 自动验收流程

只有本轮直接涉及的 `.feature` 路径或用户明确指定验收的路径才会触发检查点。其他 package 中并行变更的 feature 不会触发检查点。项目实现文件的活动只有在同一轮中已直接涉及该 feature 时，才会使其验收失效。检查点要求检查项目说明、脚本、测试配置与现有测试。失败 verdict 与 feature 检查方向会合并到同一检查点，不会互相覆盖。相同状态不会重复提示；只有相关进展或新的验证结果才允许继续。最多自动继续两次；未验证的结果需报告为 `needs_review`。

Harness 只向模型注入提示，不会自行运行测试或生成 evidence。

只有插件实际启动测试进程并读取本次新生成的证据，才能清除检查点。Inline JSON、已有 evidence 文件与 `/e2e` 仍可评估内容，但无法证明来源，也不能清除验收状态。原生工具分别返回内容判断 `status` 和运行来源 `verifiedRun`。

在**调用 e2e_verify 前**配置项目已授权的 `.e2e/runner.json`：

```json
{
  "executable": "node",
  "args": ["tests/acceptance-adapter.mjs"],
  "adapterFiles": ["tests/acceptance-adapter.mjs", "tests/evidence-serializer.mjs"]
}
```

Adapter 应执行实际测试，根据应用观察结果生成 `Evidence` JSON，写入插件传入的 `PI_E2E_EVIDENCE_PATH`，并仅在执行成功时退出 0。不得复制示例证据。`adapterFiles` 必须完整列出 adapter 与**所有生成证据的依赖文件**，限 1–64 个文件或目录路径，最多 2000 个普通文件，单个不超过 1 MiB、总计不超过 32 MiB。声明完整性与测试质量由项目维护者保证；插件无法证明预先存在的 adapter 覆盖了正确业务行为。

本仓库适配器在 `tests/scenario-behavior-map.json` 登记关联测试，在 `tests/scenario-observation-map.json` 登记逐子句观察绑定。Goal seed 场景通过 `tests/observe-goal-seed.mts` 在临时新会话中运行真实 `/goal` 处理器，观察目标创建、发送选项及完整请求正文，并用独立的已认可请求契约检查正文。绑定必须与全部 Given/When/Then 及 Background 步骤一致，生产者及其依赖必须登记在 `.e2e/runner.json` 的 `adapterFiles` 中。没有绑定的测试不声明子句检查；步骤变化或生产者未登记时，适配器拒绝产出证据。

调用原生工具时使用相同命令：

```json
{
  "feature": "features/checkout.feature",
  "scenario": "Checkout succeeds",
  "runner": { "executable": "node", "args": ["tests/acceptance-adapter.mjs"] }
}
```

`runner` 与 `evidence` 不能同时提供。可选的 `runner.timeoutMs` 范围为 1–600000 毫秒，默认 120000，或使用配置里的超时。所有 Then 均有确定性检查时可设 `offline: true`；否则由 Jev 判断剩余语义条款。

每次 e2e_verify 捕获当前配置与 adapter 指纹，并启动新测试进程。同一轮内可以修复实现、测试或已授权的 adapter，然后反复调用直到通过，无需新轮次。单次执行或评估期间发生 feature/adapter 变更，该次证据无效；错误会列出变更文件。新用户轮次会使旧异步观察者失效。结束前重新检查已接受的证明；通过后又修改文件，需要重新运行。明确请求整个 feature 时，全部场景通过才清除请求。自动续跑最多催促两次；手动工具调用没有每轮次数上限。

失败、取消、超时、过量输出、过期轮次、缺失或非法证据、符号链接与非普通证据文件均不能通过验收。证据和 stdout/stderr 合计输出各限 1 MiB，每次调用后删除私有临时证据。macOS/Linux 取消与超时会终止进程组；Windows 进程树行为尚未验证。

扩展会在每轮开始和结束前扫描有上限的 `.feature` 快照，以检测 shell 等工具造成的变更。只有该 feature 所属包在本轮有文件活动，或用户明确指定其路径时，才会触发检查；其他包的无关 feature 变更不会触发。扫描跳过 `.git`、`node_modules` 和 `.pi`，最多检查 2000 个 feature 文件（单个 1 MiB、总计 32 MiB）和 20000 个目录；扫描不完整时会报告限制。变更 feature 的每个场景都需要基于新运行证据的 fulfilled verdict。场景名必须唯一，且每个场景都要包含 Then。

## 协议

MIT

状态行仅显示 `[e2e] running`、`[e2e] passed`、`[e2e] needs review`、`[e2e] failed`、`[e2e] error`、`[e2e] continue` 或 `[e2e] waiting`，没有分隔符和后缀。原生工具更新当前执行阶段；正文先显示证据来源、feature 验收进度与剩余场景，再完整换行显示条款列表，未满足项优先。Provider 阻断直接显示错误原因和恢复动作。已有证据的通过显示 `needs review`，机器 verdict 保持 `fulfilled`。`/e2e` 使用相同的持久结果渲染，不触发模型轮次。等待正文列出剩余工作、停止自动续跑的原因和下一步。完整诊断不截断、不要求 ctrl+o。用户取消时不追加续跑或通用验收警告。见[全部 TUI 场景](TUI.zh-CN.md)。

### 项目观察 producer

本仓库的 `tests/run-feature-suites.mjs` 根据 `tests/scenario-behavior-map.json`
运行关联测试；专属观察 producer 在 `tests/scenario-observation-map.json` 登记，
绑定完整 Given/When/Then 步骤，前提、动作或条款变化必须更新观察契约。Producer 必须列入
`.e2e/runner.json` 的 `adapterFiles`。只有本次真实观察声明检查，测试退出 0
不能自动证明所有条款。Goal seed producer 在隔离无 goal 会话中调用真实
`/goal` 处理器，观察是否创建 goal、是否请求模型编写 objective，以及输入引用。

工具每次判断一个场景；检查点列出剩余场景名，整份 feature 全部通过才完成验收。
完整通过报告后不再追加成功通知。缺少证据要求补观察/检查，行为失败要求修实现。
简单 `pwd`、`ls`、`cat`、`rg` 和受限 `git status` 查询保留通过。未知 shell 程序仍
保守撤销验收，因为现有 adapter 可能漏列导入的应用输入。收尾另外检查 feature
和已声明 adapter 指纹。实现与测试输入需列入 `adapterFiles`；Pi 文件工具直接
修改本轮涉及的 feature 所属包时，仍立即撤销验收。

### Goal 全量契约覆盖

当前简化 Goal 架构为准。原 106 个场景完整保存在
`tests/legacy-goal-scenarios.json`；`tests/goal-scenario-migration.json` 逐项说明
保留、迁移或撤销的要求及当前覆盖目标。当前 Goal feature 有 179 个场景、718 条
原子 Then。此覆盖结论仅适用于 Goal。

`tests/observe-goal-harness.mts` 在新进程中运行真实行为测试。共享观察器记录每条
原生断言的实际值、期望值、运算、源表达式及调用次数；冻结的 harness 哈希和断言
选择器拒绝缺失、替换或额外证据。子句检查对应断言本身，不使用套件退出码代替。
运行源码、导入的依赖和观察器同时受到 adapter 指纹检查保护。

审查契约变更后，可显式运行
`pnpm exec tsx packages/e2e/tests/sync-goal-contracts.mts --write` 更新绑定；
不带 `--write` 只检查一致性。验收不会自动重新生成期望值。生成器不能证明旧要求
已被保留，仍需审查迁移表并为有效要求添加行为断言。

完整新进程验收和 feature 门禁检查：

```bash
pnpm exec tsx packages/e2e/tests/verify-goal-contracts.mts /tmp/goal-coverage-report.json
```

每个场景必须具有 fresh proof、fulfilled 和零模型问题；最终 feature checkpoint
必须清除。证据不跨运行复用。原生 CLI/TUI 验收使用脚本 provider，不代表真实模型
决策质量。

### 验证计划

注入提示要求尽早通过已授权的 `.e2e/runner.json` 运行相关验收，为修复与
重新验证预留时间。工具本身会执行测试，不必在调用前重复跑同一套测试。
若现有测试无法在预算内完成，应报告阻塞，不得为了通过而削弱覆盖。
已启动或中断的调用不算完成验证；结果需分别说明已覆盖场景和未覆盖需求。

禁跑识别限定于测试执行指令，不再将“不要为了通过测试而改变行为”当作禁跑。
同一请求中，后面的明确执行指令优先。这仍是有边界的意图启发式，不是通用
自然语言授权解析器。预实验冻结版本与结果保留，以上改动尚未证明正确率提升。

新鲜运行证据未满足检查时，插件保留有长度上限的适配器诊断，供修复使用；诊断不会改变验收状态。

验证规划应将每项公开需求对应到可观察的检查，明确未覆盖的行为；没有新增证据时停止重复检查。修复后必须重新验证最终代码。单个回归命令通过不代表整个任务完成。
# 完整场景检查与失败证据

原生 `e2e_verify` 新增 `allScenarios: true`，配合 `feature` 和授权 `runner`，
一次工具调用逐一执行全部场景。每个场景都产生新鲜证据，adapter 根据
`PI_E2E_SCENARIO_NAME` 返回对应场景的 Then 检查（编号从 1 重新开始）。
场景名称必须唯一，最多 100 个。现有默认调用和独立 CLI 保留单场景行为。
完整模式拒绝同时指定 `scenario` 或使用未绑定场景的外部 evidence。
`coverage` 报告总数、已评估、已通过和剩余场景；feature 或 adapter 在批次中
变化会使批次失效，不交付该批次的验收回调。覆盖整份 feature 仍不代表覆盖完整需求。

确定性 check 可声明 `step` 和 `location`（源码或测试路径及行号）。结果包含
检查路径、操作符、预期值、实际值和失败类别；长值明确截断。
`findings` / `nextAction` 分为：`repair_code`（新鲜确定性反例）、
`collect_evidence`（缺失观察、无效检查、外部证据或语义不确定），以及
`resolve_blocker`（执行或提供方错误）。检查不一致提供调查线索，并不自动证明
预期本身正确；应保留断言，先解决需求冲突，不为获得通过而修改预期。


可信 Python adapter 可复用 `examples/guards/assertion_guard.py` 对照冻结原测试检查
完整断言、精确异常期待、测试删除和新增 skip/xfail。该检查采用保守的 AST 保留规则，
不证明改写语义等价，也不替代对 fixture、辅助函数和控制流的独立审查。
契约迁移例外必须在模型执行前逐项明确，不能根据候选补丁事后豁免。
消息型任务应观察完整历史（顺序、调用名/ID/参数及结果绑定），避免只检查最终响应。
