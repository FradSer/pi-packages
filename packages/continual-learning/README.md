# pi-continual-learning

Continual learning for Pi across the two surfaces that matter at runtime —
model weights are explicitly out of scope:

- **Memory and context guidance** — project facts, decisions, and personal
  preferences help the model understand the task before generation. A bounded
  memory index is injected and full entries are read when relevant. Skill
  guidance is also context; it does not guarantee enforcement.
- **Harness** — executable constraints check generated tool calls before
  execution, and inspect assistant output and configured file artifacts after
  generation. Violations produce concrete feedback with a bounded repair loop.

With auto-memory enabled (the default), a completed user task first passes a deterministic, zero-token evidence screen at `agent_settled`, after automatic retries and queued continuations. Routine tasks with no durable signal launch no learning model. Automatic runs and default `/consolidate` use only the current completed Task Slice. A lightweight metadata-only selector chooses the minimum sufficient related Memory scope; the selected bodies and task evidence form one authoritative Learning Dossier. `/consolidate full` is the only full-corpus maintenance path. New user tasks are coalesced while learning runs; extension-generated continuations do not independently retrigger learning. Interactive sessions remain responsive; print/JSON runs wait for the pipeline and its receipts before exiting.

Memory, Harness, and AGENTS.md planners consume the same bounded dossier and return only proposed deltas; they do not independently explore the complete session or repository. Their substantial Markdown protocols remain package-owned under `prompts/`, and `extensions/planner-prompts.ts` loads them through typed builders that perform literal nonrecursive binding and reject missing, unknown, or unresolved placeholders. Planning may overlap while parent validation and mutation remain sequential. Pipeline receipts account for every selector/planner attempt and display input, output, cacheRead, cacheWrite, total tokens, and provider cost availability separately.

The parent freezes the task context, runs read-only planners, validates their
bounded proposals, and applies changes. Ordinary task execution no longer asks
the main model to write memory directly. Turning auto-memory off stops new
automatic learning while preserving retrieval of existing memory. `/consolidate`
remains available for an explicit run, including headless execution.

## Install

Python 3 must be available as `python3` on `PATH`; Memory consolidation runs
the package's bundled Python validator at runtime.

```bash
pi install npm:pi-continual-learning
```

## Commands

| Command | Purpose |
| --- | --- |
| `/memory` | Memory management menu: instructions, model, consolidation, settings |
| `/consolidate` | Incrementally learn from the current completed Task Slice |
| `/consolidate full` | Explicitly run expensive full-corpus Memory, Harness, and AGENTS.md maintenance |
| `/harness` | Show active constraints, or create a rule from a prompt (default: project `.pi/harness.json`, `--local` for explicitly requested personal configuration, `--global` for user) |

## Guardrails configuration

Policies layer innermost-last; a policy name defined in several layers
resolves to the innermost definition, and any layer can disable names. Every
policy is validated against the runtime schema before it can become active;
unknown fields are rejected with a diagnostic rather than silently ignored:

Built-in defaults are the outermost package-owned baseline. User-owned configuration has exactly three layers:

1. User shared: `~/.pi/agent/harness.json` (the agent directory honors `PI_CODING_AGENT_DIR`).
2. Project shared: `<project>/.pi/harness.json`.
3. Project personal: `<project>/.pi/harness.local.json`.

The obsolete user-personal `~/.pi/agent/harness.local.json` and project `.pi/agent/harness*.json` files are not discovered or shown by `/harness`. Runtime precedence is project personal over project shared over user shared (with built-in defaults outermost).

Policy shape:

```jsonc
{
  "name": "ui-fixed-width",
  "tools": ["edit", "write"],
  // AND-gate: scope the policy to a class of calls first...
  "require": { "path": "path", "pattern": "\\.(tsx|css)$" },
  // ...then patterns inspect only text being written, never edit oldText
  "paths": ["content", "newText", "edits.newText"],
  "patterns": ["width:\\s*\\d{3,}px"],
  "action": "block",
  // The policy reason is fed back when a call is blocked or confirmed,
  // and appears in the display-only transcript event for observe:
  "reason": "Fixed pixel widths break responsiveness. Use design tokens or responsive units."
}
```

