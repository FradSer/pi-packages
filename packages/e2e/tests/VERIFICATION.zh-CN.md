# pi-e2e 真实验证记录

验证日期：2026-10-08（Asia/Shanghai）。范围：`packages/e2e` 全部实现、原生 Pi 接入、CLI、证据来源与 checkpoint、报告页面。已有的其他包工作保留；未提交、发布或修改生产服务。

## 修复与来源边界

两项用户指出的问题均以失败回归复现后修复：inline `fulfilled` 无法清除 checkpoint；失败 verdict 与 changed-feature 的项目/脚本/测试检查指令合并显示。

新增原生 `runner` 路径：命令必须匹配预先配置的 `.e2e/runner.json`，配置与 `adapterFiles` 在轮次开始时固定指纹。原生工具在启动前检查授权基线与轮次，运行成功后只读取本次私有临时目录中新生成的 Evidence。feature、adapter 或轮次变化会撤销证明；结束前重新验证已接受的场景，包括未修改但用户要求验证的 feature。变更 feature 的所有场景都需通过。

独立审查发现并修复：adapter 代码替换但配置不变的伪造路径、FIFO 阻塞、异步快照跨轮覆盖、未修改 feature 的旧证明未保留、最终 await 后仍启动过期 runner。另补充失败/取消/超时/输出限制/进程树终止、非 Error 取消原因、重复场景名与缺少 Then、非法 observations 等检查。

Inline/已有文件与 `/e2e` 保持内容评估能力，明确标记 acceptance unverified。可信 adapter 的完整依赖声明和业务测试质量仍由项目保证；插件不是自动业务覆盖证明，也不隔离任意恶意的预先存在测试代码。新增或更改 adapter 后需要新轮次。

## 最终验证

| 验证面 | 结果与证据 |
| --- | --- |
| macOS 完整包测试 | `uv run --no-project --with pytest python -m pytest packages/e2e/tests/ -q`：44 passed；Node 24.16.0 |
| Linux 完整包测试 | `node:24-bookworm-slim`，工作区只读挂载，`PI_E2E_NATIVE_TYPES=1 python3 -m pytest packages/e2e/tests/ -q -p no:cacheprovider`：44 passed；覆盖进程组取消与 FIFO |
| 相关仓库契约 | `tests/test_runtime_workspace_contracts.py tests/test_pi_core_cohort.py tests/test_publish_release.py`：35 passed；新增 Pi TUI peer 已修正为 `*` |
| 类型检查 | `pnpm typecheck` 与 `pnpm exec tsc --noEmit -p packages/e2e/tsconfig.json`：通过 |
| 打包 | `pnpm --dir packages/e2e pack --dry-run`：通过，包含 `src/run.ts`；`pnpm pack:check`：19 包通过 |
| 真实 Pi 循环，脚本 provider | `uv run --no-project python packages/e2e/tests/live_gate.py`：fresh fulfilled/verifiedRun=true/0 checkpoints；inline fulfilled/false/2 checkpoints；failed not_fulfilled/false/2 checkpoints。Pi 1.0.4 实际工具注册、参数校验、执行、settlement 路径，非真实推理模型 |
| 真实 Pi 推理模型 | `PI_E2E_MODEL=cli-proxy/gpt-6-luna uv run --no-project python packages/e2e/tests/live_model.py`：模型实际修改 feature、调用 runner 执行隔离 HTTP 测试，返回 fulfilled、verifiedRun=true |
| 真实 Jev API 与新鲜 HTTP 证据 | `pnpm exec tsx packages/e2e/tests/live_jev.mts`：jev-1.13.0；取货确认 fulfilled，条款 0.94、verdict 1.00；付款失败 not_fulfilled，条款 0.02、verdict 0.98。两次均有真实 runner 和真实模型调用 |
| 浏览器报告 | `node packages/e2e/tests/build-report.mjs` 生成 CLI 报告；`E2E_CDP_ENDPOINT=<隔离 Chrome endpoint> E2E_TELEMETRY_DISABLED=1 pnpm --dir packages/e2e/tests/e2e exec e2e run --no-cache --reporter list`：1 passed。实际 Chrome DOM 验证 4 个 Then 行、确定性 PASS、其他 UNJUDGED、needs_review、退出码及 gates；不是截图质量评估 |
| 真实交互 TUI | PTY 中启动 Pi 1.0.4，完成实际 runner 工具调用、通过通知、Ctrl+O 展开；执行 `/e2e test.feature evidence.json` 确认调用 cwd 正确且显示 caller-supplied/acceptance unverified。宽度回归使用 Pi TUI `visibleWidth`，不把 ANSI 字节数当终端列数 |
| 独立复审 | 不含实现对话历史的独立代理；最终来源回归 18 passed，未发现剩余可执行问题 |
| 内容检查 | `git diff --check`：通过；双语 README、feature 契约与 Changeset 已更新 |

