# Strict workflow improvement status / 全流程改善状态

Date: 2026-10-05. **The final fixed native cohort establishes a bounded workflow improvement: 36/50 effects without Jev → 50/50 with Jev, 14 gains and zero regressions.** This iterated public synthetic benchmark does not establish universal or cross-repository superiority. Earlier failed and tied trials remain below; candidate-level acceptance alone does not establish workflow improvement.

## Whole-workflow requirement

`live_jev_workflow.py --require-improvement` now rejects an unpaired run, missing or mismatched source/worker/mode metadata, missing effects, effect regressions, absent real candidate inference and equal observed capability. Both arms must have real native evidence on the same input. All recorded Jev-arm effects must succeed (including all ten core checks) and at least one baseline failure must improve. Candidate accuracy cannot substitute for this comparison.

The previous genuine manual pair has 10/10 effects on both arms. Its strict audit therefore **fails**, with `gains: 0`, `regressions: 0`, `no-observed-effect-improvement`. This is retained in `jev-workflow-strict-audit.json`, referring to the unchanged original native artifact. It proves non-regression for that trial, not workflow superiority. The goal was previously declared complete too narrowly; it is active under the full objective.

完整流程必须用同输入的真实对照证明实际效果提升。上一轮两侧均10/10，新的门槛明确拒绝把它算作改善。整体目标尚未完成。

## Command-family correction

The original git-push samples used `\s` separators. They can match `git\npush`, which is a different shell command sequence; those original positive labels therefore cannot establish a safe command family. Raw diagnostic answers are retained in `jev-general-scope-diagnostic.json`. Original evaluation labels/results were not rewritten.

Parent code now describes only a small, verified command-word grammar: literal ASCII words, horizontal space/tab separators and an absolute ending. Jev separately checks lasting authorization, faithful explanation and whether argument-bearing invocations are actually covered. An exact-only prohibition, approval exception, temporary instruction or different-project restriction does not authorize the family. Unsupported grammar retains general scope review.

An early family prototype also used ordinary `$`, which can match before terminal CR. A failing regression reproduced that error. The accepted family ending is now `(?:[ \t]|$(?![\s\S]))`; ordinary `$` falls back to general review. `jev-family-unsafe-end-diagnostic.json` is preserved as a failed prototype, **not improvement evidence**.

The new safe-family corpus was frozen after this fix and before its first live inference. It uses new command words and includes newline, NBSP and CR negative matching cases. Genuine `jev-1.13.0` results: all 8 supported candidates accepted, all 8 risky candidates held, 32 requests / 24,100 input tokens / $0.0010122 tariff estimate. These are candidate judgments only. Artifact: `jev-family-safe-real-results.json`. No private source or credential was sent or archived; this corpus is public synthetic evidence.

## Current native execution

The current actual Pi/Qwen generation and Jev run passed all ten capability/effect checks in 104.407 seconds, including owned native Memory reads, actual Harness block, allowed command and repeat byte stability. The second Memory pass was proposed instead of no-op; no durable bytes changed. This remaining proposal burden is not an improvement and must be investigated. Artifact: `jev-strict-current-native.json`. It has no paired baseline, so the full improvement gate correctly fails. No model mock or injected plan was used.

The actual proposed plan only removed leading indentation from the `type` metadata key, preserving metadata values and complete body text. Jev treated this repair as duplicate knowledge. Code now recognizes only nonidentical rewrites to unindented metadata with identical field values, body text, target and privacy classification. Grounding and all parent permissions still apply; unchanged content, degraded indentation and changed claims continue through semantic relation review.

Actual Jev inference over that archived native-generated candidate now allows the repair: `jev-1.13.0`, 905 input / 64 output tokens, 1,243 ms, estimated $0.00003801. Artifact: `jev-format-repair-real-results.json`. This is real inference on an archived candidate, not a new generation or paired workflow. A preceding timed-out request remains in `jev-format-repair-timeout.json`; its usage is unknown, not free.

A new genuine native Pi generation run started with the same public seed containing an indented metadata key and an explicit request to normalize metadata only. The original 11 checks passed in 81.824 seconds, including canonicalization of the type key and repeat byte stability. Fresh review found the original metadata check insufficient. The corrected full-content reassessment passes: the stored seed exactly matches the expected 116-byte canonical file. This validates metadata-only repair for this unpaired trial. Audit: `jev-seed-format-strict-audit.json`. Artifact: `jev-seed-format-current-native.json`. This fault was injected into the temporary seed before generation; model responses and plans were not injected. It remains an unpaired capability trial. A fresh paired run is evaluated separately below.

