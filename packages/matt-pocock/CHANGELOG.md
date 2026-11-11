# pi-matt-pocock

## 0.3.0

### Minor Changes

- 38a8cd9: Require a recommended option on `matt_pocock_ask` and always run a deadline that adopts it, so a question can never wait indefinitely.
  
  `recommended` is now required and must copy one offered option; a call without it is refused before any dialog opens. Every ask arms one deadline (default 60 seconds, maximum 3600) that dismisses the selection and the custom-answer input through their abort signals, then returns the recommendation as the answer with `source: "timeout_recommended"`. Escape, cancellation, abort, no UI, and a blank custom answer still leave the decision pending and never adopt the recommendation. For an approval-required external or destructive action, recommend the option that does not act, because the deadline adopts it.
- e86a44f: Refresh the selected Matt Pocock procedures against upstream commit d81f3a183412e71a5b1e84ca21bc1a35eea03a60, adapt the GLOSSARY convention for Pi, and expose the promoted PR-body and retrospective procedures through the existing command. Preserve local compatibility procedures and Pi-specific workflow guidance.
  
  Allow upstream revision roles to share a commit and support isolated selection metadata for verification without rewriting workspace files. Add actual Pi v1 runtime coverage for catalog workflows, session restoration, terminal decisions and menus with a deterministic local provider.
  
  Keep CONTEXT-FORMAT as a glossary reference alias for persisted sessions, align package-local development dependencies to Pi 1.0.0, and typecheck all live fixtures against the same SDK.
- b3daa7f: A user-invoked capability such as grill-me is now reachable when the user asks for it.
  
  Eight of the twenty-one standalone capabilities were recorded as `invocation: "user"`, and `modelStandaloneCapabilities()` was the single source for both the `matt_pocock_workflow` capability enum and the injected capability catalog. Those eight ids were therefore absent from the tool schema and from the system prompt. A user who typed "grill me" gave the model no entry to route to, so the package was silently never called. The gap was hard to see because `grilling` is model-reachable, so the model could still interview the user by an improvised route.
  
  **What changed**
  
  - `catalog.ts` gains `userStandaloneCapabilities()`, the counterpart to `modelStandaloneCapabilities()`. Both derive from the recorded `invocation` mode, so the catalog stays the only source of capability visibility.
  - `matt_pocock_workflow` gains a `user-capability` mode whose enum is exactly the user-invoked capabilities. It resolves the same procedure bundle as capability mode and creates no persistent workflow state.
  - The injected guidance now carries a "User-invoked capabilities" section naming each one with its exact call, plus the rule that the model runs one only when the user explicitly asked for it. `mode: capability` still rejects a user-invoked id and `mode: user-capability` still rejects a model-reachable one, so the two sets stay disjoint and the upstream `disable-model-invocation` intent is preserved.
  - `grill-me`, `handoff`, and `improve-codebase-architecture` gain catalog descriptions, so the `/matt-pocock` menu and the prompt list stop falling back to a bare id.
  
  **Verification**
  
  The real-Pi runtime matrix now issues a `user-capability` call for all eight user-invoked capabilities and one `mode: capability` call that must be rejected, raising the run from 271 to 280 real tool executions with 4 expected rejection cases. `packages/matt-pocock/tests/test_user_capability_routing.py` covers the public seams: the tool schema, the injected prompt, the delivered dependency closure, and both rejection directions.
  
  `tests/e2e/matt_pocock_grill_me.py` is the repository E2E case. It starts the real Pi CLI against the package runtime fixture and completes grill-me through both entry points: the `/matt-pocock` menu selection, and the model gateway in `user-capability` mode. Each case must deliver the `grill-me` and `grilling` bodies, and the gateway case also asserts that autonomous mode still refuses the capability. `tests/test_matt_pocock_grill_me_e2e.py` gates that runner and the recorded result in `tests/e2e/matt-pocock-grill-me-results.json`.
  
  `user-grill-me-model-routed` is the real-model regression. Against a live model it shows the defect and the repair directly. With the fix, three of three runs recorded `{"mode":"user-capability","capability":"grill-me"}` with no errors. Against the unfixed source the same case fails, and the recorded call is `{"mode":"capability","capability":"grilling"}`: with grill-me absent from its world, the model substituted the sibling capability and grill-me was never delivered. Both outcomes are `awaiting_user`, which is the expected terminal status for a grilling case because the procedure ends by asking the user a decision.

