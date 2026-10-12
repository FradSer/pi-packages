# Frad's Pi Packages ![](https://img.shields.io/badge/packages-15-blue)

[![Runtime](https://img.shields.io/badge/runtime-Pi-blue)](https://pi.dev) [![Format](https://img.shields.io/badge/format-pi--package-green)](https://pi.dev/packages)

**English** | [简体中文](README.zh-CN.md)

Native Pi packages for reusable skills, extensions, and workflow commands.

## Packages

### [`@fradser/pi-agent-teams`](packages/agent-teams/)

Compact `agent` delegation and shared `agent_event` communication for Pi. New work starts an independent session, fresh by default or forked from the Leader's context with `fork: true`; final answers return automatically. Work IDs target existing execution. Resident teams, shared tasks, and peer messaging remain available.

`agent start` creates unassigned presence without an initial model turn or fabricated Work ID; the public call awaits native readiness so immediate exact-session assignment needs no caller wait. Later autonomous task claims remain enabled. Recovery releases and reassigns the same Work after authority is actually released, rather than delegating competing duplicate Work.

[Coordination guidance](packages/agent-teams/README.md#coordination-and-delivery) assigns one integration verification owner, binds review evidence to a candidate, and keeps implementation delivery pending until blocking reviews return and findings are resolved. Review-only work ends with its report; bounded rechecks receive an explicitly refreshed candidate brief. These are agent instructions, not a new scheduler or a runtime completion lock.

The bundled [subagent execution layer](packages/subagents/README.md#intent-tools) confirms input at startup and returns answers asynchronously. All children settle to IDLE and accept `send` until stopped or their parent exits. A user-authored disk `agent.md` is the only durable identity; the tool cannot create one or select persistence/Memory/worktree flags. Durable identities have one private data home; scratch directories are ordinary folders, not project checkouts or Git isolation. Copy full `session:` handles. Read-only `inspect` accepts known live or stopped roster entries; process controls remain living-only and never retarget replacements. Tool inputs reject misplaced fields, management readbacks are paged/bounded, codemode receives structured receipts, and cancelling a dispatched tool wait does not end its resident. pi-kit owns passive above-editor activity, without duplicate team rows. Empty, failed or truncated standalone output returns an explicit unanswered follow-up with diagnostics, not a blank review verdict.

**Subagent tools:** `agent_start`, `agent_input`, `agent_stop`, `agent_inspect`, `agent_list`.
Recorded legacy branches retain `agent`. Use explicit identity selection and next/steer input.
See [the intent interface](packages/subagents/README.md#intent-tools) for queue limits and compatibility.

TUI operation rows show readable child names and task previews; exact session/input identifiers appear on expansion. Standalone children remain visible above the editor as `Idle` after returning a result, so their availability for further input stays explicit until they close.

Standalone children can send intermediate updates through `agent_message` when that tool is explicitly granted at startup. Updates carry the child's exact session and current input, appear separately from final answers, and leave the child running. Temporary agents do not gain this capability by default; durable agents also need it in their saved tool ceiling.

Durable child history is separated by parent Pi session and project. Reopening the same parent session restores its own history; different parents share the identity's Memory and scratch while keeping independent conversations. Existing project-only histories remain in place and are not automatically imported.

**Command:** `/agent-teams`

**Install:**

```bash
pi install npm:@fradser/pi-agent-teams
```

### [`@fradser/pi-btw`](packages/btw/)

Answers side questions in a read-only overlay without adding them to the current session history.

**Command:** `/btw <question>`

**Install:**

```bash
pi install npm:@fradser/pi-btw
```

### [`@fradser/pi-context`](packages/context/)

Researches repositories, libraries, and technical questions through an isolated prompt-constrained Pi child process with read, bash, grep, and find tools; its no-modification boundary comes from the research prompt rather than an OS sandbox. Natural-language research requests invoke the tool automatically; the started display wraps the complete query without an ellipsis, while results remain compact and expandable.

**Tool:** `context_get`

**Install:**

```bash
pi install npm:@fradser/pi-context
```

### [`pi-continual-learning`](packages/continual-learning/)

Learning now enforces worker read scope and transaction ownership. Legacy populated scopes bind automatically to the first accessing canonical project; Memory metadata remains untrusted reference context. See the package upgrade notes.

Learns from settled task evidence: Memory retains reusable knowledge and supplies a bounded relevance index before generation; full entries are read when needed. Harness evaluates executable constraints, including Bash confirmation and blocking; skill/text rules provide scoped guidance. Planners propose and the parent validates evidence, privacy, rule cases and ownership before applying changes. `/consolidate` also runs learning explicitly. Installed `policies`/`skillPrompts` retain their protections through read-only compatibility, including existing output/artifact checks.

**Commands:** `/memory` opens Browse memories, Learning settings and Recent learning; `/memory <request>` records an explicit Memory request; `/consolidate` learns from the current task; `/consolidate full` performs full maintenance; `/harness` opens the rules panel; and `/harness <request>` authors a rule in project shared configuration by default.

Automatic Memory, Harness and AGENTS.md still default to applying validated changes. Explicit `/memory` requests remain available when automatic learning is off, are parent-validated, and can produce no write when the request is not durable or safe. Phase policies are under the Memory panel's Advanced section; history entries include Undo. Older `/memory model`, `/memory status`, `/memory policy`, `/memory history`, `/memory undo`, `/memory evaluate`, `/consolidate backfill`, and Harness scope aliases remain compatible.

Learning freezes the task before asynchronous work and stops on shutdown. Invalid learning settings disable automatic learning with a diagnosis. `/memory status` reports effective controls, storage, pipeline and backlog diagnostics. Skipped task references are private and project-scoped; `/consolidate backfill` reports their status without historical replay or model calls. Existing knowledge remains available when automatic learning is off.

Optional Jev judgments use the TypeSafe SDK when `jev` is configured in user-level `continual-learning.json` or `TYPESAFE_API_KEY` is present. Jev selects learning directions and checks validated candidates; the parent retains evidence, privacy, write permissions and Harness enforcement. Unknown or unavailable judgments fall back to the existing selector or save proposals. No new commands. See the [package configuration and evaluation notes](packages/continual-learning/README.md#optional-jev-judgments). See the [bounded improvement acceptance](packages/continual-learning/tests/jev-improvement-evaluation.md) for real bilingual judgments, native learning effects and remaining false holds. The [strict workflow audit](packages/continual-learning/tests/jev-workflow-strict-evaluation.md) distinguishes capability from actual paired improvement. The earlier same-version four-case public native cohort improved 36/50 effects to 50/50, with fourteen gains and no regression; fees increased, and general cross-project superiority remains unverified. The [expanded bilingual and Docker evaluation](packages/continual-learning/tests/jev-expanded-evaluation.md) records new real-project failures and fixes; short-candidate safety gains do not establish improved automatic output on large repository traces. The [latest frozen follow-up](packages/continual-learning/tests/jev-cited-followup-evaluation.md) retains failed Docker rounds and independent Git-option probes: fewer false blocks have not yet established fewer missed constraints or better complete workflows. Complete candidate failures now guide the existing bounded repair without granting partial writes.

Full maintenance extracts new knowledge even with an empty Memory corpus. If the current session has no usable evidence, it may freeze one bounded recent session for the same project and record its source digest. With neither evidence nor existing Memory, it makes zero model calls and reports `no learning input`.

Harness authoring and automatic learning default to project `.pi/harness.json`; `.pi/harness.local.json` is for explicitly requested personal configuration (`/harness --local`). User layers are `~/.pi/agent/harness.json` and project-scoped `~/.pi/agent/harness/<scopeKey>.json`; project layers take precedence. Skill guidance requires a registered skill and its expanded invocation; persistence is not trigger verification or global semantic enforcement.

**Install:**

```bash
pi install npm:pi-continual-learning
```

### [`@fradser/pi-impeccable`](packages/impeccable/)

Loads design guidance for interface polish, animation, typography, color, layout, copy, and browser-based iteration. Loading guidance does not execute scripts or authorize edits.

**Tool:** `impeccable_load`

**Command:** `/impeccable`

**Install:**

```bash
pi install npm:@fradser/pi-impeccable
```

### [`pi-keyboard`](packages/keyboard/)

Controls VIA and QMK keyboard lighting to reflect Pi states, including idle, thinking, unread messages, approval prompts, and fatal errors. Requires a compatible keyboard.

**Command:** `/keyboard`

**Install:**

```bash
pi install npm:pi-keyboard
```

### [`pi-matt-pocock`](packages/matt-pocock/)

Provides `/matt-pocock`, a persisted Pi v1.1.0 workflow harness for BDD, TDD, implementation, review, debugging, architecture, research, planning, teaching, skill writing, PR bodies, and session retrospectives.

**Tool:** `matt_pocock_workflow`

**Command:** `/matt-pocock`

**Install:**

```bash
pi install npm:pi-matt-pocock
```

### [`@fradser/pi-monitor`](packages/monitor/)

Runs finite noisy commands against an explicit result contract and reports one structured terminal result. Use `completion="exit"` to confirm exit zero and valid captured JSON after final verification; the default match mode stops on its first terminal match. Pi v1.1.0 monitor-only UI batches wake asynchronously; mixed batches, codemode and headless calls return the terminal directly. Backpressure, bounded output and exact-value capture aliases limit context; `/monitor` provides scrollable diagnostics.

Optional `compact=true` success reports preserve required data and use native call correlation to avoid repeated metadata. Design experiments found larger savings by grouping related work: a full-payload eight-job codemode batch saved 61.2–76.3% versus separate bash calls, while one grouped bash call was cheaper for all measured small-output workloads. Use the result contract when the task needs it. The [package README](packages/monitor/README.md#design-alternatives-and-adopted-optimization) records alternatives, complete-payload checks, scheduling/deadline differences and package test results. The [injected policy](packages/monitor/README.md#injected-execution-policy) now checks current active tools each turn: codemode is optional, grouped bash is suggested only when available, and direct monitor calls provide the fallback. Capability-specific prompt costs are documented.

The [TUI review](packages/monitor/README.md#tui-rendering-review) adds outcome-specific colors, state-first rows, adaptive activity budgets, value previews with a full-value view, width-aware help and live console refresh without model messages; native terminal checks cover four sizes. [Startup expansion](packages/monitor/README.md#startup-presentation-and-model-boundary) keeps shared Pi styling, prioritizes effective settings and preserves the model-facing acknowledgement.

**Tools:** `monitor_start`, `monitor_stop`

**Command:** `/monitor`

**Install:**

```bash
pi install npm:@fradser/pi-monitor
```

### [`pi-open-deskos`](packages/open-deskos/)

Reports this machine's Pi sessions and their operating events to Open DeskOS over a package-initiated Desk Link, using the same bounded event rules as the runtime's local collector. With a separate control credential it also becomes a Console that lists, launches, attaches to, steers, cancels, ends, and reads the history of the Pi sessions the desk hosts.

**Command:** `/open-deskos`

**Install:**

```bash
pi install npm:pi-open-deskos
```

### [`@fradser/pi-tasks`](packages/tasks/)

A durable work list with four states: pending, in_progress, blocked and completed. Replacements remain historical relations. The four task tools show complete wrapped results by default and list tasks with explicit cursors. Automatic continuation requires new effective work and a runnable task; exhausted allowance waits for input.

[All TUI triggers and examples](packages/tasks/TUI.zh-CN.md).

```bash
pi install npm:@fradser/pi-tasks
```

### [`@fradser/pi-goal`](packages/goal/)

Thread-scoped goal runtime with three tools, authorized continuation and an explicit tool-less completion check. Full TUI bodies and a Codex-style elapsed footer; finished goals are released without archiving.

**Command:** `/goal <objective and completion conditions>`; bare `/goal` shows this thread’s goal. Manage it with `/goal pause`, `/goal resume`, and `/goal clear`.

[TUI rows and trigger conditions](packages/goal/TUI.zh-CN.md) document the complete display lifecycle.

**Install:**

```bash
pi install npm:@fradser/pi-goal
```

### [`@fradser/pi-plan-mode`](packages/plan-mode/)

Runs one minimal read-only Pi subagent via pi-kit, then uses the native TUI to choose implementation in the current or a new session.

**Command:** `/plan <prompt>`, `/plan`, `/plan start`, `/plan exit`, `/plan model [provider/model]`, `/plan review`, `/plan status`

**Install:**

```bash
pi install npm:@fradser/pi-plan-mode
```

### [`@fradser/pi-recap`](packages/recap/)

Displays a concise summary of session progress above the TUI editor and restores it across restarts.

**Command:** `/recap`, `/recap now`, `/recap on`, `/recap off`, `/recap auto`, `/recap model [provider/model]`

**Install:**

```bash
pi install npm:@fradser/pi-recap
```

### [`pi-skill-router`](packages/skill-router/)

Routes to externally hosted skill collections: add GitHub skill repositories through the `/skill-router` menu, exposing selected skills behind a model-visible gateway. Ships no skill content directly.

**Command:** `/skill-router`

**Install:**

```bash
pi install npm:pi-skill-router
```

### [`@fradser/pi-utils`](packages/utils/)

Adds `/effort`, `/continue`, `/sessions`, `/init`, internal private live-session control, and safe Git worktree isolation. Requires Pi ≥0.85.1. Worktree entry settles the old tool batch before switching and resumes edits in the replacement cwd; stale foreign `edit`/`write` paths are blocked.

**Tools:** `enter_worktree`, `exit_worktree`, `list_directory_sessions`

**Commands:** `/effort`, `/continue`, `/sessions`, `/init`

**Install:**

```bash
pi install npm:@fradser/pi-utils
```

### [`@fradser/pi-vision`](packages/vision/)

Bridges images to a configured vision-capable model when the active Pi model only accepts text.

**Command:** `/vision`, `/vision model <model>`, `/vision on`, `/vision off`

**Install:**

```bash
pi install npm:@fradser/pi-vision
```

## Development

Workspace development requires Node.js 22.22.3 or later on Node 22, or Node.js 24.8 or later, matching the official e2e runtime requirement.

```bash
pnpm install
pnpm test
pnpm typecheck
pnpm typecheck:e2e
pnpm test:e2e
pnpm pack:check
# or run all local quality gates together
pnpm check
```

Each package keeps behavior scenarios in `features/` and tests in `tests/`.

### BDD → TDD → E2E

Start with an observable Given/When/Then contract, reproduce a behavior RED, use a focused failing test to drive the smallest GREEN implementation, verify the complete runtime path, then refactor with the affected checks still green. `.feature` files describe acceptance; the existing Python/TypeScript tests execute it. There is no automatic Gherkin conversion. TDD describes the cycle, not a requirement that every test be a pure unit test.

When E2E fails, retain the failing report and trace, then compare the observation with the BDD requirement. For a product defect, add or reuse a focused RED regression, fix the product code, and rerun the affected tests plus real Pi E2E; a subsequent full-suite pass closes the runtime acceptance. For an incorrect test, fix the test against the unchanged requirement. For infrastructure failure, repair the environment and rerun; expected negative outcomes need no product fix. Do not weaken assertions or rewrite requirements to make a result pass, and preserve the original failure beside the repair evidence. Change the BDD contract only when the requested behavior changes. Local fixes follow existing authorization; E2E does not itself authorize production writes or paid calls.

For a new monitor fix, record the failing test and assertion before implementation. A missing dependency or process startup error is a verification blocker, not a behavior RED. The mapping below describes existing tests; it does not claim they were made RED during this documentation change.

| BDD scenario or clause | Existing executable check | Coverage and evidence |
| --- | --- | --- |
| [A real Pi session receives the result of its monitored child command](features/tester-army-e2e.feature) | [monitor-native.e2e.ts](tests/official-e2e/monitor-native.e2e.ts): `real Pi delivers its monitored child result to the original session` | Full headless acceptance: one `monitor_start` and terminal result, stable call identity, success with `DONE_NATIVE`, next request after terminal, one final answer, no duplicate custom message. |
| Same scenario: private progress stays out of returned provider context | Same E2E check, reusing [native-fixture.ts](packages/monitor/tests/native-fixture.ts) | Actual Pi runs a child emitting `PRIVATE_PROGRESS` then `DONE_NATIVE`; the returned tool content must contain the terminal and exclude progress. Native `events.jsonl` and `pi.jsonl` retain the chain. |
| [A mixed tool batch waits for the terminal contract](packages/monitor/features/delivery-boundaries.feature) | [test_monitor_delivery_boundaries.py](packages/monitor/tests/test_monitor_delivery_boundaries.py): `test_mixed_batch_waits_before_the_next_provider_request` | Focused extension/agent-loop regression: the second request sees the terminal and no duplicate message is sent. Its UI-host harness is a different path from the headless E2E case. |
| [Complete records establish the success candidate](packages/monitor/features/exit-completion.feature) | [test_monitor_exit_completion.py](packages/monitor/tests/test_monitor_exit_completion.py): `test_exit_waits_for_complete_records_and_keeps_first_success` | Real-process matching regression: complete records/EOF and first success under `completion: exit`. The native match-mode example uses match completion; it does not verify this exit-mode contract. |
| Same exit-completion feature: exactly-once terminal notification regression | Same test file: `test_exit_first_json_candidate_is_not_replaced_and_delivers_once` | Checks the first JSON candidate, validity and one terminal event per monitor. This supports manager correctness; it does not alone prove delivery through real Pi. |

Run the example from the repository root, without paid models:

```bash
uv run --no-project --with pytest python -m pytest packages/monitor/tests/test_monitor_delivery_boundaries.py packages/monitor/tests/test_monitor_exit_completion.py -q
pnpm typecheck:e2e
pnpm test:e2e --grep 'real Pi delivers its monitored child result to the original session'
pnpm test:e2e
```

For implementation changes, also run affected package tests and the existing typecheck/pack gates. `pnpm check` includes E2E typechecking and the default zero-paid suite before pack validation; the dedicated E2E CI job also retains its reports. Inspect `.e2e/report.json`, `junit.xml`, `summary.md`, failed-case `results/*/trace.md`, and `.e2e/native-monitor-*/events.jsonl`, `pi.jsonl`, `stderr.txt`. Use `--output .artifacts/tester-army-integration/<unique-run>` when preserving successive runner reports: normal runs replace the report/results at their output path. Native monitor evidence stays in its separate unique directory. Keep original failures; do not select a successful retry and omit earlier attempts.

This example proves headless monitor delivery with a deterministic in-process provider. TUI input/resize, RPC dialogs, other concurrency/exit contracts and real-model quality require their own checks. AI evidence classification cannot replace exact assertions or establish code-quality benefit.

The normal project acceptance path is `pnpm check`, with no paid model. [monitor-workflows.e2e.ts](tests/official-e2e/monitor-workflows.e2e.ts) runs the actual project typecheck through real Pi/monitor and checks an isolated invalid TypeScript file returns a located compiler error. Four further cases reject a late nonzero exit, invalid JSON, a deadline after an early success candidate, and a missing sentinel. All reuse the existing [transport fixture](packages/monitor/tests/transport-matrix-fixture.ts), preserving native inputs and output under `.e2e/native-monitor-*`. These are user-facing runtime contracts, not model judgments about logs. A bad source sample is a test input, not a newly discovered project defect; deliberate failing patches establish regression sensitivity only. Former AI experiments are retired; their failures and costs remain historical evidence.

### Choose the acceptance mechanism

BDD specifies observable behavior; TDD drives the smallest implementation with RED → GREEN → REFACTOR; E2E checks the complete runtime boundary. They share the same contract but cover different failure risks. Reuse package tests and fixtures rather than repeating every assertion at every layer.

For deterministic monitor outcomes, run the existing real Pi workflow and exact `expect` assertions directly. An extra `agent.assert` over the same JSON adds no coverage. Current compiler/terminal cases also need no `agent.act`: their commands, scenarios and completion contracts are fixed. No monitor AI scenario currently adds distinct coverage, so the former AI execution/judgment and evidence-classification entries are retired.

Use `agent.act` only when autonomous actions add coverage that fixed interactions cannot reasonably provide. Use `agent.assert` only for a named semantic or visual requirement that exact assertions cannot reasonably express; state its oracle and coverage gap first. Keep deterministic values exact, and do not require an `agent.act → agent.assert → expect` chain for every case. Future paid scenarios require explicit authorization and retry-inclusive budget reservations.

### Complete integration scenario mapping

The following lists every scenario in [tester-army-e2e.feature](features/tester-army-e2e.feature). Feature tags are documentation only; they do not select tests in the official runner.

| Scenario | Executable or verification | Status/boundary |
| --- | --- | --- |
| Default CI execution retains actionable reports without paid calls | [e2e.config.ts](e2e.config.ts), [e2e.yml](.github/workflows/e2e.yml); inspect runner reports and a hosted workflow upload | Manual CI acceptance. Local CI-mode runs prove report generation; hosted artifact upload remains unverified until that workflow runs. |
| Valid isolated package settings pass the real CLI audit | [installation.e2e.ts](tests/official-e2e/installation.e2e.ts): `complete workspace settings pass the installation CLI` | Default zero-paid E2E. |
| A dead source is reported as a failing audit | Same file: `dead package sources fail with a located diagnostic` | Default zero-paid E2E; an expected bad installation is a passing negative test. |
| A real Pi session receives the result of its monitored child command | [monitor-native.e2e.ts](tests/official-e2e/monitor-native.e2e.ts): `real Pi delivers its monitored child result to the original session` | Default zero-paid headless match-mode acceptance. |
| A real Pi startup failure retains subprocess diagnostics | Same file: `real Pi startup failures retain subprocess diagnostics` | Default zero-paid regression; retains stdout/stderr even when Pi rejects the provider, then removes temporary settings. This verifies diagnostic retention, not successful monitor execution. |
| Real Pi confirms finite verification outcomes through monitor | [monitor-workflows.e2e.ts](tests/official-e2e/monitor-workflows.e2e.ts): `real Pi confirms a successful project typecheck`; `real Pi returns located compiler errors for a failed verification` | Default zero-paid real compiler workflows; success JSON and located TS2322 failure. |
| Real Pi does not mistake intermediate output for completed verification | Same file: `real Pi rejects a success sentinel followed by a nonzero exit`; `real Pi rejects malformed JSON completion`; `real Pi reports a deadline after a success candidate`; `real Pi rejects a zero exit without its required result` | Default zero-paid exit-mode terminal and returned-content checks; does not cover TUI/RPC. |
| Deterministic monitor acceptance has no model entry point | [test_official_e2e.py](tests/test_official_e2e.py): `test_deterministic_monitor_acceptance_has_no_model_entry_point`; `test_developer_docs_have_one_complete_integration_section` | Zero-paid root pytest; checks active scripts/configuration/dependencies and scenario mapping. |

Official [tester.army/e2e](https://e2e.tester.army/docs) CLI checks run with `pnpm test:e2e`; typecheck them with `pnpm typecheck:e2e`. The pinned runner uses an engine-less target and exact assertions against the installation audit CLI, with temporary settings only. No model, API key, browser, custom engine, or adapter is configured. Read @.agents/skills/e2e/SKILL.md before changing these tests. Reports are written to `.e2e/` (ignored by Git); use `pnpm test:e2e --reporter list,junit,markdown --trace on` to retain trace pages. The suite also runs the real workspace Pi CLI with the existing offline monitor fixture: monitor_start executes a real child, delivers its terminal to the original session once, and keeps progress out of returned provider context. Each invocation uses disposable HOME/agent settings and retains native JSONL evidence in `.e2e/native-monitor-*`. The fixture provider is deterministic and in-process; this proves headless monitor delivery, not TUI/RPC, remote-model behavior, or general AI testing benefit. Adding model-powered steps requires separate authorization.

@e2e.config.ts emits JSON, JUnit and Markdown reports by default and retains failed-attempt traces. The stable project ID identifies deterministic CLI checks. One worker and zero automatic retries are deliberate for isolated, reproducible checks; the official cache defaults remain unchanged. @.github/workflows/e2e.yml runs typechecking and only the zero-paid suite on PRs, main pushes and manual dispatch, using Node 26 and the frozen lockfile. The read-only job retains free reports and native evidence for seven days, including on test failure; it has no model credentials. This follows the official [configuration reference](https://e2e.tester.army/docs/reference/config) and [CI guidance](https://e2e.tester.army/docs/ci/github-actions).

Historical AI experiments are described in [monitor E2E AI history](docs/history/monitor-e2e-ai.md). Original sources, frozen protocols, failed reports, inputs and cost ledgers remain in local ignored artifacts; they are not collected by pytest, TypeScript or the official runner. Removing redundant active tests does not turn those failures into passes or release their conservative reservations. No historical quality-gain claim is made.

`pnpm check` runs the package/root pytest suites, extension/E2E typechecks, the default zero-paid official CLI E2E suite, and registry-free packed-manifest checks. Use `pnpm check:install` separately to audit the packages in the live Pi settings file.

The test suite requires Python 3 with `pytest` and Bun 1.4.1 for subprocess fixtures. The CI workflows install both runtimes before running `pnpm check`.

The development and verification baseline is Pi **1.1.0**. Workspace overrides lock the core version, including automatically installed peers; the cohort regression checks actual resolution from all 18 packages declaring Pi peers. Published Pi core imports remain `"*"` peers supplied by the host, never runtime dependencies. @features/pi-core-cohort.feature and @tests/test_pi_core_cohort.py check both installed resolution and manifests.

Use `pnpm --dir packages/<name> pack --dry-run` to inspect one package's contents before publishing.

Shared runtime helpers live in the internal [`@fradser/pi-kit`](packages/kit/) package. It is an internal workspace dependency and is not installable via `pi install`; it declares no `dependencies`, only the host-provided Pi core packages it uses as `"*"` peers. Its lifecycle renderers show expansion hints only for supplementary display content or text hidden at the current width—not merely because tool results contain metadata. Consumer packages omit details that repeat the title while preserving full reports and actionable diagnostics.

## Adding a package

1. Create `packages/<name>/`.
2. Add a `package.json` with the `pi-package` keyword and an explicit `pi` resource manifest.
3. Include runtime resources in `files` and declare imported Pi core packages as peer dependencies.
4. Write the BDD scenario under `features/` before implementation, then add executable tests.
5. Add a Changeset for a released package change.

## Publishing

Releases use Changesets and the GitHub Actions workflow in `.github/workflows/release.yml`. Pull requests and releases run `pnpm check` before release actions; the root `pnpm run publish` command runs the same gate before its local release script. Push changes to `main`, then merge the generated version PR. The workflow publishes the explicit package list through npm Trusted Publishing, in dependency order, and skips exact versions already present in the npm registry.

New packages require one manual first publication and npm Trusted Publishing configuration before later versions can be released by GitHub Actions.

## License

Each package is licensed under MIT.
