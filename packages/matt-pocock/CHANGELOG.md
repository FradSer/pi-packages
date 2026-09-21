# pi-matt-pocock

## 0.2.1

### Patch Changes

- Updated dependencies [52e25f9]
  - @fradser/pi-kit@0.5.1

## 0.2.0

### Minor Changes

- 0ea4980: Replace the flat procedure allowlist with a catalog-backed capability gateway, bounded dependency resolver, legal workflow transitions, explicit completion and cancellation, progressively disclosed active tools, standalone capability routing, and verifiable upstream selection metadata.
- 80aef33: Deliver `/matt-pocock` route starts, menu starts and transitions, standalone capability starts, freeform routing requests, and the menu's "Start a task" through the displayed `matt-pocock-procedure` message, so the transcript shows one `[matt pocock] started` block instead of posting the whole procedure text or routing prompt as a user message.
  
  Align that block with `/impeccable`: the head row carries only the label, a blank band row separates it from the body, and the body is the user's own task verbatim, or the readable phase/capability name when no task was given, on pi's native user-message band. Long lines wrap and the block never advertises expansion. Agent-invoked tool rows stay inline and compact.
  
  Extend the command input to `<route|capability> [task]`, mirroring `/impeccable <capability> [request]`: the task now reaches the procedure prompt as `User target/request:` and the transcript row, while persisted workflow state keeps route, phase, and work-item identity only. `transition <target>` and `cancel <reason>` are accepted directly, and a first word matching no route, capability, or action is forwarded verbatim instead of partially matched.
- 919504f: Add a default Start a task entry as the first option of the /matt-pocock menu. It infers the current task from recent conversation context and routes it through the relevant workflow or standalone capability without manual route selection, superseding any active workflow as a new routing request.
- 919504f: Add a local `deslop` standalone capability that removes AI slop (fabricated evidence, evidence widening, defensive clutter, mock patching, vacuous names) from a bounded change set with frozen behavior, and extend the code-review Standards axis with a cross-language AI slop baseline that skips patterns repository tooling already enforces.
- 919504f: Add opt-in native macOS dialog support for `matt_pocock_ask` via `~/.pi/agent/pi-matt-pocock.json`, with strict guards against non-macOS and SSH sessions, and a dedicated native text input window for custom answers.

### Patch Changes

