# 02 — Add three-layer memory resolution

**What to build:** Memory loads user-shared, project-shared, and project-personal entries with filename-based precedence matching harness semantics.

**Blocked by:** 01 — Remove the harness user-personal layer.

**Status:** ready-for-agent

- [ ] Distinct entries from all enabled layers load.
- [ ] Narrower duplicate filenames replace broader entries.
- [ ] Project layers exist only at a canonical Git root.
- [ ] Existing scoped memory migrates safely to project personal.
