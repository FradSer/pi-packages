# pi-open-deskos

把本机的 Pi 会话及其运作事件上报给 Open DeskOS；也可选择成为 **Console**，远程驱动 Open DeskOS 上托管的 Pi 会话。

**English** | [简体中文](README.zh-CN.md)

Open DeskOS 通常靠扫描来发现 Pi 会话：本地扫，或经 SSH 扫。这个方向不一定可用，而且扫描看不到会话到底在做什么。本 package 把它反过来：拥有会话的那台机器主动打开一条 **Desk Link**，自己上报。

机器还可以另外持有 **Control Credential** 而成为 **Console**：向同一个监听面另开一条控制连接，列出 desk 上托管的 **Hosted Pi**、启动新的、进入某个、改向正在执行的 turn、取消、结束，并按需读取完整历史。

## 安装

```bash
pi install npm:pi-open-deskos
```

若要从本地 checkout 安装，在仓库根目录执行：

```bash
pi install "$(pwd -P)/packages/open-deskos"
```

该命令记录 package 的绝对路径，因此 checkout 可以放在任意位置，包括含空格的目录。请保持 checkout 原地不动；Pi 直接加载本地文件。

## 配置

地址与 token 必须同时提供，机器才会开始上报；只配一半会保持静默。控制能力还需要单独的控制凭据，未配置时完全关闭。运行 `/open-deskos` 查看配置提示。

```bash
export ODK_DESK_LINK_ADDRESS="192.168.88.161:8765"   # Open DeskOS Desk Link Service
export ODK_DESK_LINK_TOKEN="<per-link token>"
export ODK_DESK_LINK_MACHINE="desk-mac"              # 可选，默认为主机名
export ODK_DESK_LINK_CONTROL_TOKEN="<control credential>"   # 可选：使本机成为 Console
```

请把它们放进 Pi 运行时的环境（桌面会话中即启动 `pi` 的那处）。控制凭据**不会上线**：desk 下发一次性 nonce，本机对 nonce 做出证明。

## 上报内容

- 当前会话的实时身份、目标、activity 与事件，以及本机注册在 `directory-sessions` 元数据中的其他会话（由 `pi-utils` 与 `pi-keyboard` 写入）。resumed、reload 或 fork 后上报端启动时会先回放当前会话自己的有界 durable JSONL 尾部，再转发后续实时消息，避免 resumed Pi 被 Desk Link 显示为运行中却没有事件。UUID 与带时间戳前缀的 UUID 别名会合并为同一会话。
- 会话状态：元数据表示工作中、Pi 进程存活、时间戳匹配该进程生命周期时才为 `running`；存活的 idle/settled 会话为 `settled`。已结束、无效、被复用、无法核实的 PID 或明确退出的记录为 `exited`。每次扫描只读取一次有界进程表（1 MiB，2 秒超时），同一 PID 只有最新且无歧义的会话可视为存活。当前会话以 Pi 自身的 idle/agent 事件为准。
- 原始元数据的 start/update 时间、可选会话名、目标与 activity/recap。扫描不会凭空发明新的 activity 时间戳，也不读取会话历史。
- 有界会话事件：每会话最多保留最新连续的 300 条事件与 1,048,576 UTF-8 字节（计入正文与工具名）。正文保留换行并按类型限长：user 8 KiB、thinking 4 KiB、tool-call 4 KiB、assistant 16 KiB、tool result 64 KiB。
- 工具结果保留完整的多行 Markdown，包括表格、代码围栏和空白，每条正文最多 65,536 UTF-8 字节。所有文本块以两个换行连接；图片与任意结果元数据不上报。任一类型的正文超过自身字节上限时会带 `truncated: true`，且不会截断 Unicode 码点。可选 `toolName` 为独立的 200 字符摘要，不再作为前缀插入 Markdown 正文。会话 activity 仍为简短的首行摘要。

