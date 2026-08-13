---
name: pi-package-npm-naming
description: npm naming for pi packages — unscoped concise names preferred; @gitagenthq needs a paid npm org; fall back to @fradser scope only when the unscoped name is taken
type: feedback
---

When picking an npm name for a pi package, prefer a concise **unscoped** name that matches the repo (e.g. `pi-git-agent`). Fall back to the `@fradser` scope only when the unscoped name is taken. Never default to an org-scoped name that mirrors the GitHub org without checking npm org pricing first.

**Why:**
- `@gitagenthq/pi-git-agent` was chosen to match the GitHub org `GitAgentHQ`, then had to be reverted — npm requires a **paid** organization to publish under an org scope ("我必须购买才能以 gitagenthq 的名义发布"). Personal/individual scopes and unscoped names are free.
- `pi-memory` was taken by another maintainer (`jayzeng`, active, 0.4.2 at the time), so the memory package became `@fradser/pi-memory` — the user's choice after options were presented.
- All `@fradser/*` packages were verified 404 on the registry — the pi-packages suite had never been published before.

**How to apply:**
1. Check availability with the anonymous registry (no auth needed): `curl -s https://registry.npmjs.org/<name>` → `{"error":"Not found"}` means free; a JSON document means taken. `npm view` fails with 401 when the token is invalid, so the curl check is the reliable one.
2. Name ladder: (1) unscoped concise name matching the repo (`pi-git-agent`); (2) `@fradser/<name>` personal scope if the unscoped name is taken; (3) org scope only if the user explicitly accepts the paid npm org.
3. npm scopes are lowercase by spec — GitHub org `GitAgentHQ` maps to `@gitagenthq` (which is why that name existed but was rejected on cost grounds).
4. Scoped packages (`@fradser/pi-memory`) and unscoped ones (`pi-git-agent`) are both fine for `pi install npm:<name>`; local dev checkouts in `~/.pi/agent/settings.json` are unaffected by npm publishing.

**Related:** [[pi-package-npm-publishing]]
