# 结合 pi-continual-learning 与 Trajectory.ai 的持续学习架构：从静态冻结到体验复利

## Introduction

本条目综合两个互补的对象，考察智能体（Agent）持续学习架构的设计空间：其一是 Trajectory.ai 提出的生产级持续学习体系——以"轨迹（Trace + Telemetry）"为新系统基元，在模型权重、Harness 与 Prompts 三个表面上联合优化，并以 SDPO++ 算法、C-LoRA 多租户训练引擎与假设驱动部署管道支撑小时级迭代[1]；其二是开源 Pi 包 `pi-continual-learning`，它在单机编码代理上把持续学习限定于 Harness（分层工具调用护栏）与 Prompts（记忆检索、注入与父拥有式整合）两个表面，明确将模型权重排除在外[2]。条目先阐述持续学习范式、核心基元、三表面模型、四大生态愿景与算法及工程实现，继而分析企业治理与行业案例，最后将 Trajectory 概念体系逐项投影到本地包的实现上，给出诚实的完成度对照、差距清单与演进路线图。

贯穿全文的主线是"体验复利"：当用户的每一次编辑、重试、撤销与接管都被观测、解释并经验证地转化为系统能力时，Agent 便从一次性发布的静态产物转变为随使用而进化的活系统。对拥有完整训练基础设施的厂商而言，这条链路延伸到权重更新；对本地单机工具而言，它同样可以在不触碰参数的前提下成立——错误调用被即时阻断并回灌纠正理由，项目经验经检索与整合跨会话保留。两种尺度的差异与衔接，正是本条目试图厘清的内容。


## 持续学习范式：终结“冻结软件”

传统软件以及早期人工智能系统通常以一次发布、长期运行的静态产物为前提：模型完成预训练或离线微调后，参数便被冻结，缺陷要等到下一轮集中式版本更新才可能修正。部署现场因而与研发时的能力假设之间形成“体验鸿沟”：系统每天面对真实用户、复杂任务和不断变化的工作流，却不能把交互中获得的经验带入下一次任务。[1] 生产中的智能体每天约产生 100 万亿 Token，但其中大量包含工作流逻辑、用户修正和失败线索的交互，在一次推理完成后就被丢弃，既没有成为评估样本，也没有成为训练信号。[1]

这种系统常被比作“第一天上班的天才”：它在离线测试中可能具备极高的知识和推理能力，初次面对具体组织的工作方式时却不了解上下文、偏好和例外处理；每次接收纠正后，下一次任务仍近似从零开始。[1] Trajectory.ai 由 Arjun Karanam、Ronak Malde 等人创立，其提出的持续学习路径试图把模型从冻结的发布物重构为能够随使用而演化的“活系统”（Living System），让失败被识别、经验被沉淀，系统能力由连续使用产生复利，而非只依赖低频的大版本升级。[1]

持续学习范式并非只把训练时间提前或缩短，而是重新定义生产交互在系统中的地位。静态 AI 依赖离线人工标注、标准数据集以及粗粒度的“赞/踩”反馈；持续学习则把生产环境中的编辑、重试、撤销和人工接管视为高密度信号，使用户实际如何修正系统成为能力改进的依据。[1] 两种范式可按下列维度区分：

| 维度 | 静态 AI | 持续学习 AI |
| --- | --- | --- |
| 模型生命周期 | 离线训练后冻结，依赖长周期版本迭代 | 持续吸收生产流量，支持更高频的动态更新 |
| 反馈信号来源 | 人工标注、标准数据集和二元“赞/踩” | 编辑、重试、撤销、接受与人工接管等生产行为 |
| 改进作用域 | 主要依赖 Prompt 工程或全局权重重训 | 联合优化模型权重、Harness 与 Prompts |
| 评估机制 | 静态基准，可能与现场任务脱节 | 重演生产流量，并在生产级 Harness 中评估 |

表中差异表明，持续学习的对象不是单一模型参数，而是一个由模型、运行框架与指令层共同构成的系统。对同一失败任务，系统既可以调整权重中的通用模式，也可以改变工具调用、检索上下文或私有数据接口，还可以修正任务意图到具体行为的提示映射。[1] 这种分层改进使“经验复利”具有工程含义：一次用户纠正不再只影响当前回答，而可能在验证后改变后续同类任务的处理方式。[1]

Trajectory.ai 的定位正建立在这一范式转换之上。它将 Agent 生产流量视作持续学习所需的原始材料，并把“活系统”作为区别于冻结软件的产品形态：系统在使用中识别错误、形成领域专长，并通过更贴近现场的评估判断改进是否真实有效。[1] 因此，持续学习的终点不是宣称模型永远自动变好，而是让每次生产体验都能被观测、解释、验证，并在适当的表面上转化为下一次运行可用的能力。[1]

## 系统基元：轨迹（Trajectory = Trace + Telemetry）

每一种技术范式都会围绕能够被记录、传输和组合的系统基元展开。数据库以“行”承载数据、以“查询”组织访问；Web 以页面承载内容、以链接构成导航关系；云计算则常以请求与响应描述一次服务交互。[1] 在 Agent 持续学习范式中，Trajectory.ai 将轨迹（Trajectory）提出为对应的核心基元。它不是单个输出，也不是孤立的日志事件，而是把 Agent 的执行过程与用户对结果的实际反应置于同一可学习单元中。[1]

