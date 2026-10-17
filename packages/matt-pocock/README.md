# pi-matt-pocock

`pi-matt-pocock` provides one `/matt-pocock` menu and a catalog-backed capability gateway for engineering workflows and focused procedures adapted from `mattpocock/skills`.

## Installation

```bash
pi install npm:pi-matt-pocock
```

## How It Works

`/matt-pocock` starts or manages persisted workflows and runs standalone capabilities. A single `procedureCatalog` manifest classifies bundled resources as workflow procedures, standalone capabilities, references, or assets, and defines their dependencies, disclosures, workflow placement, and legal transitions.

The command takes `<route|capability> [task]`, mirroring `/impeccable <capability> [request]`: the first word selects, the rest is your own task, and that task is carried into the procedure prompt and shown in the transcript row. `status` reports the active work item, `transition [target]` moves to a catalog-legal next procedure, `complete` closes it, and `cancel [reason]` records why. An input whose first word matches no route, capability, or action is forwarded verbatim for autonomous routing and supersedes any active workflow; the task itself is never written into the persisted workflow record.

The package enforces strict engineering disciplines adapted for coding agents:
- **BDD-first verification**: Executable Gherkin (`Given`/`When`/`Then`) scenarios in `.feature` files define acceptance criteria before coding.
- **Two-axis code review**: Independent evaluation along the Standards and Spec axes, sealed with a mandatory **Refute-before-PASS** red-team verification protocol.
- **AI slop elimination**: Dedicated detection and refactoring of fabricated evidence, evidence widening, defensive clutter, mock patching, and vacuous names.
- **Tracer-bullet vertical slices**: Tasks cut completely through schema, API, UI, and test layers; wide refactors sequence via expand-contract.
- **Autonomous progression (AFK)**: Non-user-owned next steps advance automatically without redundant permission prompts; user prompts are reserved for genuine design decisions.

Procedures remain internal Markdown resources; the package ships no child `SKILL.md` files, so generic names such as `tdd`, `research`, and `code-review` do not become globally discoverable skills.

## Progressive Tool Disclosure

Tools are progressively exposed based on active session state:

1. **Baseline tool**: `matt_pocock_workflow`
   - `mode: "workflow"`: Start an engineering workflow route (`idea-to-ship`, `wayfinding`, `triage`, `hard-bug`, `architecture`).
   - `mode: "capability"`: Run a model-reachable standalone capability without persistent workflow state.
   - `mode: "reference"`: Load a reference disclosed by a standalone capability.
2. **Active-only tool**: `matt_pocock_active`
   - `action: "transition"`: Advance the workflow to an allowed next procedure.
   - `action: "load"`: Load an on-demand reference disclosed by the current procedure or loaded dependencies.
   - `action: "complete"`: Formally complete the active workflow and release state.
   - `action: "cancel"`: Cancel the active workflow with an explicit reason.
3. **Active-only tool**: `matt_pocock_ask`
   - Prompt the user for structured, genuinely user-owned decisions with selectable options.
   - Requires a recommended choice and adopts it when the deadline elapses; supports custom text input. One deadline governs the ask and dismisses both the selector and the custom-answer input; elapsed clock readings alone never imply a timeout. Escape, cancellation, abort, no UI, and a blank custom answer leave the decision pending. Recommendations must match an offered option, so an approval-required action recommends the option that does not act.

## Pi v1.0 runtime boundaries

This extension targets Pi v1.0 (`@earendil-works/pi-*`). Each extension instance owns its workflow state. Session start, tree navigation, and context compaction silently restore the active branch's complete procedure context; subsequent transitions deliver only new bodies. Malformed or incompatible newest records disable workflow-only tools rather than resurrecting older work. Restored phases must match the catalog placement.

Workflow changes and session boundaries dismiss pending questions and menus. A late selection cannot act on a replacement work item. Invalid arguments to `status` or `complete` report usage without cancelling the active work.

Standalone reference loading remembers the current capability's disclosure chain in memory, so a reference can disclose further references without creating workflow state. This chain resets when the capability restarts or the session context changes. Standalone procedures ask decisions in conversation rather than relying on workflow-only tools.

The catalog is validated before tools are registered, including alias conflicts, duplicate route placements, and required dependency cycles. A cumulative reference bundle is validated against the 64 KiB limit before state is persisted. Dialog cancellation propagates to Pi UI and native subprocesses; native process failures fall back to Pi UI.

