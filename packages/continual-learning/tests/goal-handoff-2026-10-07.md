# Goal 交接：continual-learning 可选 Jev 的学习质量提升

导出核验时间：2026-10-07 11:17–11:20（Asia/Shanghai）。
仓库：`/Users/FradSer/Developer/FradSer/pi-packages`。

## 在接手 agent 中启动

```text
/goal 请读取 /Users/FradSer/Developer/FradSer/pi-packages/packages/continual-learning/tests/goal-handoff-2026-10-07.md，接续原目标：continual-learning 加入 Jev（设计上可选），必须用证据证明提高学习质量。先核验文件、进程及保留的真实实验结果，按文中的职责、安全边界和验收标准继续。不要重新启动已完成或仍运行的实验，不要把通过率或 mock 当成质量改善。
```

目标尚未完成。不能为了结束工作缩小目标、降低门槛或把实验正结果当作预设。
本次导出会话的 `get_goal` 返回 null；原目标需要在接手 agent 中启动，本文是
可复制的完整续接输入，不是已自动迁移的后台 goal。

## 原始需求与授权

优化整个 `packages/continual-learning`，真实运行、修复必要问题。Memory 是
注入上下文的持久知识；Harness 是原生执行约束。减少误记与漏记，保留正确约束。
早期手动 full 消耗很多 tokens 却无落盘，是问题线索，但不能为增加产出而误记。

Jev 负责小而明确的语义判断；大模型生成候选；插件冻结证据、检查结构、引用、
权限、隐私并决定写入和执行。Jev 不得直接写文件、重分类隐私或绕过 Harness。

用户已明确授权网络、Docker、真实模型和付费 Jev 推理，反复给予广泛授权。
当前主模型必须是 **provider `cli-proxy` / model `opencode/deepseek-v4.1-flash`**；
之前的 `opencode/space-bunny-free` 已被用户替换，不要切回。
Jev SDK 固定 0.6.0，模型固定 `jev-1.13.0`。
每个新实验仍须核验当前凭据、版本、调用上限和费用；不得输出凭据。
没有 npm 发布、远端分支写入或破坏性清理要求。

配置在 `~/.pi/agent/continual-learning.json` 的 jev 项，或 `TYPESAFE_API_KEY` 环境变量；
不是必须配置用户级 `jev.json`。保持 `/memory`、`/harness`、`/consolidate` 简单，
允许 `/memory <要求>`，不增加 `/jev`。

必须满足：

- 增量选择分别判断持久知识、行为约束，两种方向可同时成立；评分 Memory 元数据；
  空索引直接路由保留；Jev 不可用沿用已有选择器。
- 候选先通过代码结构与冻结原文引用核验，再判断支持、已读 Memory 重复/补充/冲突、
  Harness 是否扩大约束。独立判断可并行，正文依赖必须等正文读取后执行。
- 显式 Memory 要求必须处理，低置信度不能静默丢弃或借机改 Harness。
- 不确定、超时、服务不可用不是“没有学习机会”，不能解除已有约束；保留原因，
  回退或提案。父进程继续拥有写入权限、事务和证据时效检查。
- 回执说明方向、所选 Memory、停止/回退原因、应用结果、Jev 耗时及实际版本；
  不记录敏感原文。
- 覆盖双方向、显式 Memory、推测/临时故障、重复/补充/冲突、Harness 不泛化、
  不可用回退、未授权写入；固定中英文样本和未参与调优样本；分别统计有效落盘、
  误记、误拦、约束执行、耗时与费用。

## 工作约束

读取当前 AGENTS.md；用户最新版本新增 `packages/tasks` 工作记录要求，多步或
跨回合工作用 create_task/update_task/get_task/list_tasks，goal 不能替代 task。
本导出环境没有暴露这些任务工具，未伪造任务记录；接手后按可用接口记录工作。

Given/When/Then → RED → GREEN → REFACTOR。使用 pnpm 和 uv，保持现有测试布局。
安全、并发或复杂状态改动自测后必须让无实现历史的新 agent 审查。该要求允许
必要的审查委派；其他情况下遵守当前 developer 对主动委派的限制。

工作树有大量既有未提交修改，不能 reset、批量清理、提交或覆盖无关工作。
不要写用户全局配置、Codex memory、发布包或修改远端。临时实验在隔离 Docker
及 `~/.cache/pi-continual-learning/` 中。保留所有失败实验和冻结原始材料。
未证明的 composed 策略仍默认关闭，实际项目实验显式开启只限临时测试镜像。

## 当前实现：需以源码重新核验

- `extensions/jev-learning.ts`：引用支持、完整反证覆盖、描述独立检查、Memory
  关系与 Harness 权限/范围判断。请求有体积、批次、版本与并发检查；提案不授予写入。
- `extensions/jev-memory-readiness.ts`：严格三标签 selfContained/needsOther/unresolved，
  confidence ≥0.8、所选概率 ≥0.9；保持完整候选上下文、hash 绑定与无写权限。
- `extensions/independent-memory-partition.ts`：只有新增、已通过原始支持检查且
  父进程证明独立的候选可分区；完整反证、所有依赖判断先于写入。失败保留原策略。
