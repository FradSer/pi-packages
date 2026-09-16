---
name: pi-kit-package-owned-agents
description: Pi packages own typed prompt builders and neutral prompt resources while pi-kit owns only the one-shot worker runtime
type: project
---

## Why

A package's research/planning child is part of that package's published surface, not user or repository configuration: the prompts were previously discovered from a repository-level `.agents/` directory, which the user rejected in favour of package ownership plus one shared runtime in `@fradser/pi-kit`.

## Status

The misleading package-Agent helper has been removed from pi-kit with no compatibility wrapper. Package prompt semantics now stay with their owning packages; pi-kit exposes only the one-shot process adapter.

- Context uses `extensions/context-prompt.ts` to treat internal `prompts/context-research.md` as a reference protocol and build a task-specific review prompt from the actual query and working directory. The Markdown path is not an execution identity; the UI renders `[context] research started · <research query>`, a `[context] researching` row on toolPendingBg while the child streams progress, and a compact expandable `[context] researched` row on toolSuccessBg when settled.
- Continual Learning keeps its substantial planner protocols under `prompts/` and binds them through typed builders in `extensions/planner-prompts.ts`.
- Builders perform literal nonrecursive replacement and reject missing, unknown, or unresolved placeholders.

## How to apply

- Keep prompt resources and typed binding rules in the consumer package.
- Use neutral `prompts/` or `procedures/` paths for one-shot worker protocols; reserve `agents/` for real Agent Definitions.
- Pass the complete prompt directly to `runPiWorker({ prompt, tools, minimal: true })`, or to a package-owned low-level child adapter when it needs additional lifecycle controls.
- `runPiWorker` adds `--no-session`; minimal mode also disables extension, skill, prompt-template, context-file, and theme discovery. It provides no Agent identity or memory.
- Context retries once only when a successful child returns no textual final answer. The retry receives the complete original request and explicit completion requirements without depending on hidden reasoning or the prior child state. Failed or cancelled children do not retry.
- Contract coverage lives in `packages/context/features/native-tool-runtime.feature`, `packages/continual-learning/features/`, and their package tests.

## Architectural boundary

- **agent-teams**: real Agents with definitions, lifecycle, scope hierarchy, worktree isolation, and persistent identity.
- **pi-kit `runPiWorker`**: one-shot stateless Pi workers (no session, no memory, no agent-teams state).
- **Package callers (context, continual-learning)**: own typed prompt builders and pass complete prompt strings to their worker adapters.

## Related

[[project_pi_kit_internal_dependency]] [[project_monitor_display_pattern]] [[project_plan_mode_main_session_first]]
