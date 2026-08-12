# Upstream synchronization

- Repository: `mattpocock/skills`
- Upstream commit: `84fdeffd12f2ee307994d1eb6feb48173b6e0502`
- Upstream baseline: `v1.2.3` plus one documentation commit after the tag
- Checked: 2026-08-09

## Result

The latest upstream `main` is `84fdeffd` (`docs(grill-me): drop the "holds decisions" phrasing`). Its only change after `v1.2.3` is outside the registered skill tree: `docs/productivity/grill-me.md` changes wording from “until it has real decisions in it” to “until you can commit to it”. No registered upstream `SKILL.md` changed.

The Pi package therefore needs no skill-content update. It keeps its existing adapted skill files, including the local BDD/tdd split and Pi `/skill:` references. Claude-only `agents/openai.yaml` files and unregistered upstream buckets are intentionally not copied.

## Sync rules

1. Clone and compare upstream before changing files.
2. Use `cp` only for selected new or unchanged supporting files; never overwrite the adapted skill tree wholesale.
3. Preserve the local `bdd` skill and BDD-driven `tdd` implementation.
4. Remove Claude-only frontmatter, tools, paths, and invocation syntax from copied content.
5. Re-run the feature and package tests after synchronization.