会话开始时以及每次扫描后每 5 秒刷新一次清单，链路离线期间同样刷新。刷新只替换被发现的条目：当前会话的身份与事件不会被陈旧元数据删除或覆盖。关闭/重载会取消刷新调度，并使待处理结果与重连失效。

最多上报 64 个会话。只有当前会话固定保留；其余按 running、settled、exited 顺序优先，再按时间排序。曾直接观察的会话被其他进程恢复时，可由更新的元数据刷新状态，同时保留已有事件。容量上限允许淘汰旧历史及其事件，并非归档。

每次扫描最多访问 256 个 workspace、2,048 个 JSON 文件、8,192 个目录项，每个文件最多读取 16 KiB。格式错误、超限、符号链接与非普通文件一律跳过。名称、目标与 activity 各限 200 字符，并可能在传输中进一步压缩以符合 65,536 字节的快照预算。会话 ID、精确工作目录、workspace 名称与时间戳从不缩短或折叠。若精确身份字段仍超出该预算，上报端会整条省略优先级最低的条目，并由 `/open-deskos` 报告省略数量。当前会话始终保留。单个当前身份大于帧预算时无法在不改变该身份的前提下表示；这是病态上限。

默认读取 `~/.pi/agent/directory-sessions`。可用 `PI_DIRECTORY_SESSIONS_DIR` 指定注册表；否则 `PI_CODING_AGENT_DIR`（或旧的 `PI_AGENT_DIR`）覆盖 agent 目录。元数据写入端必须使用同一目录。发现过程不修改、清理注册表文件。不凭空创建没有元数据的会话；被删除的元数据会在下次刷新消失，除非本上报端曾直接观察该会话。

## 驱动 Hosted Pi

`/open-deskos` 会打开菜单，其控制台一行列出 desk 托管的 Hosted Pi（含状态、目标、项目与时长），并可启动新的会话、进入已有会话、追加指令（**运行中也可**，此时是改向当前 turn 而不是另起一个）、取消当前 turn、结束会话、按需读取完整历史。

- **一个 Console 同时驱动一个 Hosted Pi。** attach 是替换而非共享，可重复且按会话身份幂等，因此重启后的 Pi 会话可以重新 attach。
- **不重复、不遗漏。** 事件位置是其对应完整条目在 Hosted Pi 会话日志中的物理位置；若中间有非消息条目，位置只保证严格递增，不保证连续。首次 attach 发送 `after: null`，从 desk 当前边界开始；旧内容需显式通过 history 获取。恢复 attach 会发送上次已应用位置，先按序接收直到 `caught_up` 边界的补流，再进入实时事件。没有重放窗口，也没有需要解释的 resync。
- **会话比连接活得久。** 控制连接断开不会结束 Hosted Pi：它继续运行、保留身份、仍可按身份 attach。
- **进入上下文的只有有界尾部。** 实时事件与终态结果以有界摘要进入你的会话；完整内容通过 history 工具与控制台面板按需获取。
- **desk 自己说了算。** 本机驱动期间，desk 会在 Pi Sessions 总览标题上标明驱动方，本地触控与键盘始终可用。
- **工具面。** 助手可调用 `desk_*` 工具完成 list / start / attach / prompt / cancel / end / history。控制台面板自己接管键盘输入，不拦截全局终端输入。

## 不上报什么