轨迹的第一部分是 Trace，即 Agent 为完成任务所采取的完整决策树和动作序列。Trace 不仅包括最终答案，还包括子 Agent 的调用关系、工具调用及其参数、不同步骤之间的动作路径和中间思考过程。[1] 这种记录方式回答“系统做了什么”：它允许观察一个结果是由哪条分支、哪次检索或哪次工具操作产生，也使长任务中的局部失败可以被定位，而不必把整次运行压缩成一个成功或失败标签。[1]

轨迹的第二部分是 Telemetry，即用户收到 Agent 输出之后留下的真实交互与修正行为。报告列举了五类关键行为：用户重新发起任务或要求生成的 retries，撤回上一步结果的 undos，直接改写输出的 edits，明确采用结果的 acceptances，以及由人工介入完成任务的 escalations。[1] 这些事件与 Trace 发生关联后，能够说明用户对哪一步不满意、何种输出被保留、哪里需要人工接管，以及一个看似完成的任务是否实际上仍需返工。[1] 因而 Telemetry 不是附加的产品统计，而是对 Trace 的结果语义进行补充：前者描述执行之后发生了什么，后者描述执行本身如何展开。

传统训练流程往往只保留模型的输入、输出或人工标注，重点放在 Trace 的一部分，却忽略了用户在界面上的细粒度纠正。Trajectory.ai 试图把这些被遗弃的遥测转化为高密度的监督与强化学习信号：一次编辑可以作为期望输出的局部证据，一次重试可以提示当前路径未达到要求，一次撤销或人工接管可以标记风险更高的行为，而一次接受则提供正向结果线索。[1] 信号并不要求用户额外填写复杂标签，系统可以从实际工作流中提取行为差异，再将其用于理解失败模式、构造评估任务或驱动后续训练。[1]

把 Trace 与 Telemetry 合并为单一基元，还改变了生产评估的边界。仅看 Trace，某次工具调用可能在语法上成功，但用户随后立即编辑、撤销或接管，说明任务结果并未达到生产标准；相反，某些看似非典型的执行路径若稳定获得接受，便可能代表值得保留的策略。[1] 轨迹因此既是可观测的执行记录，也是可重演、可比较和可改进的数据对象。持续学习系统可据此重建真实任务，在同一个生产级 Harness 中检验候选更新是否减少重试、撤销和接管，同时保持用户接受的行为模式。[1]

从系统设计角度看，Trajectory 这一基元把“模型输出”扩展为“行动—反馈”闭环。Agent 的调用链、工具交互和中间步骤构成可追踪的过程，用户的编辑、重试、撤销、接受及升级构成对过程结果的现场判断；两者共同提供比二元赞/踩更丰富的学习材料。[1] 只有当这类材料被持续保存并与任务、版本和评估关联时，生产流量才不再是一次性消耗的 Token，而能成为可积累的系统经验。[1]

## 三层表面的联合优化

Trajectory.ai 将持续学习的对象从单一模型扩展为三个相互作用的表面（surfaces）：Weights、Harness 与 Prompts。[1] 这一划分回应了 Agent 系统中“智能”分布在不同组件里的事实。模型参数能够表达跨用户、跨会话仍然适用的通用模式，但工具接口、检索路径、私有数据访问和任务意图映射往往具有应用或组织特异性，不能全部通过全局权重解决。[1]

Weights 表面吸收的是跨用户、跨 session 的长期通用模式。经过 post-training，反复出现且具有普遍性的工具调用习惯、推理策略或错误修正，可以进入模型本身，使其在相似任务中不必每次依赖显式提示。[1] 这一表面适合承载能够泛化的能力改进，但其影响范围最大，因此需要生产数据边界、评估门禁和版本验证，以避免将单一组织的偏好误传播到其他用户。[1]

Harness 表面吸收的是 Agent 周围的运行时结构，包括工具调用逻辑、检索上下文、私有数据接口以及向 Agent 提供信息的方式。[1] Harness 决定模型能够调用哪些工具、以什么顺序获得何种上下文，以及工具响应是否足够明确。许多失败并非模型缺少抽象知识，而是工具返回信息稀疏、上下文缺失或接口流程过于僵硬；此时更新 Harness 往往比重训全局模型更直接，也更容易限定在特定应用或组织范围内。[1]

Prompts 表面负责修正任务意图映射和系统引导规范。[1] 同一个用户目标可能因为指令措辞、约束顺序或角色设定不同而被映射为不同动作。将稳定的用户纠正转化为更清晰的系统 Prompt，能够使 Agent 在后续会话中理解任务边界、输出格式和工作偏好；与 Weights 相比，这种更新更易检查和回滚，也可针对单个项目或组织生效。[1]

三层表面不是彼此替代，而是共同参与同一失败闭环。一个 Agent 可能在通用推理上具备能力，却因为检索未带入必要的私有数据而调用了错误工具；也可能已经获取正确上下文，却因 Prompt 未准确表达任务意图而输出不符合组织规范的结果。系统首先通过 Trace 和用户 Telemetry 定位失败发生在哪个层面，再决定将修正写入模型权重、Harness 还是 Prompts。[1]

