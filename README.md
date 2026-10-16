# Frad's Pi Packages ![](https://img.shields.io/badge/packages-19-blue)

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

Provides `/matt-pocock`, a persisted Pi v1.0 workflow harness for BDD, TDD, implementation, review, debugging, architecture, research, planning, teaching, skill writing, PR bodies, and session retrospectives.

**Tool:** `matt_pocock_workflow`

**Command:** `/matt-pocock`

**Install:**

```bash
pi install npm:pi-matt-pocock
```

### [`@fradser/pi-monitor`](packages/monitor/)

Runs finite noisy commands against an explicit result contract and reports one structured terminal result. Use `completion="exit"` to confirm exit zero and valid captured JSON after final verification; the default match mode stops on its first terminal match. Pi v1.0 monitor-only UI batches wake asynchronously; mixed batches, codemode and headless calls return the terminal directly. Backpressure, bounded output and exact-value capture aliases limit context; `/monitor` provides scrollable diagnostics.

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

### [`@fradser/pi-loop`](packages/loop/)

Repeats one message into the current session on a schedule. Each repetition is
delivered through the native user-input path, so it is a real user turn rather
than a system note, and it appears in the transcript like any prompt.

**Commands:** `/loop <request>`, `/loop status`, `/loop stop`

State the schedule with flags when you know it. The flag form calls no model:

```bash
/loop --every 5m --times 3 check the build
/loop --every 1h --until "the deploy is green" report deploy status
```

The message may use `{{index}}`, `{{total}}`, `{{remaining}}`, `{{time}}` and
`{{date}}`. A tick whose previous turn has not settled is skipped, never queued,
so a slow turn cannot build a backlog of prompts.

Or write the request in your own words. The cadence, the run limit, the stopping
condition and the repeated text are then chosen by TypeSafe Jev decisions over
candidates the extension builds. A segment that only states how many repetitions
to run is the run limit, never a stopping condition, and it leaves the repeated
message. The cadence is optional: `/loop 输入3次Hi` repeats `输入Hi` three times,
and `/loop 检查项目修改，总结` repeats until you stop it — five minutes apart unless
you state another interval, and the start notice says when it was assumed.
Free requests and `--until` need `TYPESAFE_API_KEY`; without it they are refused
rather than guessed.

Measured against the live service on twelve labelled requests, ten of them
resolved: the interval, the stopping condition and the message were each right in
all ten, and the run limit in all four requests that state a count. The other two
were refused rather than guessed. An eight-hour five-minute loop with a stopping
condition costs about $0.02. Read [the package README](packages/loop/README.md#measured)
for the numbers and for what stays unverified.

**Install:**

```bash
pi install npm:@fradser/pi-loop
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

```bash
pnpm install
pnpm test
pnpm typecheck
pnpm pack:check
# or run all three checks together
pnpm check
```

Each package keeps behavior scenarios in `features/` and tests in `tests/`.

`pnpm check` runs the package and root pytest suites, the extension TypeScript project, and a registry-free packed-manifest check for every workspace package. Use `pnpm check:install` separately to audit the packages in the live Pi settings file.

The test suite requires Python 3 with `pytest` and Bun 1.4.1 for subprocess fixtures. The CI workflows install both runtimes before running `pnpm check`.

The `kit` / `subagents` / `tasks` / `agent-teams` development chain selects the root Pi 1.0.0 cohort explicitly. Published Pi core imports remain `"*"` peers supplied by the host, never runtime dependencies. @features/pi-core-cohort.feature and @tests/test_pi_core_cohort.py check both installed resolution and manifests.

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
