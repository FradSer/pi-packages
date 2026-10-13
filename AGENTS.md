# Repository Guidelines

## Project Structure & Module Organization

Packages live in `packages/*`, with `index.ts` loading `src/` or `extensions/`.
Directories differ from npm names: `continual-learning`/`kit` publish
`pi-continual-learning`/`@fradser/pi-kit`. List bundled Markdown, templates,
and scripts in manifest `files`. Package/root `features/` and `tests/` hold
contracts and checks.

## Build/Test/Development Commands

```bash
pnpm install
pnpm test
pnpm typecheck
pnpm pack:check
pnpm check
```

`pnpm check` requires Python 3 with pytest and Bun 1.4.1 and runs
package/root tests, the extension TypeScript project, and registry-free
packed-manifest validation. CI installs both runtimes before this command.
Focus: `python3 -m pytest packages/<name>/tests/ -q`.
Pack: `pnpm --dir packages/<name> pack --dry-run`.
SDK example: `pnpm example:sdk`. Pi loads TypeScript without a build step.

## Coding Style & Naming Conventions

Use strict ESM TypeScript (ES2022; Node ≥20), kebab-case modules, snake_case
tools. No formatter/linter is configured; match local style. Edit dependencies
through pnpm. Extensions declare
`"pi": { "extensions": ["./index.ts"] }`; Pi-core/TypeBox imports are peers.
List bundled non-TypeScript files (Markdown, templates, scripts) in manifest `files`.

## Shared Runtime: pi-kit

Prefer internal `@fradser/pi-kit` for shared helpers/infrastructure:
`"@fradser/pi-kit": "workspace:*"` under `dependencies`, never `peerDependencies`.
If absent, record the gap; invent no replacement or unverified registry dependency.

## Testing Guidelines

Start behavior changes with Given/When/Then `.feature` scenarios, then RED,
GREEN, refactor. Keep `test_*.py` and Node/tsx harnesses in `tests/`; run
both suites and tsc. Runtime changes require `pnpm check:install` and
live `pi --print` verification; test TUI interactively. Package moves must
update installed paths in `~/.pi/agent/settings.json`.

## Real Pi Terminal Verification

For TUI changes, run the actual `pi` CLI in an interactive terminal or a PTY.
Renderer/unit tests and `pi --print` do not prove input ownership, viewport
composition, focus, navigation, or resize behavior.

- Use a disposable cwd and agent directory with isolated `HOME` and
  `PI_CODING_AGENT_DIR`. Keep user settings, credentials and package installation
  unchanged. For offline fixture runs, use a deterministic local provider,
  `PI_OFFLINE=1`, and disable unrelated extensions, skills, prompt templates,
  themes, context files and built-in tools; load only the fixture extension.
  Isolation flags are test conditions, not production defaults.
- Spawn `pi` through `pty.openpty()` (or the existing interactive terminal).
  Set dimensions with `TIOCSWINSZ`; resize the same live component and send
  `SIGWINCH`. Exercise 120x40, 48x24 and a short-height case such as 48x12.
  Do not recreate a component and call that a live-resize test.
- Send actual terminal key bytes through the PTY: arrows, Enter, Escape,
  Ctrl-C, Ctrl-O and PageUp/PageDown. Include SS3/CSI variants for custom key
  handling. Synchronize on lifecycle/menu/render events and input release;
  drain output before capture. Fixed sleeps are not acceptance conditions.
- Walk complete paths: command entry, empty/loading/error states where present,
  long lists, list ends and navigation actions, full-body start and tail,
  search input, detail close, parent return, retained selection, and exit.
  Check meaningful labels and essential actions remain readable, not merely
  that rendered lines fit. Check resize preserves the logical reading position.
- Retain raw PTY bytes, terminal dimensions, ordered interactions and structured
  renderer events. Inspect the composed terminal screen as well as component
  lines. ANSI-to-text alone loses cursor placement, color and occlusion; use a
  terminal-state parser for captures and keep its resize sequence. Label images
  reconstructed from terminal bytes as reconstructions, not OS screenshots.
  Record source revision/local changes and capture provenance; never retain
  authentication values or private user data in evidence.
- Distinguish evidence: real CLI + deterministic fixture proves native display
  and interaction only; real-model/service learning and persistent mutations
  require separate acceptance. Test RPC with actual `--mode rpc` requests and
  `extension_ui_response` dialogs; native custom UI is unavailable there.
  Report unverified screen-reader, physical-terminal/theme, service and mutation
  cases explicitly. Never weaken validation to obtain a green result.

