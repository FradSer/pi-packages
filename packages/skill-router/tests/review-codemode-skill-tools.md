# Review brief — pi-skill-router codemode skill tools

Authoritative brief for the review and its bounded recheck. Read this before
inspecting the candidate; validate the fingerprint below first, and say so if it
does not match.

## Baseline and candidate

- Task baseline: uncommitted work tree of this repository. The task's own change
  set is `packages/skill-router/**` (plus `README.md`, `README.zh-CN.md`,
  `pnpm-lock.yaml`, `docs/adr/0010-…`, `docs/spec-…`, and
  `.changeset/skill-router-codemode-skill-tools.md`). Unrelated dirty work in
  `packages/continual-learning`, `packages/goal`, `packages/utils`, `packages/sdlc`,
  and `scripts/` is pre-existing and out of scope; it must not be inspected,
  edited, staged, or reverted.
- Requirements: `docs/spec-skill-router-codemode-skill-tools.md` plus
  `packages/skill-router/features/codemode-skill-tools.feature`, whose Gherkin
  scenarios are the acceptance criteria. Decision record:
  `docs/adr/0010-skill-router-codemode-skill-tools.md`. Vocabulary:
  `packages/skill-router/GLOSSARY.md`.
- Reviewed files: `index.ts`, `package.json`, `src/skills.ts`, `src/paths.ts`,
  `src/sync.ts` (the `gatewayContent` change), `tests/router_harness.ts`,
  `tests/test_codemode_skill_tools.py`,
  `features/codemode-skill-tools.feature`.
- **First candidate fingerprint: `9a73c9cf5868c7992276b0b0fab409e1`** — sha256 of
  the per-file `sha256  path` lines for the reviewed files above, in that order.
  This is the candidate the first review judged.
- Second candidate fingerprint: **`281d300233736e998a3b128c1ec0edda`** — same file list and
  same construction as the first.

## Prior findings and their disposition

Findings are reproduced unchanged in the review report that follows this section.

| Finding | Disposition |
| --- | --- |
| B1 — global `some()` gate suppresses the fallback for a skill whose own tool is unreachable | Accepted. Fixed: the gate resolves the match first and checks that one skill's tool. |
| B2 — containment anchored on the resolved `exposed` dir, so a symlinked `exposed` leaks | Accepted. Fixed: `exposed` must be a real directory and the leaf must resolve inside the real router root. |
| N1 — gate checks that `reachesTools` is declared, not what it answers | Accepted as a documented limit, no code change. Pi's own MCP extension decides the same way ("only when the tool of that name declares `reachesTools`"), and the alternative couples the gate to codemode's script input shape. Recorded in the ADR. |
| N2 — description and namespace instructions are captured at load | Accepted. Fixed by documentation: any collection change needs `/reload`, not only a new collection. |
| N3 — the returned body exceeds `MAX_SKILL_BODY_CHARS` by the truncation note | Accepted. Fixed by stating the invariant precisely (the bound applies to instructions; the note follows it) rather than by shrinking the body. |
| N4 — TOCTOU between the checks and the read | Accepted. Hardened: the read opens with `O_NOFOLLOW` and re-verifies the regular file on the descriptor, so a swap for a symlink cannot redirect it. |
| T1 — the feature-listing test is a doc-consistency check | No change. `tests/test_skill_router.py` already asserts the same way for `features/skill-router.feature`; repository convention overrides. |
| T2 — no scenario pins the surrogate guard | Accepted. New scenario and test. |
| T3 — no scenario pins a missing or deleted clone | Accepted. New scenario and test. |
| T4 — the oversized-body test does not pin the numeric bound | Accepted. The test now pins the exact bound. |
| T5 — gating gaps unrepresented (partial allowlist, collection added after load) | Accepted. New scenarios and tests for both. |
| T6 — harness allowlist fidelity | Accepted. `call` now resolves from the session's visible tools, so a hidden tool cannot be called through the harness; the matcher's simplification is recorded in a comment. |

## Correction delta

Changed since the first fingerprint:

- `src/skills.ts`
  - B1: `codemodeReachesSkillTools(pi, skillTools)` became
    `codemodeReachesSkillTool(pi, toolName)`; it checks one exact tool. The
    `some()` over every registered tool is gone, and `registerSkillTools` returns
    nothing again.
  - B2: `readLeafSkill` requires the real `exposed` directory and resolves the
    instruction file inside both the real router root and the real
    `exposed/collections` tree.
  - N4: a shared `readRegularFile` opens with `O_NOFOLLOW`, re-verifies a regular
    file with `fstatSync`, and reads from the descriptor; the leaf read and
    `managedFile` both use it.
  - N3: no code change. The bound stays 20000 characters of instructions with the
    truncation note after them; the wording in `AGENTS.md` and `README.md` now
    says so.
- `index.ts`: the route resolves first and the gate receives
  `skillToolName(match.collectionId, match.skillName)`.
