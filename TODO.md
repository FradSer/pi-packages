# TODO: Project Memory DAG 架构重构方案

## 真实 Memory 闭环通过后的对照验证

- [ ] 通过后，再做小规模有无 Memory 对照，衡量正确率、重复错误、延迟和总成本。**一个闭环通过只证明这个场景可用，持续学习需要后续连续任务的证据。**

当前恢复运行固定 Pi 1.4、Luna 普通服务等级、原任务和原校验门槛；以下 DAG 草案不属于本轮改动。

## 背景与现状
当前 Pi 编码智能体采用 **“广播模型（Broadcast Model）”**：将所有项目记忆的元数据（文件列表、摘要）作为 `<project_memory_discovery>` 一股脑塞进系统提示词。这导致了约 500 ~ 1,000 tokens 的常驻开销，且随着记忆增多，存在上下文膨胀和指令冲突的风险。

**目标**：将 Project Memory 重构为 **DAG（有向无环图）**，转变为 **“拉取模型（Pull Model）”**，实现按需加载与冲突自动裁决。

---

## 一、 DAG 记忆图谱的设计模型

在 DAG 中，记忆不再是孤立的 Markdown 文件，而是具有明确拓扑关系的节点：

1. **节点（Nodes）**：
   - 每一个记忆条目（如 `.memory/decision_tui_render.md`）是一个节点。
   - 节点包含：核心内容、适用上下文（Tags/Triggers）、置信度/状态（Active/Deprecated）。

2. **有向边（Directed Edges）**：
   - **`supersedes`（取代）**：解决冲突。新决策指向旧决策，Agent 遍历时只读取叶子节点（最新决策）。
   - **`refines`（细化）**：从宏观原则推导出的具体实施细节。
   - **`depends_on`（依赖）**：当前记忆生效的前提条件（例如：“TUI 渲染规范” 依赖于 “pi-kit 基础架构”）。
   - **`contradicts`（矛盾）**：标记为互斥，强制 Agent 在推理时进行裁决。

3. **无环（Acyclic）**：
   - 确保记忆演进是单向的（时间箭头），不会出现 A 取代 B，B 又取代 A 的死循环。

---

## 二、 核心优势（为什么 DAG 是最佳实践？）

### 1. 极致的 Token 压缩（从 1000 降至 100）
- **现状**：系统提示词中硬编码了所有记忆的元数据。
- **DAG 方案**：系统提示词中只需保留一句极简指令：*“在遇到复杂决策前，使用 `query_memory_dag` 工具检索相关记忆图谱。”* 
- Agent 只在需要时，通过工具调用获取当前任务相关的子图（Subgraph）或叶子节点，**将常驻 Token 开销降至接近于零**。

### 2. 自动解决记忆冲突（Conflict Resolution）
随着项目迭代，必然会出现“新规范推翻旧规范”的情况。在 DAG 中，通过 `supersedes` 边，Agent 在遍历时会自动过滤掉被取代的旧节点，永远只采纳最新的叶子节点，避免大模型在相互矛盾的指令中产生幻觉。

### 3. 支持条件触发与上下文感知（Context-Aware Traversal）
可以通过给节点打上“触发标签（Trigger Tags）”。例如：
- 当 Agent 检测到当前任务是 `TUI 渲染` 时，自动激活 `tui` 标签相关的记忆子图。
- 当涉及 `子代理协作` 时，激活 `agent-teams` 相关的记忆子图。

---

## 三、 在 Pi 中的具体落地方案

### 1. 元数据声明（Frontmatter）
在每个 `.memory/*.md` 文件的头部使用 YAML 声明图关系：
```yaml
---
id: memory_042
tags: [tui, lifecycle, rendering]
supersedes: [memory_018]
depends_on: [memory_005]
---
# TUI 生命周期渲染规范
...
```

### 2. 构建索引与遍历工具（Traversal Tool）
提供一个内置工具（如 `memory_query`），接受标签或起始节点 ID，返回相关的 DAG 节点内容。
```javascript
// 伪代码：Agent 调用工具
await tools.memory_query({ tags: ["tui", "lifecycle"] });
// 返回：过滤掉被取代的节点，返回最新的叶子节点内容
```

### 3. 系统提示词瘦身
移除 `<project_memory_discovery>` 中的长列表，替换为：
> *“项目记忆以 DAG 形式维护。在开始复杂任务或遇到架构决策时，必须调用 `memory_query` 检索相关记忆，避免重复踩坑。”*

---

## 四、 潜在的代价与权衡（Trade-offs）

1. **多一轮工具调用的延迟**：
   Agent 需要先调用 `memory_query` 获取记忆，然后再执行任务。这会增加一次 LLM 的推理轮次（Turn）和几十毫秒的延迟。
2. **索引构建的维护成本**：
   需要在后台（如 Pi 启动时或文件保存时）解析所有 `.md` 的 Frontmatter，构建并缓存这个 DAG 索引。如果图结构损坏（如引用了不存在的节点），需要有降级策略（Fallback）。

---

## 五、 总结

将 Project Memory 改造为 **DAG 架构**，是将 **“静态上下文注入”** 升级为 **“动态知识图谱检索”** 的关键一步。它完美契合了大模型时代 **“System Prompt 极简，Tools 极智”** 的最佳实践，能够从根本上解决记忆膨胀和冲突问题。
