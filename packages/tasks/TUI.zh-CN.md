# Tasks TUI 场景

所有行由 pi-kit 生命周期渲染器绘制，统一 `[tasks]` 前缀。所有工具结果默认收起：收起行只显示 `[tasks] <action> · <标题>`，展开提示跟在标题的最后一行，正文需展开后查看。标题超宽时整体换行显示，不省略中间，除最后一行外都按整宽换行，只有最后一行给展开提示留位，完整任务名和结尾状态（如 `(in progress)`、`(blocked)`）都保留。显式工具结果的正文按窗口宽度换行。使用 Ctrl+O 或原生行操作展开完整详情。显示编号按全任务集的创建顺序固定，存储 id 留在结构化结果中。列表收起时只显示任务数量，完整正文通过展开或 `get_task` 读取。

下表的正文内容均指展开后的内容。

| 场景 | 触发条件 | 显示 |
| --- | --- | --- |
| 创建 | `create_task` 成功 | `create · #N 标题 (pending)`，描述、Verify、依赖、Blocked by |
| 读取 | `get_task` 找到任务 | `get · #N 标题 (状态)`，正文、证据、恢复信息、替换关系 |
| 列表 | `list_tasks` 成功 | `list · N tasks`，编号标题、状态、依赖、阻塞关系 |
| 空列表 | 无匹配记录或 limit=0 | `list · No tasks`，分页信息仍依返回值展示 |
| 分页 | 尚有未返回记录 | 显示本页范围和下一页 cursor；用同一 cursor 继续读取 |
| 修改 | 无 status 的有效内容修改 | `update · #N 标题 (状态)`，已保存的完整内容 |
| 开始 | pending 的依赖已完成且没有其他持有人或资源冲突 | `update · #N 标题 (in progress)`，完成所需证据与 verdict |
| 阻塞 | 非完成、非替换任务提交 status=blocked 和 reason | `update · #N 标题 (blocked)`，完整阻塞原因 |
| 取消 | 非完成、非替换的未完成工作提交 status=cancelled 和 reason | `update · #N 标题 (cancelled)`，保留取消原因；不再计入未完成，依赖它的任务仍然被阻塞 |
| 恢复 | blocked 提交 status=in_progress 和恢复理由，依赖及权限允许 | `update · #N 标题 (in progress)`，恢复信息与既有证据 |
| 完成 | success、证据、依赖、完成 gate 均符合要求 | `update · #N 标题 (completed)`，本次证据 |
| 失败 | completed 路由提交 outcome=failed | `update · #N 标题 (blocked)`，本次失败证据和原因 |
| 重开 | completed 或 cancelled 提交 status=pending | `update · #N 标题 (pending)`，保留证据，指出被失效的下游任务 |
| 替换 | 创建新任务时指定 supersedes | 新任务 create 行，Replaced；旧记录保留并显示 Replaced by |
| 拒绝 | 未知 id、非法参数、权限、依赖、证据、gate、恢复理由或预算不满足 | `<action> not applied`，完整错误；同调用中已接受的内容修改明确保留 |
| 持久化告警 | 文件无法读取/写入或恢复修复了异常记录 | `Notice:` 完整原因；后续成功写入清除写入告警 |

```text
[tasks] update · #2 Validate dependency behavior (blocked) · to expand

# Ctrl+O 展开后：
Description:
Exercise the dependency transitions and retain the result evidence.
Verify:
All affected checks pass.
Depends on #1
Reason: The test environment is unavailable.
Evidence: The setup command failed with the recorded diagnostic.

```

Tasks 只记录任务，不注入模型指令，不自动续跑，也不显示 waiting 或 continue 行。模型可以在收尾时主动调用 `list_tasks` 查询 pending、in_progress、blocked，再用 `get_task` 检查详情。未完成任务不会阻止模型结束。