核心覆盖还包括本地 HTTP provider 的 401/422/429/529/500、非法 JSON/模型答案、API 取消、CLI 0/1/2 与无效参数、HTML 转义、Gherkin 不支持结构、原型路径、确定性 veto 与概率/confidence gates。模型测试只证明这些已运行用例，不证明一般业务判断质量。

## 范围外结果与环境限制

- 广域 `pnpm check` 运行到 272 passed、3 failed 后中止；失败来自 `agent-teams` 的 coordination rows、task prompt wording、task structured schema，与本次 e2e 修改无关。不能报告全仓库绿色或完整执行了全仓库测试。
- 另一个已有失败：`tests/test_package_root_entry.py::test_git_agent_scopes_cover_the_current_package_layout`，当前 `.git-agent/config.yml` 的包范围不完整；该文件在本次开始前已修改，未覆盖用户工作。
- `pnpm check:install` 显示 10 个其他包未配置：agent-teams、btw、context、keyboard、monitor、plan-mode、recap、skill-router、utils、vision。e2e 不在缺失集合；未替用户安装其他包。
- 首次真实 Pi 模型调用使用默认 `opencode/space-bunny-free` 遇到 429，随后已配置的 `cli-proxy/gpt-6-luna` 成功；失败调用不计通过。
- Playwright Chromium 下载受环境影响未完成；实际浏览器验证使用单独临时 profile 的已安装 Chrome/CDP，未操作用户浏览器 profile。
- 测试只访问隔离本地 HTTP fixture 与授权的模型 API，没有验证真实 billing 产品、生产流程或 Windows 进程树。

TypeSafe API 契约已核对官方文档：<https://docs.typesafe.ai/api>、<https://docs.typesafe.ai/primitives/noul>。运行结果以本记录中的实测为准。

## 继续修复与最终门禁（2026-10-08）

用户要求继续，并明确选择保留当前全局安装、只修复代码和检查失败。本轮未修改 `~/.pi/agent/settings.json`，上述十项安装缺项按用户选择保留。

- 原先四项遗留失败均先复现，再修复：task 的 create 提示补上任务操作名且保持步骤/文件/轮次触发条件；coordination row 集成断言适配当前 `(in progress)` 展示；context 集成回归验证开放 schema 后由执行层拒绝 `handOff`、点名正确位置并保持 task 内容不变；补齐缺失包的 Conventional Commit scope，保留已有配置。
- 相关检查：coordination rows、prompt accuracy、structured schema、root entry 共 12 passed；task discoverability 6 passed；两个受影响包 pack dry-run 通过。新增 task 提示 feature 场景与 patch Changeset。
- `pnpm check` 的全仓库测试完整执行了 3,209 项，结果为 3,207 passed、2 failed，耗时 37 分 11 秒。两项新增失败位于 plan-mode 的真实 TUI 测试：测试看到模型 footer 后过早提交命令，Pi 返回 Startup is still in progress；并非业务 planner 失败。
- 修复该测试的同步条件：等待隔离 readiness extension 的 `session_start` 标记，再发送命令，没有增加固定延时或弱化选择/取消断言。真实 print 与两种 TUI implementation 选择重跑 3 passed。
- 之后在同一 `pnpm` 执行环境运行 `pnpm test --lf && pnpm typecheck && pnpm pack:check`：两项失败重跑通过、全仓库类型检查通过、19 包 packed manifest 检查通过。这里记录的是完整首次遍历加失败回归门禁，没有声称修改测试后再次完整执行全部 3,209 项。
- 真实 e2e Pi 循环再次验证：fresh 为 fulfilled / verifiedRun=true / 0 checkpoints；inline 为 fulfilled / false / 2 checkpoints；failed 为 not_fulfilled / false / 2 checkpoints，保留项目检查指令。

本轮发现的代码与测试失败均已修复。前述模型、浏览器环境及业务信任边界仍适用；未提交或发布。

## 独立 Docker 验证（2026-10-08）

用户授权用 Docker 单独验证。使用本机现有 Linux 基础镜像 `pi-reflection-fixes:20261008`（9f443f61ab8f），在新容器 `/work` 中复制当前源码快照，排除宿主机 node_modules、Git 数据与 .env。源码挂载只读；容器使用单独临时 Pi agent 目录，没有挂载用户主目录或改变全局安装。`pnpm install --frozen-lockfile` 在容器内重新安装 Linux 依赖；安装结束后断开 bridge 网络，测试仅访问容器内本地服务。

运行时：Node 24.21.0、Python 3.13.7、uv 0.8.22、pnpm 11.21.0、锁定的 Pi 1.0.0。Python 检查通过 uv 的离线环境执行。安装阶段 npm 连接重置经过重试恢复，不算测试通过证据。