### Patch Changes

- 8662e95: Use additive run-start prompt contributions instead of complete prompt overrides. Do not use custom messages for context injection. Handle custom startup without a user prompt. Keep unrelated workflow records and authorization checkpoints.
- e86a44f: Dismiss pending decisions and menus when workflow state or session context changes, and prevent stale selections from operating on a replacement work item. Reject malformed control commands without changing active work.
  
  Preserve literal option labels, whitespace-bearing recommendations, and legacy delivery tracking. Validate native dialog responses, buttons, and timer bounds, with regression coverage for catalog-derived resource graphs and actual Pi v1 UI races.
- e86a44f: The package configuration now lives at `matt-pocock.json` in Pi's agent directory, resolved through Pi's own agent-dir lookup.
  
  The file was read from a hardcoded `~/.pi/agent/pi-matt-pocock.json`, so it ignored `PI_CODING_AGENT_DIR` and used a `pi-` prefix that no other Pi package follows. `defaultConfigFile()` now returns `join(getAgentDir(), "matt-pocock.json")`, matching how `vision.json`, `recap.json`, and `plan-mode.json` are located.
  
  **@pi-matt-pocock**
  
  - `matt_pocock_ask` reads `matt-pocock.json` from the agent directory: `~/.pi/agent/matt-pocock.json` by default, and `$PI_CODING_AGENT_DIR/matt-pocock.json` when that variable is set (tilde-expanded, as Pi does everywhere else).
  
  Renaming the file is a one-line action for anyone who opted in to native dialogs:
  
  ```bash
  mv ~/.pi/agent/pi-matt-pocock.json ~/.pi/agent/matt-pocock.json
  ```
  
  The `PI_MATT_POCOCK_CONFIG_FILE` override is unchanged and still takes precedence.
- 7cccf2f: Return the full decision question and the selected answer in the model-facing ask result. Format the answer as a block quote, and remove the `(Recommended)` marker from the chosen answer while retaining the original option in the selection UI.
- e86a44f: Use readable catalog labels consistently in standalone starts, procedure messages and reference lifecycle rows, including historical results. Normalize reference display labels while preserving resource ids and verbatim user tasks.
  
  Transition menus use readable route and destination phase titles matching lifecycle rows while preserving command identifiers.
- 38a8cd9: Reorganize the package files so the directory layout matches the catalogue's own kinds, and gather the upstream-sync and test surfaces.
  
  - `procedures/` holds the 27 loadable capabilities, `references/` the 27 on-demand documents and `assets/` the 2 templates. `src/catalog.ts` derives each resource path from its kind and `src/resolver.ts` loads through it, so `resolveProcedureBundle` keeps its interface. Cross-directory Markdown links became relative, and the link rewriter accepts a relative prefix while leaving external URLs untouched.
  - `upstream/` holds `UPSTREAM.md`, `upstream-selection.json` and `check-upstream-sync.mjs`; the package-root copies and `scripts/` are gone.
  - `tests/` keeps the 26 pytest modules with their helpers, `tests/live/` holds the eight real-Pi acceptance harnesses with the shared `live_pty.py` helper and their seven `.ts` fixtures, and `tests/reports/` holds the four evidence documents.
  - `procedures/hitl-loop.template.sh` was unreachable: no catalogue edge produced it, although `diagnosing-bugs` tells the model to drive a human with it. It now has an inbound edge and a link in that text.
  - The packed manifest, every documented run command and the layout-pinning catalogue test were updated; the catalogue remains the single source of truth.
  - `tests/live/restore_live.py` now passes. Its fixture recorded the system prompt from the provider context, which Pi 1.2 no longer fills, so the restore contract is observed where it is actually carried: the `matt_pocock_workflow` prompt section this extension injects. The assertions are unchanged in substance - the restored turn receives the inactive catalogue and no active guidance - and the fixture typecheck now globs `tests/**/*.ts` so the moved fixtures stay compiled.
  - The link rewriter accepts only a bare resource name or a `./`/`../`-relative path, so a URL, a protocol-relative host or a bare host path can never be rewritten, and a rewritten link keeps its anchor and title.
