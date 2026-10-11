# DeepSeek 4.1 Flash：协议 3 配对实验

2026-10-10，Asia/Shanghai。**控制器已修复，实验完成两题的全部预定模型阶段及六份独立评分；不足以确认 E2E 提高代码质量、整题完成度，或值得作为模型 review 的替代。** 本轮不再是“框架报错后没有比较数据”：有两题的配对交付补丁及独立代码评分，但完整合规流程对数为 0，结论只能是描述性结果。

证据目录：`runs/paired-resume-20261010/`。机器结果 `outcome.json`；结果表 `paired-results.csv`。旧协议及失败完整保留在 `runs/paired-fresh-20261010/`，旧的 3 次调用费用只计一次，不计入新效果。

## 配对结果

每题先生成插件关闭的共同初稿，再逐字复制为 A/B；review 后验证未改初稿，再执行相同 fix 模板和 20 次请求额度。两组均无隐藏评分、参考实现和最终评分反馈。B review 仅一次原生 E2E，没有追加模型源码 review。顺序固定为第一题 A/B、第二题 B/A，各一次，无择优重跑。

| 真实任务 | 初稿独立评分 | A 最终独立评分 | B 最终独立评分 | A/B 救回 | A/B 回归 |
|---|---|---|---|---|---|
| ADK env helper 与三个消费者 | 5/5，整题通过 | 5/5，整题通过 | 5/5，整题通过 | 0 / 0 | 0 / 0 |
| DSPy History 与 Evaluate 导出 | 0/3，整题失败 | 2/3，整题失败 | 2/3，整题失败 | 0 / 0 | 0 / 0 |

初稿整题完成率 **1/2=50%**；A、B 最终均 **1/2=50%**。两组任务完成率差为 0 个百分点。需求检查分组均从 5/8 改善至 7/8；这是分组检查计数，不是经过校准的通用代码质量分数，不能将部分修复称为整题救回。

ADK 三份交付均通过全部独立需求检查和 pristine 原始回归 **108 passed**。B 的产品源码与初稿相同，仅追加测试，没有救回代码缺陷。

DSPy 初稿是空补丁，执行阶段在读取后耗尽请求额度，没有交付实现。A、B 最终都完成 History 递归转换与 merge 修复，但遗漏 `Evaluate._prepare_results_output` 的 scalar prediction 分支：它仍将未转换的 History 放入输出，JSON 导出失败。两份最终公开检查均通过，原始 focused suite 均为 **24 passed、25 skipped**；独立完整需求检查和另一次断网双臂探针都实际复现 `TypeError: Object of type History is not JSON serializable`。因此公开通过不能替代完整任务评分。未运行官方 benchmark grader、项目全量测试或真实模型业务服务回归，不声称覆盖这些范围。

## 流程完成度及有效性

| 阶段报告正常完成 | A | B |
|---|---:|---:|
| review | 0/2 | 2/2 |
| fix | 0/2 | 0/2 |
| 完整 workflow | 0/2 | 0/2 |

共同 execute 为 1/2 正常完成报告；所有 10 阶段合计 3/10 正常报告、7/10 受固定请求额度截断。所有补丁均捕获，所有固定输入完整，模型返回标识一致；四条 workflow 的 `workflowValid=false` 均保留，不剔除其代码交付评分。

两份 A review 用满 8 次请求；四份 fix 用满 20 次请求。阶段安全时间上限为 40 分钟，本轮未触发该上限。六个阶段出现的 `modelErrors=1` 主要是额度拦截后 Pi 的错误事件，结合 `reason=request_allowance_handoff` 应归为阶段额度未完成，而不是远端服务失败或产品代码错误。无上游传输错误。ADK A review 虽无此错误事件，仍未完成报告。

这说明本协议的 15/8/20 请求分配未给多数阶段足够余量，限制了对“完成执行 → 完成 review → 完成 fix”的评价。不能用这些数据推断充分额度下的能力。没有在观察中间表现后提高某组额度、重跑、换题或混合协议；也没有把未完成阶段算成质量得分 0。

## E2E 实际发现到修复的证据链

| 任务 | 原生 E2E 实际返回 | 后续模型行为 | 独立验证 | 可归因范围 |
|---|---|---|---|---|
| ADK | fresh 公开命令通过；Jev 对完整行为证据给 0.40，`needs_review` | B fix 检查源码并增加测试，产品源码不变 | 初稿和最终均完整通过 | 发现证据覆盖不确定，不能称发现代码 bug 或产生代码修复收益 |
| DSPy | fresh 公开命令 exit 1；Jev 0.02，`not_fulfilled` | B fix 读取源码、实现递归和 merge，并增加测试 | 0/3→2/3；scalar 导出仍失败 | 正确暴露了失败信号；无法建立“E2E 定位具体缺陷→完成修复→全需求通过”链 |

