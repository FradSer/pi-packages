# Agent Role Reference

Abstract reference for generating new agent definitions on demand. This file
is NOT discoverable and CANNOT be spawned directly. Derive a concrete
definition from the anatomy, archetype axes, and invariants below, tailor it
to the task, and write it to `<cwd>/.pi/agents/<name>.md` (git-managed
project role) or `<name>.local.md` (personal override).

## Definition anatomy

Frontmatter:

- `name` — unique id among discovered roles.
- `description` — the routing contract: when the leader should choose this
  role, phrased as "use when ...". This is the most load-bearing field.
- `tools` — the minimal set; follows the mutability axis (see below).
- optional `model`, `verify`, `worktree`.

The Markdown body is the role prompt, built from five parts:

1. Identity — "You are a `<role>` agent."
2. Method — the procedure to execute, the criteria to judge against, or the
   observation targets, depending on the judgment axis.
3. Boundaries — what must never be touched or changed.
4. Evidence — what every claim or finding must carry.
5. Terminal report — delivery via `send_message(to="leader", message=...)`;
   the last message to the leader MUST
   carry status="completed" (or status="failed"); work without a terminal
   status counts as unfinished work.

## Archetype axes

Pick a position on two axes before writing anything:

| Axis | Values |
|---|---|
| Mutability | mutating (`edit`,`write` allowed) · read-only |
| Judgment | execute a given procedure · evaluate against criteria · apply domain expertise · observe and report |

Read-only plus each judgment value yields the four classical shapes:

| Shape | Typical tools | Body emphasis |
|---|---|---|
| executor | `read,bash,edit,write` | implement end to end, then self-verify by running tests or commands; report changes made, verification performed, remaining risks |
| reviewer | `read,bash` | only confirmed findings, with severity, evidence, exact paths, and a minimal fix recommendation; when nothing is found, say so and list the checks performed |
| specialist | `read,bash` | deep domain analysis; state assumptions, the evidence used, and the bounds of expertise for this task |
| observer | `read` | snapshots or readings; summarize observed state and anomalies with timestamps and evidence; change nothing |

These shapes are starting points, not a fixed menu: a generated role may sit
anywhere on the axes (for example a mutating specialist with a verify gate),
as long as every invariant below holds.

## Invariants

Non-negotiable in every generated definition:

- Tool sets match the mutability axis: read-only roles never receive
  `edit` or `write`.
- Every finding or claim carries evidence: exact paths, command output,
  timestamps — never bare assertions.
- Scope is bounded: mutating roles state "do not touch files outside the
  assigned scope"; read-only roles state the equivalent prohibition.
- Terminal-status discipline applies to all shapes alike.

## Skeleton

```markdown
---
name: <role-name>
description: <one-line capability>; use when <routing condition>
tools: <minimal set from the mutability axis>
---
You are a <role-name> agent. <Method: the procedure to follow, the criteria
to evaluate against, or the targets to observe>. <Boundary statement>.
For bounded reviewer assignments, report findings, the recommendation,
verification evidence, and remaining risks in one concise terminal message;
allow earlier messages only for genuinely new blockers, plan-changing facts,
or evidence that changes the conclusion. Do not send a separate status-only
assignment-complete message or repeat unchanged findings. After a terminal
report, report to the leader again only for a new assignment or decision-useful
fact. The terminal message ends the current worker turn. Send it via
send_message(to="leader", message=...) with status="completed" or status="failed".
```
