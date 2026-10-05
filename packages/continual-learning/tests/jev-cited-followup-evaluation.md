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
