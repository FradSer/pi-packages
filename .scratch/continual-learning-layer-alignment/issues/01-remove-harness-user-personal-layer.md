# 01 — Remove the harness user-personal layer

**What to build:** Harness configuration and commands use exactly user shared, project shared, and project personal ownership layers, with no discovery or targeting of a user-personal file.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Harness precedence is project personal over project shared over user shared.
- [ ] The removed user-personal file is ignored and absent from diagnostics.
- [ ] Global/user command flags target user shared.
- [ ] BDD, tests, and documentation describe exactly three layers.
