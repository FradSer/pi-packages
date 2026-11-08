# A single learn tool with an entry-scoped Harness route

`pi-continual-learning` exposes one zero-argument model-facing tool named
`learn`. Its guidance covers both explicit Memory requests and explicit Harness
rule requests. The parent freezes the current task evidence and routes the
request; the model supplies no intent, type, content, path or file.

This supersedes the `learn_current_memory` name used in ADR-0012 and ADR-0013.
Those two ADRs are historical decision records and remain byte-identical; their
frozen Memory-organization behaviour (in-process pure organize, mirror
normalization) is unchanged. Only the tool name and its request routing change.

## Context

The previous surface registered four model-facing tools
(`learn_current_memory`, `harness_preview`, `learning_read`,
`harness_check_cases`) plus dynamic active-set loadouts. The user asked for one
tool and identified two prompt families: Memory requests ("整理记忆", "记住这个")
and Harness requests ("以后禁止 npm", "纠正旧规则").

The consolidation pipeline's `screenLearningEntries` has a frozen truth table:
`durableUser = constraint || knowledge` and `memory = durableUser || recovery`.
Every constraint/correction prompt therefore screens `{memory:true,
harness:true}`, asserted by `tests/test_learning_efficiency.py`. Changing that
table would reclassify frozen evidence and the historical cohorts, which is
forbidden. The tool's ENTRY route must nevertheless keep the two request
families distinct.

`startRuleProcedure` in `extensions/guardrails.ts` owns the interactive Harness
write: exact candidate/predecessor bytes, positive and negative cases,
no-UI fail-closed, option confirmation, atomic readback and rollback. It is a
`triggerTurn:true` follow-up: the write happens in a later turn through Pi's
native `write`, gated by the `tool_call`/`tool_result` hooks.

## Decision

1. **One name, no alias.** `TOOL_NAMES.learn = "learn"`. The other three tool
   registrations remain in this layer until their own retirement phases; the
   tool-surface loadout and the `learning_read` frozen-dossier evidence marker
   are unchanged.
2. **Entry-scoped classification.** `extensions/learn-intent.ts` reads only the
   last real `role:user` entry and returns `harness | memory | none`. It is a
   separate, pure classifier: it does not alter `screenLearningEntries`,
   `deriveLearningSignals`, the frozen truth table or any historical proof.
   Negated/temporary/quoted "remember" text does not trigger a route.
3. **Harness route.** An explicit rule request calls the narrow
   `startHarnessProcedureForLearn` bridge, which opens the identical guarded
   `/harness` procedure. `learn()` returns an honest `authoring-started`
   outcome; it never claims a rule was written, never starts the Memory
   pipeline, and never fabricates a terminal learning receipt. The
   follow-up turn's guarded write keeps every write-time gate.
4. **Memory route.** Memory and ordinary prompts keep the existing twelve-gate
   Memory-only `startConsolidationPipeline({agentRequested:true})` path, its
   organizer in-process branch, receipts, backlog replay and undo unchanged.
5. **No second pipeline.** A learn() call that opened the Harness procedure
   records the task anchor as handled; the settled learner returns early for
   that anchor so it cannot author the same rule twice.
6. **Guidance consistency.** `AGENT_LEARNING_TOOL_GUIDANCE`,
   `SETTLED_LEARNING_GUIDANCE`, `project_memory_protocol` and the tool
   description/promptGuidelines all name `learn`, cover both request families,
   and never redirect the user to a slash command. Memory stays untrusted
   discovery context, never instruction authority.
7. **Frozen evidence.** `tests/continuous-command-proof.ts`,
   `tests/continuous_project_evidence.py`,
   `tests/live_continuous_project_learning.py`,
   `tests/test_continuous_project_protocol.py`,
   `tests/live_automatic_source_refresh.py`, `tests/fixtures/**`, the
   preintegration copies, `tests/jev-*.json` manifests, the nine `--learning-*`
   planner-child structured-output flags, `planner-json-output.ts`,
   `tests/test_learning_efficiency.py`, and ADR-0012/0013 stay byte-identical.

## Consequences

- `learn()` is not a terminal Harness authoring result. A rule is only added
  after the follow-up turn's guarded, confirmed and readback-verified write.
  Callers must report "authoring started" rather than "rule added".
- The Harness procedure writes through guardrails' native-write hook, which
  does not yet emit a learning receipt or `recordLearningMutation` undo record.
  Adding those to the write hook is a separate, explicitly reviewed change;
  this ADR does not claim they exist.
- The entry classifier and the pipeline screen are intentionally different:
  the former picks an entry point from the real user request, the latter
  decides which consolidation phases frozen evidence can support. Neither
  overrides the other.
- Scripts and tests that named `learn_current_memory` are updated; the two
  historical ADRs are not. A negative assertion in the contemporary tests
  prevents the old name from being resurrected.
- This is a breaking tool rename. It ships as a major-version change with no
  alias, no compatibility layer and no recorded-branch migration.
