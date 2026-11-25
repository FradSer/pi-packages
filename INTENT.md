# Intent: 退役 @fradser/pi-plan-mode
Author: Not provided. Status: draft.

## Problem
用户要求退役仓库中的 `packages/plan-mode/`（npm 名 `@fradser/pi-plan-mode`）。该包继续留在活跃工作区会持续占用发布 allowlist、根 README 与包内约定中的位置，也会让维护者的 Pi 配置继续加载一个不再维护的扩展。

## Proposed outcome
`packages/plan-mode/` 迁移到 `deprecated/plan-mode/` 并冻结，附带退役原因与兼容说明；它不再出现在发布 allowlist、不再被本仓库发布，也从维护者的 Pi 配置中移除。成功标准是：仓库门禁（Bun 测试、typecheck、打包清单校验）通过，根级 pytest 中受影响的接线测试通过，归档包自身测试在新路径下仍可运行；`pi list` 不再列出该包，`pi --print` 可以正常启动。

## Affected users and systems
本仓库 pi-packages 的工作区结构、发布 allowlist、根 README/AGENTS 文档与测试；维护者本机 `~/.pi/agent/settings.json` 中的本地包条目。用户未指定其他系统。

## Constraints
沿用 `deprecated/tasks` 的退役方式：保留源码与 Git 历史，不删除文件，不改动归档包的运行时行为。不执行需要额外授权的公共注册表操作，包括 `npm deprecate`、取消发布或发布新版本。保留其他会话已有改动与仓库现有约定（git-agent 提交、Changesets 发布流程）。

## Open questions
是否要在 npm 上将 `@fradser/pi-plan-mode` 标记为 deprecated 尚未确认；该操作会修改公共注册表，需要单独授权。归档包的真实 PTY/模型验收（`tests/test_plan_live.py`）未运行。退役后用户是否有替代的本地计划流程（例如 sdlc 或 matt-pocock 的计划阶段）未经用户确认。

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

<!-- intent:event:6a206be9a85c38b9ba373a5d18bf31e3113459bb1296b252491254b528878e4c -->
<details>
<summary>User request 789eb6ba834ef57c — 2026-11-12T03:06:03.638Z</summary>

> npm login 已经登录

</details>

<!-- intent:event:f53a616b6ab2398e730aed813c6473f62c325051210f2c2701d99eba87f6d1e3 -->
<details>
<summary>User request dd1f3b0100bc4556 — 2026-11-12T05:37:50.196Z</summary>

> 弄好了

</details>

<!-- intent:event:1cef8261256e93a679768f8061197db1b7fbc59478343eb093bfb6b26170491e -->
<details>
<summary>User request d35ff83df0e2d6d4 — 2026-11-12T05:39:56.766Z</summary>

> ➜    for p in @fradser/pi-magpie pi-keyboard @fradser/pi-agent-teams @fradser/pi-context pi-matt-pocock pi-skill-router pi-open-deskos; do
>      npm trust github "$p" --file release.yml --repo FradSer/pi-packages --allow-publish -y || break
>    done
> Establishing trust between @fradser/pi-magpie package and GitHub Actions
> Anyone with GitHub repository write access can publish to @fradser/pi-magpie
> Two-factor authentication is required for this operation
>
> package: @fradser/pi-magpie
> file: release.yml
> repository: FradSer/pi-packages
> permissions: publish
>
> https://www.npmjs.com/package/@fradser/pi-magpie
> https://github.com/FradSer/pi-packages/blob/HEAD/.github/workflows/release.yml
> https://github.com/FradSer/pi-packages
>
> npm notice npm tokens that bypass 2FA are being restricted for account changes and direct publishing. Learn how to prepare: https://gh.io/npm-gat-bypass2fa-deprecation
> npm error code E409
> npm error 409 Conflict - POST https://registry.npmjs.org/-/package/@fradser%2fpi-magpie/trust - a trusted publisher configuration that a token could also match already exists for this package; list the package trusted publishers to find it
> npm error A complete log of this run can be found in: /Users/FradSer/.npm/_logs/2026-11-12T05_39_48_638Z-debug-0.log

</details>
