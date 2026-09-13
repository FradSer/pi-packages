---
name: pi-kit-package-owned-agents
description: Pi packages own their sub-agent prompts inside the published package and run child Pi workers through pi-kit's shared package-agent runtime with minimal discovery
type: project
---

## Why

A package's research/planning child is part of that package's published surface, not user or repository configuration: the prompts were previously discovered from a repository-level `.agents/` directory, which the user rejected in favour of package ownership plus one shared runtime in `@fradser/pi-kit`.

## How to apply

- Ship the child's prompt inside the package and list it in `package.json` `files` (for example `@fradser/pi-context` publishes `agents/context-researcher.md`).
- Load it through pi-kit's `createPackageAgentRun({ packageRootUrl, resourcePath, namePrefix, toolCallId, request, requestLabel })`: the resource path must stay package-relative and inside the package root (realpath + symlink escape checks), and the returned `prompt` is the bundled agent text plus the caller's request.
- Give the child one stable identity per tool execution with `subagentDisplayName(prefix, toolCallId)` (`@context-<hash>`), and render the lifecycle rows plus the above-editor status widget with that same name.
- Start the child through `runPiWorker({ ..., minimal: true })`, which adds `-ne -ns -np -nc --no-themes` so the child loads no extensions, skills, prompt templates, context files, or themes. `runPiWorker` still has no wall-clock timeout; abort and process shutdown are the only cancellation.
- Contract coverage: `packages/context/features/native-tool-runtime.feature` (bundled agent, minimal child, named sub-agent started row, live status widget).

## Related

[[project_pi_kit_internal_dependency]] [[project_monitor_display_pattern]] [[project_plan_mode_main_session_first]]
