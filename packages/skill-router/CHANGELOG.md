# pi-skill-router

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
