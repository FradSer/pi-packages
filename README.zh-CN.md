# Frad 的 Pi Packages ![](https://img.shields.io/badge/packages-15-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

[English](README.md) | **简体中文**

面向 Pi 的原生包，用于复用 skills、extensions 和工作流命令。

## 包列表

### [`@fradser/pi-agent-teams`](packages/agent-teams/)

通过简洁的 `agent` 委派和共享 `agent_event` 通信进行协作。每次新工作启动独立会话，默认使用全新上下文，也可用 `fork: true` 继承 Leader 上下文；最终回答自动回传，`work` 定向已有执行。仍支持常驻团队、共享任务和点对点消息。

省略 `definition.tools` 或传入 `[]` 只授权协调工具，不默认提供文件或 shell 能力；委派、启动和检查结果会显示实际工具授权。执行任务需明确选择最小工具集（`read`、`bash`、`edit`、`write`、`grep`、`find`、`ls`）。无法执行时，Worker 必须用 `work` 的 `submit` 动作明确提交 `outcome: "failed"`，不能只在最终回答里描述阻塞。普通最终回答是成功候选；没有验证门的完成并不表示独立验证通过。Leader 应委派具体的真实验收标准，必要时设置验证门；信息报告无需重复确认，除非决策或行动发生变化。

`agent start` 创建未分配的常驻会话，不伪造 Work ID，也不运行无任务的初始模型轮次；公开调用会等待原生就绪确认，返回后可立即向该精确会话分配任务，无需调用方轮询。后续任务通知和自主认领仍保留。恢复时先明确释放原 Work，确认执行权限真正释放后再分配同一 Work，不通过重复委派制造竞争任务。

