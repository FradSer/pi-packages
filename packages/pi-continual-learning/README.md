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
| `/consolidate` | Run manual memory consolidation now |
| `/guardrails` | Show active policies, sources, and config paths |

## Guardrails configuration

Policies layer innermost-last; a policy name defined in several layers
resolves to the innermost definition, and any layer can disable names:

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
  // The block reason is fed back to the model as the more correct prompt:
  "reason": "Fixed pixel widths break responsiveness. Use design tokens or responsive units."
}
```

A generalized example — AI-generated UI widths violating layout rules — ships
at `examples/ui-width.harness.json`: edits touching UI files that contain
fixed pixel widths above the threshold are blocked with design guidance, while
the same text in non-UI files passes through. Drop the file's contents into
your project `.pi/harness.json` to activate it.

Built-in defaults cover known-futile automation: interactive auth commands
(`npm/pnpm/yarn login|adduser|logout`) and OTP-via-file/chat routing are
blocked with guidance to hand those steps to the user's own terminal.

## Memory

See `AGENTS.md` and `procedures/consolidate.md` for the memory loading rules,
privacy constraints, and the parent-owned consolidation protocol. State lives
in harness memory directories; only safe files sync to public `.memory/`.
