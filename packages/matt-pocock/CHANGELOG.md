# pi-matt-pocock

## 0.2.0

### Minor Changes

- 0ea4980: Replace the flat procedure allowlist with a catalog-backed capability gateway, bounded dependency resolver, legal workflow transitions, explicit completion and cancellation, progressively disclosed active tools, standalone capability routing, and verifiable upstream selection metadata.
- 919504f: Add a default Start a task entry as the first option of the /matt-pocock menu. It infers the current task from recent conversation context and routes it through the relevant workflow or standalone capability without manual route selection, superseding any active workflow as a new routing request.
- 919504f: Add a local `deslop` standalone capability that removes AI slop (fabricated evidence, evidence widening, defensive clutter, mock patching, vacuous names) from a bounded change set with frozen behavior, and extend the code-review Standards axis with a cross-language AI slop baseline that skips patterns repository tooling already enforces.
- 919504f: Add opt-in native macOS dialog support for `matt_pocock_ask` via `~/.pi/agent/pi-matt-pocock.json`, with strict guards against non-macOS and SSH sessions, and a dedicated native text input window for custom answers.

### Patch Changes

- 9cabb0d: Bump every package by one patch version.
- 93e3302: Fix TUI rendering issue when answer contains multiple lines or tabs in matt_pocock_ask
- 2e2ef21: Route procedure cross-references through the catalog gateway instead of Pi skills. Model-reachable capabilities name matt_pocock_workflow mode capability, disclosed references name the matt_pocock_active load action, and required dependencies are described as already bundled. No procedure text calls a catalog procedure a skill, arms a skill state, runs user-invoked setup, or points at available_skills.
- Updated dependencies [9cabb0d]
- Updated dependencies [919504f]
- Updated dependencies [28bdae2]
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
