# Agent Teams 设计反思

后续规划：@SPEC-unified-work.md 与 @PLAN-unified-work.md 记录用户最新选择的三工具 interface，保留高级 Work 管理、常驻执行与自主 claim。下文关于两工具、移除 board 控制及未来扩展的建议是早期审查记录，不覆盖该选择。

## 结论

产品方向成立，但 `DESIGN.md` 还不是可以直接实施的完整协议。它准确记录了用户要什么，却把一些尚未解决的执行问题写成了「内部自动处理」。

最需要修正的不是工具数量或对象名称，而是三个问题：多 runtime 的写入归属、消息的因果关联，以及每次状态变化的授权证据。下面是审查建议，不表示已经实现，也不撤回用户已确认的产品决策。

## 应保留的决策

- Agent 是跨项目的持续身份；project Definition 是同一 Agent 的 specialization。
- 一个 Agent 可以并发承担多个 Work Item，每项工作使用隔离 Work Session。
- Agent Memory 在 Agent 自己的文件夹中，只沉淀可复用能力与方法；项目事实留在 Project Memory。
- 未知名字产生 Temporary Agent；leader 可以根据首次高质量结果自动决定 Promotion。
- `agent` 负责委派/工作控制；`agent_event` 是 Leader、Worker 和 Agent 间共享的通信工具，不属于某一个角色或 Definition scope。
- 执行工具可以不同，并按需渐进披露。通信可达性不等于工作状态变更的授权。
- 不实现后台 daemon；持久身份与存储不等于离线自主执行。

## 1. 小工具 schema 不等于简单 interface

证据：`DESIGN.md` 的 External interface。原审查按 Leader/Worker 分开的工具说明，已根据用户纠正改为委派接口与共享通信接口。

`agent` 的三个字段已经承担新建、唤醒、定向 steering 等不同语义。`agent_event` 的 status 又同时表达消息意图、工作完成和记忆提案。字段少，但调用者仍需要掌握隐藏的组合规则。

具体缺口：

- `work` 究竟是 Work Item、Work Session 还是 Assignment Attempt？它存在但 `prompt` 缺失时做什么？
- `name` 和 `work` 的当前 owner 不匹配时，拒绝、转移还是创建新任务？
- `completed` 发给另一个 Agent，表示向对方报告，还是结束当前工作？
- handoff 的 `accept`、`decline` 如何通过共享通信工具表达？
- leader 的最终 Promotion 决定如何从一次模型判断进入持久状态？
- verification、resource scope 和 Memory Proposal 的结构化数据从哪里来？

建议：保留两个工具，不再压缩字段，也不因审查就新增 `kind` 或 action 参数。先为每个合法组合写明「寻址对象、同步效果、待处理转换、下一执行者」。消息正文是内容，不应凭一句自然语言就改变 owner、权限或持久身份。缺失的控制信息可以由运行环境绑定或按状态提供最小结构，但不能消失在 prose 中。

`work` 必须确定一种语义。建议保留为稳定的 Work Item 引用，由 harness 解析当前活动 Attempt 并把 steering 绑定到该 Attempt 版本，而不是让模型追踪不断替换的 Process Incarnation；若无活动 Attempt、Agent 不匹配或版本已变化，则返回明确的未路由结果，不能静默选一个 Session。

### 通信不按 Leader/Worker 划分 scope

先前按「Leader 只有 agent，Worker 只有 agent_event」划分是错误的。Leader → Worker、Worker → Leader、Agent → Agent 应使用同一个 `agent_event` 通信 interface；Leader/Worker 是当前协作中的角色，不是不同通信系统。`agent` 对已有工作发送的 guidance 也应复用这条消息交付协议。

Leader 的发送身份可以只是当前 Pi session，不需要伪造 Worker Assignment Attempt。Worker 的结果提交则必须验证其 Attempt 和 Process Incarnation。共享的是通信能力与路由语义，不是所有状态变更权限。

`to` 省略时只能采用当前唯一绑定的回复路由，不能对 Worker 默认为 Leader、对 Leader 却猜测某个 Worker；不存在唯一回复路由时要求显式收件人。这项已补入设计，其他如 handoff 接受、Promotion 落盘等控制协议仍未闭合。