[调度指导](packages/agent-teams/README.md#coordination-and-delivery) 明确单一集成验证负责人，将评审证据绑定到候选版本，并要求阻断评审返回、问题解决后再交付实现。纯评审任务返回报告即结束，定向复核需显式交接更新后的候选 brief。这是 Agent 指导，不是新增调度器或运行时完成锁。

捆绑的 [subagent 执行层](packages/subagents/README.md#intent-tools) 在启动时确认输入接收，答案异步回传；所有子进程交付后都进入 IDLE，可继续 `send`，直到 `stop` 或父 Pi 关闭。用户编写的磁盘 `agent.md` 是唯一持久身份判据，工具不能创建它，也没有持久性、Memory 或 worktree 开关。持久身份的数据统一存于自己的 home；scratch 是普通目录，不是项目 checkout，也不提供 Git 隔离。诊断或继续输入须完整复制带 `session:` 前缀的句柄；只读 `inspect` 可以读取 roster 中仍保留的 live 或 stopped 记录，控制操作仍仅允许存活的精确实例，旧句柄不会转向替代进程。工具拒绝错用字段，管理查询分页且整体限长，codemode 接收结构化回执；取消已派发调用的等待不会结束对应子进程。输入框上方活动显示仍由 pi-kit 统一负责且不重复团队行。独立子进程的空白、失败或截断输出会回传带诊断的 unanswered 通知，不再表现为空白评审结论。

**子代理工具：** `agent_start`、`agent_input`、`agent_stop`、`agent_inspect`、`agent_list`。
旧分支保留 `agent`。新接口明确区分持久身份、显示名称，以及 next／steer 输入。
队列限制和兼容方式见[意图接口](packages/subagents/README.md#intent-tools)。

TUI 操作行显示子代理名称和任务摘要，精确的会话与输入标识在展开后显示。独立子代理返回结果后仍在输入框上方显示静态的 `Idle` 行，明确表示可继续接收输入，直到进程关闭。

独立子进程在启动时显式获授 `agent_message` 后，可以向父会话发送中间进度消息。消息携带精确的子会话和当前输入标识，与最终答案分开显示，发送后子进程继续工作。临时代理默认不启用这项能力；持久代理的磁盘工具授权上限也须包含它。

持久子代理的历史按父 Pi 会话和项目隔离。重新打开同一父会话可恢复自己的历史；不同父会话共享该身份的 Memory 和 scratch，各自保留独立对话。原有项目历史保留原位，不自动导入新的父会话分区。

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

通过独立的、受研究提示词约束的 Pi 子进程（提供 read、bash、grep、find 工具）检索代码仓库、库与技术问题；不修改工作区的边界来自研究提示词，而非操作系统沙箱。自然语言调研请求会自动调用工具；开始时完整显示请求文本，超宽自动换行，不加省略号，结果仍保持紧凑且可展开。

**工具：** `context_get`

**安装：**

```bash
pi install npm:@fradser/pi-context
```

### [`pi-continual-learning`](packages/continual-learning/)

学习 worker 的读取范围和事务回滚所有权现在由代码限制。旧作用域首次访问时自动绑定 canonical cwd，后续碰撞被拒绝；Memory 元数据以不可信参考上下文提供。升级说明见包内 README。

从完成的任务证据中学习：Memory 积累可复用知识，在生成前注入相关性索引，需要时读取全文；Harness 将可执行的约束交给运行检查，包括 Bash 确认和阻止，skill/text 规则则提供有范围的提示。规划模型提出方案，父进程验证证据、隐私、规则正反样例和所有权后应用。也可通过 `/consolidate` 显式整理。存量 `policies`/`skillPrompts` 通过只读兼容保留原有保护，包括已有 output/artifact 检查。

**命令：** `/memory` 打开 Browse memories、Learning settings 和 Recent learning；`/memory <request>` 记录明确的 Memory 请求；`/consolidate` 学习当前任务；`/consolidate full` 执行完整维护；`/harness` 打开规则面板；`/harness <request>` 默认在项目共享配置中编写规则。

Memory、Harness 和 AGENTS.md 默认仍自动应用通过验证的变更。即使关闭自动学习，也可以显式执行 `/memory` 请求；请求由父进程验证，若内容不够持久或不安全，也可以不产生写入。各阶段策略位于 Memory 面板的 Advanced 区域，历史记录内提供 Undo。旧版 `/memory model`、`/memory status`、`/memory policy`、`/memory history`、`/memory undo`、`/memory evaluate`、`/consolidate backfill` 及 Harness 范围别名仍兼容。

学习在异步处理前冻结任务，关闭会话后停止。学习设置损坏时关闭自动学习并报告原因；`/memory status` 查看实际策略、存储、学习状态和队列诊断。跳过的任务只保存私有、按项目隔离的引用，`/consolidate backfill` 查看其状态，不回放历史或调用模型。关闭自动学习后，已有知识仍可读取。

在用户级 `continual-learning.json` 中配置 `jev`，或提供 `TYPESAFE_API_KEY` 环境变量，即可启用可选的 Jev 判断：选择学习方向并审查已通过代码校验的候选；证据、隐私、写入权限和 Harness 执行仍由父进程控制。不确定或不可用时沿用现有选择器或保存提案，不新增命令。详见[配置与评估说明](packages/continual-learning/README.md#optional-jev-judgments)。 [改善验收报告](packages/continual-learning/tests/jev-improvement-evaluation.md)分别记录真实中英文判断、插件实际效果和剩余误拦，不把模拟测试算作效果提升。 [严格全流程审计](packages/continual-learning/tests/jev-workflow-strict-evaluation.md)要求真实配对效果提升；此前四场公开样本的真实同版本对照为 36/50 → 50/50 效果，十四项改善、零退步；费用增加，不能推广为所有项目都更好。 [扩大的中英文与 Docker 评估](packages/continual-learning/tests/jev-expanded-evaluation.md)保留新的真实项目失败和修复；短候选的安全性改善不能证明大型仓库轨迹的自动学习产出提高。 [最新冻结复测](packages/continual-learning/tests/jev-cited-followup-evaluation.md)保留失败轮次与独立 Git 选项探针：误拦减少仍未证明漏拦或完整流程改善。完整候选停止信号现在帮助已有的有界修复，不授予部分写入权限。

完整维护也会从空 Memory 中提取新知识。当前会话没有有效证据时，可冻结同一项目最近的一份有界会话，并在回执中记录来源摘要；没有证据也没有已有 Memory 时，零模型调用，报告 `no learning input`。

Harness 编写与自动学习默认写入项目 `.pi/harness.json`；明确请求个人配置时使用 `.pi/harness.local.json`（`/harness --local`）。用户层包括 `~/.pi/agent/harness.json` 和按项目隔离的 `~/.pi/agent/harness/<scopeKey>.json`，项目层优先。Skill 指导需要已注册的 skill 及其展开后的调用；文件保存成功不等于触发验证通过，更不代表全局语义强制执行。

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

提供持久化 Pi v1.1.0 工作流 harness，覆盖 BDD、TDD、实现、评审、调试、架构、调研、规划、教学、skill 编写、PR 正文与会话复盘。

**工具：** `matt_pocock_workflow`

**命令：** `/matt-pocock`

**安装：**

```bash
pi install npm:pi-matt-pocock
```

### [`@fradser/pi-monitor`](packages/monitor/)

按明确的结果契约运行输出繁杂的有限命令，返回一条结构化终态结果。有限工作流建议使用 `completion="exit"`，最终验证后等待退出码为零，并校验捕获的 JSON；默认匹配模式在首次终态匹配时停止进程组。Pi v1.1.0 中仅含 monitor 的界面工具批次异步唤醒；混合批次、codemode 和无界面调用直接返回终态。输出背压、大小限制和相同捕获值的引用去重控制上下文开销，`/monitor` 提供可滚动的诊断。

可选 `compact=true` 成功回复保留必要数据，通过原生调用关联省去重复元数据。设计对照实验中，八任务 codemode 批量执行保留完整 JSON，比八次独立 bash 调用降低 61.2–76.3% 的累计输入估算；同样任务合并成一次 bash 则更便宜。按任务需要选择监控契约。方案对比、载荷校验、调度及超时差异、包测试结果见[包 README](packages/monitor/README.md#design-alternatives-and-adopted-optimization)。 [提示词注入](packages/monitor/README.md#injected-execution-policy)现已每轮检查当前启用工具：codemode 是可选能力，bash 可用时才推荐分组，否则使用直接 monitor 调用；文档列出各能力组合的提示词成本。

[TUI 审视](packages/monitor/README.md#tui-rendering-review)补上终态配色、状态前置、自适应运行列表、值预览与完整值视图、帮助和控制台实时刷新，不产生模型消息；原生终端验证覆盖四种尺寸。[启动展开](packages/monitor/README.md#startup-presentation-and-model-boundary)沿用统一 Pi 样式，优先显示有效配置，并保留模型启动回执。

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

### [`@fradser/pi-tasks`](packages/tasks/)

持久化工作清单，仅使用 pending、in_progress、blocked、completed 四种状态。替换以历史关系保留。四个任务工具默认完整换行显示结果，列表提供明确分页。自动续跑需要新有效工作和可执行任务；额度耗尽等待用户输入。

[全部 TUI 场景和触发条件](packages/tasks/TUI.zh-CN.md)。

```bash
pi install npm:@fradser/pi-tasks
```

### [`@fradser/pi-goal`](packages/goal/)

会话级目标运行时：三个工具、授权续跑、显式无工具完成检查。TUI 正文完整显示，底部保留 Codex 风格的执行时长；目标结束后释放，不归档。

**唯一命令：** `/goal <目标和验收条件>`；裸 `/goal` 查看当前线程目标。使用 `/goal pause`、`/goal resume`、`/goal clear` 管理目标。

[完整 TUI 文案与触发条件](packages/goal/TUI.zh-CN.md) 列出所有结果行、状态、通知和转换路径。

**安装：**

```bash
pi install npm:@fradser/pi-goal
```

### [`@fradser/pi-plan-mode`](packages/plan-mode/)

通过 pi-kit 启动最小配置的只读 Pi 子代理生成计划，再通过原生 TUI 选择在当前或新会话中执行。

**命令：** `/plan <prompt>`、`/plan`、`/plan start`、`/plan exit`、`/plan model [provider/model]`、`/plan review`、`/plan status`

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

提供 `/effort`、`/continue`、`/sessions`、`/init`、内部私有实时会话控制，以及安全的 Git worktree 隔离。需要 Pi ≥0.85.1。进入 worktree 前结束旧工具批次，切换后在新 cwd 继续编辑，并阻止 `edit`／`write` 使用指向其他 worktree 的旧路径。

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

工作区开发需要 Node.js 22 分支的 22.22.3 及以上版本，或 Node.js 24.8 及以上版本，与官方 e2e 运行时要求一致。

```bash
pnpm install
pnpm test
pnpm typecheck
pnpm typecheck:e2e
pnpm test:e2e
pnpm pack:check
# 或一次运行全部检查
pnpm check
```

每个包将行为场景放在 `features/`，测试放在 `tests/`。

### BDD → TDD → E2E

先用 Given/When/Then 定义可观察的行为，再复现行为失败（RED），通过小范围失败测试推动最小实现变为 GREEN，验证完整运行链路，最后在相关检查保持绿色的前提下重构。`.feature` 文件表达验收标准，已有 Python／TypeScript 测试负责执行；不自动转换 Gherkin。TDD 是开发循环，不要求将所有进程或扩展集成测试改写成纯单元测试。

E2E 失败后，先保留失败报告和 trace，再对照 BDD 需求定位。若为产品缺陷，补充或复用能复现问题的 RED 回归，修复产品代码，重跑受影响测试及真实 Pi E2E，再用完整默认套件确认运行验收。若为断言错误，依据未变的需求修测试；若为基础设施故障，修环境后重跑；预期失败的负例无需修产品代码。不能弱化断言或改写需求来制造通过，原失败与修复证据一起保留。只有要求的行为变化时才更新 BDD 合同。本地修复遵循已有授权；E2E 结果不授权生产写入或付费调用。

新增 monitor 修复时，在实现前记录失败测试及具体断言。依赖缺失或进程启动错误是验证阻碍，不能算行为 RED。下表对应已有测试，不声称本次文档修改重新制造了历史 RED。

| BDD 场景或条款 | 已有可执行检查 | 覆盖范围与证据 |
| --- | --- | --- |
| [A real Pi session receives the result of its monitored child command](features/tester-army-e2e.feature) | [monitor-native.e2e.ts](tests/official-e2e/monitor-native.e2e.ts)：`real Pi delivers its monitored child result to the original session` | 完整无界面验收：一次 `monitor_start` 和终态、调用身份一致、成功且匹配 `DONE_NATIVE`、下一请求晚于终态、一次最终回答、没有重复自定义消息。 |
| 同一场景：返回的 provider 上下文排除私有进度 | 同一 E2E 检查，复用 [native-fixture.ts](packages/monitor/tests/native-fixture.ts) | 真实 Pi 执行先输出 `PRIVATE_PROGRESS`、再输出 `DONE_NATIVE` 的子进程；返回工具内容必须包含终态、排除进度。原生 `events.jsonl` 和 `pi.jsonl` 保留证据链。 |
| [A mixed tool batch waits for the terminal contract](packages/monitor/features/delivery-boundaries.feature) | [test_monitor_delivery_boundaries.py](packages/monitor/tests/test_monitor_delivery_boundaries.py)：`test_mixed_batch_waits_before_the_next_provider_request` | 扩展／agent-loop 小范围回归：第二次请求已收到终态，且没有重复消息。它使用 UI-host harness，与无界面 E2E 是不同路径。 |
| [Complete records establish the success candidate](packages/monitor/features/exit-completion.feature) | [test_monitor_exit_completion.py](packages/monitor/tests/test_monitor_exit_completion.py)：`test_exit_waits_for_complete_records_and_keeps_first_success` | 真实进程匹配回归：验证 `completion: exit` 下完整记录／EOF 与首个成功结果。原生 match 模式示例不覆盖此 exit 契约；另有 monitor-workflows 用例验证 exit 模式交付。 |
| 同一 exit-completion feature：终态仅通知一次的回归 | 同一测试文件：`test_exit_first_json_candidate_is_not_replaced_and_delivers_once` | 检查首个 JSON 候选、有效性及每个 monitor 仅一个终态事件；支持 manager 正确性，不能单独证明真实 Pi 中的交付。 |

在仓库根目录运行示例，不调用付费模型：

```bash
uv run --no-project --with pytest python -m pytest packages/monitor/tests/test_monitor_delivery_boundaries.py packages/monitor/tests/test_monitor_exit_completion.py -q
pnpm typecheck:e2e
pnpm test:e2e --grep 'real Pi delivers its monitored child result to the original session'
pnpm test:e2e
```

实现变更还须运行受影响包测试及现有类型／打包检查。`pnpm check` 已在打包校验前包含 E2E 类型检查和默认零付费套件；单独的 E2E CI 任务还负责保留报告。检查 `.e2e/report.json`、`junit.xml`、`summary.md`、失败用例的 `results/*/trace.md`，以及 `.e2e/native-monitor-*/events.jsonl`、`pi.jsonl`、`stderr.txt`。需要保留连续运行报告时，使用 `--output .artifacts/tester-army-integration/<unique-run>`；普通运行会覆盖对应输出目录中的报告和 results。原生 monitor 证据另存于独立唯一目录。保留原失败，不择优保留重跑成功结果。

此示例只证明确定性进程内 provider 下的无界面 monitor 交付；TUI 输入／缩放、RPC 对话、其他并发／exit 契约和真实模型质量须分别验证。AI 证据分类不能代替精确断言，也不构成代码质量收益。

日常项目验收直接运行 `pnpm check`，无需付费模型。[monitor-workflows.e2e.ts](tests/official-e2e/monitor-workflows.e2e.ts) 通过真实 Pi／monitor 执行项目实际类型检查，并验证隔离的错误 TypeScript 文件返回可定位的编译诊断；另外四例防止后续非零退出、无效 JSON、早期成功候选后的超时，以及缺失完成标记被误报为成功。全部复用现有 [transport fixture](packages/monitor/tests/transport-matrix-fixture.ts)，在 `.e2e/native-monitor-*` 保留输入及原生输出。这些验证实际运行合同；错误源码是测试输入，不是新发现的项目缺陷，故意失败的补丁也只证明回归敏感性。原 AI 实验已停用，失败和费用仍作为历史证据保留。

### 选择验收方式

BDD 定义可观察行为，TDD 通过 RED → GREEN → REFACTOR 推动最小实现，E2E 验证完整运行路径。三者共享合同，覆盖不同故障风险；复用包测试和 fixture，不必在每层重复全部断言。

monitor 的确定性结果直接通过已有真实 Pi 流程和精确 `expect` 断言验收，对同一份 JSON 再做 `agent.assert` 没有新增覆盖。当前编译／终态用例的命令、场景和完成合同都是固定的，也无需 `agent.act`。现阶段没有可提供独立覆盖的 monitor AI 场景，因此停用原 AI 执行／判断和证据分类入口。

仅当自主操作能增加固定交互难以合理覆盖的行为时引入 `agent.act`；仅当某项明确的语义或视觉要求难以用精确断言表达时引入 `agent.assert`，先说明判断依据和覆盖缺口。确定性数值仍用精确断言，不要求每例都串联 `agent.act → agent.assert → expect`。未来新增付费用例须获得明确授权并预留失败及重试费用。

### 接入场景完整对应表

下表覆盖 [tester-army-e2e.feature](features/tester-army-e2e.feature) 的每个场景。Feature 标签只用于说明，不会在官方 runner 中筛选 TypeScript 测试。

| 场景 | 可执行检查或验证方式 | 状态／边界 |
| --- | --- | --- |
| Default CI execution retains actionable reports without paid calls | [e2e.config.ts](e2e.config.ts)、[e2e.yml](.github/workflows/e2e.yml)，检查 runner 报告及远程 workflow 上传 | 人工 CI 验收。本地 CI 模式可证明报告生成；远程 artifact 上传仍待 workflow 实际运行验证。 |
| Valid isolated package settings pass the real CLI audit | [installation.e2e.ts](tests/official-e2e/installation.e2e.ts)：`complete workspace settings pass the installation CLI` | 默认零付费 E2E。 |
| A dead source is reported as a failing audit | 同一文件：`dead package sources fail with a located diagnostic` | 默认零付费 E2E；预期安装失败属于通过的负例。 |
| A real Pi session receives the result of its monitored child command | [monitor-native.e2e.ts](tests/official-e2e/monitor-native.e2e.ts)：`real Pi delivers its monitored child result to the original session` | 默认零付费无界面 match 模式验收。 |
| A real Pi startup failure retains subprocess diagnostics | 同一文件：`real Pi startup failures retain subprocess diagnostics` | 默认零付费回归；Pi 拒绝 provider 时仍保留 stdout/stderr，随后移除临时设置。这证明诊断保留，不代表 monitor 执行成功。 |
| Real Pi confirms finite verification outcomes through monitor | [monitor-workflows.e2e.ts](tests/official-e2e/monitor-workflows.e2e.ts): `real Pi confirms a successful project typecheck`; `real Pi returns located compiler errors for a failed verification` | 默认零付费真实编译流程；校验成功 JSON 和可定位 TS2322 失败。 |
| Real Pi does not mistake intermediate output for completed verification | Same file: `real Pi rejects a success sentinel followed by a nonzero exit`; `real Pi rejects malformed JSON completion`; `real Pi reports a deadline after a success candidate`; `real Pi rejects a zero exit without its required result` | 默认零付费 exit 模式终态与返回内容检查；不覆盖 TUI／RPC。 |
| Deterministic monitor acceptance has no model entry point | [test_official_e2e.py](tests/test_official_e2e.py)：`test_deterministic_monitor_acceptance_has_no_model_entry_point`、`test_developer_docs_have_one_complete_integration_section` | 零付费根 pytest，核验当前脚本／配置／依赖及场景对应。 |

官方 [tester.army/e2e](https://e2e.tester.army/docs) 命令行检查使用 `pnpm test:e2e` 运行，使用 `pnpm typecheck:e2e` 检查类型。固定版本的 runner 采用无引擎目标，以临时设置和精确断言验证现有安装审计命令；未配置模型、API 密钥、浏览器、自定义引擎或适配层。修改这些测试前阅读 @.agents/skills/e2e/SKILL.md。报告位于 Git 忽略的 `.e2e/`；使用 `pnpm test:e2e --reporter list,junit,markdown --trace on` 保留 trace 页面。用例还通过现有离线 monitor fixture 启动工作区真实 Pi CLI，验证 monitor_start 执行真实子进程、终态仅一次回到原会话，以及进度不进入返回的 provider 上下文。每次使用临时 HOME／agent 设置，原生 JSONL 证据保存在 `.e2e/native-monitor-*`。fixture provider 在进程内确定性执行；这证明无界面 monitor 交付，不代表 TUI／RPC、远程模型行为或一般 AI 测试收益；增加模型步骤需另行授权。

@e2e.config.ts 默认生成 JSON、JUnit 和 Markdown 报告，并保留失败尝试的 trace。稳定项目标识用于确定性 CLI 检查；单 worker、零自动重试用于隔离和复现，官方缓存默认行为保持不变。@.github/workflows/e2e.yml 在 PR、main 推送和手动触发时使用 Node 26、冻结 lockfile，运行类型检查和零付费套件。任务仅有读取权限，无模型凭证；失败时也保留免费报告及原生证据七天。配置依据官方[配置参考](https://e2e.tester.army/docs/reference/config)与 [CI 指引](https://e2e.tester.army/docs/ci/github-actions)。

原 AI 实验见[monitor E2E AI 历史记录](docs/history/monitor-e2e-ai.md)。原源码、冻结协议、失败报告、输入及费用账本保留在本地忽略目录，不参与 pytest、TypeScript 或官方 runner 的当前收集。停用重复测试不会把历史失败改成通过，也不释放原保守费用预留；不宣称历史质量收益。

`pnpm check` 会运行包和根目录 pytest、扩展和 E2E 类型检查、默认零付费官方 CLI E2E 套件，以及无需访问 registry 的打包清单检查。使用 `pnpm check:install` 可以单独审计当前 Pi 设置文件中的已安装包。

测试需要 Python 3、`pytest` 以及供子进程测试使用的 Bun 1.4.1。CI 工作流会在运行 `pnpm check` 前安装这两个运行时。

开发与验证基线为 Pi **1.1.0**。工作区 overrides 固定核心版本（包括自动安装的 peers），回归检查全部 18 个声明 Pi peers 的包实际解析结果；发布清单中的 Pi core 仍是由宿主提供的 `"*"` peers，不是运行时依赖。@features/pi-core-cohort.feature 和 @tests/test_pi_core_cohort.py 同时检查实际模块解析与清单。

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