When auditing continual-learning TUI, use
@packages/continual-learning/tests/live_meaningful_details.py for native
print/interaction acceptance and
@packages/continual-learning/tests/tui_showcase.py with
@packages/continual-learning/tests/tui-showcase-fixture.ts for terminal captures
and RPC dialog evidence. From the repository root:

```bash
uv run --no-project packages/continual-learning/tests/live_meaningful_details.py
uv run --no-project --with pyte --with pillow python packages/continual-learning/tests/tui_showcase.py /tmp/continual-learning-tui-cases
```

Inspect the showcase `manifest.json`, PNGs, `.txt`, `.ansi`, `events.jsonl` and
`rpc-dialogs.json`. The showcase uses actual product components with isolated
fixture data; it does not perform real undo, policy writes or remote learning.
After a user reloads Pi, also reproduce the reported case in that reloaded
session; an isolated process is not evidence that their session loaded the fix.

For first-use Harness authoring, run
@packages/continual-learning/tests/live_harness_first_run.py with a disposable output
parent. The offline provider exercises rejected preview, corrected preview, one
complete write, readback and fresh-session revision delivery. `--real-model`
repeats the original `/harness 避免后续 D0 的流量被打爆` request with the configured
provider and records every call and reported cost without accessing D0. Admit
`harness_preview` explicitly when using a CLI tool allowlist; the command activates
this read-only tool and authoring completion removes it. Keep plain positive,
unrelated-action, same-action/different-resource and near-name negatives. A
syntax-valid selector, saved file or delivered guidance alone does not establish
scope correctness or enforced traffic limits. Preserve failed runs, including
acceptance withdrawn after stronger counterexamples; never broaden the filesystem
allowlist or remove failing cases to manufacture a pass.

For intermittent AGENTS learning failures, use
@packages/continual-learning/tests/live_agents_reliability.py with `--full-pipeline`.
Retain actual planner-child transport, receipts and before/after documents in
disposable roots. A successful retry does not identify an earlier failure's
cause. Check that every required dossier read is actually authorized, rather
than inferring it from a final applied outcome. Receipt diagnostics must use
parent-controlled categories, never arbitrary child stderr or model output.
For large repair contexts, also run
@packages/kit/tests/test_large_worker_prompt.py. Native Pi stdin trims boundary
whitespace; prove exact prompt delivery through the actual CLI, not only a fake
stdin reader. Reproduce Linux argument-limit failures with the original frozen
evidence before changing transport; reducing evidence is not a transport fix.

For downstream Memory claims, use
@packages/continual-learning/tests/live_real_project_memory.py and its frozen
@packages/continual-learning/tests/real_project_tasks.py protocol. Run
`--preflight-only` before real calls. This Docker study enables Jev only in its
isolated configuration, learns from real source work, and starts fresh sessions
with identical post-training code. Hidden checks enter containers after model
execution. Preserve failures and ties; invalid training must stop downstream
tasks. Small authored feature tasks on previously used public projects do not
establish broad model capability or production benefit.
After a confirmed learning runtime fix, `--resume-from <prior-cohort>` may reuse
verified real source observations instead of repeating the audit. Keep the
original project/model/protocol and source hashes, use the existing `continue`
contract. For a summary-only continuation, replace the parent tool allowlist with
`--no-tools`; a prompt-only ban can loop, and combining it with `--tools` reopens
those tools. Independent learning workers keep their own explicit authorization.
Require `originalObservationsPreserved=true` in the actual learning
dossier. A new substantive summary request starts a new task slice and is not
proof that old tool evidence was reviewed. Record failed cohorts, cumulative
resumed usage and the changed protocol; never seed Memory or future answers.
For citation failures, compare raw dossier entries with the frozen snapshot before
assuming an offset bug. Incremental Memory model inputs label each unchanged entry
with its original `snapshotIndex`; validate against raw evidence, not the display
projection. For long encoded verifier-line citation changes, also run
`uv run --no-project packages/continual-learning/tests/live_memory_citations.py`.
It drives actual Pi 1.0 scoped reads with a deterministic local provider and
checks complete chunk reconstruction, exact parent extraction and unchanged
source. This proves the citation interface only, not model selection or learning
effectiveness; keep failed whole-line/partial-quote plans rejected.
For Jev bounds, measure the fully encoded wire request, retain the
rejection, and never trim original evidence or lower thresholds to manufacture
a valid experimental arm.
For private Memory maintenance, run
@packages/continual-learning/tests/live_private_memory_consent.py with a disposable
output parent. It exercises actual workspace Pi `/memory 整理记忆` through native
PTY cancellation and an id-bound RPC refusal, with external requests forbidden.
Require zero planner runs, unchanged Memory and unchanged privacy configuration.
Controlled consent/write tests establish authorization wiring only; actual private
model review requires explicit human permission for that data and service. Never
reuse public-project experiment consent for a different private project.

