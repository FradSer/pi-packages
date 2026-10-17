# Matt Pocock 构造场景与真实模型验证

确定性与原生运行基线日期：2026-10-03；真实模型扩展验证：2026-10-04。Pi CLI、包内 `pi-ai`、`pi-coding-agent`、`pi-tui` 均为 **1.0.0**。

本轮新增 **29 个参数展开后的构造场景**，测试先复现失败，再修复并回归。覆盖当前目录的所有条目及转换边；这不表示穷举任意输入、调度时序或下游业务结果。

## 已复现并修复

| Given / When | 修复前观察 | 修复后的约束 |
| --- | --- | --- |
| A 的菜单等待期间，A 结束并启动 B，再返回旧选择 | 旧 Complete/Transition 可以操作 B，旧路由选择可以覆盖 B | 关闭旧菜单，按打开时的工作项校验选择 |
| 菜单已返回选择，两个微任务之间替换 A→B | 4 条记录，最新 B 为 completed | 校验后同步调用选中动作；3 条记录，B 保持 active |
| 选择器或自定义输入等待期间，流程完成、转换或切换会话 | 未及时中断等待，需要迟到回答才能结束 | 向等待中的 UI 传播 AbortSignal，立即返回 pending/aborted |
| 输入 `complete unexpected` | 将控制命令误当作新任务，取消旧流程并投递路由提示 | complete/status 的额外参数报告用法，保留原工作项 |
| 提供字面选项 `Type custom answer...`，或包含空白的推荐标签 | 字面选项被识别为自定义输入；合法推荐被拒绝 | 自定义入口使用不冲突的标签，优先匹配完整原始标签 |
| 投递记录含旧别名、重复项、未知 ID，或旧状态没有投递字段 | 重复投递正文；缺少字段可能导致迭代错误 | 规范化为现存 canonical ID，兼容缺少投递字段的旧记录 |
| 转换传入正确程序但错误 phase 的状态 | 当前 phase 未被校验 | 转换前校验程序在路由中的位置与 phase |
| 原生适配器收到非 JSON，或 timeout 为 Infinity/超过 Node timer 上限 | 泄漏 SyntaxError；Infinity 被接受；超限 timer 可能约 1ms 结束 | 受控解析错误，在启动子进程前拒绝非法 timeout |

原生测试还覆盖 null、缺失或错误类型字段、未知按钮、多项列表、无效按钮配置、取消与真实进程失败的区别，以及 spawn 前后 abort。这些异常返回使用替代 `osascript` 进程构造。

## 目录及边界覆盖

| 范围 | 已验证内容 |
| --- | --- |
| 56 个资源 | 正文可加载、requires 闭包顺序及去重、大小约束 |
| 3 个别名 | 别名、`.md` 后缀和两端空白规范化 |
| 68 条披露关系 | 每条关系均可通过参考解析器访问 |
| 5 条路由、28 个程序位置、57 条合法转换边 | 合法目标通过；每个位置的非法目标必须抛错且不改原状态 |
| 21 个独立能力 | 13 个模型入口、8 个用户入口；独立能力不污染工作流状态 |
| UTF-8 边界 | 多字节正文恰好 65,536 字节通过，增加 1 字节拒绝；修改只发生在临时包副本 |
| 会话记录 | 最新异常记录不复活旧 active；完成、取消、版本、phase、reference、procedure 异常恢复 |
| 参考读取兼容 | 可只读用户入口能力披露的参考正文，不启动该能力根、不写工作流、不激活工作流工具；直接模型启动用户入口能力仍拒绝 |

用例分别位于 `test_adversarial_gateway.py`（16）、`test_adversarial_decisions.py`（7）、`test_adversarial_resources.py`（6）。目录用例从 manifest 生成，新增条目会自动进入检查。

## 验证结果

- 完整包测试：**158 passed**。
- 无实现历史的独立复审：新增 **29 passed**；`CI=true` 下原生/问答 **7 passed**。
- `pnpm typecheck`、`pnpm check:install`、包的 `pack --dry-run`：通过。
- 更新后的所有 TypeScript 夹具严格 Pi v1 API 检查与包内依赖解析：**2 passed**。
- 实际 Pi 工具矩阵：**271 次工具执行，3 个预期拒绝**；重启、原生树切换和原生会话压缩通过。
- 实际 TUI 命令矩阵：**26 个入口**（21 个能力、5 条路由），每轮均有程序投递和 agent_end 证据，**26 个进程均正常退出，exitCode=0**。
- 实际 TUI：选项、自定义输入、取消、超时、View/Transition/Cancel/Complete、Escape、Ctrl+O、48 列窗口、AbortSignal，以及旧问题/旧菜单与替换状态的竞争检查通过。
- 实际恢复边界：完成、取消、错误版本、错误 phase、非法 reference、非法 procedure 共 **6 类**通过。
- 实际 macOS `osascript`：列表、输入、提示超时及列表 abort 共 **4 类**通过。

