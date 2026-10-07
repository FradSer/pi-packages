# 完整证据与语义对象分离的后续验证

2026-10-05。承接 @jev-cited-evidence-evaluation.md；目标仍是可选 Jev 提高实际
学习质量，尚未宣告整个目标完成。所有新外部判断都请求 `jev-1.13.0`。

## 已实现的修正

1. 24KB 是优选窗口大小。26–29KB 的完整工具条目单独成窗，不截断；全部请求
   仍须在第一次发送前通过64KB wire限制、32问题及最多12请求检查。
2. 每个反证窗口携带原始引用支持上下文，后来纠正仍优先。缺少支持语境不能
   被当作存在反证；所有原始条目仍完整覆盖。
3. 只有 rule.message 逐字等于已经校验的原始用户 citation，且代码已证明
   literal/family matcher 时，代码证明措辞相等并省略 explanation 判断。
   Jev授权、参数范围、完整反证与父层权限仍执行。改写提示仍需要语义检查。
   生成提示优先逐字保留原文范围、时效及批准条件。
4. 新 Memory 反证问题只比较知识正文，不携带 action、target、storageScope。
   否则“任务代理不要直接写学习文件”可能被误读为“不应记住知识”。完整原候选
   的隐私、分类、引用、support/relation、权限检查均保留；没有变更分类。

五项新回归均先 RED，再修复；新增引用测试13项，引用+原有 Jev判断测试40项
通过。两次独立只读安全审查验证大条目、逐字说明以及正文投影没有绕过原始
隐私扫描、已有 Memory关系、后续纠正、授权、作用域或父层写入控制。

## 同一输入上的真实比较

@jev-cited-context-replay-manifest.json 固定最新 Click/Mitt公开合成实验 plan 和
snapshot 的 SHA256。所有输入预检后才允许真实推理；未知或更改过输入拒绝。
`--preflight-only` 验证2组输入、零调用。私人标记来自公开合成测试，不是实际
用户私人知识。回放不写文件，不证明端到端效果。

- 仅追加支持语境的第一次比较，Click/Mitt仍均提案，完整保留失败结果。
- 研究影子只去除反证问题中的管理字段：Click仍提案，Mitt允许。
- 接入正文投影后，用完整相同证据/候选/支持语境/阈值做配对对照。before恢复
  旧管理字段，after使用当前生产问题：**2/2提案 → 2/2允许**。
  18次实际调用，89,283输入tokens，估算$0.003749886。
- 独立完整窗口回放也允许两组候选；对照仅去掉支持语境时两组均提案。
  18次调用，85,692输入tokens，估算$0.003599064。
- 当前生产判断器在6个固定长证据样本上仍保留2个有效事实、识别4个工具反证/
  偏好撤回，完整31/31或32/32覆盖。36次调用，117,956输入tokens，$0.004954152。

原始输出：@jev-content-only-context-shadow-real-results.json、
@jev-content-only-production-paired-real-results.json、
@jev-content-only-production-replay-real-results.json、
@jev-content-only-long-real-results.json。配对样本只有两组，有训练/调试重用，
不把2/2升级为泛化能力或跨会话实际写入结论。

## Harness 的真实结果与失败保留

旧短改写说明的两个长证据正例均误拦。完整原文说明重测第二轮，2个正例允许，
2个后来批准例外以 conflict 保留，2个 exact-only 扩张保留（不确定）。完整6/6
覆盖，36调用，159,667输入tokens，估算$0.006706014。
这是说明生成形状也改变了的比较，不能单独归因于省略一个模型问题。

第一轮逐字说明重测包含两项 timeout/unavailable，已保留；不能用第二轮成功
覆盖这些请求的未知成本。新增20项中英文 git-fetch/npm-publish边界样本全都
结构合法；16个无持久授权/缺少批准例外/扩大参数/其他项目的候选未放行。
4个正例中中文2项允许，英文2项仍不确定，整套失败；不修改原金标掩盖失败。
英文“with any arguments”可能有零参数范围歧义，尚未完成独立标注复核。

原始输出：@jev-harness-verbatim-real-results.json、
@jev-harness-verbatim-r2-real-results.json、@jev-verbatim-boundaries-real-results.json。

## 命令范围的代码证明与语义反证

R3 p-limit 的实际 Harness 候选用了字符类中的真实 TAB。它与 `\\t` 的正则
转义等价，原来的 tiny grammar 却未识别，退回了要求 Jev 理解正则的通路。
当前只规范化完整的 `[ 空格 TAB]` 字符类用于证明，不修改落盘正则；宽空白、
NBSP、CR、转义方括号、普通 `$` 及未知表达式仍走原有完整语义判断。

仅加入 Tab 等价证明的真实回放仍失败：授权和参数范围明确，完整反证窗口
仍不确定。6调用，36,419输入tokens，$0.001529598，保留于
@jev-tab-spelling-real-results.json。

先做研究影子，再接入：仅在 block 家族范围已经代码证明后，反证候选用精确
命令单词、真实 block action、ASCII 匹配边界、当前项目作用域和原 message
表达。删除管理 op/id 和 generated fixtures，不要求 Jev 再理解原始正则。
所有原始候选隐私扫描、父层权限、支持/参数授权和完整证据窗口仍保留。
其他 regex、confirm 和 disabled 规则没有这个投影。

- 同一 p-limit 输入、完整22/22证据、门槛的生产配对：before提案，after允许；
  6实际调用，36,055输入tokens，$0.001514310。
  @jev-tab-spelling-production-real-results.json
- 研究影子同样得到提案→允许，6调用，35,848输入tokens，$0.001505616。
  @jev-harness-meaning-shadow-real-results.json。先前研究包装器误用字段的失败
  单独保存 @jev-harness-meaning-shadow-wrapper-failure.json；它的两个反证处理
  在发请求前抛错，不是服务故障或模型效果结果。4实际付费调用、6次 judge
  尝试，不把内部尝试都记为网络调用。
- 接入后长证据第一轮含一项服务不可用，未完全覆盖，整体失败；34调用已知
  144,566输入tokens，估算已知下界$0.006071772，不抹去未知费用。
  @jev-harness-proved-meaning-real-results.json。
- 为服务失败做明确的第二轮全套重测，6/6完整通过：2有效禁止允许、2后来批准
  例外和2 exact-only扩张都未放行。36调用、158,407输入tokens、$0.006653094。
  @jev-harness-proved-meaning-r2-real-results.json。

两项新语义回归覆盖四种 literal/escaped TAB 拼写、无效范围、原文伪造、审批例外、
撤销、未证明规则及原 message/action 保真。独立只读审查13项引用测试通过；
补充探针确认投影前敏感 fixtures 仍拒绝，confirm/非block/disabled 路径未变。
它是对代码控制链路的验证，不是对真实模型必然识别所有例外的保证。

只有一个 p-limit 同输入改善，不升级为新项目端到端学习成功。

Docker导出隐私修正另加4项先RED后GREEN回归：超时错误、复制内容/合并报告、
截断边界、凭据路径名。原始复制先进入0700临时目录，全部路径预检拒绝symlink
和含凭据的相对路径；导出bytes替换已知transport凭据及JSON转义拼写，CRLF等
未含凭据的原始bytes保持一致。cp/rm的stderr先脱敏再取尾部。独立审查用fake
凭据复测通过，未读取真实key。旧两个Docker测试fixture更新为真实proxy字段
及临时复制目标；原“超时保留失败”“非零退出不能被passed覆盖”断言保持。

完整包检查曾报两个旧fixture缺少新proxy字段的失败（774 passed、2 failed），
已修复fixture，11项Docker相关测试通过；最终完整包复测 **777 passed，
242.49s**，无该变更引起的剩余失败。根类型检查、严格评估入口类型检查、
目标pack及安装检查通过；18包pack清单检查也通过。


## 弃用的影子方案

- 说明拆成“新增义务”“虚构事实”两个 Noul：12样本的4个正例仍误拦，未接入。
- 改写反证分类标准以区分临时故障/偏好不遵守：未改善真实项目判断，并出现
  一个长证据正例被保留；有服务失败，整体不完整。未接入生产。

全部失败数值保留于 @jev-explanation-shadow-real-results.json、
@jev-invalidation-context-shadow-real-results.json、
@jev-invalidation-long-shadow-real-results.json。
研究传输包装器只用于显式 paid CLI，不被 package index/extensions 导入。

## 当前端到端验证边界

- 程序类型检查、严格评估入口类型检查、目标pack通过；18个workspace pack清单通过。
- 内容投影后完整包测试770 passed，245.40s；新增受控诊断回归后，
  最新完整包测试 **771 passed，244.40s**。类型检查及目标包pack再次通过。
  原不受控诊断投影下该新测试先失败，修复后仅记录受信任标签及有限数值，
  拒绝服务端额外文字、未知标签或非数值概率。
- 本轮第一次真实 Pi smoke失败：legacy选择器输出被“expected exactly one JSON object”
  拒绝，导致后续学习未运行。Jev显式关闭，这不是Jev推理故障；不能沿用此前
  smoke通过声称该次成功。尚未取得第一次原始worker输出，原因未确认。
  保留证据的下一次复现中 selector、Memory、Harness、AGENTS 均应用，
  全smoke仍在后续验收失败；没有把它归因到第一次的selector错误。
  第三次保留证据复测通过：privatePreference、sharedFact、updatedSeed、
  learnedConstraint、agentsApplied、freshSessionRead、freshHarnessEnforcement、
  verifiedReceipts，以及实际 Bash 和 scopedGuidance 均通过。Jev仍关闭，
  这证明当前基础流水线可运行，不证明Jev效果。保留前两次失败，不据重试
  成功抹去随机失败；第三次公开合成验收证据位于受保护缓存
  `~/.cache/pi-continual-learning/selector-reproduction/10d0950b3166465c8eebf4fa742f9572`。
- R3 的3项目/开启关闭共6次 Docker串行已结束：关闭2/3、开启0/3。摘要
  `2cef105edc24f9062b2e8bebcc505a8517ca0bf9ae7f01b13365870301816ab7`。
  该镜像包含逐字说明、大条目及支持语境，**不包含后加入的正文投影**。
  Click/p-limit开启均因真实语义判断未通过；Mitt关闭在原生 Bash 验收缺少
  工具调用，模型拒绝不算hook执行证据；Mitt开启在 GitHub DNS setup失败，
  尚未进入学习。保留这两类基础设施/行为失败，不归因于Jev推理。
  36 Jev调用均有usage，207,066输入tokens、$0.008696772；主模型204次请求，
  费用未汇总，不记为零。@jev-cited-verbatim-r3-docker-results.json。
  该轮不含正文投影、Tab证明及匹配语义投影，必须分别验证更新版本。

另已冻结最终正文版本 `9ce6461ae9a4be35dbf7ce7572161ae3933648444302873fc0b550e88ac5811f`，
在同一已确认存活的串行前序程序退出并保存summary后才开始后续6次配对运行，
输出目录 `~/.cache/pi-continual-learning/docker/20261005-content-only-r4`。
冻结镜像不可与前序镜像混淆；R4已开始，尚未完成不计为通过。R4亦不含
后续的Tab证明及Harness匹配语义投影。

R4当前Click关闭通过、开启未整体通过；开启的真实Memory已decided/supported，
28/28证据、7/7调用完整覆盖，36,198输入tokens、$0.001520316。Harness候选
后来包含从一次`python: command not found`扩张到bare python/python3的指导，
整计划保留；没有为获得端到端通过而放行这个候选。p-limit关闭已持久化
Memory及安全镜像，但在新会话使用私人偏好的验收失败；不算已完成跨会话
使用。该轮其余执行仍进行。

完整修复版已冻结 `11b7bcb8d51b27dcf2de8da9836cf505e1c3e0bc2ee9f842710a48a60424d3a9`，
输出 `~/.cache/pi-continual-learning/docker/20261005-proved-meaning-r5-final`；
等待R4保存固定摘要后自动开始6次串行配对，主模型最多360请求。
先前候补 `cbf5142c0380767ca399b0b2e53afaf3cc040429af29172b172860df105b24d6`
在等待阶段、零推理时停用并保留manifest/镜像，因为独立审查发现导出漏洞；
不把它计入6次付费执行或完成轮次。


必须继续证明实际学习与跨会话效果；当前局部正向信号不代表整个目标已经完成。

## 后续修复：保留遗漏候选及原始引用

R4 已结束，3 项目共 6 次独立 Docker 执行：关闭 **2/3**（Click、Mitt），
开启 **0/3**。p-limit 关闭未完成新会话私人偏好使用；开启的 Memory 在两次
支持判断均不确定，Harness 两次父验证失败。Mitt 开启的 Memory 判断支持，
Harness 在 scope / counterevidence 不确定。Click 开启的 Memory 判断支持，
但 Harness 混入由一次 Python 临时故障推导的长期指导。不能把所有 hold
都标注为误拦截，也不能将单阶段成功升级为整个任务成功。
36 次 Jev 调用均返回 usage，实际模型 jev-1.13.0，201,158 输入 tokens，
估算 $0.008448636；主模型 182 次请求、0 provider errors，费用未汇总。
结构化结果：@jev-content-only-r4-docker-results.json。

按该混合计划信号，单次语义修复可去除不支持的 companion，但父代码将
被遗漏操作及完整原始引用重编号后保存为私有 pending proposal；剩余计划
仍完整重复父验证和 Jev 判断。空计划、新身份、改变 retained 原始引用都
保留原计划，不解除已有规则。没有修改概率门槛或允许部分未经验证的写入。
新增回归先失败再通过；独立复核发现引用截短漏洞，也以失败回归复现后
修复。父代码比较除 index 外全部引用字段，并保留重复引用计数。
最新完整包测试 **780 passed, 247.10s**。相关修复套件 **25 passed, 11.76s**；独立复核无剩余阻断问题，属于模拟边界
验证，不代表真实模型效果。root TypeScript、目标 pack、18 包 pack:check、
17 包 /18 settings check:install 均通过。最新版实际 Pi smoke 全部通过，
Jev 关闭；不作为 Jev 质量证明。

R5 已开始，Click 关闭在 setup 失败；其余尚在运行，不能提前汇总通过率。
最新候补 R6 已冻结源码
`474eea5081bb8694d90e22cae81131ce4ffb40f726f65affcdb0f5f7912b5d47`，
包含语义遗漏保留与原始引用验证；等待 R5 summary 后串行执行同样 6 个
开启/关闭项目，主模型预算 360 请求，实际凭据仅留在 host proxy。
它与 R5 的旧冻结源码必须分开评估；等待阶段不计为已进行真实推理。
输出：`~/.cache/pi-continual-learning/docker/20261005-retained-citations-r6`。

## 新 Memory 支持问题移除管理信息

R4 p-limit 两次 Memory 计划在支持判断都不确定。其候选正文和引用成立，
但原支持问题也携带 action、target、storageScope。只读对照仅移除支持问题
中的这三个管理字段，完整原始隐私扫描、引用、反证窗口、关系判断及门槛
都保持。该投影只用于父验证过的完全引用新 Memory；rewrite/delete/mixed
仍保留原有操作/保全知识语境。

真实推理与回归分开记录：

| 验证 | 样本/调用 | 误记（前→后） | 误拦截（前→后） | 输入 tokens / 估算费用 |
| --- | --- | --- | --- | --- |
| 首次只读 shadow：两份 R4 计划 +8 个既有中英文样本 | 10 /44 | 0→0 | 2→0 | 92,966 / $0.003904572 |
| 接入生产后，同输入、同判断门槛重复对照 | 10 /44 | 0→0 | 2→0 | 92,966 / $0.003904572 |
| 扩展：两份 R4 计划 +16 个既有中英文 Memory 样本 | 18 /76 | 0→0 | 2→0 | 115,860 / $0.004866120 |
| 生产长证据：正常事实、后续工具反证、撤回偏好 | 6 /36 | 0（反例4/4保留） | 0（正例2/2允许） | 117,716 / $0.004944072 |

以上误记/误拦截按整份计划计数（两份 R4 计划各含多个候选），不等同逐条候选计数。
全部调用有 usage，实际模型 jev-1.13.0。重复同输入不计为新独立样本；
扩展语料是此前固定语料的复用，不声称未见 holdout。扩展包含重复、补充、
冲突、推测、临时故障。10 样本生产对照中位耗时707→579.5 ms，扩展中
495→677.5 ms；不能声称稳定降延迟。各费用为按费率估算，并非账单。
这是候选判定的同输入对照，不是旧主模型 selector 或完整 Docker 学习流程
的优越性结论，也没有向 Memory/Harness 写入测试内容。

@evaluate_jev_support_projection.ts、@jev-support-projection-manifest.json 冻结
两份公开合成 Docker 证据的 SHA256；`--preflight-only` 10 样本、0外部调用，
`--expanded` 18 样本。对照先通过现有生产隐私与父引用验证，再在测试
transport 恢复旧支持管理字段；生产侧保持完整正文。原始候选及证据不会
写进报告；受控答案仅含已知标签和概率。结果分别见
@jev-support-projection-real-results.json、
@jev-support-projection-production-real-results.json、
@jev-support-projection-expanded-real-results.json、
@jev-support-projection-long-real-results.json。

新增行为回归 RED（管理字段让模拟判定保留）→GREEN；完整候选敏感字段
和未授权 private 仍在 transport 前阻止。独立只读安全审查通过，14项聚焦
回归通过。最新完整包 **781 passed, 246.23s**；root 类型、研究脚本严格类型、
目标 pack、18包 pack:check、17包/18settings check:install 全通过。
另修正 README 中旧的24,000请求上限文案：代码完整wire上限一直是64,000，
24,000仅为反证窗口的优选尺寸，本轮未提高请求上限。

R5 Click 开启的 Harness 修复已应用，但 Memory 仍在counterevidence不确定，
整体失败；不能据此汇总未完成的其余项目。R6旧候补
`474eea5081bb8694d90e22cae81131ce4ffb40f726f65affcdb0f5f7912b5d47`
在确认进程等待且未进行推理后停用，原manifest/镜像保留，标记零推理。
R6最终镜像已冻结
`d70610bbf869bb0d5a54096c2e73046d79461b4abf2fadacab5d6683c790b4f0`，
包含正文支持判断及遗漏候选保留；等待R5 terminal summary 后6次串行配对，
主模型最多360请求。输出
`~/.cache/pi-continual-learning/docker/20261005-support-body-r6-final`。

## R5 反证研究：信号不稳定，尚不接入

R5 p-limit关闭通过（学习、跨会话、原生Harness执行）；开启仍失败：
Harness真实支持并应用，Memory在3请求中的1个5秒超时，已有2请求usage
构成17,746 tokens / $0.000745332已知下界，不能当作无学习机会或解除规则。
关闭侧已全部结束：p-limit通过，Click与Mitt都在setup失败（1/3）；
开启Mitt仍运行，不提前汇总最终开启通过率。setup失败不能归因于Jev语义判断。Click关闭的GitHub DNS失败已确认；
Mitt关闭在npm依赖下载时失败，尚未进入学习。两个失败均保留，不能升级
为Jev关闭的语义失败。

针对R5 Click两份冻结计划，复用此前未接入的invalidation研究提示，明确
“不遵守偏好不等于用户撤回”；没有改生产提示、原始证据、分类、门槛、
超时或SDK重试配置。

- 首轮10计划、56请求，全usage，整计划误拦截2→0，误记0→0，138,420输入
  tokens、$0.005813640；@jev-r5-counter-research-real-results.json。
- 同提示6个长证据样本全部符合预期：2正常事实允许，4工具反证/撤回保留；
  36请求、118,466输入tokens、$0.004975572；
  @jev-r5-counter-long-shadow-real-results.json。
- 明确复测此前提示仍保留的旧Click/Mitt固定输入：新旧提示都允许，不存在
  新收益证据；18请求、88,688输入tokens、$0.003724896；
  @jev-counter-prior-failure-replay-real-results.json。旧失败记录未删除。
- 扩展到18计划后，原提示也允许两份R5计划；其中一个反例的新提示调用
  超时，缺1请求usage。17个完整配对的误拦截0→0、误记0→0，无新增收益；
  另1对未验证。实际88请求，已知160,606输入tokens、$0.006745452下界；
  @jev-r5-counter-expanded-shadow-real-results.json。不能把反例因超时保留
  当作“正确语义拦截”，不能声称18/18完整通过。

信号未稳定复现，所以没有将该counter提示接入生产。以上真实API调用与
R5 Docker使用同一凭据有时间重叠；可能影响服务延迟，因果未证实。这轮
超时不作为隔离负载下的延迟结论。后续不并行启动付费研究，R6只运行其
既定Docker队列；R5失败保留，不因疑似负载而改为通过。

研究统计已修复：完整实际模型+usage的计划才计入语义指标；timeout等
缺失推理单列，比较时再限制为双方完整的配对。将原来的全行统计抽成
@jev-paired-metrics.ts 后，以含正/反例超时及缺少模型/输出usage的两项
回归复现失败，再过滤不完整结果通过（2 passed, 0.05s）。
@jev-r5-counter-metrics-reassessment.json 为0外部调用的离线重新统计，
引用原始JSON的SHA256；没有覆盖原始真实结果或伪造新推理。
两份研究脚本严格TypeScript检查通过；完整包测试 **783 passed, 242.99s**。
补充的完整usage但服务timeout回归也先失败后通过（2 passed, 0.05s）；只有
受控语义判定原因才进入准确性统计。冻结输入SHA256与新增JSON引用检查通过；
生产代码本轮未变化。

## 评估完整性与运行观察补充（2026-10-06）

配对研究的complete判定也采用完整语义返回条件：实际模型、输入/输出
usage、受控语义原因缺一则不完整；空语料不能生成完整结论。含部分
usage和完整usage但服务timeout的场景在旧判定下复现失败，修复后
3 passed, 0.07s；有效的uncertain仍是可统计的hold。两份研究脚本严格类型
检查通过。完整包 **784 passed, 244.64s**。

只读检查Memory修复流程确认，候选名称、操作意图及隐私分类会保留；
当前真实失败主要为有效偏好不确定或服务超时，未据此放宽候选保留规则。
R5 Mitt开启已从setup进入实际Pi任务，等待其学习完成；R6仍等待前序
summary，两个具体进程均经活跃handle核实。没有并行付费研究推理。

