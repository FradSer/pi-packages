# Memory — Consolidate procedure

> **Inline procedure.** The `/memory` command, `/consolidate`, and the
> auto-trigger write this document into a temporary task file and start a fresh
> background Pi child with `--print --mode json --no-session @<task-file>`. It
> is not a skill and is never invoked as `/skill:consolidate`. `{{PKG_DIR}}` is
> substituted with the installed package directory before the child starts.
>
> A zero child exit alone does not prove consolidation. The parent reports
> success only when the JSONL stream records completed tool work, a passing full
> validator, and a G1–G8 passed gate report; otherwise it shows a diagnostic
> status without claiming memory was consolidated.

The project's memory lives in two locations that must stay **identical for safe (public) files** (idempotent):

1. **`~/.pi/agent/memory/<escaped-cwd>/`** — harness, loaded by pi, written first
2. **`.memory/`** — canonical, git-tracked, written second — **safe files only**

Resolve the harness path: `~/.pi/agent/memory/<cwd-with-/→->/` (probe both space-handling forms: `/→-`+` →-` and `/→-`+space-kept).

Private files (user preferences, credentials, PII) live in **harness only**. They must never appear as files or index lines under `.memory/`.

## Active Write

When you encounter a decision, preference, lesson, or anything worth remembering, write it **immediately** — do not wait for the /memory consolidate command.

### Before writing

1. **Search existing memories first** (`bash` search / `read` harness `*.md` by theme keywords). If one already covers the topic, **edit that file** instead of creating a near-duplicate.
2. Refuse pure operation logs: if you cannot state a durable **Why** and a reusable **How to apply**, do not write a memory. Put timelines in git/commits/docs, not memory.
3. Prefer one decision per file. Two independent decisions → two files; the same decision learned twice → one file.

### Privacy check

`.memory/` is a **public GitHub repo**. Private = secrets/PII/credentials **or user preferences / personal workflow habits**. Safe technical content → both locations. Private → harness only; harness index line ends with `(harness only)`.

### How to write

1. Write file to harness `.../memory/<filename>.md`
2. If **safe** → write identical file to `.memory/<filename>.md`. If **private** → do **not** write to `.memory/`; if `.memory/<filename>.md` already exists, **delete it**.
3. Update indexes:
   - **Harness `MEMORY.md`**: include every file (private lines marked `(harness only)`)
   - **`.memory/MEMORY.md`**: **safe lines only** — never copy `(harness only)` lines into the public index

File naming: `<type>_<kebab-slug>.md` (type: feedback, project, reference)

Format:
```markdown
---
name: <kebab-slug>
description: <one-line hook distinguishing this from similar files>
type: feedback | project | reference
---

<the fact>

**Why:** <why this decision exists>

**How to apply:** <actionable rules>

**Related:** [[other-memory]] [[another-memory]]
```

## Memory is decision log, not operation log

Every memory file answers two questions only:
- **Why** — why this decision or rule exists
- **How to apply** — what to do next time

Remove all operation history (version numbers, dates-as-timeline, "first X then Y"). That lives in `git log`. Keep only the durable rationale and actionable rules.

## MEMORY.md index format

Each line: one concise sentence, no version numbers, no date ranges, no timeline descriptions. One line per surviving file. Prefer ≤50 lines for scanability; if more files exist, **keep every entry** and group by theme — never drop entries to hit 50.

Good: `feedback_git_commit_hook_needed.md — git PreToolUse hook intercepts git add/commit, redirects to /skill:commit; only chain with git-agent commit is allowed`
Bad:  `feedback_git_commit_hook_needed.md — git PreToolUse hook intercepts git add/commit; v0.5.3 command position anchoring + two exceptions + 26 regression tests`

## Red lines

- Never drop `[[name]]` cross-links when rewriting — preserve all from the original unless the target is intentionally deleted and the reference is removed in the same pass
- Never delete a file referenced by `[[name]]` in another memory file unless the reference is also removed
- **`rm` only under the harness memory directory or `.memory/`** — never elsewhere
- Never publish private content to `.memory/` (file body or index line)

---

## Consolidate (via /memory menu, /consolidate, or auto-trigger)

User-invoked via the /memory menu or /consolidate, or **auto-triggered** by the
extension when the session context fill reaches `consolidateAtContextFraction`
of the active model's context window (default 0.4 = 40%, based on research that
long-context quality degrades from ~40-50% fill; 0 = off, persisted in
`~/.pi/agent/memory/settings.json`). It fires once per fraction boundary
(40%, 80%, …) after a real user turn (`input` source "interactive") in a TUI
session, so the consolidation run itself never re-triggers.
Default failure mode of a weak run is **cosmetic tidy while leaving thematic
redundancy and factually dead notes**. This procedure is fail-closed against that.

