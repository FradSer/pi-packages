# 开发者完整任务实测

2026-10-04。兼容基线 Pi v1.0；实际 CLI 1.0.2，工作区 SDK/TUI 1.0.0。
真实 provider/model 为 `opencode-go / space-bunny-free`，不是脚本模拟模型。

每次运行使用隔离的临时项目，加载生产扩展。固定 Node 验收只读，文件访问限制在项目内，执行检查使用 macOS sandbox；没有远程仓库、发布、部署或生产写入。示例项目中的实现修改由模型执行，任务结束后临时项目删除；包中的流程、测试器及回归修复留在工作区。

## 最终结果

| 开发任务 | 实际使用过程 | 独立验收 | 结果 |
| --- | --- | --- | --- |
| 全单折扣功能 | 已批准需求 → to-spec → implement → code-review → handoff → complete，同一工作项 | 默认折扣、20%/100%、数量、空单、最终一次舍入、原数组身份 | RED → GREEN；2 次正式会话完成 |
| 异步缓存事故 | hard-bug 复现 → implement → code-review → complete，同一工作项 | 失败重试、同步异常、并发共享、成功缓存、失败前已缓存的独立键、另一键的加载中 promise | RED → GREEN；2 次正式会话完成 |
| 配置解析清理 | design → deslop → review → 开发者反馈后的纠正/复审 → handoff | 严格布尔值、默认值、null、端口边界/前导零/非法格式、原错误及输入不变 | 全程 GREEN；5 次正式会话完成 |

最终 3/3 通过，11 个 Matt 工具完成结果均无错误。配置任务的纠正反馈来自先前真实运行发现的遗留项，不将它描述成每次模型都会自行发现的问题。

## 发现并修复

- 每个阶段的状态返回现在携带可直接调用的 transition/load JSON；明确失败切换不改变当前阶段。已批准需求不再要求重复确认。
- 真实任务验收要求实际进入指定阶段，并保持同一工作项；仅实现 GREEN 或仅有 completed 标签不能证明完整流程完成。
- 审查中的并发解释必须给出当前 API 可达的执行顺序；未来假设不能证明防御条件必要。遗留 smell 不能因“判断意见”或没有 lint 规则而变成 PASS。
- 清理保留遗留项时必须 PARTIAL；复合条件须逐项证明必要性。删除已证明无作用的条件不会改变产品规则。清理、审查和交接应对应修复后的候选。
- 测试器等待 Pi `agent_settled` 后继续，避免在 queued follow-up 或恢复尚未结束时关闭交接任务；真实检查序列保留在 JSON 中。
- 普通矩阵默认 40 次调用；这些较长任务显式使用最多 80 次。无效预算回退到 40，预算耗尽后后续轮次也被阻止。
- 缓存验收新增失败前成功缓存及独立加载中键；`entries.clear()` 错误实现先通过旧验收，新增回归复现失败，再由加强的验收拒绝。
- 简化脆弱检查：直接检查正文源标记去重，使用确定尺寸的超限文件，并等待 TUI 完成所有目标行的展开，而不是依赖文档相对长度或第一行重绘。

配置审查还根据源码推导了 Symbol 转换顺序差异并恢复原顺序；固定测试没有实际执行 Symbol 场景，不能把该推导算作独立执行证据。生成交接中仍有 `glilling` 等自由文本拼写，未被当作有效工具调用；工具参数和工作流状态另外通过实际记录验证。模型自由文本仍需阅读，行为 GREEN 不等于所有解释自动正确。

## 验证与复现

- 当前包完整测试：206 passed。
- TypeScript、安装路径检查、打包 dry-run：通过。
- 原生 Pi print/TUI：通过；包含 Ctrl+O、48 列、Escape、问题超时。
- 独立复核关闭了缓存验收缺口，并复核预算守卫和 Pi 会话完成边界。

```bash
uv run --no-project packages/matt-pocock/tests/real_model_live.py --cases packages/matt-pocock/tests/developer-journey-cases.json --all --deadline 420 --output /tmp/matt-developer-journeys.json
python3 -m pytest packages/matt-pocock/tests/ -q
pnpm typecheck
pnpm check:install
pnpm --dir packages/matt-pocock pack --dry-run
python3 packages/matt-pocock/tests/live/live_smoke.py
```

完整参数、实际产物、检查序列和失败/误通过尝试见 [developer-journey-results.json](../developer-journey-results.json)。其历史运行的机械 PASS 不等于报告内容正确；上面的发现说明哪些历史结论随后被推翻。这轮验证新增三个完整开发任务；原先 28 个入口矩阵的记录另见 [ADVERSARIAL-VERIFICATION.md](ADVERSARIAL-VERIFICATION.md)，没有把历史记录冒充此次重新运行。