For explicit maintenance source collection, parent-provided complete old bodies
are untrusted verification questions, never independently observed facts. Keep
them out of appended source evidence and the collector's source read scope. Bind
their safe revisions before writes; source-only post-apply checks must permit
the plugin's own authorized corrections.

For Memory maintenance bounds, replay the actual rewrite/delete mixed plan and
its frozen selected predecessor bodies; a create-only test does not cover this
path. Verify every original entry is reviewed, including final revocations.
Normal project learning delegates request capacity
to the configured service without a local request-byte cap. Historical bounded
studies must explicitly retain their original `maxRequestBytes` and transport
bound; record an authorized protocol change separately, preserving prior failures
and costs. Removing a local capacity gate does not establish semantic acceptance
or learning benefit. Preserve each historical study's count limits. Normal mutation
review explicitly uses at most 32 candidates and 16 complete windows plus support
and novelty, or 576 prepared requests; record this separately from the old
68-request bound. Keep deadlines and 0.9/0.8 thresholds unchanged.
Mutation reviews require operation/preservation intent,
exact old bodies and same-plan replacement bodies; none of that state authorizes
the mutation. An all-positive offline judge proves framing and coverage only.

For a learning/history/undo acceptance request, also run
@packages/continual-learning/tests/live_learning_history_undo.py:

```bash
uv run --no-project --with pyte --with pillow python packages/continual-learning/tests/live_learning_history_undo.py /tmp/continual-learning-full-path
```

This drives the real Pi CLI, planner children, parent validation and file writes,
then native history/detail menus and undo confirmation in one disposable project.
Each invocation creates a new private run directory under the supplied output
parent and prints its `outputDir`. Inspect that directory, not an older sibling.
The runner uses the installed workspace Pi CLI and records its version, so a
global CLI upgrade cannot silently change the compatibility baseline. It checks
isolation before spawning Pi, snapshots source hashes at startup,
refuses a pass after source drift, and automatically writes a manifest, run log
and gallery on success or failure. Freeze implementation before the final run;
stabilize deterministic acceptance and obtain required independent review before
calling a real provider. Re-run checks only for affected changes or unresolved
failures. Dialog evidence must match the current dialog id and event offset.
It also resizes the same history list between 120 and 48 columns and checks that
applied and undone statuses remain readable.
Its loopback provider is deterministic; explicitly disable Jev in the disposable
agent configuration and whitelist inherited environment variables to keep remote
services out of this offline run. Verify rendered results against receipts,
history targets and actual bytes. Bind cancellation evidence to the current
dialog; undo every applied record in reverse order, including index bootstrap
records. Compare predecessor bytes, permissions and missing files, retain undone
history and the original receipt, and preserve unrelated files. Inspect
`manifest.json`, `snapshots.json`, `receipt.json`, both history JSON files,
`events.jsonl`, raw terminal bytes and reconstructed images. This proves the
learning/undo mechanics with controlled plans; report real-model learning and
remote semantic review separately.
The optional `--real-model` flag runs the same native path with the configured
real provider for Memory only, copying auth into the disposable agent directory
with private permissions. Use it when real-service verification is authorized;
it may incur model usage. It retains synthetic receipts and terminal evidence,
never credentials. Jev remains disabled, so this does not verify remote semantic
review. A failed real-model receipt remains a failure, separate from loopback
acceptance.



## Extension Architecture

- Activate state-dependent tools with `pi.setActiveTools()` only after valid
  transitions; remove on exit/invalid restore. Results identify state,
  synchronous outcome, pending intent, and next actor.
- Use pi-kit lifecycle renderers, `renderShell: "self"`, and empty `renderCall`.
  Prefer direct APIs, bounded/sanitized output, abort propagation, and explicit
  headless/missing-auth handling. Shared worker JSON uses atomic tmp+rename.
