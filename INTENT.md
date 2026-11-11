# Intent: 统一输入框上方 agent 消息的 thinking 显示
Author: Not provided. Status: draft.

## Problem
用户指出 `@packages/` 中 TUI 输入框上方的 agent 消息，对 Pi 的 thinking 显示设置处理不一致：只有 `@packages/subagents/` 在读者隐藏思考块时把推理原文换成 `Thinking...`，其他包仍把子代理或工作进程流式输出的 thinking 原文显示在同一类活动行上。

## Proposed outcome
所有 `@packages/` 中输入框上方的 agent 活动行统一使用 Pi 的 `hideThinkingBlock` 设置，并与 `@packages/subagents/` 的现有实现一致：设置为不显示时只显示 `Thinking...`（工具名、回答文本优先；设置可读时按每次刷新读取，会话中切换后下一次刷新生效），设置为显示或没有 settings API 时保持原有行为。共享标签、设置读取与活动策略放在 `@fradser/pi-kit`，由各包复用，避免再次各自实现。验收标准是：新增的隐藏/显示/回答优先回归场景通过，受影响包的测试、`bun run typecheck`、`bun run check` 与 pack 检查通过。

## Affected users and systems
用户只指明 `@packages/` 下 TUI 输入框上方的 agent 消息，以及作为参照的 `@packages/subagents/` 实现。其他受影响的用户或系统未提供。

## Constraints
用户的参照实现是唯一的显示规则来源；不改变各包已有的活动到达顺序、worker 启动参数、安装方式，也不新增外部依赖。仓库现有规则要求先写失败的回归场景、保持公共契约兼容，并运行受影响检查。未提供的限制：无。

## Open questions
用户未说明是否也要替换模型可见的 partial result 中的 thinking 文本；当前按"同一个活动文本"统一处理，以避免同一来源在两处给出不同内容。用户未指定真实终端 PTY 验收范围；按仓库规则做本地可复现验证并明确报告未验证的部分。

<!-- intent:event:c98094464f4ee20a9b7f50dd4038fe72b46eb45dd2571fc19e0670091f852103 -->
<details>
<summary>User request f5f90d75933e8c10 — 2026-11-09T08:19:12.669Z</summary>

> 所有 @packages/ 中TUI输入框上方的agnet的消息，都需要thinking的配置统一，如果pi的thinking设置为不显示，这里就和 @packages/subagents/ 的实现一样，只显示 Thinking...

</details>

<!-- intent:event:d4f9401a6977ae8c07677c69a48f358fd548678e55f0ec0b75827411bac8063f -->
<details>
<summary>User request 0990cb0757ece7db — 2026-11-11T16:59:47.047Z</summary>

> /skill:commit-and-push

</details>

<!-- intent:event:acc3b83042f5ad4f2783a726c2b9ce0cfe0de2a8c95a61bcb948fc2668e5dd9c -->
<details>
<summary>User request d324766487ddfe48 — 2026-11-11T17:02:22.623Z</summary>

> 并且发布所有的可发布的新版本

</details>
