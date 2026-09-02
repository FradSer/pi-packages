# Frad 的 Pi Packages ![](https://img.shields.io/badge/packages-12-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

[English](README.md) | **简体中文**

面向 Pi 的原生包，用于复用 skills、extensions 和工作流命令。

## 包列表

### [`@fradser/pi-agent-teams`](packages/agent-teams/)

面向 Pi 的 Claude Code 风格多 Agent 协同团队：支持具名常驻队友、共享任务看板和点对点消息通信。

**工具：** `teammate_spawn`、`teammate_shutdown`、`task_create`、`send_message`、`task_list`

**命令：** `/agent-teams`、`/teammate`

**安装：**

```bash
pi install npm:@fradser/pi-agent-teams
```

### [`@fradser/pi-btw`](packages/btw/)

在只读浮层中回答旁路问题，不会把问题加入当前会话历史。

**命令：** `/btw <question>`

**安装：**

```bash
pi install npm:@fradser/pi-btw
```

### [`@fradser/pi-context`](packages/context/)

通过独立的只读 Pi 子进程检索代码仓库、库与技术问题。

**工具：** `context_get`

**命令：** `/context`

**安装：**

```bash
pi install npm:@fradser/pi-context
```

### [`pi-continual-learning`](packages/continual-learning/)

harness 与提示词表面的持续学习：声明式工具调用 guardrails（拦截并给出更正指引），以及记忆检索、注入与手动整合。

**命令：** `/memory`、`/consolidate`、`/guardrails`

**安装：**

```bash
pi install npm:pi-continual-learning
```

### [`pi-keyboard`](packages/keyboard/)

控制 VIA 和 QMK 键盘灯光以反映 Pi 的运行状态，包括空闲、思考、未读消息、审批提问和致命异常。

**安装：**

```bash
pi install npm:pi-keyboard
```

### [`pi-matt-pocock`](packages/matt-pocock/)

提供持久化 Pi 工作流 harness，覆盖适配 Pi 的 BDD、TDD、实现、评审、调试、架构、调研、规划、教学与 skill 编写流程。

**工具：** `matt_pocock_workflow`

**命令：** `/matt-pocock`

**安装：**

```bash
pi install npm:pi-matt-pocock
```

### [`@fradser/pi-monitor`](packages/monitor/)

按明确的结果契约在后台运行命令，并发送一条结构化终态结果。

**工具：** `monitor_start`、`monitor_stop`

**命令：** `/monitor`

**安装：**

```bash
pi install npm:@fradser/pi-monitor
```

### [`@fradser/pi-plan-mode`](packages/plan-mode/)

在修改代码前于主会话中进行只读探索与规划，支持独立的规划模型。

**命令：** `/plan`、`/plan start`、`/plan exit`、`/plan model`、`/plan status`

**安装：**

```bash
pi install npm:@fradser/pi-plan-mode
```

### [`@fradser/pi-recap`](packages/recap/)

在 TUI 输入框上方显示会话进展摘要，并支持在重启后恢复。

**命令：** `/recap`、`/recap on`、`/recap off`、`/recap language <lang>`、`/recap model <model>`

**安装：**

```bash
pi install npm:@fradser/pi-recap
```

### [`pi-skill-router`](packages/skill-router/)

路由到外部托管的 skill 集合：通过 `/skill-router` 菜单添加 GitHub skill 仓库，将所选 skill 挂载在模型可见的网关之后。包本身不直接附带 skill 内容。

**命令：** `/skill-router`

**安装：**

```bash
pi install npm:pi-skill-router
```

### [`@fradser/pi-utils`](packages/utils/)

提供 `/effort`、`/continue`、`/sessions`、`/init`，并将安全的 Git worktree 定向到 `.pi/worktrees/`。

**工具：** `enter_worktree`、`exit_worktree`、`list_directory_sessions`

**命令：** `/effort`、`/continue`、`/sessions`、`/init`

**安装：**

```bash
pi install npm:@fradser/pi-utils
```

### [`@fradser/pi-vision`](packages/vision/)

当当前 Pi 模型只接受文本时，将图片交给已配置的视觉模型进行分析。

**命令：** `/vision`、`/vision model <model>`、`/vision on`、`/vision off`

**安装：**

```bash
pi install npm:@fradser/pi-vision
```

## 开发

```bash
pnpm install
python3 -m pytest packages
npx tsc --noEmit -p tsconfig.extensions.json
```

每个包将行为场景放在 `features/`，测试放在 `tests/`。

在包目录执行 `pnpm --dir packages/<name> pack --dry-run` 可以检查将要发布的文件。

共享运行时辅助位于内部包 [`@fradser/pi-kit`](packages/kit/)。它是内部工作区依赖，不能通过 `pi install` 安装。

## 添加包

1. 创建 `packages/<name>/`。
2. 添加包含 `pi-package` keyword 和明确 `pi` 资源声明的 `package.json`。
3. 将运行时资源包含进 `files`，并将导入的 Pi 核心包声明为 peer dependency。
4. 在实现前于 `features/` 下编写 BDD 场景，然后添加可执行测试。
5. 为已发布包的修改添加 Changeset。

## 发布

发布使用 `.github/workflows/release.yml` 中的 Changesets 和 GitHub Actions 工作流。将修改推送到 `main`，然后合并生成的 version PR。工作流通过 npm Trusted Publishing 发布明确列出的包，并跳过 npm registry 中已经存在的版本。

新包需要先手动完成一次首次发布并配置 npm Trusted Publishing，后续版本才能通过 GitHub Actions 发布。

## 许可证

每个包均使用 MIT 许可证。
