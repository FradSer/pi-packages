# Docker learning experiment — 2026-10-04

This report covers actual configured-provider inference through Pi 1.0.2 in
independent Linux ARM64 Docker containers. Model: `cli-proxy/bailian/qwen3.8-flash`;
Node: 22.23.2. Each case starts with empty Memory and enabled automatic learning.
AGENTS.md learning is disabled to keep this experiment focused on Memory and
Harness. No upstream commits or remote publication are performed.

## Measured projects

| Project | Pinned commit | Independent checks | Learned operations | Fresh session and native enforcement |
| --- | --- | --- | --- | --- |
| [Click](https://github.com/pallets/click) | `06b2a678741131fd577ce170e23e5ca0aeba0309` | 2,241 baseline → 2,242 passed; 24 skipped, 31,000 upstream stress cases deselected, 1 expected failure | 2 Memory + 1 Harness | Passed |
| [p-limit](https://github.com/sindresorhus/p-limit) | `a8a6fbec4e0e866d6d779b10889bb4f5567e70eb` | 30 baseline → 32 passed | 2 Memory + 1 Harness | Passed |
| [mitt](https://github.com/developit/mitt) | `6b41670516ed8e8b738612f60491995470aa63b3` | 19 baseline → 20 passed, plus original typecheck/lint/type-test stages | 3 Memory + 1 Harness | Passed |

Click exercises environment restoration after a caught command exception;
p-limit exercises a raised concurrency limit with queued fulfilled/rejected work
and invalid setter values. All checks execute the real project implementation.
mitt exercises a handler unsubscribing itself during event emission while the
remaining handlers still run. No case needed to change project production source.
All three complete cases passed, with **7 Memory operations and 3 Harness rules**.

Passing cases require actual parent receipts, private preference retention,
safe project facts, byte-identical safe mirrors, complete Memory reads in a new
session, the saved verification command, a paired native blocked Bash result
before a local marker side effect, and a separate successful allowed Bash call.
The push executable is a harmless local wrapper: this proves native interception
and absent execution, not a real GitHub push.

## Confirmed plugin improvements

The first real p-limit learning receipt accounted for 274,317 tokens across
selection, Memory and Harness. Its evidence carried assistant reasoning,
signatures, and provider transport metadata, which cannot establish durable
knowledge or verified behavior. Incremental evidence now preserves complete
human/tool entries and their positions while retaining only visible assistant
text and tool calls. The source session is not mutated; full maintenance retains
its existing scope.

A paired projection of that exact captured task reduced its compact serialized
Task Slice from **119,842 to 73,496 bytes (38.67%)**. All 42 entries remain, with
zero omitted entries. This is a same-input payload measurement, not a claimed
38.67% reduction in billing or inference latency. Later tasks differ in tool
history and provider caching, so their token totals are not a controlled cost
comparison.

One early real p-limit selector attempt failed with no persisted rejection
reason. The headless receipt now retains a controlled parent-generated diagnosis
for schema rejection, worker failure, cancellation or changed selected Memory.
Raw model output and stderr are not copied into that diagnostic. Invalid digest,
filename and schema boundaries still fail closed; no durable output is forced.

## Comparison and limits

The no-extension baseline uses a separate empty agent configuration on the same
filesystem. It is allowed to discover Memory manually and did recall the private
preference. It is not deliberately made to fail.

| Project | Baseline tool calls / seconds | Plugin tool calls / seconds |
| --- | --- | --- |
| Click | 9 / 34.21 | 4 / 17.28 |
| p-limit | 8 / 33.87 | 3 / 14.81 |
| mitt | 11 / 76.88 | 5 / 32.25 |

These are single observations for one provider and small tasks, without a
statistical latency or quality claim. Learning has an upfront cost. This does not
establish that every conversation contains a useful durable lesson, that all
providers work equally, or that AGENTS.md learning is effective.

## Environment and experiment repairs

Failed attempts are retained. Click initially lacked the `less` pager; the image
now includes it. An earlier Click run added a valid test to the existing test
module rather than the requested new file, so the task now follows the upstream
module convention.

The historical mitt checkout needs npm-compatible hoisting, generated bundles,
Node 18 types compatible with TypeScript 4.9, and ts-node CommonJS loading instead
of obsolete `esm` on Node 22. The disposable checkout's environment patch is
exported separately. Original typecheck, lint, Mocha and type-test stages remain;
their initial failures are not attributed to continual-learning.

The harness initially misclassified a valid native refusal because it expected
English block keywords. Verification now compares the actual enabled block
rule's exact message with the paired native error and absent side effect, using
only exact target commands and bounded working-directory/redirection variants.
Echoes, ordinary shell errors and disabled rules do not pass. A separate false
success path where a nonzero runner exit could retain `status: passed` is fixed.
Artifact-transfer/timeout failures remain failures and retain their report before
owned-container cleanup.

## Verification and artifacts

- Package suite: **689 passed** before the final additional coverage; latest
  affected tests: **37 passed**, including projection, selector diagnostics,
  native-proof and container-failure regressions.
- Root typecheck, installation check, package dry pack and packed manifest checks
  for all 18 workspace packages passed.
- Real-provider host Pi smoke passed Memory updates, AGENTS.md application,
  new-session retrieval and real Bash guard behavior in disposable roots.
- Offline native TUI check passed expansion, 48-column resize, full prompt
  readback and management menus. It made zero remote requests; it is separate
  from the real-provider Docker cases.
- Fresh independent reviews found no remaining blocker in the changed evidence,
  diagnostic or Docker-proof paths after the reported fixes.

All successful cases use identical plugin/kit runtime source:
`3211201ed431c87fe12ea4da2d259b6b09f55e769374b7bb194f0292943a1af7`.
This digest hashes sorted extension/prompt/kit-source relative paths, a zero-byte
separator and file bytes, followed by both package entry points. Docker runner
digests additionally include the harness and Dockerfile; they differ while the
fixture is repaired, without changing that runtime implementation.

Local raw artifacts are under
`/Users/FradSer/.cache/pi-continual-learning/docker/`:

- `20261004T075822Z/click/`: complete passing case; runner digest
  `6dba7804647e82ec282037fcbbd61d7fa1ce5338d31a12ed50f1936c9473fc96`.
- `20261004T075450Z/p-limit/`: complete passing case; runner digest
  `65d7172d8368c474169d63aec61c3a66b5530cc9fe52decfbfe91715bcfd9b1e`.
- `20261004T080510Z/mitt/`: complete passing case; runner digest
  `f25a4c61f5f306a692b9ba8cb822d844335c5fc7c64f67945f4263f3e8668671`;
  includes the historical test-environment patch.
- `20261004T071427Z/p-limit/`: first actual learning receipt and unchanged source
  for the paired payload measurement; the original baseline assertion failed
  because manual filesystem discovery succeeded.
- `20261004T072634Z/`: original environment failures and the selector failure
  without a persisted diagnosis.
- `20261004T074436Z/`: actual applied learning and native p-limit refusal retained
  despite the earlier verification false negative.
- Other timestamped directories retain the intervening environment and fixture
  failures. Each case exports its report, sessions, real checks, diff and Memory;
  each host run records source digest, image ID and provider request/error counts.

See [the runner instructions](README.md) to reproduce with the current source.

## Follow-up: avoid a redundant cold-start selector

Reflection on these runs identified a structural cost: with an empty indexed
Memory corpus, explicit user facts/preferences already establish the parent
phase floor. A selector model has no existing entries to choose, but can still
fail its output format and prevent the planners from running.

Automatic learning now routes that narrowly defined empty-index case locally.
An initial explicit `/memory <request>` is Memory-only and uses the same path.
Nonempty indexes, ambiguous tasks and ordinary `/consolidate` keep the metadata
model selector. The same immutable dossier, planner proposals, private/safe
classification, evidence checks, transactional writes and policy masks apply.
This saves one selector inference, without mandating durable output.

The updated p-limit case at
`/Users/FradSer/.cache/pi-continual-learning/docker/20261004T120843Z/p-limit/`
passed the complete independent-test, learning, private/safe mirror, full-read,
saved-command and native Bash block/allow checks. Its selector receipt records
**79 ms, no worker usage**, with diagnostic
`empty Memory index; parent-routed explicit evidence`. Memory initially rejected
a candidate, then applied three operations after one bounded repair; Harness
applied one rule. Both rejected and repaired attempts remain in its receipt.
Total reported learning usage is 70,583 tokens, including the repair and cache
reads. Different task histories and retries prevent a controlled total-cost
comparison with the earlier runs.

The tested runner/runtime source digest equals the current digest:
`190db136644528803e9ef992e477ab1c4d22dfd71c1613525c5e06fcecff8ac4`.
The first build attempt failed on a registry EOF before any model call; the retry
used the corrected current source. One real-provider host smoke rejected an
inexact Harness citation safely; a subsequent complete smoke passed. Those are
distinct attempts, not an unconditional success-rate claim.

Focused routing/selector tests passed, and the phase-policy/manual-request/model-
freeze group passed 46 checks. The model-freeze fixtures use a nonempty index so
they still exercise selector inference and all later phases. A fresh independent
routing review found no actionable regression. Native offline TUI expansion,
resize, prompt readback and management checks passed again. The final complete
package suite passed **693 tests**; root typecheck, installation verification,
package dry pack and source whitespace checks passed. All owned test containers
were cleaned up after exporting their evidence.
