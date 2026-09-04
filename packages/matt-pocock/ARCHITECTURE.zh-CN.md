# pi-matt-pocock 架构说明

`pi-matt-pocock` 将 [mattpocock/skills](https://github.com/mattpocock/skills) 中选定的工程方法适配为 Pi 的**目录驱动能力网关**。它不是上游仓库的完整镜像，也不把每份上游 `SKILL.md` 注册为 Pi skill。

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
version / workItemId / route / procedure / phase / status / loadedReferences
```

- `workItemId` 是每次工作流启动时生成的稳定 UUID，用于区分独立工作项。
- 活动记录的 `status` 为 `active`。
- 结束记录保留同一 `workItemId`，`status` 为 `completed` 或 `cancelled`；取消记录可包含原因。
- 状态通过 `pi.appendEntry` 写入 session branch。重启时只恢复最新的有效 `active` 记录；最新记录已结束时不会恢复旧活动状态。
- 恢复前会重新验证 route、procedure 与资源 bundle。无效的陈旧状态会被明确记录为 `cancelled`，而不是静默回退到 route 默认入口。

工作流启动、恢复或迁移时会返回当前 procedure bundle。之后每个 agent turn 只追加紧凑 guidance，包含 `workItemId`、当前阶段、合法下一步、可加载 reference 与终止责任，不会把整个目录反复注入 system prompt。

模型可以通过 `matt_pocock_active` 明确完成工作流；完成不再依赖用户进入菜单。用户仍可从同一 `/matt-pocock` 菜单迁移、完成或取消，作为显式控制入口。

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
npx tsc --noEmit -p tsconfig.extensions.json
pnpm --dir packages/matt-pocock pack --dry-run
```

需要核对上游 checkout 时再运行：

```bash
node packages/matt-pocock/scripts/check-upstream-sync.mjs --upstream /path/to/mattpocock-skills
```

## 与上游纯 skills 方案的差异

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
