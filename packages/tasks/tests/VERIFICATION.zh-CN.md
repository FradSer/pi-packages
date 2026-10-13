# Tasks 四状态与完整 TUI 验收

日期：2026-10-08。范围：Tasks 的状态、持久化兼容、工具、自动继续与 TUI，以及 Agent Teams 对此公共契约的必要适配。未发布、未修改远程分支；既有任务历史和其他工作区修改保留。

> 后续变更（2026-10-12）：TUI 显示契约改为全部行默认收起，只显示标题与原生展开提示；正文经 Ctrl+O 或行操作展开。本文档下表中“全部默认完整 TUI”一行，以及“原生运行与 Docker 边界”一节中“完整默认长文本尾部可见”“没有展开提示”等表述，属于 2026-10-08 的验收记录，已被取代。当前契约与证据见 ../CONTEXT.md 与 ../TUI.zh-CN.md。

> 后续变更：Tasks 现为被动任务记录，已删除自动续跑、waiting/continue 消息和能力说明注入。下文涉及自动继续的内容仅是历史验收，不再描述当前实现。当前验收见 ../CONTEXT.md；被动行为测试见 test_passive_tasks.py。

## 需求与证据

| 要求 | 当前实现与验收来源 |
| --- | --- |
| 四种状态与旧数据兼容 | types.ts 的 TASK_STATUSES；store.ts 的 loadTasks；test_simplified_tasks.py 验证 recovery_hold、失败证据、替换链和缺失替换目标。 |
| 依赖、恢复、重开保护 | graph.ts、takeTask、blockTask、reopenTask；test_task_tool.py、test_work_domain.py 和 test_simplified_tasks.py 覆盖依赖拒绝、恢复理由、重开下游失效及证据保留。 |
| waiting 不冒充暂停 | stop-check.ts；test_task_stop_check.py 与真实 Pi progress 模式验证三次额度耗尽及具体等待原因。 |
| 四工具一致 | tool.ts 的参数与返回投影；test_task_surface.py、test_task_tool.py、test_work_context.py 的公开结构和状态枚举检查。 |
| 全部默认完整 TUI | rows.ts 使用一套 pi-kit 绑定；TASK_ROW_SPEC 与自动消息保持完整正文；test_task_contents.py、test_task_content_tui.py、test_simplified_tasks.py 和原生终端帧验证正文、尾部、证据、错误及告警。全部触发条件见 ../TUI.zh-CN.md。 |
| 超过 40 项可访问 | list_tasks 的快照分页 cursor；test_simplified_tasks.py 覆盖全列表、过滤器、非法 token 与过期快照。 |
| 有效工作与输入竞争 | tool_execution_start/end 收据；test_task_stop_check.py、test_simplified_tasks.py 验证重复收据、参数键顺序、纯任务编辑、待处理输入、其他 handler 和取消不消耗额度；变化的 blocker/notice 不被去重吞掉。 |
| 历史与运行安全 | test_work_domain.py 验证原子持久化、恢复、会话切换及 sole writer；任务意图和所有权检查保留；替换记录不可 discard，停止执行者即使超过文本预算也释放 lease 并保留诊断。 |
| 工作清单边界 | 只注册四个任务工具；替换为关系，执行记录只保留兼容历史，不参加续跑；没有新增研究、归档或底部 goal 状态流程。 |

行为契约先写入 features/simplified-tasks.feature，并同步已有 feature。test_simplified_tasks.py 的 16 项回归覆盖新增行为与修复；已有测试继续覆盖四工具、迁移、权限及拒绝路径，未以删除检查代替修复。

RED 记录保存在 /tmp/tasks-optimize/：red.log、red-blocked.log、red-resident.log、red-unresolved-label.log。新增缺失替换目标文案断言在修复前显示 `undefined` 并失败，修复后通过。

## 检查结果

