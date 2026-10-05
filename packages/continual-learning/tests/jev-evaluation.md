# Jev learning evaluation — 2026-10-04

Historical measurements are retained here. For the subsequent judgment/repair changes, strict improvement gate and current native results, read [Jev improvement acceptance](jev-improvement-evaluation.md).

This report separates boundary tests, offline evaluation, native Pi runtime checks, and real model inference. It records bounded real inference. The refined candidate gate improves decisions on these public samples; general and end-to-end accuracy remain unestablished.

## Interface verification

Checked the official [JavaScript SDK](https://docs.typesafe.ai/sdk/javascript), [API](https://docs.typesafe.ai/api), [Noul](https://docs.typesafe.ai/primitives/noul), [Choice](https://docs.typesafe.ai/primitives/choice), [Score](https://docs.typesafe.ai/primitives/score), [confidence](https://docs.typesafe.ai/confidence), and [models](https://docs.typesafe.ai/models), then inspected installed `@typesafe-ai/sdk` 0.6.0 declarations.

`systemOne({state,questions,model},{signal,timeout,retry})` returns `answers`, actual `model`, and input/output token usage. Noul has no separate confidence. Choice has a winning label and probability map; Score uses an ordered array of criteria and returns an expected score, confidence, legend and probability map. One request evaluates independent questions against the same state; body-dependent relationships are sent only after parent body retrieval. The installed SDK's `models.list()` returns an array, whereas one official models-page example accesses `.models`; the implementation follows installed declarations.

The documented model is `jev-1.13.0`, priced at $0.042 per million input tokens with free output. Limits are 64k total tokens and 32k for state plus the longest question. The integration conservatively bounds serialized requests to 24,000 UTF-8 bytes and 32 questions. Confidence is a distribution statistic, not proof or write permission. English is the primary training language; Chinese performance requires separate evidence. Thresholds are provisional and not fitted to this corpus.

## Regression evidence

`test_jev_learning.py` uses the real SDK with isolated fake transport, and the existing parent workflow fixture with controlled judgment results. It covers both directions, relevance selection, compatible supplementation, duplicate/conflict proposals, unsupported candidates, Harness scope expansion, explicit Memory processing, service/timeouts/abort/bounds/malformed responses, legacy selector fallback, empty-index bypass, parent quote validation before inference, apply/propose policy, unified configuration or environment activation, explicit disable precedence, scope participation, private Memory permissions, discovery beyond keyword screening, and credential checks before JSON encoding. These tests prove wiring and boundaries; their synthetic answers do not prove semantic accuracy.

The fresh independent review reproduced a credential-exfiltration bug through JSON-escaped multiline/structured secrets. A RED test recorded four transport attempts. The fix scans original strings and structured sensitive fields before encoding; GREEN records zero attempts. The reviewer independently reran the seven Jev tests and typecheck, finding no remaining actionable issue in the reviewed paths.

## Fixed offline corpus

Source: [fixtures/jev-learning.json](fixtures/jev-learning.json). Reproduction:

```sh
bun packages/continual-learning/tests/evaluate_jev.ts
```

There are 18 fixed public examples, nine English and nine Chinese. They cover fact + restriction, conjecture, temporary API failure, duplicate, supplement, conflict, narrow/broad Harness, and explicit uncertain Memory. Every Memory candidate passes the existing structure/evidence normalizer; Harness candidates pass `validateHarnessPlan` including quote and fixture checks. No files are applied.

The baseline is the **existing deterministic parent screen plus the existing semantic candidate gate's absence**. It is not the old LLM selector, not a candidate-generator comparison, and not a measurement of actual Memory writes. The deliberately risky candidates measure semantic exposure at that gate, not the rate at which the large model would generate those candidates.

| Offline metric | English (9) | Chinese (9) | With real Jev |
| --- | ---: | ---: | --- |
| Missed expected directions | 0 | 0 | See live comparison below |
| Extra directions | 4 | 2 | Only two decided samples; see below |
| Risky code-valid candidates passed by the baseline semantic gate | 6 | 6 | 0 / 0; see false holds below |
| Supported candidates incorrectly held | 0 | 0 | See live comparison below |
| Median deterministic screen time | ~0.013 ms | ~0.012 ms | 523.5 ms request medians |
| Model requests / input tokens | 0 / 0 | 0 / 0 | 36 / 20,773 total |
| Inference fee comparison | No offline inference | No offline inference | $0.000872466 estimated total |

The evaluator also reports per-language metrics, actual returned model versions, partial results and unknown cost explicitly; a first request with unavailable pricing or incomplete usage stops further requests; uncertain semantic selections still receive independent candidate validation. Simulated test runs are labeled `simulated-jev-inference`, never real inference.

Raw public offline results: [jev-offline-results.json](jev-offline-results.json). Offline After fields remain `null`; separate live artifacts contain actual model judgments, not simulated accuracy numbers. Baseline timings are one local run and are not performance claims. The parent retains deterministic evidence floors, so Jev can add missed directions but does not by itself remove these extra directions; candidate validation is the intended write-quality gate.

## Native Pi runtime

`uv run --no-project packages/continual-learning/tests/live_meaningful_details.py` passed real Pi `--print`, TUI, keyboard expansion, 48-column resize, existing management menus and phase-policy persistence. The receipt displayed selected filenames, controlled fallback reason and returned-version fields. This uses a deterministic local provider and synthetic receipt, with **zero external requests**. It verifies runtime loading and rendering, not Jev inference or a real learned write.

## Initial real Jev inference

The user explicitly authorized the bounded paid evaluation. The primary run used the same 18 fixed public samples, `bun packages/continual-learning/tests/evaluate_jev.ts --live`, and the current environment credential. All 36 requests completed and returned **jev-1.13.0**. No private session or Memory evidence was used. Results: [jev-real-results.json](jev-real-results.json).

| Metric | English baseline / Jev | Chinese baseline / Jev |
| --- | --- | --- |
| Code-valid risky candidates accepted (6 per language) | 6 / 0 | 6 / 0 |
| Risky Memory candidates accepted (5 per language) | 5 / 0 | 5 / 0 |
| Supported candidates held as proposals (3 per language) | 0 / 3 | 0 / 3 |
| Supported Harness candidate held (1 per language) | 0 / 1 | 0 / 1 |
| Usable semantic direction judgments | 9 / 1 | 9 / 1 |
| Median Jev request latency | 523.5 ms | 523.5 ms |

Primary-run totals: **20,773 input tokens**, **$0.000872466 estimated cost**. Baseline inference requests and fees at this deterministic gate are zero. This compares the deterministic screen and absent semantic candidate gate with Jev; it does not compare legacy LLM selector quality, total worker costs, or actual persisted learning.

The remaining 16 direction judgments were uncertain and require the existing selector fallback; that fallback was not executed by this evaluator. Missed/extra-direction counts in the raw report apply only to the two decided samples, so they cannot establish an overall direction improvement or zero misses. The Chinese transient-failure example still triggers two extra directions through the existing deterministic evidence floor. A held candidate means a proposal, not a silently discarded request or an executed Harness block.

A diagnostic repeat of three public English samples made six additional requests using the same prompts and thresholds: [jev-real-diagnostics.json](jev-real-diagnostics.json). It returned **jev-1.13.0**, **3,437 input tokens**, and **$0.000144354 estimated cost**. Correct candidate support probabilities were 0.65, 0.76 and 0.67, below the 0.9 acceptance threshold. Metadata Score distributions were spread across adjacent levels, yielding confidence 0.44, 0.70 and 0.48. These explain conservative fallback/proposals; they do not justify lowering thresholds on this small corpus. No thresholds or corpus labels were changed after observing the answers.

Across both runs: **42 requests**, **24,210 input tokens**, **$0.00101682 estimated cost**, below the authorized 60-request/one-million-token/$0.042 limits. Costs use the published model tariff and returned input usage; actual account billing was not retrieved. Primary-run per-language timings are request medians, not end-to-end learning latency. Timeout/service failures did not occur in this live sample; fallback behavior remains supported by boundary tests.

**Initial-run outcome: no overall learning-quality improvement established.** The gate rejected all supplied risky candidates, but also held every supported candidate, and selection coverage was low. The small curated corpus measures exposure at the semantic gate rather than real-world false-write prevalence. Threshold/prompt calibration on a separate, larger corpus and an end-to-end legacy-selector comparison remain future validation needs; this task does not claim general accuracy, throughput or cost improvement.

The runtime remains optional: configure the `jev` section in user-level `continual-learning.json`, or provide `TYPESAFE_API_KEY` to enable default model/scopes. An explicit disable overrides the environment. Neither option grants mutation permissions. `allowPrivateMemory` is separate and defaults false. No real user config was written by this work.

## Refinement and real quality comparison

The first live run exposed two design errors: Score confidence in an individual level was used to decide whether any relevant level applies; and support judgments were asked to prove administrative frontmatter and executable test fixtures. The refined adapter sums P(level 2)+P(level 3), preserving the same 0.9/0.1 decision bounds. It presents the Memory knowledge body or Harness rule, preserving rewrite action, target and relevant context, while scanning the full original candidate before projection. Parent validation still owns metadata, quotes, fixtures and permissions. Candidate acceptance thresholds were **not lowered**. Harness state explicitly carries its parent-validated project shared-layer execution scope; no global write authority is inferred.

A RED regression reproduced fallback for a Score distribution concentrated across two relevant adjacent levels. The GREEN regression also checks frontmatter/fixture projection, rewrite identity/context and original-secret blocking. Independent review reproduced an incorrect rewrite action; it was fixed and independently retested. These changes address the decision representation rather than fit probabilities to labels.

The final run repeats the original **unchanged 18 examples** against the refined adapter: [jev-quality-results.json](jev-quality-results.json). The initial live adapter is retained in [jev-real-results.json](jev-real-results.json).

| Original corpus metric | Before Jev (deterministic gate) | Initial Jev | Refined Jev |
| --- | ---: | ---: | ---: |
| Risky candidates accepted / 12 | 12 | 0 | 0 |
| Supported Memory accepted / 4 | 4 | 0 | 4 |
| Supported Harness held / 2 | 0 | 2 | 2 |
| Supported candidates held / 6 | 0 | 6 | 2 |
| Decided semantic selection samples / 18 | Not applicable | 2 | 6 |
| Median request latency, English / Chinese | No model request | 523.5 / 523.5 ms | 523.5 / 520.5 ms |
| Input tokens / estimated fee, whole run | 0 / $0 | 20,773 / $0.000872466 | 20,657 / $0.000867594 |

All ten supplied risky Memory candidates remain unaccepted. Duplicate and conflicting Memory now receive explicit duplicate/conflict findings rather than uncertain support. The two supported Harness candidates still become proposals: certainty about non-expansion remains insufficient. This is a remaining false hold, not an executed tool block or a discarded user request.

Direction coverage improves in this fixed corpus but remains only 6/18; the other 12 cases need the unmeasured legacy selector. Refined raw zero-miss counts apply only to decided cases. Existing deterministic floors still add one extra direction in the English decided subset and two in Chinese. No overall routing or end-to-end learning claim follows from these partial judgments.

A new, separately written **12-example Memory corpus**, labeled before inference and not used to adjust the adapter, covers uv/Ruff facts, review preferences, conjecture, transient downloads, duplicates and supplements in both languages: [fixtures/jev-learning-holdout.json](fixtures/jev-learning-holdout.json). It is a small manually authored supplementary corpus, not an independent statistical benchmark. Final results: [jev-holdout-results.json](jev-holdout-results.json).

| New corpus metric | Deterministic gate | Refined Jev |
| --- | ---: | ---: |
| Risky Memory accepted / 6 | 6 | 0 |
| Supported Memory held / 6 | 0 | 1 |
| Supported Memory accepted / 6 | 6 | 5 |
| Decided semantic selection samples / 12 | Not applicable | 5 |
| Median request latency, English / Chinese | No model request | 383 / 364 ms |
| Input tokens / estimated fee | 0 / $0 | 13,106 / $0.000550452 |

The held new candidate is an English compatible supplement. Chinese direction floors produce two extra directions among three decided samples, versus one extra direction across the full Chinese deterministic subset; denominators differ and routing improvement is not established. The baseline also misses two expected directions per language across all six samples; uncertain semantic routes are not treated as absent learning opportunities.

The first new-corpus attempt stopped at the synthetic review preference because parent normalization marks preferences private. It made five actual network requests and six adapter invocations; the sixth was locally denied and had no model usage. Its partial artifact is [jev-holdout-policy-results.json](jev-holdout-policy-results.json). A repeat explicitly enables private transmission **only for this checked-in public synthetic fixture**; runtime defaults and real user config are unchanged. Reproduce the final corpus with `bun packages/continual-learning/tests/evaluate_jev.ts --live --holdout` under authorized credentials and cost limits.

Across both final corpora, 18 risky candidates remain unaccepted and 9/12 supported candidates are accepted. The candidate error count falls from 18/30 at the deterministic semantic gate to 3/30 with refined Jev. Relative to initial Jev on the unchanged original corpus, four valid Memory candidates are recovered with no additional risky acceptance. This is measured improvement at the candidate gate on these curated samples, with reduced recall and remaining Harness holds explicitly reported. It is **not** a production false-write rate, an actual durable-write benchmark, or evidence of general model accuracy.

Development artifacts also retain the 9-example refinement probe, intermediate full-corpus request answers, and four Harness scope probes: [focused](jev-quality-focused-results.json), [prompt comparison](jev-quality-prompt-results.json), [scope probe](jev-quality-scope-results.json). No labels or thresholds were modified after these observations. The user's subsequent ongoing authorization covers additional inference beyond the initial 60-request ceiling. Cumulative actual network requests across all recorded runs: **169**, **95,709 input tokens**, **$0.004019778 estimated fee**. One additional adapter invocation was denied locally. Every completed inference returned **jev-1.13.0**. Actual billed fees were not retrieved.

## Final local verification

- Full continual-learning pytest run after refinement: **706 passed**, 469.16 seconds.
- Latest affected Jev and evaluator regressions: **13 passed**, 15.99 seconds; unknown pricing, incomplete usage and their combination stop further calls.
- Root TypeScript check: latest rerun passed. The earlier unrelated `packages/goal/src/scheduler.ts:367` TS18048 diagnostic no longer occurs in the current worktree; this task did not modify that module.
- Isolated continual-learning runtime and evaluator TypeScript check, extending the root compiler options: passed.
- `pnpm check:install`: passed; 17 installed Pi packages and 18 settings entries checked.
- Target package `pack --dry-run`: passed; new Jev runtime module included.
- Root `pnpm pack:check`: passed; 18 packed workspace manifests validated.
- Native offline Pi print/TUI: passed, including Jev receipt details; zero remote requests.
- Independent boundary reviews: reproduced privacy and evaluator accounting findings fixed with regressions; final follow-ups passed.

No remaining failure was observed in the listed checks. The whole repository pytest suite was not run. No package was published, and no real user settings, Memory or Harness files were changed.

## Completion audit

| Requirement | Current evidence | Limit |
| --- | --- | --- |
| Optional unified configuration or environment activation | SDK transport regressions, explicit disable and scope tests | Real user configuration unchanged |
| Independent Memory/Harness judgments and metadata selection | Noul/Score adapter and fake-transport assertions | General accuracy unestablished; limited live comparison above |
| Body-dependent relation judgment after retrieval | Parent dossier flow and Choice candidate regressions | General relationship quality unestablished; limited live samples reported above |
| Frozen quotes and parent-owned writes | Invalid-quote zero-call regression, apply/propose policy checks | Synthetic candidate generation |
| Explicit Memory, fallback, duplicate/conflict and broad Harness | Parent workflow and adapter regressions | Workflow regressions use simulated answers; separate live judgments reported above |
| Privacy, bounded transport and controlled receipts | Credential regressions, private scope checks, native print/TUI | No real private evidence transmitted |
| Package tests, types, installation and packing | Exact verification results above | Whole repository pytest not run |
| Fixed bilingual comparison | 18 public offline/live examples and real returned model/usage | Small curated corpus; legacy LLM fallback not measured |
| Learning-quality conclusion | Original and new public live corpora, risk acceptance preserved and valid Memory recovered | Candidate-gate improvement established on these samples; general/end-to-end effects unproven |

The requested implementation, boundary verification and bounded real-effect evaluation are complete within the reported scope. Real inference establishes the limited candidate-gate improvement described above and retains remaining false holds and routing gaps; mock tests are not used as quality evidence.
