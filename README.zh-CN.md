# Frad 的 Pi Packages ![](https://img.shields.io/badge/packages-10-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

[English](README.md) | **简体中文**

面向 Pi 的原生包，用于复用 skills、extensions 和工作流命令。

## 使用包

Skill 使用 Pi 的 `/skill:<name>` 命令。命令后的参数会追加到 skill 文本。Pi 不会展开 `$ARGUMENTS`，也不会执行 skill Markdown 中嵌入的 shell 替换。

管理交互式工作流的包使用 `/keyboard`、`/recap`、`/memory`、`/btw`、`/teammate` 等原生命令，而不是 skill。

已发布的包可以使用 npm 源安装：

```bash
pi install npm:pi-keyboard
pi install npm:@fradser/pi-memory
```

开发时，所有包都可以从当前 checkout 安装：

```bash
pi install /path/to/pi-packages/packages/<name>
```

## 包列表

### [`keyboard`](packages/keyboard/)

控制 VIA 和 QMK 机械键盘的 RGB 灯光以反映 Pi 的运行状态，包括空闲待命白色呼吸、思考运行蓝色呼吸、未读消息绿色呼吸、审批提问黄色闪烁以及致命异常红色闪烁。所有更新均在内存中执行，不写入 EEPROM 或 Flash。

**命令：** `/keyboard`、`/keyboard on`、`/keyboard off`、`/keyboard status`、`/keyboard test <state>`

**安装：**

```bash
pi install npm:pi-keyboard
```

---

### [`recap`](packages/recap/)

在 TUI 输入框上方生成并展示当前会话进展的精简回顾。支持在重启后恢复已保存摘要，并自动同步同一目录下的多会话进展。

**命令：** `/recap`、`/recap on`、`/recap off`、`/recap language <lang>`、`/recap model <model>`

**安装：**

```bash
pi install npm:@fradser/pi-recap
```

---

### [`vision`](packages/vision/)

当当前模型仅支持文本时，通过已配置的 Pi 视觉模型将图片转换为文字。它保留原始会话附件，只将视觉分析加入瞬态 provider context。

**命令：** `/vision`、`/vision model provider/model`、`/vision on`、`/vision off`

**安装：**

```bash
pi install npm:@fradser/pi-vision
```

---

### [`btw`](packages/btw/)

在只读浮层中回答旁路问题，不会写入当前会话历史。子 Pi 进程可以使用 `read`、`grep`、`find` 和 `ls` 检查代码库，但不能使用 `bash`、`edit` 或 `write`。

**命令：** `/btw <question>`

**安装：**

```bash
pi install npm:@fradser/pi-btw
```

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

**工具：** `monitor_start`、`monitor_stop`

**Skill：** `/skill:using-monitor`

**命令：** `/monitor`

**安装：**

```bash
pi install npm:@fradser/pi-monitor
```

---

### [`utils`](packages/utils/)

增加选择模型 thinking level 和恢复中断工作的命令，提供跨会话注册表同步，并将安全的 `git worktree add` 调用定向到 `.pi/worktrees/`。

**命令：** `/effort`、`/continue`、`/sessions`

**安装：**

```bash
pi install npm:@fradser/pi-utils
```

---

### [`agent-teams`](packages/agent-teams/)

通过以 run 为核心的任务图和邮箱协议协调自治的子 Pi worker。Team leader 可以单次调用派发具有依赖关系的任务图、追踪进展、取消或重试节点，并打开全屏控制台。

**工具：** `teammate_run`、`teammate_status`、`teammate_cancel`、`teammate_retry`、`teammate_message`、`teammate_inbox`

**命令：** `/teammate`

**可用性：** 请从当前 checkout 安装。该包目前尚未发布到 npm。

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

## 开发

```bash
pnpm install
python3 -m pytest packages
```

每个包将行为场景放在 `features/`，测试放在 `tests/`。修改 extension 后，运行对应的严格 TypeScript 检查：\

```bash
npx tsc --noEmit --strict --skipLibCheck --target ES2022 \
  --module ESNext --moduleResolution bundler --types "" \
  packages/<name>/{src,extensions}/*.ts
```

在单个 package 目录执行 `pnpm pack --dry-run` 可以检查将要发布的文件。

## 添加包

1. 创建 `packages/<name>/`。
2. 添加包含 `pi-package` keyword 和明确 `pi` 资源声明的 `package.json`。
3. 将所有运行时资源包含进 `files`，并将导入的 Pi 核心包声明为 peer dependency。
4. 在实现前在 `features/` 下编写 BDD 场景，然后添加可执行测试。
5. 使用 `pi install /path/to/pi-packages/packages/<name>` 本地安装该包并校验其内容。

## 发布

本仓库通过 Changesets 和 GitHub Actions 发布工作流进行发布。不要在仓库根目录直接运行递归的 `pnpm publish`。

对于已发布包的修改，创建 Changeset，推送到 `main` 分支，并合并生成的 version PR。发布工作流仅通过 npm trusted publishing 发布白名单中指定的包。新增的包需要先完成首次 npm 手动发布与 trusted-publishing 信任配置，后续版本才能通过工作流自动发布。

## 许可证

每个包在自己的清单中声明 MIT 许可证。本仓库不设单独的根许可证文件。
