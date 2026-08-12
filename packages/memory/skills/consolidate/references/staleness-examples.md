# Staleness rubric — full table and worked examples

Score each file during consolidate. Calendar age is only one signal. Prefer delete/merge over keeping "still recent but dead" notes. Prefer the harsher verdict when two apply.

## Verdict table

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

## Worked examples

### CONTRADICTED

- Memory: "review uses events-relay Worker"
- Tree: Worker removed; direct review path only
- Action: prune or rewrite to current path; never leave the dead name

### SUPERSEDED

- Memory A (Mar): "billing v1 counts raw tokens"
- Memory B (Jul): "billing redesign: pipeline display + adjusted accounting"
- Action: one billing file; durable rules from B; drop A's implementation detail unless still true

### SUBSUMED

- `project_deploy-all.md`, `project_deploy-before-check.md`, `project_deploy-needs-build.md` all restating the same deploy checklist with different incident openers
- Action: one `project_deploy.md` with the checklist; delete the three openers

### OPS-ONLY / ONE-SHOT

- "On 2026-06-12 migration 0020 partially applied; fixed with …"
- Keep only if it yields a portable rule ("partial unique index publish can leave DO stale — always …")
- Otherwise delete; git history holds the episode

### KEEP (distinct decisions in same theme)

- `feedback_stacked-pr-and-rebase-traps` (git workflow trap)
- `project_review-pipeline` (product review architecture)
- Same "review" word, different decisions → keep separate with explicit justification

### Description collision

If two `description` lines are interchangeable after removing proper nouns, treat as merge candidates even if bodies differ in length.