「一个工具」指一个共享通信工具，不是每个参与者只能使用一个工具。`read`、`bash`、外部工具及渐进能力发现仍有自己的执行 interface；如果能力请求也要走 `agent_event`，必须把这条转换明确写出。

## 2. 跨项目并发需要跨进程串行化，不需要 daemon

证据：`DESIGN.md` 的 Agent Directory、Work Session Runtime、Agent Memory、Runtime Coordinator 和 Storage ownership。

反例：Pi runtime A 和 B 同时使用同一 Agent，各自在自己的进程里运行「Agent-level serial reducer」。两者都读到记忆版本 7，分别写成版本 8。单个进程内部虽然串行，全局更新仍会丢失；两者还可能消费同一 inbox request 或同时 Promotion 同名 Agent。

建议：

- 每个 Work Session 有明确的 runtime owner；其他 runtime 不能同时接管。
- Agent 身份、Promotion、Agent Memory 和 inbox consumption 在共享存储的短事务内检查版本并提交。
- 原子文件替换保证读不到半个文件，不保证两个写者不会覆盖彼此。
- 请求、提交、接受和合并都有幂等标识；失效 runtime 的迟到写入必须被 generation/version 拒绝。
- 不做后台进程。没有 runtime 时，待处理工作保持等待；下次合法 runtime 取得执行权后才继续。

### inbox 到执行之间的崩溃窗口

空白审查补充了一个跨记录反例：消费 inbox 后、创建 Work Item 前崩溃，会丢工作；先创建 Work Item、后确认消费，重放时又可能重复建单。单独保证每个文件原子写入不能解决这个问题。

请求需要持久的关联标识，使 inbox receipt、Work Item 和启动授权可以在恢复时互相核对。相同请求重放应返回既有逻辑工作；启动前记录授权，启动结果不明时先协调核实，不能直接再启动一个写者。此处可以采用本地事务或可恢复的文件协议，不要求一个跨所有项目的大事务，也不要求 daemon。

应验证的是「一个逻辑 Work Item、一个有效执行授权、消息不丢失」，而不是宣称任意 shell 或外部请求都恰好执行一次。首版可先限定同一用户、同一机器，跨主机不作为隐含保证。

存储目录的具体拼写可以后定，但 writer 归属和跨进程互斥不能推迟为「实现细节」。

同时要区分三类信息：Presence 是可投影的状态，leader 工作结果是必须可靠交付的协调事件，用户通知才需要按重要性筛选。「减少打扰用户」不能变成「只把重要的 worker 结果交给 leader」，也不能要求 leader 调用有唤醒副作用的 `agent({ name })` 来轮询进度。

## 3. 按 Agent 名寻址还不足以隔离任务

证据：`DESIGN.md` 的 Product model、Shared communication 和 State contracts。共享通信的基本角色对称性已修正，但跨 runtime 的具体消息关联与消费协议仍须补齐。

反例：同一 `security` Agent 在项目 A、B 各有一个 Work Session。另一个 Agent 发来「这个问题已修复」。只有接收 Agent 名，无法确定这是给 A 的回复还是给 B 的新工作。把它交给「最新 Session」会泄漏项目上下文。

建议：所有内部消息保留 message id、可信的发送方 session/runtime 身份，以及必要的收件与回复关联。与具体工作相关的消息再携带对应 project、Work Item 和 Assignment Attempt；普通 Leader 消息不要求发送方拥有 Work Item 或 Attempt。消息可以引用目标工作，但引用不等于发送方拥有该工作的执行权。sender 的可信绑定解决「谁发的」，工作关联解决「这条消息属于哪件事」，两者不能混为一谈。

- 新 request 明确创建关联的协作 Work Item，保留原项目和授权范围。
- 回复使用 harness 提供的精确 reply route，不能依赖全局 Agent 名猜测。
- `to` 可以接受已披露的路由引用，不必因此增加一组常驻参数。
- 省略 `to` 采用唯一绑定回复路由；无路由或路由不明确时拒绝。这一规则已写入当前设计，不再采用「leader/current work」二选一。
- Agent 跨项目复用不等于消息、Presence 明细、历史证据可以跨项目自动注入。

## 4. 工作生命周期缺少关键中间状态

