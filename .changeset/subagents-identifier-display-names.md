---
"@fradser/pi-subagents": patch
"@fradser/pi-agent-teams": patch
---

An Agent's display name is one identifier-shaped token, and a start reads as `@task-sql-work` rather than as the phrase a caller typed.

**The rule**

A caller writes free text into `agent_start`'s `label`, and every surface painted that text as the child's name:

```
 [agent] reported · @Task SQL measured optimization · ctrl+o to expand
```

A row names a child; it does not quote a sentence. A person also copies that name out of a transcript, and a name with spaces and capitals is not one token to copy. `agentDisplayName` in `src/intent-tools.ts` projects the authored label once, at the `agent_start` boundary, so the roster entry, the receipt, the Session Result notice, the parent message, the result envelope, the activity area and the stop row all carry the same name:

```
 [agent] reported · @task-sql-measured-optimization · ctrl+o to expand
```

The projection lowercases the label, replaces each run of other characters with one hyphen, trims the edge hyphens, and bounds the result. It is deliberately ASCII, because a letter outside ASCII renders as a word rather than a token. A label that holds no ASCII letter or digit therefore projects to nothing, and the child keeps its own name: an identity name, or `subagent-<8 hex>`. `Task  SQL  work` and `Fix OAuth 2.0!` read as `task-sql-work` and `fix-oauth-2-0`.

The authored text is not discarded. A temporary child's role keeps it as its purpose, which is what a coordinator hands its teammates, so the receipt still reports `role · Fix OAuth 2.0!` beside `Label: fix-oauth-2-0`. The `label` parameter description, the README, `VISION.md` and `references/agent-roles.md` state the rule, and the Agent Teams leader guidance names it.

Contract: the new rule `A label is one identifier-shaped display name` in `packages/subagents/features/intent-tools.feature`.

**Verification**

- `packages/subagents/tests/test_intent_tools.py` starts a child for each of three authored labels and asserts the receipt, the roster entry, the Session Result notice and the `<agent-result from=…>` envelope that real Pi delivered, plus the role line that keeps the authored text. A label holding no ASCII letter or digit keeps the child's own name.
- `packages/subagents/tests/test_intent_tui.py` renders the real rows: input, stop and list subjects read `@friendly-reviewer`, `@original-reader` and `@storage-reviewer`, and the authored phrase never reaches a row. `test_agent_activity_widget.py` asserts the same for the working row above the editor.
- `test_intent_host.py` keeps `definition.description == "friendly label"` and adds `receipt.label == "friendly-label"`, which records the split between the role's purpose and the display name.
- Real `pi` against a loopback provider (`tests/test_live_intent.py`, cases `print-prose-label` and `tui-prose-label`) starts a child with the label `Task SQL measured optimization`. One real process reports `label=task-sql-measured-optimization` on the start receipt, on the stop receipt and on both result notices. The captured 70-column composer shows `[agent] started · @task-sql-measured-optimizat…`, `[agent] queued · …`, `[agent] stopped · @task-sql-measured-optimization` and `⠦ task-sql-measured-optimization · FIRST RESULT`, and never the authored phrase.
- `packages/subagents` passes (584 tests), `packages/agent-teams` passes (302 tests), `tsc --noEmit -p tsconfig.extensions.json` and `node scripts/publish-release.mjs --check` are clean, and `tests/test_prompt_budget.py` still holds the Agent Teams prompt ceilings.