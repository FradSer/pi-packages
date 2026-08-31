# pi-continual-learning

Continual learning for Pi across the two surfaces that matter at runtime —
model weights are explicitly out of scope:

- **Harness** — declarative tool-call guardrails. Layered JSON policies are
  evaluated on every tool call; matching calls are blocked (or gated behind
  user confirmation) with corrective guidance fed back to the model, so the
  system's tool-use behavior evolves without touching weights.
- **Prompts** — durable project memory: retrieval, injection, auto-memory
  guidance, and manual consolidation keep task-intent mapping and system
  guidance current across sessions.

## Install

```bash
pi install npm:pi-continual-learning
```

## Commands

| Command | Purpose |
| --- | --- |
| `/memory` | Memory management menu: instructions, model, consolidation, settings |
| `/consolidate` | Consolidate now: memory first, then harness guardrails and project AGENTS.md mined from session history |
| `/harness` | Show active tool-call guardrails, or create a global rule from a prompt |

## Guardrails configuration

Policies layer innermost-last; a policy name defined in several layers
resolves to the innermost definition, and any layer can disable names. Every
policy is validated against the runtime schema before it can become active;
unknown fields are rejected with a diagnostic rather than silently ignored:

1. Built-in defaults ship with the package.
2. Pi agent directory `harness.json` (+ `harness.local.json`; defaults to `~/.pi/agent`, honors `PI_CODING_AGENT_DIR`)
3. `<project>/.pi/harness.json` (+ `harness.local.json`)

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

Only the declarative policy fields shown above are supported: `name`, `tools`,
`paths`, `pattern` or `patterns`, optional `require`, `action`, and `reason`.
Fields such as `scope` and `rule` are not aliases and are rejected. A matching
policy can `block`, `confirm`, or `observe`: observe leaves the call untouched
and records a display-only harness event with its reason. Policies do not run
multi-step checks, probe services, or repair runtime state.

A generalized example — AI-generated UI widths violating layout rules — ships
at `examples/ui-width.harness.json`: edits touching UI files that contain
fixed pixel widths above the threshold are blocked with design guidance, while
the same text in non-UI files passes through. Drop the file's contents into
your project `.pi/harness.json` to activate it.

To create a global rule directly, pass a natural-language request: `/harness
block edits that add hard-coded colors`. The request is sent as a follow-up with
an explicit write protocol for `~/.pi/agent/harness.local.json`. It reads that
exact global file, creates it there when missing, preserves existing entries,
and verifies the result; it does not search for a project-local harness file.

Built-in defaults cover known-futile automation: interactive auth commands
(`npm/pnpm/yarn login|adduser|logout`) and OTP-via-file/chat routing are
blocked with guidance to hand those steps to the user's own terminal.

`matt_pocock_ask` is also gated by the current session branch: it can run only
after `matt_pocock_workflow` has recorded an active workflow. The Matt Pocock
harness supplies `/matt-pocock end` as the explicit exit mechanism; its exit
record immediately disables further structured interview prompts until a new
workflow starts.

### Harness consolidation

After a verified memory consolidation, `/consolidate` runs a second read-only
planner against the same immutable session snapshot: it mines blocked tool
calls, confirmation outcomes, and user corrections, then proposes bounded
policy/skill-prompt changes citing that evidence. The parent alone applies
them — atomically, and only to the personal project-local layer
(`.pi/harness.local.json`). Shared layers are never written; a failed or
rejected harness plan never touches applied memory results; `no-context`
runs skip the phase entirely.

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

`skillPrompts` adds corrective guidance when Pi expands a configured
`/skill:<name>` invocation. The same four layers apply (user, user-local,
project, project-local), with the innermost definition winning by skill name.
`disabled` only affects tool-call policies, not skill prompts:

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

See `AGENTS.md` and `procedures/consolidate.md` for the memory loading rules,
privacy constraints, and the parent-owned consolidation protocol. State lives
in harness memory directories; only safe files sync to public `.memory/`.
