# pi-matt-pocock

## 0.1.2

### Patch Changes

- 93e3302: Fix TUI rendering issue when answer contains multiple lines or tabs in matt_pocock_ask

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