**Default behavior:** the run starts by capturing durable content from the current
session context into memory (Step 0 below), then consolidates existing memory.
If the session has no memorable content, capture is skipped and consolidation runs
directly. To skip capture explicitly, invoke the /memory consolidate with "no-context".

Work order: Step 0 session capture, then harness first, then sync to `.memory/`.

### Step 0: Session context capture (default)

Before touching existing memory, review the **current session context** — the
active conversation in your context window, including compaction summaries and
all messages that preceded this invocation. If relevant history was compacted or
predates your window, read the tail of the current session file under
`~/.pi/agent/sessions/--<cwd-with-/-→-->--/` (`/session` in interactive mode shows
the exact path); it is JSONL — one JSON entry per line with `role`/`content` fields.

1. Scan the conversation for **durable** content, applying the **Before writing**
   checks from Active Write (search existing memories first; refuse ops-only logs;
   one decision per file):
   - **Decisions** — architecture/tech choices, naming, process or CI decisions made or confirmed this session
   - **User preferences and corrections** — "always/prefer/never" statements, style or workflow preferences, feedback on approach
   - **Lessons and gotchas** — root-cause findings, surprising tool/library behavior, mistakes to avoid
   - **Repo/tooling facts** — reusable non-obvious facts about this project discovered this session
2. For each candidate that passes the checks, write it **immediately** with the
   **Active Write** procedure (harness first; safe → also `.memory/`; private → harness only).
3. If nothing passes the checks (empty session, or purely operational exchanges
   with no decisions/preferences/lessons), record that and continue directly to
   the consolidation below — do not invent memories.
4. Files written in Step 0 are ordinary memory files: they join the inventory,
   cluster map, and staleness pass that follow, exactly like pre-existing files.

### CRITICAL: Mutation freeze until planning artifacts exist

**Do not `write`, `edit`, or `rm` any memory file** until all three artifacts exist in this conversation
(Step 0 session-context captures are exempt — they follow the Active Write procedure and are folded into the inventory):

1. **Inventory** — complete name list of harness `*.md` and `.memory/*.md` (including both `MEMORY.md`)
2. **Cluster map** — every non-index file appears in exactly one theme cluster
3. **Staleness table** — every non-index file has a rubric verdict (step 4)

After ground-truth probes (step 5), also hold a **ground-truth table** with tool-observed paths (`path → found|missing|updated`) before applying claim fixes. Fabricating these tables without `read` / bash grep / `find` / `ls` is a failed run.

### CRITICAL: Machine validator (cannot self-attest past this)

Write (via Pi `write`/temp files) inventory / cluster / staleness / report to temp files, then run:

```bash
# Pre-mutation (lift freeze only if exit 0)
python3 "{{PKG_DIR}}/scripts/validate-consolidate.py" \
  --inventory /tmp/mem-inventory.txt \
  --cluster /tmp/mem-cluster.txt \
  --staleness /tmp/mem-staleness.txt \
  --check=cluster,staleness

# Post-sync before claiming done (exit 0 required)
python3 "{{PKG_DIR}}/scripts/validate-consolidate.py" \
  --inventory /tmp/mem-inventory.txt \
  --cluster /tmp/mem-cluster.txt \
  --staleness /tmp/mem-staleness.txt \
  --report /tmp/mem-report.md \
  --harness "<harness-memory-dir>" \
  --public "<repo>/.memory"
```

Exit `1` → fix artifacts / privacy and re-run. Exit `0` is required to lift the mutation freeze (pre) and to report consolidate complete (post). Do not claim G2/G3/G4/privacy by prose alone.

### CRITICAL exit gates (must all pass before reporting done)

Do **not** claim consolidate complete unless every gate below is true:

| Gate | Requirement |
|------|-------------|
| G1 read | Every `*.md` in harness and `.memory/` was read (including both `MEMORY.md`) |
| G2 Cluster | Theme-cluster map covers **every** non-index file **before** any merge/delete |
| G3 Staleness | Every file scored with the staleness rubric (not calendar age alone) |
| G4 Ground truth | Every `project_*` claim checked against the **current** tree with cited paths (or N/A with reason) |
| G5 Merge bias | Every multi-file cluster either merged, or has an explicit one-line "keep separate because …" |
| G6 Adversarial | Independent second pass ran when required (step 8); findings applied or rejected with reason |
| G7 Report | Report includes session-capture outcome, inventory counts, cluster map, prune/merge table, ground-truth table, residual risks |
| G8 Validator | `validate-consolidate.py` exit 0 on pre-mutation (`cluster,staleness`) and post-sync (full checks) |

If any gate fails mid-run, continue until it passes — do not stop at "normalized frontmatter + rebuilt index".

### 1. Read every file (Pi `read`)