当失败具有跨任务、跨用户的重复性时，相关模式可通过 post-training 进入 Weights，改善模型的通用判断；当失败由工具逻辑、检索上下文或私有接口造成时，Harness 可以调整可用原语、数据访问路径和响应格式，在运行时阻断同类错误；当失败主要是任务意图、输出规范或组织偏好映射不准时，Prompts 可以补充引导和约束。[1] 三者的协同意味着，同一类问题不必只靠更强的基础模型解决，而能在最接近错误来源的表面上采取修正。[1]

这种联合优化还具有范围控制的意义。全局能力缺陷可以上升到共享权重，组织特定的格式偏好则可以留在组织 Context、Harness 或私有适配器中，避免局部经验污染全局系统。[1] 因而持续学习的核心不是让每次交互都直接改参数，而是将轨迹证据分流到合适的表面，并在生产级评估中检验三层更新是否共同减少失败、提高任务成功率，同时维持可解释和可治理的变化边界。[1]

## Trajectory.ai 的生态改进四大愿景

Trajectory.ai 将持续学习视为 Agent 生态系统的整体改造，而不仅是训练算法的替换。其提出的四大愿景分别涉及观测生产行为的可追溯性、以真实流量为中心的评估、运行框架的优化，以及对模型权重和路由的战略控制。[1] 四者共同构成从数据捕获到能力更新、从实验验证到生产部署的基础条件。

**可追溯性（Traceability）**首先要求记录完整的决策树与工具调用细节，并把 Agent 的行动和用户的后续修正放在同一轨迹中。[1] 这一愿景反对把反馈简化为噪音较大的二元“赞/踩”，转而提取界面上的矫正行为，例如用户直接修改代码、重写文本、重复请求或接管任务。[1] 这些行为比单一满意度标签更接近生产目标：它们显示用户具体改了什么、在哪一步放弃了自动化，以及哪些结果被实际接受。可追溯性由此为失败模式分析、训练样本构造和版本比较提供共同的证据基础。[1]

**生产对齐的评估（Production-Aligned Evals）**要求评估环境与真实生产流量保持一致，覆盖用户实际尝试的边缘任务，而不是只在简化的离线测试套件中取得高分。[1] 任务需要具备可重演性（Rolloutable），使系统能够用历史轨迹复现相同或相近的场景，并在生产级 Harness 中对候选更新打分。[1] 这种方法把评估对象从单次模型答案扩展到完整 Agent 行为，包括工具选择、上下文使用、用户是否需要返工以及运行成本等现场结果。只有当新版本在真实或可重演的工作流中证实改进，持续学习才不会变成未经验证的自动漂移。[1]

**Harness 优化（Harness Optimization）**强调为 Agent 提供灵活而可组合的原语，而不是用硬编码流程限制所有任务。[1] 原语包括工具、私有数据上下文及与之配套的调用接口；Agent 的接口应与用户界面形成一对一映射，使用户在界面上的操作能够准确反映为系统可学习的行为。[1] 工具响应还应具有高信息密度，例如明确确认特定数据库读写细节，而不是只返回模糊的成功标记。信息越具体，模型和评估系统就越容易判断动作后果，用户反馈也越能转化为学习信号。[1]

**开放权重战略与路由（Open-Weight Strategy & Routing）**要求生态系统拥抱开放权重模型，以保持对模型参数的掌控和持续微调能力。[1] 在此基础上，模型路由器可按照任务复杂度、领域需求或运行条件，把请求分发给更匹配的模型层级，而不是让单一模型承担所有工作。[1] 开放权重为持续 post-training 提供可操作的参数入口，路由则使不同能力版本能够在生产中并存和比较；二者结合，也为组织级适配与全局能力改进之间的分层治理留下空间。[1]

四大愿景相互依赖：没有 Traceability，生产修正无法成为可靠数据；没有 Production-Aligned Evals，候选更新无法在真实工作流中得到判断；没有合适的 Harness，模型也可能因工具和上下文缺陷而重复犯错；没有开放权重与路由，已验证的改进则缺乏持续部署和范围控制的基础。[1] Trajectory.ai 的目标是一条可观测、可重演、可调整、可验证的改进链路：从用户行为中提取信号，在生产级环境中重放与打分，再将结果作用于模型、Harness 和 Prompts，并通过路由决定何时、对谁生效。[1]

## 算法层：SDPO 与 SDPO++

持续学习若直接面向生产流量，会首先遭遇两类约束。其一是单次采样约束（Single Rollouts）：一个真实请求通常只产生一条可用轨迹，无法像离线强化学习那样反复采样同一任务。其二是离线陈旧性（Off-Policy Staleness）：轨迹异步进入训练队列，训练器实际处理它时，策略权重可能已经更新了若干步骤，数据分布因而与当前策略不再一致。[1] 这两点使传统组相对优势方法难以直接迁移。以 GRPO 为例，它需要对同一任务采样多条轨迹，再用组内结果计算相对优势；在生产请求规模和延迟约束下，这种多轨迹采样被认为不可行。[1]

SDPO（Self-Distillation Policy Optimization）采用提示教师机制，将一条生产轨迹转化为可学习的教师信号。给定输入提示 x，学生在权重 θ 下按 x 采样并生成轨迹 y；教师并非另一个模型，而是在相同权重 θ 下接收增强提示 x+h 的同一模型。这里的 h 是事后获得的特权信息，来源包括用户随后进行的直接修改或纠正、成功的同类任务采样，以及标准答案或环境返回的错误日志。[1] 因而，失败结果并不必然意味着没有监督：它可以与后续修正、成功示例或错误说明组合，构成教师条件分布。

