---
"pi-matt-pocock": patch
---

Reorganize the package files so the directory layout matches the catalogue's own kinds, and gather the upstream-sync and test surfaces.

- `procedures/` holds the 27 loadable capabilities, `references/` the 27 on-demand documents and `assets/` the 2 templates. `src/catalog.ts` derives each resource path from its kind and `src/resolver.ts` loads through it, so `resolveProcedureBundle` keeps its interface. Cross-directory Markdown links became relative, and the link rewriter accepts a relative prefix while leaving external URLs untouched.
- `upstream/` holds `UPSTREAM.md`, `upstream-selection.json` and `check-upstream-sync.mjs`; the package-root copies and `scripts/` are gone.
- `tests/` keeps the 26 pytest modules with their helpers, `tests/live/` holds the eight real-Pi acceptance harnesses with the shared `live_pty.py` helper and their seven `.ts` fixtures, and `tests/reports/` holds the four evidence documents.
- `procedures/hitl-loop.template.sh` was unreachable: no catalogue edge produced it, although `diagnosing-bugs` tells the model to drive a human with it. It now has an inbound edge and a link in that text.
- The packed manifest, every documented run command and the layout-pinning catalogue test were updated; the catalogue remains the single source of truth.
- `tests/live/restore_live.py` now passes. Its fixture recorded the system prompt from the provider context, which Pi 1.2 no longer fills, so the restore contract is observed where it is actually carried: the `matt_pocock_workflow` prompt section this extension injects. The assertions are unchanged in substance - the restored turn receives the inactive catalogue and no active guidance - and the fixture typecheck now globs `tests/**/*.ts` so the moved fixtures stay compiled.
- The link rewriter accepts only a bare resource name or a `./`/`../`-relative path, so a URL, a protocol-relative host or a bare host path can never be rewritten, and a rewritten link keeps its anchor and title.