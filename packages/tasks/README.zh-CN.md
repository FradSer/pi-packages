# @fradser/pi-tasks

Tasks 是支持依赖关系和完成证据的持久化工作列表。目标是持续追求的一个结果；任务是列表中可以排序、领取和完成的一项工作。

[English](README.md)

## 何时使用 Tasks

**Tasks 是可选基础设施，不是每次编码都需要的额外记事本。** 对单模型、单会话的日常工作，会话上下文通常已经足够。维护独立任务列表会增加工具调用和状态更新，也可能让列表与实际工作脱节。仅仅涉及多个步骤或多个文件，不足以说明需要 Tasks。

当工作需要明确的共享状态时，再使用 Tasks：例如参与者领取归属、依赖检查、持久化恢复或完成证据。上下文召回帮助模型记住已有工作，但不会强制执行这些协调规则。Agent Teams 使用本包的存储和状态转换接口，因此删除本包还需要调整该消费者。

Tasks 不保证工作会完成，也不保证完成声明正确。它是被动记录器：未完成任务不会触发下一轮模型执行；记录验证结论也不等于实际执行检查。参见[被动监控](#被动监控)。

建议普通单会话工作默认不用 Tasks，在确有协调或恢复需求时启用。这项建议不会覆盖仓库中要求记录任务的现有指令。

## 安装

```bash
pi install npm:@fradser/pi-tasks
```

扩展注册四个工具，使用 `@fradser/pi-kit` 的共享渲染、持久化原语和参与者契约。Agent Teams 使用同一个存储；Tasks 不启动 worker，也不添加研究、归档或独立历史工作流。任务工具不会传入子进程。子代理不能领取或完成任务，主代理需要根据子代理报告记录结果。

## 工具与状态

| 工具 | 用途 |
| --- | --- |
| `create_task` | 记录标题、可选详情、依赖和替代关系。 |
| `get_task` | 读取完整任务，包括证据和后续上下文。 |
| `list_tasks` | 按 statusFilter、claimable、ready、limit 和 cursor 读取摘要。 |
| `update_task` | 编辑内容，并可同时申请一次受检查的状态转换。 |

`subject` 是不超过 60 个字符的简短标题；`description` 是可选详情。仅有标题也可以构成完整任务。只有前置任务完成后才能开始的工作，应在 `dependsOn` 中声明依赖。用 `supersedes` 替代过时或错误的工作：新任务接管其依赖者，旧记录仍可读取。任务 id 在创建时由标题生成，改名不会改变 id。

| 状态 | 含义 | 下一步 |
| --- | --- | --- |
| pending | 等待依赖完成后可领取，也包括重新打开的工作。 | in_progress |
| in_progress | 调用者持有本次执行。 | completed 或 blocked |
| blocked | 需要解除阻塞或检查上一次执行。 | 附带 reason 转为 in_progress |
| completed | 已交付成功结果、证据及所需验证结论。 | pending，重新打开 |
| cancelled | 调用者放弃的未完成工作，退出看板但保留记录。 | pending，重新打开 |

前置依赖未完成时，任务保持 pending，并显示 `Blocked by #N`，不能开始或成功完成。`supersededBy` 是替代关系，不是状态。被替代记录仍可读取，但不会进入待处理、可领取、就绪或继续执行的工作集合。持有被替代任务的参与者必须先确认取消，才能释放租约。

`update_task` 的状态转换规则：

- `in_progress`：由推导出的调用者领取。恢复 blocked 工作时，必须用 `reason` 说明如何安全恢复。
- `blocked`：记录 `reason`，释放当前执行归属，保留之前的证据。
- `cancelled`：用 `reason` 记录放弃原因。任务不再计入未完成工作，但保留历史；已取消的前置任务仍会阻塞依赖者。没有外部条件需要等待时，应使用 cancelled，而不是 blocked。
- `completed`、`outcome=success`：记录 `result`。依赖、先前执行和声明的 verify 门槛必须满足完成检查；声明了门槛时，必须提交 `verdict=pass`。blocked 工作必须先恢复，才能提交成功。
- `completed`、`outcome=failed`：保留失败结果并转为 blocked。后续成功仍保留 `failureEvidence`。
- `pending`：重新打开 completed 或 cancelled 任务并保留证据。已完成或被持有的传递依赖者转为 blocked，原结论撤回，租约释放。恢复时必须处理已重新打开的前提。

存储只记录验证结论，不会执行验证提示。库消费者可以分别选择完成检查；面向模型的工具要求全部检查。归属由调用者确定，不接受 assignee 参数。外部持有者、替代关系、无效依赖图或状态转换会导致操作被拒绝。

内容编辑可以替换 subject、description、dependsOn 或 verify；context 合并后续信息。未知依赖和环路会被拒绝。被持有或已完成的任务不能新增未完成前置依赖。一次调用可以同时编辑内容和转换状态：若内容编辑成功、状态转换失败，内容编辑仍保留，结果会明确说明；若内容编辑被拒绝，两部分都不会记录。

## 渲染与分页

所有工具结果使用 pi-kit 的 `[tasks]` 生命周期样式，默认折叠，只显示标题行和末行的原生展开提示。过长标题会完整换行，而不是截断。任务名和末尾状态保持可读。使用 Ctrl+O 或原生行操作展开详情，查看描述、Verify、证据、阻塞、错误和持久化提示。列表折叠时只显示任务数量。

```text
[tasks] create · #2 Verify dependency handling (pending) · to expand
```

显示编号按完整任务集合的创建顺序排列，因此筛选结果可能跳号。普通行不显示存储 id、持有者和资源锁；公开工具不接受或返回资源字段。

列表只包含摘要，不含描述、验证门槛和完整结果；需要详情时使用 `get_task`。每页最多 40 项。`count` 是匹配总数，`shown` 是本页数量，`offset` 是本页位置，`cursor` 是下一页令牌。将 cursor 传回即可继续读取，筛选条件随令牌保留。无效令牌、筛选不匹配或列表快照变化都会被拒绝；发生修改后应重新列举。`limit=0` 不返回行，正小数向下取整，负值被拒绝。

参见[全部 TUI 触发条件与示例](TUI.zh-CN.md)。

## 被动监控

Tasks 记录工作，不控制模型执行。扩展不注册结算、请求上下文或工具活动钩子，不添加能力提示、自动提醒、等待行或继续执行行。未完成任务不会请求下一轮模型执行。

模型可以在最终答复前主动检查：

1. 用 `statusFilter: ["pending", "in_progress", "blocked"]` 调用 `list_tasks`。
2. 沿所有 cursor 读取全部匹配项。
3. 对需要完整检查的任务调用 `get_task`。
4. 报告未完成工作，或附带证据记录完成。

这是调用者主动执行的检查，不是运行时要求。Tasks 不会把最终答复视为任务完成；`update_task` 仍需通过状态和证据检查。

旧的结算辅助函数、能力提示辅助函数和状态消息渲染器及其公开导出已移除，不保留兼容实现。四个任务工具和已保存的任务格式保持不变。

## 持久化与兼容性

```text
~/.pi/agent/tasks/<sessionKey>/tasks.json            原子替换，单写入者
~/.pi/agent/tasks/<sessionKey>/claims/<id>.json      独占创建的领取意图
~/.pi/agent/tasks/<sessionKey>/submissions/<id>.json 独占创建的提交意图
```

独立安装时，Tasks 在会话启动时恢复 tasks.json，在修改后持久化。协调器接管存储后承担唯一写入者职责；仅发布参与者注册表不构成接管。会话切换先解除旧写入者，再加载新状态。已有文件不可读或不兼容时，会报告提示，不会用空存储覆盖。任务文件版本仍为 2。

旧 recovery_hold 映射为 blocked。旧 superseded 映射为普通状态并保留替代关系；缺少替代对象时保留 replacementUnresolved 元数据，保持不可用并提示修复。在关系修复前，不能重新领取、删除或作为依赖。没有参与者的 in_progress 任务恢复为 blocked。已完成记录、结果、恢复说明和替代关系保留。旧执行记录会被分类，不删除历史。已退役的 board.json 不会被加载、复制或删除。

存储会规范化恢复字段并报告修复。context 更新合并历史发现；显式 outstanding 列表替换当前列表，空列表清空它。默认保留文本预算为 64 KiB，包含标题、描述、verify、证据、阻塞原因、失败证据、恢复说明、保留的证据历史、资源和上下文。调用者只能降低预算。超预算的模型写入会被拒绝，不会静默截断。运行时停止清理始终保留诊断并释放已停止的持有者，也适用于已经超预算的旧记录。

任务意图通过独占创建写入；只有存储所有者写任务状态。已知消费者所需的资源兼容辅助函数仍保留。`TASK_HOLDER_ENV` 和参与者接口使用 pi-kit 契约，不重复定义注册表类型。

## 验证

行为契约位于 features/，回归检查位于 tests/。

```bash
python3 -m pytest packages/tasks/tests/ -q
pnpm typecheck
pnpm --dir packages/tasks pack --dry-run
uv run --with pyte python packages/tasks/tests/task_native_frames.py --output /tmp/tasks-native-frames
sh packages/tasks/tests/tasks_docker.sh
```

原生 CLI/TUI 检查使用真实 Pi 和确定性的本地 provider，不使用凭据，也不请求外部模型。这些检查证明运行时行为，不证明真实模型的判断能力。完整验证完成后，证据和限制另行记录。

## 许可证

MIT