### 真实 Pi 路径与 literal RPC 计数

以下两组是本轮在当前工作区实际执行的精确入口；没有重复计入前面的单元测试或旧 reference 矩阵：

```text
python3 packages/matt-pocock/tests/live/runtime_live.py
```

这次完整 Pi v1 矩阵报告了：

- **21 个 standalone roots**，其中 **8 个 user-only roots**；
- **122 条 standalone reference 路径**，每条路径使用独立临时 session；
- **268 次 standalone reference load**，包含 direct/transitive disclosure chain 和 `requires` closure；
- **28 个 workflow placements**，拆为 **43 个 direct reference load cases** 与 **3 个无 disclosure placement cases**；
- 额外覆盖合法 `CONTEXT-FORMAT` alias，并在每个 case 的持久化 Pi `toolResult` 中检查 canonical `<procedure-source>`；
- 同一完整 invocation 还通过了 **271 次真实工具执行、3 个预期拒绝、restart、RPC tree/compact，以及 26 个 native TUI command 入口**。

literal command 组使用如下等价的 targeted invocation，避免重新运行上面的 disclosure 组：

```text
python3 - <<'PY'
import shutil, tempfile
from pathlib import Path
import sys
sys.path.insert(0, "packages/matt-pocock/tests/live")
import runtime_live
pi = shutil.which("pi")
assert pi
with tempfile.TemporaryDirectory(prefix="matt-pocock-literal-final-") as directory:
    runtime_live.run_literal_commands(pi, Path(directory))
PY
```

literal 组使用 **8 个 fresh RPC sessions**：

- **2 literal cases**：inactive/freeform/alias routing 与 active supersession；
- **3 control cases**：legal transition、bad target、missing target UI cancel、complete/cancel/end；
- **3 menu cases**：workflow route、standalone capability、Escape/View/StartTask；
- 每个会 turn 的 case 都等待 RPC `agent_end` 和 evidence 中对应 PID 的 procedure；no-turn control 只等待 RPC response，并检查 notify 或 `extension_error`；
- 最终输出为 `literalCommandCases=8, literal=2, control=3, menu=3`。

这些 invocation 使用真实安装的 Pi v1 CLI 加载真实 `matt-pocock` extension、schema、command registry、session persistence、active tool loadout、RPC UI request/response 和 lifecycle events。模型 transport 是测试夹具中的**本地确定性 provider**（由 `PI_RUNTIME_CALLS` 驱动），因此这些结果证明 Pi/extension/runtime 行为，不代表外部模型质量或真实模型调度结果。

实际命令矩阵曾在初始化等待屏幕 READY 标记时超时，完整包测试同时运行时耗时也明显增加。该次超时没有定位为生产扩展缺陷。检查脚本现按 PID 和文件中的 `session_start → agent_end → procedure → agent_end` 同步，保留有界等待和具体命令/阶段/退出状态诊断，退出使用 Pi 的 `/quit`。修复脚本的首轮运行还暴露了尚未创建的证据文件问题；处理缺失文件、初始事件基线和 PTY 读取边界后，完整矩阵通过。

## 实测范围

Pi 检查使用隔离 HOME/settings、允许列表环境变量与确定性本地 provider，不继承模型凭据。工具执行、持久化、TUI、树切换和压缩由真实 Pi 完成；压缩摘要由夹具提供。竞争检查通过注册的处理器注入状态变化，不能据此推断真实模型调度的所有并发时序。

原生 JSON/异常与 CI 场景使用模拟环境和替代子进程；真实 macOS 检查覆盖超时及 abort，未自动点击按钮或验证物理显示。这些确定性检查不调用外部模型；下面的独立矩阵实际调用外部 provider。

## 真实模型调用与产物回归（2026-10-04）

真实 Pi 1.0 CLI 加载生产 extension，调用本机配置的 `opencode-go / space-bunny-free`，thinking 为 **off**。用例包含 21 个独立能力、5 个工作流入口、自然语言路由，以及额外的 scope-creep 审查回归，共 **28 项**。这是每个入口的具体 receipt 项目任务；不等于穷举任意业务项目或所有模型输出。

