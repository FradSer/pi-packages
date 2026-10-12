# Pi package 与 CM5 / Windows 掌机连接审查

日期：2026-10-03 至 2026-10-04（Asia/Shanghai）。本报告记录本地修复、设备检查及获得用户全量授权后的 CM5 部署。CM5 和 Windows 均已激活修复版本，并完成真实模型的 Mac 原会话续接验收。现场麦克风输入尚未验收。下文保留各阶段证据及其适用范围。

## 覆盖范围

- `src/`：配置、多 desk 路由、发现与进程身份、事件序列化、上报与 TCP 传输、控制认证、Console、当前会话端点、SSH relay、历史回放及协议类型；同时检查入口与发布清单。
- Open DeskOS 的直接服务端：`runtime/shell/src/odk-link-service.js`、`odk-link-host-adapter.js`、`odk-link-client.js`，以及相关平台、本地通道、Pi Sessions 消费契约。
- 实际设备：读取 CM5 的活动服务与运行时快照；读取 Windows 运行时命名管道快照；比较每 desk 凭据是否匹配；从开发机执行 CM5 控制认证和只读列表。凭据内容不进入报告或日志。

## 修复与验收场景

| Given / When | Then：修复后的行为 |
| --- | --- |
| TCP 已接通，服务尚未确认上报认证 | 保持 `connecting`；合法 v1 ACK 后才为 `connected`。拒绝或 10 秒无响应会关闭并退避重试 |
| 中文字符、长 JSON 行跨 TCP 分片 | UTF-8 字符保持完整；超过 1 MiB 的记录关闭连接，尾部不会变成另一条有效记录 |
| 创建或写入连接同步失败 | 关闭失败连接，保留状态与有界历史，调度下一次重连 |
| 用户粘贴多行文本，或新消息结束 | 保留 Markdown 换行；活动摘要立即随快照更新 |
| 配置含非十进制端口、括号 IPv6 或同主机多端口 | 拒绝非法端口；正确解析 IPv6；Console 的歧义目标须明确到端口 |
| Windows 查询进程，或 OS 查询不响应退出 | 使用一次有界只读 CIM 查询，识别带空格的引号路径；独立截止时间释放子进程句柄和流 |
| Attach 失败、被替换、连接断开或旧回调迟到 | 关闭旧连接，忽略旧记录，保留断线原因；超时后才完成的服务端 Attach 也会关闭 |
| prompt / cancel / end 完成前 Console reload 或替换 | 结果仍标识原目标；旧请求不能注入新会话上下文或关闭新连接 |
| 同一项目有多个当前会话，或一条请求继续收到分片 | 按请求的 taskId 选择会话；同一请求最多分派一次 |
| Unix 仅声明当前会话端点，未配置上报 | 当前会话端点独立工作；shutdown 等待清理并使迟到 startup 失效 |
| Windows 试图启用当前进程 SessionHost | 明确拒绝不受支持的私有 IPC，并通过命令诊断显示原因 |
| Hosted Pi 晚于 Open DeskOS Link 启动，或更新其端点 | 按请求重新发现；已挂接连接继续使用自己的原端点 |
| 大会话快照含长目录或 JSON 转义文本 | 完整保留 cwd、workspaceName、sessionId；只缩短描述，无法容纳的记录整体拒绝并报告数量 |
| 多机器合计响应超过 2 MiB | 返回可关联的 `odk-link-response-too-large`，运行时客户端保留该原因 |
| 安装发布包，或运行跨仓库协议检查 | 包含 `session-control` 启动器；协议检查使用当前 `runtime/shell` 路径，实际执行而非误跳过 |

所有行为修复先建立失败回归，再修复并重跑相关检查。独立代理复审额外复现了旧控制请求操作新会话、长目录被截短两个问题；两者均补修并通过复查。

## 当日早期只读设备证据

| 检查层次 | CM5 | Windows 掌机 |
| --- | --- | --- |
| 访问与服务 | SSH 可达，Open DeskOS Link 用户服务 active / running，TCP 8765 在监听；活动 release 为 `20261003-personal-bot-v6` | 早先只读检查时 SSH 可达，既有 Open DeskOS Link 计划任务存在；后续预检 SSH 超时，当前可达性未确认 |
| 运行时通道 | Unix socket 快照成功，观察到 6 个上报会话；Hosted Pi 列表成功且为空 | 命名管道及通道令牌握手成功，快照成功；当时没有上报机器或会话 |
| 凭据匹配 | 本机配置中的上报和控制凭据均与运行服务一致 | 上报凭据匹配；控制凭据文件内容为空，属于只接受上报的配置 |
| 开发机控制链路 | 真实挑战认证与只读 `list` 成功，返回 0 个 Hosted Pi | 当前配置未启用控制 |
| 新 Windows 进程读取代码 | 不适用 | 源码通过 stdin 在设备上执行只读 CIM 读取，返回 0 个 Pi 进程；未部署文件 |