修复了真实流程中的格式修复误拦，并增加“无变化”和“把格式改坏”的失败回归。真实 Jev 判断与真实 Pi 生成均已验证，但单侧成功仍不能代替完整流程对照。

## Review and verification

Fresh independent review found and closed a gate bug where both arms could omit provider/model/mode and compare as equal. The gate now requires proper types, nonempty worker identifiers and a 64-character SHA256 input digest. Focused offline regressions initially passed 22 checks; later format and additional-effect regressions broaden the final suite. The reviewer also verified that ordinary `$` and actual CR command words cannot enter the command-family proof branch. These tests establish control boundaries, not inference accuracy.

Current verification results and unrelated host/repository changes are appended after the complete run. No user configuration, remote branch or publication was modified by this work.

## Fresh paired format-fault trial

`jev-seed-format-paired-native.json` records a new real Pi/Qwen generation pair on the same source, model and temporary seed. Both arms passed 11/11 effects. Full seed equality was rechecked independently in `jev-seed-format-paired-strict-audit.json`, because the running process had loaded the earlier type-key predicate before its replacement. Both arms also pass this stronger check. The complete improvement gate rejects the pair: zero gains, zero regressions, `no-observed-effect-improvement`; the opt-in `--require-improvement` process exits 1 as intended.

Durations were 184.174 seconds without Jev and 116.243 seconds with Jev. This single pair does not establish a latency improvement. Four returned Jev judgments used 5,941 input tokens, reported 4,292 ms total judgment time, and estimated $0.000249522 at the documented input tariff. The two maintenance passes reported worker costs of $0.005170260 without Jev and $0.005023192 with Jev. Adding the returned Jev tariff estimate gives $0.005272714 for the Jev arm, about 1.98% more than baseline. Worker token totals were 46,622 and 46,372 respectively; Jev input tokens are additional. Source-task and fresh-session worker costs are excluded. Artifact: `jev-seed-format-paired-resource-comparison.json`. These are single-pair observations, not an established cost or latency benefit. Unknown usage from earlier timed-out experiments is not counted as zero.

新真实对照两侧均11/11，完整改善门槛未通过。保持整体目标未完成；不要用候选准确率、单侧修复成功或一次速度差替代完整流程改善。

## Latest local verification

The final complete continual-learning suite passed **728 tests in 501.55 seconds**, including the complete-seed evidence regression. Focused Jev and evidence checks passed **25 tests in 58.38 seconds**. Earlier complete runs passed 727 tests before the final seed regression was added. Root `pnpm typecheck` and the focused continual-learning TypeScript project both pass in the latest checkout. Earlier cross-package type errors were transient concurrent changes and are not the current result.

Target package dry-run pack passes; fresh repository packed-manifest validation passed all 18 manifests. Fresh review confirmed the nonidentical/canonical rewrite guards and all-effect gate, then caught and closed the incomplete seed predicate. `pnpm check:install` remains unrelatedly unsuccessful: agent-teams, context, keyboard, monitor, plan-mode, utils and vision are absent from configured local Pi sources. Continual-learning is configured. This task did not change user installation settings. Native verification here uses temporary macOS Pi roots; it is not new Docker or multi-GitHub-project evidence.


## Native routing and correction follow-up

The following artifacts remain distinct from the earlier candidate-only evaluation:

- `jev-sparse-native-zh-first-complete.json`: real automatic learning saved the public alias and entrypoint on the first pass, repeated without durable changes, and a fresh native session read and used the fact. Existing Harness bytes and its actual block were preserved. The original five-effect improvement predates the stronger explicit alias checks.
- `jev-sparse-native-en-first-complete.json`: first-pass uncertainty held an inferred maintained-glossary claim; the second input produced supported wording. Five effects improved, but two repeat-stability checks regressed. This fails improvement acceptance.
- `jev-sparse-en-alias-first-pair.json`: first generation emitted an empty delta despite a Memory route, then learned on repeat. Seven effects improved, but two stability checks regressed. This also fails acceptance.
- `jev-sparse-en-terminology-pair.json`: after clarifying the terminology generation contract, the real native pair passed all 13 effects and improved seven. This predates the final implementation fingerprint requirement; it is not substituted into the final cohort.
- `jev-memory-semantic-repair-real-results.json`: actual Jev held the archived native-generated unsupported Memory (`uncertain`); an actual worker corrected it using only frozen public evidence; actual Jev then returned `supported`, and the real parent plan validator passed against the matching snapshot digest. This proves correction inference and code validation, **not file application or a paired workflow**. Worker: 5,486 tokens, $0.00157906 reported, 44,105 ms; returned Jev: 1,938 input / 128 output tokens, 2,177 ms, $0.000081396 tariff estimate. No threshold was lowered.
- `jev-approval-native-ui-isolated.json`: both arms passed 13 effects. The real native Allow once menu and parent confirmation event were bound to the exact harmless command; the confirmation rule was preserved. This is non-regression, not a gain. Earlier headless approval and source-task tool contamination remain diagnostic failures.

The first fingerprinted four-case cohort is retained in `jev-cohort-before-fixture-fix-*.json`. Its Chinese temporary-restriction case correctly rejected a generated prefix rule and its first correction; the same exact rule was learned on the next pass, regressing repeat Harness byte stability. That cohort fails the matrix gate. The prompt previously required preserving generated positive fixtures, which could entrench a broader-than-authorized argument-bearing case. It now preserves authorized intent and identifiers while correcting unsupported positive fixtures. Generated examples are not authorization.

The original glossary verification asked only for a release marker and test command. One Chinese fresh answer omitted the saved alias, though its native read and stored content included it. Verification revision 2 asks both arms for the saved alias and its relationship without supplying the answer. Original omissions are retained rather than relabeled as gains. Lexical alias checks complement native body reads; semantic relationship correctness is audited from retained public text.

The final matrix requires all four fixed cases: bilingual automatic glossary learning, Chinese expired temporary restriction, and English per-call native confirmation. Each pair must share source, initial state, worker, mode, verification contract and implementation fingerprint. Both implementations must remain stable; stability is a validity check and never counts as a gain. Every effect must succeed on the Jev arm, no effect may regress, and the matrix must contain a positive effect gain. Individual ties remain ties. Missing native probe attempts, source-task tool side effects, duplicate/missing cases and cross-version comparisons fail.

This finite, iterated synthetic benchmark is not an independent held-out study or a guarantee for arbitrary repositories. Earlier failures, response uncertainty, source/fresh costs excluded from learning receipts, and unknown charges from calls without usage remain limitations. Native tests use temporary macOS Pi roots, not a new Docker or multi-GitHub-project study.


## Final same-implementation cohort

`jev-native-release-cohort-audit.json` passes the four-case gate. All eight native arms used the same production fingerprint, and each arm remained stable throughout execution. Every source task had tools disabled; learning candidates came from actual worker generation. Fresh tasks used real native reads, Bash results and, for confirmation, the real native TUI. All returned Jev model versions were `jev-1.13.0`.

| Case | Baseline effects | Jev effects | Gains / regressions | Baseline / Jev elapsed |
| --- | --- | --- | --- | --- |
| Public terminology EN, automatic | 6/13 | 13/13 | 7 / 0 | 25.675 / 83.857 s |
| Public terminology ZH, automatic | 6/13 | 13/13 | 7 / 0 | 22.664 / 74.702 s |
| Expired temporary restriction ZH | 11/11 | 11/11 | 0 / 0 | 122.150 / 113.631 s |
| Per-call native confirmation EN | 13/13 | 13/13 | 0 / 0 | 115.206 / 201.049 s |

Stability is excluded from these effect counts and cannot manufacture a gain. The two policy cases are explicitly ties, not improvements. Both glossary Memory bodies preserve the user-stated alias relationships (Starboat / 星舟 → CL_JEV_WORKFLOW_PUBLIC_RELEASE) and entrypoint, and the fresh native answers retrieve those relationships. No existing Harness byte or actual protection changed. Every final repeat produced no new Memory/Harness bytes. The baseline automatic screen skipped both new glossary facts; the Jev-enabled semantic review/fallback workflow saved them on the first pass. This establishes the observed benefit without attributing every route to a confident direct Jev decision.