此次独立验证额外发现并修复两个测试基础设施问题：真实 Pi 脚本无条件传入 Pi 1.0.0 不支持的 --no-mcp；取消测试的 PID 标记文件事件早于完整写入。前者依据实际 CLI --help 选择可用选项，增加两项版本回归；后者使用临时文件加原子 rename，并检查标记必须为有效正整数 PID。未弱化取消后进程退出或 checkpoint 断言。

最终整组命令（容器已断网）：

```bash
uv run --no-project --offline --python /opt/venv/bin/python3 --with pytest python -m pytest \
  packages/e2e/tests packages/tasks/tests packages/plan-mode/tests \
  packages/agent-teams/tests/test_coordination_rows.py \
  packages/agent-teams/tests/test_prompt_accuracy.py \
  packages/agent-teams/tests/test_tool_param_schema.py \
  tests/test_package_root_entry.py tests/test_runtime_workspace_contracts.py \
  tests/test_pi_core_cohort.py tests/test_publish_release.py -q -p no:cacheprovider
```

环境设置：PATH 优先 /work/node_modules/.bin；PI_CODING_AGENT_DIR=/tmp/pi-e2e-agent、PI_OFFLINE=1、PI_TELEMETRY=0、PI_E2E_NATIVE_TYPES=1。

- 最终 Linux 整组 **267 passed**，114.17 秒。日志：`docker-verification-20261008.log`。首次遍历为 264 passed、1 个取消标记失败；修复后完整重跑所选整组并加入两项 CLI 回归，全部通过。
- Linux 实际 Pi --print（脚本 provider）：fresh fulfilled/true/0 checkpoints；inline fulfilled/false/2；failed not_fulfilled/false/2，项目检查方向保留。
- Linux `pnpm typecheck` 与 `pnpm pack:check`：通过，19 包验证成功。
- 宿主机最终 e2e 完整回归：**46 passed**，11.29 秒；真实 Pi 三种 checkpoint 流程再次通过。

这是所列检查面的 Linux 独立验证，没有在 Docker 重跑全仓库全部测试，也没有在断网容器里调用真实外部模型。此前真实模型证据与业务 adapter 信任边界仍按前文说明。完成后只清理本轮创建的容器和临时脚本，保留基础镜像、用户全局安装和其他工作。


## 同轮验证重试与整包复查（2026-10-09）

本轮针对用户报告的“adapter 本轮变化，需要新轮次”拒绝与取消后的重复警告。此前记录中的 turn-start adapter 冻结已被本轮设计替代；历史验证记录保留，不作为本轮当前结果。

### 设计与覆盖

- 每次 e2e_verify 捕获当前授权配置和 adapterFiles，执行新进程；同轮修复后可以不限次数重试。自动催促仍限两次，不能代替工具运行。
- 单次执行前后核对 feature 和 adapter 指纹；新用户轮次拒绝过期 observer。WeakMap 证明只能由真实成功进程产生，inline/已有 evidence 不能解除运行验收。
- 本次 runner error 撤销旧通过状态并形成 needs_review 检查点。成功重跑清除同场景错误；无效场景名的错误可在正确调用后恢复，过期错误回调不能污染新轮次。
- 明确请求和泛化 E2E 请求均保留部分验证的 feature，全部场景通过才结束。根 feature 与嵌套 package 的实现编辑会失效旧验收，项目外编辑保持隔离。仅在 shell 中提到 feature 不算变更，真实快照和证明指纹决定是否失效。
- 意图初始化合并到 recordUserPrompt；beginTurn 不再覆盖“不运行”的指令，也不在异步捕获后重复清空状态。删除未被读取的 verdictInCurrentTurn 标记和整轮 runner 配置缓存。
- 工具默认完整显示报告、标题与错误，取消 100 行裁剪和展开依赖。检查点使用共享 pi-kit 行，展示路径、原因和实际额度；模型流程指令保留在上下文。正常未完成提示简化为 waiting，已报告取消不再追加通用警告。全部触发条件与示例见 ../TUI.zh-CN.md。

整包只读审查覆盖 src 的 parser、checks、questions、TypeSafe client、compose、verify、report、CLI、run、tool、presence、harness、types，以及入口、manifest 和文档。重点保留确定性 veto、概率/confidence gates、CLI 0/1/2、HTML 转义、来源证明、进程组取消、文件预算和会话竞态。没有把整个已有 dirty worktree 归为本轮修改。

RED 日志位于 /tmp/e2e-retry-audit/：red.log、red-read-only.log、red-generic.log、red-last-error.log、red-implementation.log、red-root-scope.log；red-full-feature.log 对本轮实施前备份验证完整请求与恢复缺陷。既有 repeated-settlement 回归还发现 shell 路径被误算进展，该断言继续保留；另一条旧测试改用实际 edit 事件授予第二次催促，仍断言二次额度与重复抑制。

### 当前门禁

