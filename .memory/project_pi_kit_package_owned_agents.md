---
name: pi-kit-package-owned-agents
description: Pi packages own their sub-agent prompts inside the published package and run child Pi workers through pi-kit's shared package-agent runtime with minimal discovery
type: project
---

## Why

A package's research/planning child is part of that package's published surface, not user or repository configuration: the prompts were previously discovered from a repository-level `.agents/` directory, which the user rejected in favour of package ownership plus one shared runtime in `@fradser/pi-kit`.

## Status

The user has stated that the markdown-resource-as-prompt pattern (`createPackageAgentRun` loading `agents/*.md`) should not be used in pi-kit; instead callers should construct optimized prompts inline. Migration away from this API is pending due to cross-package dependencies (`context`, `continual-learning`). Until migrated, the API remains in the codebase and callers still use it.

**Rationale for full removal (not rename):** `createPackageAgentRun` uses "Agent" in its name but provides none of the features that `agent-teams`' Agent Definition system provides (session, memory, agent definition, scope, lifecycle, inbox, work item, persistent identity, worktree). It is conceptually just "load a package-relative Markdown file as a prompt string plus display metadata." The naming and directory structure (`agents/*.md`, `@<name>` display) implies it belongs to the same mechanism as `agent-teams`, causing confusion. The correct action is to remove it entirely after migrating all callers, rather than renaming.

**Intended replacement pattern:**
- Inline prompt constants or builder functions within the caller package (e.g. `const RESEARCH_PROMPT = "..."; function buildPrompt(query) { return RESEARCH_PROMPT + "\n\n" + query; }`).
- Separate display constants for name and path (e.g. `CONTEXT_AGENT_NAME`, `CONTEXT_AGENT_PATH`).
- Direct call to `runPiWorker({ prompt, tools, minimal: true })` with no intermediate `createPackageAgentRun` wrapper.

## How to apply

- Ship the child's prompt inside the package and list it in `package.json` `files` (for example `@fradser/pi-context` publishes `agents/context-researcher.md`).
- Load it through pi-kit's `createPackageAgentRun({ packageRootUrl, resourcePath, toolCallId, request, requestLabel })`: the resource path must stay package-relative and inside the package root (realpath + symlink escape checks), and the returned `prompt` is the bundled agent text plus the caller's request.
- Give the child one fixed package-level identity (e.g., `CONTEXT_AGENT_NAME = "conext-research"` for the context package) rather than a per-tool-call dynamic name; every invocation of the same package's child uses the same `@<name>` in both the started row and the status widget. The dynamic `elegantContextAgentName` function with adjective/noun lists has been removed.
- Start the child through `runPiWorker({ ..., minimal: true })`, which adds `-ne -ns -np -nc --no-themes` so the child loads no extensions, skills, prompt templates, context files, or themes. The child runs with `--no-session` and retains no agent memory or agent-teams state between invocations. `runPiWorker` still has no wall-clock timeout; abort and process shutdown are the only cancellation.
- **Retry on empty answer**: when the child exits 0 but its JSONL output contains no textual final `message_end` assistant message, append `FINAL_ANSWER_RETRY_INSTRUCTION` to the prompt and call `runResearchChild` once more (recursive, `finalAnswerRetry = true`). Update the status widget to "Retrying final answer..." before launching the retry. Only if the retry also returns empty text does the tool throw `"returned no answer after retry"`. A failed or cancelled child does NOT trigger retry.
- Contract coverage: `packages/context/features/native-tool-runtime.feature` (bundled agent, minimal child, fixed-name stateless started row, live status widget, empty-success retry scenario, failed-child no-retry).

## Architectural boundary

- **agent-teams**: real Agents with definitions, lifecycle, scope hierarchy, worktree isolation, and persistent identity.
- **pi-kit `runPiWorker`**: one-shot stateless Pi workers (no session, no memory, no agent-teams state).
- **Package callers (context, continual-learning)**: use inline prompts + `runPiWorker` directly; no `PackageAgentRun` intermediary.

## Related

[[project_pi_kit_internal_dependency]] [[project_monitor_display_pattern]] [[project_plan_mode_main_session_first]]