SDPO 的优化目标是学生与提示教师之间的逐 Token 逆向 KL。逆向 KL 具有模式寻求（mode-seeking）性质，倾向于把学生推向教师概率最高的 Token，而不是将概率平均摊给所有可能输出。[1] 这一目标还保留了零奖励情形下的明确梯度：即使一条轨迹得到的奖励为零，教师提示仍可提供逐 Token 的方向，因此失败轨迹也能参与学习。SDPO 的要点不是凭空制造奖励，而是利用单条轨迹及其随后可获得的上下文，把事后信息蒸馏为局部策略改进目标。

SDPO++ 主要处理训练队列中的离线陈旧性。若轨迹生成时的策略与训练时的策略相差 N 步，直接使用重要性采样（Importance Sampling，IS）可能使罕见 Token 的 IS ratio 膨胀至约 50 倍甚至 100 倍，并诱发梯度爆炸。[1] 为此，SDPO++ 使用双重裁剪稳定器。第一层是 PPO Clipping：将 IS ratio 限制在由 ε 指定的区间内，抑制陈旧样本造成的权重比率异常。第二层是 3× Advantage Clipping：把单个 Token 对梯度的优势贡献限制在其运行均值三倍以内，以削弱尾部样本并消除不同随机种子之间的评估方差。[1] 两层裁剪针对不同放大源，且不需要额外 Reference Model 的评估开销；前者约束策略比率，后者约束单 Token 优势贡献。

在包含长达数小时代理轨迹的 APEX-Agents 基准上，基于 GPT-OSS-120B 的 SDPO++ 达到 25% 的任务成功率，相对 Zero-shot 基线提高 5 倍。[1] 报告同时指出，在数据陈旧度较高时，该方法仍保持收敛，并带来 2 倍 wall-clock 训练加速。[1] 这些结果将 SDPO 的单轨迹学习与 SDPO++ 的离线稳定机制连接起来：前者降低生产监督的采样要求，后者限制异步更新中的比率和梯度风险。

## 工程架构：C-LoRA 与分钟级部署管道

为支撑小时级更新和多租户隔离，C-LoRA（Concurrent Multi-LoRA）将持续训练从离线串行作业改造成常驻、可热更新的服务。该架构由 UC Berkeley Sky Lab 与 Anyscale 联合推进，基于 SkyRL 开源实现。[1] 其核心思路是让不同租户的适配器共享基座模型的推理与训练基础设施，同时避免为每个租户单独启动完整流程。

在推理层，C-LoRA 使用 vLLM 热加载 LoRA 适配器，并通过 SGMV（Segmented Matrix-Vector）解码核，将来自不同租户、不同适配器的 Decode Token 融合到同一个 GPU Batch 中执行。[1] 这样，多租户请求不必拆分为相互隔离的解码步骤，常驻服务也能在适配器切换时保持 GPU 批处理效率。训练层则由 AdapterStore 管理适配器状态：每个租户的 FP32 主权重、优化器矩和梯度缓冲区存放在 pinned CPU memory 中，训练时只把当前 Batch 所需状态 Swap 进 GPU，完成前向与反向传播后再换回 CPU。[1] 该 CPU-GPU Batch Swap 使训练状态不必全部常驻显存，显存开销降低一个数量级。

C-LoRA 还提供 In-place Weight Sync。梯度更新完成后，新 LoRA 权重可直接原位同步到推理引擎，不需重启进程，也不打断其他租户正在进行的 Decode 流程。[1] 这使训练、加载和在线推理成为连续管道，而不是依赖停机窗口的离散发布步骤。在 H200 单节点、Qwen3-4B-Instruct 模型的八路并行实验中，C-LoRA 达到 2.81 倍端到端吞吐，奖励曲线与串行基线对齐。[1] 后一结果表明，并行化并未以明显改变优化轨迹为代价换取吞吐增长。

训练产物进入生产前，还需要通过与 Baseten 合作构建的分钟级部署管道。第一道门是 Architecture-Aware Merge：合并 LoRA 与基座模型时，校验 Fused QKV 投影、MXFP4 块缩放以及 MoE Expert Broadcasting 等架构细节，避免适配器合并过程隐式损坏模型。[1] 第二道门是 Truss 打包，将依赖与推理服务配置封装为可部署产物。[1]

第三道门是 Runtime Validation，对量化层、RoPE 扩展和推测解码所使用的草稿模型匹配关系进行检查，确认合并后的权重与目标运行时一致。[1] 第四道门是 Hypothesis-Driven A/B Routing：新模型不被直接视为确定性升级，而作为待验证假设与旧版本并行接收分流流量；两组遥测彼此隔离，只有真实生产数据证明实验版本胜出后，才将其全量晋升。[1] 四道门共同把持续训练、运行时兼容性和生产效果验证串成发布闭环。

## 产品控制平面与企业级治理

### Instrument–Understand–Steer–Learn：从可见性到自动化

