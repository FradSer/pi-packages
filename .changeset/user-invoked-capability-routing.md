---
"pi-matt-pocock": minor
---

A user-invoked capability such as grill-me is now reachable when the user asks for it.

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