- `extensions/inject-memory.ts`：普通生产 constructor 仍为 `createJevJudge()`；
  composed/independent 两项实验开关只在测试镜像显式改写，不能默认激活。
- `extensions/consolidation-run.ts`：最终核验位于回滚事务内；私有/public/index
  写入后核验，失败回滚并保留提案。
- `extensions/harness-command-coverage.ts`：有限 git push 模板匹配证明不是授权；
  等价 literal tab 修复保留严格模板范围。
- `learning-efficiency.ts` 的 telemetry/receipt 保留支持覆盖、关系、readiness 含义。

生产文件的大量改动来自此前同一目标；不要按本文记忆直接宣称当前已全部正确。
关键研究材料在 `packages/continual-learning/tests/`，引用以下文件再决定下一步。

## 最新真实 Docker 实验：交接时状态已改变

新流程修复：初始 prompt 不再提前把命令称作“已验证”；必须独立执行原命令，
成功后才记忆 verified 项目事实。`learningCommandNativeSuccess` 用原生调用/结果
链接和保守命令匹配验证，最终断言放在 Memory/Recall/Harness 观察之后。
相关文件：

- `tests/live_docker_projects.py`（新增 regression_task_prompt 与 provenance gate）
- `tests/test_project_verification_provenance.py`
- `features/project-verification-provenance.feature`
- `tests/project-verification-provenance.md`
- `tests/project-verification-provenance-results.json`

运行命令曾为：

```bash
uv run --no-project --python /opt/homebrew/bin/python3 python packages/continual-learning/tests/live_docker_projects.py --cohort heldout --jev paired --memory-policy composed --jobs 1
```

计划三个项目 off/on 共六臂，固定源码 digest：
`1af9118d7857e81542410e5f44dde74c2ba233cdc1baa6cbc6ed4d7d360758c0`。
原始目录：`/Users/FradSer/.cache/pi-continual-learning/docker/20261007T025657Z`。

**导出时实际核验：旧工具句柄 23790 不可用；未找到对应主机 runner；
开启组容器仅有 sleep，没有模型/实验进程。不能再称整批正在运行。**
目录里没有 summary，也没有其余四臂结果。只确认以下部分：

1. `yocto-queue-off/report.json`：passed，学习371.14秒，独立命令结果、回归测试、
   私有偏好、安全知识、public mirror、fresh完整读取/执行、原生 Harness 阻止及
   无关 Bash 均通过。SHA256：
   `22bf43308550509a57708f4e67312f9a5bede72eb4399bf68194164d00b47f81`。
   baselinePrivateRecall 也为 true；baseline 可读同一文件系统，不能当成无 Memory 反事实。
2. `yocto-queue-on` 的未汇出材料仍在容器
   `cl-project-yocto-queue-8cf61da7:/home/node/results`，本次已完整复制到新的本地目录
   `.../20261007T025657Z/handoff-retained-yocto-queue-on`。
   其 report 是 **failed**，stage native-harness-enforcement，学习55.04秒；
   learningCommandNativeSuccess/regressionChanged true；Memory failedCheck
   missing-supported-memory-judgment，Recall unverified(memory-prerequisite-failed)，
   Harness failedCheck phase-callback-error；jevJudgments 为空。原因尚未展开排查，
   不能直接归因于 Jev 语义判断。报告 SHA256：
   `2bbf0a3df4172a7a334c6d464024c795b592584aecbc3950c7293c58516c1555`。

**接手第一步**：核验上述进程与 raw 文件，读 on 的本地 receipt/失败记录，识别
是否为真实调用、缺失回执、流水线或测试参与失败。保护私人证据，不把全文写进报告。
保留首次失败；先判断为何其余四臂未执行，恢复测试必须新协议/明确记录，不能
为了好看重跑失败组。不要使用跨 agent 失效的 exec handle，也不要在容器仍活跃时重启。

容器 `keen_kowalevski` 是既有无关容器，必须保留。当前开启组 sleep 容器也暂时保留，
证据已复制但没有执行删除。首轮构建目录 `20261007T025543Z` 因 ghcr EOF 终止，
在任何模型调用前失败；同官方 uv0.8.22 镜像 pull 恢复了第二次构建。
该 pull digest 为 `sha256:9874eb7afe5ca16c363fe80b294fe700e460df29a55532bbfea234a0f12eddb1`。

项目冻结版本：

- yocto-queue：72a8fa96a9d389765cdf2bb9c6daba8302fc375d；pnpm test；部分 drain/clear/reuse FIFO 回归。
- humanize：785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b；uv run --no-sync pytest -q；负数小数秒回归。
- referencing：f6adc7b74af8347e2c59c45256be7b8a8030a3f5；uv run --no-sync pytest -q referencing；
  registry removal immutability；suite 固定8a502de2f75cd436ecf023b350c1bd0698f3a395。

这些曾是 heldout cohort，现在已经参与实验，不得声称它们仍是盲测新项目。

## 已完成验证