- `tests/router_harness.ts`: the route-driving code moved into `driveRoute`; new
  `route-after-add` command (adds a collection after load and reports the
  registered tool names); `call` refuses a tool the allowlist removed; the
  matcher's simplification is documented.
- `tests/test_codemode_skill_tools.py`: 15 → 20 tests. New: partial allowlist,
  collection added after load, symlinked `exposed` directory, surrogate pair at
  the bound, deleted clone. The oversized-body test now pins the exact bound.
- `features/codemode-skill-tools.feature`: 14 → 19 scenarios, one per new test.
- `AGENTS.md`, `README.md`: the gate rule is stated per matched skill, the bound
  wording is exact, and any collection change — not only a new collection — is
  documented as needing `/reload` (N2).
- Unchanged by decision: N1 (the gate keeps checking that `reachesTools` is
  declared, as Pi's MCP extension does; recorded in the ADR) and T1 (the
  feature-listing test matches the existing repository convention).

Checks on the second candidate: `python3 -m pytest packages/skill-router/tests/
-q -W ignore` → 95 passed; `pnpm typecheck` → clean; `pnpm --dir
packages/skill-router pack --dry-run` → clean. A live Pi 1.3.0 run on this
candidate ran `searchTools("seo audit")`, called
`tools.skill_router__upstream__seo_audit({})` from inside the script (a nested
call: the tool was never declared), and answered with the token only the skill
body contains.

## Post-recheck delta

Third candidate: **`6faecc13c33b172eaeb89190e90d4465`** (same list and construction).
The recheck returned Standards pass, Spec pass, blocking count 0, with one
non-blocking test-strength finding: `startswith(complete[:20000])` pins a lower
bound, not equality, because any bound in `[20000, 36490]` still passes.

Applied as prescribed: the oversized-body test now asserts the note's exact
omitted count, `…{len(complete) - 20000} chars truncated…`. The delta contains no
production-code change — `src/skills.ts` is byte-identical to the rechecked
candidate — so the recheck's B1 and B2 conclusions carry over unchanged.

Owner-side verification that the tightened assertion can fail: with
`MAX_SKILL_BODY_CHARS` temporarily raised to 25000, the test failed with
`assert '…16491 chars truncated…' in '…'`, and it passed again after restoring
20000. The constant is confirmed back at 20000, and the full suite is 95 passed
with `pnpm typecheck` clean on the third candidate.

1. Are B1 and B2 resolved by the delta above, and does the new code introduce no
   new blocking defect? Resolved — see "Post-recheck delta" for the verdict and
   the residual limits the recheck recorded (a symlinked router root is resolved
   rather than refused, as before this change; an intermediate directory swapped
   between the checks and the open is still possible for a concurrent local
   writer, which `O_NOFOLLOW` does not cover).
2. Do the new scenarios pin what they claim, and does any new test pass for the
   wrong reason? Yes; the one looseness the recheck found was the oversized-body
   bound, tightened and mutation-verified above.

## Second post-recheck delta

Fourth candidate: **`1d2551e0915a495b5ff24634e9dcde15`** (same eight reviewed
files and construction). `src/menu.ts`, now part of the change, hashes to
`018c2a02b692a805…` on its own. Three findings the recheck left non-blocking or
as a residual were closed, because each had a real failure behind it:

- **N1, closed.** `codemodeReachesSkillTool` no longer reads the `reachesTools`
  declaration; it asks with `{ code: "await searchTools('')" }` and requires the
  answer to be `"all"` or to name the tool, mirroring Pi's word-matching
  direction. A `codemode` that declares `reachesTools` and names nothing now keeps
  the fallback. New harness state `misdeclared`; new scenario and test.
- **N2, closed.** `registerSkillTools` became `refreshSkillTools`, which the
  extension calls at load and after every `/skill-router` mutation through a
  required `refreshTools` hook the command handler supplies. It re-registers the
  desired definitions (fresh descriptions and namespace instructions) and
  withdraws names a change removed by re-registering them with `hidden` exposure,
  tracked per extension instance in a `WeakMap`. `RELOAD_HINT` now says the tools
  updated and that `/reload` refreshes the gateway command. New harness abilities:
  `menu-add` drives the registered command so the extension's own wiring runs and
  reports registered exposures; a `refresh` command withdraws after an out-of-band
  change. New scenarios and tests for install, remove, and disable.
- **N4 residual, closed.** `readRegularFile` now takes the `Stats` it validated
  and requires the opened descriptor to match that device and inode, so a
  directory swapped between the containment check and the open cannot redirect
  the read. Both callers pass their own `lstat` result.

Kept as a recorded residual: a symlinked router root is resolved rather than
refused, exactly as `loadCollections` and `managedFile` already did, and the sync
layer refuses to create one. Also recorded: the answer check couples the gate to
codemode's `code` input shape, which Pi defines.

New tests were shown capable of failing before being credited: removing
`hooks.refreshTools()` from `addFlow` made the install test fail with
`KeyError: 'skill_router__upstream__bug_diagnosis'`, and removing the withdrawal
loop made the remove/disable tests fail with `'codemode' == 'hidden'`. Both
mutations were reverted.