- **上报永远不等于管理。** 只持有上报 token 的机器只能上报：package 从不向被上报的会话发送 prompt、不阻塞回合、不修改消息；通过 Desk Link 可见**不等于**可管理。
- **控制是独立能力。** 它需要 Control Credential，且从不走上报连接；没有该凭据的机器不可能成为 Console。
- **不管理被上报的会话。** 即使作为 Console，package 也不管理自己上报的那些会话；控制只作用于 desk 托管的 Hosted Pi，那是另一回事。
- **不能回答 Hosted Pi 的中途请求。** desk 的 Pi host 不加载扩展，SDK 也不提供权限、审批或提问面，因此 Hosted Pi 无法产生需要你回答的请求。这是 host 配置的限制，不是缺失的功能。
- **无网络发现与配对。** 发现的是本地会话元数据；不知道地址与 token 的机器无法注册，Console 也必须事先知道控制凭据。
- **不扫描其他会话历史与凭据。** resumed、reload 或 fork 后当前 Pi 启动时只读取 `sessionManager.getSessionFile()` 指向的当前 JSONL 文件有界尾部，并按同一事件上限回放；不读取其他会话的历史、认证文件或任意额外元数据（其他会话只贡献注册表元数据，不合成事件）。当前会话的工具结果正文**会**在上述上限内上报，其中可能包含文件内容或工具返回的敏感输出；只有在你确实愿意共享时才配置该链路。
- **不加密。** Desk Link 是面向仅局域网监听的明文连接。控制凭据不上线，因此抓包拿不到可复用的执行凭据，但内容本身并未加密。请勿把 Desk Link Service 暴露到局域网之外。

## 在 Pi 内查看链路

```
/open-deskos
```

菜单在任何配置下形状一致，不可用的一行会说明原因而不是消失。其中状态一行显示链路状态、机器标识、连接地址、上报会话数、事件数、控制状态，以及最近的连接错误（如有）；控制台一行打开 Hosted Pi 列表。带参是快捷路径：`console`、`status`、`attach`、`launch`、`cancel`、`history`。诊断信息在任何配置下都仅通过命令查看：Open DeskOS 不添加页脚状态行、自定义页脚或工作目录后缀，离线或未配置时也一样。

## 链路断开时的行为

上报端以递增等待重连（1s、2s、4s……上限 30s），并始终只保持一条链路。历史与待发事件均受每会话 300 条 / 1,048,576 字节上限约束。每次新连接都会发送当前会话状态，重放完整的已保留事件尾部，即使离线期间没有新事件也一样，因为服务端可能在最后一条链路关闭后清除机器状态。此连接后续刷新只发送新事件。

控制连接是分开的，不复制这套行为：list / launch / history 用一枪式请求连接，仅在本机 attach 到某个 Hosted Pi 期间才保持一条连接。丢失它不影响上报，也不会结束 desk 上的会话。

## 线上契约

一条 TCP 连接上的换行分隔 JSON，上报为版本 1。清单发现的会话带 `discovered: true`，当前会话直接观察的记录不带该标记，使服务端优先采用活动中的直接观察，而非其他上报端读取的更晚元数据。上报端写 `hello`、`sessions`、`events`、`bye`；服务端可回 `ack`、`error`。版本 1 预留的 `prompt` 回复仍未实现，且控制不使用它。分帧只按 LF，并容忍尾部 CR。结果事件的 `text` 为原始 Markdown，可带 `toolName` 和 `truncated: true`。追加式 `events` 记录按完整事件拆成每帧最多 1 MiB 的批次，上限包括 JSON 转义和末尾 LF；不会为适应帧大小而拆分、压平正文。替换式 `sessions` 快照仍使用独立的 65,536 字节生产端预算。若完整身份字段导致单条事件无法装入一帧，该事件不会发送，命令会显示帧上限错误。

控制使用版本 2，走同一监听面上的独立连接。`control-hello` 携带上报 token、协议版本、机器名与当前 Pi 会话身份，因此同一机器上的两个 Pi 会话是两个可区分的 Console。desk 返回一次性 `hmac-sha256` challenge；证明内容把 `open-deskos-control-v2`、版本 `2`、nonce、机器名与 Console 会话 ID 以换行分隔的 UTF-8 文本绑定起来。独立 Control Credential 只作为 HMAC 密钥，绝不上线。每个请求都有 `requestId`，变更请求另有可用于重试对账的稳定 `mutationId`，保持连接的 attach 流量带 `attachmentId`，会话日志事件带物理 `position`。list / launch / history 为一枪式连接，attach 才保持连接。desk 不接受的版本会先明确报错，不会伪装成凭据错误。规范 fixture 随包位于 `fixtures/control-v2.json`。没有 detach 记录、没有重放窗口、也没有 resync 记录。

## License

MIT