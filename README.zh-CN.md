# Frad 的 Pi Packages ![](https://img.shields.io/badge/packages-10-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

[English](README.md) | **简体中文**

面向 Pi 的原生包，用于复用 skills、extensions 和工作流命令。

## 包列表

### [`keyboard`](packages/keyboard/)

控制 VIA 和 QMK 键盘灯光以反映 Pi 的运行状态，包括空闲、思考、未读消息、审批提问和致命异常。

**安装：**

```bash
pi install npm:pi-keyboard
```

### [`recap`](packages/recap/)

在 TUI 输入框上方显示会话进展摘要，并支持在重启后恢复。

**命令：** `/recap`、`/recap on`、`/recap off`、`/recap language <lang>`、`/recap model <model>`

**安装：**

```bash
pi install npm:@fradser/pi-recap
```

### [`vision`](packages/vision/)

当当前 Pi 模型只接受文本时，将图片交给已配置的视觉模型进行分析。

**命令：** `/vision`、`/vision model provider/model`、`/vision on`、`/vision off`

**安装：**

```bash
pi install npm:@fradser/pi-vision
```

### [`btw`](packages/btw/)

在只读浮层中回答旁路问题，不会把问题加入当前会话历史。

**命令：** `/btw <question>`

**安装：**

```bash
pi install npm:@fradser/pi-btw
```

### [`pi-continual-learning`](packages/continual-learning/)

harness 与提示词表面的持续学习：声明式工具调用 guardrails（拦截并给出更正指引），以及记忆检索、注入与手动整合。模型权重不在范围内。

**命令：** `/memory`、`/consolidate`、`/guardrails`

**安装：**

```bash
pi install npm:pi-continual-learning
```

### [`monitor`](packages/monitor/)

按明确的结果契约在后台运行命令，并发送一条结构化终态结果。

**工具：** `monitor_start`、`monitor_stop`

**安装：**

```bash
pi install npm:@fradser/pi-monitor
```

### [`utils`](packages/utils/)

提供 `/effort`、`/continue` 和 `/sessions`，并将安全的 Git worktree 定向到 `.pi/worktrees/`。

**安装：**

```bash
pi install npm:@fradser/pi-utils
```

### [`agent-teams`](packages/agent-teams/)

通过依赖关系任务图、并发限制、取消、重试和全屏控制台协调 Pi 子 worker。

**工具：** `teammate_run`、`teammate_fanout`、`teammate_message`、`teammate_cancel`、`teammate_retry`

**命令：** `/teammate`

**安装：**

```bash
pi install npm:@fradser/pi-agent-teams
```

### [`context`](packages/context/)

通过原生 Pi extension 提供 DeepWiki、Context7 和 Exa 检索工具，并支持 clone 与 HTTP 抓取兜底。通过系统提示词指引加 `/context` 命令（无 skill）。

**命令：** `/context`

**安装：**

```bash
pi install npm:@fradser/pi-context
```

### [`matt-pocock`](packages/matt-pocock/)

提供 `/matt-pocock` 持久化 Pi 工作流 harness，覆盖适配 Pi 的 BDD、TDD、实现、评审、调试、架构、调研、规划、教学和 skill 编写 procedure。

**从本地检出安装：**

```bash
pi install /path/to/pi-packages/packages/matt-pocock
```

### [`skill-router`](packages/skill-router/)

路由到外部托管的 skill 集合：通过 `/skill-router` 菜单添加任意 GitHub skill 仓库，所选 skill 会被封装为带前缀的隐藏叶子，挂在模型可见的网关之后，并提供精准的路由建议。包本身不携带任何 skill 内容，集合也不再是独立 npm 包。

**安装：**

```bash
pi install npm:pi-skill-router
```

## 开发

```bash
pnpm install
python3 -m pytest packages
```

每个包将行为场景放在 `features/`，测试放在 `tests/`。修改 extension 后，运行对应的严格 TypeScript 检查：

```bash
npx tsc --noEmit --strict --skipLibCheck --target ES2022 \
  --module ESNext --moduleResolution bundler --types "" \
  packages/<name>/{src,extensions}/*.ts
```

在包目录执行 `pnpm pack --dry-run` 可以检查将要发布的文件。

共享运行时辅助（TUI 旋转帧/主题样式原语、消息文本提取）位于内部包 [`@fradser/pi-kit`](packages/kit/)。它不是 Pi 包，不能用 `pi install` 安装；消费包在 `dependencies` 中以 `"@fradser/pi-kit": "workspace:*"` 声明它。

## 添加包

1. 创建 `packages/<name>/`。
2. 添加包含 `pi-package` keyword 和明确 `pi` 资源声明的 `package.json`。
3. 将运行时资源包含进 `files`，并将导入的 Pi 核心包声明为 peer dependency。
4. 在实现前于 `features/` 下编写 BDD 场景，然后添加可执行测试。
5. 为已发布包的修改添加 Changeset。

## 发布

发布使用 `.github/workflows/release.yml` 中的 Changesets 和 GitHub Actions 工作流。将修改推送到 `main`，然后合并生成的 version PR。工作流通过 npm Trusted Publishing 发布明确列出的包，并跳过 npm registry 中已经存在的版本，因此部分发布失败后可以安全重试。

新包需要先手动完成一次首次发布并配置 npm Trusted Publishing，后续版本才能通过 GitHub Actions 发布。

## 许可证

每个包均使用 MIT 许可证。