- 9cabb0d: Bump every package by one patch version.
- b0231e3: Clarify agent orchestration with scoped dependency-aware assignments, one integration verification owner, candidate-bound review evidence, and a finish line that waits for blocking review results. Distinguish review Work completion from an implementation PASS, describe `verify` accurately as a reviewer prompt, and refresh candidate briefs explicitly before bounded rechecks. Review-only assignments finish with their reports rather than implementation repairs; reuse completed Work only with an authoritative current-attempt brief, otherwise create a linked bounded follow-up. Make Matt Pocock reviews proportional and support confirmed conversation requirements plus scoped uncommitted baselines without changing runtime lifecycle or persisted state.
- efd5641: Declare the pi core packages these extensions already use as `"*"` peer dependencies instead of resolving them by hoisting, per pi's package guide: `typebox` for pi-kit, impeccable, matt-pocock, and utils; `@earendil-works/pi-ai` for plan-mode, recap, and skill-router; `@earendil-works/pi-tui` for plan-mode, skill-router, and vision; and `@earendil-works/pi-coding-agent` for pi-kit, whose best-effort worker CLI probe resolves it at runtime. `import type` counts because pi packages ship TypeScript source that a consumer's type-checker must resolve. impeccable no longer bundles `typebox` in `dependencies`, since pi provides core packages. A pi-kit check now fails when a package uses a core package without declaring it as a `"*"` peer or when a core package ships as a dependency.
- 6d21149: Remove prompt text that duplicated each tool's own description. The isolated-research section keeps its trigger and no longer restates the child process mechanics, the monitor section keeps its behavior rules and no longer repeats the result-pattern, buffer, timeout, and notification mechanics, and the workflow gateway description no longer enumerates standalone capabilities that the injected catalog already lists. Agent Teams no longer advertises a template-creation action that does not exist, and its dead leader-tool disclosure hook and call sites are removed.
- 93e3302: Fix TUI rendering issue when answer contains multiple lines or tabs in matt_pocock_ask
- 2e2ef21: Route procedure cross-references through the catalog gateway instead of Pi skills. Model-reachable capabilities name matt_pocock_workflow mode capability, disclosed references name the matt_pocock_active load action, and required dependencies are described as already bundled. No procedure text calls a catalog procedure a skill, arms a skill state, runs user-invoked setup, or points at available_skills.
- 7cd9e33: Keep inactive Matt Pocock guidance positive-first: lead with starting a workflow via matt_pocock_workflow and name no unavailable tool, so the model stops calling matt_pocock_active before any workflow is active.
- 0c3aeef: Keep lifecycle expansion focused on meaningful details: workflow starts show a readable route title without a redundant phase id, cancellation shows its recorded nonblank reason, and other operations omit repeated action or subject fields. Preserve phase-only titles, model-visible results, persisted workflow state, and structured decision metadata while using pi-kit's shared width-aware expansion.
- 0c3aeef: Use the actual readable phase title in workflow lifecycle rows instead of route ids or route titles. Apply the same display rule to starts, transitions, completion, cancellation, and previously saved results without changing persisted workflow state or silent restoration.
- 34c5b62: Include model-aware instruction auditing in writing-for-agents: narrow skill triggers, minimal routers, contextual repository guidance, safe autonomy, and explicit completion boundaries.
- 5b4f51b: Align tool lifecycle TUI styling with Pi native tokens: partial results render on toolPendingBg with warning accents, settled results on toolSuccessBg with success accents, and errors on a symmetrical toolErrorBg band whose subject is the first error line with remaining lines as expandable details (no duplicated subject). Remove the renderError escape hatch so every consumer error renders through the shared band, and style interactive model-picker query input in native blue
- 552a083: Unify every transcript row on one pi-kit mechanism. Kit gains `bindLifecycleRenderers` (geometry bound once per extension: shared expand hint, wrapping, and empty call), `contentDetailLines`, the `label · value` body vocabulary (`fieldLine`/`fieldBlock`), `displayText`, and handle scrubbing (`scrubHandles` with an injectable resolver). All packages render tool and message rows through the bound renderer: no call site can drop the expand hint or wrapping anymore, expanded bodies share one dialect, and runtime handles never reach human text (agent Work/session handles become names and subjects; monitor keeps its functional monitor id). Model-facing tool content is unchanged.
- Updated dependencies [b0231e3]
- Updated dependencies [ac83f4e]
- Updated dependencies [9cabb0d]
- Updated dependencies [919504f]
- Updated dependencies [bcb0054]
- Updated dependencies [efd5641]
- Updated dependencies [919504f]
- Updated dependencies [274cc90]
- Updated dependencies [28bdae2]
- Updated dependencies [707c4c5]
- Updated dependencies [5b4f51b]
- Updated dependencies [b0231e3]
- Updated dependencies [552a083]
- Updated dependencies [efd5641]
  - @fradser/pi-kit@0.5.0

## 0.1.1

### Patch Changes

- c568d73: Resolve workspace dependency protocol on @fradser/pi-kit in published npm package to prevent EUNSUPPORTEDPROTOCOL on pi install

## 0.1.0

### Minor Changes

- 74b74a1: Publish `pi-matt-pocock` at its first public version, `0.1.0`. It exposes `/matt-pocock` as a persisted workflow harness that injects bundled plain-Markdown procedures instead of recursively discovered child skills, preventing generic skill-name collisions. Arbitrary prompts after `/matt-pocock` are forwarded to the agent with guidance to use the most applicable structured workflow instead of being rejected as invalid syntax.

### Patch Changes

- 3e50fcf: Accept the `clarify-goal` wayfinding entry point and route it to the bundled `wayfinder` procedure.
- 25b3787: Keep the structured Matt Pocock interview tool out of ordinary sessions. It now becomes available only while a workflow is active and is removed again when the workflow ends.
- 3e50fcf: Constrain workflow procedure inputs to the bundled procedure vocabulary, recover unknown route-procedure combinations with the route default and an actionable correction, and make stale restored workflow errors list valid alternatives.
- 3e50fcf: Accept the `tight-red-loop` hard-bug entry point and load the bundled diagnosing-bugs procedure while retaining the requested phase.
- ec7d764: Adopt static tool lifecycle renderers and computeScrollWindow in consumers, remove unused pi-kit exports, and restore strict local typecheck.
- fab8160: Unify package TUI notifications, lifecycle rows, panels, and widgets through shared pi-kit rendering abstractions.
- Updated dependencies [ec7d764]
- Updated dependencies [b28ef2d]
- Updated dependencies [fab8160]
  - @fradser/pi-kit@0.4.2
