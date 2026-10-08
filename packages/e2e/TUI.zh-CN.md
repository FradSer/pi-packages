# E2E 工作流与 TUI

流程：运行当前项目 adapter → 判断本次证据 → 修复未满足项 → 同轮再次 e2e_verify。每次都运行新测试，手动调用没有每轮次数限制。自动检查点只是最多两次催促，不能代替测试或强制通过。

| 场景 | 触发条件 | 默认显示和后续动作 |
| --- | --- | --- |
| fulfilled | 本次所有 Then 已确认 | 完整报告及 verified fresh test process；整个请求 feature 的所有场景通过才解除验收。 |
| not_fulfilled / partially_fulfilled | 确定性失败或语义判定未满足 | 完整失败条款和原因；修复后同轮再调用。 |
| needs_review | 缺少证据、未判断条款、概率不足或模型不可用 | 显示未判断条款与原因，不推断通过。 |
| error | 无效参数、缺少配置、runner 非零、超时、非法证据等 | 完整诊断；本次失败撤销该场景旧验收状态，修复后重试。 |
| adapter 两次调用之间变更 | 已授权的实现、测试或 runner 被修复 | 下次调用捕获新版本并执行新测试，无需开启新对话。 |
| adapter 单次调用期间变更 | 执行或评估过程中指纹变化 | 拒绝本次证据，列出变更文件，要求重新运行。 |
| 通过后又变更 | feature、adapter 或相关实现活动使证明过期 | 旧结果不能清除检查点，必须重新执行。 |
| inline、已有 evidence 或 /e2e | 仅判断调用者提供的内容 | 可以报告 fulfilled，但来源标记 caller-supplied，不能解除运行验收。 |
| 自动继续 | 请求、改动或失败尚未验收，存在新相关进展且还有额度 | `[e2e] continue · acceptance verification`，路径、剩余场景名、失败原因和实际额度；完整流程指令仅留在模型上下文。 |
| 相同检查点 | 没有新相关工作或新判断结果 | 不重复催促。 |
| 正常结束仍未验收 | 缺少通过结果、场景只通过一部分或额度耗尽 | `[e2e] waiting · … need verification`，不重复打印计数和模型行为指令。 |
| 用户取消或 agent error | before_settle 提供非 completed outcome | 不自动继续，不追加通用验收警告；取消不能产生通过证据。 |
| 待处理用户输入 | 当前 boundary 或公开 ctx 表明输入待处理 | 不争抢自动续跑。 |
| 新用户轮次 | 用户开始下一轮 | 清除当前验收状态；旧异步结果与错误回调不能污染新轮次。 |
| 仅审查、不运行 | 用户明确拒绝执行 e2e | 不生成缺少验证的自动检查点；若随后实际修改 feature，其变更检查仍按契约运行。 |

工具结果、错误和检查点使用 pi-kit 的 `[e2e]` 行，正文默认完整换行，不以省略号或 100 行上限丢掉尾部，不要求 ctrl+o。一次检查点最多列出 20 个路径和 20 个失败场景，并明确说明遗漏数量；完整任务仍在模型上下文和验证报告中。

```text
[e2e] error · verification
e2e_verify failed: Runner configuration or adapter changed during verification:
tests/acceptance-adapter.mjs. Call e2e_verify again to run fresh tests

[e2e] continue · acceptance verification
Feature: features/checkout.feature
Checkout succeeds (not_fulfilled): deterministic check failed for clause 1
Automatic continuation 1/2

[e2e] waiting · 1 feature(s) need verification
```

取消边界：Pi 1.0 在正常 before_settle 时不提供 active signal。用户恰好在异步快照期间取消的窄竞态，当前公开事件可能不反映取消；这里只能对实际提供的 signal/outcome 和待处理输入作检查。该 SDK 边界没有被本包宣称为已修复或实机复现。

通过报告是最终成功显示，不再另发成功通知。部分通过的检查点增加
`Remaining: <feature> · <scenario>`，避免重跑已通过的场景。`needs_review`
要求补齐观察/检查或解决 runner/provider 阻断；不得仅因缺证据就修改实现。
无新变化的真实收尾刷新不会重新授予或消耗催促额度。
