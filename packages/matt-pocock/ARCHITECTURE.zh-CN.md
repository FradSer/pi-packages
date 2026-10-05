# pi-matt-pocock 架构说明

`pi-matt-pocock` 将 [mattpocock/skills](https://github.com/mattpocock/skills) 中选定的工程方法适配为 Pi 的**目录驱动能力网关**。它不是上游仓库的完整镜像，也不把每份上游 `SKILL.md` 注册为 Pi skill。

上游检查已更新至 `d81f3a1`。新增 `pr`（模型与命令可用）和 `retro`（用户命令）能力；词汇表采用 `GLOSSARY.md`，旧 reference id `CONTEXT-FORMAT` 通过别名继续可恢复。上游移除的 `resolving-merge-conflicts` 保留为本地兼容能力。开发依赖与可执行运行 fixture 都按包内实际解析结果验证 Pi v1.0。

## 核心模型：procedureCatalog manifest

`src/catalog.json` 中的 `procedureCatalog` manifest 是能力与资源关系的单一事实来源，`src/catalog.ts` 提供类型化查询与校验。命令菜单、模型可见能力、工作流入口、route 标题与说明、阶段、别名、依赖、引用披露、合法迁移和完整性检查都从目录派生，而不是分别维护 route/procedure 巨型枚举。

目录中的资源分为四类：

- **workflow（工作流 procedure）**：可位于一个或多个持久化 route 中；部分也可作为 standalone capability 运行。
- **standalone capability（独立能力）**：目录中标记 `standalone` 的 workflow 或 utility，可一次性运行，不创建持久化工作流状态。
- **reference（参考资料）**：只在当前 procedure 或已加载 reference 明确披露后可访问。
- **asset（资产）**：procedure 使用的脚本或模板，不作为公共能力入口。

每条目录记录还声明调用模式：`model`、`user` 或 `internal`。模型基线网关只枚举 `model` 且可独立运行的能力；`/matt-pocock` 菜单可展示全部 standalone capability。内部 reference 与 asset 不会成为顶层菜单项或全局 skill。

## 单一用户入口与渐进式 tool

包只有一个命令入口 `/matt-pocock`。同一菜单同时提供：

- 启动五类持久化工作流：`idea-to-ship`、`hard-bug`、`triage`、`wayfinding`、`architecture`；
- 运行目录中的 standalone capabilities；
- 查看、迁移、完成或取消当前工作流。

模型侧始终保留一个基线网关：

- `matt_pocock_workflow`
  - `mode: workflow`：根据 route 启动目录定义的入口 procedure；
  - `mode: capability`：运行一个模型可达的 standalone capability；
  - `mode: reference`：加载该 standalone capability 已披露的 reference。

工作流成功启动或恢复后，扩展通过 `pi.setActiveTools()` 渐进启用：

- `matt_pocock_active`：迁移 procedure、加载可访问 reference、完成或取消工作流；
- `matt_pocock_ask`：通过 Pi 选择 UI 处理真正由用户拥有的结构化决策。

工作流完成、取消或恢复校验失败后，这两个 active-only tool 会被移除。这样基线 schema 不再列出所有 route 与 procedure 的组合，也不会让无活动状态的会话携带迁移、完成和访谈操作。

## 工作流状态与生命周期

启动 route 时，`src/workflow.ts` 从目录查找唯一入口，并创建如下持久化状态：

```text
version / workItemId / route / procedure / phase / status / loadedReferences / deliveredProcedures
```

- `workItemId` 是每次工作流启动时生成的稳定 UUID，用于区分独立工作项。
- 活动记录的 `status` 为 `active`。
- 结束记录保留同一 `workItemId`，`status` 为 `completed` 或 `cancelled`；取消记录可包含原因。
- 状态通过 `pi.appendEntry` 写入 session branch。Pi v1.0 的 session start、tree navigation 和 context compaction 都以当前分支最新记录为准；记录已结束、损坏或版本不兼容时，不会回退恢复旧活动状态。
- 恢复前会重新验证 route、procedure 与资源 bundle。无效的陈旧状态会被明确记录为 `cancelled`，而不是静默回退到 route 默认入口。

扩展实例独立持有运行状态，避免同一进程中多个会话串扰。工作流启动或恢复时会返回完整的当前 procedure bundle；迁移只交付本次连续上下文中尚未交付的正文。压缩上下文后重置交付集合并静默注入当前完整 bundle。之后每个 agent turn 只追加紧凑 guidance，包含 `workItemId`、当前阶段、合法下一步、可加载 reference 与终止责任，不会把整个目录反复注入 system prompt。

模型可以通过 `matt_pocock_active` 明确完成工作流；完成不再依赖用户进入菜单。用户仍可从同一 `/matt-pocock` 菜单迁移、完成或取消，作为显式控制入口。

### 生命周期提示中的阶段标题

工作流提示使用事件发生时的实际阶段标题，不使用 `hard-bug` 等 route 标识、route 标题，也不生成任务标题。展示复用 `src/workflow.ts` 的 `readablePhaseTitle()` 映射。例如，工作流经过诊断、实现和审查后结束：

```text
[matt pocock] started · Reproducing & Diagnostics
[matt pocock] event · Implementation
[matt pocock] event · Code Review
[matt pocock] event · Code Review completed
```

如果在实现阶段取消，则显示 `[matt pocock] event · Implementation cancelled`。`completed` / `cancelled` 仍表示**整个工作流**结束；前面的标题仅说明结束时所在的阶段，可以是入口阶段，不假设已到达流程末尾。

| Route | 可用阶段标题（不是强制执行顺序） |
| --- | --- |
| `idea-to-ship` | Shaping & Requirements；Research & Feasibility；Prototyping；Specification Design；Task Decomposition；Implementation；Code Review；Handoff & Summary |
| `wayfinding` | Initiative Mapping；Research & Feasibility；Prototyping；Specification Design；Task Decomposition；Implementation；Code Review |
| `triage` | Task Triage；Specification Design；Task Decomposition；Implementation；Code Review |
| `hard-bug` | Reproducing & Diagnostics；Implementation；Code Review |
| `architecture` | Architecture Survey；Architecture Design；Implementation；Code Review |

route、procedure、phase、workItemId 和状态的持久化结构不变，模型 guidance、工具参数与结果 details 仍使用原标识。展开启动提示时仅显示不同于阶段标题的 `route · <Readable Route Title>`，例如 `route · Hard Bug Diagnosis`，标题复用 `readableRouteTitle()`；若两者相同（如 Task Triage 入口），也省略该字段。不再重复 phase id，也不会展示 procedure 正文。

展开仅补充当前提示尚未显示的信息：

- 迁移、完成和参考资料加载不显示重复的 `action` 字段；独立能力和独立参考资料也不把标题再复制为字段。标题完整可见时，这些提示没有展开提示或额外正文。
- 取消提示只在该结果保存的终止快照包含非空白原因时，展开显示一次 `reason · <stored reason>`，不显示 `action · cancel`，也不读取当前工作流的原因。缺失、空字符串或纯空白原因均不会新增详情或展开提示。
- 窄终端中的标题或摘要被截断时，由 Pi-kit 共享渲染器提供展开，并使用 Pi 原生换行恢复完整文本；本包不自行计算宽度。仅供模型使用的正文与 metadata 不会触发展开提示。

`matt-pocock-procedure` 消息渲染器负责这条块状提示。用户从 `/matt-pocock` 启动 route/独立能力、用自由文本触发路由、或在菜单里选 “Start a task” 时，procedure 都通过这条可见消息交付，而不是把正文当 user message 贴出：

```text
[matt pocock] started

fix the login redirect
```

head 单独成行，一个空行分隔，随后是用户自己的任务原文（未提供任务时用可读的阶段标题或能力显示名称）；整块使用 Pi 原生 user-message 底色（`userMessageBg`），逐行保留换行、过长自动换行，且不提供展开。模型侧仍收到完整正文和 `User target/request:` 段落。恢复会话时仅静默注入 guidance（`display: false`），不新增重复的启动行。旧工具结果即使保存了 route 风格的 subject，也根据该事件保存的 phase 和 action 重新渲染，不读取当前工作流的可变状态，无需迁移会话数据。

能力与引用统一使用目录中的可读显示名称；阶段切换菜单使用目标阶段标题，与进入阶段后的状态行一致。命令和持久化数据仍保留原有 id，用户任务原文不改写。

独立能力、参考资料和提问保留各自的展示对象：`started · <capability>`、`started · <capability> · <reference>`、`event · loaded <reference>` 和 `ask · <question>`，不替换成工作流阶段。提问的答案或待定状态保持可见，超时、无 UI 和自定义输入等有效 metadata 仍可展开查看，不重复答案。

从仓库根目录运行 `uv run --no-project packages/matt-pocock/tests/live_smoke.py`，可在真实 Pi CLI 中验证 print 模式、交互终端提示、真实选择超时与 Escape 取消、Ctrl+O 展开、缩至 48 列，以及 `/matt-pocock hard-bug fix the login redirect` 只产生一块 user-message 底色的块状提示。脚本使用临时 HOME 与离线脚本化 provider，不读取用户凭证或调用外部模型。

`tests/runtime_live.py` 从 catalog 派生全部 route、合法转移和独立能力，在真实 Pi agent loop 中运行，并验证持久化重启；`tests/decision_live.py` 通过 PTY 发送实际选择、文本输入与取消按键。运行方式同上。原生进程失败模拟与实际 macOS 对话框验证分别记录。这些验证覆盖 Pi 集成路径，不证明外部模型的决策质量，也不代表每份 procedure 的下游工程任务已执行。

## 协作验证与完成门槛

实现阶段由各执行者运行分配的安全局部检查，由一个集成负责人承担共享验证。验证前先确认 HOME、凭证和测试数据的隔离条件；本地命令不等于无生产访问。集成后记录候选版本或本次改动快照，评审与最终检查必须针对同一候选；纳入未跟踪的任务文件，排除原有脏改动和无关工作。后续修改使受影响的证据失效，只重跑适用检查，不要求每个 Agent 重复全仓验证。

评审仍分别给出 Standards 与 Spec 结论，但小范围改动可由一个全新上下文的 reviewer 完成两个维度；只有规模、专业分工或仓库规则需要时才拆成多个 reviewer。当前对话中已确认的需求与验收场景可作为本地未提交任务的 spec，不必为了评审创建 issue tracker 或提交。

评审 Work 完成表示报告已交付，不等于实现 PASS。独立评审或限定 reviewer 任务返回报告即可结束，包括 REWORK；不擅自修改实现，也不等待问题被修复。Leader 或实现负责人负责按根因合并问题、补齐相邻场景及后续交付。

复核前先保存旧报告，并准备保留的基线、新候选指纹、修复差异、原发现与安全检查范围。Agent Teams 的 reopen 会清除旧 result，但不会更新 description；reopen reason 和 assign 也不会自动传递新的复核说明。仅当原 description 已指向“当前尝试的权威 brief”时，才先更新该 brief，再 reopen/assign，且复核期间保持内容稳定。原描述固定了旧候选或没有此引用时，用完整新描述创建范围受限的后续 Work，并通过 dependsOn 关联已完成评审。它是关联的定向复核，不是新一轮广泛评审；仅范围或风险明显变化才扩大评审。

实现交付需等待所有必需结果返回、阻断问题解决且证据适用于最终候选，才调用 complete；仅剩待返回结果时保持工作流活动并让出当前回合。

这些约束属于指导文本，不是新增调度器或跨扩展的强制完成锁；不改变持久化格式，也不强依赖 Agent Teams。

## 合法迁移

每个 workflow placement 在目录中声明 `allowedNext`。迁移时运行时会：

1. 规范化 procedure id 与已知别名；
2. 验证目标是否位于当前 `{ route, procedure }` 的 `allowedNext`；
3. 验证目标确实属于同一 route；
4. 更新 procedure 与 phase，并清空先前加载的 references；
5. 解析新 bundle 后持久化状态。

不在集合内的迁移会失败并返回允许的候选项。运行时不会把非法目标替换成 route 默认 procedure，也不会用一个覆盖全部路线的 procedure enum 假装迁移有效。

## `requires` 与 `discloses`

目录用两种边表达不同的上下文语义：

- `requires`：执行根 procedure 必须同时加载的依赖。`src/resolver.ts` 递归解析依赖闭包、去重并检测环；这些正文与根 procedure 一起进入 bundle。
- `discloses`：当前正文允许按需访问、但尚未加载的 reference 或辅助能力。网关只返回可用 id；模型需要时再通过 `matt_pocock_active` 或 standalone reference 模式加载。

已加载 reference 也可以继续披露下一层 reference。运行时根据当前 procedure 与 `loadedReferences` 计算可达集合，拒绝目录图之外的任意文件请求。这既保留方法论所需的强依赖，也避免把所有可选资料一次性塞入上下文。

## 稳定来源标识与体积边界

每个解析后的正文都包在独立来源块中：

```text
<procedure-source id="<catalog-id>" source="procedure/<catalog-id>">
...
</procedure-source>
```

`source:procedure/<id>` 不依赖本机安装路径，可供模型、日志与检查器稳定指代来源。根 procedure 与全部 `requires` 内容拼接后按 UTF-8 字节数计算；单个 bundle 上限为 64 KiB。超过上限会直接失败，不会截断正文或静默遗漏依赖。

## 为什么没有子 `SKILL.md`

上游以多份嵌套 `SKILL.md` 分发能力。Pi 会递归发现 skill root 下的这些文件，因此 `tdd`、`research`、`implement`、`code-review` 等通用名字可能与用户安装的其他集合冲突，也不天然表达工作项状态和合法阶段迁移。

本包把选定内容保存为 `procedures/*.md`、reference Markdown 或 asset，并由 extension 目录解析。包内不含子 `SKILL.md`：

- 名称不会进入全局 skill 命名空间；
- workflow 与 standalone capability 共用同一个目录和网关；
- reference 只能沿 `discloses` 边访问；
- 持久化状态、渐进 tool 和终止语义由 Pi extension 统一管理。

因此本包也不需要第二个公共 skill surface，或为每条工作流增加单独命令。

## 上游选择与同步校验

[`upstream-selection.json`](upstream-selection.json) 是机器可读的上游选择记录。它把最新检查版本中的每个上游 skill 标为：

- `selected`：映射到本地 catalog id、普通 Markdown resource 与上游调用模式；
- `excluded`：保留明确排除理由，包括依赖 Claude Code hook 或后台 agent 命令的宿主专属能力。

[`UPSTREAM.md`](UPSTREAM.md) 记录比较 commit、tag、tag commit、最新检查 commit 以及适配规则。[`scripts/check-upstream-sync.mjs`](scripts/check-upstream-sync.mjs) 是同步 checker：不带参数时验证本地元数据和资源；传入已克隆的上游路径时，还会检查完整 skill inventory、调用模式和正文差异。checker 不会自行 clone 或 fetch。

贡献者应运行：

```bash
node packages/matt-pocock/scripts/check-upstream-sync.mjs
python3 -m pytest packages/matt-pocock/tests/ -q
pnpm typecheck
pnpm --dir packages/matt-pocock pack --dry-run
```

需要核对上游 checkout 时再运行：

```bash
node packages/matt-pocock/scripts/check-upstream-sync.mjs --upstream /path/to/mattpocock-skills
```

实际 Pi v1.0 检查见 [`README.md`](README.md) 中的运行命令。目录矩阵从 manifest 派生所有 route、合法迁移和独立能力，通过真实 Pi agent loop 执行，并检查工具启停、持久化、重启、原生树切换与上下文压缩。压缩检查通过 `session_before_compact` 提供固定摘要；Pi 的压缩事件与会话写入仍实际执行，下一次模型上下文需包含恢复后的完整 procedure 来源。

决策、活动菜单和 AbortSignal 检查运行在真实 Pi 终端中。测试使用临时 HOME 和本地固定响应 provider，不读取用户认证，也不验证外部模型的决策质量或 procedure 指导的下游项目任务。故意失败的模拟原生子进程只证明 TUI fallback；独立 macOS smoke 使用实际 `osascript` 验证超时、中止和进程退出，不代替原生按钮选择或物理界面的人工验收。

真实模型检查单独使用 `tests/real_model_live.py`，用例清单位于 `tests/real-model-cases.json`，覆盖 21 个独立能力、5 个工作流入口、自然语言路由和“测试全绿但含需求外行为”的审查回归，共 28 项。`--list` 只列清单；显式 `--case` 或 `--all` 使用当前 Pi provider/model，thinking 为 off，并在每项独立的临时项目中加载生产扩展。认证副本只用于 provider 请求，项目文件工具无法读取；固定验收在 macOS sandbox 中执行，模型不能修改验收文件。产物检查、需要人回答的问题、失败和未运行项分别记录，不以进程正常退出作为成功证据。有待回答问题时，总体状态保持 `awaiting_user`，预期的 pending 验收仍以退出码 0 表示。外部 provider 不可用时停止，不自动更换模型。

## 与上游纯 skills方案的差异

| 维度 | `mattpocock/skills` | `pi-matt-pocock` |
| --- | --- | --- |
| 分发 | 多份独立 `SKILL.md` | 一个 Pi extension 与普通内部资源 |
| 入口 | 每个 skill 独立发现 | 一个 `/matt-pocock` 菜单与目录驱动 gateway |
| 能力组织 | 文件与 skill 名称 | workflow、standalone capability、reference、asset 分类 |
| 上下文 | 每个 skill 独立加载 | `requires` 强依赖随根加载，`discloses` reference 按需加载 |
| 状态 | 主要由对话维持 | `workItemId` 与 active/completed/cancelled 记录持久化 |
| 推进 | 由方法正文解释 | `allowedNext` 在运行时强制执行 |
| 公共命名 | 通用 skill 名可能冲突 | 无子 `SKILL.md`，通用 procedure 名不全局注册 |
| 同步 | 直接跟随上游文件 | selection metadata 与 checker 约束选择性适配 |

## 结构化决策与 macOS 原生弹窗配置

工作流进行决策访谈（如 `grilling`、`domain-modeling`）时，通过 `matt_pocock_ask` 工具向用户发起选项选择或自定义输入。默认情况下，使用 Pi 终端内置的 TUI 界面（`ctx.ui.select` / `ctx.ui.input`）。

用户可在 Pi 的 agent 目录下的 `matt-pocock.json` 中配置是否在本地 macOS 环境下启用系统原生弹窗（默认 `~/.pi/agent/matt-pocock.json`；若设置了 `PI_CODING_AGENT_DIR`，则使用该目录）：

```json
{
  "useNativeDialog": true
}
```

- **默认值**：`false`（默认使用终端内置交互，用户不配置或文件不存在时不启用）。
- **严格环境守卫**：只有在 macOS 本地图形会话中才会唤起系统弹窗；非 macOS 平台、远程 SSH 会话（`SSH_CONNECTION` / `SSH_CLIENT` / `SSH_TTY`）或 CI/自动化环境下会自动优雅降级为终端内置 TUI。
- **智能动态上下文**：弹窗标题由 AI 提问时指定或自动从当前工作流 Route/Phase 上下文关联派生；按钮文案自动根据提示语语言智能适应，配置文件仅保留 `useNativeDialog` 单一开关，保持极简。
- **原生交互体验**：
  1. **列表单选**：调用系统原生 `choose from list` 弹窗展示选项，支持上下键移动、回车选择；
  2. **自定义输入**：当用户选择“输入自定义回答...”时，自动唤起原生文本输入窗口（`display dialog` 带输入框），供用户直接打字；
  3. **推荐超时自动采纳**：仅实际达到超时时间后采纳推荐选项；推荐必须属于候选项。取消、工具中断或流程切换均保持待定。需要授权的操作应省略推荐，不得以超时视为授权。

原生对话框仅在配置 `useNativeDialog: true`（布尔值）时启用。取消信号会关闭 TUI 或终止并回收 osascript 子进程；进程启动、退出或解析失败会回退到 TUI。Catalog 在注册工具前校验别名冲突、重复路由位置和 requires 环；加载 reference 前校验累计上下文的 64 KiB 限额，失败不写入部分状态。独立能力在内存中保存当前披露链，可继续加载 reference 披露的下级资料，不创建持久流程状态；重启能力或跨会话上下文时清空。

开发者完整任务另见 `tests/developer-journey-cases.json`：折扣需求到审查交接、异步缓存故障修复、配置解析的设计/清理/审查/交接，使用真实模型连续多轮调用。运行 `tests/real_model_live.py --cases packages/matt-pocock/tests/developer-journey-cases.json --all --deadline 420 --output /tmp/matt-developer-journeys.json`。独立验收验证公共行为；审查中的因果解释和清理结论另需阅读实际产物验证，不能把测试通过等同于报告正确。

完整任务以实际进入指定阶段及单一工作项身份为验收条件，跨轮次等待 `agent_settled` 后继续；缓存测试覆盖失败前成功缓存和独立的加载中键。这三个任务显式设置最多 80 次工具调用，普通矩阵默认仍为 40 次，预算耗尽后后续轮次也不能绕过。