Declarative policies support `name`, `phase`, `tools`, `paths`, `artifactPaths`,
`pattern` or `patterns`, optional `require`, `action`, and `reason`.
Fields such as `scope` and `rule` are not aliases and are rejected. A matching
policy can `block`, `confirm`, or `observe`: observe leaves the call untouched
and records a display-only harness event with its reason. Policies do not execute
generated scripts or probe external services.

### Check phases

| Phase | Checked input | Response to a violation |
| --- | --- | --- |
| `tool-call` (default) | Generated tool arguments, before execution | Block, ask for confirmation, or observe |
| `output` | Completed assistant text | Request a corrected response, or observe |
| `artifact` | Actual workspace file bytes | Request correction of the file, or observe |

For example, an artifact rule can inspect the final dependency declaration even
when it was written through a shell command:

```json
{
  "name": "no-retired-sdk",
  "phase": "artifact",
  "tools": ["write", "edit", "bash"],
  "artifactPaths": ["package.json"],
  "pattern": "\"retired-sdk\"\\s*:",
  "action": "block",
  "reason": "The retired SDK is prohibited. Remove its dependency declaration."
}
```

Artifact paths are explicit workspace files; checks read actual content rather
than trusting the tool arguments. Unsafe paths, missing files, and files beyond
the read limit are reported as unsupported, never as passed. Checks cover only
their declared files and patterns; regex matching cannot establish arbitrary
semantic correctness.

Post-generation checks have a bounded repair budget per user task. They report
unresolved violations when that budget is exhausted. Assistant text has already
been streamed when an output check runs: a correction does not retract or hide
the original response. Use tool-call gates for actions that must be prevented
before their side effects occur.

A generalized example — AI-generated UI widths violating layout rules — ships
at `examples/ui-width.harness.json`: edits touching UI files that contain
fixed pixel widths above the threshold are blocked with design guidance, while
the same text in non-UI files passes through. Drop the file's contents into
your project `.pi/harness.json` to activate it.

To create a rule directly, pass a natural-language request: `/harness
block edits that add hard-coded colors`. By default, it targets the project
shared layer at `<project>/.pi/harness.json`. Use `--local` (or `--project-local`)
only for explicitly requested non-Git-tracked personal configuration at `.pi/harness.local.json`.
`--shared`, `--project`, and `--repo` explicitly select the default; use `--global`
(or `--user`) to target the user-shared `~/.pi/agent/harness.json`. The request is sent as a
follow-up with an explicit write protocol: it reads that exact target file,
creates it there when missing, preserves existing entries, and verifies the
result at that same path.

Built-in defaults cover known-futile automation: interactive auth commands
(`npm/pnpm/yarn login|adduser|logout`) and OTP-via-file/chat routing are
blocked with guidance to hand those steps to the user's own terminal.

### Harness consolidation

In incremental mode, Harness consumes the selector-built Learning Dossier and current Task Slice; it does not run an independent model explorer or repository-wide scan. After verified Memory learning, or a verified no-mutation Memory gate, one read-only planner runs against that same frozen task context: it mines blocked tool
calls, confirmation outcomes, and user corrections, then proposes bounded
policy/context-guidance changes citing that evidence. The parent alone applies
them — atomically, and only to the project layer
(`.pi/harness.json`). User and project-personal layers are never written; a failed or
rejected harness plan never touches applied memory results; `no-context`
runs skip the phase entirely. Evidence must quote real user or tool messages
from the captured context. Policy additions and updates must also supply
positive and negative examples that the parent executes with the runtime
evaluator. A model-written evidence summary or occurrence count alone is not
proof. Automatically learned rules cannot override other layers, built-in, or
manually authored constraints; explicit rule changes remain available through
`/harness`.