- UI reference: @packages/btw/src/overlay.ts. `ctx.ui.custom` owns input;
  widgets stay passive, width-bounded, spinner-aligned. Never intercept global
  terminal input.
- Workflow menus are commands; routing uses `before_agent_start`. Do not
  register custom user-interaction tools (`gh_confirm`, `git_ask_name`); use
  TUI menus, slash commands, or native prompts instead.
- Flow/procedure starts are abstract lifecycle lines, never full-text dumps:
  send the procedure via `pi.sendMessage({ customType: "<pkg>-procedure",
  content, display: true, details }, { deliverAs: "followUp", triggerTurn:
  true })` and render it with `pi.registerMessageRenderer` as one
  `[<pkg>] started · <subject>` row (bold `customMessageLabel` prefix,
  `safeDisplayText` subject). Tool starts render the same shape through
  pi-kit lifecycle renderers in `renderResult`. Full content stays in LLM
  context; the transcript shows only the line. Reference:
  @packages/impeccable/src/index.ts, @packages/matt-pocock/src/index.ts.

## Task Records

Record work in `packages/tasks` when a request has several steps or several
files, or when the work outlives the turn. A single edit is not a task.

- `create_task` records the work, its `dependsOn`, and its completion gate.
- `update_task` moves it: `in_progress` takes it, `completed` delivers it with
  its evidence, `pending` reopens it. One call may carry both a content edit and
  a status change; a refused status keeps the edit.
- `get_task` reads one task in full. `list_tasks` reads the list.

A goal is not a task. A goal is one objective that keeps running until it is
met. A task is one unit of work in a list you order, take, and finish.

The task tools do not reach a child process. A subagent cannot take or complete
a task, so the leader records the outcome from the child's report.

## Decision Boundaries & Completion

- **Autonomous local work**: Contributors and agents are authorized to modify
  package code, add or adjust tests/features, and fix failures caused by
  requested changes without intermediate sign-off.
- **Explicit approval required**: Publishing packages to npm, modifying remote
  git branches, and destructive operations (force push, worktree deletion)
  require explicit user confirmation.
- **Verification & Stopping Conditions**: Local work is complete when the
  target package's tests pass (`python3 -m pytest packages/<name>/tests/ -q`),
  type check passes (`pnpm typecheck`), and `pnpm --dir packages/<name> pack --dry-run`
  confirms manifest packaging. Do not halt for review before completing
  verification.

## Commit & Pull Request Guidelines

Use @.git-agent/config.yml Conventional Commit scopes (`feat(mp):`, `fix(mon):`).
Commit via git-agent with `session_context` intent, exact staging, `--no-stage`;
never bare git add/commit. No PR template: describe packages, behavior,
verification, release impact. Update both READMEs for package/install changes.

Published changes require Changesets; CI versions/publishes after the version
PR merges. Keep @scripts/publish-release.mjs's explicit allowlist pi-kit-first
and packed manifests free of `workspace:` protocols.

## Memory

Search before adding decisions. Keep safe `.memory/` files byte-identical with
canonical `~/.pi/agent/memory/<escaped-cwd>/`; private entries stay private.
Use `name`/`description`/`type` frontmatter, **Why**, and **How to apply**.