Trajectory.ai 将持续学习组织为 Instrument、Understand、Steer、Learn 四个阶段。Instrument 通过轻量 SDK 接入应用，在不改变既有工作流的前提下捕获 Agent 的 Trace 与 Telemetry，包括用户编辑、重试等交互信号。Understand 对真实使用模式进行自动聚类，定位系统反复出现的 Failure Modes，并说明失效发生的环节。Steer 不采用以人工标注为中心的界面，而是提供创意工具界面，让开发团队直接设定行为优化方向与评估维度。Learn 才执行 post-training，并同步更新模型、Prompt 与 Harness；候选更新须先通过 Eval 门禁，随后才能部署到生产环境。[1]

四阶段的顺序构成一条责任链：先使生产行为可见，再由人决定干预方向，最后才把经过验证的修正自动化。换言之，“学习”不是对线上数据的无条件吸收，而是建立在观测、解释和人为设定目标之上的受控流程。该安排也将失败模式、优化假设和部署结果置于同一条可追溯链路中，避免把未经解释的行为变化直接当作能力提升。[1]

### 企业治理承诺与分层学习拓扑

Trajectory.ai 的治理承诺首先体现为数据控制权。“You Decide What Trains”要求客户决定哪些数据可以进入训练边界，并支持全流程审计及 SOC 2 标准；“Nothing Deploys Without You”则要求每次模型更新通过客户自定义 Eval 套件和人工审批后，方可进入生产。[1] 对敏感数据，系统提出提取概率分布并生成高保真合成数据的做法，以降低直接使用原始企业数据所带来的跨客户泄露风险。[1]

这种治理还通过分层学习拓扑区分能力缺陷与组织偏好。能够跨组织复现的通用工具调用失败、语法或逻辑错误，可上升到全局模型，用于改善基底能力；“永不使用某个子 Agent”、输出格式或审批习惯等组织特定偏好，则隔离在该组织的 Context、Harness 或私有 LoRA 中，不应外溢为全局行为。[1] 因而全局泛化与局部定制并非同一训练作用域，数据是否可共享、更新是否可晋升，都需要在控制平面中分别处理。

### 行业案例与市场切入策略

Trajectory.ai 公布的案例显示，其优先进入的是错误代价高、知识长尾且组织偏好差异显著的专业工作流。GTM 场景中的 Clay 需要系统吸收客户对市场推介任务的微调与修正，使 Agent 能够在犯错过程中自愈和进化；企业客服平台 Decagon 面向多个企业客户，重点验证跨企业部署中的 Steerability 诊断与可控进化；法律 Agent Harvey 则利用真实实务轨迹处理判例和裁量等长尾知识，并在 24 小时内完成 NVIDIA Nemotron 3 Ultra 等模型的 post-training。[1]

这些案例共同指向一种市场切入路径：先服务专业工作流中可观察、可反馈且失败损失明确的任务，再将经过客户授权和评估的改进沉淀为相应层级的能力，而不是先追求无边界的通用自动训练。对本地 Agent 而言，pi-continual-learning 以分层配置、工具调用纠正和 fail-closed 验证门禁复刻了其中的最小治理闭环：策略由内置、用户和项目层级解析，命中时阻断或要求确认；整合与验证只有在契约检查通过后才能被视为完成。[2][17][18] 这为后续讨论单机环境中的记忆、Harness 与可回滚实践提供了治理语义上的衔接。

## 本地实践：pi-continual-learning 的无权重持续学习

### 包定位与边界

`pi-continual-learning` 将持续学习限定为运行时的两个表面：Harness 与 Prompts；模型权重明确不在范围内。[2][6] Harness 是声明式工具调用门禁，Prompts 是跨会话的项目记忆、检索、注入、自动记忆指导与手动整合。[2] 包由 `@fradser/pi-memory` 改名而来，改名同时标志着从单一 prompt surface 扩展到 harness surface；它没有独立的 skill surface。[3] 通过 `pi install npm:pi-continual-learning` 安装，主要命令是 `/memory`（记忆模型、指令、设置与整合菜单）、`/consolidate`（立即整合）、`/harness`（查看活动策略、来源及配置路径）；`/consolidate` 在验证通过的记忆整合后，还会对同一不可变会话快照运行第二阶段只读规划，把护栏证据转化为仅写入项目个人层 `.pi/harness.local.json` 的有界策略更新。[2][11]

### Harness 表面：分层策略与即时纠偏

Guardrails 的配置从内到外组成四层：包内置默认策略、Pi agent 目录的 `harness.json` 与可选 `harness.local.json`、项目 `.pi/harness.json` 与可选 `.local` 文件；配置目录遵循 `PI_CODING_AGENT_DIR`，解析时项目层和 local 层位于更内侧。[2][9] 同名策略以后出现的内层定义覆盖外层定义，任意层的 `disabled` 名称都会移除该策略，因此项目可以收窄、替换或关闭默认规则，而无需改包代码。[10]

每次 `tool_call` 都由引擎评估。`tools` 先限制工具名称，`require` 是 AND 门：路径范围命中与违规模式命中必须同时成立，适合把规则限定到某类调用。[8][10] `paths` 是点路径数组；引擎沿对象字段取值并对数组扇出，所以 `edits.newText` 能检查每个替换片段。若省略路径则扫描序列化参数；`pattern` 或 `patterns` 用正则测试，多个模式任一命中即可。[8][10] 动作默认为 `block`，直接拒绝调用；`confirm` 在有 UI 时让用户选择一次允许或阻断，无 UI 时则直接阻断。[7][10] 返回值中的 `reason` 带策略名并说明正确程序，作为模型下一轮可见的纠正性反馈；这不是参数更新，而是“失败尝试—解释原因—重写工具调用”的无权重学习回路。[7][10]