Windows 返回 0 个 Pi 进程只证明该查询能执行；真实 Pi 进程识别仍由捕获/注入数据回归覆盖。空列表不证明存在活动上报流。

## 首轮验证结果（2026-10-03）

- 包的 Node 全套：119 passed，0 failed，0 skipped。
- 包的 Python 全套：24 passed，0 skipped。此前因旧路径误跳过的跨仓库协议 fixture 检查已恢复。
- Open DeskOS Link 服务端及客户端相关测试：75 passed，0 failed。
- 扩大到 Pi Sessions source/events、Windows host、本地通道：117 passed，1 skipped，1 unrelated failure。失败是另一个任务删除或搬移了 `docs/wayfinding/windows-x64-shell-host/SPEC-WINDOWS-SHELL-HOST.md`，相应文档引用测试尚未完成调整。
- 包的独立 TypeScript 检查及全仓最终 `pnpm typecheck` 均通过。期间曾遇到并行任务在 monitor 包中的两处错误，最终复跑时已消失；本次未修改该包。
- `pnpm check:install` 通过；发布清单 dry-run 通过，包含 `session-control`。
- 实际安装的 Pi v1.0.0：隔离环境下 `--print /odk status` 成功；真实 TUI 菜单及 Link status 操作成功。环境没有模型和凭据，没有模型请求。
- 本任务改动的差异格式检查通过；独立审查最终未发现新的可确认阻塞项。

## 反思

1. 连接状态应来自协议证据。TCP 接通、认证成功、快照可读、存在上报流、控制动作执行，是不同的事实；每一层应有自己的验收证据。
2. 每个异步请求都应绑定会话身份和 generation。只在开始时检查当前连接，无法阻止 ACK、回放或 shutdown 之后的 continuation 操作替换后的会话。
3. 字节预算属于完整序列化记录。JSON 转义、重复工作区字段及机器归属会放大响应；限制必须保留身份、路径与关联字段，并让省略或拒绝可见。
4. 跨平台连接同时涉及路径、进程读取和权限。Windows 文件路径不能充当 Unix socket；没有私有 IPC 认证方案时，明确不可用更符合当前能力。
5. 测试本身需要验收。迁移目录后的 skip 曾隐藏跨仓库一致性检查；只校验 happy path 的 mock 也曾把未认证 TCP 当作 connected。现在检查实际 ACK、迟到回调、并发替换和查询硬截止时间。
6. 原 Pi 续接与 Hosted Pi 新建任务是不同路径。远端续接必须选择准确的原项目和会话身份，不能在发现失败时悄悄创建替代任务。
7. 原生扩展的 void 返回值不能证明某条消息已接收。保留 mutationId 与未知投递状态，禁止自动重放；原会话消息、工具结果和文件变更提供独立的执行证据。
8. 活动版本必须不可变。首次原地修改已恢复，最终采用新版本、完整发布预检及标准激活流程。实际部署范围、运行代码哈希和回滚资料都应单独核对。
9. 设备验收必须匹配驻留服务的用户身份。SSH 可达不表示登录用户可以读取产品凭据；应使用服务用户，保留凭据的所有权保护。

## 原 Pi 会话续接补充检查

本节检查 Personal Agent 经 SSH 把新 prompt 送入远端原有 Pi 会话的路径。它与 Open DeskOS Link 上报、Hosted Pi 新建任务分别验收。

修复包括：

- 按开发根目录列出所有子目录会话，保留同项目多个会话；变更必须指定准确 project 和 taskId。
- 部分端点未返回有效列表时，保留其他有效会话并报告 `incomplete / unavailable`；不再用完整空列表掩盖通信失败。
- 列表响应预算包含最长布尔字段及换行符，完整 262144 字节边界可以保留；超限项目明确截断，不丢失整个列表。
- 默认使用普通 Pi Enter 的 steer 行为，显式 followUp 保留到下一轮；启用原生命令与模板展开。
- 同一 mutationId 的相同请求或并发请求只提交一次；内容冲突被拒绝。单个 SessionHost 生命周期保留 256 条变更回执，满后拒绝新变更。
- 原生 prompt 回执始终为 `submitted: true / accepted: false / delivery: unknown`。公开扩展 API 返回 void，不能确认具体消息已接收；相同文本、乱序 steer/followUp 或手动输入不再认证某条变更。
- 状态分别提供原会话实际观察到的 prompt、response、activity、回合结果；传输失败保留实际 mutationId，禁止自动重放。
- 快速完成的回合结果不再被投递后的状态清空覆盖；跨平台临时目录较长时，验收夹具使用独立短 socket 路径。