Checks on the fourth candidate: `python3 -m pytest packages/skill-router/tests/
-q -W ignore` → 99 passed; `pnpm typecheck` → clean; `pnpm --dir
packages/skill-router pack --dry-run` and `pnpm pack:check` → clean. A live Pi
1.3.0 run repeated the search-and-call and answered with the skill body's token.

## Third post-recheck delta

Fifth candidate: **`4c601ecc0c1a7df8331c85e7b2ef5126`** (same eight reviewed files
and construction); `src/menu.ts` is unchanged at `018c2a02b692a805…`.

The recheck returned Standards pass, Spec pass, blocking 0, with notes that were
all dispositioned:

- **An unguarded `reachesTools` call, closed.** A replacement `codemode` that
  throws when asked what it reaches aborted the handler after the routing section
  had been deleted, costing the turn its only working path. The call is now
  guarded and answers `false`, which is the conservative direction. New harness
  state `throwing`; new scenario and test, which failed first with the crash the
  finding described.
- **The misdeclared test now asserts the active state**, so it cannot pass because
  the harness failed to mark codemode active.
- **The missing half of the refresh coverage, closed.** A new test edits a
  collection's capability summary while the session is live and requires the
  existing skill tools to carry the new namespace description and gateway
  instructions; the harness `refresh` command reports both. Shown able to fail: a
  refresh that skipped names it had already registered left the old description
  and the test failed on it.
- **Kept as residuals.** The device/inode check can in theory collide with an
  inode reused inside the race window, which needs a concurrent local writer and an
  allocation collision; two extension instances would be last-writer-wins on a
  name-keyed registry, which Pi's documented loading cannot produce; a symlinked
  router root is resolved rather than refused, as before this change.
- **Reviewed and left alone.** The `selectionFlow` cardinality guard compares
  counts, not sets — correct for an add-only flow (the loop only adds to
  `selected`), so it cannot discard a swap.

Checks on the fifth candidate: `python3 -m pytest packages/skill-router/tests/ -q
-W ignore` → 101 passed; `pnpm typecheck` → clean; `pnpm --dir
packages/skill-router pack --dry-run` → clean. A live Pi 1.3.0 run repeated
`searchTools` and the nested skill-tool call and answered with the skill body's
token.

## Terminal evidence and a factual correction

After that verdict, the tool row was checked in a real interactive TUI under a PTY
(`packages/skill-router/tests/terminal-row-evidence.md`), because the change adds
a transcript row. It renders `[skill-router] loaded · upstream/seo-audit ·
ctrl+o to expand`, `ctrl+o` reveals the skill file, and the same component stays
readable after a live resize to 60x24. That check only changed documentation files
and added that evidence file: the reviewed candidate is byte-identical, so this
round's verdicts still apply.

The check found a factual error in the README and changeset, now corrected: an
allowlist match cannot declare a `codemode`-exposure tool (`_isDeclarable` accepts
only `direct` and `model-only`), so `--tools '…,skill_router__*'` keeps the tools
callable from a script but does not let the model call them directly. Only
`tool_search` loading a tool — or another orchestrator using `setActiveTools` —
declares it. The ADR now records the distinction.

## Docker acceptance

After the fourth round, the whole acceptance was repeated in an isolated container
from packed tarballs (`packages/skill-router/tests/skill_router_docker.sh`): only the
packed package loads, the package gate is 101 passed, a collection installs through
the real router path, `searchTools` ranks both skill tools and the matched call
returns the body, directory and untruncated flag, and the fallback assembly produces
the routing suggestion with no codemode call. It changed no product code; it added
`tests/skill_router_e2e.py`, `tests/skill_router_e2e_fixture.ts`, the Docker script
and `tests/docker-acceptance-evidence.md`, so the reviewed fingerprint is unchanged
and this round's verdicts still apply. The container found two environment
requirements of the existing suite — Bun 1.4.1 and a warmed corepack — which the
setup now satisfies instead of skipping any test.

## What this recheck should decide

1. Are the fourth round's changes correct: the guarded `reachesTools` call, the
   strengthened misdeclared assertion, and the new in-place-refresh test? Can the
   guard mask a real reachability answer, and does the new test pass for a reason
   other than the refresh re-registering an existing name?
2. Do the dispositions above hold — in particular, is the `selectionFlow`
   cardinality guard genuinely add-only, and are the kept residuals described
   accurately rather than optimistically?
3. Any blocking defect remaining in the change as a whole?

## Safe check scope for the recheck

```bash
python3 -m pytest packages/skill-router/tests/ -q -W ignore
pnpm typecheck
pnpm --dir packages/skill-router pack --dry-run
```

Do not run installers, do not write to `~/.pi/agent`, and do not touch files
outside `packages/skill-router`. A live Pi run with a real model is the
implementation owner's evidence and needs no repetition here.