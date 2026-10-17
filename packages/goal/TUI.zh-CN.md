# Goal TUI 与触发条件

Goal 是当前线程的一个持续目标。公开工具只有 `create_goal`、`get_goal`、`update_goal`；命令只有 `/goal`。普通工作使用 Pi 原有工具。

## 显示规则

所有 Goal 的工具结果、命令结果和自动状态消息使用 pi-kit 的同一 `[goal]` 样式。工具调用头为空，由结果负责显示一次。目标、完成条件、原因及检查报告默认完整显示，按终端宽度换行；不使用省略号，也不要求 `ctrl+o` 才能读取正文。给模型的 `get_goal` 内容可分页，但首个 TUI 结果保留完整正文。

底部是被动状态行，不接管输入。实际运行或已获得继续授权时显示：

```text
Pursuing goal · 2h 25m
```

| 底部文本 | 触发条件 |
| --- | --- |
| `Pursuing goal · <elapsed>` | active 且允许继续，调度器正在运行、已 armed 或已 claimed |
| `Goal waiting · <elapsed>` | active，但无有效运行/继续授权，包括恢复旧会话、无新工作、检查失败或运行失败 |
| `Goal paused · <elapsed>` | 用户明确暂停 |
| `Goal blocked · <elapsed>` | 同一阻塞连续三个 Goal 工具轮次出现，期间没有有效进展 |
| `Evaluating the objective and recorded evidence...` | 显式完成请求正在执行一次无工具检查；用一行中性说明暂时替换普通状态行。该行不加 `[goal]` 前缀，因为行位置已经属于这个目标 |
| 无 Goal 状态行 | 当前线程无开放目标，目标已完成或已清除 |

时间是已记账的运行时间，恢复时不归零。静止 waiting 状态不会增加时间。后台检查的 token 计入目标；检查中断或线程切换不免除已返回的用量。

自动继续的进度只认工作区变更：只有目标尚未见过的成功 `edit` 或 `write` 才换来下一次运行。读取、搜索、抓取、跑命令以及把工作交给子进程都属于探索，不能无限维持循环；连续三轮没有任何可观察变更时自动继续停止并说明原因，`/goal resume` 重新开始这个窗口。修订目标不会清空这个记忆，所以换一种说法不能把同一次变更重新算成进度。用户自己的一轮算新机会，不计入窗口。

目标没有预算，也不能被设置预算：它由自己的工作量界定。用量只是报告，不是闸门 —— 模型与完成检查的 token 都记在目标上，但没有任何数字太大会让目标停下。旧记录里的 `tokenBudget` 字段被忽略。

## 工具结果

| 显示头 | 触发条件与后续行为 |
| --- | --- |
| `[goal] started` | 成功创建目标，正文包含完整目标及完成条件 |
| `[goal] creation not applied` | 已有目标、空目标或存储/聚焦失败；目标没有被替换 |
| `[goal] active` / `paused` / `blocked` | `get_goal` 返回当前状态及完整正文；`section: objective` 返回目标正文 |
| `[goal] no active goal` | 当前线程没有开放目标；不会借用其他线程的目标 |
| `[goal] read not applied` | 无效或已过期的分页 cursor；重新从第一页读取 |
| `[goal] updated` | 原子提交完整修订目标及其完成条件；已接受的 `/goal <text>` 请求可授权恢复，普通修订保留暂停状态 |
| `[goal] update not applied` | 空更新、混合状态与修订字段、缺少原因、空目标、已封顶目标修订或存储竞争；正文说明具体原因 |
| `[goal] paused` | 用户明确要求暂停，通过命令或工具统一中止当前运行与检查，撤销继续授权 |
| `[goal] blocker reported` | 同一阻塞的第 1 或第 2 个连续轮次；同一轮重复报告只计一次 |
| `[goal] blocked` | 第 3 个连续阻塞轮次；撤销自动继续，解决后由用户恢复 |
| `[goal] not met` | 完成检查正常返回 NOT MET；保留目标，显示全部缺失要求，不自动暂停或自动重复检查 |
| `[goal] check failed` | 检查调用、解析或用量记账失败；显示完整原因，等待后续明确操作 |
| `[goal] check cancelled` | 本次检查被取消，且要求未变化；不会完成目标 |
| `[goal] check discarded` | 检查过程中目标要求、状态、调度 generation、线程聚焦发生变化，或结束提交失去竞争；旧结果不结束新要求 |
| `[goal] completed` | 显式完成请求的单次检查返回 MET，且提交时目标仍有效、属于本会话；删除开放记录并结束当前运行 |