原 Pi 续接阶段验证（受限入口补充结果见下节）：

- 包的 Node 全套：132 passed，0 failed，0 skipped；Python 全套：24 passed。
- Personal Bot 续接、任务客户端、会话控制、路由及集成相关测试：43 passed，0 failed，0 skipped；Open DeskOS Link 相关最终复跑：75 passed。
- 原生 SDK 端到端：闲置续接、运行中 followUp、运行中默认 steer 均实际写入临时项目标记；三条用户 prompt 持久化，原 UUID 和 sessionFile 不变，没有替代任务。
- 该端到端测试在默认及故意加长 TMPDIR 下通过。使用实际已安装 Pi SDK、公共扩展 API、实际工具和 relay，模型及 Jev 判断为离线脚本夹具。
- 包与 Personal Bot 类型检查、打包及差异检查通过。全新独立复核的三项发现均已补修并复查。
- 后续实机只读调用发现的列表失败掩盖、响应边界问题也已补修并独立复查。诊断测试按实际状态等待认证，不再用服务端收到清单推断客户端已处理 ACK。
- 扩大 Personal Bot 检查还发现 `candidate-checks.test.mjs:556` 的 `details.truncation` 未定义，单独运行可复现；它不属于连接路径，本次未修改。

授权前设备配置快照：

| 路径 | 只读实机证据 | 尚需操作 |
| --- | --- | --- |
| Windows → Mac | 使用设备上 v6 task-client 与既有 SSH 身份，成功查询演示 Pi 原会话 `01a0f0ba-8e8b-750f-aaae-c29d6fd8e743`。该旧端点未返回有效列表；实际 coding_tasks_list 在 helper 修复后明确返回 `incomplete:true / unavailable:1` | Mac 目标仅覆盖 `/private/tmp/odk-session-demo`；运行中的旧 Pi 端点与设备服务尚未更新，真实 Personal Agent 提示未验收 |
| CM5 → Mac | CM5 Personal Bot 服务 active；当前仅有 CM5 本地目标。已有 monitor 身份和主机密钥 pin；使用其既定 HostKeyAlias 能通过只读认证 | monitor 身份在 Mac 上被强制为只读快照命令，不能发送 prompt；普通 IP 连接未采用该 alias 时主机校验失败。须新增专用控制身份与 Mac 目标；尚未修改配置、身份或服务 |

这些早期本地执行证明与设备只读查询不能合并为“真实模型在两台设备上续接成功”。后续用户已明确授权目标/SSH 配置、修复部署、相关服务重启及隔离项目中的真实模型验收；实际结果见后续章节。

## 受限控制入口与部署预检（2026-10-04）

- 新增固定操作参数 `--allow-root`，最多配置 16 个目录。受限入口仅接受合法的 v1 `list / status / prompt / cancel` 请求；使用真实目录路径校验项目范围，拒绝父目录、越界目录、符号链接逃逸及无效协议，拒绝发生在端点发现或 socket 连接之前。
- SSH 强制命令可固定批准目录；客户端的 `SSH_ORIGINAL_COMMAND` 不参与参数选择。该限制保护会话选择，Pi 原有工具能力和文件访问权限保持不变。
- 全新独立复核没有发现可确认的权限绕过或并发缺陷，发现批准 `/` 时误拒绝子目录的功能问题，已建立失败回归后修复。
- Windows 验收新增显式启用的测试。默认跳过实机操作；启用后先检查现有目标、目录所有权及连接，再创建独立 Mac 临时项目，只调用该项目的准确原会话 UUID。验收使用离线模型夹具，覆盖闲置续接、followUp 和默认 steer，不操作已有演示会话。
- 验收响应使用独立 nonce、版本、命令和准确任务身份校验；UTF-8 分片、超限、错误关联、连接未关闭及观察超时均有本地回归。传输失败不重放变更。
- 两次显式 Windows 验收均在只读 SSH 预检阶段超时，发生在临时项目、socket 或 prompt 创建之前。因此没有 Windows → Mac 实际续接成功证据；也没有真实模型判断、Personal Agent 自然语言路由、设备 UI 或物理输入验收。
- CM5 的三个 Open DeskOS Link 生产源文件与本地 HEAD 基线逐字节匹配。Windows 服务端基线因 SSH 超时而未知；设备 Personal Bot v6 的基线证据来自早先成功读取，不能替代部署前的新校验。
- 已生成本地候选包 `/tmp/odk-connection-bundle-itfzjeso.tar.gz` 及其 `manifest.json`，包含范围清单、逐文件哈希、受限控制参数与远端基线限制。该阶段尚未部署；package 快照仍含 `workspace:*` 依赖，不能直接作为独立 npm 安装包。
- 候选包只包含本任务的生产源文件和明确列出的验证资料，排除两个仓库内其他任务的改动；该阶段未修改索引、提交、授权文件、主机信任文件或驻留服务。