证据：`DESIGN.md` 的 External interface、Work Item 和 Agent Promotion。

文档写 Work Item 「恰好有一个当前 owner」，但排队中尚未分配、已完成、已取消的工作不应有活动 owner。应改为「至多一个活动 Assignment Attempt；只有已授权执行的工作才有活动 owner」。

其他需要补全的转换：

- `completed` 是结果提交，不直接等于验证通过。提交、验证、最终完成必须区分，并绑定同一证据版本。
- target 接受 handoff 前不能按普通新任务检查与 source 冲突的锁，否则会永远无法接受；应先准备 target，再暂停并确认 source 不再写入，最后原子转移。
- 每个 handoff offer 要绑定 offer identity、来源 Attempt、目标准备中的 Session，以及预期 ledger revision。接受只能作用于仍有效的 offer；来源已完成、转移或撤回后到达的接受不得改变 owner。重复接受返回已记录结果，不重复转移。
- steering 已完成 Work Item 不能顺手清除历史结果；新工作和有新 Attempt 的显式重开必须区分。
- 「完成」要有持久可检索的交付物。隔离 worktree 里的验证通过，不等于结果已经集成到用户工作区。

### 旧进程失效不等于旧 Attempt 失效

同一 Work Session 的进程 I1 被 I2 替换时，Assignment Attempt 可能仍是 A。因此只检查 Attempt A 仍活动，不足以接受 I1 的迟到 completion。

建议：可修改状态的事件必须同时匹配当前 Attempt 和已授权的 Process Incarnation；执行权替换时，存储中的授权版本原子更新，使旧进程携带的授权失效。新的 incarnation id 或授权 epoch 都可以承担这一职责，不必同时增加多个等价字段。对不再有权修改状态的事件保留历史证据，但不执行其状态请求。

验证者不是执行 Agent，其结果应绑定提交记录和被审查的成果版本，不能假装来自当前 worker；不同来源的事件各自检查对应授权。

### 无 daemon 时如何恢复

没有 daemon 不妨碍数据持久化，但不能只把旧 JSON 重新读入就宣称恢复完成。下次 runtime 取得工作前，应协调核实前一 runtime/进程是否仍拥有执行权，并把工作明确置于可恢复、已释放或待人工判断状态。

仅有心跳超时或模型沉默不能证明旧进程已停止，更不能直接授予新写者同一 workspace。存储层拒绝旧事件也不能停止一个仍在运行的 shell；复用资源前必须确认旧写操作已停下，不能确认时保持阻塞。外部操作结果不明时先核实，不能盲目重放。

这些是正确性的前提，不是实现后再补的异常处理。

## 5. Agent Memory 与自动 Promotion 需要防止全局污染

证据：`DESIGN.md` 的 Agent Memory、Agent Promotion 和 Storage ownership。

能力记忆可以来自项目实践：按内容和适用性归属，而不是按学习发生的位置归属。从项目中抽象出的通用方法、判断准则和可复用能力可以成为 Agent Memory；项目事实、具体决策和历史仍属于 Project Memory。原项目记录与独立的抽象经验可以同时存在，并不需要把前者迁移或复制给 Agent。

但「方法」也可能夹带项目事实或无依据的普遍化。例如「分析重试时先检查操作是否幂等」可以作为有适用条件的方法；某项目选用了哪个组件、为何上线以及当时发生了什么仍是项目内容。去掉项目名称不等于完成抽象，证据摘录也可能重新泄漏原始事实。

建议：

- Agent 文件夹只存泛化、可复用的方法及最小能力证据；原始轨迹与业务材料留在来源 Work Item/Project Memory。
- 「这是能力经验还是项目事实」属于语义判断，不能靠目录或 schema 机械保证；不能仅因经验来自项目就拒绝，也不能仅因删除了项目名就接受。合并前检查可复用性、适用条件、敏感内容和证据，不确定的原始经验留在来源项目。
- 证据引用仍受来源项目可见性约束；跨项目检索不得顺着引用自动注入原始材料。
- 项目 Definition 是 specialization，不是修改全局 Agent 方法、用户授权或其他项目习惯的许可。
- Promotion 保留 leader 的质量判断，不改成固定复用次数；但落盘必须有绑定已验证结果的决定记录，不能从最终答复里的赞美推断。
- 首次成功可以证明「这个 Agent 值得保留」，不证明「它的全部做法都应成为全局默认」。Promotion 和具体 Memory Proposal 的合并是两项独立转换。
- 同名并发 Promotion 应有一致的解析和冲突结果，不能让最后一个文件写入者决定身份。最终创建 user Agent 的操作必须检查名称占用及 Definition 版本；发生冲突时不覆盖现有身份，也不合并两份项目上下文。
- Temporary Agent 的创建条件统一为「请求名称没有对应的持久 user Agent」，有无 project specialization 都适用。持久化前的临时身份可以留在创建它的执行范围内，不必为了同名就把两个项目的临时上下文绑定成一个全局对象。

