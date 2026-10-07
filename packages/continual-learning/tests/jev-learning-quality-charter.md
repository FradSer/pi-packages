# 学习质量与研究边界

本任务的目标是让插件可靠保存有用知识、保留正确约束，并减少误记和漏记。
Jev 是可选的判断工具；研究无需得出正面结论。没有净收益证据时保持默认关闭，
保留失败结果和未验证项。单个候选从提案变为放行只能作为诊断信号。

## 预先固定验收依据

- 在推理前冻结项目版本、任务、证据、预期事实与条件、配置、模型和费用边界。
- 区分已参与调优的探索样本、未参与调优的中英文样本和新开源项目；不重新包装为未见样本。
- 由独立审查核对原文支持、知识价值、隐私与例外。模型审查不是人工 gold；
  无可靠标签的样本只报告判断与行为，不能算误记率或误拦率。
- 对显式 Memory 要求，保留处理及未决原因；不得借低置信度静默丢弃或修改 Harness。
- 原始对照的任务、门槛、报告和失败保持不变。新的观察设计须在调用前单独冻结。

## 同时观察收益与损失

分别报告有效知识落盘、必须保留知识的丢失、误记、正确拒绝、误拦/未决、
新会话实际读取和使用、Harness 实际拦截与无关操作、耗时和已知/未知费用。
拒绝无依据候选可以是正确结果；放行数量不是质量指标。

下一轮工作流分别收集 Memory、召回与 Harness 证据，再汇总最终验收。
某阶段失败不能自动遮住其他可安全执行的阶段；缺少前提时明确标为未验证。
依然要求原生工具调用和副作用证据，模型口头拒绝不能代表 Harness 生效。
修复生成器和改善 Jev 判断必须分开比较，不能把候选过度扩写全部归因于 Jev。

## 采纳与停止条件

不得通过降低置信门槛、挑选有利重试、扩大写权限或改标签获得收益。
不得用更高放行率抵消必须事实、条件、隐私或许可边界的损失。
收益和安全、时间、费用分别列出，不用加权总分掩盖回归。
有明确局部修复证据可以保留该修复，但不能因此宣布插件整体更优。
没有净收益时保留 Jev 可选及默认关闭，并诚实报告假设未获支持。

当前 R17 为关闭2/3、开启0/3；它支持继续诊断，不支持整体改善结论。
@jev-template-tab-r17-final-results.json 为原始结果，
@jev-durable-core-research-plan.json 保留原先的前瞻研究方案。
@jev-durable-core-generator-manifest.json 为已完成的固定合成开发对照；
独立模型审查发现减噪收益及必须知识遗漏，因此未采纳实验提示。
它不属于未见项目或人工 gold 评估，详见
@jev-durable-core-generator-adoption-decision.json。

分离价值与完整性判断的48样本开发实验已完成80次真实Jev调用。
按冻结标签，不适合候选放行4→1，但有效候选放行20→10；7个标签遗漏中0个被确定检出，2个漏检、5个不确定。
新增10个有效hold为9个不确定加1个超时，不能都称为语义误判。
另16个新编写样本的baseline均为提案，通用description导致支持不确定，
因此不能证明新项目工作流改善。不采纳新门槛，不修改原标签或重试以美化结果。
已知79次用量、1次超时用量未知；无持久写入或召回/约束执行证据。
@jev-memory-quality-real-results.json 保留逐项结果；
@jev-memory-quality-adoption-decision.json 记录未采纳及下一轮待验证项。
后续Pi主模型使用cli-proxy / opencode/space-bunny-free；
@jev-space-bunny-model-probe.json 只证明隔离真实调用可用。

手选原文要求的分项完整性实验已完成20次真实Jev调用。
9个标签遗漏中，确定检出3→4，唯一误判完整变成不确定；11个完整仍识别8个。
两个恢复与两个新增hold抵消，新增hold均为中文，中文完整识别4→3。
48分项中38个确定正确、10个不确定，含5个缺失项仍未确定检出。
原文要求为人工选择，不能证明自动提取完整或真实持久学习净收益，故未采纳。
两种方法同批调用，耗时和费用不可假装分摊为各自或增量成本。
@jev-request-completeness-real-results.json 保留逐项结果，
@jev-request-completeness-adoption-decision.json 保留取舍及未验证项。
初次准备因实际配置路径未冻结而失败，0模型请求记录保留；修复后离线回归和
预检通过才执行推理，详见 @jev-request-completeness-prepaid-final-review.json。

### Automatic original-request text coverage pilot

`jev-user-request-coverage-real-results.json` records a separate once-only real
Jev comparison over the unchanged 20 development outputs. Code produces 30
exhaustive original-user text spans instead of the 48 manually selected
requirements. Exact UTF-16 reconstruction covers conditions and negation;
capacity failure returns no partial list. This is text coverage, not validated
atomic semantic extraction or durable relevance. Whole-entry context accompanies
each question. A fresh review found a backtick delimiter bug; a failing
regression preceded the exact-length closing fix.

All three methods share each API batch. Whole/manual/automatic judgments
respectively detected 2/4/4 of 9 incomplete outputs; mistakenly recognized
1/0/0 incomplete outputs as complete; and recognized 9/7/6 of 11 complete
outputs. Remaining outcomes were uncertain, not definitely detected errors.
Chinese complete recognition was 4/3/2. The API reported jev-1.13.0 for all
20 requests, with no errors and all usage known. Joint execution took 31.355s;
36,893 input and 2,088 output tokens yield a known estimate of $0.001549506,
not verified billing. Per-method latency and cost are not measured.

The production gate and default remain unchanged. This negative tradeoff is
preserved in `jev-user-request-coverage-adoption-decision.json`. No candidate
generation, Memory writes, recall or native Harness execution occurred. It is
not a new-project, heldout, human-gold or end-to-end effectiveness result.

### Selected main-model output-budget diagnostic

`jev-main-output-budget-real-results.json` records two once-only real Pi
readiness calls on cli-proxy/opencode/space-bunny-free. The actual request caps
were 524,288 and 8,192; only that selected model field differed in private
configuration. Both returned HTTP 429, with `model_cooldown` and approximately
6h36m remaining reported at execution time. Neither generated content. This
cannot establish an output-cap effect on a healthy model, nor learning quality.
CLI exit 0 did not imply model success; failed usage and billing remain unknown.
No plugin or global host configuration change was adopted.

Prereview caught resource defects in the private diagnostic runner. Its owned
proxy process now exits before advancing arms, and container removal requires
verified ownership and ID. A local blocked-socket regression reproduced the old
in-process proxy leaving an upstream socket open, then proved local closure after
owned-process termination. This fixture called no external model and does not
prove remote-provider cancellation. Both real arms recorded terminated CLI and
proxy process groups, settled container creation, and absent owned containers.
See `jev-main-output-budget-prepaid-review.json` and
`jev-main-output-budget-verification.json` for the separated evidence.