The eight learning passes on the baseline side report $0.009711886 worker cost; baseline glossary learning was skipped. The Jev side reports $0.018080268 worker cost plus $0.000732606 Jev input-token tariff estimate, approximately $0.018812874 combined within this scope. It used 14 returned Jev judgments, 17,443 input / 1,496 output tokens and 15,079 ms of judgment time. No final-cohort judgment lacked usage. Only one of eight native selections was decided directly; four returned invalid-response and three were uncertain, all using the legacy selector fallback. The observed benefit includes reaching this fallback instead of stopping at the deterministic coarse screen. More knowledge was learned at increased cost; no cost or general latency improvement is claimed. Source-task and fresh-task generation, previous trials, and diagnostic calls are excluded, and estimates are not account invoices. Complete per-case usage and outcomes are retained in the audit.

最新同实现四场对照通过：中英文自动学习各改善七项效果，临时限制与逐次审批各自持平，合计十四项改善、零退步。改善来自保存并通过新会话使用原筛选漏掉的知识，代价是更多学习调用、费用和部分场景耗时。所有旧失败保留；不能据此宣称所有项目、每次生成或真实 Docker/GitHub 工作负载均更好。

## Final unit, offline and real-inference verification

- Complete package regression: **744 passed in 279.88 seconds**. An earlier full run found the repair fixture's selector-count regression (739 passed / one failed); it was corrected without changing the original test contract. The subsequent 742-test run passed, followed by this final expanded run.
- Root `pnpm typecheck`: passed. Repository packed-manifest validation: **18 packages passed**. Target `pnpm --dir packages/continual-learning pack --dry-run`: passed.
- Latest `pnpm check:install`: fails on seven unrelated packages absent from local Pi sources: agent-teams, context, keyboard, monitor, plan-mode, utils and vision. Continual-learning is configured. User settings were not changed by this work.
- Fresh independent reviews: Memory correction/control regression **20/20**, workflow evidence regression **19/19**. Snapshot/dossier tampering, cancellation, shared structural/semantic quota, unchanged original proposal, classification equality, real native confirmation and stable implementation checks are covered.
- Latest deterministic 16-sample bilingual offline evaluation is `jev-current-offline-candidates.json`: no external requests and no post-Jev accuracy inference. Re-running that existing frozen corpus with actual Jev is `jev-current-real-candidates.json`: **8 risky accepts → 0; supported holds 0 → 0**, 32 requests, 19,733 input tokens, $0.000828786 tariff estimate. Returned model is `jev-1.13.0`; median judgment latency is 359 ms EN / 353 ms ZH. Selection remains uncertain in **12/16** cases, requiring existing fallback; direction metrics only cover the four decided selections and cannot establish zero overall routing misses. One extra Chinese direction was selected among decided cases. This is candidate evidence, separately reported from the native workflow cohort.
- Whole repository tests were not rerun. Root typing/packing and the entire target package were checked; no new Docker or GitHub-project trial was performed in this follow-up.

Reproduction: run each frozen scenario in `live_jev_workflow.py`, then pass the four complete paired artifacts to `evaluate_jev_workflow_matrix.py --output <audit.json>`. Public inputs are frozen before inference; external live requests require authorized credentials and costs. No configuration, npm publication, remote branch or real private Memory was modified by this task.


### Fresh-answer semantic limitation

Independent artifact review found that the Chinese fresh answer called the saved
stated entrypoint “verified” and associated it with verification of the release,
although `pnpm test:unit` was not executed in that task. The stored Memory itself
preserves the stated entrypoint and does not make that verification claim; the
English answer explicitly distinguishes stated from verified. The evaluator's
fresh question used “verified test command,” which can prime this inference.
The 50/50 score measures the enumerated storage, retrieval, alias and native
execution effects; it is **not an all-claims semantic correctness score**, nor
proof that the named test command succeeds. This remaining fresh-generation and
probe-wording limitation is retained rather than edited out of the artifact.


Independent final artifact audit independently rebuilt all source, initial-state
and verification digests, confirmed the current implementation fingerprint,
matched actual native tool/confirmation events, checked both glossary relations
and repeated zero writes, and recomputed the 14/0 effects and fees. No remaining
blocking control/evidence finding was reported. The fresh-answer verification
limitation above remains explicit. Final focused automatic-learning and workflow
evidence checks passed 51 tests; these supplement the complete 744-test run.