每项使用独立临时项目、HOME 和 agent 目录。认证副本权限为 0600，仅 provider 使用，结束后移除。模型文件工具被限制在项目内；固定测试在 macOS sandbox 内执行，禁止外部文件、网络和验收文件写入。父进程独立执行固定验收、核对测试字节与权限、检查实际工具结果和模型上下文中的 procedure source，不以模型自述或 CLI 退出码代替验收。

### 实际发现与修正

| 真实调用中的问题 | 修正和复核目标 |
| --- | --- |
| domain-modeling 在 glossary 中写实现路径、code/spec divergence、Open questions，并断言尚未决定的舍入规则 | glossary 只记录已确定的术语；实现诊断与未决政策放在独立说明中 |
| hard-bug review 承认 `quantity ?? 1` 超出 spec，却以“不影响场景”支持 Spec PASS | unresolved scope creep 阻止 Spec PASS；增加初始/最终测试全绿但应 REWORK 的独立审查案例 |
| questionnaire 把目标行为写成当前实现，且合并独立决策 | Context 区分已观察事实、目标与未决事项；每道题只问一个独立决策 |
| prototype 用浮点实验推出“必须逐行舍入”的业务策略 | 报告区分 measured results 与生产建议，未测试的业务规则保持未决 |
| codebase-design 将 spec 未说明的“禁止逐行舍入”写成已有约束 | 对比方案区分 sourced requirements 与 proposed invariants；未证实的约束标为假设或待决定事项 |
| recommended 漏掉 options 中的 `(Recommended)`，连续遭拒 | schema 说明要求完整复制 options 标签；保留严格不匹配拒绝 |
| domain-modeling 用 `mode: workflow` 加 capability，连续发生 schema error | 网关给出三种模式的精确 JSON 示例，并明确 capability 不能作为 route |

修正前的五份实际语义产物保留于 [`fixtures/real-model-semantic-red.json`](../fixtures/real-model-semantic-red.json)。其中旧 questionnaire 是首轮报告保留的末尾 4,000 字符；旧 hard-bug 保存了 review 中记录的默认值，没有保留源文件全文。新报告最多保留每份产物的前 64 KiB，并记录完整字节数与 SHA-256。

首轮 27 项自动验收的 3 个失败还暴露了测试脚本误判：merge 被额外要求执行冲突文件得到模型 RED、retro 被要求使用不属于任务的字面关键词、自然路由的扁平状态没有被识别。修正后这 3 项复跑符合预期；merge 的独立初始 RED 与最终 GREEN 保留，普通诊断/TDD/hard-bug 仍要求模型 RED → GREEN。

独立复审另复现并修复测试脚本的 symlink 验收文件绕过、漏检新增源文件、pending 汇总为 passed、pending 不检查负向 sandbox probe。正负 probe 均通过后才启动模型；未配置 provider/model 时停止，不选择隐含模型。`awaiting_user` 保持待回答状态，预期的 pending 检查退出码为 0。对话题、setup 和教学的待回答状态不表示相应任务已经完成。

术语表修正后的首个完整矩阵仍生成了 `Open questions`。随后进一步收紧指引，移除了会暗示这些章节的检查措辞。单项重试还出现过空 finalText、零 usage、没有 Matt 调用的失败；该次不计通过，也未产生修正后的业务产物。测试脚本现将 observer 的 agent_end 错误诊断写入报告，并在实际 provider failure 时停止后续案例。

最终候选采用如下完整调用，逐项保存清理后的证据：

```text
python3 packages/matt-pocock/tests/real_model_live.py --all --output /tmp/matt-pocock-real-final.json
```

这次 28 项完整运行用时 **1,452.70 秒**，产生 **19 项产物通过、8 项待回答、1 项术语表失败**。后续只重跑受影响的 `cap-domain-modeling`、`cap-codebase-design`、`user-improve-codebase-architecture` 和 `route-triage`。实际 Pi 将主动 abort 报为 `stopReason: error / This operation was aborted`；分诊复测确认该诊断在已记录问题并由脚本发起 abort 时属于预期等待，其它 provider failure 仍拒绝。

逐项取最终验证结果后：**20 项产物验收通过、8 项按预期待回答、0 项失败**。总体保持 `awaiting_user`。完整记录（包括此前失败尝试、实际调用参数、原始 abort 诊断、产物全文/字节数/哈希和独立验收结果）见 [`real-model-results.json`](../real-model-results.json)。最终源文件与 procedure 候选指纹为 `856246ebd7fcf3f1dc136b1bb86ac9991b4991d67df44aee600e5d665491b207`；完整运行的初始指纹及过程中两处指引收紧在该记录中单独说明。