- 宿主机完整包测试：70 passed，/tmp/e2e-retry-audit/verified-gate.log。
- 共享 pi-kit 与 workspace/cohort/publish 契约：137 passed，/tmp/e2e-retry-audit/shared.log。
- pnpm typecheck 与包 tsconfig：通过；final-typecheck.log、final-package-typecheck.log。
- pack dry-run 与 19 包 packed manifest：通过；final-pack.log、final-pack-check.log。新增 TUI.zh-CN.md 纳入包。
- 真实 Pi CLI 1.1.0：fresh、inline、failed、retry 四模式通过；final-native.log。retry 在一次用户输入中执行四次工具，实际结果依次为 not_fulfilled、fulfilled、fulfilled、fulfilled，每次 verifiedRun=true，最终 0 检查点。
- 真实 Pi 交互 PTY 1.1.0：80/40 列完整长标题与条款尾部可见；没有展开提示或通过后的 waiting；/tmp/e2e-retry-audit/final-tui/results.json。使用较高终端行数容纳 transcript，不声称物理终端滚动验收。
- 独立复审发现泛化请求部分场景、后续执行错误遗留旧 pass、根项目编辑作用域三项问题；全部修复。最终独立 13 项重试回归通过，未发现其余材料问题。
- 最终隔离 Docker（Pi 1.0.4）完整包测试：70 passed；四种原生 CLI 模式通过，正常 package 自动加载下同轮四次结果为 not_fulfilled、fulfilled、fulfilled、fulfilled，verifiedRun=true。配置只安装一个 E2E 扩展。收据：/var/folders/vn/whfnt01d4b19zg44txbtznbc0000gn/T/e2e-docker-2if5ornv/；verification.log、native-retry.json、autoload.jsonl。
- 最终 tarball 源码、feature、入口与 README/TUI 文档逐文件与当前工作区一致。E2E SHA-256：fe302044136b098e59c9585573aa88d643e04a7d26144673bb5874231095d176；pi-kit：59a6d77f051fbfbf2f04709a13764655ffebd108339626c7960a53b218382ee9。
- pnpm check:install：E2E 已配置，整仓检查仍因另 10 个包未安装而失败（agent-teams、btw、context、keyboard、monitor、plan-mode、recap、skill-router、utils、vision）；没有为通过检查修改用户全局安装配置。install.log。

修复前的真实项目 adapter 通过 e2e_verify 在同轮执行两次（project-dry.json），均有新测试进程及 verifiedRun=true，没有 turn-start 漂移拒绝。当时 run-feature-suites.mjs 只记录关联 pytest 结果，没有逐 Then 业务观察检查；offline 判断如实保留三个条款 unjudged 和 needs_review。这是修复前的历史结果，后续 Goal seed 观察链路修复见文末。不能把关联测试绿色自动转换为业务 fulfilled；脚本 provider/隔离 HTTP fixture 的 fulfilled 不代表真实业务语义已验证。

### Docker 方法与限制

新增 tests/e2e_docker.sh：打包当前 E2E 和必需 pi-kit，在 node:24-bookworm-slim 安装 Pi 1.0.4；运行配置只加载 E2E package，本地测试 provider 作为 fixture 显式加载。运行代码、feature、示例和 README 指向安装后的 tarball。静态 workspace manifest 与 AGENTS 检查使用只读来源文件；Goal/Tasks 只提供 parser 参考 feature，未安装或加载其运行扩展。pnpm override 指向打包的同一 pi-kit，避免注册表替换。

Docker 发现测试视图缺少 examples/AGENTS/LICENSE，已补齐；Linux kill(pid,0) 可能看见已经退出的 zombie，取消检查补充 /proc 的实际状态判断，仍拒绝可执行的活进程；容器启用 --init 回收子进程。没有削弱真实超时、取消或 fresh-proof 断言。只清理本轮创建的容器，保留收据与其他容器。

Pi 1.0 的 before_settle 正常时 ctx.signal 已为 undefined；用户恰在异步快照期间取消的窄窗口，公开事件不能可靠反映取消。本包检查可用 outcome/signal/待处理输入，但没有宣称该 SDK 限制已修复；该窄竞态只有源码证据，未做真实取消复现。Windows 进程树、真实浏览器报告和外部 Jev/推理模型未在本轮重跑。

Changeset：@fradser/pi-e2e patch。项目 adapterFiles 新增 test_retry_workflow.py，覆盖新声明的执行依赖。没有发布或修改远程分支；加载运行中的新实现需要重新加载 Pi。

## 再次 dry run 与整体反思（2026-10-09）

当前源码重新执行：包测试 70 passed（19.41s）；包 TypeScript 检查通过；真实 Pi CLI 的 fresh/inline/failed/retry 四模式再次通过；同轮 retry 四次调用保持 not_fulfilled → fulfilled → fulfilled → fulfilled，最终没有检查点。真实交互 PTY 的 80/40 列再次通过，标题和条款尾部默认可见，收据 /tmp/e2e-reflection-dry/tui-retry/。首次 PTY 尝试因宿主 Python 缺少 pyte 未完成；随后通过 uv 临时依赖环境运行，没有修改全局 Python。