最新本地验证：

- Pi 包 Node 全套：134 passed，0 failed，0 skipped；其中当前会话及受限 relay 测试 44 passed。Python 全套复跑：24 passed。
- 新增回复观察器与原生 SDK 续接验收：4 passed，0 failed；Windows 实机测试 1 skipped，明确要求显式启用。
- Pi 全仓与 Personal Bot 类型检查通过；本任务源文件差异检查通过。此前服务端相关 75 项及 Personal Bot 相关 43 项检查的源文件没有在本补充阶段继续修改。
- 根目录修复经独立代理再次检查；候选包的源文件、补丁及归档清单另行逐字节验证。Personal Bot 新增跨仓库测试及其 helper 依赖未包含在生产源文件候选包中，执行仍使用当前两个本地仓库。

## 授权后的部署与访问修复（2026-10-04）

用户明确授权全部必要操作，并要求使用记忆中的 Windows 访问方法。以下操作在该授权之后执行。

- Mac 为 CM5 新增专用受限 SSH 控制入口，固定开发根目录及演示根目录。原有只读 monitor 身份保留。私钥只保留在 CM5；主机公钥经过指纹核对并固定，严格主机校验保持启用。
- Mac 的 `.zshenv` 为之后启动的 Pi 设置 `ODK_SESSION_HOST_SOCKET`。已注册的本地包由新 Pi 会话加载；现有旧会话没有被重启或改发 prompt。原文件及授权文件均有备份。
- CM5 新增 Mac 任务目标，修复原有本地目标指向过时 voice-agent 路径的问题。真实本地列表由调用失败恢复为空列表。目标配置与 SSH 配置均有回滚副本。
- CM5 最终活动版本为 `/opt/odk/releases/20261004-connection-fixes-v2`。此前活动 v6 的六个生产源文件已恢复原始哈希，全部 17 个版本目录保留。最终候选使用原项目 updater 激活，目录归 root 所有且不可写，`previous` 指向第一版修复版本。
- 部署仅复制本任务的三个 Open DeskOS Link 源文件及三个 Personal Bot 源文件；没有复制另一个任务正在修改的 `agent.mjs`。新版本另外修正发布标识及环境变量文档，默认值与实际源码一致。
- 首次操作曾写入活动 v6；复核发现违反不可变发布规则后，已从逐文件备份恢复。后续更正与默认值修复均建立新版本，经过完整预检后激活，没有继续编辑活动版本。
- 最终版本完整预检：706 passed，0 failed，4 skipped；样式构建和 Electron 图形 smoke 通过。激活后五个用户服务均为 active/running。父代理另行核对活动路径、发布标识、六个源文件哈希、只读权限及驻留进程目录。
- 最终 v2 激活前，驻留 Personal Bot 为 idle，本地 Hosted Pi 清单为零。第一版激活缺少重启前即时任务清单，不能补造该证据；当时持久化任务目录没有任务记录。最终版本已补做即时检查。
- 最终部署、预检、保护检查与回滚资料保留在 CM5 `/opt/odk/rollback/connection-fixes-v2/`。最初六个源文件备份另保留在 `/opt/odk/rollback/connection-ea0ov0bw/`。
- Windows 的现有 Tailscale、MagicDNS 和旧局域网地址均无法连接，Tailscale 显示设备离线。另从 CM5 所在局域网检查 SSH 公钥，没有发现与既有可信 Windows 主机公钥一致的端点。没有放宽主机信任，也没有部署 Windows 修复。已请求用户唤醒设备。
- 真实设备验收 helper 已补充五类失败回归：变更错误保留实际 mutationId、畸形服务响应、独立有界清理、原生 fixture 清理、其他变更工具拒绝。另补充结算后的迟到 socket 错误回归。相关组合检查为 9 passed、1 Windows optional skip、0 failed；独立复核通过。

## CM5 真实 Personal Agent 续接验收

本轮在 CM5 上运行实际部署 v2 的 factory、Personal Bot service、SDK、配置、Jev 判断及模型。验收以 orangepi 身份运行，使用独立临时状态及经过认证的临时服务通道。录音和转录依赖提供一条测试文字；不是驻留服务的麦克风、触摸或 UI 验收。

