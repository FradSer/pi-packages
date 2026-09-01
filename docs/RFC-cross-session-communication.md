# RFC: 沿用 agent-teams 机制的 Pi 跨 Session 纯点对点通信 (Direct Cross-Session Messaging)

## 1. 核心设计原则 (Core Principles)

1. **破除一切中间抽象（No Room / No Session History）**：
   - A 与 B 交流，自然形成协作流；B 与 C 交流，自然形成另一个协作流。
   - 收发的消息直接注入各自 Session 的对话历史，**上下文就是历史**，无需额外的 `session_history` 查询工具。
2. **完全复用 `@packages/agent-teams` 已验证的文件通信范式**：
   - 复用 `inbox-*.jsonl` 的 Append-only 邮箱；
   - 复用 `readJsonlBatch(file, byteOffset)` 的增量字节偏移量消费与消息 ID 去重；
   - 复用 `pi.sendMessage(..., { deliverAs: "followUp", triggerTurn })` 的上下文注入与 `FollowUpQueue` 排队调度机制。
3. **从“单 Team 封闭”走向“全局会话互联”**：
   - 现有的 `agent-teams` 作用于同一个 Leader 派生的 Worker；
   - 本方案将其泛化为：**面向任意独立终端启动的平级 Pi Session 的点对点通信扩展**。

---

## 2. 物理架构与存储布局 (Architecture & Storage Layout)

直接复用并扩展 Pi 既有的文件存储规范：

```text
~/.pi/agent/
  ├── directory-sessions/             # [已存在] 全局活跃 Session 注册表 (utils/sessions.ts)
  │     └── --path-to-cwd--/
  │           ├── 01a05c52.json       # 记录 sessionId, name(@alice), pid, cwd, status
  │           └── 01a04457.json       # 记录 sessionId, name(@bob), pid, cwd, status
  │
  └── mailboxes/                      # [新增] 沿用 agent-teams 规范的全局邮箱目录
        ├── inbox-<sessionId_A>.jsonl # A 的专属追加写收件箱
        └── inbox-<sessionId_B>.jsonl # B 的专属追加写收件箱
```

---

## 3. 沿用自 agent-teams 的核心机制实现 (Mechanism Inheritance)

### 3.1 发件机制 (`session_send` 写入端)
参考 `agent-teams` 中 `appendInboxMessage` 的实现：
- 发送方通过 `directory-sessions` 校验目标 Session 是否存活（`isProcessAlive(pid)`）；
- 直接以追加写（`fs.openSync(..., "a")` + `fs.writeSync`）方式向目标邮箱 `inbox-<targetSessionId>.jsonl` 写入单行 JSON：

```typescript
export interface PeerInboxMessage {
  id: string;              // UUID
  from: {
    sessionId: string;     // 发送方 Session ID
    name: string;          // 发送方别名 (@alice)
  };
  to: string;              // 接收方 Session ID
  timestamp: number;       // 发送时间戳
  body: string;            // 消息正文 (提示词/对话/下棋走法/代码)
  replyTo?: string;        // (可选) 关联的上一条消息 ID，用于链式追踪
  expectReply?: boolean;   // (可选) 是否期待对方自动触发下一轮回复 (默认 false)
}
```

### 3.2 收件与增量消费机制 (`readJsonlBatch`)
完全沿用 `agent-teams` 的 `readJsonlBatch`（`packages/agent-teams/src/statefile.ts`）：
- 接收端在后台轮询或监听自己的 `inbox-<mySessionId>.jsonl`；
- 维护上次读取的字节位置 `byteOffset` 与已见过的 `messageIds` 集合；
- 每次只读取增量字节块，按 `\n` 切分出完整记录并解析，自动跳过残缺未完结的行；
- 自动更新 `byteOffset`，实现**低开销、零锁竞争、幂等去重**的增量消费。

### 3.3 消息注入与排队调度 (`FollowUpQueue`)
完全沿用 `agent-teams` 的 `FollowUpQueue`（`packages/agent-teams/src/follow-up-queue.ts`）与 `pi.sendMessage` 范式：
- 收到消息后，将其排入 `FollowUpQueue`，由队列统一调度；
- 调用 Pi 标准 API 将其作为格式化的自定义消息注入上下文：

