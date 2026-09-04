---
name: pi-package-done-includes-live-install
description: A pi package is not done when repo tests pass — done means it appears in ~/.pi/agent/settings.json and survives one live pi run; uninstalled packages fail silently, producing no error, only absence
type: feedback
---

Package work in pi-packages is only complete when the package is installed into the live agent config (`~/.pi/agent/settings.json` `packages` array) and exercised once in a real pi run. In-repo pytest/tsc verification proves the code works; it never proves pi can see the package.

**Why:**
Discovered 2026-08-30 with `packages/context`: the directory was renamed `code-context/` → `context/` on 08-18, the dead settings.json entry was later cleaned up without installing the successor path, and three more rounds of development (root extension entry, keyless Exa, docs) were verified only by package tests. Result: for ~2 weeks pi never loaded the package — no startup error, no warning, the three tools and `/context` simply did not exist in any session. The only symptom was an absence ("pi never searches the web"), invisible until the user explicitly asked why the package is never used. Diagnosis was fast only because this memory system existed; detection took weeks because nothing in the flow checks for silent absence.

**How to apply:**
1. Done-definition for any pi-package behavior change: `pi list` shows the package, plus one live `pi --print` smoke run exercising the new surface (cf. vision package's installed-package verification rule). Package tests are necessary, never sufficient.
2. Directory renames/moves: update `~/.pi/agent/settings.json` in the same task as the rename, not as a follow-up. Cleaning a dead entry without installing the successor is data loss.
3. Symptom signature: a capability that "should exist" but is never used → check settings.json package list FIRST, before questioning tool descriptions, guidance text, or model behavior.
4. Live smoke pattern that works: `pi --print --mode json --model <cheap-model> "Call the <tool> ..."` and grep the JSONL for the tool call and result.

**Related:** [[stale-session-skill-paths]] [[vision-package-design]] [[pi-package-conventions]]