B 的 review packet 只含原生结果，没有追加模型源码 review；但原生交接只提供命令失败/证据不足摘要，没有 stdout 堆栈或源码位置。具体定位由 fix 模型自行完成。A 同样达到 2/3，所以这部分改善不能单独归因于 E2E。

独立审查还发现复用 adapter 的 `observations.scope` 残留旧任务的 POSIX/Windows/MSYS2 文案。真实 TASK、命令、源码、公开检查均正确且两组权限一致，但这段无关元数据会污染 Jev 对证据覆盖的解释。冻结输入和失败记录未被事后改写；没有因它取消独立评分。它不影响独立代码检查，却进一步阻止将语义分数视为 E2E 质量收益证据。下一协议必须先离线纠正并回归这项元数据；不得悄悄改写本协议后合并效果。

## 成本与时间

所有用量均与原始响应独立核对：**134 次 DeepSeek + 4 次 Jev = 138 次计费上游请求**，缺失 usage 为 0。累计包括旧失败预检 3 次、新预检 3 次、正式阶段 132 次。无付费重跑。失败预检费用不退款、不剔除。

| 成本项目 | A USD | B USD |
|---|---:|---:|
| 两题 review + fix | 0.061462200 | 0.055693278 |
| 加各分摊一半共同初稿 | 0.074531508 | 0.068762586 |
| review + fix 阶段时间 | 826.91 秒 | 983.78 秒 |

观察到 B 的 review+fix 估算费用少 **$0.005768922（约 9.4%）**，但耗时多 **156.87 秒（约 19.0%）**。B fix 本身费用略高，主要节省来自原生 review 使用较少模型请求；两次语义服务共 $0.000137550 已计入 B。不能把少调用直接等同收益，也不能将额度截断的流程成本外推为正常完成流程的成本。

| 累计费用 | USD |
|---|---:|
| 正式配对阶段 | 0.143294094 |
| 旧失败预检 + 新通过预检 | 0.002090436 |
| **累计使用量估算** | **0.145384530** |
| **累计保守预留**：138 × $0.125 | **17.250000000** |
| 硬上限 | 20.000000000 |

总账在上游转发前以 flock、fsync、原子替换持久化预留；累计最多 160 次 × $0.125 = $20，输入与输出有逐请求上限。旧账本的不可变三条前缀及旧 manifest 哈希受 guard 检查。没有因为费用估算很低而释放预留或临时增加实验额度，因此大部分实际预算未花出。该保守分配也限制了阶段额度，是本次证据不足的原因之一。