最新 provenance 改动：RED 1 failed/1 passed；focused23 passed0.23s；
独立审查相关41 passed；完整 continual-learning **1078 passed in424.01s**；
pnpm typecheck、19工作区 packed manifests、目标 dry pack、diff check 通过。
报告保存于 project-verification-provenance-results.json。
没有生产 runtime 改动，因此不把研究 runner 的成功当生产新功能验收。

命令：

```bash
uv run --no-project --python /opt/homebrew/bin/python3 python -m pytest packages/continual-learning/tests -q
pnpm typecheck
pnpm pack:check
pnpm --dir packages/continual-learning pack --dry-run
```

Homebrew Python3.14 有 pytest；默认 uv3.13 没有。Bun1.4.1，Docker Pi1.0.2。
此前 install gate exit1：agent-teams,bdd-jev,btw,context,keyboard,monitor,plan-mode,
recap,skill-router,utils,vision 共11无关包未配置；continual-learning 已安装。
不要改全局设置来掩盖这些无关失败。更早仓库广泛检查有无关失败，非当前全绿证明。

## 必须保留的负面研究结果

1. 原18次 Docker（3项目×3轮）：最终 off2/3、on0/3，不能丢弃。
2. 首轮 DeepSeek 六臂已完整结束，目录 `.../docker/20261007T014740Z`，exit1、5/6：
   off3/3、on2/3；预期 Memory6/6 vs5/6；Harness3/3两侧。
   学习累计秒474.67 vs928.79；已知学习费用估算$0.115457712 vs$0.154381752，非账单。
   总transport200，其中main171、Jev29（providerRequests含Jev，不能称main200）。
   Jev190962输入/3364输出，估算$0.008020404。十一已写 Memory 在正例中未观察到误记，
   但没有专门负例率；候选独立生成，不能把总耗时差当因果开销。
   报告：deepseek-heldout-comparison.md 与 -results.json。
3. 描述拆分研究：真实13次Jev，false holds作者标注1→7；false-compatible0；拒绝采用。
   22176输入/1283输出，费估$0.000931392，median1084ms。
   description-counter-decomposition.md/-results.json；raw根
   `.../research/description-counter-20261007T023201Z`。
4. 结构视图研究：26次实际HTTP尝试，25个固定版本响应、1URLError不重试；
   12完整配对/1不完整，false holds1→1、false-compatible0，拒绝采用。
   44444输入/1426输出，已知费$0.001866648，失败调用费用未知；median1076.5ms。
   真实样本compatible概率.74→.88，仍低于.90；输入8911→17078近翻倍。
   evidence-structural-view-plan.md/-results.json；raw根
   `.../research/structural-view-20261007T024511Z`，manifest-v3 hash：
   `2f7256192f67fd87594e7bfa0556d0daed1128d9782c493f37d54edfa610981f`。
   12人工中英文开发样本+1复用失败，不是 blind heldout；没有 Memory 写入。
5. 此前 Noul、时间判断、描述上下文、检索cue等分支没有通过净收益标准，不要重新
   包装为已证明改进。检索cue曾使旧有效私人偏好由allow退化hold，因此未采用。
6. composed 固定主模型 native study（真实Jev28次）和人工开发90次曾改善部分判断，
   但主模型是fixture或样本人工，不能替代真实生成、新项目和完整原生行为结论。

描述/结构两项研究是官方HTTP真实Jev推理，但请求来自生产判断源码+离线SDK fixture
重建，并非原始 on-wire 字节回放。新增 questions 彼此独立，不可用 mock 声称效果。
旧 yocto 原始工具用 pnpm test|tail，无原进程 exit；作者正标签只是期望，不能
把该 hold 单独当成错误语义判断。保留旧标签与原始文件，补充限制，不事后改真值。

不要编辑 `jev-controlled-diagnostics.ts` 来修简单兼容问题：许多历史冻结 manifest
绑定其字节；新研究另写helper。也不要改已冻结 corpus、manifest 或raw result。

## 下一步与完成门槛

先解释已保留的新 on 失败与中断，完成可信真实对照；不能把没有JeV回执、服务失败、
候选生成失败或未执行探针统统算成同一种判断错误。然后按证据调整生成器/判断边界，
优先解决明确问题，不围绕一个样本重复优化。需要新的独立标注/未参与调优项目与
负例，覆盖推测、暂时故障、撤销、补充、冲突、限定范围、审批例外和未授权写入。

合格的净收益证据同时衡量有效知识落盘、误记、误拦、正确约束执行、成本与时延。
Jev放行率提高不是质量证明，正确拦截也可能是收益。不确定候选的独立应用必须
保留父进程权限与证明，不能为增加输出削弱安全。未证明净收益则继续调整或保持
相关实验策略默认关闭；不能宣称完整目标完成。

完成前逐项核验原始需求、类型/测试/pack、真实模型与原生执行、未知样本和回退安全，
审查当前源码而非依赖这份交接。按需求报告精确结果与无关失败。没有充分证据不得
把 goal 标为 complete。

官方资料（使用相关API/研究假设时重新读取）：
https://docs.typesafe.ai/models
https://docs.typesafe.ai/api
https://docs.typesafe.ai/model-jaggedness/jev-1.13
本地技能：`.agents/skills/typesafe-ai/SKILL.md`。