```typescript
pi.sendMessage({
  customType: "peer-message",
  content: `<agent-message from="@${msg.from.name}" id="${msg.id}">\n${msg.body}\n</agent-message>`,
  display: true,
  details: msg,
}, {
  deliverAs: "followUp",
  triggerTurn: Boolean(msg.expectReply),
});
```

* **历史自动归档**：注入成功后，该内容自然成为当前 Session 的对话历史，模型后续轮次天然可见，无需任何专门的 history 查询接口。

---

## 4. 极致收敛的工具面 (Ultra-Minimal Tool Surface)

系统仅向 LLM 暴露 **2 个最纯粹的原生工具**：

```typescript
/**
 * 1. 发现当前活跃的会话
 */
session_list(): Array<{
  sessionId: string;
  name: string;        // 别名，如 "@backend"、"@bob"
  cwd: string;
  status: "idle" | "busy";
}>;

/**
 * 2. 给指定会话投递消息
 */
session_send(params: {
  to: string;            // 目标会话别名 (@bob) 或 sessionId
  message: string;       // 消息内容 (普通文本、代码 diff、象棋着法等)
  replyTo?: string;      // (可选) 回复的上一条消息 ID
  expectReply?: boolean; // (可选) 是否期待对方收到后自动应答 (默认 false)
}): { msgId: string; status: "queued" };
```

---

## 5. 各种协作场景的自然展开 (Use Cases)

### 5.1 场景 A：日常跨窗口协同答疑
- **前端 Session**：
  > `session_send({ to: "@backend", message: "登录接口 token 字段改叫什么了？", expectReply: true })`
- **后端 Session**：
  > 收到消息，自动唤醒一轮：`accessToken`
  > `session_send({ to: "@frontend", message: "改叫 accessToken 了" })`
- **前端 Session**：
  > 收到回复，直接呈现在对话上下文中。

### 5.2 场景 B：双 Agent 下象棋 / 回合制对弈
- **Session A（白方）**：
  > `session_send({ to: "@bob", message: "我走了 e2e4，当前局面 FEN: rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1。轮到你了。", expectReply: true })`
- **Session B（黑方）**：
  > 收到包含 FEN 与走法的消息，自动唤醒，结合自身上下文计算出下一步：
  > `session_send({ to: "@alice", message: "我应了 e7e5，当前局面 FEN: ...。轮到你了。", replyTo: "...", expectReply: true })`

双方在各自的上下文里自然推演棋局，无需外部房间或中心仲裁。

---

## 6. 防死循环与安全熔断机制 (Safety Circuit Breaker)

多 Agent 跨会话自主通信必须具备物理层面的防无限循环机制：

1. **默认人工参与 (Human-in-the-Loop by Default)**：
   - 若 `expectReply: false`（默认值），收到消息仅在 TUI 显示，不自动唤醒模型，等待人类按 Enter 继续。
2. **沿因果链的步数硬熔断 (Hop Limit)**：
   - 消息内部沿 `replyTo` 链路隐式累加 `hopCount`；
   - 当连续自动来回超过上限（如 30 回合）时，强制将 `triggerTurn` 降级为 `false`，并在 TUI 输出提示，要求人类接管，防止 Token 无限消耗。
3. **单飞保护 (In-Flight Guard)**：
   - 接收端若正处于 Agent Turn 或 Tool 执行中，到达的 Peer 消息在 `FollowUpQueue` 中排队，当前轮次完全结束后才作为下一轮 `followUp` 注入，杜绝并发抢占。

---

## 7. 实施计划 (Implementation Roadmap)

| 阶段 | 目标 | 涉及模块与交付物 |
|---|---|---|
| **Phase 1: 基础设施迁移** | 复用 `agent-teams` 的 `readJsonlBatch` 与 `directory-sessions` 注册发现机制 | 新建 `@fradser/pi-session-bus`，实现邮箱目录管理与 `session_list` / `session_send` 工具 |
| **Phase 2: 队列与注入** | 复用 `agent-teams` 的 `FollowUpQueue` 实现消息排队与上下文安全注入 | 完善增量文件监听、去重、`FollowUpQueue` 调度与 TUI 自定义消息渲染 |
| **Phase 3: 熔断与安全** | 引入 `hopCount` 自动应答计数限制与单飞保护 | 30 步连续自动触发熔断器、单飞防竞态机制 |