## 6. 渐进工具与 Computer Lease 不能冒充安全隔离

证据：`DESIGN.md` 的 Capability Resolver 和 Computer Lease Manager；当前 `src/spawner.ts` 和 `src/worktree.ts`。

当前 spawner 使用本机进程并继承环境；worktree 只是从 Git HEAD 创建另一份工作目录。这些实现能隔离部分上下文与文件修改位置，但不会阻止获得 shell 的进程读取宿主目录、调用外部命令或继续运行后台子进程。

因此必须区分：

- 工具是否对模型可见；
- 当前请求是否被授权；
- 执行环境是否强制限制了文件、网络和凭证访问。

同样，`DESIGN.md` 中「秘密永不进入 prompts」是目标，不是现有机制能够证明的绝对保证。运行时可以不主动注入凭据、限制可读路径、过滤已知敏感字段，但任意源文件或第三方内容仍可能含有未知秘密。设计应分别描述可强制执行的规则与语义识别的残余风险，不把后者包装成完全隔离。

Takeover 尤其不能只切换一个状态标记。已经启动的 shell、浏览器请求或子进程可能仍在写入。只有能阻断新写入并确认在途操作已停下的 adapter，才可以宣称安全转移控制；其他 adapter 只能提供真实的只读 Preview 或报告不支持 Takeover。

不必在首版建设云电脑平台，也不应把每个 Work Session 都强制变成 Git worktree。保留独立的 workspace authority，按工作需要选择已支持的环境形式。

## 7. 模块清单过度展开，交付步骤还不是纵向闭环

证据：`DESIGN.md` 的 Deep modules、Delivery slices 和 First implementation acceptance scenarios。

Agent Directory 同时拥有身份、Promotion、inbox 和 Presence；Runtime Coordinator 又消费 inbox、驱动执行、产生通知。这两个 module 的职责存在重叠。「Deep modules」只是标题，还没有证明 locality。

建议先收敛为三个主要 module：

1. **Agent Catalog & Learning**：身份、Definition specialization、Promotion、能力记忆。
2. **Work Coordination**：Work Ledger、消息关联、handoff、验证、执行归属与 leader delivery。
3. **Session Execution**：Pi session、Process Incarnation、有效工具、workspace 和执行事件。

存储与运行环境是内部 adapter；Console 是投影，不再成为一份状态真相。Memory merge 可以有独立的内部 seam，但不必为每个术语创建一个顶层 manager。

现有交付顺序先 Directory、再 Ledger、再 Runtime，直到第四步才有新工具；这仍是按技术模块铺开。首步验收却已经依赖第三步的并发 Session 和第五步的 Memory Proposal，存在明确的计划错位。

建议纵向顺序：

1. **一次委派闭环**：解析 Agent/Temporary Agent → 独立 Work Session → 一个结果提交 → 可检查的验证与交付物 → 自动返回 leader。
2. **并发与恢复**：两个 runtime 使用同一 Agent，分别执行项目工作；旧 Attempt/Incarnation 不得污染当前状态。
3. **协作闭环**：request → 精确 reply → accepted handoff；无需用户转发消息。
4. **学习闭环**：leader Promotion 决定 → user Agent → 独立记忆文件夹 → 一条可验证能力记忆 → 另一个项目只复用该能力。
5. **按真实需要扩展**：更多工具 adapter、受支持的 Preview/Takeover、runtime 内 Routine。