- 首次自然语言验收在 factory 启动时失败，尚未调用 coding 工具或提交 prompt。原因是 SSH root 身份与 Jev 凭据所有者 orangepi 不符。凭据保护正确拒绝访问；没有复制凭据或修改其权限。
- 对验收进程增加驻留 UID 检查，位置在读取私有环境和导入生产模块之前。回归先失败再通过，独立复核通过。单独 factory 探针以 orangepi 启动成功且没有 prompt；该成功不等于自然语言验收。
- 后续完整自然语言验收退出 0。实际 Personal Agent 模型为 `opencode-go/muse-spark-1.3-contributor`，实际 Jev 选择 `session_continue`。服务状态经过 recording、transcribing、thinking，回到 idle。
- 真实调用顺序为 `coding_targets`、`coding_tasks_list`、一次 `coding_task_prompt`。清单选中原 Mac Pi 会话 `01a102b3-573b-779e-bd1c-b5eeb49d73ec`，项目为独立临时目录 `/private/tmp/odk-session-demo/real-native-TGPTRv`；没有新建替代任务。
- Mac Pi 使用真实 `openai-codex/gpt-6-luna`。续接消息为“请在当前项目里把 cm5-marker.txt 写为 cm5-continued，并说明完成结果。不要新建任务。”，精确持久化一次。真实 write 工具成功，文件内容准确为 `cm5-continued`。
- 原 UUID、sessionFile 和项目保持一致；会话目录只有原记录文件。父代理直接读取原 JSONL 和标记文件，并通过 SSH 独立读取设备回执，逐项核对，而非仅采用子代理结论。
- mutationId 为 `6e942fd6-dff8-4765-8522-ef4a632ec8ea`。API 回执仍为 submitted true、accepted false、delivery unknown，没有自动重放；文件及原会话执行证明单独记录，不把它们升级为特定变更的准入确认。
- 成功回执、首次失败和独立 startup-only 探针记录保留在 `/tmp/odk-real-cm5-evidence-2akidjvt/`。父代理证明为该目录中的 `parent-verification.json`。CM5 成功 actor 回执保留在 `/tmp/odk-personal-evidence-k3kinQ/receipt.json`，临时 actor 的清理失败列表为空。
- 最新验收支持及回复观察器组合检查：9 passed、1 Windows optional skip、0 failed。UID 支持回归子集为 6 passed。此前整个 Pi 包的 134 Node 和 24 Python 检查、CM5 的完整发布检查独立记录，不合并为一个覆盖所有设备的总数。
- Mac 临时进程正常退出，原 fixture 项目、该 UUID 的 descriptor 和 socket 已删除；父代理另行核对均不存在。CM5 自建 runner 目录在所有权与文件清单核对后删除，限定回执继续保留。清理证明为证据目录中的 `cleanup.json`。部署时临时使用的 package-manager shim 也已删除，正式配置与活动进程均未引用它。

## 普通 Pi CLI 与既有任务恢复补充

- 使用真实安装的 Pi 1.0.0 CLI RPC 模式、真实 ResourceLoader 和本包入口，取代仅通过 SDK factory 建立会话的方式。测试隔离其他扩展、背景上报及目录注册表，没有修改全局 Pi 设置或复制凭据。
- 原 CLI 正常 EOF 退出，原记录文件保留；随后使用 `pi --session <exact existing JSONL>` 恢复。同一 UUID `01a102e2-2a11-7577-b48b-5671384da996`、项目、名称及记录文件保持不变，没有第二次初始化 prompt、fork 或替代记录文件。
- 恢复时真实 CLI `session_start` 重新发布端点；原 4737 字节记录前缀保持逐字节一致，仅追加同名元数据。父代理另核对实际进程的 cwd 和 Unix socket，确认 live CLI 对应准确项目。
- CM5 的实际部署 factory、真实模型/Jev 与 SSH 向该恢复会话提交一次新提示；`cli-marker.txt` 精确写为 `cli-continued`。提示持久化一次，真实 write call 和成功 result 按 toolCallId 关联，原 UUID 和 sessionFile 保持不变。
- mutationId 为 `cd588012-b65c-4340-9a0a-89b02f4ccf1b`，准入状态仍 unknown，没有重放。此提示是新实验中的独立指令，不是重发上一轮 `cm5-marker.txt` 变更。
- 初始模型没有遵守“不要写文件”的准备指令，额外写入本实验的 `acceptance.txt`。该 no-write 检查记为失败；原文件及哈希作为基线保留。整个会话共两次 write，其中初始化额外写入一次，后续请求的 marker 写入一次。没有将整体写入次数改写为一。
- 父代理直接读取原 JSONL、基线文件及 marker，并通过 SSH 独立读取 actor 回执，核对其与本地证据逐字段一致。证明保留在 `/tmp/odk-real-cli-evidence-rv16bg4o/parent-verification.json`，初始化、关闭、恢复及续接证据位于同目录。
- Mac 全局 Pi 注册使用相对 agentDir 的 package source，解析后为本包目录，只有一条匹配注册。实际 CLI 使用显式扩展入口；该实验不代表完整全局扩展自动发现、TUI 键盘输入或其他已运行旧会话均已可控。
- 两份 README 补充了旧进程安全恢复方法：空闲时退出，设置端点变量，恢复准确原 JSONL，只运行一个对应进程。该操作在本轮普通 CLI 实际验收中验证。
- 恢复后的 CLI 正常 EOF 退出，退出码 0，真实 `session_shutdown` 移除端点。自建项目、registry 及 CM5 临时 runner 已清理；父代理另外直接核对项目和端点不存在。限定证明保留，清理记录为同目录的 `cleanup.json`。