| 真实模型入口 | 案例数 | 产物验收通过 | 按预期待回答 |
| --- | ---: | ---: | ---: |
| 模型可调用独立能力 | 13 | 12 | 1 |
| 用户命令独立能力 | 8 | 5 | 3 |
| 工作流入口 | 5 | 2 | 3 |
| 自然语言路由 | 1 | 0 | 1 |
| 额外 scope-creep 审查回归 | 1 | 1 | 0 |

最终包测试 **190 passed**；最后收紧 provider-error 诊断后，受影响的 runner 回归 **18 passed**，并重新校验已保留的实际 Pi pending 诊断。`pnpm typecheck`、`pnpm check:install`、包 `pack --dry-run` 通过。与真实上游 checkout 比较也通过：**37 skills、25 selected、12 excluded**，远端 HEAD 仍为 `d81f3a183412e71a5b1e84ca21bc1a35eea03a60`。独立复审的 path guard、source-file 验收、pending 汇总和错误诊断反例均已修复。

收尾在当前最终候选上再运行 `python3 packages/matt-pocock/tests/live/live_smoke.py`：真实 Pi print、TUI、问答超时、Escape、Ctrl+O 展开和 48 列窗口均通过。这轮 smoke 使用独立 HOME 与本地确定性 provider；上述 28 项则使用实际外部模型。

真实模型只覆盖 receipt 临时项目中的规定任务；研究仅使用本地主来源，wizard 验证生成脚本的语法并遵照用例不执行交互向导。外部 publication、部署、远端 Git 写入和真实用户对待回答问题的答案不属于这轮验收。
## 开发者完整任务补充（2026-10-04）

随后新增并真实运行三个多轮开发任务：折扣功能到交接、异步缓存事故、配置清理及纠正复审。最终 3/3 通过，当前包 206 tests passed；详见 [DEVELOPER-JOURNEYS.md](DEVELOPER-JOURNEYS.md) 和 [developer-journey-results.json](../developer-journey-results.json)。此补充保留历史结果，不把此前入口矩阵计作本轮重跑。

## 能力路由补充（2026-10-07）

本轮修复了一个可发现性缺陷：8 个 `invocation: "user"` 的独立能力从未出现在 `matt_pocock_workflow` 的 schema 或注入的 guidance 中，因此用户说 "grill me" 时模型没有任何入口可路由。修复新增 `mode: "user-capability"`（enum 恰为这 8 个 id）与 guidance 中的 user-invoked 小节，并保持两个能力集合互斥：`capability` 仍拒绝 user id，`user-capability` 仍拒绝 model id。

真实模型证据使用本机 `cli-proxy / opencode/deepseek-v4.1-flash`。同一个用例 `user-grill-me-model-routed` 在两种源码下结果相反：有修复时记录 `{"mode":"user-capability","capability":"grill-me"}` 且 `errors` 为空；无修复时记录 `{"mode":"capability","capability":"grilling"}` 并因 `missing model context sources: grill-me` 失败。也就是说，缺陷形态是模型静默替换为兄弟能力，而不是报错。

全量扫描 **29 项**用时 **1,153.40 秒**，结果 **20 项产物验收通过、9 项按预期待回答、0 项失败**，总体 `awaiting_user`。当前候选指纹为 `8b1e6c770eccec3851a90ae9e84ac1e31e5e5f1b38ded77b2eb3ef4819bfa6d2`，按记录中已有的 `hashMethod` 计算；被取代的指纹与上一轮运行说明保留在 `previousFullRunCandidateSha256`、`previousFullRuns`、`previousRechecks` 中。

本轮首次扫描曾出现 3 项失败（`cap-pr`、`cap-wizard`、`route-hard-bug`），看起来像本变更引入的回归。对照实验否定了这一点：同一模型、同一用例，仅源码不同，有变更臂 6 轮 18 次用例运行失败 3 次，无变更臂 5 轮 15 次失败 1 次，Fisher 精确检验双尾 **p = 0.6074**，且 `route-hard-bug` 在无变更臂同样失败。结论是该套件本身存在逐用例的随机失败率，首次扫描的 3 项失败属偶发聚集；这一统计已写入 `real-model-results.json` 的 `flakiness` 字段，供后续读者区分真回归与随机失败。

本轮验证：包测试 **250 passed**；`pnpm typecheck`、包 `pack --dry-run` 通过；真实 Pi 运行矩阵 **280 次工具执行、4 项预期拒绝**；`tests/e2e/matt_pocock_grill_me.py` 的两个入口（菜单与模型网关）均 `completed`。仓库级测试 139 passed、2 failed，两项失败均由未跟踪的 `packages/bdd-jev/` 引起（不在 PUBLISH_SCOPE、无 git-agent scope），与本变更无关。