第一条委派闭环必须自带最小共享通信、基础工具授权、必要资源互斥、结果交付和 Attention 出口，不能等数个后续步骤补齐。每个可发布切片分别完成 BDD→RED→GREEN、测试与 typecheck、Changeset、安装检查和真实 Pi 演示；不是最后才验证新工具是否真的加载。

自动 Promotion 与能力学习仍是产品目标。把其完整执行安排在学习切片，区别于首个委派切片，并不意味着取消它们或把最终规则改成人工逐项批准。

## 文档一致性

- `CONTEXT.md` 应解释领域概念，`DESIGN.md` 应给出完整状态契约；审查中发现的建议不自动变成已确认需求。
- 审查发现前期架构 Canvas 曾提议每个 Coworker 共用稳定 Pi session，并把项目知识混入角色记忆。这些已被后续用户决策否定；本轮已将该页替换为当前设计反思，避免继续传播旧结论。
- `features/agent-teams.feature` 描述的是旧工具和旧生命周期。`features/shared-communication.feature` 与 `features/agent-memory-abstraction.feature` 分别记录共享通信和项目经验抽象的设计，带 `@design @unimplemented` 标记；没有对应实现或可执行测试，不应将它们当作已验证行为。

## 独立审查的取舍

两份定向审查及一份空白上下文审查已完成：

- 简化性审查确认工具协议未闭合、Directory 职责重叠、Promotion 提交途径不明，以及交付步骤与验收不匹配。
- 一致性审查确认消息关联、handoff 接受条件、旧 incarnation 授权失效、并发 Promotion 和 runtime 丢失后的恢复契约需要补全。
- 空白审查仅接收当前设计、领域词汇、ADR 和共享通信场景，未获此前讨论或审查结论；其报告声明未读取旧审查、Canvas、memory 或会话，只补读包内规则和 README。它独立识别出相同主问题，并补充 inbox→建单→启动的崩溃窗口、交付切片应自带基础授权/Attention、每片都要 live install 验证，以及秘密处理的绝对保证过强。它没有做 src 实现审计或运行测试。

不照单全收其具体改法：增加 `kind` 不是当前首选，也不直接删除用户已要求的每个 Work Session 独立 workspace authority。先保留两个协调工具与 Computer Lease 的归属语义，收窄它们能保证什么；只有实际支持的执行 adapter 才能提供相应隔离和 Takeover。

同时纠正报告中的两项过强表述：

- `DESIGN.md` 说没有 user Agent 的 project specialization 会产生 Temporary Agent，并没有说只有这种情况才产生。另一处又明确新名字先创建 Temporary Agent；这是表述覆盖不统一，不是逻辑上的互斥规则。
- `CONTEXT.md` 中「only when bound to the active Assignment Attempt」是必要条件，不是充分条件。不能由此推断旧 incarnation 必然被授权；真正缺失的是完整的执行权判定和替换协议。

空白审查建议推迟自动晋升执行和自动记忆合并，但这只作为分期建议记录，不撤回用户已选择的 leader 自动 Promotion 与能力学习目标。也不因为多个审查者得到类似结论就宣称方案已经验证；它们提供的是一致的反例和取舍分析。

这些都属于尚未实现的设计缺口，不能表述为已经复现的运行错误。

## 实施前的审查门槛

在以下反例有确定结果之前，不应宣布协议设计完成：

- 两个 runtime 同时消费一个 Agent request、更新同一条能力记忆或 Promotion 同名 Agent。
- 在 inbox 消费、Work Item 建立和执行启动之间逐点崩溃；恢复后不吞消息、不重复建单，也不产生两个有效写入授权。
- Leader 与 Worker 使用同一通信工具双向联系；Leader 不需要 Worker assignment，缺少唯一 reply route 的调用不猜测收件人。
- 同一 Agent 在两个项目工作，peer 回复只进入原项目对应 Work Session。
- source 交接时仍有写操作，target 此时接受或退出。
- 已完成工作收到旧 submission、旧 verify 结果或不明确的 steering。
- 一条声称是能力经验的记忆夹带项目事实或原始证据。
- runtime 退出后，等待的 request、Attention Request 和不可重复的外部写入各自如何恢复。

本次结论：保留 Agent-first 方向，减少过早拆出的 module，先补齐可验证的协议，再按委派、协作和学习三个用户结果闭环实施。
