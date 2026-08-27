---
"@fradser/pi-kit": minor
---

Converge lifecycle titles on the spec API and delete `formatToolEventLabel`: semantic verbs (`listed`, `created`, `gathered`, `to @name`) now ride `ToolLifecycleSpec.label` instead of an ever-growing kind union, so `formatToolLifecycleTitle` with the `startedToolLifecycle`/`eventToolLifecycle` builders is the only title path. Expand behavior keys off data inside `renderToolLifecycle`: any collapsed row carrying detail lines appends the configured hint and expands to reveal them. Monitor, utils/sessions/worktree-session, and pi-git-agent session_context migrate onto it.
