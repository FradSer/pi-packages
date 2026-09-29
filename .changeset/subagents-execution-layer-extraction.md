---
"@fradser/pi-agent-teams": patch
---

The subagent execution layer moved out to a new workspace package, `@fradser/pi-subagents`, which now owns the `agent` tool and the child roster outright.

This step alone changed no behaviour. The tool surface changed later, in the same 1.0.0 release: see `three-package-split.md`. `/agent-teams` is unchanged.

**What moved**

`src/agents.ts`, `src/child-env.ts`, `src/leader-reports.ts`, `src/spawner.ts`, `src/work-context.ts`, and `src/worker-tools.ts` are now `@fradser/pi-subagents`, along with `WorkerUsage`. (`src/worktree.ts` moved here too and was later deleted, superseded by `src/workspace.ts`.) `src/types.ts` re-exports that type because `Teammate` references it.

What stays here is the coordination core: `state.ts`, `statefile.ts`, `team-machine.ts`, `worker.ts`, `tools.ts`, `ui.ts`, `tool-copy.ts`, `tool-render.ts`, `agent-actions.ts`, `recipient.ts`, `guidance.ts`, and `activity.ts`.

**Why the spawner had to change shape first**

`spawnResident` hardcoded two things belonging to this package: a `WORKER_EXTENSION` constant pointing at its own `src/index.ts`, and `WORKER_CAPABILITY_TOOLS = ["agent_event", "work"]`. Moving the spawner without removing those would have made the execution layer load this package's worker entry and grant two tools it does not register — installing `@fradser/pi-subagents` alone would have advertised a coordination surface nothing implemented.

Both are now contributed per spawn:

- `extensions: [WORKER_EXTENSION_PATH]` — `--extension` is repeatable and `--no-extensions` still loads explicit paths, so several packages can each contribute a worker extension to one child.
- `capabilityTools: WORKER_CAPABILITY_TOOLS` — `resolveWorkerTools`, `workerToolUniverse`, and `unknownWorkerTools` all take the contributed set.

Declaring capability tools with no extension to register them is refused rather than silently granting ids the child's `--tools` filter would drop.

The declaration lives in a new dependency-free `src/capability-tools.ts` because both the registration site (`worker.ts`) and the presentation site (`tool-copy.ts`) read it, and `worker.ts` imports `tool-copy.ts` — declaring it in `worker.ts` would close a cycle.

**Publishing order**

`@fradser/pi-subagents` must reach the registry before this package can publish, because the packed manifest now depends on it at an exact version (`0.1.0`, resolved from `workspace:*`). It is listed directly after `@fradser/pi-kit` in `scripts/publish-release.mjs` `PUBLISH_SCOPE`. Its first release needs the interactive bootstrap and npm trust setup, not a Changesets bump.