## 驻留输入入口与剩余设备条件（Windows 恢复前）

- 独立完成审查确认：当前驻留 socket 没有自由文本 prompt 命令，正常用户输入走录音、STT、驻留 agent。临时 factory 的注入转录不能冒充该正常入口。
- CM5 当前驻留服务为 v2、active，生产 socket 状态 idle；配置输入是 P4 USB microphone。播放设备只有 DP/HDMI，未发现 ALSA loopback 或重定向配置，也没有已知可用的音频回送入口。
- 没有通过新增隐藏 API、修改驻留依赖、空音频或未知环境录音制造入口通过。已请求用户确认可在设备端朗读一条预定测试指令；仍需该现场输入才能验证驻留录音、真实 STT 和设备反馈。
- Windows 最新只读快照仍离线，既有运行手册及记忆没有可执行的可信远程唤醒渠道。没有猜测 MAC 地址或放宽 SSH 主机信任；仍等待设备恢复联网。

## 外部条件阻塞审查（2026-10-04，Windows 恢复前）

- 用户授权全部必要操作之后，Windows 离线连续出现在三轮目标工作中。最新权威快照为上海时间 02:00:28，设备仍 offline，最后在线时间仍为 00:20。部署前的当前路径、进程及真实 Windows 续接无法验证。
- 本轮另行读取 CM5 当前状态：活动版本仍为 `20261004-connection-fixes-v2`，Personal Bot PID `1265399`，用户服务 active/running，生产通道 idle。没有发出录音、转录或新提示命令。
- 普通 CLI 恢复与续接证明仍完整，准备阶段 no-write 失败仍单独记录。父代理重新核对自建项目、descriptor 和 socket 均不存在，测试进程已正常退出，限定回执保留。
- 用户已有的全量授权继续有效。剩余外部条件是 Windows 恢复联网，以及设备收到一条预定现场语音。取得这些条件后继续原目标，不需要重复授权。

## 剩余能力与验证边界

- 源码保留在两个本地仓库，尚未提交或对外发布。CM5 与 Windows 均已激活本次修复。前文早期只读结果描述的是其当时运行版本。
- Windows 当前进程 SessionHost 仍未实现安全私有 IPC；Windows Open DeskOS Link 上报与远程 Hosted Pi 控制的代码路径继续受支持。
- Open DeskOS Link v1 事件没有全局事件身份。当同一机器仍有其他连接保留服务状态时，重连回放可能重复已有事件；本次保留协议兼容性，未承诺 exactly-once。
- CM5 的真实模型自然语言路由、实际 SSH、原 Pi 消息及文件执行已通过。输入使用注入转录文字；驻留服务完整交互、设备 UI 像素、物理输入及音视频采集未验收。Windows 的部署及真实续接现已完成，证据见下一节。
- 用户已让 Windows 恢复联网，随后明确现场讲话暂时不方便。全量授权继续有效；物理麦克风与驻留 STT 入口留待现场输入时验收。
- Windows 模拟平台的失败复现触发了旧实现对当前目录执行 `chmod(0700)`；错误路径产生的测试描述文件已清理，修复后的代码在 Windows 分支提前拒绝。当前 `pi-packages` 工作树目录权限为 `0700`，复现前没有权限基线，无法确认是否发生变化，因此未猜测恢复。


## Windows 恢复、修复与实际验收（2026-10-04）