## R5 最终结果与 R6 开始

R5 固定镜像 `11b7bcb8d51b27dcf2de8da9836cf505e1c3e0bc2ee9f842710a48a60424d3a9`
六个独立Docker执行全部结束：关闭 **1/3**、开启 **1/3**，总2/6。
关闭p-limit通过；Click的GitHub DNS和Mitt的npm依赖下载setup失败。
开启Click的Memory反证不确定；p-limit的Memory服务超时；Mitt全通过。
@jev-proved-meaning-r5-docker-results.json 保存控制回执及结果。

Mitt开启是真实端到端证据：实际修改开源项目回归测试；Memory与Harness
先各被Jev保留一次，然后共享边界内的独立修复通过；持久化private偏好与
safe事实，安全镜像字节一致，新会话读取完整Memory并实际运行验证命令，
原生Bash阻止git push、阻止副作用且允许无关Bash均成立。Memory支持修复
后使用4请求完整覆盖54条原始证据（3窗口）；Harness修复同样完整覆盖。
此镜像尚不含后加入的Memory支持正文投影和Harness遗漏候选保留，不能
归功于这些较新的改动。结果证明Jev开启的全流程可工作，整体1/3尚未超过
关闭1/3；其他infra与判断失败未删除，不证明普遍质量提升。

Jev实际46请求，45个返回usage，实际模型均jev-1.13.0；已知260,628输入
 tokens、$0.010946376费用下界。1个缺usage，不能声称总费用完整；主模型
172请求、1 provider error，费用未汇总。曾与只读研究有并发负载，相关延迟
与超时仍保留且有负载混杂限制。

R6最新冻结镜像 `d70610bbf869bb0d5a54096c2e73046d79461b4abf2fadacab5d6683c790b4f0`
已在R5 terminal summary验证后开始；Click关闭目前setup失败，Click开启
运行中。当前运行源码摘要与冻结镜像一致（研究测试/文档不属于runtime
摘要），没有并行付费研究；不得提前宣称该轮通过或降低原始判断门槛。

## 官方接口依据

