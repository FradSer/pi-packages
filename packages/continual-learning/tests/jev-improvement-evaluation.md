# Jev improvement acceptance / Jev 改善验收

Date: 2026-10-05. User-authorized real requests, SDK 0.6.0, returned model `jev-1.13.0`. All inputs are fixed public synthetic evidence. No real private Memory or credential is archived. Native generation uses `cli-proxy/bailian/qwen3.8-flash`; no mock provider or injected plan. These are local native Pi trials, not a new Docker/open-source-project study.

## What changed / 改动

The earlier compound Noul questions held valid candidates. The revised judge splits Memory grounding into explicit grounded/speculative/transient/unsupported/unclear choices. It combines compatible Memory relation classes and general Harness same/narrower classes. Parent code proves only an absolute-end anchored literal matcher; Jev separately checks lasting authority and faithful message wording. Plain `$`, whitespace classes, conditions, temporary restrictions and extra message obligations do not qualify for literal proof. Thresholds were not lowered.

A semantic hold can use the existing single read-only Harness repair slot under apply policy; structural and semantic repair share the same maximum of two generation calls. Repaired output repeats structure, frozen quotes and semantic validation. Unavailability does not trigger repair, and empty/failed/uncertain repair retains a proposal. Every asynchronous judgment and queued application checks frozen snapshot integrity. Jev never gains file permissions or overrides existing Harness. The generation prompt now includes valid JSON with CR/NBSP negative cases and a message limited to quoted authorization.

此前的复合问题会误拦有效候选；现在把事实依据、权限、消息表述和泛化范围拆开，兼容的类别概率合并判断。修正额度保持一次，原文与父级权限检查继续执行，不通过的候选仍保留为提案。

## Real candidate judgments / 真实候选判断

Baseline here means code-valid candidates with no semantic gate, **not the legacy LLM selector or actual learning workflow**. Unit tests establish control boundaries; offline evaluation establishes deterministic counts. Only the following live artifacts establish real inference outcomes.

| Fixed corpus | Risky accepts baseline → Jev | Supported holds baseline → Jev | Requests | Median request | Estimated Jev fee |
| --- | --- | --- | --- | --- | --- |
| Original 18 bilingual samples | 12 → 0 | 0 → 2 (6 supported) | 36 | 519 ms | $0.000953862 |
| Literal authority 24 bilingual samples | 12 → 0 | 0 → 0 (12 supported) | 48 | 518 ms | $0.001279740 |
| Fresh 16 bilingual acceptance samples | 8 → 0 | 0 → 0 (8 supported) | 32 | 517.5 ms | $0.000826098 |

The fresh corpus was frozen before its first live inference and uses distinct commands, phrasings and Memory facts. `--require-improvement` passes only with complete real inference, fewer risky accepts and no added supported holds. The fresh run passed. This is a bounded candidate-quality improvement, not a universal accuracy claim. The authority corpus was used during design, so it is not independent confirmation. The original corpus still has one general git-push Harness hold per language; no label was changed or sample removed. Uncertain selections use the legacy fallback, and these candidate results do not prove routing improvement.

独立的 16 条样本通过了预设门槛；旧样本仍有两条 Harness 误拦。没有把未知响应算作负例、删除失败样本，或用模拟数据代替真实效果。

Artifacts: `jev-improvement-fresh-results.json`, `jev-improvement-authority-results.json`, `jev-improvement-original-results.json`. Input-token estimates use published pricing, not account invoices; original and authority input totals are 22,711 and 30,470, fresh 19,669. Failed earlier calls without usage have unknown charges. These totals do not include every exploratory diagnostic or native worker call.

## Native Pi effects / 真实插件效果

`live_jev_workflow.py --require-effects` requires all ten material-effect checks, including exact owned native read/result matching, forbidden/allowed native tools and repeated byte stability. The current automatic run passed all ten: first pass applied Memory and Harness, second pass no-op, a fresh session read the saved fact, blocked the prohibited command and ran the allowed command. Duration 119.556 seconds for source, two learning passes and fresh probe. Artifact: `jev-improvement-auto-workflow.json`.

Before the repair, the prior automatic trial persisted Memory but held Harness (`jev-workflow-final-auto.json`). Failed intermediate real runs remain in `jev-improvement-failed-auto-workflow.json` and `jev-improvement-failed-manual-workflow.json`: structural generation failures or first-pass semantic holds prevented effects/repeat stability. They are not counted as successes. The current automatic repeat used a legacy selector after a Jev invalid-response; fallback preserved the correct no-op. No file was manually installed to make effect probes pass.

The automatic two-pass receipts report $0.003695576 worker cost and $0.0001995 Jev tariff estimate. Initial source generation and fresh probe are outside pipeline receipt totals, so this is not a complete run invoice. The experiment is small and generation is stochastic; duration and cost are observations, not a statistically established speed/cost improvement.

自动流程已验证记忆与约束实际生效，并且重复执行不产生新变化；此前及中间的失败保留。实际费用按回执范围披露，不能把候选评估的改进推算成所有项目都更好。

The same-input paired manual run also passed all ten checks in both arms; both applied Memory/Harness on pass one and made no changes on pass two. Neither arm saved the unverified Redis guess or resolved 503 in Memory. Artifact: `jev-improvement-manual-workflow.json`.

| Paired manual arm | Entire trial duration | Effects | Two-pass worker cost reported | Jev tariff estimate |
| --- | --- | --- | --- | --- |
| Baseline | 124.522 s | 10/10 | $0.005107772 | $0.000000000 |
| Jev | 113.411 s | 10/10 | $0.004261608 | $0.000229236 |

The paired trial preserves baseline capability while the separate fixed-candidate trials show fewer unsafe accepts. One paired run cannot prove a general latency or billing improvement. The earlier pre-refinement native Harness holds were resolved in the current manual and automatic trials.

## Reproduction

- `bun packages/continual-learning/tests/evaluate_jev.ts --live --fresh-acceptance --require-improvement`
- `uv run --no-project packages/continual-learning/tests/live_jev_workflow.py --auto-only --require-effects`
- `uv run --no-project packages/continual-learning/tests/live_jev_workflow.py --require-effects` for paired manual baseline/Jev.

Official reasoning: [Jev known limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13), [bounded cascade cookbook](https://docs.typesafe.ai/cookbooks/sde_cascade). Neither source establishes this application's empirical accuracy.

## Final verification / 最终验证

- Package regression: `uv run --no-project --with pytest pytest packages/continual-learning/tests -q` — **723 passed in 316.39 s**. The earlier 12 frozen-snapshot fixture failures and prompt-example parser regression were corrected; the final complete rerun is green.
- `pnpm typecheck` — passed (extension TypeScript project).
- `pnpm check:install` — passed, 17 installed workspace Pi packages / 18 settings entries.
- `pnpm pack:check` — passed, 18 registry-free packed manifests.
- `pnpm --dir packages/continual-learning pack --dry-run` — passed for `pi-continual-learning` 0.4.0.
- Fresh independent control-flow/security review — 87/87 focused offline regressions passed; no remaining blocking findings. This verifies control boundaries, not model accuracy.
- Real fresh candidate acceptance and real native manual/automatic effects gates — passed, separately archived above.

The entire repository test suite was not rerun; root typecheck, installation and packed-manifest checks were run. No unrelated failures were observed in those executed checks. No user configuration was changed, package published or remote branch modified.