### AGENTS.md consolidation

In incremental mode, AGENTS.md planning reuses the same Learning Dossier and Task Slice as Harness and returns only proposed edits. The third pipeline phase treats the repository-root `AGENTS.md` like trained
weights. Against the same snapshot, a read-only planner proposes at most five
evidence-cited edits — rewrite, remove, add, or extract addressable units.
The parent enforces the discipline in code before anything is applied:

- Every cited quote must come from an indexed user or tool-result message and
  appear verbatim in the snapshot text; unverifiable quotes are discarded
  mechanically, and an operation left without evidence never reaches the
  automatic application step.
- A brand-new unit needs batched evidence (at least two cited occurrences in
  the current session).
- The post-edit document must fit the byte budget (default 16 KB ≈ 4k English
  tokens by the bytes/4 heuristic — deliberately tighter than backpass's ~20 KB
  default and Claude Code's 25 KB MEMORY.md load cap; lower it further for
  primarily Chinese files, where UTF-8 packs fewer tokens per byte); once the
  file sits at or above budget, updates are zero-sum — removals pay for
  additions.
- Narrow instructions are extracted instead of kept: trigger-scoped guidance
  becomes a harness skill prompt; durable detail becomes a memory file.

After the mechanical gates pass, surviving operations are applied
autonomously within one parent-owned transaction and rollback boundary. Before mutation, an `agents-pre-receipt.json` records the plan digest plus exact predecessor files and directory existence; if the process stops before the post receipt, the next session validates and consumes that record before new learning starts. The pre receipt is retained beside a verified post receipt. User-level instruction files are never touched, and the child planner remains read-only.
Configure via the agent-global settings file at
`<agent-dir>/memory/settings.json` (normally
`~/.pi/agent/memory/settings.json`; `<agent-dir>` honors
`PI_CODING_AGENT_DIR`). These settings apply to every project using that agent
directory:

```json
{ "autoMemory": true, "agentsMd": { "budgetBytes": 16384 } }
```

`"disabled": true` inside `agentsMd` turns the phase off. A failed AGENTS.md
phase never touches applied memory or harness results.

### Skill prompt guidance

Authoring preserves the user's semantic boundary: a fullscreen popup describes an overlay relationship. Clarify ambiguous requirements and ask before adding opacity, input, or scroll restrictions.

`/harness <request>` supplies the current session's registered skill keys. Policy names may be descriptive; `skillPrompts` keys must be exact registered skill names, and values must be `{ "prompt": "...", "target": "system" | "user" }` objects, never strings. Complete `write` tool calls to harness configuration files are checked before writing: all invalid/unknown skill entries are blocked, including unchanged malformed entries. The blocked write leaves existing data intact; repair or removal requires explicit user authorization. The `edit` tool is blocked for these configuration paths with guidance to read and write the complete validated JSON instead. Native tool path aliases (including `~`, a leading `@`, file URLs, and Unicode spaces) receive the same write/edit gates. Pi currently exports no native target resolver, and pi-kit has no equivalent; this gate uses local deterministic normalization tested against the public `createWriteTool`, without importing private modules from `PI_PACKAGE_DIR` (which may contain only binary assets); reads remain available for diagnosis. This gate does not intercept arbitrary shell writes or make semantic instructions globally enforceable.

Automatic harness consolidation and AGENTS.md skill extraction also validate additions against the session registry; without a registry, adding a skill prompt fails closed. Runtime loading with a skill registry excludes unknown names as well as malformed entries, while keeping valid siblings. `/harness` status and planner surface summaries list registered guidance and report invalid-entry diagnostics. Both consolidation surfaces reject malformed existing roots or containers before mutation or pre-receipt creation, preserving the original bytes and ownership metadata rather than resetting invalid data. Registered does not mean trigger-tested: reading JSON back proves persistence only. A skill prompt is not a project-wide rule, and unsupported global/multi-step requirements must be reported rather than assigned an invented skill name.

