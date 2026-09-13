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

With auto-memory enabled (the default), a completed user task triggers learning
at `agent_settled`, after automatic retries and queued continuations. New user
tasks are coalesced while learning runs; extension-generated continuations do
not independently retrigger learning. Interactive sessions remain responsive;
print/JSON runs wait for the pipeline and its receipts before exiting.

The parent freezes the task context, runs read-only planners, validates their
bounded proposals, and applies changes. Ordinary task execution no longer asks
the main model to write memory directly. Turning auto-memory off stops new
automatic learning while preserving retrieval of existing memory. `/consolidate`
remains available for an explicit run, including headless execution.

## Install

```bash
pi install npm:pi-continual-learning
```

## Commands

| Command | Purpose |
| --- | --- |
| `/memory` | Memory management menu: instructions, model, consolidation, settings |
| `/consolidate` | Run learning now: memory first, then harness constraints and project AGENTS.md mined from the frozen task context |
| `/harness` | Show active constraints, or create a rule from a prompt (default: project personal `.pi/harness.local.json`, `--shared` for project repo, `--global` for user) |

## Guardrails configuration

Policies layer innermost-last; a policy name defined in several layers
resolves to the innermost definition, and any layer can disable names. Every
policy is validated against the runtime schema before it can become active;
unknown fields are rejected with a diagnostic rather than silently ignored:

Built-in defaults are the outermost package-owned baseline. User-owned configuration has exactly three layers:

1. User shared: `~/.pi/agent/harness.json` (the agent directory honors `PI_CODING_AGENT_DIR`).
2. Project shared: `<project>/.pi/harness.json`.
3. Project personal: `<project>/.pi/harness.local.json`.

The obsolete user-personal `~/.pi/agent/harness.local.json` is not discovered
or shown by `/harness`. Runtime precedence is project personal over project
shared over user shared (with built-in defaults outermost).

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
personal layer at `<project>/.pi/harness.local.json`. Use `--shared` (or `--project`,
`--repo`) to target the git-tracked `<project>/.pi/harness.json`, or `--global`
(or `--user`) to target the user-shared `~/.pi/agent/harness.json`. The request is sent as a
follow-up with an explicit write protocol: it reads that exact target file,
creates it there when missing, preserves existing entries, and verifies the
result without wandering to other layers.

Built-in defaults cover known-futile automation: interactive auth commands
(`npm/pnpm/yarn login|adduser|logout`) and OTP-via-file/chat routing are
blocked with guidance to hand those steps to the user's own terminal.

### Harness consolidation

After verified memory consolidation, learning runs a second read-only
planner against the same frozen task context: it mines blocked tool
calls, confirmation outcomes, and user corrections, then proposes bounded
policy/context-guidance changes citing that evidence. The parent alone applies
them — atomically, and only to the personal project-local layer
(`.pi/harness.local.json`). Shared layers are never written; a failed or
rejected harness plan never touches applied memory results; `no-context`
runs skip the phase entirely. Evidence must quote real user or tool messages
from the captured context. Policy additions and updates must also supply
positive and negative examples that the parent executes with the runtime
evaluator. A model-written evidence summary or occurrence count alone is not
proof. Automatically learned rules cannot override shared, built-in, or
manually authored constraints; explicit rule changes remain available through
`/harness`.

### AGENTS.md consolidation

The third pipeline phase treats the repository-root `AGENTS.md` like trained
weights. Against the same snapshot, a read-only planner proposes at most five
evidence-cited edits — rewrite, remove, add, or extract addressable units.
The parent enforces the discipline in code before anything is applied:

- Every cited quote must appear verbatim in the snapshot text; unverifiable
  quotes are discarded mechanically, and an operation left without evidence
  never reaches the automatic application step.
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

After the mechanical gates pass, every surviving operation is applied
autonomously in one atomic write (with a pre-apply digest for mid-apply
shutdown recovery). User-level instruction files are never touched, and the
child planner remains read-only.
Configure via the per-project settings file:

```json
{ "autoMemory": true, "agentsMd": { "budgetBytes": 16384 } }
```

`"disabled": true` inside `agentsMd` turns the phase off. A failed AGENTS.md
phase never touches applied memory or harness results.

### Skill prompt guidance

`/harness <request>` supplies the current session's registered skill keys. Policy names may be descriptive; `skillPrompts` keys must be exact registered skill names, and values must be `{ "prompt": "...", "target": "system" | "user" }` objects, never strings. Complete `write` tool calls to harness configuration files are checked before writing: new or changed invalid/unknown skill entries are blocked. Unchanged existing entries and removal of stale entries remain allowed. The `edit` tool is blocked for these configuration paths with guidance to read and write the complete validated JSON instead. This gate does not intercept arbitrary shell writes or make semantic instructions globally enforceable.

Automatic harness consolidation and AGENTS.md skill extraction also validate additions against the session registry; without a registry, adding a skill prompt fails closed. `/harness` status separates registered guidance from inactive unknown skill names and displays malformed-entry diagnostics. Registered does not mean trigger-tested: reading JSON back proves persistence only. A skill prompt is not a project-wide rule, and unsupported global/multi-step requirements must be reported rather than assigned an invented skill name.

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

1. Harness/private (canonical and complete): `~/.pi/agent/memory/<escaped-canonical-project-path>/`
2. Project shared (safe Git mirror): `<git-root>/.memory/`

The private directory replaces each path separator in the canonical project path with `-`, including the leading POSIX separator (for example `-Users-FradSer-Developer-FradSer-cerberus`). Safe entries are byte-identical in both roots; entries marked `(harness only)` in the private `MEMORY.md` never appear in the project mirror. Before consolidation, newer-mtime-wins drift normalization runs bidirectionally, with ties preferring the private copy. The private root remains the runtime source of truth, while project `.memory/` participates in first adoption and committed-update synchronization.

See `AGENTS.md` and `procedures/consolidate.md` for loading rules and the parent-owned transactional consolidation protocol.

New memories are proposed separately from the parent-selected existing-file
scope, so a project with no memory files can learn from its first task. Each
proposal names a bounded Markdown file and cites the exact text and index of a
user or tool-result message in the immutable snapshot. Preferences remain
private; credentials and tokens are rejected even for private storage. New
names cannot overwrite existing entries, and creations participate in the same
rollback, index, privacy, hash, and receipt validation as existing-file edits.