- 用户确认 Windows 已开机联网后，沿用既有 SSH 身份及严格主机信任完成连接。部署前重新读取实际任务、路径、六个源文件基线与空闲状态。
- 新增平台回归发现：Windows 路径标准化会绕过 `/opt/odk` 的保留目录配置限制，包括 `//opt/odk/current`。两次实机 RED 后统一保留目录比较，原始远端项目路径仍原样传递。最终本地相关组合为 38 passed、0 failed；Personal Bot typecheck 通过。
- Windows 活动版本为 `%LOCALAPPDATA%\odk\connection-releases\20261004-connection-fixes-v3`。只更新六个生产模块；原 v6 `agent.mjs`、原依赖目录、设备配置与凭据均保留。候选依赖使用原目录 junction。活动版本 11 个传输条目逐一匹配发布清单哈希。
- Windows 针对性回归：Shell 6 passed、2 Unix-only skips；目标配置/项目携带 4 passed；Jev intent 12 passed。完整旧 task-client Unix fixture 在 Windows 不能作为通过证据，相关失败日志保留。本次没有宣称 Windows 全套或物理输入通过。
- 第一次切换因计划任务 `/tr` 长度限制失败，第二次因预先存在的孤立 Shell 窗口占用应用会话而失败。两次均记录退出、任务恢复与原路径/通道复核；旧服务已恢复。最终使用保留原属性的 XML 注册，并准确停止旧监督进程、所属子进程及孤立的原 Shell 窗口后激活成功。
- 最终进程：Personal Bot `3908`、Open DeskOS Link `17968`、Shell 窗口 `10600`、renderer `11852`。实际候选路径、认证后的 Bot idle 与 Open DeskOS Link snapshot 均已验证。任务的 principal、triggers、settings、working directory 与单一 Exec 属性逐项保持原值。
- 离线 Electron 窗口 smoke 为实际 1280×720、exit 0。此前 1280×800 smoke 被 Windows work area 限为 1280×776，失败记录保留；它没有走驻留窗口的全屏进入路径。部署后实际 Shell 窗口及屏幕均为 1280×800，坐标 0,0，并保存窗口截图。这不是完整 UI 交互或像素断言。
- Windows 建立独立 Session Control SSH 密钥，仅授权 Mac 固定 helper 与演示/开发根目录。私钥仅在 Windows，按 Windows ACL 限制访问；既有监视/隧道身份保留。Mac 原 authorized_keys 前缀与备份保留；不接受任意原始 SSH 命令或放宽主机信任。
- 两次真实 agent fixture 在建立测试私有通道前失败，`codingTrace:[]`，原 Mac JSONL 原始哈希不变且没有新 marker。复现定位为夹具中的 Windows named-pipe 转义；使用 `String.raw` 生成正确端点并补充 RED/GREEN。支持与回复观察器本地为 10 passed；Windows 支持夹具为 7 passed。Windows 针对性检查合计 29 passed、2 Unix-only skips；独立复核通过。
- 实际 Windows 安装 factory、Jev、model `cli-proxy/bailian/qwen3.8-flash`、认证私有通道及受限 SSH 完成续接。保留该设备既有 `coding` profile；仅测试录音/转录文字被注入，没有调用驻留麦克风，也没有改变驻留 profile。
- Jev 实际选择 `session_continue`，随后调用 targets、准确列表、一次 prompt、一次 status；未创建替代任务。Mac 原生实际模型为 `openai-codex/gpt-6-luna`，会话 UUID `01a10739-7a00-75fd-90cd-79c23dc44419`，原项目 `/private/tmp/odk-session-demo/real-native-MjMPWv`。
- 父代理直接读取原 JSONL 与项目文件，确认只有一个会话文件、原始字节前缀未改变、远端提示恰好一次、实际 write 成功一次，`windows-marker.txt` 精确为 `windows-continued`，没有换行。初始准备回合没有写入文件；一次初始 read 错误另行保留。实际完整会话结果不等于某次 mutation 的入队证明。
- 回执 mutation `e69a5de9-a357-44b7-9775-60300ec38bd0` 保持 `submitted:true / accepted:false / delivery:unknown / retry:never`。父代理比较远端最终回执所有主要字段，并单独验证原会话执行结果，没有凭匹配文字改称 admitted 或重发。
- 本轮本地证据为 `/tmp/odk-win-connection-current/`，原生回执另在 `/tmp/odk-native-evidence-0tweT1/receipt.json`。远端部署/恢复/窗口证据在 `%LOCALAPPDATA%\odk\deploy-backups\connection-20261004`，成功 actor 回执在其 `real-acceptance-v3\odk-personal-evidence-kEjdHX\receipt.json`。均保留，不进入提交。
- 最终重新读取双端 Bot 均 idle，服务 active；Windows 原 runtime 三个模块仍保持部署前基线哈希。原生测试正常退出，cleanup failures 为空；自建项目、对应 descriptor 与 socket 已由父代理确认删除。Windows actor 清理为空，独立 smoke/窗口检查任务已删除，实际部署任务及回滚记录保留。
- 此阶段用户暂时无法现场讲话，完整语音入口尚未验收。下节记录后续 Windows 受控音频验收；CM5 现场麦克风仍未验收。