## Workflow Routes & Graph Topology

Each workflow operates as a state machine governed by `src/catalog.json`. Graph reachability is validated automatically at test and startup time, ensuring no orphaned or unreachable procedures exist.

### 1. `idea-to-ship` (Shaping to Delivery)
- **Entry**: `grill-with-docs` (`shaping`)
- **Key Flow**:
  - `grill-with-docs` ⇄ `grill-me` (flexible documentation-driven or conversational interview)
  - `research` ⇄ `prototype` (bidirectional exploration loop)
  - `to-spec` → `to-tickets` → `implement` ⇄ `code-review` → `handoff`

### 2. `wayfinding` (Exploration Under Uncertainty)
- **Entry**: `wayfinder` (`mapping`)
- **Key Flow**:
  - `wayfinder` maps decisions onto an issue tracker map.
  - `research` ⇄ `prototype` (bidirectional investigation loop linked back to map tickets)
  - `to-spec` → `to-tickets` → `implement` ⇄ `code-review`

### 3. `triage` (Incoming Request & Issue Triage)
- **Entry**: `triage` (`triage`)
- **Key Flow**:
  - `triage` classifies requests into bugs or enhancements and generates durable agent briefs.
  - Transitions into `to-spec` or `to-tickets` → `implement` ⇄ `code-review`

### 4. `hard-bug` (Diagnostic Feedback Loops)
- **Entry**: `diagnosing-bugs` (`feedback-loop`)
- **Key Flow**:
  - Build minimal reproduction and tight red-green feedback loop before forming hypotheses.
  - `diagnosing-bugs` → `implement` ⇄ `code-review`
  - **Diagnostic Return**: `implement` and `code-review` can transition back to `diagnosing-bugs` if a hypothesis is refuted or a new root cause emerges.

### 5. `architecture` (Deepening & Codebase Design)
- **Entry**: `improve-codebase-architecture` (`survey`)
- **Key Flow**:
  - `improve-codebase-architecture` surveys friction and publishes an interactive HTML candidate report.
  - `improve-codebase-architecture` ⇄ `codebase-design` (formal Architecture Design review of interfaces and deep modules).
  - Transitions into `implement` ⇄ `code-review`.

## Coordinated implementation and review

Implementation assigns safe local checks to each contributor and shared verification to one integration owner. After integration, name a candidate revision or scoped snapshot; review and final checks must judge that same candidate. Keep unrelated dirty work outside the review baseline, include untracked task files, and invalidate affected evidence when the candidate changes.

Code review retains separate Standards and Spec verdicts, but a bounded change can use one fresh reviewer for both. Separate reviewers are appropriate for distinct expertise, larger scope, or repository policy—not mandatory for every task. Confirmed conversation requirements and acceptance scenarios can serve as the spec for an uncommitted task.

A completed review assignment is not an implementation PASS. A standalone review or bounded reviewer returns its report, including REWORK, without editing the implementation or waiting for repairs. The Leader or implementation owner groups findings by root cause and owns remediation and delivery.

Before a recheck, preserve the prior report and supply the retained baseline, new candidate fingerprint, correction delta, prior findings and safe checks. Agent Teams reopen/assign does not refresh a fixed description or forward the cleared result. Reuse completed review Work only when its description already points to an authoritative current-attempt brief; update that brief before reopening/assignment. Otherwise create bounded follow-up Work with the refreshed description and a dependency on the completed review. This linked recheck is not a new broad review; broaden only for changed scope or risk.

Complete implementation delivery only after required reports arrive, blocking findings are resolved, and applicable verification covers the final candidate. If only required results remain outstanding, yield with the workflow active instead of announcing completion.

These are agent instructions, not a new runtime scheduler or an enforced dependency on Agent Teams. The workflow state format and completion tool contract are unchanged.

## Standalone Capabilities

The following curated capabilities are reachable via `matt_pocock_workflow` (`mode: "capability"`) without initiating persistent workflow state:

- **`research`**: Primary-source research that writes a cited repository note.
- **`prototype`**: Throwaway code that answers one logic, state, or UI design question.
- **`code-review`**: Two-axis diff review against repository standards and originating spec.
- **`diagnosing-bugs`**: Root cause analysis and feedback loop generation for hard bugs.
- **`codebase-design`**: Deep module and seam design using locality and leverage principles.
- **`writing-for-agents`**: Authoring and auditing agent instruction files, skills, and AGENTS.md.
- **`resolving-merge-conflicts`**: Conflict resolution preserving the intent of both branches.
- **`deslop`**: Eliminating AI code smell patterns while keeping interfaces and tests green.
- **`wizard`**: Generating interactive human-in-the-loop shell wizards.
- **`grilling`**: Relentlessly interviewing requirements one question at a time.
- **`domain-modeling`**: Clarifying ubiquitous domain language and GLOSSARY.md.
- **`tdd`**: Running the BDD-driven red-green automation loop.
- **`pr`**: Writing a concise PR body with evidence and merge risk.

User-invoked capabilities also appear in the command menu. `/matt-pocock retro` reviews a session and proposes improvements to the agent environment. The upstream glossary rename retains `CONTEXT-FORMAT` as an alias of `GLOSSARY-FORMAT`, so existing workflow records can still restore. `resolving-merge-conflicts` remains a local compatibility capability after its removal upstream.

## Lifecycle Display Lines

Following `@fradser/pi-kit` lifecycle renderer conventions, all tool invocations and workflow transitions render as compact single-line lifecycle indicators in the transcript instead of dumping raw payloads.

### Workflow Phase Titles

Workflow lifecycle subjects use the readable title of the phase recorded at that event, not the route id, route title, or a generated task title. The mapping is shared through `readablePhaseTitle()` in `src/workflow.ts`.

| Operation | Lifecycle line |
| --- | --- |
| `/matt-pocock <route> [task]` start, menu start, or menu transition | `[matt pocock] started` block, then the task or the readable phase title |
| Agent-invoked workflow start (`matt_pocock_workflow`) | `[matt pocock] started · <Phase Title>` |
| Transition to a phase | `[matt pocock] event · <Phase Title>` |
| Complete the workflow | `[matt pocock] event · <Phase Title> completed` |
| Cancel the workflow | `[matt pocock] event · <Phase Title> cancelled` |

A user-invoked start mirrors `/impeccable`: the head row carries only the label, a blank band row separates it from the body, and the whole block paints on Pi's native user-message band (`userMessageBg`). The body is the user's own task verbatim when they supplied one, otherwise the readable phase or capability name:

```text
[matt pocock] started

fix the login redirect
```

Every authored task line keeps its own row, long lines wrap instead of merging, and the block never advertises expansion. Agent-invoked starts stay on the compact inline row because a tool call has no user text to echo.

For example, a `hard-bug` workflow that reaches code review before completion renders:

```text
[matt pocock] started · Reproducing & Diagnostics
[matt pocock] event · Implementation
[matt pocock] event · Code Review
[matt pocock] event · Code Review completed
```

Cancelling during implementation instead renders `[matt pocock] event · Implementation cancelled`. Completion and cancellation still end the **entire workflow**; the title identifies its actual phase at termination, which can also be the entry phase. The renderer never assumes the workflow reached its last phase.

Supported titles by route (not a mandatory execution order):

| Route | Phase titles |
| --- | --- |
| `idea-to-ship` | Shaping & Requirements; Research & Feasibility; Prototyping; Specification Design; Task Decomposition; Implementation; Code Review; Handoff & Summary |
| `wayfinding` | Initiative Mapping; Research & Feasibility; Prototyping; Specification Design; Task Decomposition; Implementation; Code Review |
| `triage` | Task Triage; Specification Design; Task Decomposition; Implementation; Code Review |
| `hard-bug` | Reproducing & Diagnostics; Implementation; Code Review |
| `architecture` | Architecture Survey; Architecture Design; Implementation; Code Review |

Route and phase ids remain unchanged in tool arguments, model guidance, result details, and persisted state. A workflow-start row shows the readable phase title only. The row does not repeat the route id or its title, and it does not expose procedure bodies.

No Matt Pocock row hides a field body behind expansion. Every row shows its facts in the collapsed transcript:

- Transitions, completion, and reference loads omit repetitive `action` fields; standalone capability and reference rows do not repeat their subjects as fields. When the title fits, these rows have no expand hint or extra detail body.
- A cancellation row carries `reason · <stored reason>` inline when that result's terminal snapshot has a nonblank reason. The reason appears once, never as `action · cancel`, and it does not come from the current workflow. A missing, empty, or whitespace-only reason adds no body line.
- At narrower widths, Pi-kit's shared renderer can offer expansion to wrap a clipped title or body line with Pi's native wrapping. Model-only content does not itself create an expand hint.

The `matt-pocock-procedure` message renderer owns that block layout. A `/matt-pocock` route or capability start (including a freeform routing request and the menu's "Start a task") delivers the procedure through this displayed message instead of posting the procedure text as a user message, while the model still receives the complete body plus any `User target/request:` section. Session restoration reinjects guidance silently (`display: false`), without a duplicate lifecycle event. Saved active-tool results with old route-based subjects are rendered from their recorded phase and action, not the session's current workflow; no session-data migration is needed.

### Other Lifecycle Displays

These operations keep their own subjects rather than substituting a workflow phase:

- **Reference loading (`load`)**: `[matt pocock] event · loaded <reference>` (e.g. `[matt pocock] event · loaded HTML Report`).
- **Standalone capability**: `[matt pocock] started · <capability>` (e.g. `[matt pocock] started · Diagnosing Bugs`).
- **Standalone reference**: `[matt pocock] started · <capability> · <reference>`.
- **`matt_pocock_ask`**: `[matt pocock] ask · <question>`, with the answer or pending status below. The model-facing result includes the full question followed by the chosen answer as a block quote (`> <answer>`); `(Recommended)` is only a choice label and is omitted from the answer. Timeout, no-UI, and custom-input metadata appear as inline body lines below the answer, which is never repeated.
- **Fallback**: `[matt pocock] event · workflow updated` when no action or subject is available.

Capability and reference names use readable catalog labels consistently. Transition-menu choices use their destination phase titles, matching lifecycle rows. Command identifiers and saved resource ids remain unchanged; user-supplied tasks are displayed verbatim.

Run the actual Pi checks from the repository root:

```bash
uv run --no-project packages/matt-pocock/tests/live/live_smoke.py
uv run --no-project packages/matt-pocock/tests/live/runtime_live.py
uv run --no-project packages/matt-pocock/tests/live/restore_live.py
uv run --no-project packages/matt-pocock/tests/live/decision_live.py
uv run --no-project packages/matt-pocock/tests/live/active_menu_live.py
uv run --no-project packages/matt-pocock/tests/live/abort_live.py
uv run --no-project packages/matt-pocock/tests/live/adversarial_live.py
node --import tsx/esm packages/matt-pocock/tests/live/native_real_smoke.ts
```

The lifecycle check covers print mode, terminal rows, timeout and Escape, Ctrl+O, 48-column resizing, and the user-message band. The catalog matrix derives routes, legal transitions and standalone capabilities from the manifest and exercises them through Pi's agent loop, including persistence, restart, native tree navigation and native compaction. The compaction probe supplies a deterministic summary through `session_before_compact`; Pi still performs compaction and session persistence. Restored procedure sources are checked in the next model context.

The restart boundary check also covers completed/cancelled latest records, incompatible versions, and invalid phase/reference/procedure records, with older active records still present. It verifies inactive tools and guidance, and cancellation records for invalid active state.

The adversarial check opens real Pi selectors and menus, then injects deterministic state changes through the registered handlers. It verifies immediate dismissal, replacement work-item identity, and reference-only loading before and after a user command. Package tests additionally derive resource/alias/disclosure/transition cases from the catalog and test exact UTF-8 size boundaries in disposable package copies.

Repository verification details and reproduced failures are recorded in [the adversarial verification report](tests/reports/ADVERSARIAL-VERIFICATION.md).

The decision and active-menu checks send actual keyboard input through Pi's terminal UI. They cover option/custom input, cancellation, timeout, View, Transition, Cancel and Complete. The abort check interrupts a live selector with an AbortSignal. These Pi checks use an isolated home, allowlisted process settings and a deterministic local provider; they do not inherit provider credentials or validate external-model decisions or downstream project work performed by a procedure.

The decision check deliberately fails a simulated native subprocess to exercise TUI fallback. On macOS, the separate native smoke uses the real `osascript` to verify list/input/prompt timeout and list abort, including process exit. It does not automate native button selection or verify physical rendering. Package tests also typecheck every TypeScript test fixture and verify package-local Pi v1.0 dependency resolution.

The separate real-model matrix covers all 21 standalone capabilities, five workflow entries, natural-language routing, and a review regression where passing tests coexist with unrequested behavior (28 cases). Listing it does not read credentials or start Pi:

```bash
uv run --no-project packages/matt-pocock/tests/real_model_live.py --list
uv run --no-project packages/matt-pocock/tests/real_model_live.py --case cap-pr --output /tmp/matt-real-pr.json
uv run --no-project packages/matt-pocock/tests/real_model_live.py --all --output /tmp/matt-real-matrix.json
```

`--case` and `--all` call the configured real provider and model, with thinking off. Each case uses a disposable project and agent directory; authentication files are copied with private permissions and deleted afterward. The production extension runs through native Pi RPC. File tools stay inside the project, fixed tests run in a macOS sandbox, and the verifier cannot be modified. Results distinguish verified artifacts, questions awaiting an answer, failures, and skipped cases. If any question is pending, the aggregate remains `awaiting_user`; an expected pending result has exit code 0. A provider failure stops the matrix instead of switching models. These runs are deliberately separate from the credential-free package test suite.

Three multi-turn developer journeys additionally cover an agreed discount feature through review and handoff, async cache incident repair, and configuration cleanup through design, de-slop, review and handoff. Their fixed acceptance tests verify public behavior and independent cache keys; review notes are also inspected for unsupported causal claims and misleading verdicts. Workflow journeys require the actual requested stages and one work item. The harness waits for Pi agent settlement between turns. These longer journeys explicitly allow up to 80 tool calls; the ordinary matrix retains its default 40-call budget, and exhaustion blocks later turns too.

```bash
uv run --no-project packages/matt-pocock/tests/real_model_live.py --cases packages/matt-pocock/tests/developer-journey-cases.json --list
uv run --no-project packages/matt-pocock/tests/real_model_live.py --cases packages/matt-pocock/tests/developer-journey-cases.json --all --deadline 420 --output /tmp/matt-developer-journeys.json
```

The developer journey evidence and observed limitations are documented in [DEVELOPER-JOURNEYS.md](tests/reports/DEVELOPER-JOURNEYS.md).

## Configuration

You can optionally configure native macOS dialog prompts for `matt_pocock_ask` via `matt-pocock.json` in Pi's agent directory (`~/.pi/agent/matt-pocock.json`, or `$PI_CODING_AGENT_DIR/matt-pocock.json` when that variable is set):

```json
{
  "useNativeDialog": true
}
```

Only the boolean `true` enables native dialogs; strings and numbers keep them disabled. By default (`useNativeDialog: false` or missing file), Pi uses its built-in TUI selection dialog. Native dialogs are automatically guarded to only trigger on local macOS GUI sessions (SSH sessions, non-macOS platforms, and CI environments always fall back cleanly to terminal TUI).

See the detailed [中文架构说明](ARCHITECTURE.zh-CN.md), the upstream [selection metadata](upstream/upstream-selection.json) and [sync rules](upstream/UPSTREAM.md), and the deliberately deferred items in [TODO.md](TODO.md).

## License

MIT

Eight additional developer fixtures cover generated frontend HTML, API request boundaries, authorization, versioned migration, operation-count performance, localization, lexical paths and behavioral test design. Together with the earlier journeys, these cover eleven developer task categories. The catalog-derived inventory checks every supported standalone capability and route; JSON boundary checks cover all JSON value classes.

```bash
uv run --no-project packages/matt-pocock/tests/type_inventory.py
uv run --no-project packages/matt-pocock/tests/real_model_live.py --cases packages/matt-pocock/tests/expanded-type-cases.json --list
uv run --no-project packages/matt-pocock/tests/real_model_live.py --cases packages/matt-pocock/tests/expanded-type-cases.json --all --deadline 300 --output /tmp/matt-expanded-types.json
```

The real-model verifier returns bounded redacted diagnostics and requires an immutable acceptance completion marker, so an early successful process exit cannot silently skip acceptance. See [TEST-TYPES.md](tests/reports/TEST-TYPES.md) for the coverage inventory, actual attempts and limitations. These checks do not establish browser assistive-technology behavior, deployed services, physical input or every possible software task.