真实项目 adapter 同轮重新执行两次：verifiedRun=true、needs_review、unjudged=3，原因仍为 no settled evidence for clause 1, 2, 3，详见 /tmp/e2e-reflection-dry/project.json。这证明当前执行路径允许重复验证，也证明目前项目 adapter 的输出不足以验收这些语义条款。CLI/provider fixture 的通过只能证明包的流程，不能填补真实项目的缺失证据。本轮没有调用外部模型或浏览器业务系统。

本次隔离 Docker（Pi 1.0.4）也重新通过：70 passed（24.56s），四模式原生 CLI 与正常自动加载同轮四调用全部通过；配置仅加载 E2E 扩展。当前 tarball SHA 与上一轮一致：E2E fe302044136b098e59c9585573aa88d643e04a7d26144673bb5874231095d176。收据 /var/folders/vn/whfnt01d4b19zg44txbtznbc0000gn/T/e2e-docker-Zo2V5zEE/。本次 pnpm pack --dry-run 与 git diff --check 通过。

### 整体职责

| 环节 | 当前行为 | 反思 |
| --- | --- | --- |
| 入口与请求 | e2e_verify 可执行 runner 或判断 evidence；CLI 和 /e2e 判断已有 evidence；harness 识别请求/变更 | 多入口有实际用途，但相同 verdict 不等于相同验收权。应让用户首先看到验收结果和证据来源。 |
| Gherkin | Feature/Rule/Background、唯一 scenario、Then 条款；不支持 Outline/Examples、表格/doc string，明确拒绝 | 当前是受限解析器，应保留清晰边界，不能宣传为完整 Gherkin 引擎。 |
| 执行与证明 | 项目授权命令、新进程、私有 evidence、前后指纹、进程取消、WeakMap 证明 | 必要的可信边界；重试必须放在两次执行之间，不能接受执行期间变化或用旧 evidence 补通过。 |
| 条款判断 | 精确检查先判断；未覆盖条款可交给 Jev；代码执行概率门禁；证据不足保留 needs_review | 确定性检查全覆盖时不调用模型，符合简单流程。needs_review 优先补观察、配置或可用判断能力，不应总被描述为实现错误。 |
| 验收收尾 | 工具每次验证一个 scenario；harness 聚合整份 feature；部分通过不结束 | 两种粒度容易误解。显式选择 scenario 是判断一个场景，整份 feature 变更仍需全部验收；后续应直接显示剩余场景名，避免用户反复验证同一个场景。 |
| 自动续跑 | 有缺失/失败与相关进展才继续；最多两次，泛化缺失请求一次；同状态不重复 | 上限约束自动催促，不能约束用户或模型主动调用。额度耗尽只意味着结束自动催促，不能推断通过。 |
| TUI | 完整工具结果、共享检查点、最终 waiting/通过通知 | 信息没有再被裁掉；成功工具报告后额外通过通知仍有重复，通知文案与 [e2e] 行尚未完全统一。后续应只在最终验收状态需要说明时通知，避免增加新的摘要层。 |

### 应继续简化的地方

1. 保留三件核心事实：待验收范围、每场景最近一次结果及证明、自动继续额度。verifiedInCurrentTurn、多个 modified/touched 集合与聚合缓存增加同步负担；若重构，应以现有恢复/部分通过/竞态回归为边界逐步归并，而不是新增状态机层。
2. 当前无法识别目标的 shell 调用会保守撤销已有验收，甚至纯读取命令也可能导致重跑；这会增加冗余。准确减少重跑需要已声明实现依赖与可观察变更证据，不能单靠命令字符串猜测，也不能只删除失效保护。
3. 真实项目 runner 尚未声明逐 Then 的业务检查。重复执行现有 adapter 不会凭空产生缺失证据。应由业务测试 adapter 产出对应观察和检查，再判断；不能给每个 Then 绑定同一个“pytest exit 0”。
4. 每次证明检查都重新读取 adapter 指纹，目录依赖会放大成本；只允许边界内短期复用，不能恢复整轮锁定或复用旧测试进程。
5. 运行错误、条款不满足、证据不足应分别指向“修复运行配置”“修复行为”“补充证据”。目前统一催促文字仍偏向 fix implementation；这是可读性改进方向，而非增加新的公开状态。

结论：同轮重试与来源保护已在本次实际重跑中成立；当前最大未完成点是项目业务证据适配，不是继续扩大自动催促。此次未改动运行代码；这些简化方向未被宣称已经实现。SDK 取消窄窗口、Windows 进程树、外部模型及真实业务浏览器验收边界沿用上节说明。


### 2026-10-09：Goal seed 观察链路修复

