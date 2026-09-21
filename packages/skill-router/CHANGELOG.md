# pi-skill-router

## 0.2.2

### Patch Changes

- Updated dependencies [52e25f9]
  - @fradser/pi-kit@0.5.1

## 0.2.1

### Patch Changes

- 9cabb0d: Bump every package by one patch version.
- efd5641: Declare the pi core packages these extensions already use as `"*"` peer dependencies instead of resolving them by hoisting, per pi's package guide: `typebox` for pi-kit, impeccable, matt-pocock, and utils; `@earendil-works/pi-ai` for plan-mode, recap, and skill-router; `@earendil-works/pi-tui` for plan-mode, skill-router, and vision; and `@earendil-works/pi-coding-agent` for pi-kit, whose best-effort worker CLI probe resolves it at runtime. `import type` counts because pi packages ship TypeScript source that a consumer's type-checker must resolve. impeccable no longer bundles `typebox` in `dependencies`, since pi provides core packages. A pi-kit check now fails when a package uses a core package without declaring it as a `"*"` peer or when a core package ships as a dependency.
- ac83f4e: Wait asynchronously for collection registry locks and propagate cancellation from the loading overlay through summary generation. Cancelled operations leave other owners' locks and registry state intact. Close cancelled overlays promptly while authentication or model responses are pending, and ignore late results.
- e448729: Generate and directly save the Add collection capability summary with the active AI model from selected skill descriptions, without manual editing or confirmation. Abort installation with an error when generation is unavailable or invalid instead of substituting a deterministic fallback.
- 0b22cb0: Parse the skill-collection registry once per session instead of on every user turn. Prompt routing read and re-parsed the registry JSON during `before_agent_start`, so the parse is now keyed on the file's own identity and invalidated by an application write or any change to the file. Measured: 0.34 ms to 0.002 ms per turn with two collections installed.
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

## 0.2.0

### Minor Changes

- 1c60486: Route to externally hosted skill collections: clone GitHub skill repositories via the `/skill-router` menu, wrap selected skills as hidden prefixed leaves behind generated gateways under `~/.pi/agent/skill-router/`, expose them through `resources_discover`, and keep deterministic `before_agent_start` suggestions. The package ships no skill content and routed collections are never npm packages.

### Patch Changes

- 07f4705: Expose only one namespace-derived gateway skill for each collection, keep selected sub-skills internal with their upstream names, and route matching requests directly to their internal files. Collection installation now ignores malformed and test-fixture skills, reports interactive progress, and derives a stable `owner-repo` internal id for GitHub collections.
- 25b3787: Ignore symlinked repository metadata files such as `CLAUDE.md` while continuing to reject symlinked directories, and use the native Pi loading spinner during fetch, install, and update operations.
- fab8160: Unify package TUI notifications, lifecycle rows, panels, and widgets through shared pi-kit rendering abstractions.
- Updated dependencies [ec7d764]
- Updated dependencies [b28ef2d]
- Updated dependencies [fab8160]
  - @fradser/pi-kit@0.4.2
