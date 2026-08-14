# Frad 的 Pi Packages ![](https://img.shields.io/badge/packages-8-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

[English](README.md) | **简体中文**

面向 Pi 的原生包，用于复用 skills、extensions 和工作流命令。

## 使用包

Skill 使用 Pi 的 `/skill:<name>` 命令。命令后的参数会追加到 skill 文本。Pi 不会展开 `$ARGUMENTS`，也不会执行 skill Markdown 中嵌入的 shell 替换。

管理交互式工作流的包使用 `/memory`、`/btw`、`/teammate` 等原生命令，而不是 skill。

已发布的包可以使用带 `npm:` 前缀的命令安装：

```bash
pi install npm:@fradser/pi-memory
```

开发时，所有包都可以从当前 checkout 安装：

```bash
pi install /path/to/pi-packages/packages/<name>
```

## 包列表

### [`vision`](packages/vision/)

当当前模型仅支持文本时，通过已配置的 Pi 视觉模型将图片转换为文字。它保留原始会话附件，只将视觉分析加入瞬态 provider context。

**命令：** `/vision`、`/vision model provider/model`、`/vision on`、`/vision off`

**可用性：** 请从当前 checkout 安装。首个 npm 版本尚未发布。

---

### [`btw`](packages/btw/)

在只读浮层中回答旁路问题，不会写入当前会话历史。子 Pi 进程可以使用 `read`、`grep`、`find` 和 `ls` 检查代码库，但不能使用 `bash`、`edit` 或 `write`。

**命令：** `/btw <question>`

**安装：**

```bash
pi install npm:@fradser/pi-btw
```

---

### [`code-context`](packages/code-context/)

提供 DeepWiki、Context7 和 Exa 检索工具，并以 clone 与 HTTP 抓取工作流作为兜底。该包直接调用 REST API，不使用 MCP sidecar。

**Skills：** `/skill:get-context`、`/skill:code-context`

**工具：** `context_deepwiki`、`context_context7`、`context_exa`

**可用性：** 请从当前 checkout 安装。该包目前尚未发布到 npm。

---

### [`mattpocock`](packages/mattpocock/)

一组适配 Pi 的 BDD、TDD、实现、评审、调试、架构、调研、规划、交接、教学和 skill 编写工作流。

**Skills：** 共 27 个独立 skill，包括 `/skill:bdd`、`/skill:tdd`、`/skill:implement` 和 `/skill:code-review`

**可用性：** 请从当前 checkout 安装。该包目前尚未发布到 npm。

---

### [`memory`](packages/memory/)

通过 `/memory` 菜单、自动记忆引导和后台整合管理持久化项目记忆。整合流程在独立的子 Pi 进程中执行，其原始工作内容不会进入当前对话。

**命令：** `/memory`、`/consolidate`

**安装：**

```bash
pi install npm:@fradser/pi-memory
```

---

### [`monitor`](packages/monitor/)

在后台按明确的结果契约运行命令。普通输出保留在模型 context 之外，并且仅在成功、失败、超时或缺失结果时发送一条结构化终态结果。

**工具：** `monitor_start`、`monitor_read`、`monitor_list`、`monitor_stop`

**Skill：** `/skill:using-monitor`

**命令：** `/monitor`

**安装：**

```bash
pi install npm:@fradser/pi-monitor
```

---

### [`agent-teams`](packages/agent-teams/)

通过 leader 持有的任务板和邮箱协议协调自治的子 Pi worker。Team leader 可以注册 teammate、创建并启动就绪任务、等待结果、发送消息、取消运行，并打开全屏控制台。

**工具：** `teammate_register`、`teammate_list`、`teammate_configure`、`teammate_remove`、`teammate_message`、`teammate_inbox`、`teammate_create_task`、`teammate_list_tasks`、`teammate_start_task`、`teammate_wait`、`teammate_cancel_task`、`teammate_cleanup`

**命令：** `/teammate`

**可用性：** 请从当前 checkout 安装。该包目前尚未发布到 npm。

---

### [`utils`](packages/utils/)

增加选择模型 thinking level 和恢复中断工作的命令，也会将安全的 `git worktree add` 调用定向到 `.pi/worktrees/`。

**命令：** `/effort`、`/continue`

**安装：**

```bash
pi install npm:@fradser/pi-utils
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

在单个 package 目录执行 `pnpm pack --dry-run` 可以检查将要发布的文件。

## 添加包

1. 创建 `packages/<name>/`。
2. 添加带有 `pi-package` 关键字和明确 `pi` 资源清单的 `package.json`。
3. 将所有运行时资源加入 `files`，并把每个导入的 Pi 核心包声明为 peer dependencies。
4. 先在 `features/` 中写 BDD 场景，再实现代码和可执行测试。
5. 使用 `pi install /path/to/pi-packages/packages/<name>` 本地安装，并验证 package 内容。

## 发布

本仓库通过 Changesets 和 GitHub Actions release workflow 发布。不要在仓库根目录执行递归 `pnpm publish`。

对于已发布包的改动，创建 Changeset、推送到 `main`，然后合并生成的 version PR。release workflow 仅使用 npm trusted publishing 发布明确的 package allowlist。新包在 workflow 可发布后续版本前，需要先完成首次 npm 发布和 trusted publishing 设置。

## 许可证

每个包在自己的 manifest 中声明 MIT 许可证。仓库根目录没有单独的许可证文件。
