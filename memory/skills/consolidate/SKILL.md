---
name: consolidate
description: >
  Consolidates project memory across harness and .memory/ with theme clustering,
  practical-expiry prune, ground-truth verify, and an adversarial second pass.
  Use when the user runs /skill:consolidate, asks to tidy/dedupe/prune memory,
  or reports redundant or stale memories. Also covers active writing during work.
---

# Memory — Active Write & Consolidate

The project's memory lives in two locations that must stay **identical for safe (public) files** (idempotent):

1. **`~/.pi/agent/memory/<escaped-cwd>/`** (or `~/.claude/projects/<escaped-cwd>/memory/`) — harness, loaded by pi/Claude Code, written first
2. **`.memory/`** — canonical, git-tracked, written second — **safe files only**

Resolve the harness path: `~/.pi/agent/memory/<cwd-with-/→->/` or `~/.claude/projects/<cwd-with-/→->/memory/` (probe both space-handling forms: `/→-`+` →-` and `/→-`+space-kept).

Private files (user preferences, credentials, PII) live in **harness only**. They must never appear as files or index lines under `.memory/`.

## Active Write

When you encounter a decision, preference, lesson, or anything worth remembering, write it **immediately** — do not wait for /skill:consolidate.

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

## Consolidate (/skill:consolidate)

User-invoked only. No auto-consolidation. Default failure mode of a weak run is **cosmetic tidy while leaving thematic redundancy and factually dead notes**. This procedure is fail-closed against that.

Work order: harness first, then sync to `.memory/`.

### CRITICAL: Mutation freeze until planning artifacts exist

**Do not `write`, `edit`, or `rm` any memory file** until all three artifacts exist in this conversation:

1. **Inventory** — complete name list of harness `*.md` and `.memory/*.md` (including both `MEMORY.md`)
2. **Cluster map** — every non-index file appears in exactly one theme cluster
3. **Staleness table** — every non-index file has a rubric verdict (step 4)

After ground-truth probes (step 5), also hold a **ground-truth table** with tool-observed paths (`path → found|missing|updated`) before applying claim fixes. Fabricating these tables without `read` / bash grep / `find` / `ls` is a failed run.

### CRITICAL: Machine validator (cannot self-attest past this)

Write (via Pi `write`/temp files) inventory / cluster / staleness / report to temp files, then run:

```bash
# Pre-mutation (lift freeze only if exit 0)
python3 "../../scripts/validate-consolidate.py" \
  --inventory /tmp/mem-inventory.txt \
  --cluster /tmp/mem-cluster.txt \
  --staleness /tmp/mem-staleness.txt \
  --check=cluster,staleness

# Post-sync before claiming done (exit 0 required)
python3 "../../scripts/validate-consolidate.py" \
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
| G7 Report | Report includes inventory counts, cluster map, prune/merge table, ground-truth table, residual risks |
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

Use Pi `read` on `references/staleness-examples.md` for the full table, actions, and worked examples. Protect `feedback_*` preferences: incident dates do not make them OPS-ONLY.

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
- Gates: G1–G8 checklist
```

Write the report body to a temp file and run the **post-sync** validator (full checks). Exit non-zero → do not claim done. If nothing changed after a full gated run, still show inventory, cluster map, ground-truth, and validator output.

## Anti-patterns (do not do these)

- "Normalized frontmatter and rebuilt MEMORY.md" as the whole job while thematic near-duplicates remain
- Pruning only by "older than 3/6 months" while leaving last week's superseded architecture notes
- Creating a new memory file without searching for an existing theme file to edit
- Concatenating three incident writeups and calling it a merge (that is still an ops log)
- Skipping adversarial review because the first pass "felt thorough"
- Reporting done without G1–G8, without pre-mutation inventory/cluster/staleness, or without validator exit 0
- Copying the same MEMORY.md (including `(harness only)` lines) into both locations
- Leaving a private file that was once copied into `.memory/` after a later privacy classification
- Self-attesting cluster/path/privacy in prose while skipping `validate-consolidate.py`