价格记录见 `pricing.json`，依据 [OpenCode Zen](https://opencode.ai/docs/zen/) 和 [TypeSafe 模型文档](https://docs.typesafe.ai/models)。估算按完整 usage 和冻结费率计算，原始响应逐请求总和与阶段总和一致；实际账单未核验。实验转发账本不含不可观测的 Codex 平台编排/内部审查计费，不宣称其成本为零。Docker、主机资源、人工有效工时没有货币估价。

本次准备约 6 分钟（约 12:01 至 12:07），新计费预检完成后正式阶段于 **12:07:58** 开始、**12:55:52** 完成，墙钟约 **47 分 54 秒**；其中模型阶段合计约 34 分钟、离线评分约 13 分 22 秒。另有独立审查和报告时间；旧协议约 43 分钟准备单独保留。操作由代理完成，没有用户手工修补候选。不能将代理墙钟编造成人工有效工时。

## 修复、准备和完整性验证

旧控制器错误：报告已正常完成、自动 followup 被预期 409 拦截后，stage 从完整 `events` 统计模型错误，而 completion/review packet 已按报告边界裁剪。新实现统一从 `packet_events` 分类模型错误；原始尾部事件仍保留，额外上游请求或任何 `tool_execution_*` 事件仍使流程偏离。报告之前的错误不被吞掉。

新增回归先失败后修复；直接回放旧真实事件，并测试边界前错误、边界后工具 start/update/end、额外上游请求。另修正恢复账本上限绑定，加入累计前缀及跨阶段防并发重复启动锁。**17 项离线测试通过，独立审查重复通过**。真实 Docker Pi 离线夹具证明报告后拦截不会再使 modelErrors 增加，保留源码、阶段隔离和原生调用，零计费调用。此前离线夹具也分别保留，没有覆盖旧失败。

协议 3 在模型调用前冻结，独立批准绑定 32 个文件哈希。完整评分要求和输入未改；复用六份当前哈希一致的负例/参考控制：两题空补丁失败、完整参考通过、故意漏集成/导出路径的补丁失败。参考和隐藏评分仅 host 可读，没有挂载给模型。

真实 Pi **1.0.4**、`@fradser/pi-e2e` **0.1.0 + 冻结源码快照**；API 返回模型 **deepseek-v4.1-flash**，语义 **jev-1.13.0**。固定不可变任务镜像、实际 runtime 内容、完整提示词和源码哈希均在 `manifest.json`。API 标识不是托管权重哈希。

全部模型阶段结束后才开始隐藏评分；每份补丁应用到 pristine、断网镜像，仅执行原始测试、固定公开 contract 和 host 隐藏检查。候选新增测试及完整补丁保留供审查，不用候选测试制造通过。独立审查绑定六份补丁、六份收据和输入哈希，确认没有删除原始断言或修改评分器。ADK B 事件日志尾部有被终止截断的 JSON 行，保留为阶段截断证据，不解释为产品故障。

本轮未修改产品源码、发布包、提交远程修改或清理其他项目资源。旧运行保持原样。此前 E2E 包验证为 176 项通过、包 typecheck 和 pack dry-run 通过；本次控制器修改重跑了相关 17 项测试及真实 Pi 夹具，没有把旧包检查伪装为本次全仓检查。根 typecheck 的既有 continual-learning TS2322 单独保留，未跨范围修复。

## 统计不确定性与建议

这是两个预选真实问题的一次便利样本，不是随机抽样。A/B 整题结果两题均一致，没有不一致对，也没有完整流程有效对；不能确认优越、等价或一般 SOTA 收益。形式上的双侧配对精确检验 p=1 没有检验力；即使忽略流程限制，1/2 完成率的形式二项 95% 区间也约为 1.3%–98.7%，且便利抽样不支持总体推断。

一题初稿已完整通过，有明显天花板；另一题初稿为空且最终额度仍不足。这不是充分额度下强模型收益的好证据。不能把本轮相同评分解释成“E2E 没用”，也不能把 B 的低费用解释成“更划算”。

当前建议：**不据本轮把模型 review 全面替换成 E2E review**。E2E 可作为具有明确行为观察的辅助检查；`needs_review` 应保持证据不足含义，不自动扩展成代码缺陷或无目标修复。若另行继续研究，应先修正 scope 元数据、用离线数据验证请求额度能让阶段完整完成，并在新未见任务上重新冻结；旧题只能作诊断，不能混为新效果。更高额度或更少任务应在模型结果出现前固定。本轮按已冻结两题计划停止，不追加择优重跑。

## 复现入口

- `PROTOCOL.md`、`COVERAGE.md`、`selection.json`、`prior-run.json`、`manifest.json`：冻结协议与来源。
- `harness/test_report_boundary.py`、`offline-fixture-final/receipt.json`、`independent-review.json`：修复和启动前证明。
- `results/<task>/initial.patch`、`A|B/source.patch`、各阶段 `prompt.txt/events.jsonl/result.json`、`review-packet.json`：输入、交付与真实调用。
- `controls/<task>/*-final-score/`：六份独立需求评分、原始回归日志、完整收据。
- `independent-final-review.json`、`independent-scalar-probe.json`：独立补丁与实际缺陷复核。
- `cost-ledger.json`、`cost-ledger-requests/*`、`usage-audit.json`：累计计费及原始 usage。凭证不进入模型挂载或持久证据，传输使用临时 bearer 并脱敏。
- `outcome.json`、`paired-results.csv`、`provenance.json`：最终机器结果、版本与时间。

离线回归命令：

```bash
uv run --no-project --with pytest python -m pytest packages/e2e/tests/quality-pilot/runs/paired-resume-20261010/harness/test_fresh.py packages/e2e/tests/quality-pilot/runs/paired-resume-20261010/harness/test_launch_contracts.py packages/e2e/tests/quality-pilot/runs/paired-resume-20261010/harness/test_orchestration.py packages/e2e/tests/quality-pilot/runs/paired-resume-20261010/harness/test_report_boundary.py -q
```

付费入口已有完成标记、防重放检查及独占锁，不能覆盖重跑。复现当前结论无需再次调用模型。数据为 [SWE-Bench-ProMax](https://huggingface.co/datasets/swe-bench-promax/SWE-Bench-ProMax)，revision `014a4113c86327beacee3b85e567d32afd56ba56`；两题任务 ID、镜像及源哈希在记录中可定位。