内置规则覆盖已知徒劳自动化，例如交互式 npm、pnpm、yarn 或 bun 认证命令，以及通过文件或聊天转运 OTP，要求用户在自己的终端完成认证。[2][10] README 还给出 UI 固定像素宽度的策略：用 `require` 先筛选 UI 文件，再以 `paths` 检查写入文本，命中三位数像素宽度就阻断，并提示采用设计令牌或响应式单位。[2][10]

`skillPrompts` 是 Harness 的另一种引导机制：按 skill 名在用户、用户 local、项目、项目 local 四层覆盖，内层定义胜出；`disabled` 只作用于工具策略，不会关闭 skill prompt。[2][9][10] 当 Pi 完整展开指定 skill 后，指导可追加到 system prompt，或作为隐藏的 user context 注入；后者因为 `before_agent_start` 无法改写已展开的用户消息而采用消息注入。匹配针对完整 skill XML，而非原始 `/skill:` 字符串，并以幂等检查避免同一指导重复追加。[2][7]

### Prompts 表面：检索与父拥有式整合

每轮 `before_agent_start`，扩展从公共 `.memory` 与 harness memory 目录安全读取、去重并限制文件数、单文件字符数和总字符数，然后将现有记忆作为“不可信参考数据”注入 system prompt。[11][13] 自动记忆开启时，额外注入指导，要求模型遇到决策、偏好、lesson 或 gotcha 立即记录，先检索旧文件，按“一项决策一文件”维护 `Why`、`How to apply` 与关联链接；这一开关只控制自动写入指导，已有记忆仍会加载。[11]

整合不是 child 自主写盘，而是 parent-owned 事务。父进程先按项目规范获取锁，建立 canonical scope，捕获不可变会话快照或显式 `no-context` 模式，再启动只读、`--no-extensions`、仅具备 `read/grep/find/ls` 工具的 worker。[3][15][16] 父进程把选定 memory 文件范围、运行标识、快照摘要和路径写入任务；worker 必须返回一个有界结构化计划，`inventory`、`clusters`、`staleness`、`grounding`、`report` 五部分覆盖同一选定范围，不能修改记忆目录。[15][16]

应用前先做身份、范围、快照哈希、隐私与结构验证，写入 pre-receipt 后才执行计划；执行期间检测取消、源文件漂移并保留事务快照，失败时恢复文件。应用后重建索引、按安全分类同步到公共 `.memory`，私有文件留在 harness 目录，再写 post-receipt，并以 plan、receipt、privacy 门禁复核；任一校验失败都不能报告整合完成。[3][15][16][18] 这种设计把可回滚、可审计和隐私分界置于提示层持续改进之前：它积累的是可检索的项目指导与可验证的工具规则，而不是模型参数。

## 概念映射：Trajectory 体系在单机 Agent 上的投影

把 Trajectory 的术语直接套在本地包上会夸大实现程度。更准确的做法是区分“已有运行时原语”和“尚未形成的生产系统”。

| Trajectory 概念 | pi-continual-learning 对应物 | 完成度 |
|---|---|---|
| Trace | `tool_call` 钩子看到的工具名与参数；父进程捕获的会话 context/branch 快照 | 局部雏形 |
| Telemetry | 尚无统一事件模型；接受、拒绝、编辑、undo、retry、escalation 未系统捕获和关联 | 缺失 |
| weights | 包及入口明确将 model weights 排除在外 | 缺失（明确边界） |
| Harness | 分层 JSON guardrails、`require` 门、`paths`/正则匹配、block/confirm 与纠正 reason；skill prompt 覆盖 | 局部落地 |
| Prompts | memory retrieval、`before_agent_start` 注入、auto-memory guidance、手动 consolidation | 局部闭环 |
| Rolloutable Evals | `features/*.feature` 中的 BDD 契约及 `validate-consolidate` 检查 | 契约雏形 |
| 假设驱动门禁 | 计划身份、范围和哈希绑定，pre/post receipt，privacy 验证，失败关闭 | 验证雏形 |

Trace 的对应物首先是 `tool_call`：扩展在每次工具调用时按策略评估参数，命中规则便阻断或要求确认。[7][10] consolidation 则由父进程从 session manager 构建 context 或复制 branch，生成不可变快照并交给只读 worker。[15] 这两处能保存“某次尝试调用了什么”以及“某次整合看到什么上下文”，但都不是完整轨迹仓库：源码没有以统一事件格式持久化决策树、子 Agent 链、中间思考、工具结果及其因果关系。[11][15] 因此不应把快照称为 Trajectory 的完整 Trace。

Trajectory 所强调的 Telemetry 在本包中更为缺席。现有 Harness 记录阻断决定与 reason，memory 侧记录整合计划和 receipts，却没有一个 SDK 化 schema 将 session、tool、用户接受或拒绝、直接编辑、撤销、重试、升级人工和最终结果以关联 ID 串起来。[7][11][15] 这意味着“reason 回灌模型”是即时纠偏，而不是从生产反馈自动学习新策略的遥测闭环。