## Windows resident microphone continuation acceptance

- The user was unavailable to speak. Windows played controlled Chinese speech through its existing default audio output.
- The default speaker volume was approximately 2%. The first microphone capture did not reproduce the test sentence.
- The first STT response contained unrelated context. This probe sent no model prompt or remote mutation.
- A second probe temporarily used 35% speaker volume. The actual production recorder and STT reproduced the exact test sentence.
- Each playback test restored the original speaker volume. The recording files were removed through the recorder cleanup contract.
- The complete run used the deployed resident Personal Bot and its published authenticated `status` and `toggle` protocol.
- This run did not inject a transcript, substitute PCM input, change the agent profile, or replace service dependencies.
- The spoken request selected the unique original session named `掌机麦克风续接验收`. STT preserved this exact name and the requested file content.
- The service reported `recording`, `transcribing`, `thinking`, and `idle`. Its final response identified the original Mac session and observed execution.
- The Mac session ID was `01a10765-c955-74bf-80d9-90c8f31e8973`. Its project was `/private/tmp/odk-session-demo/real-native-V6PbGU`.
- The Mac received exactly one continuation prompt: `请创建文件语音验收，文件内容是续接成功，不要换行。`
- Its actual `write` tool created `语音验收` with the exact content `续接成功`, without a newline.
- Independent parent verification confirmed the original UUID, unchanged original JSONL prefix, one session file, and one successful write.
- Mutation `bc4723ae-4001-4758-8ae7-74496d9e7285` retained unknown admission and no automatic replay. Observed session execution remains separate evidence.
- Two observer setup attempts ended before recording. One imported an unexported helper; the other omitted the initial status request.
- Both setup failures preserved the original Mac session without an extra prompt. The successful observer used only published protocol messages.
- Local evidence is in `/tmp/odk-win-connection-current/resident-result.json`, `resident-parent-verification.json`, and `resident-native-receipt.json`.
- Device evidence is under `%LOCALAPPDATA%\odk\deploy-backups\connection-20261004\resident-voice-v3`.
- The original native test session closed normally. Its temporary project, descriptor, and socket were removed.
- Seven owned audio test tasks were removed. Their scripts and diagnostic records were archived; production tasks remained active.
- This proves Windows resident microphone, STT, agent, restricted SSH, original Mac Pi continuation, and returned service feedback.
- The speech source was controlled playback, not a human speaker. Touch input, pixel assertions, and CM5 physical microphone acceptance remain unverified.

## Live Mac terminal visibility acceptance

- On October 4, 2026, the operator opened a real Terminal.app window with interactive Pi 1.0.2.
- Pi loaded the installed Open DeskOS package through its normal CLI extension path. It used a private test project and actual model.
- This run used neither SDK-only observation nor RPC-mode output as proof of terminal visibility.
- The original session ID was `01a10776-920f-77c5-8222-e61de73a67a8`. The Terminal window ID was `107726`.
- The first Windows request timed out. Later read-only queries showed no corresponding prompt or marker in the original session.
- The unknown request was not replayed. Its attempted mutation ID was `b3238851-426a-4b24-88de-837fe49b2df6`.
- A distinct Windows test used the deployed `task-client.mjs`, existing target configuration, restricted SSH identity, and original session ID.
- The open Mac terminal displayed that new user prompt, its actual write operation, and `WINDOWS实时终端显示验收完成`.
- The Windows marker contained exactly `windows-tui-visible`, without a newline.
- CM5 then used its deployed task client as `orangepi` to send a different prompt into that same terminal session.
- The open Mac terminal displayed the CM5 prompt, its actual write operation, and `CM5实时终端显示验收完成`.
- The CM5 marker contained exactly `cm5-tui-visible`, without a newline.
- Neither successful continuation reopened the terminal, resumed the session, or created a replacement session.
- Terminal.app contents and actual window screenshots prove rendered visibility. Independent JSONL and file checks prove execution and identity.
- The original JSONL prefix remained unchanged. The session directory contained one session file, three user prompts, and two successful writes.
- The prompts were one local preparation prompt and one independent continuation from each device.
- Successful receipts retained unknown mutation admission. Observed terminal execution did not upgrade those receipts to accepted delivery.
- Evidence is in `/tmp/odk-terminal-live-24j0c5dt/`, including screenshots, terminal captures, device receipts, and `verification.json`.
- This closes the earlier live-terminal visibility gap. It does not add a new CM5 physical microphone test.
- The test Pi exited normally through its terminal. Its descriptor, socket, temporary project, and owned CM5 helper files were removed.
- The original JSONL and markers were archived with the evidence. The test window closed; pre-existing terminal windows were preserved.