- RED：配置中的项目 adapter 运行成功、verifiedRun=true，但 Goal seed 三条 Then 都是 unjudged，最终 needs_review。回归为 tests/test_feature_adapter.py。
- GREEN：scenario-observation-map.json 绑定完整 Given/When/Then 与 Background；observe-goal-seed.mts 在独立临时目录中调用真实 /goal 处理器，观察初始状态、store.create 调用、持久记录、消息正文与 followUp/triggerTurn。完整正文使用独立认可契约检查，禁止仅靠引用存在就推断原话未被指定为 objective。
- .e2e/runner.json 登记生产者、绑定、测试及 Goal/pi-kit 源码依赖；运行使用 tsx，以保持 Node >=20 兼容。未绑定场景依然不声明 checks，绑定变化或生产者未登记直接拒绝证据；没有调整概率门槛。
- 反例覆盖：创建目标、创建后立即释放、直接发送原始 seed、附加“原话就是 objective”、只发送 transcript 消息均得到 not_fulfilled；未登记生产者及步骤变化拒绝产出证据。
- 最终完整 E2E 包测试 81 passed；pnpm typecheck、E2E tsconfig、生产者单独 strict typecheck、包 pack --dry-run、19 包 pnpm pack:check 均通过。独立复审确认观察语义与 pi-kit 来源登记缺口已修复，无剩余材料问题。
- 真实 Pi 1.1.0 --print 调用当前项目 adapter：fulfilled、exitCode=0、verifiedRun=true、unjudged=0，三条 Then 全部 met/deterministic/score=1。收据：/tmp/pi-goal-seed-evidence-native.json。模型由 scripted provider 驱动，工具与命令处理器执行真实，没有外部模型 API 调用。另有既有 live_gate.py 四种真实 Pi CLI 路径通过。
- pnpm check:install 仍因十个无关包未登记而失败：agent-teams、btw、context、keyboard、monitor、plan-mode、recap、skill-router、utils、vision；未修改用户全局安装配置。

## 修复全部可操作问题与 Goal seed 证据链（2026-10-09）

本节取代上节中“简化方向未实现”和“Goal seed 缺少三条证据”的当前状态描述；其他没有专属观察的场景仍然不能凭测试绿色宣称通过。Goal 源码未因本次 adapter 修复而改动；既有 dirty worktree 保留。

### 已实现

- 移除 verifiedInCurrentTurn 可变聚合标记，从真实验证结果集合推导状态，提供 isAccepted() 判断整份 feature。单次工具仍验证一个场景；检查点和 TUI 列出 Remaining 场景名。
- 已验证通过的完整工具报告不再追加成功 toast。纯 pwd 与限定选项的 git status 不撤销验收；其他未知 shell 命令继续保守失效，实际 adapter/feature 漂移仍在收尾检查。
- needs_review 方向改为补 missing observations or clause checks，或解决 runner/provider 问题；行为检查失败才要求修实现。未改变概率、confidence 或确定性 veto 门禁。
- 独立复查发现 refreshFeatureChanges 在没有新变化时清空重复抑制标记，已修复为只有实际漂移/旧证明失效才更新进展。真实 before_settle 钩子回归先 RED 后 GREEN：首次继续、无进展不再继续、有实际进展继续。原生 inline/failed 模式由两次无效催促变为一次；额度仍可留给后续进展。
- 非零 runner 退出现在附带 stdout/stderr 诊断，最多最后 8192 bytes，并明确标注超过预算时的尾部范围。原有 1 MiB 输出限制、超时、进程组取消和私有 evidence 清理保留，失败无证明。

### 真实 Goal seed 观察

项目 adapter 登记 tests/scenario-observation-map.json，并把登记文件、observe-goal-seed.mts 与 pi-kit 依赖纳入 .e2e/runner.json 的 adapterFiles。绑定完整 Given/When/Then 步骤，任何前提、动作或条款变化都必须更新 producer 契约。Producer 调用真实 Goal extension 注册的 /goal handler，在私有无 goal 会话中观察：没有创建记录；向模型发送一次编写 objective 的 followUp 请求并触发模型轮次；原词以转义引用传递而不直接作为 objective 提交。调用结束 shutdown 并删除本次私有目录。

测试不仅验证正例，还修改隔离副本中的真实命令：直接创建 goal、创建后释放、传递 raw seed、附加“原词就是 objective”指令、只写 transcript 不触发模型。所有五种变异都得到 not_fulfilled，证明检查会识别行为回归。未绑定的 suite 没有 checks；producer 未登记、Given/When/Then 不匹配会拒绝；false 观察值保持 false，不被 suite exit 0 覆盖。

当前真实项目 e2e_verify 同轮两次：fulfilled、verifiedRun=true、unjudged=0，全部三条 Then 为 met / deterministic；收据 /tmp/e2e-fix-all/project.json、project-verified.log。这只是该 Goal seed 场景的验收，不表示 Goal 整份 feature 或真实模型编写的目标已全部验收。没有降门禁，没有外部模型调用。