Use Pi `read` on every `*.md` in both harness memory and `.memory/`, including `MEMORY.md`. Detect drift (name sets and content hashes / word-level diffs). List harness-only private files. Emit the **inventory**.

### 2. Normalize shape plan (do not stop here; mutations still frozen)

Plan only until artifacts in the freeze section exist:
- Relative dates → absolute `YYYY-MM-DD`
- Frontmatter: `name`, `description`, `type` only (strip `node_type`, `originSessionId`, `modified`, nested `metadata`)
- `description` specific enough to distinguish similar files
- Ensure **Why** / **How to apply** sections exist; if missing, derive them or mark for prune as non-decision

Normalization alone is **not** consolidation.

### 3. CRITICAL: Theme-cluster before merge

Group every non-index file into theme clusters (e.g. deploy, billing, review pipeline, naming). Use overlapping keywords, shared `[[links]]`, and near-duplicate descriptions.

Output a cluster map (keep it for the report):

```text
cluster: <theme>
  - file-a.md
  - file-b.md
 merge-default: yes|no — <one line>
```

**Default bias:** 2+ files in one theme → merge into one decision log, unless each holds a **distinct durable decision** that would become muddled if combined.

### 4. CRITICAL: Staleness rubric (practical expiry ≠ calendar expiry)

Score every non-index file. Calendar age is only one signal — a note can be days old and still SUPERSEDED or OPS-ONLY.

**Verdicts:** `CONTRADICTED` | `SUPERSEDED` | `SUBSUMED` | `OPS-ONLY` | `ONE-SHOT` | `DORMANT` | `KEEP`

Full rubric table and worked examples (embedded):

| Verdict | When | Action |
|---------|------|--------|
| CONTRADICTED | Claim false against current code, config, docs, or a newer memory | Fix to match truth, or delete if no remaining lesson |
| SUPERSEDED | A newer memory or shipped code fully replaces the decision | Merge lesson into survivor; delete the rest |
| SUBSUMED | Content is a strict subset of another file in the same cluster | Delete after absorbing any unique phrase into the survivor |
| OPS-ONLY | Narrative of what happened (versions, incident timeline, one-off commands) with no reusable rule | Delete, or rewrite down to pure Why/How if a rule exists |
| ONE-SHOT | True only for a finished episode (a specific outage, PR, migration) and does not transfer | Delete unless a portable rule can be extracted in ≤5 bullets |
| DORMANT | 6+ months untouched **and** no durable lesson / no inbound `[[links]]` | Prune |
| KEEP | Still true, still actionable, not redundant | Keep (possibly rewritten) |

**Practical expiry:** a note can be days old and still SUPERSEDED or OPS-ONLY. Do not keep files merely because they are recent.

**Protect `feedback_*` preferences:** do not score user-preference feedback as OPS-ONLY/ONE-SHOT just because it mentions an incident date — keep the durable rule.

Worked examples:

- **CONTRADICTED** — Memory: "review uses events-relay Worker"; Tree: Worker removed; direct review path only → prune or rewrite to current path; never leave the dead name
- **SUPERSEDED** — Memory A (Mar): "billing v1 counts raw tokens"; Memory B (Jul): "billing redesign: pipeline display + adjusted accounting" → one billing file; durable rules from B; drop A's implementation detail unless still true
- **SUBSUMED** — `project_deploy-all.md`, `project_deploy-before-check.md`, `project_deploy-needs-build.md` all restating the same deploy checklist with different incident openers → one `project_deploy.md` with the checklist; delete the three openers
- **OPS-ONLY / ONE-SHOT** — "On 2026-06-12 migration 0020 partially applied; fixed with …" → keep only if it yields a portable rule ("partial unique index publish can leave DO stale — always …"); otherwise delete; git history holds the episode
- **KEEP (distinct decisions in same theme)** — `feedback_stacked-pr-and-rebase-traps` (git workflow trap) vs `project_review-pipeline` (product review architecture): same "review" word, different decisions → keep separate with explicit justification
- **Description collision** — if two `description` lines are interchangeable after removing proper nouns, treat as merge candidates even if bodies differ in length

### 5. CRITICAL: Ground-truth verify

For each `project_*` (and any `reference_*` that asserts repo-local facts):

1. Locate the claimed path, flag, API, architecture fact, or workflow in the **current working tree**
2. Record: `VERIFIED` | `UPDATED` | `PRUNED` | `N/A (no repo)` | `UNVERIFIABLE (state why)` plus **tool-observed** `path → found|missing`
3. Never leave a known-false claim in place after consolidate

Use Pi `read` and `bash` (`find`/`ls`/`stat`/`diff`/grep) against the project — keep shell scoped to inspection. Do not trust memory text over the tree.