三表面的完成度也应如实表述。weights 没有训练器、权重同步或模型路由，且 README 将其明确排除。[2][6] Harness 已有可执行门禁，但策略仍来自内置或人工配置，不会根据 Telemetry 自动生成规则；Prompts 能检索和注入项目记忆，auto-memory 提供即时记录指导，consolidation 则由用户通过命令触发。[2][11] 契约还明确，context fill 或 agent settle 不能自行启动整合，因而它是受控的手动闭环，而非自动持续训练。[16][19]

`features/guardrails.feature` 与 `features/validate-consolidate.feature` 可以被看作 Rolloutable Evals 的雏形：前者规定分层优先级、门禁、纠正阻断和无 UI 行为，后者规定覆盖、grounding、privacy、身份、收据及 fail-closed 结果。[17][18] 但它们测试的是包的契约和 artifact 状态，不是生产 Trace 回放、Harness 得分、流量分组或改动后的任务成功率。相同地，validate-consolidate 加 receipts 提供了“假设先门禁、验证后应用”的安全原语，却不等于 Trajectory 的 A/B 路由或自动晋升。诚实的结论是：本地包把 Trajectory 的 Harness/Prompts 控制语义投影到单机 Agent，但尚未成为 Trace、Telemetry、权重和生产评估组成的等价系统。

## 差距分析与发展路线图

将 `pi-continual-learning` 置于 Trajectory 的生产级持续学习框架中，最重要的不是补写“自动学习”叙事，而是明确缺口及其先后关系。当前包已经提供工具调用门禁、持久记忆、父拥有式整合、结构化计划和验证收据；但这些原语尚未组成一条能从生产行为自动发现问题、重演改动并衡量收益的流水线。[2][3][15]

### 缺失项

第一项是统一 Telemetry schema 与 SDK 化捕获。系统需要至少为事件、session、tool、用户修正和任务结果建立稳定字段，并以关联 ID 串起调用、输出、接受或拒绝、编辑、undo、retry、escalation 与最终结果；现有源码没有这样的通用事件模型。[1][7][11] 没有这一层，guardrail 的阻断 reason 只是当下的纠正提示，不能回答某类错误在生产中发生了多少次，也不能证明一条新规则减少了多少失败。

第二项是 Rolloutable Evals 的生产化。`features/*.feature` 已为策略与整合验证提供 BDD 契约，validator 也能检查计划范围、grounding、privacy、身份和 receipts；但它们还不是把真实轨迹固化为可回放 fixture、并在生产 Harness 中打分的评估集。[17][18][19] 下一步应将脱敏的真实轨迹及其用户修正保存为可重复样本，使用同一工具门禁和 prompt 注入路径回放，比较任务完成、纠正次数、人工接管及副作用，再决定是否应用配置变化。

第三项是失败模式自动聚类。当前 consolidation worker 对选定记忆生成 `clusters`、`staleness` 与 `grounding` 等计划工件，但它只服务一次父拥有式记忆整合，并不从统一 Telemetry 中持续发现失败模式。[15][16] 只有当遥测和可回放评估先稳定下来，聚类才有可靠输入；否则自动化只是把偶然的单会话现象写成永久规则。第四项是长期的权重表面：包明确将 model weights 排除在外，没有训练器、权重更新或路由，因此跨用户泛化能力仍不属于本地实现。[2][6]

### 演进顺序

较稳妥的顺序是“先遥测，再评估，后自动化，最后才谈权重学习”。第一阶段建立事件 schema、脱敏策略、session 与结果关联，以及接受、拒绝、编辑、撤销和重试等修正信号的可靠采集。第二阶段将真实事件转化为可回放 fixture，接入现有 Harness 与 Prompts，并让 BDD 契约之外的生产评估衡量任务结果和回归风险。第三阶段才引入失败模式聚类、候选 guardrail/prompt 修正和受门禁的自动提案；每次变更仍应绑定范围、哈希、计划和 pre/post receipt，沿用 validator 的 fail-closed 语义。[15][18] 只有这些环节能持续证明收益，才有理由讨论权重训练、适配器或模型路由，并将其置于额外的隐私、隔离与发布治理之下。[1]

### 能力边界与收束

无权重路线的复利发生在 Harness 与 Prompts 行为层：错误调用可被即时阻断，正确程序可由 reason 回灌，项目经验可经检索与整合跨 session 保留。[2][7][11] 但它不能宣称 SGMV 式解码吞吐收益、C-LoRA 式热更新能力，也不能宣称 SDPO 式统计优势；这些结论要求权重训练、轨迹遥测与生产级评估数据，而不是 JSON 策略或 memory 注入本身。[1]

因此，`pi-continual-learning` 更适合作为演进起点：以单机、可审计、可回滚的控制原语证明“持续改进不必先改权重”，再逐层补齐遥测、评估与自动化。最终路线不是把一个包包装成完整的 Trajectory，而是从单机包走向生产级持续学习系统：先让每一次体验留下可关联证据，再让修正能够重演和度量，继而安全地自动提出行为层改进，最后才在确有数据和治理基础时考虑权重学习。

## Conclusion

