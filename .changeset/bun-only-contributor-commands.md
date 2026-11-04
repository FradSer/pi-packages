---
"@fradser/pi-goal": patch
"@fradser/pi-loop": patch
"@fradser/pi-monitor": patch
"pi-sdlc": patch
"@fradser/pi-subagents": patch
"@fradser/pi-tasks": patch
---

Document the workspace's bun-only commands instead of the earlier package manager. Contributor guides, README verification blocks, BDD wording and shipped command examples now use `bun run typecheck`, `bun run check:install`, `bun pm pack` and `bun test`. Test fixtures and opt-in Docker acceptance harnesses invoke bun directly. No runtime behavior changes.
