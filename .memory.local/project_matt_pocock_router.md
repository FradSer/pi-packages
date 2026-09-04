---
name: matt-pocock-workflow-harness
summary: pi-matt-pocock is an extension-only persisted workflow harness with one /matt-pocock command and internal Markdown procedures
type: project
---

## Why

Pi recursively discovers every nested `SKILL.md` below a package's declared skill root. The original Matt Pocock collection exposed generic names such as `tdd`, `code-review`, and `research`, which collide with independently installed skills; Pi keeps the first discovered duplicate. The collection is also a stateful set of routes and phases, so command-level harness orchestration is a better fit than model-only skill routing.

## How to apply

- The package is `packages/matt-pocock/`, publishes as `pi-matt-pocock`, and exposes only the extension command `/matt-pocock` from `index.ts`.
- `src/workflow.ts` owns stable route ids, allowed per-route procedures, custom session-entry state, restoration, and compact guidance. A state entry records selection, never phase completion.
- `src/index.ts` owns the single route menu, explicit commands (`status`, `transition`, `end`), arbitrary-prompt forwarding for any other arguments, the `matt_pocock_workflow` tool, procedure injection, UI status, session restoration, and concise active-phase or available-workflow `before_agent_start` guidance.
- Procedures and support files live in `procedures/`. They have no frontmatter or `SKILL.md`; upstream cross-skill calls become relative Markdown links.
- The user manually transitions phases. Deferred automation is recorded in `packages/matt-pocock/TODO.md`: completion inference, automatic sessions, automatic teammates, tool-level BDD/TDD write blocking, per-procedure commands, and a second public skill surface.
- Keep `package.json` at `pi.extensions: ["./index.ts"]` with the Pi peer dependency. Test command registration, procedure injection, state restoration, manual transition, compact guidance, package discovery, links, and TODO coverage.
- Upstream synchronization is documented in `packages/matt-pocock/UPSTREAM.md`. Preserve Pi adaptations for BDD/tdd, conversation, teammates, instruction files, and git-agent.
- The unclaimed npm name starts at `0.0.0` and the minor Changeset produces the first public `0.1.0`; publishing requires the first-release Trusted Publishing bootstrap in [[project_pi_package_npm_publishing]].

## Related

[[project_pi_package_conventions]]
[[feedback_pi_package_npm_naming]]
[[project_pi_package_npm_publishing]]
