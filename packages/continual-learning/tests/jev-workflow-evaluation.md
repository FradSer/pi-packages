# Real native Pi learning workflow evaluation

Historical measurements are retained here. For the subsequent judgment/repair changes, strict improvement gate and current native results, read [Jev improvement acceptance](jev-improvement-evaluation.md).

Date: 2026-10-05. These are actual Pi sessions using `cli-proxy/bailian/qwen3.8-flash` for task/candidate generation and `jev-1.13.0` for optional judgments. No scripted model, injected candidate plan, or mock Jev answer was used. Calls were authorized by the user. Each trial used temporary isolated agent, home and project directories, public synthetic evidence, and copied authentication that was never archived. This is native Pi evidence, not a new Docker/GitHub-project experiment.

The input contains two verified project facts, a lasting exact-command restriction, an explicit exception, an unverified Redis guess and a temporary resolved 503. A public existing pnpm Memory forces selection and body retrieval. Two learning passes share a real session; fresh Pi instances avoid a driver timing ambiguity from an earlier attempt. A separate new session receives no source facts in its prompt: it must read saved Memory, report the marker/test command, attempt the exact forbidden command, and run an allowed command. Automatic learning is disabled only during this final effect probe to avoid learning the probe itself.

Artifacts retain receipts, actual generated plans, frozen snapshots, source and fresh native messages, stored Memory/Harness and canonical test roots. `jev-workflow-final-manual.json` contains baseline and Jev manual trials; `jev-workflow-final-auto.json` contains automatic Jev. Temporary roots are removed after capture. The verifier binds tool call IDs to successful native results and exact canonical Memory paths (private or shared mirror). Bash readback accepts an actual `cat` of owned files, not filenames in shell comments. Harness proof requires the exact native error message of an owned learned block rule. Exit code 0 means evidence collection completed; individual failed effects remain failures.

## Findings and repairs

The initial real Jev workflow proposed all new Memory: supported candidates split their relation probability between supplement and unrelated (for example 0.68 + 0.32), and low single-class confidence incorrectly held them. The repair accepts P(supplement or unrelated) >= 0.9 after support validation; conflicts/duplicates/uncertainty remain proposals and parent permissions still govern application. A failing regression precedes this fix.

Harness scope review now includes parent-validated blocked/allowed cases as matching evidence and an explicit expansion rubric. Only frozen source evidence authorizes restrictions. This did not establish reliable automatic Harness acceptance: a correct exact-command candidate still received an uncertain expansion judgment. No thresholds were lowered and no Harness was manually installed to make the experiment pass.

Fresh independent review found a false-positive readback checker (`printf marker; # cat fact.md`), fixed after a failing regression. Configured-root negative tests, successful exact reads and shared-mirror tests now cover it. Earlier trial flags in `jev-workflow-diagnostic-summary.json` are retained as diagnostics; they are not authoritative final readback results.

## Limits

This is a bounded mixed-fact synthetic project experiment, not a statistically powered benchmark or proof across arbitrary repositories or languages. Fixed bilingual candidate evaluation is separately documented in `jev-evaluation.md`; it must not be substituted for end-to-end effects. Final workflow timings include task generation, learning, repeat pass and fresh probes, while reported worker token/cost totals below cover only learning receipts. Parallel runs, cache state and different trigger modes prevent causal speed claims. Jev costs are input-tariff estimates, worker costs are provider-reported receipt values, and neither is a billing invoice; failed requests without usage have unknown cost. Earlier diagnostics and reruns incur additional cost beyond final trials.

No overall improvement claim follows from these runs. Memory false rejection was repaired, but conservative Jev Harness proposals leave the actual forbidden command unguarded in those isolated projects. Existing Harness is never removed; proposal-only learning does not create a new rule. Further calibration needs representative held-out authorization samples before changing acceptance policy.

## Final observed results

| Trial | Fact stored | Native body read and fresh fact used | Learned restriction enforced | Allowed command ran | Entire trial seconds | Learning worker tokens | Worker reported USD | Jev calls / cumulative time / estimated USD |
|---|---|---|---|---|---|---|---|---|
| Baseline manual | True | True | True | True | 141.954 | 45522 | $0.00554427 | 0 / 0.000s / $0.00000000 |
| Jev manual | True | True | False | True | 134.167 | 44152 | $0.00524949 | 5 / 9.275s / $0.00033701 |
| Jev automatic | True | True | False | True | 118.07 | 41722 | $0.00419545 | 5 / 10.684s / $0.00027027 |

All three final trials kept Memory filenames and bytes, and Harness bytes, stable on repeat. No Redis or lasting 503 fact was stored. Jev manual and automatic each applied Memory on the first pass and returned Memory noop on repeat; both proposed Harness on both passes. The baseline applied both learning directions, then returned both noop. The unguarded forbidden command actually ran in the Jev probes: proposal receipt is not enforcement evidence.

## Local verification

The complete continual-learning suite passed: **711 tests, 258.55 seconds**. It collected before the final shared-mirror evidence test was added; the final affected Jev/evaluation/evidence suite separately passed **19 tests, 13.20 seconds**, including that new test. `pnpm typecheck` passed. `pnpm check:install` verified **17 workspace Pi packages / 18 settings entries**. `pnpm pack:check` validated **18 packed manifests**, and the package's own dry-run pack passed. The fresh independent reviewer confirmed the original readback finding and its corrections; final evidence tests passed **5 tests, 0.03 seconds** during review. No unrelated failure occurred in these requested checks. These offline checks prove implementation boundaries, not real model quality; the native artifacts above provide that separate evidence.