| 检查 | 结果 | 输出 |
| --- | --- | --- |
| Tasks + pi-kit + Goal 完整套件 | 295 passed；最终拒绝文案微调另通过 16 项回归 | /tmp/tasks-optimize/core-frozen.log、unresolved-green.log |
| Agent Teams 完整消费方套件 | 298 passed | /tmp/tasks-optimize/acceptance-consumers.log |
| 最新错误/告警/自动消息的受影响检查 | 43 passed | /tmp/tasks-optimize/presentation-final.log |
| 最终 TypeScript 检查 | 通过 | /tmp/tasks-optimize/typecheck-final.log |
| 工作区 packed manifest | 19 包通过 | /tmp/tasks-optimize/pack-frozen.log |
| Tasks pack dry-run | 通过，包含 TUI.zh-CN.md | /tmp/tasks-optimize/tasks-pack-frozen.log |
| 原生 CLI | 六种模式通过；同时包含在完整 Tasks 套件内 | /tmp/tasks-optimize/native-cli-current.log |
| 原生交互 TUI | 两项 pytest + 三种同步终端帧模式通过 | /tmp/tasks-optimize/native-frames/native-results.json |
| 最终 packed-only Docker | 164 passed + 三种原生帧 + 自动加载 CLI 通过 | /tmp/tasks-optimize/docker-final.log |

`git diff --check` 对本次 Tasks、Agent Teams、README 和 changeset 的修改通过。验证文件与 TUI 触发表、manifest 和 README 引用均已核对。Docker 在最后一项拒绝文案修复后重新打包运行全部 Tasks 检查。

## 原生运行与 Docker 边界

test_task_stop_live.py 使用真实 Pi CLI，执行 recover、ignore、progress、restore、inspect-only、content 六种模式。覆盖依赖顺序、失败恢复、持久化恢复、只读等待、额度和 headless 最终文本。

task_native_frames.py 通过 PTY 启动真实交互 Pi，以同步终端帧在 80、40 列验证 content、ignore、progress：完整默认长文本尾部可见，等待原因显示，没有展开提示或伪用户暂停。测试使用较高的终端行数容纳全部 transcript；这证明渲染和窗口宽度适配，不是物理终端滚动操作验收。

tasks_docker.sh 打包 Tasks 与必需的 pi-kit，安装在 node:24-bookworm-slim 的隔离 Pi 1.0.4 中。设置 packages 只有 @fradser/pi-tasks；测试用本地 provider fixture 单独加载。pnpm-workspace.yaml 显式将传递 pi-kit 指向同一 tarball，避免混入注册表版本。源码检查及运行检查指向安装的打包文件；Subagents 仅提供只读 participant-registry 参考文件，未安装或加载其扩展。验证完成后仅移除本次创建的容器，tarball、哈希、原生帧和日志保留在 receipt 目录。

最终 receipt：`/var/folders/vn/whfnt01d4b19zg44txbtznbc0000gn/T/tasks-docker-bZ0nqzC9`。

- Tasks SHA256：`7c13df54c5b1b6ffbf8f48f3b9099014a56e19f4e1433c247400b42f95580721`
- pi-kit SHA256：`59a6d77f051fbfbf2f04709a13764655ffebd108339626c7960a53b218382ee9`
- `verification.log` 的 settings 收据为 `packages:["/isolated/node_modules/@fradser/pi-tasks"]`，三个帧模式均覆盖 80、40 列。

以上使用确定性脚本 provider，无凭据和真实模型请求。验证的是实际 Pi 生命周期及渲染，不证明真实模型会正确判断完成条件。

## 独立复查与发布影响

独立只读复查发现并推动修复四项问题：停止清理被预算拒绝后遗留 lease、discard 删除替换历史、被替换的 resident 接受新输入、恢复理由在默认 TUI 不可见。各项都有回归，后续复查未发现材料性问题；最新去重和错误展示改动另通过独立两项回归。审查者未独立重跑整个 Docker 与全套测试。

Changeset 为 @fradser/pi-tasks minor、@fradser/pi-agent-teams patch。公开状态由旧状态收敛为四种，Agent Teams 消费方同步适配；旧文件在读取时兼容，保留证据与替换历史。加载新代码需要重新加载 Pi。当前没有执行发布。

pnpm check:install 仍受用户现有全局 Pi 安装设置影响：缺少 Agent Teams、btw、context、keyboard、monitor、plan-mode、recap、skill-router、utils、vision 共十项本地安装路径。未为通过检查而修改用户设置或安装无关扩展。独立 Docker 安装验收只证明本次 Tasks 安装范围；整个全局安装环境仍有此阻碍。
