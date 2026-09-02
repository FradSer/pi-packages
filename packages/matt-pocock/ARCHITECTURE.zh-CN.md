# pi-matt-pocock 架构说明

`pi-matt-pocock` 将 [mattpocock/skills](https://github.com/mattpocock/skills) 中适合工程协作的内容，适配为 Pi 内部的**持久化工作流编排器**。它不是把每一份上游 `SKILL.md` 原样公开为一个 Pi skill。

术语对照：

- **workflow harness（工作流编排器）**：负责选择、保存、恢复并推进工程流程的扩展。
- **route（路线）**：一个大类工程流程，例如 `hard-bug` 或 `idea-to-ship`。
- **procedure（流程步骤）**：路线内当前正在执行的具体 Markdown 指引，例如 `diagnosing-bugs`、`to-spec` 或 `code-review`。
- **phase（阶段）**：当前流程步骤所处的可读阶段。

## 对用户暴露的入口

包只提供一个管理命令和一个主要编排 tool：

- `/matt-pocock`：打开路线菜单、查看状态、手动切换或结束工作流。
- `matt_pocock_workflow`：模型启动或切换工程工作流时调用。
- `matt_pocock_ask`：仅在工作流激活期间启用，用于需要用户作出的结构化选择。

当前支持五条 route：

| Route | 适用场景 |
| --- | --- |
| `idea-to-ship` | 从需求澄清、规格到任务、实现和评审的完整功能工作 |
| `hard-bug` | 困难、间歇性或回归问题的诊断与修复 |
| `triage` | 将原始请求或 issue 整理为可执行 brief |
| `wayfinding` | 为大型、模糊的计划建立决策与实施路径 |
| `architecture` | 调查并改善代码库架构 |

## 工作流如何运行

```text
复杂工程请求
  → 判断是否需要结构化工作流
  → 选择 route 和当前 procedure
  → matt_pocock_workflow 加载该 procedure
  → 将 route / procedure / phase 写入 Pi session
  → 该步骤完成后切换至下一 procedure
```

调用 `matt_pocock_workflow` 后，扩展会校验 route 和 procedure，读取 `procedures/<procedure>.md`，并将当前 `{ route, procedure, phase }` 写入 Pi 的 custom session entry。会话重启时，扩展从同一 branch 的最后一个有效状态恢复当前步骤，因此不会依赖模型从长对话中猜测进度。

当前 procedure 的完整正文只会在**启动、切换或恢复**这个步骤时按需注入。后续 agent turn 只增加简短的阶段 guidance，例如当前应遵循哪个步骤、下一步明确时应自动推进、以及只有什么情况才应询问用户。它不会在每轮重新注入所有流程正文。

如果任务不属于复杂、多步骤的工程流程，就不应启动该工具；正常处理请求即可。不确定时宁可不进入工作流，也不应猜测一个 route 并加载无关 procedure。

## Q：为何不直接公开一堆 skills？更新是不是更麻烦？

**A：主要收益是控制上下文、避免全局命名冲突，并获得可恢复的流程状态。**

上游的纯 skills 方案会把多份 `SKILL.md` 作为可独立发现的能力。`tdd`、`research`、`implement` 和 `code-review` 之类的通用名称容易与用户已安装的其他 skill collection 冲突；它们也不天然记录“当前任务走到了哪一步”。

本包将 procedure 保留为包内普通 Markdown 资源，不含 `SKILL.md`，因此不会被 Pi 递归发现为全局 skills。编排器只在命中工作流后加载当前 procedure，并持久化流程状态。这样保留上游方法论的内容，同时让多阶段工程工作具有明确的进度、自动切换与重启恢复能力。

更新确实不是简单复制上游文件，但工作集中在一个明确的同步边界：选择需要的上游内容，将 `SKILL.md` 转为 `procedures/*.md`，删除宿主专属 frontmatter 和调用语法，并保留 Pi 的会话、UI、工具启停和工程约束。具体同步规则见 [UPSTREAM.md](UPSTREAM.md)。这是一层有意维护的适配，而不是对上游仓库的镜像。

## Q：只暴露一个 tool，但 schema 仍列出 procedure，真的节省上下文吗？

**A：不能把“只注册一个 tool”误说成 schema 成本为零。**

当前主 tool 的 `route` 固定为五个值；`procedure` 参数会列出该 route 下允许的流程步骤和已知别名。这样模型切换阶段时可受约束地选择有效步骤，扩展也能验证请求，而不是接受一个凭空编造的名称。

因此，schema 仍然有少量 route / procedure 枚举成本。不过它避免了每个独立 skill 各自的发现、描述和完整正文同时进入上下文。更重要的是，体积最大的 procedure 正文按需一次加载；正常后续轮次只保留状态和精简 guidance。

一个更激进的未来设计可以让路由层只返回 procedure 名，再由运行时查表加载正文，并在不确定时返回空结果而不猜测流程。但这会失去 schema 对阶段切换的即时约束，需要单独权衡可靠性与 token 成本。本包当前选择的是受限枚举加按需正文加载。

## 与 `mattpocock/skills` 纯 skills 方案的区别

| 维度 | 上游 `mattpocock/skills` | `pi-matt-pocock` |
| --- | --- | --- |
| 分发形式 | 多份独立 `SKILL.md` | 一个 Pi extension 加包内 procedure Markdown |
| 发现方式 | 每个 skill 都可独立发现 | 只有 `/matt-pocock`、主 workflow tool 和条件启用的问答 tool |
| 通用名称 | 可能与其他集合的 `tdd`、`research`、`code-review` 冲突 | procedure 不注册为全局 skill，因此无同名冲突 |
| 正文加载 | 各 skill 独立装载 | 命中 route 后按需加载当前 procedure |
| 状态 | 通常由模型和对话自行维持 | `route / procedure / phase` 持久化在 Pi session 中 |
| 重启后 | 需要从对话重新理解进度 | 恢复最后一个有效 workflow state 与当前 procedure |
| 推进 | 模型根据 skill 内容决定下一步 | 通过相同的 `matt_pocock_workflow` 显式切换并保存 |
| 更新 | 直接跟随上游 skill 文件 | 选择性同步，并适配 Pi 运行时 |

概括来说，上游仓库是一组可单独使用的方法论；`pi-matt-pocock` 则是一个把这些方法论组织为连续、受状态约束、可恢复工程流程的运行时。