`skillPrompts` is a context-guidance namespace stored alongside policies in the
same configuration layers. Its separate `context-guidance` extension adds
guidance when Pi expands a configured
`/skill:<name>` invocation. The same three user-owned layers apply, with the
project-personal definition winning over project shared and user shared by skill name.
`disabled` affects declarative policies in every phase; it does not affect skill prompts:

```json
{
  "skillPrompts": {
    "using-open-artifacts": {
      "prompt": "Use coda0.com as the default instance unless the user specifies another host.",
      "target": "system"
    },
    "impeccable": {
      "prompt": "For Live on macOS, use open <served app URL>, never helper serverPort or agent-browser; then keep one foreground live-poll.mjs active.",
      "target": "system",
      "userMessagePattern": "^live$"
    }
  }
}
```

`target: "system"` appends the prompt to the current system prompt. The
`target: "user"` form delivers a hidden custom context message because Pi's
`before_agent_start` hook cannot rewrite the already-expanded user message;
both targets are matched only against Pi's complete expanded skill XML, not a
raw `/skill:` command or arbitrary XML-looking text. An optional
`userMessagePattern` narrows a prompt to the expanded block's user-message
suffix (for example `^live$`); it is a regular expression and invalid patterns
are skipped with a configuration diagnostic. Guidance is appended idempotently
when a hook is evaluated more than once.

## Memory

Memory has exactly two synchronized roots:

1. Agent-private (canonical and complete): `<agent-dir>/memory/<escaped-canonical-cwd>/`
2. Project-shared Git mirror: `<canonical Git project root>/.memory/` (safe to commit)

`<agent-dir>` is normally `~/.pi/agent` and honors `PI_CODING_AGENT_DIR`.
The project-shared mirror is enabled only when Pi runs at that canonical Git
root. Private Memory is never persisted anywhere inside
the project; no project-local private root is recognized.

The private directory name uses Pi's official flat escaping matching session storage:
leading slash stripped, path separators and colons replaced with `-`, wrapped in
double dashes (`--<escaped-path>--`). For example: `--Users-FradSer-Documents-Home Lab--`.
Names over 240 bytes are rejected, never truncated. `scopeKey` is this same readable
name, used for `memory/<scopeKey>/`, `memory/locks/<scopeKey>.lock`, and
`memory/runs/<scopeKey>/`. The separate `locks/` directory prevents locks from colliding
with private directory names. No project path uses a hash; content-integrity digests
remain unchanged. Paths with the same escaped name share private Memory, a lock, and run storage.

Safe entries are byte-identical in both roots; entries marked `(harness only)`
in the private `MEMORY.md` never appear in the project mirror. Before
consolidation, newer-mtime-wins drift normalization runs bidirectionally, with
ties preferring the private copy. The private root remains the runtime source
of truth, while project `.memory/` participates in first adoption and
committed-update synchronization.

The flat escaped canonical-path directory is the only agent-private runtime
root. Other layouts, including hash-only and hash-suffixed directories, are
ignored: the extension does not discover, read, import, rename, or delete them,
and provides no compatibility fallback or migration interface. Existing flat
directories matching the current sanitizer are used directly.

See `prompts/memory-consolidator.md` for the parent-owned transactional consolidation protocol.

New memories are proposed separately from the parent-selected existing-file
scope, so a project with no memory files can learn from its first task. Each
proposal names a bounded Markdown file and cites the exact text and index of a
user or tool-result message in the immutable snapshot. Preferences remain
private; credentials and tokens are rejected even for private storage. New
names cannot overwrite existing entries, and creations participate in the same
rollback, index, privacy, hash, and receipt validation as existing-file edits.

Automatic and manual consolidation may delete contradicted, superseded, or subsumed Memory only when a mechanically verifiable `preservedIn` repository file or same-transaction Memory target proves where the durable knowledge survives. The receipt's change summary is checked against the validated plan. Built-in Harness rules also block generated shell commands that bulk-delete `.memory` or the private Pi Memory root.
