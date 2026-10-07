# pi-e2e

通过一次测试运行的客观证据，判断 Gherkin `.feature` 端到端场景是否达成。

代码裁决你能够精确比对的条款；TypeSafe **Jev** 决策模型仅回答那些需要理解证据语义的条款。最终结论在代码层通过概率门限组合，未达到置信度的结论将转为人工复核，绝不冒充通过。

## 为什么这样做

BDD / 端到端验收测试条款通常分为两种不同性质：

- **明确的事实断言**（例如 "工作区计划为 Pro"）：属于代码比对范畴。调用模型只会徒增成本与延迟，且存在误判风险。
- **业务意图条款**（例如 "账单页面显示的金额仅覆盖当前计费周期的剩余天数"）：需要将条款语义与真实账单数值结合理解。这是判断而非简单的字符串匹配。

本包将第一类留在代码中裁决，仅将第二类交给 Jev。

## 安装

```bash
pnpm add -D @fradser/pi-e2e
```

设置环境变量 `TYPESAFE_API_KEY` 以便 Jev 评测未声明代码检查的条款。本包不支持通过命令行参数传入密钥，防止密钥泄露至上下文。

## 命令行使用

通过 `pnpm exec tsx`、`npx tsx` 或 `bun` 运行（Node.js 原生去类型机制默认跳过 `node_modules`）：

```bash
pnpm exec tsx node_modules/@fradser/pi-e2e/src/cli.ts verify \
  --feature examples/billing.feature \
  --evidence examples/billing-evidence.json \
  --offline --report-html report.html
```

或直接在源码目录运行：

```bash
node src/cli.ts verify \
  --feature examples/billing.feature \
  --evidence examples/billing-evidence.json \
  --offline --report-html report.html
```

参数说明：`--scenario <名称>`、`--clause-gate <0..1>`、`--verdict-gate <0..1>`、`--report-md <路径>`、`--report-html <路径>`、`--json`。

退出码对 CI 稳定友好：`0` 达成，`1` 未达成，`2` 需要复核。

## 在 Pi 中使用

插件注册了一个斜杠命令：

```
/e2e <feature.feature> <evidence.json> [场景名称]
```

或显式带有 `verify` 子命令：

```
/e2e verify <feature.feature> <evidence.json> [场景名称]
```

## 协议

MIT