### 验证

- 宿主完整 E2E 包：82 passed（36.30s），/tmp/e2e-fix-all/host-verified.log。
- pnpm typecheck、包 tsconfig、pack dry-run 与 19 包 manifest 校验通过。
- 真实 Pi 1.1.0 CLI 四模式通过：fresh/retry 0 检查点，inline/failed 各 1；retry 同轮四次依次 not_fulfilled、fulfilled、fulfilled、fulfilled，所有调用有 fresh run proof。native-verified.json。
- 真实 Pi 1.1.0 PTY：80/40 列完整标题和条款尾部默认可见，无展开要求或通过后 warning，tui-final/results.json。
- 全部 37 个 E2E 场景与其测试引用已核对，git diff --check 通过。
- pnpm check:install 仍因另 10 个包未配置失败，E2E 本身已配置；未修改全局安装配置。SDK 收尾取消窄窗口、Windows 进程树与真实外部业务浏览器的未验证边界不变。

Docker 方法已扩展以验证实际项目 adapter：只安装/加载 E2E 扩展和必要 SDK/pi-kit；Goal/Tasks 源码作为测试 fixture 复制，不安装其扩展。复制测试树、固定 kit 依赖和 type=module 保证 Python 路径与 ESM 解析；不放宽符号链接安全检查。初次验收捕获了测试路径、软链接、ESM 视图与 Goal 入口缺失问题，已调整 setup。最终隔离 Docker（Pi 1.0.4）82 passed（35.33s）；项目真实 Goal seed adapter 也在该完整包测试中通过。四模式原生 CLI 及正常自动加载同轮四次重试通过。收据 /var/folders/vn/whfnt01d4b19zg44txbtznbc0000gn/T/e2e-docker-i1H1lr82/，verification.log、native-retry.json、autoload.jsonl。E2E SHA-256 99e0c57334866ddcee3bc18db2d364b6d32be994dcf1f8096679c2e2f9bbae22；kit SHA-256 59a6d77f051fbfbf2f04709a13764655ffebd108339626c7960a53b218382ee9。19 个打包运行源码/feature/入口/README/TUI 文件与当前工作区逐字节一致。

最终独立只读复查无新发现：adapter/诊断测试 12 passed；独立 20 KB 输出探针确认尾部预算、遗漏范围标记和实际诊断保留。最新项目配置的两个受影响回归再次通过，current-adapter-gate.log。Changeset 为 E2E patch；未发布、未提交，运行中的 Pi 需要 reload 才加载新逻辑。


### 2026-10-09：Goal 全量逐子句覆盖及旧契约迁移

用户明确选择以当前简化架构为准，迁移旧契约并保留覆盖记录。
原 106 个场景保存在 legacy-goal-scenarios.json；goal-scenario-migration.json
逐项说明保留、修订和撤销要求，独立审查已读完全部旧子句。
当前 Goal feature 有 179 个场景、718 条原子 Then，全部有完整步骤绑定。
观察器执行独立原生断言，记录实际/期望值、源表达式、哈希和调用次数；生产者拒绝
缺失、替换、额外或重复证据，不用 pytest 退出码推断子句。没有降低概率门槛。
显式 sync 生成器不参与验收；默认只读一致性检查通过，CI 同时检查冻结哈希。

RED：旧 Goal 缺少 105 个绑定，覆盖回归失败；独立审查发现一条恒真的
assert.equal(false,false)，新增检查亦失败。GREEN：改为恢复后真实 scheduler/status
检查，补齐有效要求，包括暂停修订的 pursuing footer、有效记录上的链接写拒绝、
claim/evidence 分离、报告转义、Markdown 空行、主体标题、单次结果、restore blocker
reset 和空工作等待。复查未发现新的具体阻断项。

最终稳定版本的实际验收：

- verify-goal-contracts.mts 执行配置中的真实 adapter，每个场景启动新测试和观察进程。
  179/179 fulfilled、718/718 deterministic met、零 Jev 问题、全部 fresh proof；
  最终 pendingCheckpoint=null。完整逐场景报告为 goal-coverage-report.json。
- 隔离 TMPDIR 的 Goal + E2E 测试：130 passed（128.20s）。其中 10 个观察/运行时
  mutation 回归覆盖缺失、增添、变换、重复、冻结哈希、false witness，以及真实
  symlink guard、报告转义和 executor claim 注入缺陷；均正确拒绝错误实现。
- 根 pnpm typecheck、Goal test tsc、E2E tsc、三个维护/验证脚本 strict tsc、
  git diff --check、默认 sync 一致性检查通过。