Trajectory.ai 与 `pi-continual-learning` 代表同一范式在两个工程尺度上的实现。前者给出了完整闭环的参考架构：以 Trace + Telemetry 为基元统一捕获执行与修正，以 SDPO++ 在单轨迹与离线陈旧约束下提取学习信号，以 C-LoRA 实现多租户热更新训练，再以分钟级四道门与假设驱动路由把每次权重变更当作待验证假设；治理层面则用四阶段控制平面与分层学习拓扑保证进化可审计、可由客户决定[1]。后者证明该范式的最小内核可以在不修改任何模型参数的情况下落地：声明式护栏构成无权重的 Harness 学习回路，持久记忆与父拥有式整合构成可验证的 Prompts 演进，BDD 契约与 fail-closed 校验充当评估门禁与发布闸门的雏形[2][3][17][18]。

两者的差距同样清晰：本地包尚无统一遥测 schema、可重演的生产评估与失败模式自动聚类，因而不能宣称等价于 Trajectory 的完整系统[1][7][11]。但差距本身指出了路径——先遥测、再评估、后自动化、最后才谈权重学习。若软件交付正从"发布固定功能"转向"交付具备自我进化能力的智能引擎"，那么无论规模大小，起点都是同一个：让每一次真实使用留下可关联、可重演、可度量的证据。

## 来源与方法说明

本条目为 STORM 流水线产物（研究—大纲—写作—润饰）。撰写会话中直接网络检索出口不可用，语料为本地文档池：用户提供的 Trajectory.ai 综合研究报告（其内含 10 个网络来源 URL，见报告末尾 Works cited）与 `pi-continual-learning` 包源码及 BDD 契约文件。所有引注 [n] 均指向下列本地文档；引用 [1] 处的事实性内容均可在该报告所列原始来源中追溯。

## References

1. Trajectory.ai 核心产品理念与持续学习架构设计深度研究报告（用户提供的综合报告） — file:///var/folders/vn/whfnt01d4b19zg44txbtznbc0000gn/T/tmp.cWGnPPM6hL/storm-pi-continual-learning-trajectory-ai/docs/user-report.md (accessed 2026-08-26)（内含 Trajectory.ai manifesto、Scaling SDPO、Multi-LoRA Training、Baseten、Newsfilter 访谈、Zenodo 论文、SkyRL Releases 等 10 个网络来源 URL）
2. pi-continual-learning README — file:///Users/FradSer/Developer/FradSer/pi-packages/packages/pi-continual-learning/README.md (accessed 2026-08-26)
3. pi-continual-learning AGENTS.md（仓库指南） — file:///Users/FradSer/Developer/FradSer/pi-packages/packages/pi-continual-learning/AGENTS.md (accessed 2026-08-26)
6. pi-continual-learning index.ts（扩展入口） — file:///Users/FradSer/Developer/FradSer/pi-packages/packages/pi-continual-learning/index.ts (accessed 2026-08-26)
7. extensions/guardrails.ts（工具调用护栏扩展） — file:///Users/FradSer/Developer/FradSer/pi-packages/packages/pi-continual-learning/extensions/guardrails.ts (accessed 2026-08-26)
8. extensions/guardrail-types.ts（策略类型定义） — file:///Users/FradSer/Developer/FradSer/pi-packages/packages/pi-continual-learning/extensions/guardrail-types.ts (accessed 2026-08-26)
9. extensions/guardrail-config.ts（分层配置解析） — file:///Users/FradSer/Developer/FradSer/pi-packages/packages/pi-continual-learning/extensions/guardrail-config.ts (accessed 2026-08-26)
10. extensions/guardrail-engine.ts（策略求值引擎） — file:///Users/FradSer/Developer/FradSer/pi-packages/packages/pi-continual-learning/extensions/guardrail-engine.ts (accessed 2026-08-26)
11. extensions/inject-memory.ts（内存注入、/memory 与 /consolidate 命令） — file:///Users/FradSer/Developer/FradSer/pi-packages/packages/pi-continual-learning/extensions/inject-memory.ts (accessed 2026-08-26)
13. extensions/memory-files.ts（安全内存文件加载） — file:///Users/FradSer/Developer/FradSer/pi-packages/packages/pi-continual-learning/extensions/memory-files.ts (accessed 2026-08-26)
15. extensions/consolidation-run.ts（父拥有式整合协议） — file:///Users/FradSer/Developer/FradSer/pi-packages/packages/pi-continual-learning/extensions/consolidation-run.ts (accessed 2026-08-26)
16. procedures/consolidate.md（只读子代理整合流程） — file:///Users/FradSer/Developer/FradSer/pi-packages/packages/pi-continual-learning/procedures/consolidate.md (accessed 2026-08-26)
17. features/guardrails.feature（护栏 BDD 契约） — file:///Users/FradSer/Developer/FradSer/pi-packages/packages/pi-continual-learning/features/guardrails.feature (accessed 2026-08-26)
18. features/validate-consolidate.feature（整合校验 BDD 契约） — file:///Users/FradSer/Developer/FradSer/pi-packages/packages/pi-continual-learning/features/validate-consolidate.feature (accessed 2026-08-26)
19. features/ 目录（BDD 契约集） — file:///Users/FradSer/Developer/FradSer/pi-packages/packages/pi-continual-learning/features/ (accessed 2026-08-26)
