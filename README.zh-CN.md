# Frad 的 Pi Packages ![](https://img.shields.io/badge/packages-15-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

[English](README.md) | **简体中文**

面向 Pi 的原生包，用于复用 skills、extensions 和工作流命令。

## 包列表

### [`@fradser/pi-agent-teams`](packages/agent-teams/)

通过简洁的 `agent` 委派和共享 `agent_event` 通信进行协作。每次新工作启动独立会话，默认使用全新上下文，也可用 `fork: true` 继承 Leader 上下文；最终回答自动回传，`work` 定向已有执行。仍支持常驻团队、任务看板和点对点消息。

省略 `definition.tools` 或传入 `[]` 只授权协调工具，不默认提供文件或 shell 能力；委派、启动和检查结果会显示实际工具授权。执行任务需明确选择最小工具集（`read`、`bash`、`edit`、`write`、`grep`、`find`、`ls`）。无法执行时，Worker 必须用 `work` 的 `submit` 动作明确提交 `outcome: "failed"`，不能只在最终回答里描述阻塞。普通最终回答是成功候选；没有验证门的完成并不表示独立验证通过。Leader 应委派具体的真实验收标准，必要时设置验证门；信息报告无需重复确认，除非决策或行动发生变化。

`agent start` 创建未分配的常驻会话，不伪造 Work ID，也不运行无任务的初始模型轮次；公开调用会等待原生就绪确认，返回后可立即向该精确会话分配任务，无需调用方轮询。后续看板通知和自主认领仍保留。恢复时先明确释放原 Work，确认执行权限真正释放后再分配同一 Work，不通过重复委派制造竞争任务。

[调度指导](packages/agent-teams/README.md#coordination-and-delivery) 明确单一集成验证负责人，将评审证据绑定到候选版本，并要求阻断评审返回、问题解决后再交付实现。纯评审任务返回报告即结束，定向复核需显式交接更新后的候选 brief。这是 Agent 指导，不是新增调度器或运行时完成锁。

**工具：** `agent`、`work`、`agent_event`

**命令：** `/agent-teams`

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

通过独立的、受研究提示词约束的 Pi 子进程（提供 read 和 bash 工具）检索代码仓库、库与技术问题；不修改工作区的边界来自研究提示词，而非操作系统沙箱。自然语言调研请求会自动调用工具；开始时完整显示请求文本，超宽自动换行，不加省略号，结果仍保持紧凑且可展开。

**工具：** `context_get`

**安装：**

```bash
pi install npm:@fradser/pi-context
```

### [`pi-continual-learning`](packages/continual-learning/)

从完成的用户任务中自动学习持久记忆与有明确范围的规则。Memory 提供有预算且可继续查阅的索引；扁平 Harness `rules` 提供 skill/text 指导，以及 Bash 消息、确认或阻止。也可通过 `/consolidate` 显式整理。存量 `policies`/`skillPrompts` 通过只读兼容保留原有保护，包括已有 output/artifact 检查；升级不改写配置，也不会仅因文件格式较旧就阻止无关命令。

**命令：** `/memory`、`/consolidate`、`/harness`

Harness 编写与自动学习默认写入项目 `.pi/harness.json`；只有明确请求不纳入 Git 的个人配置时，才使用 `.pi/harness.local.json`（`/harness --local`）。全局配置仅支持 `~/.pi/agent/harness.json`。Skill 指导需要已注册的 skill 及其展开后的调用；文件保存成功不等于触发验证通过，更不代表全局语义强制执行。

**安装：**

```bash
pi install npm:pi-continual-learning
```

### [`@fradser/pi-impeccable`](packages/impeccable/)

加载界面打磨、动画、排版、配色、布局、文案和浏览器迭代的设计指导。加载指导本身不会执行脚本，也不代表授权修改。

**工具：** `impeccable_load`

**命令：** `/impeccable`

**安装：**

```bash
pi install npm:@fradser/pi-impeccable
```

### [`pi-keyboard`](packages/keyboard/)

控制 VIA 和 QMK 键盘灯光以反映 Pi 的运行状态，包括空闲、思考、未读消息、审批提问和致命异常。需要兼容的键盘。

**命令：** `/keyboard`

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

### [`pi-open-deskos`](packages/open-deskos/)

把本机的 Pi 会话及其运作事件经 package 主动打开的 Desk Link 上报给 Open DeskOS，事件规则与运行时本地采集器完全一致。另外持有独立控制凭据时，可作为 Console 列出、启动、进入、改向、取消、结束并读取 desk 托管的 Pi 会话历史。

**命令：** `/open-deskos`

**安装：**

```bash
pi install npm:pi-open-deskos
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

**命令：** `/recap`、`/recap now`、`/recap on`、`/recap off`、`/recap auto`、`/recap model [provider/model]`

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

提供 `/effort`、`/continue`、`/sessions`、`/init`、内部私有实时会话控制，以及安全的 Git worktree 隔离。

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
pnpm test
pnpm typecheck
pnpm pack:check
# 或一次运行全部检查
pnpm check
```

每个包将行为场景放在 `features/`，测试放在 `tests/`。

`pnpm check` 会运行包测试和根目录 pytest 测试、扩展 TypeScript 项目检查，以及对每个工作区包进行无需访问 registry 的打包清单检查。使用 `pnpm check:install` 可以单独审计当前 Pi 设置文件中的已安装包。

测试需要 Python 3、`pytest` 以及供子进程测试使用的 Bun 1.4.1。CI 工作流会在运行 `pnpm check` 前安装这两个运行时。

在仓库根目录执行 `pnpm --dir packages/<name> pack --dry-run` 可以检查单个包将要发布的文件。

共享运行时辅助位于内部包 [`@fradser/pi-kit`](packages/kit/)。它是内部工作区依赖，不能通过 `pi install` 安装。生命周期渲染器仅在有补充展示内容，或当前宽度隐藏了可展开恢复的文字时提示展开，不因工具结果含有 metadata 就显示提示。各包移除与标题重复的详情，同时保留完整报告和有用的诊断信息。

## 添加包

1. 创建 `packages/<name>/`。
2. 添加包含 `pi-package` keyword 和明确 `pi` 资源声明的 `package.json`。
3. 将运行时资源包含进 `files`，并将导入的 Pi 核心包声明为 peer dependency。
4. 在实现前于 `features/` 下编写 BDD 场景，然后添加可执行测试。
5. 为已发布包的修改添加 Changeset。

## 发布

发布使用 `.github/workflows/release.yml` 中的 Changesets 和 GitHub Actions 工作流。Pull request 和发布流程都会在发布动作前运行 `pnpm check`；根目录的 `pnpm run publish` 也会在本地发布脚本前运行同一质量门。将修改推送到 `main`，然后合并生成的 version PR。工作流按依赖顺序通过 npm Trusted Publishing 发布明确列出的包，并跳过 registry 中已经存在的精确版本。

新包需要先手动完成一次首次发布并配置 npm Trusted Publishing，后续版本才能通过 GitHub Actions 发布。

## 许可证

每个包均使用 MIT 许可证。