- pnpm pack:check：19 包通过；Goal/E2E dry pack 通过。
- macOS 原生 Goal CLI/TUI：complete/refuse/empty/error/blocked/long/cancel 通过。
  原生 E2E Pi --print 的 fresh/inline/failed/retry 四模式通过，重复修复验收无 checkpoint。
- Linux 打包隔离环境（Pi 1.0.4）：E2E 100 passed（75.41s），正常自动加载重试
  not_fulfilled→fulfilled→fulfilled→fulfilled，全部 fresh proof。
  Goal 四个行为 harness 及原生 CLI/TUI、正常自动加载 empty/long 通过。
  收据分别位于 /var/folders/vn/whfnt01d4b19zg44txbtznbc0000gn/T/e2e-docker-GYmqVkgd/
  和 /var/folders/vn/whfnt01d4b19zg44txbtznbc0000gn/T/goal-docker-Id5VfyZH/。

范围与限制：以上覆盖用户报告的 Goal feature 及关联 E2E 证据基础设施。
没有宣称 Tasks/E2E 其他 feature 的业务子句已全量绑定。原生验收使用脚本 provider，
不是外部真实模型能力验证。pnpm check:install 仍报告另 10 个包未配置，未修改全局安装。
额外根 pnpm check 在无失败的 276 passed 后主动中断（389.66s），没有宣称全仓库 check
通过；相关包的最终完整测试、根 types 和打包检查如上。

## 2026-10-09：状态行与反馈修订

用户指定状态行仅显示 `[e2e] running`、`[e2e] passed`、`[e2e] needs review` 等状态，不带分隔符或场景后缀。新增共享反馈渲染，原生工具提供执行阶段更新；正文先显示来源和 feature 验收进度，再显示未满足项优先的完整条款列表。Provider 原因同时进入默认结果、检查点和等待反馈；`/e2e` 使用同一持久结果显示且不触发 agent 轮次。简单 shell 查询保留通过，未知程序保留原有的保守失效边界。

回归先失败后修复。独立审查又复现两项问题：未知 shell 修改未声明的应用输入后证明仍通过、失败重跑沿用旧成功计数。新增对应回归，恢复未知 shell 的保守撤销，并在失败重跑时重新核验、撤销旧场景通过状态。独立复审确认两项已修复，单独运行新增反馈测试 8 passed。

| 检查 | 本次结果 |
| --- | --- |
| macOS 完整包测试 | `uv run --no-project --with pytest python -m pytest packages/e2e/tests/ -q`：108 passed |
| 类型检查 | `pnpm typecheck`、`pnpm exec tsc --noEmit -p packages/e2e/tsconfig.json`：通过 |
| 打包 | `pnpm --dir packages/e2e pack --dry-run` 包含新 feedback.ts；`pnpm pack:check`：19 包通过 |
| 安装检查 | 隔离 settings 配置：18 个 Pi 扩展包通过；用户当前 settings 的默认检查仍列出 10 个其他包未配置，未改写用户配置 |
| 真实 Pi CLI | 本机 Pi 1.1.0、脚本 provider；fresh、inline、失败及失败后重试通过，原机器 status/verifiedRun 保持不变 |
| 真实 Pi PTY | 80/40 列；运行阶段、失败后重试、已有证据、业务失败、缺 provider key、runner 错误、continue/waiting，以及 /e2e 的共享渲染通过；状态行无分隔符和后缀，长文本尾部完整 |
| 仓库相关契约 | 34 passed、1 failed：continual-learning 的 typebox peer 为 ^1.3.27，契约要求 *；该 manifest 与 HEAD 相同，属于本次 E2E 范围外的既有失败 |
| 修改检查 | `git diff --check -- packages/e2e .changeset/e2e-feedback-and-freshness.md`：通过 |

PTY 文本帧保存在 `/tmp/pi-e2e-feedback-20261009/`。本次没有重跑 Linux、真实 Jev 或真实推理模型；没有提交、发布或修改生产服务。既有其他工作区改动保留。

## ProMax 预实验后的提示与意图优化

冻结预实验不变。优化修复了保留原行为的约束意外取消显式验收请求的问题，
并把注入和工具说明调整为尽早运行已授权适配器、避免重复执行同一测试套件、
预留修复时间及明确已覆盖场景。新增请求用例覆盖中英文行为约束、执行禁令、
只审查、无关测试禁跑和后续显式指令。

`tests/live_gate.py` 的 `requested-inline` 用真实 Pi、脚本化本地 provider、
独立 HOME/agent 目录验证：不修改 feature，显式请求仍触发 checkpoint；
inline fulfilled 不能清除它。这是运行和状态契约证据，不是模型正确率提升证据。
本轮未改变 TUI 渲染，没有新增物理终端或屏幕阅读器验收结论。

本地日志、任务及打包 Docker 证明位于 `tests/runs/prompt-optimization/`（忽略提交）。
全局 `check:install` 缺少其他插件的结果保留，未修改用户安装。
