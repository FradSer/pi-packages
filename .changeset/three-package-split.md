---
"@fradser/pi-agent-teams": major
"@fradser/pi-subagents": minor
"@fradser/pi-tasks": minor
"@fradser/pi-kit": minor
---

`@fradser/pi-agent-teams` is now a bundle of three independently installable packages, and the tool surface has changed. This is a breaking release: 1.0.0.

## The three packages

| Package | Owns | Registers |
| --- | --- | --- |
| `@fradser/pi-subagents` | child process spawn and lifecycle, the child roster, workspace isolation, environment policy, Agent Memory | `agent` |
| `@fradser/pi-tasks` | the task board: data model, status machine, dependency graph and resource rules, per-task context | `task` |
| `@fradser/pi-agent-teams` | peer messaging, notices, Agent Presence, the Team Console | `message` |

Installing `@fradser/pi-agent-teams` still gives all three tools: its manifest loads the other two extension entries. Each also works alone, and any pair works. A tool has exactly one registrant in every combination, which is what the split's own tests enumerate rather than assume.

## What a caller must change

- **`work` is now `task`.** The package was already `@fradser/pi-tasks` and the type was already `BoardTask`, so `work` was the only name contradicting the other two — and it is a mass noun, which forced a model reading `work` plus an `action` parameter to decide whether the tool performs work or registers work items.
- **`agent_event` is now `message`,** and its parameters are `to`, `body`, and `kind`. `body` avoids a caller writing `message: { message: … }`; `kind` is what the recipient owes the sender, nothing or a decision, rather than an intent the tool acts on.
- **`agent` has four actions** instead of four differently named ones: `start` (with an optional `prompt`), `inspect`, `list`, `stop`. `delegate` and `start` were the same operation dispatched twice, differing only in whether a prompt was delivered.
- **The board action set shrank from fourteen actions across two divergent schemas to five across one.** `assign`, `claim`, `release`, `abandon`, `reclaim`, `submit`, `supersede` and `get` are gone; `reopen` survives as `update status=pending` and `supersede` as `create supersedes`. A task names no owner, and there is no `assignee` parameter anywhere: a participant takes a task with `update status=in_progress`, and the caller is recorded as the holder.
- **The board status `claimed` is now `in_progress`.**
- A task failed, or an unfixable verification gate, returns to pending under a **recovery hold**, and the retry needs a stated reason. That replaces a leader-side release action: the runtime records an attempt as not delivered and nobody has to clear a state nothing can clear.
- Retained evidence moved from `errorMessage` to `result`, the field the board reads and shows.

## Why the tools are three

The test applied to every merge and split in this release was not symmetry but: *when the model judges wrong, is the mistake cheap, and is it reversible in both directions?* `agent delegate` created a direct task implicitly, so a model could not afterwards tell which mode it was in and a wrong choice was invisible. Every change above either removes a choice or makes the outcome observable.

## Not in this release

Workspace durability, Agent Memory and the child environment policy shipped earlier in the series and are described in their own changesets. The Computer Lease's sandbox profiles, budget and depth guards, task handoff transfer, and a durable Agent Inbox are deliberately absent: they are independent of the split and remain open.
