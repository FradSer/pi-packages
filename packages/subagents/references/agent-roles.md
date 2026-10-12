# Minimal subagent roles

Author one focused role with the smallest useful tool grant. This reference is
not itself discoverable or spawnable and imposes no coordination requirement.
Read [VISION.md](../VISION.md) for the identity and lifecycle contract, and
[AUTHORITY.md](../AUTHORITY.md) before creating definitions or migrating data.

## Temporary delegation

Give `agent_start` a prompt and the tools needed for that input.
Add temporary `instructions` when standing guidance helps. A `label` changes display
only; it cannot select saved identity. Give the label as words, and Pi projects it to
one lowercase hyphenated display name, so `Task SQL work` shows as `task-sql-work`. No durable home or Memory is created.
Recorded legacy branches use `agent` with `description` and `role_prompt`.

The start receipt confirms accepted input, not the answer. The complete result
arrives later as an automatic follow-up. Continue independent work, or end the
turn when the next step depends on it. Use `inspect`/`list` for requested status
or diagnostics, not a waiting loop. Report only delivered results with their own
prompt and exact `session:<name>:<incarnation>` handle.

Temporary and durable children both become **IDLE after results**. Continue with
`agent_input` and delivery next to that exact incarnation. Delivery steer guides
only an active input; it never aborts or becomes next. `agent_stop` and parent shutdown
close the process. The bounded next queue preserves input-result IDs. Temporary context disappears with the
parent Pi and cannot be promoted or recovered by defining the name later.

## Disk-defined identity

A valid canonical `agent.md` is the only durable identity declaration. A user
may author it or explicitly authorize a library definition operation; the
model tools cannot create one. It has no `persistent`, `memory`,
`worktree` or promotion parameters.

Definition locations are `<agent-dir>/agents/<name>/agent.md`,
`<project>/.pi/agents/<name>/agent.md` and
`<project>/.pi/agents/<name>.local/agent.md`. Project-local > project > user >
session precedence supplies the standing role and tool ceiling. Inline input
cannot replace a disk role. Select it explicitly with identity; missing identity
fails, and temporary instructions cannot accompany it. Explicit tools may narrow it, including to `[]`,
but may not widen it or turn that identity into an amnesiac temporary run.

All disk roles have private capability Memory, ordinary scratch and project-scoped
Pi history under `<agent-dir>/agents/<name>/`. Project definitions do not create a
user `agent.md`. Derived directories and state never declare identity. Durable
data can survive shutdown; a process, exact handle and live context cannot survive
its parent Pi. Later starts use a new incarnation even when private history resumes.

Use only `name`, `description`, `tools`, optional `model` and `verify` frontmatter.
The Markdown body supplies standing instructions; there is no Memory opt-in.

## Role anatomy

- Purpose: what this child should accomplish and when to choose it.
- Method: a short procedure or judgment criteria for its work.
- Scope: which files/resources it may affect and which it must leave alone.
- Evidence: observations and safe checks its answer should include.
- Output: a nonempty final answer with findings, verification, blockers and limits.

Canonical built-ins are `read`, `bash`, `edit`, `write`, `grep`, `find`, `ls` and
`powershell`. No role implicitly receives all parent tools. A reviewer normally
needs `read`, `grep`, `find` and `ls`; grant a shell only for necessary safe
verification. An implementer also needs `edit`/`write` as appropriate.

A durable `workspace/` is ordinary scratch, **not a project checkout**. Editing
project files changes the original working tree directly, with no Git isolation,
automatic commit or rollback snapshot. Parallel children must honor explicit file
ownership. `bash`/`powershell` can write and access whatever the OS user can access;
a prompt, tool allowlist or scratch folder is not containment.

Keep Memory capability-focused: methods, criteria, applicability and limits.
Project facts and history stay in Project Memory. Memory action=append creates
or replaces a same-name capability entry under the effective write grant. Read-only
execution grants cannot append entries, but may write unaccepted proposal files
under a narrow explicit exception. A proposal is evidence for separate
continual-learning or human review, never automatic acceptance. Tool availability
or loader activation does not authorize delegation. A cancelled caller wait after
dispatch does not close the resident or permit duplicate input; inspect its exact
handle before retrying.
