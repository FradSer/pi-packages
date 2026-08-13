# Frad 的 Pi Packages ![](https://img.shields.io/badge/packages-8-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

[English](README.md) | **简体中文**

面向 Pi 的原生包,用于复用 Agent skills、extensions 和项目工作流。

## 调用方式

所有 skill 都使用 Pi 的 `/skill:<name>` 命令调用。参数会追加在 skill 内容之后;Pi 不会展开 `$ARGUMENTS`,也不会执行 skill Markdown 中的 shell 注入。工作流类包使用原生命令(`/memory`、`/btw`、`/teammate`)。

## 包列表

### [`btw`](packages/btw/)

`/btw <question>` 在输入框上方的只读浮层中回答旁路问题,不打断当前任务,也绝不进入会话历史。与 Claude Code 的 `/btw` 不同,它会调用只读工具(`read`、`grep`、`find`、`ls`)在代码库中验证事实,并且严格只读:`bash`、`edit`、`write` 始终被排除。

**命令:** `/btw <question>`

**安装:**
```bash
pi install npm:@fradser/btw
# 或本地安装:pi install /path/to/pi-packages/packages/btw
```

---

### [`code-context`](packages/code-context/)

通过 DeepWiki、Context7、Exa、直接 git clone 和网页抓取获取代码上下文。检索方式是原生 pi 工具(`context_deepwiki`、`context_context7`、`context_exa`),直接调用公开 REST API;git clone 和 HTTP 抓取始终作为兜底可用。

**Skills:** `code-context`、`get-context`

**安装:**
```bash
pi install npm:@fradser/code-context
# 或本地安装:pi install /path/to/pi-packages/packages/code-context
```

---

### [`lark`](packages/lark/)

### [`lark`](packages/lark/)

镜像自 larksuite/cli 的飞书/Lark CLI skills:文档、表格、消息、日历、审批、云盘、知识库、通讯录、邮件、任务、会议及相关服务。

**Skills:** `lark` 路由加镜像的 Lark 子 skills

**安装:**
```bash
pi install npm:@fradser/lark
# 或本地安装:pi install /path/to/pi-packages/packages/lark
```

---

### [`mattpocock`](packages/mattpocock/)

改编自 Matt Pocock skills 的 BDD 优先工程与效率 skills,涵盖 TDD、实现、调试、架构、调研、代码评审、规划、交接、教学和 skill 编写。

**Skills:** `engineering`、`productivity`(内含各主题子 skills)

**安装:**
```bash
pi install npm:@fradser/mattpocock
# 或本地安装:pi install /path/to/pi-packages/packages/mattpocock
```

---

### [`memory`](packages/memory/)

原生 `/memory` 命令:自动记忆引导、指令编辑菜单和记忆整合(聚类、时效检查、接地验证、隐私校验)。整合以内联流程在后台 worker 中运行。无 skill 面。

**命令:** `/memory` 菜单: 立即整合、编辑指令、打开自动记忆目录、开关自动记忆

**安装:**
```bash
pi install npm:@fradser/memory
# 或本地安装:pi install /path/to/pi-packages/packages/memory
```

---

### [`monitor`](packages/monitor/)

在后台运行 shell 命令并把 stdout 流式推给 agent 作为通知,让它在日志、部署、CI 或文件变化发生的当下做出反应,无需轮询循环。

**工具:** `monitor_start`、`monitor_list`、`monitor_stop` · **Skill:** `using-monitor` · **命令:** `/monitor`

**安装:**
```bash
pi install npm:@fradser/monitor
# 或本地安装:pi install /path/to/pi-packages/packages/monitor
```

---

### [`teammate`](packages/teammate/)

多 agent 团队系统:注册 teammate、分配任务、邮箱通信,以及监控自己邮箱并自主决定何时关闭的自治子 Pi worker。通过 `/teammate` 全屏控制台管理。

**工具:** `teammate_register` / `list` / `send` / `read_mailbox` / `assign_task` / `list_tasks` / `update_task` / `broadcast` / `spawn` / `task_deps` / `remove` / `cleanup` / `reset` / `update_model` · **命令:** `/teammate` · **Skill:** `using-teammate`

**安装:**
```bash
pi install npm:@fradser/teammate
# 或本地安装:pi install /path/to/pi-packages/packages/teammate
```

---

### [`utils`](packages/utils/)

一个 pi 原生的 `/effort` 命令,用于设置会话的 thinking level(菜单或内联,例如 `/effort max`)。

**命令:** `/effort`

**安装:**
```bash
pi install npm:@fradser/utils
# 或本地安装:pi install /path/to/pi-packages/packages/utils
```

## 说明

`git-agent` 的 pi 包已移到 git-agent 仓库(`git-agent/git-agent-pi-package`),以 `/git-agent` 暴露 `commit` / `commit-and-push` 工作流(AI 原子提交,git-agent CLI),无 skill 面。`memory` 包采用同样的菜单模式(`/memory`,无 skill 面)。

## SDK Harness

`examples/sdk-session.ts` 演示了 `createAgentSession()` 的编程式用法,接线包扩展并检查发现的 skills。

```bash
pnpm example:sdk
# 或直接运行:
npx tsx examples/sdk-session.ts
# 可选:真实模型回合
PI_SDK_LIVE=1 npx tsx examples/sdk-session.ts
```

## 添加新包

1. 在 `packages/` 下创建包目录。
2. 添加带 `pi-package` 关键字和 `pi` 资源清单的 `package.json`。
3. 在 `package.json` 声明的路径下添加 skills、extensions、prompts 或 themes。
4. 用 `pi install /path/to/pi-packages/packages/<name>` 安装本地包并运行其测试。
5. 运行 `/skill:update-readme` 同步两个 README 文件。

## 发布

包以 `@fradser` scope 发布到 npm,并通过 `pi-package` 关键字出现在 [pi.dev/packages](https://pi.dev/packages) 画廊。

```bash
pnpm install          # 安装工作区开发依赖
pnpm publish          # 发布所有包(pnpm -r publish --access public)
pnpm publish:dry-run  # 打 tarball 检查包内容
```

## 许可证

每个包在自己的清单中声明 MIT 许可证。仓库根目录没有单独的许可证文件。