`feedback_*` about user/process preferences: verify consistency with other feedback files and current plugin/skill code when they name a mechanism; do not invent user-preference changes. Prefer KEEP on preference files unless contradicted by the user's later explicit preference.

### 6. Deduplicate and merge within clusters

Mutation freeze lifts only after inventory + cluster map + staleness table exist **and** pre-mutation `validate-consolidate.py --check=cluster,staleness` exits 0. For claim edits, also hold the ground-truth table first.

- Merge duplicates; keep the most detailed durable rules
- Collapse near-duplicates that differ only in incident detail
- Preserve all unique `[[name]]` targets; rewrite links to survivors after renames/merges
- After merge, survivor must still be decision-log shaped (Why + How), not a concatenated scrapbook

### 7. Rewrite for concision

- **Why** — root cause or decision rationale (1–3 short paragraphs max)
- **How to apply** — actionable bullets
- **Related** — `[[name]]` cross-links
- Strip version theater, step timelines, and "we tried X then Y"

### 8. CRITICAL: Independent adversarial pass

Run a **second pass with clean context** when **any** of: starting count ≥ 8 (excluding MEMORY.md); **any cluster has 2+ files**; ≥3 merges/deletes; user mentioned redundancy/stale memory; or you are unsure about keep-separate.

How: run an **adversarial second pass** in a clean reasoning context (no prior keep-separate justifications). Pass inventory, cluster map, and paths only. Propose merges, flag CONTRADICTED/SUPERSEDED/OPS-ONLY, list near-duplicate descriptions, and default to **merge or prune** when uncertain. Apply accepted findings; reject with one-line reasons in the report.

Zero findings despite multi-file clusters → re-check the largest cluster yourself. Skip only when count ≤ 5, all clusters size 1, no mutations, and ground-truth found nothing stale — state the skip. Never skip because the first pass "felt thorough".

### 9. Rebuild indexes (split public/private)

Rewrite **two** indexes:

1. **Harness `MEMORY.md`** — one line per surviving harness file; private lines end with `(harness only)`
2. **`.memory/MEMORY.md`** — one line per **safe** survivor only; strip every `(harness only)` line

No version/date theater. Group by theme if helpful. Keep every required entry (no hard 50-line drop).

### 10. Sync to `.memory/` (privacy fail-closed)

For each file in harness memory:

1. If **safe** → write identical content to `.memory/`
2. If **private** → **do not write** to `.memory/`; **delete** `.memory/<same name>` if it exists (stale public copy)
3. Delete `*.md` in `.memory/` that are not among current **safe** harness files
4. Never delete harness private files by "syncing absence" from a partial `.memory/` read

After sync: public safe sets match; no private bodies or private index lines remain under `.memory/`.

`rm` targets only paths under harness memory or `.memory/`.

### 11. Report (required sections)

```text
## Consolidate report
- Session capture: captured N file(s) from session context | skipped (no durable content) | skipped (no-context flag)
- Inventory: harness N, .memory/ M, drift: …
- Clusters: (map covering every non-index file)
- Staleness: verdict counts
- Ground truth: rows with path → found|missing + VERIFIED/UPDATED/PRUNED counts
- Merged: (old files → survivor) × reasons
- Pruned: (file × rubric verdict × reason)
- Kept-separate: (cluster × justification)
- Privacy: private files kept harness-only; public scrub actions
- Adversarial pass: ran|skipped — findings applied/rejected
- Index rebuilt: harness yes|no; .memory yes|no (safe-only)
- Validator: pre exit=…; post exit=… (paste PASSED/FAILED summary)
- Residual risks: anything still fuzzy
- Gates: `G1 passed`; `G2 passed`; …; `G8 passed` (state every gate individually; this is the child JSONL evidence required for the parent success notice)
```

Write the report body to a temp file and run the **post-sync** validator (full checks). Exit non-zero → do not claim done. If nothing changed after a full gated run, still show inventory, cluster map, ground-truth, and validator output.

## Anti-patterns (do not do these)

- Consolidating existing files while ignoring durable decisions/preferences/lessons sitting in the current session context
- Inventing memories when the session had no durable content instead of recording "skipped"
- Pruning only by "older than 3/6 months" while leaving last week's superseded architecture notes
- Creating a new memory file without searching for an existing theme file to edit
- Concatenating three incident writeups and calling it a merge (that is still an ops log)
- Skipping adversarial review because the first pass "felt thorough"
- Reporting done without G1–G8, without pre-mutation inventory/cluster/staleness, or without validator exit 0
- Copying the same MEMORY.md (including `(harness only)` lines) into both locations
- Leaving a private file that was once copied into `.memory/` after a later privacy classification
- Self-attesting cluster/path/privacy in prose while skipping `validate-consolidate.py`