SDK 参数验证失败也使用 Goal 的同一结果样式，正文显示参数错误。非 Goal 工具被停止守卫拒绝时，宿主仍使用该工具原有错误显示，不另发重复 Goal 事件。

## 命令与自动路径

| 操作/显示 | 触发条件 |
| --- | --- |
| `/goal` → 当前状态与完整正文 | 只读取当前线程目标；不调用模型检查 |
| `/goal <text>` → `[goal] requesting` 与原话 | 向模型递交完整请求；transcript 只显示一行 `[goal] requesting` 及其下方的用户原话，共享 band 会剥离原话里的控制字节；完整请求正文不进入终端 transcript，但模型仍读取它，会话记录也保留它。实际创建或修订结果显示在自己的行。追加要求先保留旧目标，模型提交合并后的完整修订。只有单独一个管理动词才是命令：`/goal clear my schedule` 是请求，不是清除 |
| `[goal] request not sent` | 请求递交失败，撤销未接受的激活意图 |
| `/goal pause` → `[goal] paused` | 显式用户暂停；中断检查、当前运行及排队继续 |
| `/goal resume` → `[goal] resumed` | 当前记录仍有效且有 run allowance；保留累计 token、时间及运行次数 |
| `/goal clear` → `[goal] cleared` | 撤销授权并把记录标为终态完成；不宣称目标已完成，不写归档，也不删除记录 |
| `[goal] clear not applied` | 清除时修订号变化或存储写入失败 |
| `[goal] waiting` | 本轮运行失败、没有新的有效工作、连续三轮没有可观察变更、run allowance 用尽、继续递交失败、恢复被拒绝或 checkpoint 被拒绝；正文给出原因 |
| `[goal] failed` | 后台路径报告异常；正文给出具体原因 |
| 自动继续（无额外日志行） | 成功完成了新的工作区变更（或用户自己的一轮），宿主空闲且没有用户排队消息，所有权/generation/次数均有效；一次授权只消费一次 |

相同工具、参数及输出的重复读取只算一次工作；输出发生变化可成为新工作，但只有 `edit`/`write` 的未见过变更才延长自动继续。Goal 自身的读取和更新不算工作。用户排队输入优先于自动继续。没有逐轮自动验收模型调用。

## 已删除的分支

没有 `research_goal`、`next_action`、独立 Goal history、`2 ledger events`、三次完成拒绝自动暂停、`Nothing to record` 或 `Archived under .pi/goals/archived/.`。旧 history/research 读取请求只返回迁移说明；旧字段不获得调度权。历史归档、旧 ledger 和其他既存文件不删除，也不再写入。

新目标仅维护一个原子开放记录。完成和清除都释放运行状态；会话 transcript 保留可读事件历史。完成检查使用完整目标、完成条件及有来源的会话证据；检查报告按不可信数据注入且不会跨目标、线程或修订残留。

## 可重复验收

`python3 -m pytest packages/goal/tests/ -q` 运行行为、存储竞争、真实 SDK 脚本会话与渲染测试。`python3 packages/goal/tests/goal_native_completion.py` 使用真实 Pi CLI、PTY 与同步终端帧，覆盖完成、拒绝、失败、取消、阻塞、长中文换行、暂停/恢复/清除。`uv run --no-project --with pyte python packages/goal/tests/goal_native_request_row.py` 输入一次 `/goal <text>`，断言屏幕上只有一行 `[goal] requesting` 与原话、窄宽度换行后仍可读，并断言请求正文从未到达终端。`uv run --no-project --with pyte python packages/goal/tests/goal_native_revision.py` 先建立一个目标并让它因无有效工作而停下，再输入一次 `/goal <text>`，断言这个目标就地被修订：原要求与完成条件都保留、目标重新处于 pursuit、且不写归档或 ledger。

`sh packages/goal/tests/goal_docker.sh` 打包当前 Goal 和必需依赖 pi-kit，在 Docker 中安装**最新的 Pi**（运行时从 registry 解析，并把它依赖的每个 `@earendil-works/*` 一并固定到该版本；需要复现旧基线时用 `PI_VERSION=x.y.z`）；Pi 的 package 配置仅加载 Goal。测试同时覆盖打包源码及正常自动加载路径。模型为确定性脚本 provider，完成检查为注入式 stand-in；这些证据验证宿主集成和 TUI，不宣称真实远程模型的判断质量。