For continuous-learning effectiveness, use
@packages/continual-learning/tests/live_continuous_project_learning.py and the frozen
@packages/continual-learning/tests/continuous_project_tasks.py protocol. Run
`--preflight-only` first. It resets disposable project/agent state, never seeds
Memory or Harness, converges source bytes before each paired fresh-session task,
and preserves actual learned state only in the learning arm. Hidden probes enter
after model exit and are removed before the next task. Source convergence is an
experimental intervention, not independent project evolution. The standalone version-execution instruction belongs only in correction and retirement
tasks; a conditional shared instruction caused both orientation models to execute it
prematurely and is retained in the earlier cohort. Record invalid
learning, task failures, explicit recovery, all known leader/learning/Jev usage and
unknown interrupted costs; never turn one sequence into a broad capability claim.
Freeze implementation and obtain required independent review before paid calls.
When other tasks share the checkout, use a byte-verified, read-only copy of the
complete runtime and study sources for both imports and runtime image creation.
Run preflight against that same copy and retain its source hashes; do not waive
source-drift failures or treat them as evidence of a learning benefit.
Bind paid admission to the exact preflight run and wrapper digest. A no-call
preflight must enforce a zero transport budget. Acquire exclusive budget
ownership before reading the cumulative ledger, and preserve reservations on
uncertain interruption rather than reusing unaccounted requests.
The continuous protocol permits one bounded explicit backfill after initial learning
if pending, retaining the original failures and recovery cost; invalid learning
then stops dependent tasks. Read actual backlog status rather than inferring pending
work from attempt files. On interruption retain sessions and ledgers before removing
owned containers; known summaries may be incomplete, and missing usage is unknown.
The revised study loads @packages/continual-learning/tests/continuous-tool-budget.ts
only in each arm's parent task process: eighteen admitted calls, then an empty
active tool set; excess in-flight calls are blocked and make the task fail. This
experimental resource intervention is identical in both arms, preserves original
observations in the same session, and does not constrain independent learning
workers or explicit backfill. Retain prior prompt-only-budget cohorts and disclose
the changed protocol. Verify the empty next-turn tool set through the actual Pi
CLI with @packages/continual-learning/tests/test_continuous_tool_budget.py before
paid calls; do not treat prompt wording alone as a hard budget.
For requested version-permission checks, match the standalone `npm --version`
call to a unique successful actual Bash result with a version. Attempts, assistant
claims and a later pure rule-engine probe cannot satisfy the task. Record the
complete common prompt and this stricter protocol separately from prior cohorts.

Continuous coverage version 2 adds a sixth real wrapper-maintenance task after
Memory correction. Actual failed verification is read once from a complete,
source/session-bound file through `continue` in the original session, with only
one read available in both arms; this is observed evidence, never seeded Memory
or user authorization. One explicit bounded backfill may process this failure,
retaining the failed task and all added costs. Require exact acknowledgment
SHA256 of JavaScript `JSON.stringify(receipt)`, the receipt's parent mutation batch
in applied history, and subsequent consumption of the changed knowledge. A
zero-operation acknowledgment proves processing only. Require independent Jev
old/new Memory versus complete current source auditing at unchanged thresholds
and later exact-revision delivery for correction coverage. Missing coverage is
`incomplete-coverage`, even if all task processes exit. The experimental audit is
read-only and its real service usage belongs in cumulative costs.

For same-task failure feedback, inspect actual pending backlog ranges and the
`input.backlogCoverage` of replay receipts. Only independently digest-verified,
byte-identical prefix extensions may share one learning call; a new substantive
task or changed source cannot be substituted. Preserve each original failure and
one cost-bearing receipt. Exercise acknowledgment crashes before any sibling,
between siblings, and before the receipt owner, plus recovery before older retry
selection. A truncated replay must retain omission metadata and its existing
proposals-only policy. Empty pending counts alone do not establish learned benefit.

For continuous-study failure feedback, the one admitted read must target the exact
source/session-bound verifier file without offset or limit. Enforce that boundary
in the parent tool handler; `--tools read` alone permits unrelated source reads.
Retain rejected calls and their costs, and stop repeated boundary violations.
Preserve earlier cohorts that lacked this enforcement as failed evidence.

A failed feedback summary is still a failed task; it need not invalidate an
already complete, safely observed failure. Before independent backfill, use
@packages/continual-learning/tests/failure-observation-proof.ts to verify the
actual full read, immutable session prefix, source/log bindings, rejected-tool
results and complete pending slice. A retained zero-tool diagnostic must remain
in the longer slice; do not rewind to omit it or retry the parent summary.
For standalone recovery, use
@packages/continual-learning/tests/recovery_integrity.py: claim the exact failed
slice once with an immutable exclusive parent marker before paid calls, keeping
that claim on failure/interruption. Verify every owner history chain and actual
endpoint across private/public/project roots, including permissions and changes
that return to their original bytes. These checks admit evidence only; task
success, valid learned changes and downstream benefit remain separate claims.


Continuous coverage version 3 uses index-only Memory discovery and permits both
arms to read only Memory paths declared by the plugin. Record actual unique,
successful read calls and result hashes; require equality with retained learned
file revisions for Memory exposure and correction coverage. Partial reads,
truncation notices, index rows, and legacy injected bodies do not satisfy this
version. Read exposure is not adoption or task benefit; keep the hidden behavioral
outcomes and cumulative costs separate. Preserve older version 2 cohorts and
disclose this protocol change before new real calls.
