# @fradser/pi-impeccable

## 0.1.0

### Minor Changes

- 3a6cdda: Start `/impeccable` capability runs as an abstract pi-kit lifecycle message (`[impeccable] started · <capability>`) instead of dumping the full procedure text as a visible user message; the procedure still enters context through the custom message. Live mode boots immediately without interviewing the user for a target or dev-server status.
- fff0b27: Port the upstream live variant mode (skill-v4.1.2): browser element picking, three generated HTML+CSS variants hot-swapped over dev-server HMR, and the full live helper runtime (boot, poll, wrap, accept, carbonize, journal recovery) with provenance for all 64 added sources. `/impeccable` now routes any freeform request as design guidance naming the shipped capabilities instead of rejecting unknown first words, and the live picker offers only shipped actions.

### Patch Changes

- ac83f4e: Limit live JSON request bodies to 1 MiB before parsing or applying events. Return an actionable HTTP 413 response for oversized bodies and discard interrupted uploads.
- 9cabb0d: Bump every package by one patch version.
- efd5641: Declare the pi core packages these extensions already use as `"*"` peer dependencies instead of resolving them by hoisting, per pi's package guide: `typebox` for pi-kit, impeccable, matt-pocock, and utils; `@earendil-works/pi-ai` for plan-mode, recap, and skill-router; `@earendil-works/pi-tui` for plan-mode, skill-router, and vision; and `@earendil-works/pi-coding-agent` for pi-kit, whose best-effort worker CLI probe resolves it at runtime. `import type` counts because pi packages ship TypeScript source that a consumer's type-checker must resolve. impeccable no longer bundles `typebox` in `dependencies`, since pi provides core packages. A pi-kit check now fails when a package uses a core package without declaring it as a `"*"` peer or when a core package ships as a dependency.
- 40df4fd: Show only resources other than the header root in the loader's expanded `dependencies` field, and omit that field for singleton bundles. Preserve reference disclosures, byte counts, script-execution status, and the complete model-facing bundle.
- 3e8a186: Render the `/impeccable` procedure start as a verbatim block on pi's native user-message band: one `[impeccable] started` head row, a blank band row, then the user's request with every authored line on its own row. Long lines wrap instead of merging, the row offers no expand hint, and the band no longer uses the tool-success green.
  
  Deliver the unmatched freeform router pack as the same displayed procedure message instead of a plain-text user message, so every `/impeccable <request>` invocation shows one `[impeccable] started` block while the capability table and routing rules stay model-facing.
- 5b4f51b: Align tool lifecycle TUI styling with Pi native tokens: partial results render on toolPendingBg with warning accents, settled results on toolSuccessBg with success accents, and errors on a symmetrical toolErrorBg band whose subject is the first error line with remaining lines as expandable details (no duplicated subject). Remove the renderError escape hatch so every consumer error renders through the shared band, and style interactive model-picker query input in native blue
- 2033c26: Remove unreachable legacy Agent control, unused internal helpers and constants,
  and the unused keyboard HID encoder (hardware commands already use via-rgb).
  Retain active entry points, shared public APIs, configuration compatibility,
  and behavioral regression coverage. Remove superseded planning documents and
  checks that only assert documentation wording or recreate implementation in tests.
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
