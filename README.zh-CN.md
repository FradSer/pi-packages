# Frad 的 Pi Packages ![](https://img.shields.io/badge/packages-8-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

[English](README.md) | **Simplified Chinese**

面向 Pi 的原生包，用于复用 Agent skills、extensions 和项目工作流。

## 调用方式

所有 skill 都使用 Pi 的 `/skill:<name>` 命令调用。参数会追加在 skill 内容之后；Pi 不会展开 `$ARGUMENTS`，也不会执行 skill Markdown 中的 shell 注入。

## 包列表

### [`code-context`](code-context/)

通过 DeepWiki、Context7、Exa、直接 git clone 和网页抓取获取代码上下文。MCP 方法是可选的；没有配置时仍可使用 git clone 和 HTTP 抓取。

**Skills：** `code-context`、`get-context`

**安装：**
```bash
pi install /Users/FradSer/Developer/FradSer/pi-packages/code-context
```

---

### [`git`](git/)

自动处理 GitFlow 的 feature、hotfix 和 release 分支生命周期，包括测试、changelog 更新、tag、release 和清理。

**Skills：** `start-feature`、`finish-feature`、`start-hotfix`、`finish-hotfix`、`start-release`、`finish-release`、`commit`、`commit-and-push`

**安装：**
```bash
pi install /Users/FradSer/Developer/FradSer/pi-packages/git
```

---

### [`git-agent`](git-agent/)

提供 AI 驱动的原子提交、共同变更分析、工作区初始化，以及拦截原始 Git 提交操作的 pre-tool 防护。

**Skills：** `commit`、`commit-and-push`、`related`、`init`

**安装：**
```bash
pi install /Users/FradSer/Developer/FradSer/pi-packages/git-agent
```

---

### [`github`](github/)

处理 GitHub issue 和 pull request，包含以 TDD 为导向的质量门禁、验证，以及持续监控 CI 和 reviewer 评论的工作流。

**Skills：** `github-create-issues`、`github-create-pr`、`resolve-issues`、`review-pr`

**要求：** 必须安装并登录 GitHub CLI（`gh`），仓库还必须配置 GitHub remote。

**安装：**
```bash
pi install /Users/FradSer/Developer/FradSer/pi-packages/github
```

---

### [`lark`](lark/)

提供飞书/Lark CLI skills，覆盖文档、表格、消息、日历、审批、云盘、知识库、通讯录、邮件、任务、会议及相关服务。

**Skills：** `lark` router，以及镜像的 Lark 子 skills

**安装：**
```bash
pi install /Users/FradSer/Developer/FradSer/pi-packages/lark
```

---

### [`mattpocock`](mattpocock/)

从 Matt Pocock skills 改编的 BDD 优先工程与生产力 skills，涵盖 TDD、实现、调试、架构、研究、代码审查、计划、交接、教学和 skill 编写。

**安装：**
```bash
pi install /Users/FradSer/Developer/FradSer/pi-packages/mattpocock
```

---

### [`memory`](memory/)

维护 `.memory/` 项目记忆，并提供手动 consolidation，包含聚类、陈旧性检查、基于当前代码的事实验证和隐私校验。

**Skills：** `consolidate`

**安装：**
```bash
pi install /Users/FradSer/Developer/FradSer/pi-packages/memory
```

---

### [`utils`](utils/)

同步项目 README，并按照 Keep a Changelog 1.1.0 格式创建或更新 changelog。

**Skills：** `update-readme`、`update-changelog`

**安装：**
```bash
pi install /Users/FradSer/Developer/FradSer/pi-packages/utils
```

## 注意事项

`git` 和 `git-agent` 都提供 `commit` 与 `commit-and-push`。如果同时启用两个包，skill 的生效版本取决于安装顺序。

## SDK Harness

`examples/sdk-session.ts` 展示了如何以编程方式使用 `createAgentSession()`，加载包的 extensions 并检查已发现的 skills。这些包仍然是可安装的 skill 和 extension 集合，不是内嵌应用。

```bash
npx tsx examples/sdk-session.ts
# optional live model turn:
PI_SDK_LIVE=1 npx tsx examples/sdk-session.ts
```

## 添加包

1. 在仓库根目录下创建包目录。
2. 添加包含 `pi-package` 关键词和 `pi` 资源清单的 `package.json`。
3. 将 skills、extensions、prompts 或 themes 放到 `package.json` 声明的路径下。
4. 使用 `pi install /absolute/path/to/package` 安装本地包并运行测试。
5. 手动运行 `/skill:update-readme`，同步两个 README。

## 许可证

当前每个包都在自己的 manifest 中声明 MIT 许可证。仓库根目录没有单独的 license 文件。
