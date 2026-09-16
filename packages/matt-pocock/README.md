# pi-matt-pocock

`pi-matt-pocock` provides one `/matt-pocock` menu and a catalog-backed capability gateway for engineering workflows and focused procedures adapted from `mattpocock/skills`.

## Installation

```bash
pi install npm:pi-matt-pocock
```

## How It Works

`/matt-pocock` starts or manages persisted workflows and runs standalone capabilities. A single `procedureCatalog` manifest classifies bundled resources as workflow procedures, standalone capabilities, references, or assets, and defines their dependencies, disclosures, workflow placement, and legal transitions.

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
   - Supports recommended choices, automatic timeout adoption, and custom text input.

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
- **`domain-modeling`**: Clarifying ubiquitous domain language and CONTEXT.md.
- **`tdd`**: Running the BDD-driven red-green automation loop.

## Lifecycle Display Lines

Following `@fradser/pi-kit` lifecycle renderer conventions, all tool invocations and workflow transitions render as compact single-line lifecycle indicators in the transcript instead of dumping raw payloads.

### Workflow Phase Transitions

When transitioning between phases via `matt_pocock_active` (`action: "transition"`), the tool renders:

```text
[matt pocock] event · <route> · <Phase Title>
```

Supported workflow routes and their phase display titles:

- **`idea-to-ship`**
  - `[matt pocock] event · idea-to-ship · Shaping & Requirements` (`shaping`)
  - `[matt pocock] event · idea-to-ship · Research & Feasibility` (`research`)
  - `[matt pocock] event · idea-to-ship · Prototyping` (`prototype`)
  - `[matt pocock] event · idea-to-ship · Specification Design` (`to-spec`)
  - `[matt pocock] event · idea-to-ship · Task Decomposition` (`to-tickets`)
  - `[matt pocock] event · idea-to-ship · Implementation` (`implement`)
  - `[matt pocock] event · idea-to-ship · Code Review` (`code-review`)
  - `[matt pocock] event · idea-to-ship · Handoff & Summary` (`handoff`)

- **`wayfinding`**
  - `[matt pocock] event · wayfinding · Research & Feasibility` (`research`)
  - `[matt pocock] event · wayfinding · Prototyping` (`prototype`)
  - `[matt pocock] event · wayfinding · Specification Design` (`to-spec`)
  - `[matt pocock] event · wayfinding · Task Decomposition` (`to-tickets`)
  - `[matt pocock] event · wayfinding · Implementation` (`implement`)
  - `[matt pocock] event · wayfinding · Code Review` (`code-review`)
  - `[matt pocock] event · wayfinding · Initiative Mapping` (`mapping`)

- **`triage`**
  - `[matt pocock] event · triage · Task Triage` (`triage`)
  - `[matt pocock] event · triage · Specification Design` (`to-spec`)
  - `[matt pocock] event · triage · Task Decomposition` (`to-tickets`)
  - `[matt pocock] event · triage · Implementation` (`implement`)
  - `[matt pocock] event · triage · Code Review` (`code-review`)

- **`hard-bug`**
  - `[matt pocock] event · hard-bug · Reproducing & Diagnostics` (`feedback-loop`)
  - `[matt pocock] event · hard-bug · Implementation` (`implement`)
  - `[matt pocock] event · hard-bug · Code Review` (`code-review`)

- **`architecture`**
  - `[matt pocock] event · architecture · Architecture Survey` (`survey`)
  - `[matt pocock] event · architecture · Architecture Design` (`design-review`)
  - `[matt pocock] event · architecture · Implementation` (`implement`)
  - `[matt pocock] event · architecture · Code Review` (`code-review`)

### Other Active Workflow Actions

`matt_pocock_active` also reports non-transition workflow actions using the same event lifecycle shape:

- **Reference Loading (`load`)**: `[matt pocock] event · loaded <reference>` (e.g. `[matt pocock] event · loaded HTML-REPORT`)
- **Workflow Completion (`complete`)**: `[matt pocock] event · <route> completed` (e.g. `[matt pocock] event · idea-to-ship completed`)
- **Workflow Cancellation (`cancel`)**: `[matt pocock] event · <route> cancelled` (e.g. `[matt pocock] event · idea-to-ship cancelled`)
- **Fallback**: `[matt pocock] event · workflow updated`

### Other Lifecycle Displays

- **`matt_pocock_ask`**: User decision prompts render as `[matt pocock] ask · <question>`.
- **`matt_pocock_workflow`**: Starting a workflow, standalone capability, or capability reference renders as `[matt pocock] started · <subject>` (e.g. `[matt pocock] started · Idea to Ship · Shaping & Requirements` or `[matt pocock] started · research`).
- **`matt-pocock-procedure` message renderer**: Restoring an active workflow on session startup renders as `[matt pocock] started · <Route Title> · <Phase Title>`.

## Configuration

You can optionally configure native macOS dialog prompts for `matt_pocock_ask` via `~/.pi/agent/pi-matt-pocock.json`:

```json
{
  "useNativeDialog": true
}
```

By default (`useNativeDialog: false` or missing file), Pi uses its built-in TUI selection dialog. Native dialogs are automatically guarded to only trigger on local macOS GUI sessions (SSH sessions, non-macOS platforms, and CI environments always fall back cleanly to terminal TUI).

See the detailed [中文架构说明](ARCHITECTURE.zh-CN.md), the upstream [selection metadata](upstream-selection.json) and [sync rules](UPSTREAM.md), and the deliberately deferred items in [TODO.md](TODO.md).