- 5116108: Show every Matt Pocock lifecycle fact in the collapsed row. A workflow start shows only the readable phase title, with no hidden route field. A cancellation shows `reason · <stored reason>` inline. Structured ask rows show timeout, no-UI, and custom-input metadata below the answer. Ctrl+O no longer reveals a field body on any row.
- e86a44f: Clarify gateway JSON shapes and require literal recommended option labels after real Pi model calls exposed repeated argument errors.
  
  Keep glossaries free of implementation details and unresolved policy, treat unconfirmed scope creep as Spec REWORK, distinguish questionnaire facts from targets, and separate measured prototype results and sourced design requirements from proposed policies.
  
  Require reachable API interleavings for concurrency review claims and report retained cleanup findings as PARTIAL after complete developer journeys exposed misleading verdicts.
  
  Include exact callable transition and reference shapes in every workflow state contract, reuse previously approved requirements, and separate predicate-level evidence from compound guard outcomes.
  
  The isolated live verifier now waits for Pi settlement, verifies required workflow stages and work item continuity, covers cached and in-flight independent keys, and maintains bounded call allowances across follow-up turns.
  
  Expand real developer-task acceptance across eight additional concerns and make TDD preserve adjacent public boundaries and report observed verification evidence.
  
  Keep teaching requests in existing application repositories from silently turning into source-code repairs.
  
  Include exact completion/cancellation calls in every workflow state contract so finished work is not stranded by a transition-only call list.
  
  Generate concrete gateway JSON calls from each catalog entry and clarify schema-error recovery rather than silently applying an unloaded method.
  
  Expose root object properties and full mode/action enums in tool schemas while retaining exact discriminated branch validation for provider interoperability.
- 38a8cd9: Sync the bundled procedures with `mattpocock/skills` at `49dd158d` (tag `v1.3.1`), adopting upstream content and typography, and classify the new upstream skill.
  
  Content adopted: `grilling` now carries the design-tree, frontier and rounds model with the required recommendation, `pr` and `retro` adopt the upstream body template and retrospective categories, and `diagnosing-bugs` (prove a forced mutation landed), `implement` (fetch a passed ticket reference), `tdd` (name what each seam catches and misses), `teach` (workspace paths, varied quiz answer position), `setup-matt-pocock-skills` (create the tracker labels the repo lacks), `handoff` (resolve the temp directory), `wait-what` (`GLOSSARY-MAP.md`), `to-tickets` (native blocking edges) and `wayfinder` (wayfinder labels are the only labels, real cross-reference ids) carry their upstream changes.
  
  Typography adopted: 19 procedures and 17 supporting reference files now use the upstream punctuation (em dashes become colons, commas, semicolons or parentheses, and `*italics*` becomes `_italics_`), so `wait-what` is byte-identical to upstream and only content differences remain elsewhere. Supporting references and assets are matched to their upstream counterparts by name because `upstream-selection.json` classifies `SKILL.md` files only, and UPSTREAM.md now records that rule. `pr` carries the `show-me` attribution that upstream keeps in its separate `CREDITS.md`. Local Pi policies stay: the required-recommendation question tool, the written-deliverable rule, and the harness integration lines.
  
  `upstream-selection.json` records the reviewed commit `49dd158d`, the tag `v1.3.1` resolving to `24fe0ef7`, and excludes the new `chief-of-staff` skill as an experimental in-progress skill that needs recurring schedules and background subagent orchestration. `UPSTREAM.md` notes that the newest tag can predate the reviewed tree.
  
  Two semantic guards now assert the local question policy (required recommendation, deadline adoption) and the written-deliverable rule in the delivered bundles, so a later sync cannot drop them silently.
- 97e9add: Sync the `mattpocock/skills` selection to `v1.3.2` and the three commits after it (checked tree `4ae2317`).
  
  - Classify the new `software-factory` in-progress skill as excluded, and refresh the `implement-spec` and `chief-of-staff` exclusion reasons against the checked tree.
  - Adopt the upstream fresh-context-window guidance for delegated work in `code-review`, `research`, `improve-codebase-architecture`, `wayfinder`, `grilling`, and `DESIGN-IT-TWICE`, keeping the local teammate-or-current-context rule.
  - Bring the setup procedure's legacy `CONTEXT.md` migration and reachable-repo requirement, plus the GitHub and GitLab tracker conventions, up to the checked tree.
  - Run the package on bun only: `bun pm pack` for the packed-package fixture, `bun x tsc` for the live TypeScript fixtures, and bun commands in the contributor docs and reproduction notes.
  - Normalize the two recorded model transcripts to bun workspace wording. All hash, status and count fields stay unchanged; these remain historical evidence, not a new run.
  
  Verified with the sync checker against a real upstream checkout, the package test suite, typecheck and packing, with no package-manager shim. The repo-wide bun-only test-tooling guard lives in `tests/test_bun_only_test_tooling.py`.