按照 [Noul文档](https://docs.typesafe.ai/primitives/noul) 区分独立是非条件，
按照 [State文档](https://docs.typesafe.ai/concepts/state) 保留关联语境。
[模型文档](https://docs.typesafe.ai/models) 当前稳定和preview均指向1.13.0；
本轮没有通过改别名伪装模型升级。价格是输入token费率估算，未知请求成本保留
未知或已知下界，不是账单，也不包括主模型调用费用。


## 真实候选风险审计与修复提示截断（2026-10-06）

@jev-actual-generated-risk-manifest.json 固定两个真实 Harness 候选、原始冻结
证据及既有回执的 SHA256；@evaluate_jev_actual_generated_risk.ts 只读验证，
@jev-actual-generated-risk-audit.json 保存结果。本次为离线审计，0 外发请求，
没有重新生成候选或运行真实 Jev。两个候选都能通过结构、原文引用检查；
禁用 Jev 的对应检查会允许，但历史真实 Jev 回执都保留了候选。

R4 Click 候选把一次 `python` 缺失泛化成长期事实，范围包含实际存在的
`python3`；R6 Click 候选会匹配 `printf '%s' 'x;git push --dry-run'`，
该命令只打印文字。这说明部分 hold 有真实质量价值，不能一律当作漏检。
该对照只针对两个既有冻结候选，原始端到端失败仍保留，不是整体成功率证据。

新生成提示要求有明确整族授权的新规则优先使用文档中的 anchored ASCII
匹配，并把带操作符、参数的引用字符串纳入负例；保留 exact-only、审批例外
和旧规则保护。尚未声称它完整解释 shell 语义，也没有放宽 Jev 判定门槛。

修复回归先失败，首次追加长提示后仍失败：共享修复入口把每项错误截到
400 字，关键 scope 提示及旧有 exact-command 限制没有送达模型。现拆为
6 条短提示，每条小于 400 字；24 条上限不变。最终聚焦回归 **26 passed,
12.86s**，完整包 **785 passed, 250.54s**；根 TypeScript 检查、18 包打包
检查通过。安装检查 17 包/18 配置项通过，目标包 dry-run 打包通过。
独立只读审查未发现阻断问题，确认身份、原引用、复判、uncertain 提案门禁
未改变。R6 冻结镜像早于本次提示修改，不得把该轮结果归因于这项修复。

R6 当前 p-limit 关闭通过全部原生执行与新会话 Memory 检查；Click 开启的
Memory 已应用，但 Harness 两次判断未通过，因此整轮该项目仍失败。
其余执行未结束，暂不计算该轮最终通过率。下一轮真实推理继续串行等待
前一轮终态，避免同时付费推理造成的延迟混杂；服务失败仍保留。


R7已冻结镜像 `909012fddcc15da55f93294ce548a44e32772598dfecc4df932daedf9a525790`，
使用同一3项目、开关配对、6次独立容器执行、主模型360请求上限，等待R6
指定摘要后才启动推理。本地排队启动器在任何推理前修正异常路径的凭据
清理函数，镜像未变；没有覆盖已发生的失败或增加推理次数。真实结果待验证。


## 持久 Harness 独立质量审计（2026-10-06，0 推理）

R6 p-limit开启已结束：Memory 2条应用；Harness原始判断uncertain，修复
未通过父级结构校验，原提案保留。其原始候选还会匹配
`echo git push --dry-run`，补充为第三个hash绑定实际风险样本；只读审计通过。

更关键的是，R6 p-limit关闭虽然原流程passed，实际落盘规则也会误拦
引用printf和echo。这使原有总通过率无法充分代表学习质量。
@jev-durable-harness-quality-manifest.json 冻结R4/R5/R6已结束的13个真实任务
回执和已落盘Harness的SHA256，并绑定当前实际guardrail-engine。研究脚本
@evaluate_jev_durable_harness_quality.ts 用生产匹配器审计独立的5个命令样本，
不执行命令、不调用模型、不写生产文件；原流程状态不变。
@jev-durable-harness-quality-audit.json 保留完整受控结果。

同轮同项目均完成的5对样本：误拦案例 **5→0**，未落地约束案例 **0→8**，
全部5个匹配器样本同时通过的任务 **1→1**。缺失或保留的规则仍计算未落地
约束，不能凭减少误拦宣称完整质量提升。所有13个实际任务中关闭5个、开启
8个，样本数量不等且轮次未齐，不用于比较总体准确率。关闭有4个原流程通过，
但仅1个完整匹配器样本通过；开启有1个原流程通过，3个匹配器样本通过。
这区分了流程执行、规则落地与规则质量，也暴露了开启组仍然丢失约束的问题。

评估回归Given/When/Then先缺失模块失败（2 failed），实现后 **2 passed,
0.06s**；确认非法规则计incomplete、空样本不得成功、缺失规则计missed
constraint。研究严格TypeScript检查通过（显式Node类型，数组显式类型）；
初次独立研究检查的Node类型配置及隐式数组类型错误已修正。本段是离线
生产匹配器证据，不是新的真实Jev推理，也不是实际shell执行证明。
新测试不改变R7冻结运行源码或原始通过标准，生产插件本轮未改。


独立审查发现并修复评估边界：完整Harness顶层容器现在传给实际引擎，
非法learnedRules不能被省略后计为成功；代码冻结包括guardrail-engine、
legacy-harness运行依赖、评估helper及脚本自身；非空路径/缺失hash组合会
停止。新增整体容器入口回归先失败后通过，临时合成文件测试确认依赖改动
及缺失hash均停止。聚焦 **4 passed, 0.14s**，严格TypeScript通过；重新
只读审计的实际样本计数不变。此前完整包在只有前2个新增测试时为
**787 passed, 254.05s**，最终4个测试的完整包检查另行进行。

R6 Mitt关闭现已完整通过，最后的Mitt开启仍运行；R7队列仍经具体活跃
handle核实等待，没有把观察超时当作终态或重启推理。

评估工具的独立复核已通过：4个聚焦测试、只读重放、全部代码与输入hash
一致；原统计及配对统计不变，未发现新的实质性测量问题。

最终完整包验证 **789 passed, 261.60s**；根TypeScript及研究严格类型
检查通过。新增内容为评估与回归，生产运行摘要未变，沿用已通过的目标包
dry-run与18包pack检查。实际Docker Mitt开启容器仍活跃，R7具体队列
handle仍活跃等待R6 terminal；未提前归因新提示效果。


## R6 终态与下一步边界（2026-10-06）

R6六次独立执行全部终止，原始流程关闭 **2/3**、开启 **0/3**。关闭
p-limit和Mitt完整通过，Click setup失败；开启Click/p-limit的Memory应用，
Harness未通过；Mitt的Memory与Harness均保留提案。独立进程handle确认
已结束后，R7自动开始Click关闭/开启，未并行推理。
@jev-support-body-r6-docker-results.json 保存控制回执及原始结果。

实际Jev **33请求，33个usage**，模型全为jev-1.13.0，193,539输入tokens，
按官方输入费率估算 **$0.008128638**；主模型151请求、0 provider error，
主模型费用未汇总。没有把服务超时伪装成未知负例，也没有增加超时或调低阈值。
Mitt流程最终回执正常返回，并非生命周期死锁。

Mitt修复后的Memory方案保留用户要求的项目命令、private报告偏好和额外的
代码行为事实。最终停止位置是额外代码事实（candidateIndex 1）的
counterevidence uncertain；整个批次因此保留，所请求两条也未落盘。
@jev-memory-batch-r6-regression-manifest.json 对原方案、修复方案、冻结证据
和回执作SHA256绑定，仅是新的真实失败样本，不是新的推理或效果证明。
当前回执只报告首个失败位置，不能据此断言其他候选全部通过。

下一步判断必须考虑独立候选是否能完整分别判定；现有整批hold门禁不能
通过忽略不确定、丢掉原证据或未经复判的部分写入来绕过。只有完整判定、
独立且经过父级重新校验的候选才可能应用；显式请求、原始不确定候选、
隐私分类与现有Harness均须保留。服务异常或证据/判定不完整仍不得部分
放行。此处记录研究问题，尚未改变生产整批门禁。


## R7 首个任务与父级拒绝回执修复

R7 Click关闭setup失败；开启Memory实际Jev supported并应用，但Harness
初稿和修复都被父级拒绝，因此没有Harness Jev调用。初稿修复文件中的
受控错误明确为positive[3]未匹配、预期block却execute及report错误。
该positive案例是git全局选项出现在push之前的真实调用，不能用只识别
连续git push词的matcher替代该覆盖；也不能删除合法正例来让规则通过。
@jev-git-option-r7-regression-manifest.json 绑定实际修复任务及回执hash，
仅保存类别和索引，不记录命令或候选原文。先前5个审计探针未覆盖git全局
选项，有限探针通过不能升级为完整命令族覆盖结论。

真实失败回执仅写rejected、没有停止诊断。新增父级诊断只输出固定类别
fixtures/evidence/protocol/structure和计数，避免候选ID、regex、引用或
私密原文进入回执；空语义修复方案输出empty-plan。预算、权限、父级校验、
提案与apply门禁均未改。回归先缺diagnostic失败；首次测试误将可清理的
可选report当作拒绝，已纠正为真实无效cases修复场景；聚焦 **27 passed,
16.02s**。独立复核 **27 passed, 16.70s**，未发现阻断或信息泄露；缺失
cases容器目前归为structure，是粗粒度受控分类，未声称精确错误枚举。

根typecheck、18包pack、目标包pack dry-run、17包/18配置安装检查通过。
隔离临时Pi --print /harness真实CLI加载与只读slash分派成功，0助手回合、
未写Harness，使用本地不可访问模型端点且Jev明确关闭，没有付费推理。
该验证不证明新诊断的真实模型生成链；其边界由回归覆盖。R7冻结早于本次
诊断修改，不能把该轮结果归因于该改动。完整包最终验证进行中。

本轮最终完整包 **790 passed, 289.40s**；类型、目标pack、18包pack
及安装检查均通过。R7仍由同一活跃handle继续p-limit关闭组，生产代码
新增诊断不影响该冻结镜像。整体Jev质量优越性仍未证明，目标未完成。


## 完整候选停止信号与 Git 全局选项（2026-10-06）

原判断已经收到整批结果，却只解析首个失败。现在在全部响应通过协议校验后，
记录每个失败候选的首个停止维度；原总决策、首个原因和整批hold保持不变。
单次修复得到仅含候选索引、固定维度和固定原因的有界提示，不含证据、
私密原文或写入授权。服务不完整时不生成该失败列表，也不允许部分写入。
128候选边界仍符合Memory 16条/Harness 24条及每条400字符的已有限制。
两个回归从缺candidateFailures失败开始，聚焦56项与独立复核通过；
完整包 **792 passed, 279.55s**，目标严格类型、pack、18包pack及安装通过。
当时根typecheck受到无关并行agent-teams/subagents接口迁移影响：
agent_inspect缺失、limitAgentReadback缺失、pendingIntent inspect不兼容
以及未使用rows。没有修改这些文件以掩盖失败。

隔离真实Pi --print加载临时只读探针，确认两个候选停止位置均返回、
整体仍为propose、未写Harness。SDK使用fixture响应，1次mock请求、
0次外部请求；这是Pi加载/接口验证，不是实际Jev质量推理。第一次探针
未执行，因为临时jev:false正确覆盖了显式测试配置；修正隔离配置后通过。

R7六次独立Docker最终关闭 **2/3**、开启 **0/3**。Click关闭和p-limit
开启setup失败；Click开启Memory supported并应用，Harness父级拒绝；
Mitt开启Harness实际supported并应用，但Memory初稿和修复都在candidate0
counterevidence uncertain，故完整工作流未通过。14次Jev均返回usage，
实际模型jev-1.13.0、82,179输入tokens、估计Jev输入费 **$0.003451518**。
主模型131请求、0 provider error，主模型费用未汇总。
@jev-quote-scope-r7-docker-results.json 保留终态。该镜像冻结早于完整
候选信号和父级诊断修改，不能归因这些新修复。

依据R7真实Git全局选项正例拒绝，新增独立10探针审计：原5项保持，
增加同项目git -C .、git -c core.quotePath=false、git --no-pager
push正例，以及对应echo/quoted printf负例。Git官方接口依据：
https://git-scm.com/docs/git （2026-10-06读取）。原5探针冻结评估未修改。
新评估与全部依赖、17个已完成真实任务的回执和持久Harness均SHA绑定，
0外部请求、0命令执行、0生产写入；属于离线真实产物审计。
@jev-expanded-harness-quality-manifest.json 与
@jev-expanded-harness-quality-audit.json 保存扩展边界。

6对同轮同项目可比任务，关闭/开启误拦截 **5/0**，漏拦截 **18/26**，
完整10探针通过 **0/0**。17样本不等量，不能用总量直接比较准确率。
缺失规则仍记为漏约束，未将拒绝写入计为成功。有限新探针同样不是
完整shell语义覆盖；它们明确推翻先前仅bare-command探针的充分性。

Given/When/Then与prompt回归先RED（缺Git选项说明），然后补充生成及
单次语义修复提示：保留合法同项目选项正例、打印负例，不删除案例、
不贪婪搜索，不扩大exact/project边界，不修改旧规则或Jev门槛。
聚焦 **37 passed, 14.46s**；独立审查未发现问题，新增提示288 ASCII
字节，所有Harness修复提示最多9条，仍在400/24原限制内。
提示改进的真实效果尚待新冻结Docker验证，不能由单元测试推断提升。


本次最终全包 **794 passed, 291.67s**；目标严格类型、目标pack dry-run、
18包pack、17包/18配置安装检查通过，差异空白检查通过。最新根typecheck
仅剩packages/agent-teams/tests/tool-param-schema-fixture.ts:91、92两处
agent_inspect引用错误；先前subagents错误已由并行工作消除，未冒充本包修复。
扩展离线审计独立复现与保存结果完全一致，无新增阻断发现。

R8已经按顺序开始，冻结sourceDigest
`708467513e1939691dff48cb423d87cd45899ab512ce5cf012ed5975180ea45b`，
镜像`continual-learning-projects:708467513e193969`，主模型请求预算360，
三个固定项目off/on共六次独立运行。R7终态确认后才开始付费调用，
无并行付费研究；不调低判断阈值、延长超时或放宽写入权限。
结果尚待终态，不能提前判为改进。

R7两次setup失败的原始git-fetch记录均是Docker内github.com DNS解析
失败，尚未进入学习阶段；它们保留为环境失败，不能视作Jev语义误判。
本轮R8 Click关闭已完成相同固定提交拉取、依赖及上游测试并进入真实
学习任务，不通过重试旧失败样本改写R7终态。

R8首个Click关闭任务：Memory写入、private/safe镜像、新会话完整读取
和测试命令验证全部通过；原生Harness阶段仍失败，因为模型拒绝执行，
未观察到真实Bash调用。保留为失败，不将模型拒绝算作钩子拦截证明。
生成的持久Harness在原相同10探针离线检查中 **10/10**，0误拦、0漏拦；
@jev-r8-click-off-quality.json 绑定回执、Harness、实际审计程序及依赖。
这是单个关闭组的生成规则进展；开启组尚在运行，既不是真实钩子证明，
也不证明Jev效果或提示更改的因果优势。R8总体仍等待完整终态。


## 独立原生钩子验证与 R8 初步停止信号

R8 Click开启Memory遭遇5秒服务超时，3/4已发送请求完整返回、只覆盖2/15
原条目；保持propose，已知14,332输入tokens及$0.000601944下限，不作
完整费用或语义漏检结论。Harness初稿和修复都在support uncertain，
但新candidateFailures已真实返回受控位置。未因未知放行、重试或延长
超时。p-limit关闭真实任务也停在real-regression-task，尚未归因。
R8原配对流水线继续运行；未在运行时并行付费研究。

新增native_harness_probe.py用固定安全工具请求驱动真实Pi，独立于主
模型是否拒绝执行。十个案例逐一配对原生Bash请求和返回结果；本地git
替身对每个push只写临时标记，不调用实际git push。空规则仍报告五个
漏约束及五次本地副作用；不会用口头成功或缺失调用代替钩子证据。
初次RED是缺helper，之后实际结果发现钩子返回配置message，修正了
先前错误期待的通用前缀；与现有learned_block_result保持同样的精确
message证据，不改生产钩子。纯TypeScript固定provider原型曾遇本包
旧peer类型与根Pi1.0类型的私有类冲突，已移除该任务新建原型，改用
loopback OpenAI transport fixture，不强制依赖升级或类型强转。

独立审查发现继承BASH_ENV/HOME及Git配置不能证明宿主隔离。新增
BASH_ENV写临时标记回归先RED，然后改为环境白名单、临时HOME/XDG/
TMPDIR、空Git模板/钩子及隔离Git配置。宿主externalRequests现在是
null、networkIsolation为not-enforced-host-probe，只有fixture不转发
这一事实为0；没有把未测量网络记成0。三项测试及复核通过，复核未
独立运行Docker，范围明确。旧探针结果保留在
@jev-r8-click-off-native-probe-initial.json，因初始宿主隔离声明过强而
被新结果替代，不能引用它证明最终隔离。

修复后的helper在新建、无网络的独立Docker上重测R8 Click关闭持久
Harness，使用原冻结镜像中的Pi **1.0.2**：11次本地fixture请求、10个
原生tool results，禁止5/5、允许5/5、禁止副作用0；外部请求为0的
依据是docker --network none。@jev-r8-click-off-native-probe.json 绑定
原Harness原始hash及实际探针程序hash。不是付费Jev/主模型推理，不将
原R8原生模型拒绝造成的workflow失败改成成功。生产代码未因探针修改。

本次最终包验证 **797 passed, 250.47s**；目标严格类型、最新根类型、
目标pack、18包pack及17包/18配置安装检查均通过，差异空白检查通过。
先前根类型的无关接口失败已由并行工作消除，本包未改那些接口。
此前796项运行早于第三个BASH_ENV回归的收集，不用它替代最终797项门。

@jev-harness-support-r8-regression-manifest.json 对Click开启真实支持
不确定的历史proposal、原snapshot及report作hash绑定。只读父级结构/
引用/fixture复核0错误，五个额外匹配探针通过；这不等于完整语义授权
证明，因此未预设expectedAllow=true。拟研究支持问题只呈现约束文案
和动作、保留所有独立scope/counter gates，须配对真实推理及负例后
才能决定是否采用。研究尚未开始付费调用，生产判断题未修改。
R8同一handle继续p-limit开启组，不能提前汇总总体结果。

## R8 终态与支持问题配对研究

R8同一运行handle终态exit 1，六个独立Docker任务全部结束，关闭Jev
**1/3**、开启 **0/3**。Click关闭保留模型未调用原生Bash造成的失败；
p-limit关闭缺持久Harness规则失败；Mitt关闭完整通过。开启组Click
Memory超时、Harness支持不确定；p-limit Memory应用、Harness支持不确定；
Mitt Memory应用、Harness初稿范围不确定、修复超时。原失败门槛未降低。
@jev-all-failures-git-options-r8-docker-results.json 保存冻结digest及原汇总。
37次Jev请求中35次有usage，已知198,990输入tokens、输入费用下限
$0.00835758；两次usage缺失，不能报告完整费用。主模型178请求、2错误，
此处没有汇总主模型费用。上述原生隔离探针不改变原流水线结果。

R8终态确认之后，顺序执行只读真实Jev配对研究。冻结16个中英文标签
样本及两条无标签真实历史proposal。父级结构/引用/fixture检查先通过；
SDK实际返回模型jev-1.13.0，34次真实请求，已知65,523输入tokens、
$0.002751966输入费用。只改新命令规则support判断呈现的自然语言文案
及action，所有scope/counter题、原始证据、阈值和权限不变。
@jev-harness-support-real-results.json 保存hash、受控概率及结果，不存原文。

16个标签样本全部得到有效语义结果：两组均0误放行、6误拦截，没有
改善。六个忠实正例原组全停在scope；改写后四个转为support不确定，
两个仍scope不确定。原组英文忠实约束support .95、同义改写 .92，
但scope的same+narrower只有约.72；支持改写没有解决范围瓶颈。
真实p-limit两组均不确定；真实Click在当前复现输入边界检查即停止，
没有请求，标记bounds/incomplete，不能当语义错误或推理成功。整项
研究complete=false；标签子集完整和真实复现未完成必须分开报告。
生产代码未接入该研究改写，未证明提升，不用mock替代效果证据。

新研究只对字符串完全等于固定有限Git匹配式的scope/counter候选，
用代码证明的匹配语言描述替代regex；支持题、全证据、选项及阈值不变。
未知表达式不变，匹配描述不是权限证明。新回归先因缺模块RED，随后
4项GREEN、严格类型及18样本/16标签/0请求预检通过。先独立复核并冻结，
再顺序真实推理；研究本身永远不产生生产写入资格。

### 研究路径纠正（前述结果不可直接用于生产采用）

随后接口复核发现两项研究脚本漏传validate第六参数harnessCitations。
它们确实发送完整snapshot，但走旧全证据路径，没有引用支持与独立
counter窗口。上文“scope/counter保留”应限定为保留当时实际生成的问题，
不能理解成已经覆盖生产引用路径；真实Click旧路径bounds也不能推断
生产窗口路径同样无法容纳。冻结脚本与结果均保留，不改写旧统计。

第二项旧路径真实研究@jev-harness-git-scope-real-results.json：34次请求，
69,142输入tokens、$0.002903964输入费用；16标签误拦6→2、误放0→0，
有效调用中位时长420→435ms。仍complete=false，两个真实案例无标签。
该正向信号仅支持进一步研究，不支持上线；全量证据撤回复核尚未测到。

新增validateHarnessResearch只接受非空原始计划引用，并精确传给生产
judge。接口回归先RED后GREEN，5项通过、严格类型及18/16/0预检通过。
@evaluate_jev_harness_git_scope_cited.ts和独立manifest按修正后的生产引用
路径重新冻结；原阈值、权限、父级检查、模型和请求预算不变。后续必须
依据这一修正版真实结果，再用未参与设计的样本评估，不能复用旧路径
6→2作为生产改善结论。本轮生产扩展未修改。

## 生产引用路径与未参与设计样本的真实结果

修正版首轮已完成推理但长stdout恰在65,536字节截断。保留原缓存输出，
@jev-harness-git-scope-cited-truncated-metadata.json仅保存完整头部及rawhash，
reportComplete=false；其中82请求/161,318输入/$0.006775356只作已报告
费用记录，不拿缺失的逐项结果证明质量。复核后新增文件输出版本，
首次请求前wx独占预留报告；不可写路径RED曾触发80个mock请求，修复后
0请求。已有文件测试0请求、原字节保留。8项回归通过。测试输出契约
时隔离历史codeFreeze检查，真实推理不使用该stub。

重新按相同冻结样本完整顺序推理，@jev-harness-git-scope-cited-real-results.json：
18样本、16标签、82真实请求，complete=true。标签误拦 **6→3**，误放
**0→0**；真实Click和p-limit都完成全证据窗口判断但仍支持不确定，
无标签不进入准确率。161,318输入、$0.006775356输入费用，调用中位
时长577→529.5ms。所有模型回执jev-1.13.0，无阈值、超时或权限放宽。

设计之后、推理之前冻结20个新样本（英文10、中文10），8正例、12负例，
包含分支/当前任务/其他项目范围、批准例外、后来撤回、confirm弱化
禁令及无关临时工具故障。中文负例候选与证据都中文。独立标签复核、
父级检查、类型和预检通过；pilot终态后才开始，无并行付费研究。
@jev-harness-git-scope-heldout-real-results.json：80真实请求，complete=true，
误拦 **8→5**，误放 **0→0**；81,748输入、$0.003433416输入费用。
这是有限精确matcher及这20个样本的结果，仍有五个忠实约束被持有，
不是任意表达式或完整学习流水线优越性。

据此仅接入经证明的有限Git匹配式：scope/counter呈现代码证明的
匹配语言；support仍原始候选，引用/完整证据/隐私/现有Harness及
阈值不变。未知、禁用及非addRule表达式保留旧路径。生产回归先RED
后GREEN，另验证block/confirm的unsupported、uncertain、scope扩大、
counter冲突及服务不可用全部保持propose。此次没有采用支持题改写。

本次五次顺序真实研究（含已明确标注的旧路径两次和截断一次）合计
312请求、已报告539,049输入tokens、估算输入费用$0.022640058；其中
截断研究只保留头部，不能作逐项效果证明。这不含R8或主模型费用。
最终heldout两组中位调用时长479.5→426.5ms，单轮小样本不能据此
声称稳定延迟改善。剩余五个heldout正例两项support不确定、三项
counterevidence不确定，下一步仍需针对这些真实停止信号审计。

独立审查最终生产与prompt没有新增阻断问题，37项Jev及generalization
检查通过。新镜像sourceDigest
`a385ac89115b1ddb8da1671235dbddbfb1cc4e839586bb7e3415c7cc2e2630ea`
已冻结，宿主摘要与镜像一致。网络关闭的真实Pi **1.0.2 --print**验证
有限模板：10个实际原生tool results，禁止5/5、允许5/5、禁止副作用0，
外部请求0由network none保证。@jev-finite-git-native-probe.json 保存结果。
该步骤使用固定fixture provider，不是真实模型/Jev推理；证明原生
执行匹配，不证明生成学习候选或模型授权判断。

最终修改后的门：**808 passed, 253.26s**；根类型、目标严格类型、目标
pack、18包pack、17包/18配置安装及diff空白检查通过。803项运行收集
早于最终回归，不能替代808项。本轮无新增无关失败。

R9按上述冻结digest启动：输出目录
`~/.cache/pi-continual-learning/docker/20261006-finite-git-scope-r9-final`，
三个固定项目off/on各一次，jobs=1、主模型请求上限360。主模型当前
配置bailian/qwen3.8-flash，配置输入/输出计价0.15/0.47每百万tokens
（配置值，不是费用发票）；有效凭据存在，密钥未输出。Jev继续固定
jev-1.13.0。R8及所有研究已经终态，未并行付费实验。R9结果待终态，
仍保留原完整学习、持久产出、新会话读取及原生执行门槛，目标未完成。

## R9 终态与有限授权路径研究

R9 同一执行句柄已终态，六次独立执行未重启。@jev-finite-git-scope-r9-docker-results.json
保留原门槛：off **1/3**、on **0/3**，主模型249请求/0传输错误，Jev
45请求且45份usage完整，实际模型全部jev-1.13.0，313,681输入tokens，
估算Jev输入费用$0.013174602。Click-off没有原生Bash尝试；Mitt-off的
`cd /work/mitt && git push --dry-run`实际未被裸命令模板拦截，产生本地
Git替身标记；不是外部push。@jev-r9-mitt-wrapper-regression.json 保存
受控失败事实与原始文件hash。on三项目分别停在Harness、Memory、Harness
判断；不把完整证据覆盖等同于语义准确。历史结果不因后续修复改判。

下一项只读研究将精确有限block模板路由至已有小命令族的authority、
explanation、family判断，仍保留所有引用、完整counter窗口、权限和阈值。
先2项mock边界回归、零请求预检及独立审查；实验代码仅编译自有临时
副本，不修改生产扩展。新manifest修正总研究预算144误记为实际192；
真实请求之前修正，单判断生产限制不变。R9终态后才顺序调用真实服务。

@jev-finite-authority-development-real-results.json：36个复用开发标签加
1条无标签真实Click失败，152请求，complete=true，误拦 **9→7**、误放
**0→0**，190,271输入/$0.007991382估算费用，中位调用383→381ms。
真实Click两组仍scope不确定；不进入准确率，不声称修复真实流水线。

@jev-finite-authority-heldout-real-results.json：设计之后且推理之前冻结
24个新样本，英文12/中文12、8正/16负；96请求，complete=false。
基线24项完成、误拦4/误放0；实验23项完成、误拦6/误放0，另1项
invalid-response。缺失项不当作正确或免费。95,190已报告输入tokens，
$0.003997980估算费用。没有重试以挑选结果；**不采用此实验路径**。
两个研究248真实请求、已报告285,461输入/$0.011989362，不含R9或主
模型费用。总体仍未证明可选Jev提高完整学习质量。

## 当前项目目录包装覆盖修复

新Given/When/Then回归先RED（缺少模板模块），再GREEN。父级绑定的
简单绝对repoRoot生成有限proposal模板，保留裸git、同项目cd绝对路径
三种安全引号拼写及cd .；其他项目、打印字符串、非&&连接符、垂直/
Unicode分隔仍负例。特殊shell路径不猜测，提示验证/报告覆盖限制。
这仅改善生成提示，现有落盘规则、权限、Jev语义门和执行器没有迁移。
新的包装表达式未获得Jev快捷路径；未知表达式仍走一般判断。

@jev-project-wrapper-native-probe.json：独立Docker network none、真实
Pi1.0.2 --print、固定loopback工具provider，16原生结果，禁止9/9、允许
7/7、禁止副作用0、外部请求0。额外4种当前项目cd实际拦截，两种打印
包装字符串允许。其他项目负例由离线回归验证。该原生证据使用新模板
和已有执行器，不是真实模型生成或真实Jev语义证据；R9失败保留。

新样本两组中位调用375→383ms；本次没有延迟改善证据。invalid-response
也返回了完整usage，费用已包含；语义评估仍缺1项，不用费用完整性
掩盖结果不完整。独立包装覆盖审查相关28项通过、类型通过，无可操作
发现；审查不证明任意shell语法或实时生成质量。

当前修改最终门：**811 passed, 254.63s**；根TypeScript、目标两个模块
严格类型、目标pack dry-run、18包pack、17包/18配置安装检查、diff空白
检查均通过。没有新增无关失败。@jev-finite-authority-adoption-decision.json
记录不采用决定。下一研究信号是分开审计lasting授权与完整证据窗口的
反证歧义；这只是后续方向，不是已经验证的改善。当前总体目标保持未完成。

## 反证判断职责拆分研究（尚未推理）

当前生产Harness反证题同时问冲突/扩大/缺少持久授权，原文支持和scope
已有独立题。这是可能造成无关窗口误持有的研究假设，不是已证明原因。
遵循TypeSafe官方Choice文档的固定互斥选项与独立判断语义：
https://docs.typesafe.ai/primitives/choice 。构建指南此次网络读取失败；
当前技能说明与已安装SDK提供补充，不虚构新接口。

只读transport实验仅改变counter_*的instructions.question；请求state、
原文候选、criteria、support/authority/scope、所有完整窗口以及阈值保持
一致。题目明确保留先前条件、后来更正/撤回/例外、验证观察与原索引；
无关工具故障和模型猜测不能修改用户授权。原文支持仍独立强制验证。
mock回归RED缺模块、GREEN1项；不能作为效果证据。

冻结38个复用开发标签（24Harness/14Memory）和两条无标签R9实际
Click Harness、p-limit Memory失败；p-limit new-only计划、完整96条
snapshot及已有dossier的0个Memory正文均hash绑定。不选子候选、不删
原文窗口、不猜分类。另一组24个新样本，中英各12、Memory/Harness各12、
12正/12负，在首次推理前冻结。父级引用检查、类型和零请求预检通过。
研究总请求上限每组256，实际每判断生产限制不变。输出必须wx独占
预留，原始state/正文不写报告，结果记录模型/费用与不完整原因。

独立复核发现6条中文Harness继承language=en及--live与--preflight-only
并存会选择付费模式。首次推理之前修复标签、更新hash；模式回归先RED
后GREEN。预检现完整走fixture transport，验证开发174/新样本96次请求
和每条完整覆盖/请求字节，outboundRequests=0。复核2项测试、类型、
两个预检及hash全部通过。清单明确每组256/组合512最大上限，计划270；
不是将单组上限误写为合计。所有先前推理句柄已终态，开发组才开始，
没有并行付费实验。生产扩展此轮未改。

反证拆分真实推理两组均已同一句柄终态，无重启或并行付费：
@jev-counter-development-real-results.json：40个计划/38标签，174请求，
complete=true，误拦4→2/误放0→0；14个Memory标签两组0误拦/误放，
改善只在24个复用Harness标签。两条无标签真实R9失败保持原停止维度：
Click scope、p-limit counterevidence；不把建议持有当作无机会或丢弃。
298,353输入/$0.012530826估算费用，中位调用332.5→334ms。

@jev-counter-heldout-real-results.json：24个新标签，96请求，complete=true，
误拦4→4/误放0→0；Memory/Harness各2个正例仍被持有。81,424输入/
$0.003419808估算费用，中位329→328.5ms，不构成稳定延迟改善。
两组全部模型回执jev-1.13.0，合计270请求，379,777已报告输入tokens，
$0.015950634估算输入费用；不含主模型/历史研究。生产扩展保持原样，
@jev-counter-adoption-decision.json 明确不采用；新样本和真实失败都
不支持总体改善，不以复用标签的4→2掩盖该结论。

剩余4个新样本误拦全部停在counterevidence：中英Memory各1、Harness各1，
共同场景是用户已给事实/禁令、随后assistant提出未验证推测。
@jev-counter-provenance-audit.json 用离线角色统计绑定完整结果；实际
p-limit第2窗口没有用户条目，但有10个toolResult/9个assistant，不能
因没有用户条目就删掉它：验证工具结果仍可能改变事实。来源角色是
provenance，不是事实真伪标签。后续应检验明确的来源身份是否改善
角色理解，避免猜测助手内容能修改用户授权；当前没有该方案效果证明。

本轮最终验证：**813 passed, 253.02s**；根TypeScript、研究runner/shadow
严格类型及目标pack dry-run通过，独立审查两项修复复核通过，diff
空白检查通过。本轮生产扩展未改，因此没有新增运行时改善结论。
目标保持active；没有发布、用户配置改写或降低原验收门槛。

## 完整证据来源身份研究（首次推理前）

前一实验剩余误持有集中在未验证assistant推测。本轮检验额外结构化
provenance是否有帮助，不更换上一轮已拒绝的counter题。官方State文档
https://docs.typesafe.ai/concepts/state 建议命名JSON字段清晰呈现关系；
文档不保证本项目效果，必须以固定样本和真实推理验证。

@jev-source-provenance-shadow.ts 仅在原indexed entry旁增加sourceProvenance。
role取自message.role，回退直接entry.role，与父级snapshotEntryRecord
优先级一致；不读取内容中的role、tool name或引文来确定身份。原文、
索引、全部窗口、全部问题和准入门保留。标记provenanceOnly，不判真伪，
不变更隐私，不授权任何写入。toolResult仍保留事实检查能力；其输出
不能给予用户授权。未知来源不猜测；非cited原始输入保持原请求。

2项mock边界回归先RED后GREEN（缺模块失败），覆盖原文保留、嵌套角色
优先级、工具引文伪装user、unknown及unsupported/scope/conflict/unclear/
unavailable完整持有。62个复用标签和两条无标签R9实际失败冻结；
预检270个完整fixture请求/0外部请求。32个新样本首次推理前冻结，
中英各16、Memory/Harness各16、16正/16负；预检128个fixture请求/
0外部请求，测试助手伪造更正/授权、工具打印角色、真实用户更正/例外、
真实工具观察以及目标/临时限制。类型通过，独立审查待完成。

新研究预算每组320/两组合计640请求，计划398；增加是为了包含全部
历史标签与真实证据，不是放宽单判断限制。生产每判断12请求、完整
窗口、64KB、超时/重试及阈值均不变。全部上轮推理已终态；本组
尚未外部调用，不把mock当效果证据。

来源身份独立复核代码/语料/哈希/完整预检通过，指出真实p-limit重放
包含合成私密偏好，研究配置allowPrivateMemory=true必须明确，不能
声称仍使用默认拒绝配置。已有用户授权涵盖独立Docker与付费推理；
@jev-source-replay-privacy.json 离线验证该private/preference候选及原引文
匹配测试生成器确定性marker，不输出marker、不读取宿主个人Memory。
这里是明确的合成私密研究opt-in，保留classification，生产默认权限
没有修改。此限制写入两组新manifest后才启动真实调用。

来源身份开发组已同一句柄终态：@jev-source-development-real-results.json
64个计划/62标签，270真实请求，complete=true；误拦 **8→13**、误放
**0→0**，两条无标签R9实际失败仍停在原维度。实际模型全部jev-1.13.0，
390,996已报告输入tokens，估算输入费用$0.016421832，中位调用372→
384.5ms。新增5个持有，其中3个counterevidence、2个support；四项
中文、一项英文。来源描述也影响支持题，不能声称只是反证受益。

@jev-source-adoption-decision.json明确拒绝。因为复用开发数据已退步，
32个预先冻结的新样本**没有调用**，保留未查询状态；不能声称新样本
效果、完整学习改善或以0误放掩盖误持有增加。生产未改变，没有重试
或下调阈值。下一研究方向应检查反证题的判断极性和Primitive是否一致，
而不是继续添加身份免责声明；该方向尚未产生效果证据。

本轮最终门：**815 passed, 254.42s**；根类型、两个新研究模块严格类型、
目标pack dry-run和diff空白检查通过，独立审查2项测试及两个完整预检
通过。此轮只有研究文件与行为场景/记录新增，生产运行时保持原样。
没有新增无关失败；总体质量目标仍未完成，保持active。

## Noul 反证命题研究（首次推理前）

官方 https://docs.typesafe.ai/primitives/noul 明确Noul是命题为真的概率，
没有独立confidence。为避免把“兼容”/“冲突”极性混用，实验询问
正向命题：是否存在与候选冲突的证据。>=0.9 conflict、<=0.1该检查
通过，中间uncertain。没有降低0.9/0.1；Choice的0.8 confidence不用于
Noul，因为接口没有该值。这是Primitive加正向反证题的联合实验，
不能把结果只归因于一种类型。support/scope/relationship仍原问题。

隔离自有source copy，仅替换cited counter问法/类型与明确binary分支。
原证据、索引、全部窗口、权限/分类/隐私、超时/重试、请求/字节上限
不变。语义真伪仍需真实比较；32个来源研究新样本此前未调用，沿用
原始冻结文本给本组，两个历史文件不改。开发仍62复用标签+两条无
标签R9实际失败。每组320/组合640请求上限；零外部预检270/128个
完整fixture请求，严格类型通过，独立审查待完成。

回归先RED缺模块，GREEN1项覆盖Memory/Harness、0.1边界通过、0.11/
0.5/0.89持有、0.9 conflict及独立support/scope/服务失败持有。一次
扩大测试原始输出触及Bun65,536字节截断；改为只输出有限问题和索引
摘要，断言仍保留极性/完整检查。真实报告继续wx预留并await写文件。
合成私密研究opt-in由此前@jev-source-replay-privacy.json验证并获授权；
不是改变生产默认私密拒绝策略。生产扩展尚未修改，无外部调用。

Noul开发与新样本推理各同一句柄终态，顺序执行无并行调用：
@jev-noul-development-real-results.json：64计划/62标签，270请求，
complete=true；误拦8→7/误放0→0。拆开阶段：Memory2→3（新增中文
双方向事实候选误持有），Harness6→4。两条无标签R9失败仍持有。
375,773输入tokens/$0.015782466估算费用，中位346.5→347ms。

@jev-noul-heldout-real-results.json：32此前未查询样本，128请求，
complete=true；误拦9→8/误放0→0。Memory4→2，但Harness5→6，出现
中文工具打印角色/无关网络故障的新误持有。106,870输入/
$0.004488540估算费用，中位346.5→352.5ms。全部实际模型jev-1.13.0，
合计398请求、482,643已报告输入/$0.020271006估算费用，不含历史
实验或主模型。不使用微小总数改善掩盖各阶段退步；
@jev-noul-adoption-decision.json记为不采用，生产未变。

另核对真实Click frozen规则字节、有限模板及同项目Git选项实际匹配：
101字符/9个反斜线，实际模式等于规范模板，git -C . push被匹配。
转义不是本例停止原因，没有为错误假设改规则或重写失败证据。

中文双方向Memory新误持有和实际private候选窗口不确定提示，应继续
核查事实知识/个人偏好以及Memory/Harness约束是否混入同一反证命题。
这只是研究方向，不能因没有用户条目就排除工具窗口，也不能假设
工具输出都是真实观察或允许跨隐私写入。当前原权限/完整证据门保留。

本轮最终测试 **816 passed, 252.35s**；根类型、两个研究模块严格类型
通过。独立审查相关7项与零外部预检通过。真实报告原文剔除、wx
预留、完整落文件；诊断额外guard未知JSON不先于SDK解析抛错。
总体目标未达到，保持active，没有发布或用户配置改写。


## Memory 实际主张反证研究（2026-10-06）

基于 Noul 阶段退步与原始 p-limit 反证不确定，本轮仅在研究传输层
明确 Memory counter 比较 candidate.content 实际主张，不把遗漏另一条
行为约束或未遵守偏好本身当成撤回。Choice 三类标签、阈值、完整冻结
证据、来源、隐私/权限、独立 support/relation 和 Harness 题均不改变。
@jev-memory-claim-shadow.ts / @evaluate_jev_memory_claim.ts；回归先 RED
缺研究模块，再 GREEN 2 项，含低置信度、概率、冲突、重复和服务失败
仍整计划持有。独立审查确认作用范围、原文剔除及冻结哈希；无生产改动。

调用前冻结开发 42 reused Memory + 4 Harness controls，并原样回放两条
无标签 R9 失败，48 plans。新的 heldout 是 16 个语义场景的中英配对，
32 samples / 16 positive / 16 negative，不是 32 个独立场景。二者离线
预检 206 / 128 fixture requests、零外部请求，保持完整证据覆盖；mock
只验证路径，不能作为质量结论。测试命令正例验证候选支持，不证明
暂时 bug 应由增量选择器记作持久知识。合成私密研究 opt-in 沿用既有
授权；不读取宿主私人 Memory，不改变生产默认拒绝。

真实顺序执行，每个句柄终态后才启动下一组，模型均 jev-1.13.0：
@jev-memory-claim-development-real-results.json：206 requests，complete；
46 labels 误拦 8→8、误放 0→0（Memory 6→6，Harness controls 2→2），
无 decision changes，原始 Click/p-limit 均仍 uncertain；283,758 input
/$0.011917836 估算输入费用，中位 336→338.5 ms。

@jev-memory-claim-heldout-real-results.json：128 requests，complete；
误拦 6→5、误放 0→0，只有 en-claim-fresh-03 的合成偏好未遵守样本
propose→allow；中文对应仍持有。81,146 input / $0.003408132，中位
339→341.5 ms。合计 334 requests、364,904 已报告 input tokens，
$0.015325968 估算输入费用，不含历史研究或主模型。费用不是账单实付。

@jev-memory-claim-adoption-decision.json：不采用。单一配对样本改善
不足以支持全插件增益，开发集无改善且原始完整工作流失败仍在。真实
p-limit 某窗口兼容概率 0.73→0.87，依然不达 0.9，没有降低阈值。
剩余误持有集中在未验证助手猜测、工具打印猜测与偏好未遵守；需要
进一步检验权威事实来源和全上下文之间的分工，不能直接把角色当真值
标签、移除工具证据或借此绕过已有权限与 Harness。全部失败保留。


@jev-memory-claim-diagnostic-audit.json 为零外部调用离线汇总：此次原始
Click 37/37 entries、4/4 requests；p-limit 96/96 entries、7/7 requests
均完整覆盖，仍分别 scope/counterevidence uncertain。因此本轮回放的
停止并非容量越界或服务失败；不倒改 R9 当时的完整工作流结论。
报告与不采用决定经新鲜独立复核，模型/费用/逐阶段结果一致且没有
私密原文。根类型检查、新研究模块 strict tsc、目标 pack dry-run 和
18 包 packed manifests 检查通过；本轮不改运行时代码，不以 mock
或此前 Docker/native 结果声称新真实工作流已通过。

本轮全包最终 **818 passed, 255.87s**；上述类型与 pack 检查均通过，
限定包 diff check 无空白错误。无变更导致失败；未运行仓库完整 pnpm
check，不把 package 全绿升格为全仓审计。整体学习质量目标仍 active。


## Harness 范围扩大二元研究（2026-10-06）

上一轮 Memory 主张题未解决原始失败。本轮检查独立 scope 命题，而非
重复调整 Memory。TypeSafe 官方 Noul/Choice 文档（2026-10-06在线核对，
.md 地址不可取但普通页成功）说明前者判断是非概率，后者比较竞争项。
当前 expands Choice 已按 same+narrower 概率合计使用，不把低 Choice
confidence 单独当拒绝；所以不能把原始失败归因于漏加安全标签概率。
真正研究问题是是否直接判断扩大比四项关系分类更适配这个安全事件。

@jev-scope-noul-shadow.ts 只在独有临时源码副本将 expands 创建换成正向
Noul：true 表示扩大；false 必须建立两边界并保留每个许可例外。同样
沿用生产已有 Noul scope 分支，<=.1通过，>=.9 scope-expansion，中间
uncertain；未改结果阈值或任何其他问题。父级正则案例、用户引用、权限、
privacy、support/authority/family/explanation/relation/完整反证窗保留。
生产文件未修改，没有写入权限。回归先 RED 缺模块；GREEN1项检查
.1/.11/.5/.89/.9、支持拒绝、反证冲突、不可用。补测实现时修正夹具
对象在 await 前捕获变量及 support Noul 极性，未改生产门以通过测试。

@evaluate_jev_scope_noul.ts 在调用前冻结所有扩展与研究源码、corpus、
patched源码hash及两个原始artifact manifests，最后重新检查。每组
请求上限320，不增加生产请求上限12或重试；report用wx先留 incomplete，
实际完毕await写文件，原文/state/候选正文/existing删除；Noul诊断仅
受信任expands题号和有限0..1数值。临时目录finally清理。

开发52 reused Harness labels +4 Memory controls，加两原始R9无标签
回放=58 plans；新heldout16语义场景双语配对=32，正负各16，不是32
独立场景。独立审查调用前指出02/03只说发布或修改远端并不明确禁止
干跑，已同步用户原文/候选message/引用为禁止命令调用包括--dry-run，
重新冻结corpus hash，未看推理后调标签。两离线全覆盖预检246/128
fixture requests、outbound0；研究strict类型、根类型、目标pack通过。
合成private research opt-in沿用既有授权，宿主个人Memory不读取。


开发真实句柄30415终态完成：@jev-scope-noul-development-real-results.json
58plans/56labels，246requests，complete=true，所有遥测jev-1.13.0。
误拦13→24/误放0→0；拆开Harness11→22、Memory controls2→2，11项
均新增误持有，没有 allow 收益，两原始R9仍 uncertain且证据完整覆盖。
386,099 input tokens / $0.016216158估算输入费用。@jev-scope-noul-adoption-decision.json
决定不采用，并停止新的heldout真实调用（0requests，未验证，不能
用128次fixture预检代替模型效果）。官方primitive匹配不代表质量收益。
没有通过重跑、换标签、调阈值或省略证据追逐正结果。


两臂中位351→359.5ms；独立复核重新计算请求、tokens、成本、每个
阶段和全部11次退步，均与记录一致且无私密原文。官方来源：
https://docs.typesafe.ai/primitives/noul ，
https://docs.typesafe.ai/primitives/choice ，
https://docs.typesafe.ai/confidence 。Jev 问题形式与安全判断事件对齐
值得测试，但这次相当明确地否定“直接换成二元题必然更好”。

本轮最终 **819 passed, 251.24s**；根类型、新研究严格类型、目标pack
dry-run和限定包diff check通过；未运行完整仓库pnpm check。本轮仅
研究副本/测试/场景/证据文档改动，没有生产语义改动、用户配置改写或
发布。仍保持总体目标active，已有失败未被微小局部信号掩盖。


## Memory 索引描述知识遗漏研究（2026-10-06）

回到持久输出链路，发现生产 candidateMeaning 的整块 frontmatter
replace 同时移除了 description，而 memory-files 首个行首 description
实际用于索引、incremental-learning 也将其读入选择元数据。正文真实
但描述夹带无依据事实，可逃过既有语义检查。这里不等同名称/type这类
管理字段；应检查描述的知识主张，而不要求为文件别名生成用户证据。

@jev-description-claim-shadow.ts 在独有临时副本中只改 meaning 投影：
把完整首个 description 以明确“proposed knowledge claim”标签拼入
正文语义content，再保留完整原正文。原候选持久内容/所有索引证据不
修改，原始全候选与全快照隐私扫描先执行；同样 Choice/阈值/全窗口
反证/分类/权限和全计划原子性，Harness未改。缺模块回归先RED，
GREEN三项验证新旧投影差异、秘密header零外呼、CRLF/引号、首条重复
description、4000字符尾标记不截断、无description/纯正文逐字等价。
mock仅说明投影路径，不当作学习效果。独立审查确认实际索引使用，
补充边界并清理复制文案后重新冻结代码hash，所有变化在真实调用前。

@evaluate_jev_description_claim.ts：开发24新描述标签（8正/16负）+
8旧plain Memory/Harness controls，加2原始无标签R9回放=34plans。
另16新语义场景中英配对heldout32samples，在首次调用前冻结，尚未
真实调用，不冒充32独立场景。离线全覆盖150/128fixture requests、
outbound0；synthetic private research opt-in沿用用户授权，没有读取
宿主个人Memory。只研究判定，不直接写入，也不解除任何Harness。

真实开发句柄2777终态：@jev-description-claim-development-real-results.json
150requests，complete=true，实际模型jev-1.13.0；32标签误放16→0、
误拦2→3。新增误拦为en-description-dev-03的正确回归命令描述，support
uncertain；原来的两次hold是Harness控制。两份原始R9仍scope/反证
uncertain，不把阻止16错误描述持久化宣称为完整工作流改善。
243,093 input tokens / $0.010209906估算输入费用，不是账单实付。
@jev-description-claim-adoption-decision.json：暂不采用；进一步在开发
样本检验结构化description字段，以区分知识摘要和人为拼入的说明
标签。这是下一步假设，不能从一次模型概率归因。没有重跑找好结果，
没有降低阈值，保留全部已查询失败；新的heldout0真实requests。

两臂中位361.5→368ms。全包最终 **822 passed, 252.33s**；根类型、
研究strict类型、目标pack dry-run及限定包diff检查通过。运行时代码
本轮未改，不用mock/此前Docker结果声明新完整工作流已验证。整体
目标仍active，索引描述漏检已成为具体需修复的质量缺口。


## 独立 description 字段研究（2026-10-06）

前一轮拼接“索引描述”到content造成一个正确描述新hold。本轮研究
@jev-description-structured-shadow.ts 保留正文逐字不变，将完整首个
描述作为独立 description 字段，只在其存在时提示支持/反证比较两者。
其他判断与权限、隐私、分类、完整证据、Choice/阈值不改。回归先RED
缺模块，再GREEN4项，含跨输送逐字段断言：plain、无description和
Harness两臂wire逐字相同。原始秘密header0外呼，CRLF/quoted/重复首项/
长描述尾标记与完整body保留；研究模块及实际patched模块strict tsc
通过（初次检查少allowImportingTsExtensions，补齐仓库选项后通过）。

独立审查确认两份manifest hashes、完整请求预检150/128、权限与私密
报告边界；没有新增命令或用户配置改写。开发32复用标签+2原始R9失败
=34plans，heldout32样本仍为未查询的16中英配对场景。原文不进入报告。
真实句柄23174终态：150requests，complete=true，模型jev-1.13.0；
误放16→8、误拦2→2。Memory误放16→8、hold0→0，Harness控制hold2→2。
244,723input / $0.010278366估算输入费用，原始失败仍held。新增误持有
消失，但两种语言各四个描述仍误放。@jev-description-structured-adoption-decision.json
不采用；heldout0外呼未验证，保留以用于更具体的独立知识字段判断。
全包本阶段826passed/253.67s；根类型、target pack、strict及diff通过。

这个结果支持进一步分解支持/反证检查，而不是给整题加入更长说明。
@jev-description-atomic-shadow.ts 已在独有副本为description添加独立
supported_description、relation_description、counter_description问题。
原body题与Harness逐字保留，描述字段的重复关系不会阻止有新增正文
的候选，但冲突/不确定仍全计划hold。原body关系继续检查整条是否
重复；描述不是证据或许可，沿用原frozen quote与完整反证窗。所有额外
问题在第一个请求前按原byte/question/batch/window/concurrency caps
预检；不增加上限、超时或重试。三回归含额外support/关系/反证失败、
字段duplicate与whole-plan保留，16*15k描述的合法parent输入超过请求
批次预算时0外呼bounds。首次过大夹具16*48k超出既有新Memory总量
256k，修正为合法输入以隔离真正传输预算缺陷，未改parent限制。
atomic actual patched strict类型通过；正在独立审查，尚无真实调用。

独立审查指出原语料existing为空，补8条中英开发关系场景：描述重复/
补充允许，描述冲突和正文重复仍hold；标签在首次调用前冻结。修复
relation_description受控概率诊断，复用既有合法Choice净化、不输出原文。
再次独立审查与开发42plans/40labels/182fixture/0outbound预检通过；
heldout32/128/0 unchanged，existing关系仅在开发覆盖，不能声称留出验证。
真实开发调用采用固定jev-1.13.0，320requests研究边界，无持久写入。

真实开发句柄31166终态：42plans、40标签、182requests，complete=true；
误放18→0、误拦2→2，原R9两份回放保持scope/counteruncertain。
随后仅一次调用此前未查询heldout（句柄58012）：32samples、16中英
语义场景、128requests，complete=true；误放16→0、误拦0→0。
两臂真实模型均jev-1.13.0，开发287300input/$0.012066600估算，
heldout94592input/$0.003972864估算；费用不是账单。开发中位355→347ms，
heldout346→338.5ms。不从几毫秒差异推断速度优势，也不从此局部
字段验证宣称原来off1/3,on0/3的整体Docker工作流已改善。
@jev-description-atomic-adoption-decision.json记录局部采用决定，
已有Memory关系仅8条开发覆盖；保持已查询的失败和旧研究报告。
新增生产回归先RED：3failed/1.05s，错误描述被放行、关系题缺失和
额外合法输入问题预算未预检，随后接入独立描述门。

生产门已接入，@test_jev_memory_description.py 五项覆盖正文/描述边界、
错误描述hold、描述关系/完整反证hold、正文duplicate仍hold、原秘密
header0外呼、CRLF/首个重复键/完整4k尾标记，以及额外问题0外呼bounds。
telemetry新增可选受控field:description；bounded修复hint明确字段，
Memory大模型修复提示同时约束正文和索引摘要。未改权限、阈值、
退路或命令面。原metadata-format测试按新契约加入描述题，行为断言
仍要求格式修复允许、正文/元数据/隐私变更和正文重复持有。
保留 @fixtures/jev-learning-before-description.ts.txt，其hash等于真实
研究原baseline；三个描述研究副本与mock使用冻结baseline，不会
在生产修复后无意二次叠加门或改写历史。已冻结旧研究manifest不重写，
当前源码漂移会在任何外部调用前拒绝重跑。独立生产审查通过。

费用对比：开发before132446input/$0.005562732 → after154854/$0.006503868，
各91requests；留出before38670/$0.001624140 → after55922/$0.002348724，
各64requests。描述独立判断增加输入费用，没有把总费用当作单臂费用，
也没有宣称中位几毫秒差异为速度提升。

最终生产验证：**834passed/256.01s**，包括实际Pi --print的隔离本地
fixture-provider hook检查（非真实模型效果）。此前接入后833passed
/256.38s未收集最后新增的秘密/CRLF完整字段生产回归，因此又跑834
完整门，不以833替代最终覆盖。根TypeScript、研究strict、安装检查
17workspacePi包/18settings entries、目标pack dry-run、18workspace
packed-manifest检查和限定包diff均通过。新增changeset仅准备补丁，
没有发布或提交。独立生产安全审查无阻断；完整R10Docker仍在运行，
不可用局部判定样本代替工作流结果。

## 独立描述门 R10 Docker（2026-10-06）

@jev-independent-description-r10-docker-results.json：3项目×off/on，
6独立非root容器，jobs1串行、同一冻结image/commits/Pi1.0.2，所有
付费研究串行且完整保留失败。原生真实模型，无脚本替代，固定
主模型cli-proxy/bailian/qwen3.8-flash、Jev实际全部1.13.0。主任务
真实改回归、项目原检查、新会话读完整Memory与回忆、真实Bash
禁令拦截全部门不降低。**off3/3，on0/3**，进程5055终态exit1。
175total provider requests（含24Jev，主模型151），providerErrors0；
24/24Jevusage返回，149728input/$0.006288576估算，非账单。
相较R9请求更少不能宣称效率改善：部分失败终止了后续实际检查。

Click-on：26entries/5windows完整覆盖，body支持和候选1description
反证uncertain；Memory提案保留，Harness两次父级fixtures=1拒绝，
后者不是Jev误拦。p-limit-on：Memory完整15entries/2windows审查
supported，父级实际应用3操作；Harness首次/修复均scopeuncertain，
仍未进入完整新会话和原生拦截验收。mitt-on同样未获得successful
Memory judgment（详见冻结报告），不能用p-limit局部写入报整体通过。

完整工作流未改善，目标保持active；固定描述标签改善仅支持局部
质量修复，不预设Jev整体优于关闭。off跨轮从R9的1/3到R10的3/3
涉及不同生成和原生工具选择，描述门在off不运行，不作因果归因。

后续具体研究信号：p-limit原scope-hold的matcher逐字等于生成器的
projectPushTemplate(frozen parent manifest.cwd)，包含同项目cd
包装、dot与三种安全Git global options。当前unwrapped finite
识别覆盖不到这个模板；冻结snapshot本身无cwd，不能从候选正则
猜测/信任项目根。@jev-parent-bound-wrapper-r10-manifest.json冻结
4原始文件及hash，expectedAllow:null，不计入准确率；0外呼核验
exactParentBoundTemplateMatch=true。下一研究仅检验把父级冻结
目录绑定的代码证明传给窄语义授权/范围题是否减少不确定；此证明
不能变成用户许可，不迁移既有规则，不放宽任意cd或glob，尚未
真实推理或采用该路线。

另发现可读回执未显示JSON中的description字段，新增回归真正RED
（先修正测试串newline转义错误，再assertion失败）→GREEN18回执
检查；仅field===description追加.description，未知字符串不显示。
@jev-description-r10-receipt-display-audit.json独立重算证明只撤回
这一显示片段后当前冻结范围全摘要精确等于R10image4abfa8...，
其余学习执行源码逐字一致；不能把新版显示当作Docker中实际显示。
最终全包835门正在运行，根types、install和target pack已重跑通过。

最终显示补丁完整门：**835passed/256.96s**（包括隔离真实Pi --print
fixture-provider hooks，不冒充真实Jev效果）；根types、研究strict、
目标pack、install已通过，18包packed-manifest最终重跑与diff检查
见本轮终态。没有生产发布、提交或用户配置改写。

终态确认：18workspace packed manifests最终重跑通过；根types与研究
strict、安装检查、目标pack及限定diff全部通过。所有真实推理句柄
已终态，目标仍active，无进行中的付费调用；下阶段先写父级范围
绑定的研究场景/RED回归，再做受限影子对比，不能把匹配证明当许可。

## Parent-bound wrapper V1: real development rejection (2026-10-06)

Hypothesis: parent-owned cwd plus frozen run/scope/digest and exact equality to
`projectPushTemplate` can supply matching meaning in code, leaving semantic
permission to independent Jev authority/family judgments. Only new enabled
`addRule`/`block` candidates qualify. Wrong bindings, updates and confirmation
rules retain the existing path; complete counter windows remain mandatory.
The helper is research-only and has no persistence API. It does not infer cwd
from model text or the candidate matcher.

Given/When/Then boundaries were first reproduced RED with the missing helper;
the two original boundary tests passed GREEN. Subsequent Memory-wire/privacy
coverage and V1/V2 parameterization produced six passing cases. Matching proof
never supplies authorization or bypasses original privacy/phase permissions.

Frozen development comprised 12 new scenarios, each translated into English
and Chinese: 24 labeled plans, eight valid and sixteen invalid. Translation
pairs are not 24 independent scenarios. An additional original p-limit R10
proposal was replayed without a quality label, binding cwd to its frozen parent
manifest and verifying all original file hashes and snapshotDigest. Offline
preflight completed 102 fixture requests / zero outbound; its all-allow mock
outcomes are transport/boundary evidence, not a quality result.

Actual V1 used Jev 1.13.0 and completed 102 requests on 25 paired plans, with
125,713 input tokens and estimated input tariff $0.005279946 (not actual billed
charges). Labeled false accepts were 0 -> 0; false holds 8 -> 8. The real R10
proposal stayed held in both arms. No quality improvement was demonstrated,
so this branch is rejected for production. The frozen 24-plan heldout was NOT
queried. Original V1 source bytes are retained in frozen fixtures; the source
preservation audit verifies equality to the completed study manifest rather
than rewriting historical hashes after adding V2.

Per-arm totals including the unlabeled replay: before 69,723 input tokens,
$0.002928366 estimate, median plan time 355 ms; after 55,990 tokens,
$0.002351580 estimate, median 348 ms. These finite-sample timings do not prove a
speed benefit. Controlled diagnostics show reliable lasting-authority answers
but uncertain family/counter answers even for all eight valid restrictions.

V2 is a distinct frozen study using the same development labels (reused, not
new validation). It removes syntax details already proven by code from Jev's
scope projection and isolates counterevidence from the separately checked
lasting authorization. It preserves the original thresholds, full windows,
chronology, exceptions and unknown handling. Independent review and actual
patched SDK strict type checks passed before outbound inference. No version
is adopted merely because its questions are simpler.

### V2 actual development, heldout and conditional adoption

V2 completed 102 development requests: false accepts 0 -> 0, false holds
8 -> 0. The unlabeled original R10 p-limit proposal changed from scope-held to
allowed, without applying it. Its original complete evidence remained covered.
Development was reused after V1 and is not independent confirmation.

The previously unqueried heldout then completed 96 requests. It comprises
another 12 English/Chinese scenario pairs (24 labels: eight valid, sixteen
invalid). False accepts were 0 -> 0; false holds 8 -> 4. The remaining holds
were en-durable, zh-durable, en-anyargs and en-irrelevant, all in authority
uncertainty. No threshold was lowered, no label changed after inference, no
uncertain answer became permission, and no favorable rerun replaced a failure.
The rejected V1 heldout was never queried; V2 used the same frozen, still
unqueried sample definitions. All actual returned models were Jev 1.13.0.

V2 development: before 69,723 tokens/$0.002928366 estimated tariff/342 ms
median plan time; after 54,751/$0.002299542/330 ms. V2 heldout: before
50,599/$0.002125158/345.5 ms; after 37,409/$0.001571178/343.5 ms. Combined
V2 requests 198, input tokens 212,482, estimate $0.008924244. Actual billed
fees are unavailable. Timing and cost are bounded sample measurements.

V2 was adopted on this limited evidence: fewer valid-rule holds in development
and heldout without increased unsafe accepts in their negative samples. This
is NOT proof of whole-workflow or general learning superiority. Production
integration passes only parent-owned immutable cwd/run/scope/canonical object
digest into the semantic callback, including its single bounded repair. The
original snapshot file digest is checked separately by the parent before and
after semantic validation and before writes. No candidate-generated binding,
new command, configuration requirement or existing Harness rewrite was added.

Production regression was RED before adoption: two of three production boundary
cases failed (valid wrapper stayed held, exact-argument rejection was not the
narrow scope outcome). GREEN after adoption: nine V1/V2/production boundary
cases passed. V2 research sources and the original pre-adoption production
source are preserved in frozen fixtures; completed study hashes are unchanged.

Post-adoption full gate first reported 842 passed / 3 failed in 260.36 s.
All three were change-caused historical research-helper shape dependencies:
finite-authority (two) and counter-Noul (one) attempted to patch the current
production source. The historical helpers now load the frozen pre-bound-scope
fixture, preserving their original gates without changing runtime code or
completed report hashes. Focused historical helpers: four passed / 1.44 s;
current V1/V2/production scope and parent repair coverage: 37 passed / 16.26 s.
Final full gate is rerun after this fix rather than treating focused green as
completion. Runtime source remains byte-identical to the R11 Docker image.

Final post-fix target gate: **845 passed in 256.58 s**. Root TypeScript,
strict research/helper type checks, target pack dry-run, check:install
(17 packages/18 settings), pack:check (18 workspace manifests) and scoped
whitespace checks passed. Independent production review verified byte equality
to the actually evaluated V2 source and parent-binding/TOCTOU permissions.
No runtime changes followed the frozen R11 digest
`5888582df6c2fffbd88f7dc3354cbff37d3013c61e11e8b4b793f983bb708122`.

A separate native host Pi **1.0.3** PTY compatibility check used a temporary
agent directory, disabled auto-memory/Jev, offline startup and a non-live
fixture API key. `/memory status` rendered the explicit disabled/idle state;
`/harness` opened its rule selector, Escape cancelled it, Ctrl-D restored the
terminal and exited zero. Temporary files were removed. This proves command
and menu compatibility, not live learning inference. Docker remains pinned to
its independent Pi runtime and real providers.

### R11 native acceptance parser regression and preserved evidence

The original mitt-off R11 report failed at native enforcement. Reading its
original session revealed an actual error toolResult containing two exact
configured block messages joined by a newline; the recorded side-effect marker
was absent, and the independent allowed printf call completed successfully.
The old evaluator only accepted one configured message. This was a measurement
false negative, not evidence that the hook executed the forbidden command.

RED regression reproduced the duplicate-message rejection. GREEN parser accepts
an ordered subset of complete nonempty configured block messages, using each
rule at most once. It rejects unknown, reordered, over-repeated or trailing
text and successful (isError=false) outputs. Enabled/action filtering,
observed native Bash attempt, marker absence and allowed invocation success
remain required. Ten evaluator regressions and independent review passed.

The original report, image, original verifier, session and learned rules remain
unchanged. A separate hash-bound offline revalidation confirms all seven prior
mandatory checks and all three native checks against that same real execution;
this is neither a new Docker execution nor a new model call. The normalized
current source digest, replacing only the evaluator with its preserved original
bytes, matches frozen R11 exactly. The corrected verifier did NOT run inside
that original image. Raw Docker status and offline corrected acceptance must
remain separate. Other-stage failures cannot be reclassified by this fix.

### R11 terminal six-execution results

All six independent serial Docker executions terminated (runner exit 1), using
frozen source `5888582df6c2fffbd88f7dc3354cbff37d3013c61e11e8b4b793f983bb708122`,
main cli-proxy/bailian/qwen3.8-flash and actual Jev 1.13.0. Raw acceptance:
off **2/3**, on **1/3**. Separately, corrected offline acceptance of the SAME
original native evidence: off **3/3**, on **1/3**. The only correction is the
mitt-off combined-message measurement bug above; no new execution or favorable
inference rerun was added. R10 on was 0/3, but generations differ across rounds
and arms, so R11 1/3 is evidence of a working full workflow, not isolated causal
proof that this patch explains every improvement.

Click-on: parent repair consumed the one repair slot after a structural
rejection; Memory then proposed with description support/counter uncertainty,
covering all 22 entries in two windows. Harness passed semantic validation and
applied one operation. Full new-session/native acceptance was not reached.
Those description strings are retrieval cues ('When ...'), motivating a new
unproven hypothesis: the descriptor judgment may need the knowledge body as
interpretation context, without accepting unsupported descriptor claims. The
original Click history/snapshot/manifest/report are frozen with no quality label.

p-limit-on: initial Memory support uncertainty became supported after one
bounded repair; two Memory operations and one Harness operation applied. Full
fresh private recall, complete Memory reads, exact verified command, native
Bash block/no side effect and unrelated allowed command all passed. Learning
261.55 seconds; Jev judgments 1.095/1.174/1.077 seconds. A lower Jev latency is
not a claim that generation/repair overhead is solved.

mitt-on: both Memory attempts stayed uncertain (body support, description and
body counterevidence); both Harness attempts stayed scope-uncertain. Every
attempt completed four requests and reviewed all 44 entries across three
windows. No context-capacity or service failure was substituted for a semantic
answer. Original proposed histories and full evidence are frozen, unlabeled.

R11 provider requests **206**, including **31** Jev and **175** main-model
requests; provider errors **0**. Jev usage was complete on 31/31 responses,
236,113 input tokens and $0.009916746 estimated input tariff, not actual billed
fees. Main-provider billing is unavailable. Lower request counts in failed
arms do not prove efficiency because downstream checks stop early.

The bounded paired semantic improvement and p-limit live success are real;
general full-workflow superiority remains unachieved. Next research priorities
are descriptor retrieval-cue interpretation grounded in body/evidence, followed
by generated matcher forms that miss exact canonical proof. Neither failure
will be erased or solved by reducing confidence thresholds.

Final gate after the measurement fix: **846 passed in 260.90 s**, root
TypeScript passed. This supersedes the intermediate 845-test gate. Research
strict types, target pack, installation and all 18 packed manifests passed;
production and evaluator changes received separate independent reviews. All
paid inference, Docker, PTY and test handles are terminal. No publishing,
commit, user configuration change or confidence-threshold relaxation occurred.


### Description retrieval-cue body-context research: rejected

Hypothesis from frozen R11 Click: a Memory index description beginning with a
retrieval cue may need the proposed body to resolve its referents. Research-only
owned copies attach the complete body as context to description support,
relationship and counterevidence questions. The body is explicitly proposed
content, never evidence or authorization; its original independent grounding
and counterevidence judgments remain mandatory. No evidence truncation,
confidence change, privacy change, new write permission or production change.

Given/When/Then scenario and a RED regression preceded the research helper;
GREEN covers body unsupported, description unsupported, later correction,
original candidate secrets and unchanged capacity preflight. Original secrets
and oversized bodies cause zero outbound requests. Real SDK strict types and
independent review passed. Offline preflight: development 25 plans / 102 fixture
requests, heldout 24 plans / 96 fixture requests, **zero external requests**;
those fixture results are transport/path verification, not quality evidence.

Both real studies were frozen before calls, serial, actual Jev **1.13.0**, all
response usage and full evidence coverage complete. Development has 24 labeled
plans (12 English/Chinese pairs), plus the original hash-bound R11 Click Memory
proposal as an unlabeled read-only replay. Development false accepts **0 -> 0**,
false holds **6 -> 4**; two English positives improve. The Click proposal still
holds: the description-support uncertainty remains, although its description
counterevidence holds clear. No candidate was applied and no Docker was rerun.

Previously unqueried heldout has 24 labeled plans (12 new expression pairs),
using different commands and wording from the same archetypes, not 24
independent mechanisms. Heldout false accepts **0 -> 0**, false holds **8 -> 8**.
All eight positive holds still involve description support. One is classified
unsupported in both arms; the rest remain uncertain. This fails to demonstrate
a generalizable reduction in blocking. The development-only gain is insufficient
for adoption. **Rejected; production bytes and existing thresholds unchanged.**

Development: 102 real requests, 132,245 input tokens, $0.005554290 estimated
input tariff. Heldout: 96 requests, 95,112 input tokens, $0.003994704.
Combined: **198 requests, 227,357 input tokens, $0.009548994 estimated**, not
actual billed fees. Development input usage before/after 62,192/70,053;
heldout 44,298/50,814. Median durations development 359/357 ms, heldout
365.5/360 ms; single queries, no latency superiority or significance claim.
The extra body context increases payload and can reach the unchanged capacity
limit earlier; it is not a free fix.

Artifacts: `jev-description-context-{development,heldout}-study-manifest.json`,
corpora, real-results and `jev-description-context-adoption-decision.json`.
The decision binds both reports by SHA-256. No sensitive original text is in
these reports. All original frozen candidate, evidence, parent binding and
whole-plan/repair behavior remain authoritative. The research leaves the real
workflow result unchanged: R11 raw off 2/3, on 1/3; separate corrected native
revalidation of the same executions off 3/3, on 1/3.

Next signal is a mismatch between a retrieval cue and the existing factual
support question. Future work should test a task-specific retrieval judgment
or generate descriptions that include a supported fact. It must preserve
independent description support and whole-body grounding, test broader cues,
unsupported claims and later corrections, and use newly frozen heldout
expressions. Requerying this heldout cannot establish fresh generalization.

Final gate for this research increment: **847 passed in 264.49 s**, root
TypeScript passed, research helper/evaluator and actual owned patched SDK
strict types passed, target pack dry-run passed, scoped whitespace check
passed. Fresh independent research review found no blockers. Both paid-study
handles and test/typecheck handles are terminal; owned builder scratch removed.
No production runtime was changed by this rejected study, so no new Docker,
installation or TUI run is claimed. Overall Jev workflow superiority remains
unachieved and the active goal is not complete.


### Task-specific description retrieval judgment: aggregate gain, not adopted

Following the rejected body-context study, the research-only owned copy also
replaces the independent description support question and its Choice criteria.
It asks whether the description is a faithful index entry, recognizing both
retrieval cues and facts. It explicitly checks topic, target, conditions and
scope against original frozen evidence, checks all asserted facts/obligations,
and calls bodyContext proposed content, never evidence or authorization. The
original whole-body support, relation, full-window counterevidence, confidence,
privacy, parent validation and whole-plan write barriers remain unchanged.
No production source or prompt was changed by this study.

Given/When/Then scenario and RED test (missing helper, 1 failure) preceded
GREEN. The regression verifies task-specific criteria, independent body gates,
unsupported description, later correction, original secret and oversized-body
zero-outbound preflight. Seven related regressions passed. Research and owned
SDK strict types passed. The first standalone type invocation omitted the
allowImportingTsExtensions flag and returned TS5097; the corrected invocation
passed. Both owned copies were disposed. Independent review initially found
manifests not yet created; after freezing, review independently reran preflight
and types and found no remaining blockers. No paid inference preceded freezing.

Official Choice guidance says question IDs are hidden and option descriptions
should separate meanings; the new question therefore states its index task
explicitly, rather than relying on a description question ID. Source:
https://docs.typesafe.ai/primitives/choice . This documentation supports the
request design, not a claim that the model improves.

Development reuses all 48 previously queried body-context labels (24 bilingual
pairs), plus original R11 Click as a hash-bound unlabeled read-only replay. It
is development, not new heldout evidence. Preflight 49 plans / 198 fixture
requests; newly frozen heldout 40 plans / 160 fixture requests, both zero
outbound. Heldout consists of 20 new bilingual expression pairs (12 positives,
28 negatives), adding cross-target, approval removal, condition removal, extra
topic, untrusted evidence instructions and one-time duration counterexamples.
The pairing and overlapping mechanism limits remain; no significance claim.

Serial real Jev **1.13.0**, completed response usage and full evidence coverage:
- Development: 198 requests; false accepts **0 -> 0**, false holds **14 -> 10**.
- Fresh heldout: 160 requests; false accepts **0 -> 0**, false holds **6 -> 4**.
- Heldout English checkout-test, persistent-policy and supplement-format improve
  propose -> allow; English personal-note regresses allow -> propose. Chinese
  personal-note, persistent-policy and supplement remain held. Complete fact
  descriptions and precisely conditional cues pass in both arms.
- Original unlabeled Click remains propose -> propose. Before: one candidate
  first fails description support, another first fails description counterevidence;
  after: three candidates first fail description support. Thus support holds
  are 1 -> 3 and total held description candidates 2 -> 3. It is not an accuracy
  label, new Docker execution, applied plan, or evidence of workflow recovery.

The aggregate heldout gain is real within this bounded comparison. Nevertheless
one previously accepted valid private preference now holds, and the unchanged
real proposal remains blocked. **Not adopted**: aggregate gain alone does not
justify this question replacement or an overall superiority claim. Neither
unknown result becomes no-op or an authorization to write. All failures,
labels and original hashes remain; no threshold relaxation or favorable rerun.

Development 224,042 input tokens, estimated input tariff $0.009409764;
heldout 154,011 input tokens, $0.006468462. Combined **358 real requests,
378,053 input tokens, $0.015878226 estimated**, not billed fees.
Input before/after: development 106,490/117,552, heldout 73,054/80,957.
Median durations: development 378/392 ms, heldout 381.5/370 ms. Single paired
queries; no latency or efficiency superiority claim.

Manifests `jev-retrieval-description-{development,heldout}-study-manifest.json`
freeze corpus and code before calls. Real-results contain controlled labels,
numeric diagnostics and hashes, never original snapshot/plan/existing text.
`jev-retrieval-description-adoption-decision.json` binds reports by SHA-256.
Post-run checks confirm every frozen source/corpus, actual model, request count
and complete evidence coverage. New research never changes privacy or writes.

Next investigation moves to candidate generation: both consolidator prompts
currently demand a relevance trigger (an elliptical cue), while independent
support judges every content claim. Test concise factual descriptions that
include the evidence-backed subject, project and conditions. Such descriptions
should be generated by the existing candidate/repair model, not mechanically
rewritten or manufactured as new evidence. A new frozen study must keep adverse
cases and use fresh heldout expressions; these queried sets are now development.
The full workflow quality goal remains incomplete.

Final verification for this increment: **848 passed in 258.81 s**, root
TypeScript passed; research helper/evaluator and actual owned SDK strict types
passed; target pack dry-run and scoped whitespace check passed. Independent
post-results review verified frozen/report hashes, actual model, full coverage,
metrics and the private-preference regression. It identified a diagnostic
wording error (Click support first-failures 1 -> 3, total description candidates
2 -> 3), corrected above without editing real reports or rerunning inference.
All paid, test and type handles are terminal; owned builder and research copies
were removed. No production runtime change, new Docker, install/TUI result,
publication or commit is claimed by this research-only increment. Goal active.


### R12 factual-description generation experiment: started, not yet accepted

Prior task-specific description questions reduced aggregate holds but introduced
an individual private-preference hold, so the semantic replacement was rejected.
This round changes the two candidate-generation prompts only: index descriptions
must state a concise evidence-backed fact/preference with subject and context,
not a bare relevance trigger. Material target/condition/duration/approval and
privacy boundaries remain. If the complete claim cannot fit 120 characters,
summarize a narrower supported fact and keep the complete constraint in the body.
Original evidence must support both fields; the proposed body is not evidence.
The existing Jev question, confidence, full review and write barriers are intact.

Given/When/Then feature and two RED prompt-contract failures preceded GREEN.
Independent review found an existing project example ('How this project works')
that conflicted with the new rule. A second RED regression reproduced it; the
example now states its original body/quote-supported fact. Preserved original
prompt bytes remain unchanged, and the source manifest retains initial changed
hash and pre-inference revision. Final independent review and all 28 Memory-index
tests passed; typecheck, package pack and installation checks passed.

Prospective manifest `jev-factual-description-r12-study-manifest.json` freezes
source **39848586e489d75df2ae4cac140594ee36a361f07e4f9433547534518a16adcc**,
three original fixed open-source commits, serial jobs=1, Jev off/on and total
360 provider requests. Main model is cli-proxy/bailian/qwen3.8-flash;
Jev is pinned 1.13.0 with synthetic private fixtures authorized. No user Memory
mounts or real remote push. Actual response versions and costs remain to verify.
Replacing only the two prompts and the prior combined-message verifier with
preserved originals exactly reconstructs frozen R11 runtime digest. No other
runtime source drift is attributed to this round.

Both arms use the new prompt and independently generate candidates. This is a
same-round integration comparison, not a paired-candidate causal trial of the
prompt or a statistical reliability result. R11 generations remain historical
nonconcurrent evidence. Preserve all failures/repair histories; no favorable
reruns. Initial live runner and full-suite handles are in progress, not passed.

Local verification of the final R12 prompt source: **848 passed in 266.12 s**,
root TypeScript passed; target pack dry-run passed after final example repair;
all 18 packed manifests passed; installation validated 17 packages/18 settings;
scoped whitespace check passed. Independent final review confirmed corrected
example and baseline/final hashes. The serial real Docker runner remains live
in its first Click execution; no terminal arm or six-execution outcome is
claimed yet. This local gate does not prove quality improvement. Preserve and
resume the same live runner rather than launch a replacement round.


R12 interim, first terminal arm (Click/off): original whole-arm **failed** at
native Harness enforcement because the model did not issue the forbidden Bash
call. Absence of the wrapper marker is not enforcement evidence without an
observed invocation. Do not reclassify this failure or repeat the paid arm.
Earlier checks passed: real regression changed, private preference and shareable
verified command learned, byte-identical mirror, fresh full Memory reads,
private preference use and exact verification command. Memory applied two
operations; Harness applied one. Learning 125.28 s. Both generated descriptions
fit 120 characters (84 and 79); the public descriptor contains the exact verified
command. This metadata demonstrates generator output shape, not semantic accuracy
or a causal quality improvement. Baseline private recall also succeeded under
the previously declared same-filesystem comparison, so no exclusive recall
benefit is claimed. Actual Docker Pi 1.0.2, Node 22.23.2, Linux aarch64.

`jev-factual-description-r12-click-off-interim.json` binds the terminal original
report by SHA-256 and includes only controlled outcomes and numeric descriptor
metadata. The original session/report and source digest remain unchanged. The
parent serial runner is still live on Click/on; five arms are not yet terminal.
Round acceptance, actual on-arm Jev versions/usage and comparative quality are
pending. The disappearing Click/off container is normal task-owned cleanup after
export; it does not mean the parent experiment stopped. Resume the existing
parent handle, never restart based on a missing child container.


R12 interim correction: the preceding Click/off 'model did not issue the forbidden
Bash call' interpretation was wrong. The original log contains a project-scoped
`git push --dry-run` followed by a literal exit-status echo. The old evaluator
rejects this compound shape even though the native hook blocks the whole Bash
request. Original isError=true, exact configured rejection, absent marker, and
separate successful allowed printf were independently confirmed. This is a
measurement false negative, not a model refusal or an executed push.

RED reproduces the suffix mismatch; GREEN adds only literal `; echo "exit=$?"`
after already-recognized exact/project-prefixed/2>&1 forms. Negative cases reject
printed command text, foreign cwd, arbitrary commands, command substitution,
conditional OR, successful output and unknown messages. Eleven evaluator tests
and independent review pass. The prior verifier bytes and hashes are preserved.
Original R12 image/report/session/rules/interim remain unchanged; a separate
`jev-factual-description-r12-click-off-native-revalidation.json` binds them and
withdraws the earlier inference. All seven prior mandatory checks and four native
checks pass on that SAME original execution. Replacing only current verifier
bytes with preserved original bytes exactly reconstructs frozen R12 source.
The corrected verifier did NOT run in the old image. Raw failed status and offline
corrected acceptance remain separate; no paid or Docker retry is added.

Click/on original **failed** at real-regression-task. Memory became a proposal
because one actual Jev request timed out (5019 ms): 2/3 requests and 1/2 windows
completed, 12/26 entries reviewed. Known response model 1.13.0 and 11,459 known
input tokens are a partial total, not complete usage or zero cost of failure.
No second Memory semantic attempt is claimed. Harness two proposals both had
complete 3/3 requests and 26/26 entries reviewed: first support uncertainty,
then scope uncertainty. It applied zero Memory/Harness operations. The measurement
fix cannot reclassify this service/semantic failure. Actual generations differ
from R11; no causal prompt improvement or deterioration is inferred from this
single failure. `jev-factual-description-r12-click-on-interim.json` records the
controlled attempts and original report hash without raw evidence/candidates.
The same parent live runner has moved to p-limit/off; four arms remain pending.


R12 next terminal arm: p-limit/off **passed** the original complete acceptance,
including all learning/privacy/mirror/fresh-read/exact-command/native block/
no-side-effect/allowed-command checks. This is an off-arm result, not proof of
Jev quality improvement. A hash-bound controlled interim artifact preserves it.
Parent serial runner now executes p-limit/on; Click/on's real timeout/semantic
failure remains, and Click/off's original failed status plus separate offline
corrected acceptance remain distinct. Three arms are still pending.


R12 p-limit/on original **failed** at real-regression-task: Memory and Harness
were both proposed with real Jev unavailable, zero applied operations. Memory
1/3 requests, 1/2 windows, 7/17 entries; Harness 1/3 requests, 0/2 windows,
0/17 entries. Known returned model 1.13.0, 10,393 and 1,409 known input tokens
are partial lower bounds. HTTP status was not retained; rate limiting, quota,
capacity or another transport cause cannot be distinguished and must not be
invented. This incomplete service arm is not semantic-quality comparison proof.
Its original report and controlled attempt metadata are hash-bound in a separate
interim artifact. Parent live runner now runs mitt/off; mitt/on follows serially.

Final full gate after the exit-status measurement fix: **849 passed in
259.87 s**. This supersedes the earlier 848-test gate for R12 prototype. Eleven
measurement regressions and fresh independent verifier review passed; no
production Jev or prompt changes followed the frozen R12 image. Raw versus
corrected offline statuses and incomplete usage remain separate. No new paid
replay is used to replace failed arms.


Current primary-source diagnostic check: the official Models page reports Jev
1.13 context budgets of 64k tokens combined and 32k for state plus the longest
question, and documents dynamically adjustable token/request rate limits with
HTTP 429 on limiting: https://docs.typesafe.ai/models . The API reference is
https://docs.typesafe.ai/api . These general constraints do not identify the
cause of p-limit/on's unavailable requests: the original receipt lacks HTTP
status. No inference that these failures were quota/rate/capacity errors is
made. A useful next diagnostic improvement is retaining a controlled HTTP status
without raw error bodies, evidence or credentials. The current frozen round
must finish unchanged before diagnosing a new live transport experiment.

## R12 terminal evidence and HTTP diagnostic increment

All six original serial Docker executions ended; parent runner exit 1. Frozen
runtime/source `39848586e489d75df2ae4cac140594ee36a361f07e4f9433547534518a16adcc`
is unchanged. `jev-factual-description-r12-docker-results.json` hashes the original
summary and records **raw off 2/3, on 0/3**. Applying the independently reviewed
Click/off verifier correction to that SAME original execution yields **offline
corrected off 3/3, on 0/3**; neither original failed status nor image is rewritten,
and no paid/Docker rerun replaced a failed arm. The correction artifact was made
while the round was incomplete; the new terminal aggregate supplies final scope.

Mitt/off passed complete original learning/privacy/mirror/fresh-read/command and
native enforcement acceptance. Mitt/on finished all evidence reviews: first
Memory plan held three candidates (two support uncertainty, one counterevidence
uncertainty); bounded second plan still held candidate 1's description
counterevidence. Both plans covered all 31 entries, 2/2 windows, 3/3 requests.
Harness covered all entries and was supported. Overall still failed because no
successful real Memory judgment. This is a completed semantic hold, unlike the
incomplete Click Memory timeout and p-limit Memory/Harness unavailable phases.
None is reclassified as success or proof that the prompt change is superior.

Aggregate main-provider requests 173, provider errors 4. Jev requests 24, returned
usage for 20; actual returned version `jev-1.13.0`, **155,937 known input tokens**,
**$0.006549354 known tariff estimate**. This is a lower bound, not complete billing;
main model billing is unavailable. Original HTTP failure statuses were not retained
and are unknown. These independently generated arms used the new prompts in BOTH
arms; historical R11 is not a concurrent old-prompt control. Generation improvement
is not adopted as proven: the source tracker remains pending real quality evidence.

Current runtime adds only trusted numeric SDK `APIError.status` in range 400–599
for an unavailable request, propagating the first failed batch/window's status.
Timeout/abort precedence, thresholds, timeout 5 seconds, retries 0, full evidence,
permissions, proposals and write behavior are unchanged. SDK error text, body,
headers and URLs remain absent. Renderer omits malformed/out-of-range values.
Original runtime bytes are preserved in two before-http-diagnostics fixtures.
Replacing those two files plus the original exit-status verifier exactly restores
R12's frozen digest; diagnostic code was NOT in the R12 image.

Given/When/Then regression scenarios preceded implementation. Three new tests
failed before numeric status support/rendering and passed afterward; 52 affected
Jev/receipt tests passed. Full continual-learning gate **852 passed in 255.21 s**;
root TypeScript check, install check (17 packages, 18 settings entries), target pack
dry-run and root pack check (18 manifests) passed. Fresh independent review of
status trust, privacy, failure propagation and unchanged write boundaries found
no blockers. Actual isolated native **Pi 1.0.0** `--print` also rendered controlled
HTTP 429 with no raw private error. That native evidence uses loopback/model and
HTTP fixtures, zero external inference requests; it proves integration, not real
Jev quality or a real 429. `jev-http-diagnostics-native-print-evidence.json` records
these boundaries. No command syntax or interactive TUI behavior changed.

A separate prospective, source-frozen, one-shot PUBLIC synthetic transport probe
then ran exactly three serial real requests (no retries), with existing user
paid-test authorization and environment credential; no key/body/error was logged.
`jev-transport-r12-followup-manifest.json` freezes samples, source, actual requested
version, <=3 requests, unchanged 5-second timeout, conservative estimated input
budget $0.01; offline mock preflight is a separate artifact, not quality evidence.
Real requests were 892, 873 and 24,449 bytes, all **HTTP 200**, actual version
1.13.0, durations **965 / 360 / 425 ms**. Returned usage 5,743 input tokens,
**$0.000241206 estimated input cost**. All three selector results were **uncertain**
and used the original fallback, no writes. Thus current successful transport does
not prove useful learning selection, cannot identify the cause of old R12 failures,
and cannot be substituted for failed workflow arms. Original answer probabilities
were not retained by this transport-only probe, so no exact confidence cause is
claimed. `jev-transport-r12-followup-real-results.json` preserves controlled results.

Research signal: first investigate selector question/state framing and controlled
probability diagnostics on frozen bilingual positive/negative cases, then fresh
held-out cases. Do not loosen thresholds, repeat until favorable, increase timeout
or claim global model improvement from transport success. Full-workflow Jev quality
objective remains unmet; no semantic change is adopted from this three-case probe.

Final independent evidence review also verified original six-arm summary hashes,
Click session/rule hashes, 24/20 partial usage, normalized frozen source and the
three-request public diagnostic manifest/source. No evidence/adoption blockers.
Its bounded caveat is preserved: the one-shot diagnostic writes results at end;
missing output after interruption would NOT justify restarting paid samples. The
sole process actually ended exit 0 and its final output exists; it will not be
rerun. `jev-r12-final-independent-review.json` binds reviewed files and limitations.
Root typecheck after the new research script and scoped whitespace check passed.

## Selector framing: rejected development study

The preceding goal turn was progress: additive production diagnostics, completed
R12 failures and a real transport-only probe changed the next research question.
Current sources and terminal outputs, not an assumed live handle, were checked.
Official live Noul/state guidance was read; Markdown endpoints failed but normal
primary-source pages loaded:
https://docs.typesafe.ai/primitives/noul and
https://docs.typesafe.ai/concepts/state . Noul is a yes/no probability, with true/
false criteria optional. Explicit source/state context and one boundary per question
are appropriate research directions; documentation examples do not validate ours.

A research-owned frozen source copy replaced ONLY two selector instructions, adding
future-session/project scope, user/tool versus assistant source distinctions and
one-task exclusions. Original Noul criteria, independent Memory/Harness directions,
0.9/0.1 thresholds, metadata scoring, manual Memory override, privacy, abort/timeout,
retry0 and write permissions stayed intact. Production selector is unchanged.
Given/When/Then regression initially RED (missing research module), then GREEN;
fixture correction moved captured questions after awaited selection, not a product
behavior change. Boundary .9/.1/.5, both directions, manual Memory and unavailable
fallback are verified; controlled mocks are not real quality evidence.

`jev-selection-framing-development-manifest.json` prospectively freezes 14 fixed
bilingual samples across durable fact/preference, simultaneous learning, speculation,
transient error, one-task instructions and explicit Memory request. Each arm receives
the same evidence, no body projection or thresholds change. The evaluator persists a
reservation before any call and per-result checkpoint; interrupted paid output is
not permission to restart. Max28 serial requests, one paid run, <=64KB each, model
1.13.0, original5-second timeout and conservative expected input budget $0.01.
Offline mock preflight is separate and explicitly has zero external requests.

Real study completed exactly28 requests, actual returned model1.13.0, controlled
Memory/Harness probabilities retained. Before: correct6, wrong2, fallback6;
after: correct7, wrong4, fallback3. False accepted learning directions **2 -> 4**,
all Harness routing, not executed writes. New false Harness directions are English
ordinary package-manager fact and response-language preference. The two simultaneous
positive routes improved from fallback to both, but this does NOT compensate for
new false directions. Manual Memory cases processed in both arms, without Harness,
even though irrelevant Harness probabilities in after exceeded .1.

Thus reject per predeclared no-new-wrong-direction rule; production unchanged,
**no held-out paid calls**, no claim of quality gain from fewer fallbacks. Existing
Memory ranking and candidate/write quality are outside this bounded study; original
R12 empty-index path directly routes and bypasses selector, so this instruction
rewrite alone could not fix those workflow failures anyway. Source-owned helper,
original reports/reservation/checkpoints and rejection artifact are retained.
Fresh independent reviewer also found the two new false directions and confirmed
this is an adoption blocker. New question design must distinguish descriptive facts
and ordinary preferences from permission for enforcement; a future study needs
fresh fixed samples and actual candidate/full-workflow evidence after routing safety.

Study known usage **13,984 input tokens**, estimated **$0.000587328**; median
before319.5ms/after329.5ms, all28 HTTP200 and actual1.13.0. Independent review confirms
unique paired results, original production equals frozen baseline, all4 registered
hashes, and explicit-memory route. It notes result metadata originally omits embedded
source hashes and checkpoint uses overwrite; a clearly POST-RUN provenance supplement
links manifest/results/exact baseline+patched hashes, without retroactive preregistration
claims. The final report is complete; no paid restart is allowed. Future runners should
use atomic checkpoints. Ordinary expressive preference was labeled Harness=false
under the existing restriction/verification contract, not relabeled after results.
Standalone strict check initially lacked the repository's allowImportingTsExtensions
option and reported existing .ts imports; corrected invocation matches configuration
and passes. Root TypeScript check and target dry-run packaging also pass. No production
runtime behavior changed in this research turn, so prior actual Pi/Docker evidence
remains scoped to its frozen version; no new native/TUI integration claim is made.

Final research-turn gate: **853 passed in 259.59 seconds** (all continual-learning
pytest cases, including the new research regression). Root typecheck, explicit
strict research-module typecheck, target pack dry-run, scoped whitespace and frozen
result integrity checks passed. Fresh independent review complete. Paid research
handle35526 exited0 with its complete rejected result; full gate handle84790 exited0.
No live paid process is left, no production adoption, no publication/config changes.
The overall optional-Jev learning-quality goal remains active and unachieved.

## Harness selector obligation boundary: rejected restriction study

Previous turn counts as progress: a completed paid comparison rejected unsafe
question framing and its controlled probabilities identified false Harness routing.
Current production/source and terminal report were rechecked; no old paid handle
was restarted. New research changed only Harness question/true/false criteria,
leaving Memory question, thresholds, multi-label composition, Score, /memory,
privacy/permission/abort/timeout and zero retries intact. Separate research-owned
source module keeps production unchanged. Development labels reused from previous
study are explicitly marked reused, not called fresh heldout evidence.

Given/When/Then regression was RED missing helper, GREEN original .9/.1/.5
boundaries, simultaneous learning, manual-memory override and unavailable fallback.
Prospective manifest froze14bilingualsamples, 2arms, max28 serial actual1.13.0 calls,
5seconds, no retries, conservative $0.01 expected input budget. Offline preflight
is separately marked mock/zeroexternalrequests; it is not quality evidence.
Source scope restricts Harness to explicit prohibition/permission/required check,
with ordinary fact/communication-preference exclusions. The research evaluator
adds atomic per-result checkpoint, persistent pre-call reservation, and final
manifest/baseline/patched/code hashes. No permission or durable mutation occurs.

Actual study completed all28HTTP200/model1.13.0 requests. Before correct6/wrong2/
fallback6; after correct8/wrong0/fallback6. False learning directions2->0;
**fallback did not improve**. Known input13648, estimate$0.000573216;
median before327ms/after359ms. These are routing decisions, not writes or candidate
quality. Original report and manifest remain intact, no favorable repeat.

Fresh independent review identified a contract problem even though development
routing improved: the question excludes lasting positive mandatory behavior,
e.g. always use parameterized SQL or always return required JSON format. Current
14sample development has no such positive obligations, so its aggregate success
cannot establish unchanged behavior scope. Also the predeclared lower-fallback
condition failed. Therefore **reject**, no new heldout calls, production remains
byte-identical with original research baseline. Next design must cover all continuing
mandatory behaviors, plus paired ordinary preferences and one-task negatives; it
must not narrow scope to prohibitions/verification to get passing results.

Review also found a manifest provenance defect in the new research runner: it used
initial parsed samples but recalculated final manifest hash from current disk. An
intervening manifest edit could bind new labels to old samples. Original actual
manifest did NOT change; final recorded hash/currentbytes match. Before-run evaluator
was preserved byte-for-byte in
`fixtures/evaluate-jev-selection-restriction-before-frozen-manifest.ts.txt`, its hash
matches the original prospectively registered code hash. The original report remains
bound to that exact source, not post-run code.

A separate Given/When/Then regression was RED missing frozen-reader, then GREEN
sample manifest and code drift refusal and original restoration. The research-only
reader captures original bytes/hash and original code-hash map, verifies all first,
checks same manifest bytes and registered sources at end, and the runner reports
that captured hash. Original manifest intentionally rejects post-run changed runner
source; no attempt to rerun paid samples, rewrite past manifest or call this a
prospective fix. `jev-selection-restriction-adoption-decision.json` binds rejected
result, original source and explicit post-run fix. Both focused tests and standalone
strict typecheck pass. Full gate pending; no production runtime/native claim added.

Final restriction/provenance turn gate: **855 passed in256.63seconds**. Root typecheck,
strict research-module types, package dry-run and scoped whitespace passed. Fresh
independent review confirms manifest binding fix, preserved original source chain,
unchanged production baseline and rejected adoption. Original paid72146 terminal0,
full855gate32623 terminal0; no live paid process or unpublished successful arm claim.

A second independent security review investigated a more direct output bottleneck:
complete Memory review followed by one candidate uncertainty holds all new candidates.
The reviewer confirms all returned answers are examined, but current diagnostic
failure complement cannot be used as passed/writable indexes; same-batch dependency,
conflict and duplicate relationships are not checked. Whole-plan hold is a documented
contract. A bounded new-only derived-plan transaction could be researched only with
complete bound positive proof, pair independence checks, held-intent-first persistence,
parent revalidation and original rollback. This is NOT implemented or adopted.
`jev-independent-new-memory-research-plan.md` records prospective safeguards and
required RED/GREEN/real evaluation scope. No R12 candidate is reclassified or written
from existing telemetry. This next direction aims at real supported output while
preserving explicit requests; overall quality goal remains active and unmet.

## Read-only complete new Memory candidate observations

Previous turn was progress (actual rejected boundary experiment plus manifest binding
repair); current sources, prospective plan and parent/Jev interfaces were reread.
The independent-new-Memory research plan requires an explicit complete bound result,
not the complement of telemetry failures, before any independence or parent-writing
work. This increment implements that observational prerequisite only. It is not a
smaller definition of the overall quality objective, and it does not adopt partitioned
application or claim an improvement in actual durable output.

Given/When/Then test first failed on missing `candidateReview`, then passed with
optional original-index/check results. Baseline production bytes are preserved in
`fixtures/jev-learning-before-candidate-review.ts.txt` and a hash-bound source record.
Only complete prepared PURE new Memory can emit observations. Expected keys include
body/description support, body/description relationship when existing Memory exists,
and both body/description counter checks for EVERY original window. Each generated
key must exactly correspond to a valid answer; complete request/window/entry/model
checks must hold. Evidence, existing dossier and whole candidate digests must match
captured pre-transport values; each original index has a candidate digest and its
explicit passed/held expected checks. Input mutation, denied/private/cancelled,
missing/failed response, mixed-model, legacy and rewrite paths emit none.

The result is explicitly `purpose: diagnostic-only`,
`sameBatchIndependenceReviewed: false`; original top-level allow/propose decision,
telemetry, confidence, question meanings, transport counts and parent application
paths are unchanged. One candidate's held description STILL holds the WHOLE plan.
Parent does not consume this observation. Digest binding is not permission or an
independence/dependency/conflict proof. No new external questions/calls are introduced.

Three targeted regression cases passed, including independent-review requested
nonempty existing Memory + two original review windows; all8expected support/
relationship/counter checks appear in that positive observation. Fresh independent
security review found no blockers and confirmed original whole-plan hold compatibility.
Initial root typecheck caught an unused map parameter; fixed before broad verification,
then root types passed. No typecheck failure is left as an unrelated error.

Actual isolated native Pi1.0.0 `--print` loaded current plugin and a temporary probe,
using loopback main-provider and Jev response FIXTURES, zero external model requests.
It produced original decision propose, purpose diagnostic-only, independence false,
passed/held candidates and zero durable candidate files. Owned temporary HOME/agent/
project files were removed. `jev-candidate-review-native-print-evidence.json` records
integration only; no real Jev quality/Docker/TUI conclusion. Commands unchanged.
Install check17packages18settings, target pack dry-run, root pack18manifests and
scoped whitespace pass; one trailing documentation blank was corrected.

First full target gate **857passed in257.27s**, plus all3targeted review tests.
The final full gate is rerunning to include the later-added positive multiwindow
case in one858case collection. No live paid experiment is running, no host config,
publication or candidate write was performed. Independence and held-intent-safe
application remain future, unverified requirements of the active overall goal.

Next research-only corpus prospectively freezes8unqueried bilingual pairs across
independent/duplicate/conflict/dependent relations, with exact original evidence
references. Corpus manifest contains zero paid requests and no implementation or
quality/adoption claim. Original parent normalizeNewMemoryProposals accepts all8
structures/references; this is not semantic support or safe partition evidence.
Conflict labels describe pair relation even when original full counterevidence can
hold a candidate earlier; relation-only gold must not override original checks.
Further indirect dependencies, conditional scope and private/safe coupling need
coverage before the future feature. One preliminary tsx -e invocation used CJS
resolution and failed on an ESM peer export; same static check via repository Bun
ESM succeeded. This tooling failure is not hidden or attributed to model quality.

Final unified target gate after the added reviewer scenario: **858passed in258.30s**,
process48668 terminal0. This supersedes first857collection. All3targeted cases are
now in the final full collection. Root typecheck/install/target pack/root18manifest
checks and independent review pass; actual native Pi1.0.0 fixture process47984
terminal0, zero external requests. No paid process, no independent application or
model-effect claim. `jev-candidate-review-final-verification.json` binds current
runtime/test/native/source records. Optional-Jev overall quality goal remains active.

## Real new Memory pair relation research: not ready for application

Previous turn was verified progress: complete-candidate observations with858passing
full tests and native fixture integration. Current source, unqueried pair corpus and
pinned SDK0.6.0 types were rechecked. Official live Choice/JavaScript docs loaded:
https://docs.typesafe.ai/primitives/choice and
https://docs.typesafe.ai/sdk/javascript . Question IDs are not semantic input;
criteria/instructions define labels. Confidence and selected-label probabilities
remain original.9/.8 thresholds, not proof of workflow correctness.

Research-only tests module adds one typed Choice per pair: independent, duplicate,
conflict, dependent or unclear. It compares complete bodies+descriptions and original
sources without inferring support/authorization. Conflict precedes dependency then
duplicate; same topic alone is not a dependency. Given/When/Then test firstREDmissing
module, GREEN unchanged thresholds, unknown/invalid labels and probability shape.
No parent runtime imports this module or consumes independenceObserved. No write,
partial application or original-candidate permission follows from a relation.

Prospective8pair development is4scenario English/Chinese pairs. Exactly8serial real
requests completed model1.13.0,5seconds/retry0. Two independent pairs decisive and
correct; remaining6held, no wrong decisive relation/unsafe independence/missed
independence. Raw winning labels correct6/8: both literal-dependency cases chose
independent BELOW threshold (.55/.69) and were safely held. Do not call held rows
correct classified successes. Known6127input,$0.000257334 estimated tariff.
Conservative wire-based estimated budget corrected from.01 to.03 BEFORE paid run
(8×64KB); old mock preflight has its original distinct manifest hash and is retained.
No source/sample change is claimed between that preflight and first real run.

Independent review before new heldout found missing full original input privacy
preflight, extra-answer namespace check and unknown-model pricing. Original first
helper/runner bytes are preserved; exact hashes match development's prospective
manifest; old results/source stay separate. New Given/When/Then uncited-secret test
REDmissing guard, then GREEN. New runner checks EVERY original snapshot/candidate
through current production judge with fetch always MOCK-throw and private permission
false, before ANY external request; missing/private/sensitive/bounds denial prevents
study. Mock transport never forwards and does not constitute semantic evaluation.
Answers must be exactly relation; wrong model or usage blocks positive independence.
Only confirmed model input is priced; unknown model input is retained unpriced.
New snapshot/code/corpus manifests captured before inference and atomically checkpointed.

Fresh previously unqueried heldout has8new bilingual scenarios (16pairs), not16
independent archetypes. Covers same-topic independence, self-contained condition,
paraphrase duplicate, incompatible scope, named/condition dependency, missing third
record context and description-only conflict. Source/evidence normalization and
mock preflight passed; independent review confirmed gold-label meaning before paid
call. In particular a complete conditional retains meaning without another note,
and absent c.md leaves its environment relation unresolved rather than independent.
Relation-only gold never bypasses original support or full counterevidence checks.

Exactly16serial real heldout requests completed, actual1.13.0, all known usage,
12568input,$0.000527856 estimated. Decisive correct4, decisive wrong0, held12;
unsafe independence0 but **missed independence2/4**. Self-contained-condition
EN/ZH independence probabilities.83/.76 and confidences.78/.69 are below original
thresholds. Missing-context and description-only-conflict rows guessed independent
below threshold and safely held, not reliable category recognition. Raw winning
labels12/16correct,4/16wrong; these are distinct from safe decisive results.

Thus NOT ready or adopted: declared all4independent recognition failed. Do not lower
thresholds, relabel conditions or treat safe holds as actual output improvement.
24real requests combined18695input,$0.000785190 estimate; no production writes.
`jev-memory-pair-adoption-decision.json` binds original reports and distinctions.
A future prospective hypothesis can provide exact parsed body+description views and
explain self-contained conditions without dropping raw content/evidence, but no such
change is implemented/adopted or favorably re-queried here. Full workflow optional-
Jev quality improvement still unproven. Root typecheck/strict research types and
target pack pass; full target suite currently running860cases.

V1 final verification: full target suite terminal0, **860 passed in256.79s**;
root TypeScript and strict standalone research types passed; target pack dry-run
passed. Production runtime unchanged by this pair-only study; no new Docker,
native runtime or whole-workflow quality claim. Both paid processes terminal0.

## Prospective structured Memory pair V2

Follow the observed missed self-contained conditions and low-confidence misleading
independence for missing context/description conflict. Live official State/Choice
docs rechecked: named JSON fields and structured instructions are supported.
Hypothesis: expose exact body and frontmatter description as separate views while
preserving raw candidates and complete original evidence; define a condition
contained within its own record as distinct from a cross-record reference.
V1 source/manifests/results remain frozen. Old16pair heldout becomes V2 development,
never fresh heldout. No favorable retry, threshold relaxation or relabeling.

V2 separate research-only module and runner added, with Given/When/Then two new
regressions: RED missing module; GREEN exact raw/evidence/body/description including
CRLF and conditions, malformed/missing description rejected. Original V1 thresholds
and privacy guard reused. Strict standalone command initially omitted the repository's
allowImportingTsExtensions and failed TS5097; corrected compiler invocation passed.
Root types and target pack passed. Fresh independent pre-inference review confirmed
all hashes, known-development classification, no runtime imports or writes.

Exactly16serial V2 development requests completed model1.13.0, retry0,5s: decisive
correct8/wrong0/held8,unsafe0,missed0. Both self-contained-condition cases now decisive;
4/4independent recognized. Historical V1 same16rows: correct4/wrong0/held12,missed2;
comparison is not contemporaneous paired randomization and development was used to
shape instructions. Median348.5ms(V1) versus335ms(V2);6127/12568V1 token counts stay
separate; V2development16090input,$0.000675780estimated. Development passes its
prospective criterion, permitting one fresh heldout run, not production adoption.

Prepared20fresh heldout pairs (10bilingual scenarios) before inference. Eight
independent cases: orthogonal cache facts, self-contained retry timeout/approval
exception, fully stated disjoint conditions. Negatives: paraphrase duplicate,
worker-limit conflict, description conflict, cross-record value/exception dependency
and unresolved platform context. Full production MOCK privacy preflight passes,
zero external requests during preflight; mocked independence is not quality.
Freeze20requests/max64KB,1.13.0/5s/retry0,estimated$.08ceiling(not billing hard cap).
Declared all8independent/zero unsafe/zero wrong decisive; unclear cannot authorize.
Fresh independent gold/source review pending before paid; no original-support or
partial-application capability follows even if pair research passes.

Fresh independent pre-paid review confirmed all20gold labels and source bindings.
Exactly20serial paid heldout requests terminal0, model1.13.0 and complete usage.
**Correct decisive13, wrong0, held7; unsafe independence0, missed independence2/8.**
Both self-contained timeout+retry conditions held at ENp.78/conf.72 and ZHp.83/conf.78.
This is a new failure despite development conditions passing, so all8criterion fails.
No requery/relabel/threshold change or partial application. Raw labels18/20correct;
both unresolved environment cases guessed dependent at low confidence and held,
not correctly classified. Median341.5ms,20257input,$0.000850794 estimated.
V2 combined36paidrequests36347input,$0.001526574estimate. Original V1 also retained.
`jev-memory-pair-structured-adoption-decision.json` records NOT ADOPTED.
Research signal: self-contained shared-value conditions still ambiguous to this
relationship classifier; a future independent-decision/escalation design needs
new prospective tests. This study does not add a write gate or relieve an existing
Harness. Model-quality goal remains active and full-workflow uplift unproven.

V2 final full target verification terminal0: **862passed in257.77s**. Root
TypeScript, strict standalone research types, target pack and scoped diff check
passed. Independent final review recalculated hashes,36requests36347input and
$.001526574estimate,13decisive versus7held,6/8independent,NOTADOPTED. No production
code/writes, new Docker/native/TUI or whole-workflow acceptance in this increment.
`jev-memory-pair-structured-final-verification.json` binds exact current records.
All paid processes completed; no background paid process or further favorable run.

## Prospective V3 pair Noul decomposition development

Current-state review confirms one bounded semantic Memory repair already exists,
with original identity/privacy preservation, full revalidation and original retained
proposal on failure. Adding another retry is not justified. V2 failed self-contained
timeout while other complete conditions passed. Hypothesis: multiclass relations
compete for probability; independently judge missing context, contradiction,
cross-record dependency and redundancy over exact same structured+raw full state.
Read official current Noul/State docs: https://docs.typesafe.ai/primitives/noul and
https://docs.typesafe.ai/concepts/state . Four narrow Noul questions batched; primitive
has probability and no separate Choice confidence. Original YES.9/NO.1 retained,
not relaxation of Choice's confidence or a re-labeling of the old results.

Research-only new module/runner, Given/When/Then regression RED missing module then
GREEN threshold boundaries, missing/extra/invalid answers and unknowns. Independence
requires all4negative<=.1; any missing context, contradiction, dependency or
redundancy uncertainty means hold. Priority relations may ignore unused lower
branches, but missing context cannot be ignored. Model/version/usage/answer-set,
privacy preflight, bounds, frozen source/corpus and reservation inherited. No
runtime import, no authorization/partial application. Known V2held20becomes V3
development, never fresh heldout. Frozen20requests,1.13.0/5s/retry0,estimated$.08
(not actual billing cap). all8independent and zero unsafe/wrong required before
any new heldout. Original V1/V2 source/report/failed decisions stay unchanged.

V3 independent pre-paid review passed exact source/corpus20requests. Exactly20
serial real requests terminal0, actual1.13.0:correct1/wrong0/held19/unsafe0,
missed8/8independent. NoulmissingContext usually.15-.20 even known complete samples,
which holds all validindependent. Declared criterion FAILED; no freshheldcalls.
22377knowninput,$0.000939834estimate,median345ms. NOTADOPTED; no calibration
claim from4samebatch judgments. Original sources/results frozen, no favorable rerun.

Next actual runtime diagnostic R13 preregistered one p-limit/on isolated Docker
execution using current source including numeric HTTP diagnostic. No model/prompt/
threshold change or partial application from failedpair research. Original full
task assertions retained. Prior R12 p-limit transportcause unknown; new execution
is new evidence, cannot explain the old request conclusively or serve as paired
quality comparison. Live credentials present, mainmodel currentqwen3.8-flash;
180totalrequests hardcap, tariff estimate not billing hardcap, priorauthorization
applies. No concurrent paid process. Docker29.4.0 ready.

V3 final scoped gate terminal0:863passed258.86s,root+strict standalone types and
targetpack passed. Independent final review confirms exact metric/cost/source and
failedcriterion, no calibration or quality claim. Separate R13 real Docker still
running under original handle95480; not restarted due observation timeout.

R13 one p-limit/on real Docker execution terminal0 **passed original full task**.
Image d15717488ddb785cd98569adf24f91357429202c342364318bc56383fa3bba19;
source720269bdc080cfa64e92ddc2cf4e348e96c005c4460e50417e25844d79717f04
checked premanifest/image/runtimereport/endhost. Pi1.0.2/Node22.23.2/Linuxaarch64.
Main29requests plusJev8,aggregate37,error0. ActualJev1.13.0/all8usagecomplete,
49655input,$0.002085510estimate. Memory3operationsapplied/full22entries3windows/
4completedrequests/1082ms; Harness1applied/same22entries3windows/4requests/1216ms.
Main learning220.6s includes generated regression+verification and childplanning,
not solely Jev latency. New session private preference recall, full Memory body
reads, verifiedcommand, safe mirror byteidentity, nativeblockedgitpush/no sideeffect
and unrelatedbashallowed all passed. Baseline no private recall is intended
negative control. Original full task assertions unchanged, no verifier correction.

This is one current-runtime diagnostic, **not paired overall learning uplift**.
No service failure reproduced, so trustedHTTPdiagnostics not exercised against
realfailure here and R12failure rootcause stillunknown. Noulresearch NOT imported
or adopted. Earlierfailedruns retained, no winningproject-selection effect claim.
`jev-r13-p-limit-diagnostics-real-results.json` binds originalsummary and exact
manifest. Current quality goal remainsactive; next outcome must include actual
falsewrite/missedvalid learning comparison, not replace it with a single usable run.

Independent R13 final read-only review confirms exactsource/summary/SHA8Jev+29main,
49655input,$.00208551,3Memory+1Harnessapplied/fullcoverage and originalcontrols.
Combined turn20research+8runtimeJev72032input,$.003025344estimate,mainfees separate.
No paid processes live; both13084/95480terminal0. No productioncodechange/adoption.
`jev-r13-final-verification.json` binds full863testgate/types/pack/reviews/results.
WholeoptionalJevqualityobjective remains unproven/active.

## Prospective current-Jev same actual generated candidate replay

Previous goalturn made verified progress: R13actualp-limit/on originaltaskpassed,
V3Noul rejected/all8valid independenceheld. Current runtime inspected unchanged.
Use old hash-bound3actualunsafeHarness plans and originalR13Memoryplan3newrecords
with their full originalsnapshots. Not fabricated candidates/regeneration. Four
known plans from2repositories; not7independent scenarios or freshheldout. One
unsafeplan has a known badoperation1 and an unlabeledoperation0: no claim that
whole-plan rejection satisfies all intendedconstraints or all heldparts are bad.

Official currentModels/Confidence docs rechecked https://docs.typesafe.ai/models
and https://docs.typesafe.ai/confidence . Pinned1.13.0/input$.042M/outputfree,
actualmodel/version/knownusage mandatory, no thresholdchange. Existingauthorization
allows isolatedsyntheticprivate preference replay with explicitresearch optin; no
classification or productiondefault changes/no hostpersonalMemoryread.

New read-only inputhelper verifies every plan/snapshot/reportSHA before extraction;
Harness currentstructurevalidation and originalMemorynormalization equality.
Given/When/Then REDmissingmodule, GREENhashdrift refuses alteredcandidate before
inference. Strictstandalonetypes passed after explicittypedrows correction. Freeze
allruntimeextensions plusrunner/helper/manifesthelper; alloriginalinputs go through
productionMOCKprivacy/bounds beforeANYpaidrequest. Offdeterministicdisabledzero
request is local counterfactual; ononecurrentrealjudgereplay. No parentwrites,
no modelwrites or partialapplication.48hardrequestbudget/5s/retry0;$.15wire-based
estimate(notbillinghardcap). Unknown/service/bounds remainincomplete; cannot count
as semanticquality success. Needall4complete,zero falseaccepts/holds andsafe3Memory
retained to claimonlythispoolprecisionbenefit. Mockpreflight19fixtureanswersall
forcedallow,zeroexternals,notmodelquality. Independentprepaidreview pending.

Independent pre-paid review confirmed originalrisk labels, exactquotes andsynthetic
privacy unchanged; identified partialusage-loss inrunner and suggested explicit
coverage presence. Addednewregression REDmissingusageexport thenGREENknownlower
bounds/unknownpricing retained. inputTokens??knownInputTokens preserved; judge
reported estimates used onlyconfirmed model/notinvalidresponse, never apply tariff
tounknownversion; unverifiedJudgeEstimatedCostUsd separatelyretains unverified
originalestimate. Coveragewindows/entries mustexist, not undefined==undefined.
2focusedtests+stricttypespass. Old19mock's2originalsourcefiles/manifest preserved
exactly; newmanifest/codeSHA re-frozen BEFOREanyrealcall. Oldmocknotrewritten or
claimedsamesource. Realrunner stillre-preflightsALLoriginals beforepaidtransport.

Afterfix independentpre-paidreview approved exactSHA/labels/privacy/budget and
partialusage handling. Exactly19realrequests terminal0,actual1.13.0 and all4
planscomplete. Known110584input,$0.004644528estimate. Off4plansallows3unsafe/no
validhold; onfalseaccepts0but**falsehold1validMemoryplan containing3records**.
ThreeunsafeHarnessplanshelduncertain,full28/18/17entries reviewed6/4/2windows.
ValidR13Memory nowheldcandidate0counterevidenceuncertain/full22entries3windows.
OriginalR13allowed thissameplan; currentreplay new inference doesnotrewrite prior
record. No favorable retry. Do notcallcorrectholds3netqualityuplift whilevalid
planheld. Declaredzerofalseholdcriterion FAILED. Modelrawanswers were not stored;
actual failedcounterwindow isunknown because currenttelemetry neverretained it.
Do notinvent rootcause from plausible alternative verificationcommands or claims.
No existing Harness removed; original proposalflow and allthresholds remain.

`jev-actual-candidate-paired-effect-decision.json` binds failed criterion and next
action: retain controlledwindow/entry-range diagnostic before semanticrepair,
without rawprivate text or new writepermission. This is futurework notimplemented
in this increment; research-only usage/coverage defects fixed. Initialfullsuite
864passed262.01s(collectedbefore secondusage regression added);2currentfocused
regressionspassed,finalcurrentfullsuite will rerun865cases.

Final research-only verification: 865 passed in 260.06s, exit 0. Root and strict runner TypeScript checks and target pack dry-run passed. Independent read-only review confirmed frozen source/input hashes and the failed quality criterion. No new Docker execution or production runtime change in this replay increment.


## Controlled counter-window diagnostics after the failed replay

The frozen actual-candidate replay failed its declared zero-false-hold rule. Do
not infer its historical failed window: that call never retained one. No favorable
re-query, lower confidence threshold, new model gate, or partial Memory write was
added. The exact pre-change production files are preserved and SHA-matched against
that replay's manifest in `jev-counter-window-source-preservation.json`.

Given complete indexed original windows, a held body or description counter check
now captures the zero-based window and inclusive original entry-index range before
transport. The first failure per candidate and whole-plan first failure retain the
location. Support-first holds do not claim a counter location. Incomplete, failed,
cancelled and mixed-model batches remain proposed without an invented location.
Receipt and repair-hint formatting validate nonnegative safe integers and ordered
ranges. Repair hints validate controlled candidate/dimension/field/reason values;
they fit 15 lines and 400 characters per line and explicitly report truncation.
Existing whole-plan application and every semantic/parent gate remain unchanged.

Both new regressions failed before implementation (missing numeric location and
missing display/hint location), then passed. Focused affected tests: 54 passed in
26.75s. Root TypeScript passed; installation check passed (17 workspace packages,
18 settings entries); target pack dry-run passed. A fresh read-only reviewer
`counter_window_review`, without implementation history, found no concrete
regression and additionally verified mutation and mixed-model scenarios in isolated
fixtures. No reviewer edits or external inference.

Actual native Pi 1.0.0 `--print` in an isolated temporary HOME/agent/workspace,
without tools or discovery and with global external fetch rejected, used one offline
provider response. Complete 3-window review held candidate 0 description at window
1, entries 1-1; receipt/hints matched and operations stayed 0. No candidate file
was written. This proves diagnostic integration only, not real Jev improvement or
a new Docker workflow. Paid research remains exactly 19 calls, actual 1.13.0,
110584 known input tokens and $0.004644528 tariff estimate; no paid calls in the
diagnostic increment. Whole-workflow quality improvement remains unproven.

Final diagnostic verification: 867 passed in 267.77s, exit 0. Root types, installation, target packing and all 18 root packed manifests passed. Scoped whitespace check passed. The original quality failure remains unresolved and the goal remains active.


## Prospective explicit chronology Memory counter development

Fresh 16 public synthetic EN/ZH samples (8 valid/8 invalid), with user/verified-tool
source roles and original quotes preserved. Original production whole-plan judge
used for both arms; research-only after arm adds original cited/window index fields
and a temporal instruction to distinguish resolved earlier faults from later
revocations. Every original entry, support question, body/description counter,
Choice criterion and .9/.8 threshold remains. No deployment or parent writes.
Official State/Choice docs recommend named related fields and clarify question IDs
are not visible to the model: https://docs.typesafe.ai/concepts/state and
https://docs.typesafe.ai/primitives/choice . This was a hypothesis, not a claim
about the old R13 failed counter-window, which remains unknown.

Given original production requests, RED missing helper then GREEN original-state,
candidate/criteria preservation, no support mutation and missing-candidate denial.
Strict standalone runner typecheck passed after correcting SDK config `timeout`
before freeze. Manifest binds every production extension, research helper/runner
and corpus before paid calls. All samples pass production offline privacy/bounds;
forced preflight64 answers establish wire/response plumbing only. Fresh reviewer
`temporal_research_review` found no blocker for this fixed single-window corpus.
It noted that larger future multi-window preflight must not stop at the first mock
failure group; strengthen that before a different corpus, never assume complete
transformed preflight from mere dispatch count. Hard64transport requests, 5s,
retry0, one paid process, alternating arm order; current environment key presence
verified without revealing credentials. Published wire-based estimate bound $.18,
not an account billing hard cap. Every sample/arm is complete, actual1.13.0.

64real requests terminal0. Before15/16correct,0falseaccept,1validhold; after exactly
15/16correct,0falseaccept,1validhold. Same sole held sample replaced-toolchain-zh,
first failure support/uncertain in both arms, not counterevidence. No probabilities
were retained; do not infer cause from language, scope or individual Choice labels.
No improvement criterion met, no new heldout spend or production adoption. Total
66866knowninput, $.002808372 tariff estimate: before31013/median353ms,
after35853/median359ms. Explicit chronology added4840 input tokens without a
measured gain. Zero transport/schema/coverage failures. Original reports/reservation,
source and labels are unchanged. No favorable retry, confidence relaxation, privacy
change or new Docker workflow. Full-workflow uplift remains unproven.

Final temporal research verification: 868 passed in 262.90s, exit0. Root TypeScript, strict research runner, target pack dry-run and scoped whitespace checks passed. Fresh post-call review confirmed source/corpus/report hashes and rejection metrics. No new Docker, native Pi or production runtime changes in this increment. Goal remains active.


## Prospective narrow Noul Memory support known-development comparison

The prior temporal study's complete16case/8pair corpus is reused as KNOWN
development. Existing failures and labels are immutable; this is not fresh heldout.
Read-only owned judge copies use the byte-identical current production baseline.
Only fully cited new Memory body/description support becomes a narrow Noul;
legacy/mixed operations keep Choice, full counter and relationship Choice gates
remain, YES .9/NO .1 unchanged, Noul has no separate confidence. Official Noul/SDK
interfaces checked: https://docs.typesafe.ai/primitives/noul and
https://docs.typesafe.ai/sdk/javascript . No production runtime change.

Three Given/When/Then regressions RED missing helper, then GREEN (3passed0.70s):
new-support types/holds/privacy/legacy, exact controlled numeric observations, and
complete later-batch preflight with late oversize or sensitive input denial.
Preflight now completes ALL required fixture responses before ANY paid transport,
not just a first dispatch group. It returns original coverage and rejects incomplete
coverage, bounds and privacy. Forced64offline answers are not accuracy evidence.
Numeric observations require exact answer keys, expected types/criteria, finite
[0,1] probabilities, ordered controlled indexes and pinned model. Original request
SHA256 is retained without state, private names or SDK-error/response dumps.
Strict runner TypeScript passed. Freeze all runtime extensions, exact baseline,
helper/runner and corpus. Fresh reviewer memory_support_research_review found no
blocking issue; flagged missing direct mixed/existing-relationship fixtures and
checkpoint granularity after each pair (abrupt loss possible, never permits rerun).
Current credential presence checked without printing key; existing authorization,
hard64requests/5s/retry0/onepaidprocess, $.18wire-based estimate notbillinghardcap.

Real64requests terminal0, actual1.13.0, all32arm resultscomplete. Before15/16correct,
0falseaccept,1validhold; after14/16correct,0falseaccept,2validholds. REJECTED: extra
valid hold, no fresh heldout spend or deployment. Known59242input,$.002488164
estimate: before31013/median535ms, after28229/median530ms. Lower token usage is not
learning-quality improvement. The existing Chinese toolchain hold remains:
before body grounded .79/confidence .74, description .90/.88; after Noul body.66,
description.64. New English report-preference hold: baseline grounded1.0/1.0 both
fields; Noul .89 both, below unchanged YES .9. No favorable retries or thresholds.

Current corpus inspection suggests a specific next hypothesis: toolchain candidate
states current configuration, its cited user quote states future-task use, and the
same original snapshot has an earlier verified migration observation not included
in cited support. Current support requests project only cited entries. This is an
observable source/citation distinction, not proof of the model's internal cause.
Verify citation completeness or faithful wording prospectively. Do not relabel
original valid-knowledge gold or turn rejected Noul into production. Goal remains
active; real Docker full-workflow improvement is still unproved.

Final narrow-support research verification: 871passed268.15s, exit0. Root TypeScript, strict runner, generated owned judge strict types, target packing and scoped whitespace passed. Fresh post-result review verifies source/corpus/report/64numeric observations and rejects adoption. Paid5217terminal0, no new Docker/native Pi or production changes. Citation coverage hypothesis recorded without relabels. Goal remains active.

## Original citation completeness: positive development and fresh heldout signal

Research keeps the original production Choice judge, every threshold, candidate
content/name/kind/classification and original citation. The bounded public-only
helper adds full actual original user/tool entries (no assistant, no truncation,
max2000chars per quote/max8 quotes). Privacy or reclassification fails before
transport. This attach-all is a controlled experiment, not a production strategy.
Official citation guidance separates string matching from checking source context:
https://docs.typesafe.ai/cookbooks/citation_check . Exact original quote validation
and all full-snapshot counter gates remain authoritative.

BDD plus two regressions RED missing helper2failed0.07s, GREEN2passed0.69s.
Strict TypeScript found a role inference issue; exported NewMemoryEvidence typing
fixed it before paid calls. Initial offline artifact retained as initial-untyped,
latest source re-frozen. All arms complete offline preflight before paid dispatch;
forced answers provide no accuracy evidence. Actual credential presence verified
without key output, pinned1.13.0,5s/retry0, serial paid processes, alternating arms,
pre-call hash manifests and post-call hash verification, owned reservations.

Known16development samples:64realrequests,32completearms; before15/16correct,
0unsafe/1validhold,after16/16correct,0unsafe/0hold. Chinese toolchain case was the
sole changed decision. Before31013tokens/median380.5ms,after32663/413ms;total63676,
$.002674392 tariff estimate. This supported a fresh heldout study, not deployment.

Fresh24samples/12bilingual scenario pairs:96realrequests,48completearms; before
15/24correct,0unsafe/9validholds;after23/24correct,0unsafe/1validhold. Both arms
reject all12unsafe samples. Four original-support/later-retraction cases added
BEFORE any heldout inference after independent pre-review; original weaker corpus,
manifest/preflight preserved as initial-simple-negative. No gold changed after
inference. Remaining unrelated-network-zh valid hold remains uncertain, not retried.
Before45455tokens/median481ms,after48273/485.5ms;total93728,$.003936576estimate.
Actual1.13.0 in all responses;160combinedrequests/157404knowninput,
$.006610968total estimate, no missing priced usage; account billing not verified.

Positive signal is specific to missing original citation coverage. It does not
prove individual model causal reasoning, privacy/relationship/multi-window or
multi-candidate quality, generation or Docker full-workflow uplift. Production
runtime/prompts unchanged, zero candidate writes. Next prospective step: guide
main-model candidate generation/one existing repair to cite every factual claim's
relevant original source, retain all original gates, then actual generated/Docker
paired verification. Goal remains active.

Final citation research verification: 873passed272.28s exit0; root types, strict both runners, target pack dry-run and scoped diff check passed. Independent pre-call/post-result review passed. Both paid processes terminal0. No production runtime/prompts, Docker or native Pi changed in this research increment. Narrow development and fresh heldout criteria met; production adoption pending real generated/Pi workflow verification.

## Production citation guidance and prospective R14 workflow verification

The previous positive public citation experiment motivates guidance, not automatic
attach-all. Before implementation, two BDD regressions failed (2failed0.41s): both
Memory prompt builders must receive the same claim-specific citation requirements,
and the actual semantic repair worker must receive them while remaining tools[],
identity/context preserved, no guidance added to structural-only repair. GREEN
2passed0.38s. Before-source fixtures preserve exact planner-prompts/inject-memory
bytes, including earlier unpublished improvements. Current changes only append
shared MEMORY_CITATION_GUIDANCE to full/incremental generation and the existing
semanticContext repair. No Jev primitives/thresholds/candidate classification,
identity retention, frozen snapshots or write authority changed. The guidance asks
for actual source support for current/config/verification claims, future-vs-now
scope, later corrections and original8/2000bounds; explicitly forbids attach-all,
secrets, unrelated knowledge and Harness changes. Fresh read-only independent
citation_generation_review found no blocker and ran2tests. This prompt wiring
proof does not establish actual generator compliance or learning quality.

Isolated actual native Pi1.0.0 --print offline fixture passes both generation
prompt wiring plus original3window descriptionhold/0operations; not real model
quality. Root types/installation17packages18settings/targetpack pass. Full target
suite and actual paid Docker study are pending at this initial record.

Prospective R14 freezes source beedbeebea1f64794d21d8339fb151fa3974ed3a4ad4735bc1dfe4b6cbe274df,
three fixed upstream commits, optionalJev off/on6independent serial Docker runs,
main cli-proxy/bailian/qwen3.8-flash, Jev1.13.0/5s/retry0,shared360providerrequests.
Existing user paid authorization, tariff metadata freeze, no hostconfig writes,
real provider proxy with ephemeral container token. Original regression/private
recall/sharedmirror/blocked+allowed execution criteria retained. This current
runtime on/off study is not a prompt-before/after causal experiment. Do not claim
current prompt production effect or goal achieved before actual fullworkflow proof.

Citation generation local gates completed: 875passed265.73s exit0; roottypes, install17packages18settings, targetpack, root18packedmanifests, scopedwhitespace and exactbeforefixtures passed. Independentreview no blocker. R14 paidprocess session61811 confirmedlive, Clickfirstarm in activeDocker, no terminalreports/summary yet. This is an active verified wait, not workflow completion; preserve same process, do not restart due to observation timeout. Production prompt quality and fullgoal remain pending.

R14 continuation: original paidprocess61811 confirmedlive by terminal poll (30s observation no new output) and current active Clickon container. First Clickoff fullworkflow passes all original11checks. Read-only actual generatedplan inspection checks exact original snapshot/manifest hash and citations: projectfact includes userrequest and successfultoolresult; private preferencequotes remain useronly. Stored only indexes/roles/classification/counts/hash, no raw preference/name/claim text. Artifact jev-r14-click-off-citation-inspection.json. This demonstrates one actual generation wired to relevant tool evidence, not causal prompt effect or paired Jev uplift. Remaining5executions pending; no rerun/sourcechange.

R14 Clickpair completes off/on all11originaleffects pass; no observed capabilitygain. On eligibility realJevParticipation is additional, not an effectgain. Memory firstholdcandidate1/support uncertain, one bounded repair, secondoriginalJev supports fullplan ->Memory2applied/Harness1applied. Exactrepair inspection shows bodychanges and projectcitations3->2useronly; no causal claim citationaddition produced pass. Privacy/identities preserved, originalbeforequeries not retried. ActualJev12requests72030input/4081ms,$.00302526tariff estimate. Learningoff157.64s/on257.21s; difference includes mainmodel/planning/repairstochasticwork, notpureJevoverhead. Same originalprocess61811 now p-limitoff;2of6terminalarms, nofinalsummary. Sourceunchanged. Artifact jev-r14-click-paired-interim.json. Goalactive, nofullworkflowqualityconclusion.

Fresh independent Clickartifactreview (citation_generation_review): no blocking originalsupport/scope/privacy/Harness issue. Finalexactquotes and snapshot/appliedplandigests verified; on fact explicitly attributed to user without newexecutionclaim, privateconstraints retained and projectexports clean. Same anchored projectpushregex and native block/nosideeffect/unrelatedallow evidence. Baseline can manually discover privateMemory on sharedfilesystem and actually did; freshrecall is not a demonstrated recallgain. Onrepair changes正文andcitations; cannot attribute pass to citationaddition. Review included in jev-r14-click-paired-interim.json. Originalprocess61811 still running p-limitoff, no runtime edits or restarted execution.

R14 continuation: p-limitoff complete, all11originaleffects pass; learning276.16s,Memory2/Harness1applied. Frozen snapshot digest and exact original quotes verified: projectcandidate cites user plus successful toolentry19; privatecandidate useronly, no text/names printed. Threeof6terminalarms allpassed; p-limiton started in same originalprocess61811. Sourceunchanged; no improvement conclusion from incomplete pair. progress-observation.json binds eachcompletedreportSHA and keeps fullstudy/goalcompletefalse. Independentcontentreview requested for newcompletedoffarm.

Independent p-limitoff artifactreview completed: no blocking frozenidentity/exactquote/publicclaim/privacy/Harnessscope issue. Actualtool+independentexit0 support the publiccommand fact; private no-sharing scope retained and exports clean. Baseline manualprivate discovery again prevents recallgain inference. On notterminal. Saved controlled review in jev-r14-p-limit-off-content-review.json.

R14 p-limitpair terminal: offpassed/onfailed at No successful real Jev memory judgment. On realregressionchanged+independentcheck pass, learning426.56s vs off276.16s. Alloriginal32entries/3windows reviewed completely actual1.13; notcapacity/servicefailure. Memory support.description candidate2 uncertain +candidate0/1counterwindow1entries7-24uncertain. Memoryattempt0rejected/attempt1proposed, nosecondMemoryJevtelemetry; exactrepaircause underindependentreview, do not infer fromoutcomelabel. Harnessscope uncertain before/afterexistingrepair. Jev12requests81711input,$.003431862estimate; no originalquotes orprivatevalues ininterimreport. This is observed wholeworkflow regression, safetygold still requiresrawcandidateaudit. Originalprocess61811 nowmitt,4of6terminalruns, allfailureevidence retained, sourcefrozen. Artifact jev-r14-p-limit-paired-interim.json. Goalactive, improvement unproved.

Independent p-limiton review resolves failure interpretation: structural repair firstconsumes sharedone-slot, then singleJev wholeplanproposal; NOT semanticrepairfailed. Specific initialschemaerror notretained and remains unknown. Candidate2 genuinely expands one-task learning-handling into standingpreference and invents agentsettings persistence in description; do not markall3asgoldvalid. Candidates0/1 have originalfacts/privacy intact, counterwindowuncertainty cannot explain internalmodelcause. Harnesscanonicalprojectmatcher has no observed overbreadth, scopeuncertain nottemplateerrorproof. Zero appliedwrites correctly prevents unsupportedcandidate but also withholds2validrecords; not overallqualityuplift. Allsnapshot/quotes/bounds verified. Corrected jev-r14-p-limit-paired-interim.json without alteringoriginalreports/responses or source.

R14 mittoff terminalfailed native-harness-enforcement: modelrefusal yielded no nativeBashattempt, so actualhookeffect unproved. Earlier regression/privateMemory/publicfact/mirror/freshrecall/fullread/verifiedcmdchecks passed. Originalfailure retained, no retest or weakenedassertion; missingcoverage notproof wrongregex or unsafewrite. baselinePrivateRecallfalse is observation, notunconditionalrequiredTrueeffect. Same process61811 nowmitton finalarm,5of6terminalruns3passed2failed; sourceunchanged. Indep artifactreviewrequested. Artifact jev-r14-mitt-off-interim.json. No overallJev uplift inferred.

Independent mittoff review confirms actualmissingnativepushcoverage: one unrelatedallowedBashcall, no targetpushcall, modelexplicitselfrefusal. Storedprojectclaims/description, privateclassification/nosharing, exports, canonicalHarnessscope and allfrozenquote/digests have no blocking finding. baselineprivatefalse/freshtrue distinguish observation but cannot cancel originalnativecoveragefailure. Reviewboundin jev-r14-mitt-off-interim.json, no rerun.


## R14 terminal result

Six original isolated executions completed, exit 1. Off 2/3, on 1/3; no overall quality uplift. Source and image are bound in @jev-citation-guidance-r14-final-results.json. Provider requests are 199 total = 166 main + 33 Jev (not 199 main). All 33 Jev usage records report jev-1.13.0, 209107 input tokens, estimated $0.008782494. Recorded main usage estimate is $0.126141900; full main usage coverage and account billing are unverified. No retries/relabeling repaired these original outcomes. Structural repair consumed the only repair slot in p-limit Memory and mitt Harness; its blindness to frozen evidence is a prospective hypothesis, not a demonstrated cause. All original failed reports retained.


## Structural-repair frozen-context local increment

Given/When/Then in @../features/jev-structural-repair-context.feature. Initial RED2failed0.81s: missing frozen loader and private-to-safe repair incorrectly accepted. GREEN4passed1.11s after implementation including existing citation tests; additional production-flow RED1failed confirmed completed repair usage was lost on correct bound snapshot tampering, GREEN39passed24.26s with full relevant Jev tests. Fresh independent review identified that accounting defect and the context-based fixture classifier; both fixed, reviewer39passed/no residual blocker. Full first sweep877passed280.61s (collection predates two added cases); final879-case sweep pending. No new real-model effect yet. Current authoritative final R14 data in @jev-citation-guidance-r14-final-results.json.

Final structural-context local gate:879passed278.06s exit0; roottypes, install17packages18settings, targetpack, root18packedmanifests, nativePi1.0.0 offlinefixture and fresh independentreview passed. Runtime sourcebacf936aaefbb9d601f32d9d07c14b29739af14f2c056e30566d40ed2f5d1afd matches prospective R15 manifest. Mainmodel/credentialpresence verified without logging secrets. Six serial paid real workflows may now start under original360totalrequests hardcap; none of the local mock results is real quality evidence.


## R15 active continuation and next read-only hypothesis

R15 process50837 verifiedlive; production digest remainsbacf936aaefbb9d601f32d9d07c14b29739af14f2c056e30566d40ed2f5d1afd. Firstthree originalarms:Clickoff setupDNSfailure,Clickon Memoryheld/Harnessapplied/independentregressionpass,no firststructuralrepairtrigger;p-limitoff alloriginalworkflowcheckspass. No causal repaircontext gain or broadJevuplift established. Clickordinal2 quote positions/frozenhashes verified independently but semanticgold remainsunverified; not labeledunsafe orfalsehold.

Prospective researchonly userquote anchoring in existing Harnessfamilycandidate, with unchanged questions/criteria/full original state/counterwindows/thresholds/writeauthority.24unqueriedpublicbilingualdevelopment cases,12positive12negative, labels independentlyreviewed. RED2missinghelper; GREEN4 after sourceidentityregression RED1 strippedexception accepted fixed.96complete forcedoffline transports/48arms,zeroexternalcalls/writes; forcedmock acceptsallnegatives are not accuracy results. Strictresearch/roottypes/freshreviewpassed. Liveguardblocks preconditions/reservations/API because R15 isstilllive. Manifest/corpusgold/code hashes frozen; initialpreflightbeforeliveguard retained. No adoption. Finalpackage883testsweepactive90806.

Research preparation final gate883passed282.95s exit0; strictresearch/roottypes/scopedwhitespace/freshreviewpassed. FouroriginalR15arms complete, process50837stilllive onmitt-off. p-limiton applied2Memory aftersemanticrepair, Harness heldscopeuncertain thenrepairrejected retainedidentity/originalcitation mismatch; missingrepairedHarnessplan prevents narrower diagnosis. Originalreport/failurekept; no firststructuralMemoryrepairtrigger. Independenthash/quote/privacy/digestchecked, fullfactualentailment stillbounded. No overall qualityclaim.

R15 terminal exit1 all6originalarms. off2/3,on0/3;176totalrequests=140main+36Jev,259134Jevinputtokens,estimated$0.010883628. No overalluplift. One structuralMemoryrepair recorded in off arm only; on frozen-contextrealtriggercoverage remainsmissing. All originalfailures preserved. R15 terminal50837/dockernone confirmed before enabling newquoteanchor research; originalblockedmanifest retained byte-for-byte; fixedgold/corpus/code hashes unchanged.


## Harness citation-anchor terminal decision and repair-binding increment

Real process38817 exited0 after96requests. Before23complete/1incomplete/0falseaccept/1falsehold/22correct; after23complete/1incomplete/0falseaccept/2falsehold/21correct. Known69318inputtokens and$0.002911356estimate are partial lower bounds, not complete account billing. Both arms timeout on general-en; the added valid hold is a counter judgment, so causal harm from quote anchoring is not established. Reject/no production adoption/no heldout inference. @jev-harness-citation-anchor-adoption-decision.json.

Following R15 p-limit Harness repair rejection, preserve the entire parent-owned rule/citation binding explicitly in the existing repair prompt; distinguish controlled retention failure categories. Specific original rejected-field subtype remains unknown because its repaired plan was not retained. Given/When/Then in @../features/harness-repair-bindings.feature. RED2failed0.88s; GREEN new and existing repair tests30passed15.34s; roottypecheck passed after fixing local narrowing. Fresh independent read-only review found no blocker and30passed. This verifies boundaries, not actual model compliance or workflow quality.

Identical-request audit confirms the newly held mixed-task-zh counter transport has the same wireSHA850b79aeca89cf1eb8d0eea740d4f30815fcf40229ed9c32dc820b42188f1b2d in both arms but different numeric judgments. This is observed response variation, not evidence that the added quote itself caused that hold. Adoption remains rejected: the observed comparison did not pass the predeclared rule. No favorable retry or new paid requests. @jev-harness-citation-anchor-identical-request-analysis.json.

Harness binding local final gate885passed310.31s; typecheck, nativePi3passed10.26s, targetpack, workspace19packedmanifests, freshreview passed. Installation check exited1 solely because unrelated new bdd-jev is unconfigured; continual-learning remains configured, no host configuration changed. Frozen prospective R16 p-limit pair now starts with source5818b1f6be33de6acce0cd035e331d631ccf08c4178883466429a7df655e2967, samepins/models/gates, shared360requestcap. Historical R15 is not a controlled generator baseline; repaired-binding trigger and results must be separately measured. @jev-harness-bindings-r16-docker-manifest.json.


## R16 original p-limit pair terminal

Process20255 terminalexit1, runtime/image source5818b1f6be33de6acce0cd035e331d631ccf08c4178883466429a7df655e2967 unchanged. Originaloff passedall11checks, learning275.59s; originalon failedlearningeffect gate, independentprojecttest0exit, learning348.88s. On Memory usedfirststructuralrepair then finalJevtimeout;2candidates retainedexactly asprivateproposal,noMemoryapply. OnHarness supported/apply1, no semanticrepair. Bindingpromptactualtrigger0, so productionprompt effect remainsunverified. Independentreview confirmed3snapshot hashes/6Memorycitations/proposalretention/privacy andHarnessposthash; originalonHarnessplan andstructuralrepairrequest unretained, nofullsemanticgold orfreshon recall/enforcementcoverage.

44totalproviderrequests=38main+6Jev,1providererror. Proxy5Jevusage responses contain31414knowninputtokens/$0.001319388estimate; parentreceipt4completedJevrequests contains21572knowninputtokens. Lateproxyresponse usage doesnotcount as semanticcompletion; missingusage unknownnotfree. Recordedmainusageestimate$0.039572702, coverage/accountbilling unverified. No favorable retry/relabel/gatechange. @jev-harness-bindings-r16-final-results.json and @jev-harness-bindings-r16-known-main-usage.json.

Exact historicalR15p-limit repair input isavailable: parentvalid1operation/1citation, snapshothash7da9861460df8608df37f0712adb5e05c13c2af6cdb77fccd080a031bf2a0425. Before/after task preparation independentlyreviewed: removingthetwo addedinstructions andbindingtable restoresoriginalbytes; position/table matchproduction. Paidguard remainsfalse untilnativecontainerpath/toolboundary preflight; no additionalcalls. This prospective one-known-input comparison isnotheldout orwholeworkflow proof. @jev-harness-bindings-original-input-preparation.json. Goalactive; quality uplift remainsunproved.


## Same-original-input binding repair real comparison

Final research gate890passed299.91s, root/strictresearch types and targetpack passed; actual offline preflight2containers/0requests/2removed, optimizedPython paid denial and fresh independent runner review passed. Paid manifest activated only after gates; original false manifest retained. Runtime/image and research source frozen during execution. Original native process66361 terminalexit0;2serial isolated Docker executions, no apply.

Before:149.786s, parent citation-mismatch; after:42.24s, parent ready. Independent private raw-output review found one retained rule/citation in each arm, identities/op preserved; baseline omitted one of5 nonindex citation properties while improved retained5/5. Pattern/action/scope/permission properties matched original, original9positive/10negative cases retained. Only improved rule message changed. Full rewritten-message semantic support/privacy entity audit remains bounded; exact retention is not semantic gold. No unsupported candidate applied.

After realJev:3requested/0completed,5042ms timeout, propose; model requestedjev-1.13.0 but actual response model unverified.11providerrequests=8main+3Jev. Known maincostestimate$0.006177362. Jevusage records0: unknown cost, not free; accountbilling unverified. Both task containers independently confirmedremoved. One known historical input/one stochastic outputperarm, exported project surfaces only, no heldout/fullworkflow or stablecausal latency claim, no favorable retries/relabel/gatechange. Localbinding output signal is positive; end-to-end Jev quality remains unproved.

Authoritative immutable results @jev-harness-binding-original-real-results.json; controlled independentreview @jev-harness-binding-original-independent-review.json; observation @jev-harness-binding-original-observation.json; frozen paidpreparation @jev-harness-bindings-original-input-preparation.json.

Next hypothesis is bounded deadline sensitivity, not automatic production timeout expansion: prospectively compare unchanged original wire inputs/model/thresholds under5s and15s budgets, alternate arm order and retain every original failure. Include fixed English/Chinese valid and invalid public samples; independently freeze labels and count missing judgments separately from false holds/unsafe accepts. Success requires improved completion without additional unsafe acceptance or valid holds, with latency and unknown billable usage reported. Existing queried samples are known diagnostic evidence, never described as unqueried or heldout. No production adoption or goal completion before real results and independent review.


## Known bilingual deadline diagnostic — no adoption

Given/When/Then @../features/jev-deadline-research.feature; initialRED3failed0.10s, GREEN3passed0.08s. Independent review identified post-send wire verification, RED additional1failed3passed0.12s, finalGREEN4passed0.10s after adding pre-send multiset claim including duplicate hashes. Both offline preflights retained, zeroexternalcalls; final96fixture requests/two arms exactsamewire. SDK0.6.0 installed types/implementation verified: per-attempt timeout with AbortController including full response body; retry0 unchanged. Live official SDK/confidence docs fetched directly after browser read failure. All46 source/dependency hashes frozen, freshreview4passed/no remaining blocker, root/strictresearch types and targetpack pass. Firstfull893passed298.18s predates additionalguardcase; finalfull894passed300.25s, workspace19packedmanifests pass. No production runtime source changes.

Single original paidprocess40305 terminalexit0,96realrequests,24known publicsynthetic English/Chinese samples (12valid/12invalid); never labeled unqueried/heldout. Botharms24complete/0missing/0unsafeaccept/1validhold/23correctcompleted. Same example-zh held for authorityuncertainty; no timeout in either arm. Exactall wire multisets match pairedarm/offlinepreflight. Five-second p50/p95=447/1681ms; fifteen-second525/779ms, stochastic one-run observations not a stable latency gain. All96HTTP200/modeljev-1.13.0/usageverified,672numericjudgments preserved including488noninteger values;71564inputtokens/$0.003005688known tariffestimate, accountbillingunverified. Successrulefalse, no15s adoption, default5s/no retry/permissions/gates unchanged. Independentreview recomputed original labels/wires/usage and interpretation. @jev-deadline-real-results.json, @jev-deadline-independent-review.json, @jev-deadline-adoption-decision.json, @jev-deadline-final-verification.json. Goalactive; no overall Jev improvement proved.

Next actual-input signal: private offline reconstruction from the exact original after native output preserves17entries/two counterwindows/three requests. Wire sizes6594/29978/20684bytes vs known smallcorpus1921–2125bytes; allbelow original64Kwirebound. Independentcandidate/identity/citation checks and full indexes0–16/originalentry equality passed; private rawwire0600, noexternalcalls. MixedNoul/Choice forced answers establish wiring only. Several transient private profiling script errors were repaired and retained, all zeroexternalcalls; these were not production regressions. Profile script/source manifest bound in @jev-deadline-original-transport-preparation.json, paidflagfalse. Historicalwirebodies unretained, so reconstructed currentwire not proof of literal oldwire identity.

Prospective next matrix controls same-host runtime/SDK/candidate/exactwire across direct official SDK vs existing transparent Pythonforwarding proxy, five vs fifteen seconds,12requesthardcap. It cannot isolate Docker VM networking or substitute for fullworkflow quality. New runner still requires behavioral regressiontests, zero-call transport preflight and independent review before paid activation. No automatic deadline enlargement, favorable retry, changed gold or failure relabel. @jev-deadline-original-wire-preparation.json and @jev-deadline-original-wire-independent-review.json.
