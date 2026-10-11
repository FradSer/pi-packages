# E2E 工作流与 TUI

流程：运行当前项目 adapter → 判断本次证据 → 修复未满足项或补齐证据 → 同轮再次 e2e_verify。每次 runner 调用都运行新测试，手动调用没有每轮次数限制。自动检查点最多催促两次，不能代替测试或强制通过；仅缺少请求的验证而无变更或失败时，最多催促一次。

状态行仅显示包名和状态，没有 `·` 或后缀。Feature、scenario、来源、原因、进度和下一步放在正文。工具、`/e2e`、检查点和正常收尾等待使用同一个 pi-kit 渲染入口。

| 场景 | 状态行 | 正文和后续动作 |
| --- | --- | --- |
| 执行或评估中 | `[e2e] running` | 原生工具更新同一结果的阶段：准备、检查配置、运行测试、读取证据、检查确定性条款、必要时调用 Jev、复核新鲜度。 |
| 新运行 fulfilled | `[e2e] passed` | 先标记新鲜证据、场景和 feature 验收进度，再列出全部条款；所有请求场景通过才完成验收。 |
| not_fulfilled / partially_fulfilled | `[e2e] failed` | 未满足条款优先，显示原因与来源；修复真实行为失败后同轮重试。 |
| needs_review | `[e2e] needs review` | 警告样式，显示未判断条款、概率不足或 provider 的具体阻断。先补齐观察/检查或解决阻断，不因缺证据就修改实现。 |
| caller-supplied fulfilled | `[e2e] needs review` | 正文最前标记来源；说明内容判断 fulfilled，但验收未完成。机器 `status` 仍为 fulfilled、`verifiedRun` 为 false。 |
| error | `[e2e] error` | 显示 feature、可识别的场景、配置/执行/证据错误和恢复动作；runner 日志最多保留末尾 8192 字节，并标记截取。失败尝试撤销旧验收状态。 |
| 自动继续 | `[e2e] continue` | 列出路径、剩余场景、失败原因和实际催促额度；完整流程指令留在模型上下文。 |
| 正常结束仍未验收 | `[e2e] waiting` | 列出未完成 feature/场景、阻断原因、无新进展或额度耗尽，以及下一步；不重复相同等待状态。 |
| /e2e | running 后接判断结果 | 只判断已有文件；与工具使用同一条款列表和来源说明，不触发 agent 轮次，不解除运行验收。 |

```text
[e2e] running
Running project tests

[e2e] passed
Evidence: verified fresh test process
Feature: Checkout
Scenario: Checkout succeeds
Feature acceptance: 1/2 scenarios passed
Remaining: Payment declined
Clauses: 1/1 met

PASS 1. The order is confirmed
Source: deterministic, score 1.00

[e2e] needs review
Evidence: caller-supplied; acceptance unverified
Feature: Checkout
Scenario: Payment declined
Clauses: 0/1 met
Reason: no settled evidence for clause 1
Provider: NO_API_KEY: Set TYPESAFE_API_KEY to judge clauses with Jev.
Next: resolve the provider blocker or add deterministic checks over actual observations, then rerun verification.
```

条款和错误默认完整换行，不显示原始 Markdown 表格，不以省略号或 100 行上限丢掉尾部，也不要求 ctrl+o。检查点最多列出 20 个路径和 20 个失败场景，并说明遗漏数量；完整任务留在模型上下文和报告。通过报告是最终成功显示，不再另发成功通知。

| 生命周期边界 | 行为 |
| --- | --- |
| 两次调用之间修复 adapter | 下次调用捕获当前版本并执行新测试，无需新对话。 |
| 单次执行或评估中 feature/adapter 变化 | 拒绝本次证据，列出可识别的 adapter 变更文件，要求重跑。 |
| 通过后再次变更 | 收尾复核 feature 和已声明 adapter 指纹；相关 Pi 文件编辑仍立即撤销验收。 |
| 简单 Shell 查询 | 简单 pwd、ls、cat、rg 和受限 git status 查询保留通过，收尾仍复核指纹。组合命令和可启动子程序的选项不属于查询豁免。 |
| 未知 Shell 程序 | 保守撤销验收，避免现有 adapter 漏列应用依赖时保留旧通过。实现及测试依赖仍需在 adapterFiles 声明。 |
| 相同检查点、无新进展 | 不重复催促，也不重新授予额度。 |
| 用户取消或 agent error | 不自动继续，不追加通用验收警告；取消不能产生通过证据。 |
| 待处理用户输入 | 不争抢自动续跑。 |
| 新用户轮次 | 清除本轮验收状态；旧异步结果和错误回调不能污染新轮次。 |
| 用户明确只审查、不执行 | 不生成缺少验证的检查点；随后实际修改 feature 时仍执行变更检查。 |

取消边界：Pi 1.0 在正常 before_settle 时不提供 active signal。用户恰好在异步快照期间取消的窄竞态，公开事件可能不反映取消；本包只能检查实际提供的 signal/outcome 和待处理输入，不宣称该 SDK 边界已修复。