- e86a44f: Isolate workflow state per Pi v1.0 extension instance and restore active instructions after tree navigation and compaction. Reject incompatible newest records, phase mismatches, ambiguous catalog aliases and eager dependency cycles. Validate cumulative reference bundles before persistence and support nested standalone disclosure chains.
  
  Keep cancelled or aborted questions pending, validate recommendation membership and tool schemas, propagate dialog cancellation, require boolean native-dialog opt-in, and share native subprocess cleanup. Verify user-message backgrounds using the current Pi theme rather than a fixed RGB value.
  
  Simplify decision outcomes across native and Pi UI adapters, share workflow transition handling and native text-dialog execution, and avoid redundant procedure resolution. Consolidate test subprocess/registration harnesses, duplicate catalog checks and package packing while retaining distinct regression assertions.
  
  Use an explicit abort deadline for TUI timeout recommendations so elapsed clock readings cannot turn cancellation into consent. Preserve literal option labels when custom input is disabled. Further consolidate registration fixtures and use registered tool metadata for description checks.
  
  Reuse the common Pi registration harness in delivery and lifecycle tests, combine message and rendering assertions per scenario, and share persisted-record identity validation without changing accepted states.
- 53cb34f: Stop `setActiveTools` toggle writes from deactivating tools the harness has not published yet.
  
  `setActiveTools` is an allowlist write: the caller passes the complete set the
  model may call, and anything absent is deactivated for the rest of the session.
  Every extension that toggled a tool read the active-tool snapshot, adjusted it,
  and wrote it back, so a snapshot that had not yet reported an extension's own
  registrations silently erased them. `pi-matt-pocock` then kept delivering routing
  prompts that name `matt_pocock_workflow`, instructing the model to call a tool it
  could not see.
  
  `@fradser/pi-kit` gains `setOwnedTools`, which re-asserts the extension's own
  tools instead of trusting the snapshot, and all five call sites now use it:
  `pi-matt-pocock`, `pi-monitor`, `pi-utils` sessions and worktree-session, and
  `@fradser/pi-agent-teams`' worker disclosure. Repeated identical writes are now
  idempotent rather than accumulating a duplicate entry.
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [ff9b7ff]
- Updated dependencies [a3ee3e3]
- Updated dependencies [2bba220]
- Updated dependencies [a0923d8]
- Updated dependencies [426ef90]
- Updated dependencies [6603d43]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [6416992]
- Updated dependencies [fc0d801]
- Updated dependencies [53cb34f]
- Updated dependencies [ceb8e23]
- Updated dependencies [842b92e]
- Updated dependencies [2116b41]
- Updated dependencies [b3daa7f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [842b92e]
- Updated dependencies [e86a44f]
- Updated dependencies [53cb34f]
- Updated dependencies [53cb34f]
  - @fradser/pi-kit@0.6.0

## 0.2.2

### Patch Changes

- ad80757: Keep a multi-step workflow running to completion instead of breaking off partway.
  
  The active-workflow guidance told the agent to "yield with the workflow still active" whenever
  only teammate results remained outstanding, so any long task stopped at the first checkpoint it
  could justify. It now says to drive the current procedure to its end in this turn and not to end
  the turn to ask whether to continue, and it reserves yielding for work that genuinely depends on
  an external actor, an unreachable teammate result, or exhausted context. Completion is still
  gated on applicable verification and returned blocking reviews.
  
  A workflow step also no longer re-delivers procedure bodies the session has already been shown.
  Every transition re-sent the active procedure's whole dependency closure — the `implement`
  bundle is 14.5 KiB of `implement` + `bdd` + `tdd` — so repeated transitions spent the context the
  work itself needed and ended long tasks for want of room rather than want of work. Each
  procedure is now delivered once per session and a transition carries only the newly active one,
  while a session restore still re-delivers the full context because a restore is a context
  boundary.
- 8f0095d: Persist a started workflow's state exactly once, carrying the procedure-delivery set that its first step shows. Starting a workflow previously wrote two state entries — one without the delivery set and one with — so a restored session read two beginnings and a consumer comparing the persisted record against the delivered message details saw them disagree. The guidance sentence also names the contract term the delivery bundles use, "blocking reviews", instead of a singular rewording of it.

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
