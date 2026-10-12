from __future__ import annotations

import json
import tempfile
from pathlib import Path

from support import PKG_DIR as MEMORY_PKG_DIR, initialize_git_repo, run_bun, run_bun_script


def source() -> str:
    return (MEMORY_PKG_DIR / "extensions" / "inject-memory.ts").read_text(encoding="utf-8")


def test_extension_registers_memory_and_consolidate_commands() -> None:
    content = source()
    assert 'registerCommand("memory"' in content
    assert 'registerCommand("consolidate"' in content
    assert "before_agent_start" in content
    assert "loadAndDeduplicateMemories" in content


def test_dreaming_widget_starts_before_selector_and_survives_memory_phase_completion() -> None:
    content = source()
    pipeline = content[content.index('async function startConsolidationPipeline'):content.index('const LEARNING_RESULT_MESSAGE')]
    command = content[content.index('pi.registerCommand("consolidate"'):content.index('pi.registerCommand("memory"')]
    assert 'await resolvePackageDir()' not in command
    assert pipeline.index('setDreamingWidget(ctx') < pipeline.index('selectIncrementalLearning({')
    assert 'setDreamingActivity("selecting related memory")' in pipeline
    assert 'setDreamingActivity(fullMode ? "full memory" : "memory delta")' in pipeline
    assert 'setDreamingActivity("harness delta")' in pipeline
    assert 'setDreamingActivity("AGENTS.md delta")' in pipeline
    finish = content[content.index('const finish = async'):content.index('child.on("error"')]
    assert 'cleanup?.()' not in finish
    assert 'state.cleanup = undefined' not in finish
    assert 'cleanup?.();' in pipeline[pipeline.index('}).finally(async () => {'):]


def test_dreaming_activity_labels_a_search_by_its_pattern() -> None:
    # A consolidation worker holds read, grep, find, and ls, so a content or
    # filename search is common: its row must name the pattern rather than the
    # directory the search only looked in.
    result = run_bun(
        """
        import { dreamingToolActivity } from './packages/continual-learning/extensions/inject-memory.ts';
        const label = (toolName, args) => dreamingToolActivity(toolName, args);
        console.log(JSON.stringify({
          grep: label('grep', { pattern: 'MINIMAL_PI_WORKER_TOOLS', path: '/repo/packages/context' }),
          find: label('find', { pattern: '**/*.feature', path: '/repo/packages' }),
          read: label('read', { path: '/repo/packages/context/index.ts' }),
          ls: label('ls', { path: '/repo/packages/context' }),
          validator: label('bash', { command: 'python3 tools/validate-consolidate.py --run abc' }),
          command: label('bash', { command: '  pnpm   test  ' }),
          bare: label('grep', undefined),
        }));
        """
    )
    assert result["grep"] == {"line": "grep MINIMAL_PI_WORKER_TOOLS", "detail": "MINIMAL_PI_WORKER_TOOLS"}
    assert result["find"] == {"line": "find **/*.feature", "detail": "**/*.feature"}
    assert result["read"] == {"line": "read index.ts", "detail": "index.ts"}
    assert result["ls"] == {"line": "ls context", "detail": "context"}
    assert result["validator"] == {"line": "validate-consolidate.py", "detail": "validate-consolidate.py"}
    assert result["command"] == {"line": "pnpm test", "detail": "pnpm test"}
    assert result["bare"] == {"line": "grep", "detail": ""}


def test_dreaming_widget_and_notifications_use_shared_pi_kit_tui_primitives() -> None:
    content = source()
    assert "createLiveActivityWidget" in content
    assert 'key: "memory-dreaming"' in content
    assert 'identity: "Dreaming..."' in content
    assert 'placement: "aboveEditor"' in content
    assert "leadingSpaces: 1" in content
    assert "dreamingWidget.update(ctx" in content
    assert "dreamingWidget.clear(ctx)" in content
    assert "notifyPi(ctx.ui" in content
    assert "ctx.ui.notify" not in content


def test_dreaming_activity_updates_tui_widget_live() -> None:
    result = run_bun(
        """
        import { setDreamingWidget, setDreamingActivity, clearDreamingWidget } from './packages/continual-learning/extensions/inject-memory.ts';
        const updates = [];
        const mockUi = {
          setWidget: (key, factory) => {
            if (!factory) return;
            const component = factory({ requestRender: () => {} }, { fg: (_c, t) => t, bold: t => t });
            updates.push({ key, rendered: component.render(80) });
          }
        };
        const ctx = { mode: 'tui', ui: mockUi };
        setDreamingWidget(ctx, 'preparing full maintenance');
        setDreamingActivity('full memory');
        setDreamingActivity('harness delta');
        clearDreamingWidget(ctx);
        console.log(JSON.stringify({
          called: updates.length > 0,
          key: updates[0]?.key,
        }));
        """
    )
    assert result["called"] is True
    assert result["key"] == "memory-dreaming"


def test_consolidation_contract_is_parent_owned() -> None:
    content = source()
    assert "createConsolidationRun" in content
    assert "applyConsolidationPlan" in content
    assert "createConsolidationReceipt" in content
    assert "releaseConsolidationRun" in content
    assert "parent-owned validation receipt" in content
    # Current-session evidence is frozen. Explicit full may read one bounded
    # same-project historical source through the parent, excluding this file.
    backlog = content[content.index("function queueSettledTask("):]
    assert "getSessionFile" in backlog
    outside = content[:content.index("function queueSettledTask(")]
    assert outside.count("getSessionFile") == 1
    fallback = outside[outside.index('if (fullMode)'):outside.index("let taskSlice", outside.index('if (fullMode)'))]
    assert "recentProjectLearningInput" in fallback
    assert "currentSessionFile: invocationContext.sessionManager.getSessionFile?.()" in fallback
    assert "snapshotSessionContext(invocationContext, recent.entries)" in fallback
    for read in ("readFileSync(sessionFile", "readFile(entry.sessionFile", "Bun.file(sessionFile"):
        assert read not in content, read
    assert "G1" not in content
    assert "G8" not in content


def test_memory_planner_prompts_are_mode_specific_and_read_only() -> None:
    full = (MEMORY_PKG_DIR / "prompts" / "memory-consolidator.md").read_text(encoding="utf-8")
    incremental = (MEMORY_PKG_DIR / "prompts" / "incremental-memory-consolidator.md").read_text(encoding="utf-8")
    assert "{{PKG_DIR}}" in full and "{{SNAPSHOT_PATH}}" in full
    assert "validate-consolidate.py" in full and "SKILL.md" in full
    assert "{{DOSSIER_PATH}}" in incremental
    assert "incremental-memory-plan" in incremental
    assert "Do not emit `selected`, `inventory`," in incremental
    assert "read-only" in full.lower() and "read-only" in incremental.lower()
    assert "{{DOSSIER_INPUT}}" in incremental
    assert "No repository exploration or discovery is granted" in incremental


def test_forged_validator_text_does_not_prove_a_plan() -> None:
    result = run_bun(
        """
        import { createConsolidationEvidence, recordConsolidationEvent, missingConsolidationEvidence } from './packages/continual-learning/extensions/inject-memory.ts';
        const evidence = createConsolidationEvidence();
        recordConsolidationEvent(evidence, { type: 'message_end', message: { role: 'assistant', content: 'PASSED checks=all G1 passed' } });
        console.log(JSON.stringify(missingConsolidationEvidence(evidence)));
        """
    )
    assert "exactly one schema-valid consolidation plan" in result
    assert "a parent-owned validation receipt" in result


def test_valid_plan_is_parsed_but_not_self_attested_as_complete() -> None:
    result = run_bun(
        """
        import { createConsolidationEvidence, recordConsolidationEvent, missingConsolidationEvidence } from './packages/continual-learning/extensions/inject-memory.ts';
        const evidence = createConsolidationEvidence();
        recordConsolidationEvent(evidence, { type: 'message_end', message: { role: 'assistant', content: '{"schemaVersion":1,"runId":"r","scopeKey":"s","snapshotDigest":"d","selected":[]}' } });
        console.log(JSON.stringify(missingConsolidationEvidence(evidence)));
        """
    )
    assert result == ["completed tool work", "a parent-owned validation receipt"]


PLANNER_QUOTA_ERROR = '429: {"type":"usage_limit_reached","message":"The usage limit has been reached","plan_type":"prolite"}'
PLANNER_COOLDOWN_ERROR = '429: {"code":"model_cooldown","message":"All credentials for model gpt-5.6-luna are cooling down via provider codex"}'


def test_planner_model_error_is_classified_as_model_error_not_missing_plan() -> None:
    result = run_bun(
        f"""
        import {{ createConsolidationEvidence, recordConsolidationEvent, classifyPlanPhaseFailure }} from './packages/continual-learning/extensions/inject-memory.ts';
        const evidence = createConsolidationEvidence();
        recordConsolidationEvent(evidence, {{ type: 'message_end', message: {{ role: 'assistant', content: [], stopReason: 'error', errorMessage: {json.dumps(PLANNER_QUOTA_ERROR)} }} }});
        recordConsolidationEvent(evidence, {{ type: 'auto_retry_end', success: false, attempt: 3, finalError: {json.dumps(PLANNER_COOLDOWN_ERROR)} }});
        console.log(JSON.stringify(classifyPlanPhaseFailure(evidence, '')));
        """
    )
    assert result["kind"] == "model-error"
    assert "model_cooldown" in result["detail"]


def test_successful_model_retry_attempt_clears_the_earlier_planner_error() -> None:
    result = run_bun(
        f"""
        import {{ createConsolidationEvidence, recordConsolidationEvent, classifyPlanPhaseFailure }} from './packages/continual-learning/extensions/inject-memory.ts';
        const evidence = createConsolidationEvidence();
        recordConsolidationEvent(evidence, {{ type: 'message_end', message: {{ role: 'assistant', content: [], stopReason: 'error', errorMessage: {json.dumps(PLANNER_QUOTA_ERROR)} }} }});
        recordConsolidationEvent(evidence, {{ type: 'message_end', message: {{ role: 'assistant', content: 'prose without a plan', stopReason: 'stop' }} }});
        console.log(JSON.stringify(classifyPlanPhaseFailure(evidence, '')));
        """
    )
    assert result["kind"] == "missing-plan"


def test_plan_failure_with_child_stderr_stays_missing_plan_even_with_model_error() -> None:
    result = run_bun(
        f"""
        import {{ createConsolidationEvidence, recordConsolidationEvent, classifyPlanPhaseFailure }} from './packages/continual-learning/extensions/inject-memory.ts';
        const evidence = createConsolidationEvidence();
        recordConsolidationEvent(evidence, {{ type: 'message_end', message: {{ role: 'assistant', content: [], stopReason: 'error', errorMessage: {json.dumps(PLANNER_QUOTA_ERROR)} }} }});
        console.log(JSON.stringify(classifyPlanPhaseFailure(evidence, 'child crashed')));
        """
    )
    assert result["kind"] == "missing-plan"
    assert result["detail"] == "child crashed"


def test_model_error_plan_phase_fails_labeled_without_a_fresh_planner_retry() -> None:
    content = source()
    assert 'failure.kind === "model-error"' in content
    assert "planner model error" in content
    assert content.count("classifyPlanPhaseFailure(evidence, stderr)") == 2


def test_validator_error_entry_does_not_duplicate_its_category_prefix() -> None:
    result = run_bun(
        """
        import { formatValidatorErrorEntry } from './packages/continual-learning/extensions/inject-memory.ts';
        console.log(JSON.stringify([
          formatValidatorErrorEntry({ code: 'grounding', message: 'grounding: douyin.md observation path missing' }),
          formatValidatorErrorEntry({ code: 'privacy', message: 'raw leaked token' }),
        ]));
        """
    )
    assert result[0] == "grounding: douyin.md observation path missing"
    assert result[1] == "privacy: raw leaked token"


def test_planner_failure_reason_prefers_timeout_and_keeps_stderr_detail() -> None:
    result = run_bun(
        """
        import { plannerFailureReason } from './packages/continual-learning/extensions/inject-memory.ts';
        console.log(JSON.stringify([
          plannerFailureReason({ timedOut: true, stderrDetail: "boom", lastJsonError: "", exitCode: 143 }),
          plannerFailureReason({ timedOut: true, stderrDetail: "", lastJsonError: "", exitCode: 143 }),
          plannerFailureReason({ timedOut: false, stderrDetail: "boom", lastJsonError: "j", exitCode: 1 }),
          plannerFailureReason({ timedOut: false, stderrDetail: "", lastJsonError: "j", exitCode: 1 }),
          plannerFailureReason({ timedOut: false, stderrDetail: "", lastJsonError: "", exitCode: 7 }),
        ]));
        """
    )
    assert result[0].startswith("planner exceeded the dreaming budget (30 minutes)")
    assert "(stderr: boom)" in result[0]
    assert "stderr" not in result[1]
    assert result[2] == "boom" and result[3] == "j" and result[4] == "exit code 7"


def test_model_error_guard_requires_no_timeout_on_both_exit_paths() -> None:
    content = source()
    assert content.count('failure.kind === "model-error" && !timedOut') == 2


def test_memory_attempt_diagnostic_only_attaches_a_stop_reason_to_a_failed_outcome() -> None:
    # Given a recorded attempt outcome, When the parent builds the receipt
    # diagnostic, Then a controlled stop reason attaches only to "failed".
    # A rejected, applied, proposed, noop, or cancelled attempt stays free of
    # it, and a Jev judgment keeps its own reason.
    result = run_bun(
        """
        import { memoryAttemptDiagnostic } from './packages/continual-learning/extensions/inject-memory.ts';
        console.log(JSON.stringify([
          memoryAttemptDiagnostic({ outcome: "failed", stopReason: "memory planner model error" }),
          memoryAttemptDiagnostic({ outcome: "rejected", stopReason: "memory planner model error" }),
          memoryAttemptDiagnostic({ outcome: "cancelled", stopReason: "memory planner timed out" }),
          memoryAttemptDiagnostic({ outcome: "applied", stopReason: "memory planner timed out" }),
          memoryAttemptDiagnostic({ outcome: "proposed", stopReason: "memory planner timed out" }),
          memoryAttemptDiagnostic({ outcome: "failed", stopReason: "memory planner model error", jev: { status: "failed", reason: "unavailable" } }),
          memoryAttemptDiagnostic({ outcome: "applied", stopReason: "ignored", jev: { status: "decided", reason: "supported" } }),
        ]));
        """
    )
    assert result == [
        "memory planner model error",
        None,
        None,
        None,
        None,
        "Jev failed: unavailable",
        "Jev decided: supported",
    ]


def test_memory_stop_reason_is_a_fixed_vocabulary_without_worker_text() -> None:
    # Given a Memory phase that stopped before any Jev judgment, When the parent
    # reports the stopped attempt, Then the reason is a fixed phrase. Worker
    # stderr and model output never become a receipt reason.
    result = run_bun(
        """
        import { memoryStopReason } from './packages/continual-learning/extensions/inject-memory.ts';
        console.log(JSON.stringify([
          memoryStopReason({ timedOut: true, outputLimit: false, modelError: false, verificationFailed: false }),
          memoryStopReason({ timedOut: false, outputLimit: true, modelError: false, verificationFailed: false }),
          memoryStopReason({ timedOut: false, outputLimit: false, modelError: true, verificationFailed: false }),
          memoryStopReason({ timedOut: false, outputLimit: false, modelError: false, verificationFailed: false }),
          memoryStopReason({ timedOut: true, outputLimit: false, modelError: false, verificationFailed: true }),
        ]));
        """
    )
    assert result == [
        "memory planner timed out",
        "memory planner exceeded the output limit",
        "memory planner model error",
        "memory planner produced no usable plan",
        "memory consolidation verification failed",
    ]


def test_rejection_reason_is_head_clipped_at_a_word_agnostic_budget() -> None:
    result = run_bun(
        """
        import { clipRejectionReason } from './packages/continual-learning/extensions/inject-memory.ts';
        const long = "Consolidation validator rejected the plan: " + "g".repeat(400);
        console.log(JSON.stringify([clipRejectionReason("short reason"), clipRejectionReason(long)]));
        """
    )
    assert result[0] == "short reason"
    assert result[1].startswith("Consolidation validator rejected the plan:")
    assert result[1].endswith("…") and len(result[1]) == 241


def test_incremental_repair_diagnostic_obeys_the_exact_limit_and_redacts_before_clipping() -> None:
    # Given oversized reasons and a credential split at the clipping boundary,
    # When diagnostics are formatted, Then neither size nor privacy may weaken.
    result = run_bun("""
      import { formatIncrementalRepairDiagnostic } from './packages/continual-learning/extensions/inject-memory.ts';
      const long = formatIncrementalRepairDiagnostic('x'.repeat(5000), 'y'.repeat(5000));
      const secret = formatIncrementalRepairDiagnostic('x'.repeat(785) + ' password=supersecret');
      console.log(JSON.stringify({length: long.length, secret}));
    """)
    assert result["length"] <= 1200
    assert "password" not in result["secret"]
    assert "redacted sensitive repair diagnostic" in result["secret"]


def test_incremental_repair_diagnostic_keeps_original_and_repair_rejections_bounded() -> None:
    result = run_bun(
        """
        import { formatIncrementalRepairDiagnostic } from './packages/continual-learning/extensions/inject-memory.ts';
        const original = 'newMemories[0].kind must be preference or project';
        const repair = 'newMemories[0].evidence must contain 1..8 entries';
        const diagnostic = formatIncrementalRepairDiagnostic(original, repair);
        const redacted = formatIncrementalRepairDiagnostic(original, `${repair}; password=supersecret`);
        console.log(JSON.stringify({ diagnostic, redacted, bounded: diagnostic.length <= 1200, secret: redacted.includes('supersecret') }));
        """
    )
    assert result["bounded"] is True
    assert "original rejection" in result["diagnostic"]
    assert "preference or project" in result["diagnostic"]
    assert "repair rejection" in result["diagnostic"]
    assert "evidence must contain" in result["diagnostic"]
    assert result["secret"] is False
    assert "redacted sensitive repair diagnostic" in result["redacted"]


def test_task_feedback_lines_only_exist_with_rejection_feedback() -> None:
    result = run_bun(
        """
        import { buildTaskFeedbackLines } from './packages/continual-learning/extensions/inject-memory.ts';
        const absent = buildTaskFeedbackLines(undefined);
        const present = buildTaskFeedbackLines("grounding: douyin.md observation path does not exist as a file");
        console.log(JSON.stringify([absent, present]));
        """
    )
    assert result[0] == []
    assert len(result[1]) == 1
    assert result[1][0].startswith("- Previous planning attempt was rejected: ")
    assert "resolves every cited issue" in result[1][0]


def test_retry_spawns_carry_rejection_feedback_into_task_text() -> None:
    content = source()
    assert "...buildTaskFeedbackLines(opts.rejectionFeedback)" in content
    assert "rejectionFeedback: reason" in content


def test_recoverable_plan_rejection_is_not_reported_and_pipeline_waits_for_retry() -> None:
    content = source()
    assert "Memory consolidation plan was rejected" not in content
    assert "while (state.completion) await state.completion" in content
    assert "await spawnAsyncConsolidation(ctx, state, { ...opts, attempt: attempt + 1, rejectionFeedback: reason })" in content
    assert "reason.slice(-160)" not in content


def test_bounded_jsonl_parser_ignores_terminal_newline() -> None:
    result = run_bun(
        """
        import { extractChildPlan } from './packages/continual-learning/extensions/consolidation-run.ts';
        const event = { type: 'message_end', message: { role: 'assistant', content: '{"kind":"memory-consolidation-plan"}' } };
        console.log(JSON.stringify(extractChildPlan(JSON.stringify(event) + '\\n', { maxLines: 1 })));
        """
    )
    assert result["ok"] is True


def test_structured_plan_event_rejects_array_wrapper_payload() -> None:
    result = run_bun(
        """
        import { extractChildPlan } from './packages/continual-learning/extensions/consolidation-run.ts';
        console.log(JSON.stringify(extractChildPlan(JSON.stringify({ type: 'consolidation_plan', plan: [] }))));
        """
    )
    assert result["ok"] is False


def test_bounded_jsonl_parser_rejects_overlong_line() -> None:
    result = run_bun(
        """
        import { extractChildPlan } from './packages/continual-learning/extensions/consolidation-run.ts';
        const line = JSON.stringify({ type: 'message_end', message: { role: 'assistant', content: '{}' } });
        console.log(JSON.stringify(extractChildPlan(line, { maxLineBytes: line.length - 1 })));
        """
    )
    assert result["ok"] is False
    assert "line" in result["error"]


def test_oversized_non_plan_telemetry_is_ignored_before_final_plan() -> None:
    result = run_bun(
        """
        import { extractChildPlan } from './packages/continual-learning/extensions/consolidation-run.ts';
        const telemetry = JSON.stringify({
          type: 'message_update',
          assistantMessageEvent: { type: 'thinking_delta', delta: 'x'.repeat(1_100_000) },
        });
        const plan = JSON.stringify({
          type: 'message_end',
          message: {
            role: 'assistant',
            content: JSON.stringify({
              kind: 'memory-consolidation-plan',
              version: 1,
              runId: 'r1',
              scopeDigest: 'd1',
              artifactHash: 'h1',
            }),
          },
        });
        console.log(JSON.stringify(extractChildPlan(
          telemetry + '\\n' + plan + '\\n',
          {
            maxLineBytes: 1024 * 1024,
            expectedIdentity: { runId: 'r1', scopeDigest: 'd1', artifactHash: 'h1' },
          },
        )));
        """
    )
    assert result["ok"] is True
    assert result["plan"]["runId"] == "r1"


def test_failed_run_diagnostics_keep_more_than_the_legacy_256k_tail() -> None:
    source_text = source()
    assert "function tailBoundedUtf8Text(text: string, maxBytes = MAX_STDOUT_BYTES)" in source_text
    assert "256 * 1024" not in source_text[source_text.index("function tailBoundedUtf8Text"):source_text.index("export interface ConsolidationEvidence")]


def test_truncated_diagnostic_suffix_starts_at_a_complete_jsonl_record() -> None:
    result = run_bun(
        """
        import { completeJsonlSuffix } from './packages/continual-learning/extensions/inject-memory.ts';
        const valid = JSON.stringify({ type: 'message_end', message: { role: 'assistant', content: 'plan' } }) + '\\n' + JSON.stringify({ type: 'agent_settled' }) + '\\n';
        const partial = 'middle-of-json\\n' + valid;
        const bracePartial = '{"type":"thinking_delta","delta":"x"}}\\n' + valid;
        const complete = JSON.stringify({ type: 'message_end' }) + '\\n';
        console.log(JSON.stringify({ repaired: completeJsonlSuffix(partial), braceRepaired: completeJsonlSuffix(bracePartial), unchanged: completeJsonlSuffix(complete) }));
        """
    )
    for field in ("repaired", "braceRepaired"):
        repaired_lines = result[field].splitlines()
        assert json.loads(repaired_lines[0])["type"] == "message_end"
        assert json.loads(repaired_lines[1])["type"] == "agent_settled"
    assert result["unchanged"] == '{"type":"message_end"}\n'


def test_child_plan_extraction_handles_output_exceeding_legacy_256k_bound() -> None:
    result = run_bun(
        """
        import { extractChildPlan, MAX_STDOUT_BYTES } from './packages/continual-learning/extensions/consolidation-run.ts';
        const delta = JSON.stringify({ type: 'message_update', assistantMessageEvent: { type: 'thinking_delta', delta: 'x'.repeat(100) } }) + '\\n';
        // Generate > 300 KB of streaming delta lines
        const lines = delta.repeat(3000);
        const planEvent = JSON.stringify({
          type: 'message_end',
          message: {
            role: 'assistant',
            content: JSON.stringify({
              kind: 'memory-consolidation-plan',
              version: 1,
              runId: 'r1',
              scopeDigest: 'd1',
              artifactHash: 'h1',
            }),
          },
        }) + '\\n';
        const fullOutput = lines + planEvent;
        console.log(JSON.stringify({
          totalBytes: fullOutput.length,
          extracted: extractChildPlan(fullOutput, {
            expectedIdentity: { runId: 'r1', scopeDigest: 'd1', artifactHash: 'h1' },
          }),
        }));
        """
    )
    assert result["totalBytes"] > 300_000
    assert result["extracted"]["ok"] is True
    assert result["extracted"]["plan"]["runId"] == "r1"


def test_child_plan_extraction_accepts_one_schema_plan_after_verbose_preamble() -> None:
    result = run_bun(
        """
        import { extractChildPlan } from './packages/continual-learning/extensions/consolidation-run.ts';
        const plan = { kind: 'memory-consolidation-plan', version: 1, runId: 'r1', scopeDigest: 'd1', artifactHash: 'h1' };
        const verbose = { type: 'message_end', message: { role: 'assistant', content: 'I reviewed the corpus. Summary: {"files":44}. Final plan follows:\\n' + JSON.stringify(plan) } };
        const ambiguous = { type: 'message_end', message: { role: 'assistant', content: 'First ' + JSON.stringify(plan) + ' second ' + JSON.stringify(plan) } };
        const options = { expectedIdentity: { runId: 'r1', scopeDigest: 'd1', artifactHash: 'h1' } };
        console.log(JSON.stringify({
          verbose: extractChildPlan(JSON.stringify(verbose) + '\\n', options),
          ambiguous: extractChildPlan(JSON.stringify(ambiguous) + '\\n', options),
        }));
        """
    )
    assert result["verbose"]["ok"] is True
    assert result["verbose"]["plan"]["kind"] == "memory-consolidation-plan"
    assert result["ambiguous"]["ok"] is False


def test_child_plan_extraction_handles_markdown_code_fenced_json() -> None:
    result = run_bun(
        """
        import { extractChildPlan } from './packages/continual-learning/extensions/consolidation-run.ts';
        const event = {
          type: 'message_end',
          message: {
            role: 'assistant',
            content: '```json\\n' + JSON.stringify({
              kind: 'memory-consolidation-plan',
              version: 1,
              runId: 'r1',
              scopeDigest: 'd1',
              artifactHash: 'h1',
            }, null, 2) + '\\n```',
          },
        };
        console.log(JSON.stringify(extractChildPlan(JSON.stringify(event) + '\\n', {
          expectedIdentity: { runId: 'r1', scopeDigest: 'd1', artifactHash: 'h1' },
        })));
        """
    )
    assert result["ok"] is True
    assert result["plan"]["kind"] == "memory-consolidation-plan"
    assert result["plan"]["runId"] == "r1"


def test_later_phase_plans_accept_preambles_but_reject_ambiguity_and_stale_identity() -> None:
    result = run_bun(r"""
      import {extractChildPlan} from './packages/continual-learning/extensions/consolidation-run.ts';
      const options={expectedIdentity:{runId:'current',scopeDigest:'scope',artifactHash:'snapshot'}};
      const event=content=>JSON.stringify({type:'message_end',message:{role:'assistant',content}})+'\n';
      console.log(JSON.stringify(['harness-consolidation-plan','agents-md-consolidation-plan'].map(kind=>{
        const plan={kind,...options.expectedIdentity,operations:[]};
        const text=JSON.stringify(plan);
        return {kind,valid:extractChildPlan(event('Checked 2 files. {"count":2}\n```json\n'+text+'\n```'),options),
          ambiguous:extractChildPlan(event(text+'\n'+text),options),
          stale:extractChildPlan(event('Proposed: '+JSON.stringify({...plan,runId:'earlier'})),options)};
      })));
    """)
    for row in result:
        assert row["valid"]["ok"] is True, row
        assert row["valid"]["plan"]["kind"] == row["kind"]
        assert row["ambiguous"]["ok"] is False
        assert row["stale"]["ok"] is False and "identity" in row["stale"]["error"]


def test_consolidation_snapshot_handles_large_context_payload() -> None:
    result = run_bun(
        """
        import { mkdtemp } from 'node:fs/promises';
        import { tmpdir } from 'node:os';
        import { join } from 'node:path';
        import { captureConsolidationSnapshot, resolveConsolidationRunPaths } from './packages/continual-learning/extensions/consolidation-run.ts';
        const agentDir = await mkdtemp(join(tmpdir(), 'pi-memory-agent-'));
        const repoDir = await mkdtemp(join(tmpdir(), 'pi-memory-repo-'));
        const paths = resolveConsolidationRunPaths(repoDir, undefined, agentDir);
        // Create 2 MB of context entries
        const largeEntry = { role: 'user', content: 'y'.repeat(100_000) };
        const largeEntries = Array(20).fill(largeEntry);
        const ctx = {
          sessionManager: {
            getBranch: () => largeEntries,
          },
        };
        const captured = await captureConsolidationSnapshot(ctx, paths);
        console.log(JSON.stringify({
          entryCount: captured.manifest.entryCount,
          digest: captured.digest,
        }));
        """
    )
    assert result["entryCount"] == 20
    assert len(result["digest"]) == 64


def test_empty_first_run_apply_creates_only_verifiable_indexes() -> None:
    result = run_bun(
        """
        import { mkdtemp, access, readFile } from 'node:fs/promises';
        import { join } from 'node:path';
        import { applyConsolidationPlan, digest } from './packages/continual-learning/extensions/consolidation-run.ts';
        const root = await mkdtemp('/tmp/pi-memory-empty-');
        const harness = join(root, 'harness');
        const publicDir = join(root, 'public');
        const run = {
          manifest: {
            runId: 'run_test', scopeDigest: 'b'.repeat(64), snapshotDigest: 'a'.repeat(64),
            harnessDir: harness, publicDir, sourceHashes: { harness: {}, public: {} },
          },
          paths: {}, released: false,
        };
        await applyConsolidationPlan(run, {
          runId: 'run_test', scopeDigest: 'b'.repeat(64), artifactHash: 'a'.repeat(64), selected: [],
        });
        await access(join(harness, 'MEMORY.md'));
        await access(join(publicDir, 'MEMORY.md'));
        console.log(JSON.stringify({
          harness: await readFile(join(harness, 'MEMORY.md'), 'utf8'),
          public: await readFile(join(publicDir, 'MEMORY.md'), 'utf8'),
          digest: digest({ harness: {}, public: {} }),
        }));
        """
    )
    assert result["harness"] == "# Memory Index\n\n"
    assert result["public"] == "# Memory Index\n\n"


def test_every_run_advertises_the_digest_of_its_actual_snapshot_bytes() -> None:
    """Kept from the removed no-context mode, where it guarded the written
    placeholder snapshot. Every run freezes a snapshot now, so the invariant is
    the same and broader: the advertised digest is the digest of the bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        agent = root / "agent"
        repo.mkdir()
        result = run_bun(
            f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            const {{ createHash }} = await import('node:crypto');
            const {{ readFile }} = await import('node:fs/promises');
            const {{ createConsolidationRun, releaseConsolidationRun }} = await import('./packages/continual-learning/extensions/consolidation-run.ts');
            const run = await createConsolidationRun({{
              cwd: {json.dumps(str(repo))},
              sessionManager: {{ getBranch: () => [{{ message: {{ role: 'user', content: 'a' }} }}], buildContextEntries: () => [{{ message: {{ role: 'user', content: 'a' }} }}] }},
            }}, {json.dumps(str(repo))});
            const bytes = await readFile(run.manifest.snapshotPath);
            const actual = createHash('sha256').update(bytes).digest('hex');
            const result = {{ advertised: run.manifest.snapshotDigest, actual, contextEnabled: run.manifest.contextEnabled }};
            await releaseConsolidationRun(run);
            console.log(JSON.stringify(result));
            """
        )
        assert result["advertised"] == result["actual"]
        # No run may claim a captured context it does not have.
        assert result["contextEnabled"] is True


def test_cancelled_apply_rolls_back_harness_and_public_bytes() -> None:
    result = run_bun(
        """
        import { mkdir, readFile, writeFile } from 'node:fs/promises';
        import { join } from 'node:path';
        import { tmpdir } from 'node:os';
        import { applyConsolidationPlan } from './packages/continual-learning/extensions/consolidation-run.ts';
        const root = join(tmpdir(), `pi-memory-rollback-${Date.now()}`);
        const harness = join(root, 'harness');
        const publicDir = join(root, 'public');
        await mkdir(harness, { recursive: true });
        await mkdir(publicDir, { recursive: true });
        await writeFile(join(harness, 'project.md'), 'old\\n');
        await writeFile(join(publicDir, 'project.md'), 'old\\n');
        await writeFile(join(harness, 'MEMORY.md'), '- [project.md](project.md)\\n');
        await writeFile(join(publicDir, 'MEMORY.md'), '- [project.md](project.md)\\n');
        const crypto = await import('node:crypto');
        const hash = (value) => crypto.createHash('sha256').update(value).digest('hex');
        const run = {
          manifest: {
            runId: 'run_test', scopeDigest: 'b'.repeat(64), snapshotDigest: 'a'.repeat(64),
            harnessDir: harness, publicDir,
            sourceHashes: {
              harness: { 'MEMORY.md': hash('- [project.md](project.md)\\n'), 'project.md': hash('old\\n') },
              public: { 'MEMORY.md': hash('- [project.md](project.md)\\n'), 'project.md': hash('old\\n') },
            },
          },
          paths: {}, released: false,
        };
        let checks = 0;
        let rejected = false;
        try {
          await applyConsolidationPlan(run, {
            runId: 'run_test', scopeDigest: 'b'.repeat(64), artifactHash: 'a'.repeat(64),
            selected: ['project.md'],
            operations: [{ name: 'project.md', kind: 'rewrite', classification: 'safe', content: 'new\\n' }],
          }, () => ++checks < 3);
        } catch {
          rejected = true;
        }
        console.log(JSON.stringify({
          rejected,
          harness: await readFile(join(harness, 'project.md'), 'utf8'),
          public: await readFile(join(publicDir, 'project.md'), 'utf8'),
        }));
        """
    )
    assert result == {"rejected": True, "harness": "old\n", "public": "old\n"}


def test_later_operation_failure_rolls_back_earlier_writes() -> None:
    result = run_bun(
        """
        import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
        import { join } from 'node:path';
        import { tmpdir } from 'node:os';
        import { createHash } from 'node:crypto';
        import { applyConsolidationPlan } from './packages/continual-learning/extensions/consolidation-run.ts';
        const root = join(tmpdir(), `pi-memory-late-failure-${Date.now()}`);
        const harness = join(root, 'harness');
        const publicDir = join(root, 'public');
        const index = '# Memory Index\\n\\n';
        await mkdir(harness, { recursive: true });
        await mkdir(publicDir, { recursive: true });
        await writeFile(join(harness, 'MEMORY.md'), index);
        await writeFile(join(publicDir, 'MEMORY.md'), index);
        const hash = (value) => createHash('sha256').update(value).digest('hex');
        const run = {
          manifest: {
            runId: 'run_test', scopeDigest: 'b'.repeat(64), snapshotDigest: 'a'.repeat(64),
            harnessDir: harness, publicDir,
            sourceHashes: {
              harness: { 'MEMORY.md': hash(index) },
              public: { 'MEMORY.md': hash(index) },
            },
          },
          paths: {}, released: false,
        };
        let rejected = false;
        try {
          await applyConsolidationPlan(run, {
            runId: 'run_test', scopeDigest: 'b'.repeat(64), artifactHash: 'a'.repeat(64),
            selected: ['first.md', 'second.md'],
            inventory: [
              { name: 'first.md', classification: 'safe' },
              { name: 'second.md', classification: 'safe' },
            ],
            operations: [
              { name: 'first.md', kind: 'create', classification: 'safe', content: 'first\\n' },
              { name: 'second.md', kind: 'create', classification: 'safe', content: 'x'.repeat(64_001) },
            ],
          });
        } catch {
          rejected = true;
        }
        console.log(JSON.stringify({
          rejected,
          harness: await readdir(harness),
          public: await readdir(publicDir),
          harnessIndex: await readFile(join(harness, 'MEMORY.md'), 'utf8'),
          publicIndex: await readFile(join(publicDir, 'MEMORY.md'), 'utf8'),
        }));
        """,
    )
    assert result == {
        "rejected": True,
        "harness": ["MEMORY.md"],
        "public": ["MEMORY.md"],
        "harnessIndex": "# Memory Index" + chr(10) + chr(10),
        "publicIndex": "# Memory Index" + chr(10) + chr(10),
    }


def test_receipt_writer_rejects_phase_path_mismatch() -> None:
    result = run_bun(
        """
        import { mkdtemp, access } from 'node:fs/promises';
        import { tmpdir } from 'node:os';
        import { join } from 'node:path';
        import { createPreApplyReceipt, writeConsolidationReceipt } from './packages/continual-learning/extensions/consolidation-run.ts';
        const directory = await mkdtemp(join(tmpdir(), 'pi-memory-receipt-'));
        const receipt = createPreApplyReceipt({
          runId: 'run_test',
          scopeDigest: 'b'.repeat(64),
          artifactHash: 'a'.repeat(64),
          selected: [],
          sourceHashes: { harness: {}, public: {} },
        });
        const run = {
          manifest: {},
          paths: {
            preReceiptFile: join(directory, 'pre-receipt.json'),
            postReceiptFile: join(directory, 'post-receipt.json'),
          },
          lockPath: join(directory, 'lock'),
          released: false,
        };
        try {
          await writeConsolidationReceipt(run, receipt, 'post');
          console.log(JSON.stringify({ rejected: false }));
        } catch (error) {
          let created = true;
          try { await access(run.paths.postReceiptFile); } catch { created = false; }
          console.log(JSON.stringify({ rejected: true, created }));
        }
        """
    )
    assert result == {"rejected": True, "created": False}


def test_shutdown_waits_for_and_invalidates_async_completion() -> None:
    content = source()
    assert "state.completion = completion" in content
    assert "if (completion) await completion" in content
    assert "const ownsCurrentRun = (): boolean" in content
    assert "applyConsolidationPlan(run, plan, ownsCurrentRun," in content
    assert "if (!ownsCurrentRun()) return" in content


def test_project_instruction_resolution_uses_pi_context_resource_objects() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cwd = root / "repo" / "nested"
        cwd.mkdir(parents=True)
        global_file = root / "global" / "AGENTS.md"
        ancestor_file = root / "repo" / "AGENTS.md"
        override_file = cwd / "AGENTS.override.md"
        result = run_bun(
            f"""
            import {{ resolveProjectInstructionsFile }} from './packages/continual-learning/extensions/inject-memory.ts';
            const cwd = {json.dumps(str(cwd))};
            const result = await resolveProjectInstructionsFile(cwd, {{
              getSystemPromptOptions: () => ({{ contextFiles: [
                {{ path: {json.dumps(str(global_file))}, content: 'global' }},
                {{ path: {json.dumps(str(ancestor_file))}, content: 'ancestor' }},
                {{ path: {json.dumps(str(override_file))}, content: 'override' }},
              ] }})
            }});
            console.log(JSON.stringify(result));
            """
        )
        assert result == {"path": str(override_file), "display": "AGENTS.override.md"}


def test_consolidate_command_has_exactly_two_learning_modes_plus_an_explicit_drain() -> None:
    content = source()
    # Two learning modes. The drain is a third argument, but it is a backlog
    # status, not a way to learn — it never runs the pipeline.
    assert 'args === "backfill"' in content
    assert 'args !== "" && args !== "full"' in content
    assert 'Usage: /consolidate [full|backfill]' in content
    assert 'mode: args === "full" ? "full" : "manual"' in content
    # The removed third mode is gone, not merely undocumented.
    assert "no-context" not in content
    assert "noContext" not in content
    assert "buildIncrementalMemoryConsolidatorPrompt" in content
    assert "buildMemoryConsolidatorPrompt" in content
    assert 'minimalPiWorkerArgs(["learning_read"])' in content
    assert "plannerReadArgs" in content


def test_child_output_uses_streaming_utf8_and_byte_bounded_diagnostics() -> None:
    content = source()
    assert 'new TextDecoder("utf-8")' in content
    assert 'decode(chunk, { stream: true })' in content
    assert "Buffer.byteLength" in content
    assert "MAX_STDERR_BYTES" in content


def test_oversized_telemetry_is_ignored_by_the_streaming_memory_path() -> None:
    content = source()
    assert "isIgnorableOversizedJsonlEvent" in content
    assert "message_update" in content
    assert "if (isIgnorableOversizedJsonlEvent(line)) return;" in content


def test_child_output_limits_terminate_before_more_jsonl_work() -> None:
    content = source()
    assert "stdoutCaptureOverflowed" in content
    assert "MAX_JSONL_LINES" in content
    assert "MAX_JSONL_LINE_BYTES" in content
    assert "terminateConsolidationChild(child, 5_000)" in content
    assert "return; // child output limit exceeded" in content
    assert "isIgnorableOversizedJsonlEvent" in content


def test_stale_finish_cannot_clear_replacement_state_or_cleanup() -> None:
    content = source()
    assert "const ownsCurrentRun" in content
    assert "if (ownsCurrentRun())" in content
    assert "const cleanup = state.cleanup" in content
    assert "if (!ownsCurrentRun()) return" in content


def test_selected_scope_is_parent_bound_before_receipt() -> None:
    content = source()
    assert "normalizeSelectedScope" in content
    assert "sourceHashes" in content
    assert "expected-selected" in content


def test_selected_aliases_normalize_to_one_canonical_scope() -> None:
    result = run_bun(
        """
        import { normalizeSelectedScope } from './packages/continual-learning/extensions/inject-memory.ts';
        console.log(JSON.stringify(normalizeSelectedScope({
          selected: [{ file: 'z.md' }, { filename: 'a.md' }],
        })));
        """
    )
    assert result == ["a.md", "z.md"]


def test_worker_environment_is_an_explicit_non_credential_allowlist() -> None:
    content = source()
    assert "const workerEnv = Object.fromEntries" in content
    assert "process.env.PATH" in content
    assert "process.env.HOME" in content
    assert "process.env.PI_CODING_AGENT_DIR" in content
    assert "process.env.ANTHROPIC_API_KEY" not in content
    assert "env: { ...process.env" not in content


def test_child_task_uses_selector_scope_for_incremental_and_full_scope_for_full_mode() -> None:
    content = source()
    assert "const selectedScope = parentSelectedScope(run, opts.selectedScope);" in content
    assert "Authoritative selected Memory names" in content
    incremental = (MEMORY_PKG_DIR / "prompts" / "incremental-memory-consolidator.md").read_text(encoding="utf-8")
    assert "{{DOSSIER_INPUT}}" in incremental
    assert "...formatSelectedScopeTaskLines(selectedScope)," in content
    procedure = (MEMORY_PKG_DIR / "prompts" / "memory-consolidator.md").read_text(encoding="utf-8")
    assert "authoritative selected memory scope" in procedure and "newMemories" in procedure


def test_selected_scope_task_lines_render_exact_contract() -> None:
    result = run_bun(
        """
        import { formatSelectedScopeTaskLines } from './packages/continual-learning/extensions/inject-memory.ts';
        console.log(JSON.stringify({
          empty: formatSelectedScopeTaskLines([]),
          named: formatSelectedScopeTaskLines(['a.md', 'B.md']),
        }));
        """
    )
    assert result["empty"][0].endswith("JSON): []")
    assert "An empty selected list does not prevent new memory creation" in result["empty"][2]
    # The no-context override that used to live here is gone with the mode.
    assert len(result["empty"]) == 3
    named = result["named"]
    assert isinstance(named, list)
    assert 'JSON): ["a.md","B.md"]' in named[0]
    assert "MUST be exactly this list" in named[1]
    assert named[3:] == ["  - a.md", "  - B.md"]


def test_failed_runs_persist_bounded_diagnostics_and_retain_artifacts() -> None:
    content = source()
    assert "const persistRunDiagnostics = async (): Promise<void>" in content
    assert "const boundedStdout = tailBoundedUtf8Text(`" in content
    assert "writeFileAtomic(run.paths.stdoutFile, completeJsonlSuffix(boundedStdout))" in content
    assert "writeFileAtomic(run.paths.stderrFile, tailBoundedUtf8Text(stderr))" in content
    assert "await persistRunDiagnostics();" in content
    # Late events must not notify or retain: recheck ownership after every await.
    assert content.count("await persistRunDiagnostics();\n        if (!ownsCurrentRun()) return;") == 3
    assert "await persistRunDiagnostics();\n          if (!ownsCurrentRun()) return;" in content
    # Retention must be decided from ownership captured before state.run clears:
    # completed, failed, and no-op runs all keep their artifacts for inspection.
    assert "const ownedNow = generation === state.generation && !state.cancelled && state.run === run;" in content
    assert "releaseConsolidationRun(run, { keepArtifacts: ownedNow })" in content
    # Output-limit trips clear the capture before persistence; keep the reason.
    assert "outputLimitReason = reason;" in content
    assert "`\\n[truncated: ${outputLimitReason}]\\n`" in content


def test_identical_duplicate_plan_records_collapse_conflicting_do_not() -> None:
    result = run_bun(
        """
        import { collapseDuplicatePlanRecords } from './packages/continual-learning/extensions/inject-memory.ts';
        const plan = {
          selected: ['a.md'],
          staleness: [
            { name: 'a.md', verdict: 'KEEP' },
            { name: 'a.md', verdict: 'KEEP' },
            { name: 'b.md', verdict: 'KEEP' },
            { name: 'b.md', verdict: 'SUPERSEDED' },
          ],
        };
        console.log(JSON.stringify(collapseDuplicatePlanRecords(plan)));
        """
    )
    assert result["staleness"] == [
        {"name": "a.md", "verdict": "KEEP"},
        {"name": "b.md", "verdict": "KEEP"},
        {"name": "b.md", "verdict": "SUPERSEDED"},
    ]


def _memory_repo(tmp: Path) -> tuple[Path, Path]:
    repo = tmp / "repo"
    agent = tmp / "agent"
    (repo / ".memory").mkdir(parents=True)
    initialize_git_repo(repo)
    (repo / ".memory" / "git-agent-commits.md").write_text(
        "---\nname: git-agent-commits\ndescription: How to commit via git-agent\ntype: decision\n---\n\nLong body that must not be injected.\n",
        encoding="utf-8",
    )
    (repo / ".memory" / "no-description.md").write_text(
        "---\nname: no-description\n---\n\nBody only, no frontmatter description.\n",
        encoding="utf-8",
    )
    return repo, agent


def _format_block(repo: Path, agent: Path, options: str = "") -> dict[str, object]:
    return run_bun(
        f"""
        process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
        const {{ loadAndDeduplicateMemories, formatMemoriesBlock }} = await import('./packages/continual-learning/extensions/memory-files.ts');
        const memories = await loadAndDeduplicateMemories({json.dumps(str(repo))});
        console.log(JSON.stringify({{ block: formatMemoriesBlock(memories{options}) }}));
        """,
    )


def test_memory_block_is_an_index_without_entry_bodies() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo, agent = _memory_repo(Path(tmp))
        block = _format_block(repo, agent)["block"]
        assert "- git-agent-commits.md — How to commit via git-agent" in block
        assert "must not be injected" not in block
        assert "Body only" not in block
        assert "read" in block.lower()


def test_memory_block_without_description_still_indexed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo, agent = _memory_repo(Path(tmp))
        block = _format_block(repo, agent)["block"]
        assert "- no-description.md" in block


def test_memory_index_is_bounded_at_entry_boundaries() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo, agent = _memory_repo(Path(tmp))
        (repo / ".memory" / "huge.md").write_text(
            "---\nname: huge\ndescription: " + ("x" * 400) + "\n---\n\nbody\n",
            encoding="utf-8",
        )
        full_block = _format_block(repo, agent)["block"]
        full_lines = full_block.splitlines()
        first_entry = next(index for index, line in enumerate(full_lines) if line.startswith("- "))
        # A roomy budget lists complete filenames; bounded cues may give way.
        bare = [line.split(" — ")[0] for line in full_lines[first_entry:]]
        first_budget = len("\n".join(full_lines[:first_entry])) + 1 + sum(len(line) + 1 for line in bare)
        block = _format_block(repo, agent, f", {first_budget}")["block"]
        lines = [line for line in block.splitlines() if line.startswith("- ")]
        assert lines == bare
        assert "omitted" not in block
        assert len(block) <= first_budget


def test_bounds_and_semantic_holds_trigger_repair_but_refusals_do_not() -> None:
    # Given a review outcome reason, When the parent decides whether to repair the
    # plan semantically, Then an uncertain or unsupported judgment and a bounds
    # refusal trigger a repair, while privacy, availability, and success do not.
    # Measured need: a weak generator's review was refused at a bound and the whole
    # Memory review was lost with zero operations instead of being repaired.
    from support import run_bun

    value = run_bun(
        """
        import { repairTriggersSemantics } from './packages/continual-learning/extensions/inject-memory.ts';
        console.log(JSON.stringify({
          triggers: ['uncertain','unsupported','bounds'].map(repairTriggersSemantics),
          doesNot: ['supported','sensitive','unavailable','timeout','cancelled','duplicate','conflict','scope-expansion','private-memory-denied','missing-key','invalid-response','disabled','missing-config','invalid-config','scope-denied'].map(repairTriggersSemantics),
        }));
        """
    )
    assert value['triggers'] == [True, True, True]
    assert not any(value['doesNot'])


def test_candidate_citations_must_quote_the_entry_they_cite() -> None:
    # Given candidates whose citations are checked before any judge call, When a
    # quote is absent from the entry it cites, the index is out of range, or a
    # candidate cites nothing, Then the parent reports a controlled problem so the
    # plan can be repaired instead of being sent to a degenerate review. Measured
    # need: a weak generator cited entry 0 for every candidate while quoting four
    # different entries, and the review then died at a bound.
    from support import run_bun

    value = run_bun(
        """
        import { candidateCitationProblems } from './packages/continual-learning/extensions/inject-memory.ts';
        const evidence = { entries: [
          { message: { role: 'user', content: 'This project uses pnpm.' } },
          { message: { role: 'toolResult', content: 'pnpm test passed: 8 tests.' } },
        ] };
        const sound = [{ name: 'a.md', content: 'The project uses pnpm.', evidence: [{ index: 0, quote: 'This project uses pnpm.', role: 'user' }] }];
        const wrongEntry = [{ name: 'a.md', content: 'Use pnpm test.', evidence: [{ index: 0, quote: 'pnpm test passed: 8 tests.', role: 'toolResult' }] }];
        const outOfRange = [{ name: 'a.md', content: 'Use pnpm test.', evidence: [{ index: 7, quote: 'pnpm test passed: 8 tests.', role: 'toolResult' }] }];
        const uncited = [{ name: 'a.md', content: 'Use pnpm test.' }];
        console.log(JSON.stringify({
          sound: candidateCitationProblems(evidence, sound),
          wrongEntry: candidateCitationProblems(evidence, wrongEntry),
          outOfRange: candidateCitationProblems(evidence, outOfRange),
          uncited: candidateCitationProblems(evidence, uncited),
        }));
        """
    )
    assert value['sound'] == []
    assert value['wrongEntry'] and 'quote' in value['wrongEntry'][0]
    assert value['outOfRange'] and 'range' in value['outOfRange'][0]
    assert value['uncited'] and 'citation' in value['uncited'][0]


def test_memory_plan_expansion_checks_citations_before_any_judge_call() -> None:
    # All generation paths use one citation contract before semantic review.
    text = source()
    expansion = text.index("plan = await expandCitedIncrementalMemoryPlan(run, selectedScope, rawPlan);")
    assert expansion < text.index('opts.jevJudge!.validate("memory"')
    assert 'plan = await expandCitedIncrementalMemoryPlan(run, selectedScope, repair.plan);' in text
    corrected = text.index('const corrected = await expandCitedIncrementalMemoryPlan(run, selectedScope, distilled.plan);')
    assert text.index('const distilled = distillReviewedNewMemory(repaired.plan, candidates, mutationReview?.candidateReview,') < corrected
    assert corrected < text.index('const correctedVerdict = await validateKnowledge(correctedCandidates);')


def test_screened_constraint_with_no_harness_rule_is_named_not_silent() -> None:
    # Given the Harness phase screened constraint evidence, When the plan arrives with
    # zero operations, Then the attempt records a controlled diagnostic naming the
    # coverage miss instead of a bare noop. Measured need: the weak generator produced
    # an empty Harness plan while the task stated a durable prohibition, and the arm
    # failed with no explanation in the receipt. The attempt outcome stays noop,
    # because an existing rule can legitimately cover the constraint already; only a
    # named gap is safe here.
    text = source()
    marker = "Harness plan has no rule although constraint evidence was screened"
    assert marker in text
    coverage = text.index("const coverageMiss = harnessPlan.ok && harnessOperations === 0 && screen.harness === true;")
    assert coverage < text.index(marker)
    assert "operations: harnessOperations," in text[coverage:coverage + 900]


def test_fixed_raw_plan_stamps_identity_so_the_pipeline_derives_the_rest() -> None:
    # Given the attribution seam, When a fixed candidate list becomes a raw plan,
    # Then it carries the live run identity and only that candidate list, so
    # expandIncrementalMemoryPlan derives operations, inventory and staleness from
    # the fixed candidates instead of carrying metadata about other ones. The seam
    # reads PI_FIXED_MEMORIES, which is unset in production and in this suite.
    from support import run_bun

    value = run_bun(
        """
        import { fixedRawPlan } from './packages/continual-learning/extensions/inject-memory.ts';
        const manifest = { runId: 'run_x', scopeKey: 'scope', scopeDigest: 'digest', snapshotDigest: 'snap' };
        const memories = [{ name: 'fixed.md', kind: 'project', classification: 'safe', content: 'body', evidence: [{ index: 0, quote: 'q', role: 'user' }] }];
        const plan = fixedRawPlan(manifest, memories);
        console.log(JSON.stringify({
          kind: plan.kind,
          identity: [plan.runId, plan.scopeKey, plan.scopeDigest, plan.artifactHash, plan.snapshotDigest],
          names: plan.newMemories.map(m => m.name),
          operations: plan.operations,
          keys: Object.keys(plan).sort(),
          envSet: typeof process.env.PI_FIXED_MEMORIES === 'string',
        }));
        """
    )
    assert value['kind'] == 'incremental-memory-plan'
    assert value['identity'] == ['run_x', 'scope', 'digest', 'snap', 'snap']
    assert value['names'] == ['fixed.md']
    assert value['operations'] == []
    assert value['keys'] == sorted(['kind', 'version', 'schemaVersion', 'runId', 'scopeKey', 'scopeDigest', 'artifactHash', 'snapshotDigest', 'operations', 'newMemories'])
    assert value['envSet'] is False


def test_a_supplied_fixed_plan_survives_a_planner_model_error(tmp_path: Path) -> None:
    # Given a planner that reports a model error and returns no plan, When the
    # attribution seam supplies the plan, Then the memory phase must reach the
    # semantic judge instead of stopping at the planner error. Without the seam
    # the same error must still stop the phase, so the seam alone changes it.
    fixture = Path(__file__).with_name("learning-policy-harness.ts")
    fixed = tmp_path / "fixed-memories.json"
    fixed.write_text(
        json.dumps([
            {
                "name": "concise.md",
                "kind": "project",
                "classification": "safe",
                "content": "---\nname: concise\ndescription: Prefer concise progress updates\ntype: project\n---\nPrefer concise progress updates.\n",
                "evidence": [{"index": 0, "quote": "I prefer concise progress updates.", "role": "user"}],
            }
        ]),
        encoding="utf-8",
    )

    def memory_attempts(value: object) -> list[tuple[object, object]]:
        receipt = value.get("registryReceipt") or {}
        return [
            (attempt.get("outcome"), attempt.get("diagnostic"))
            for attempt in (receipt.get("attempts") or [])
            if attempt.get("phase") == "memory"
        ]

    without_seam = run_bun_script(fixture, "planner-model-error")
    with_seam = run_bun_script(fixture, "planner-model-error", env={"PI_FIXED_MEMORIES": str(fixed)})

    assert memory_attempts(without_seam) == [("failed", "memory planner model error")]
    assert without_seam["history"] == []
    reached = memory_attempts(with_seam)
    assert reached and reached[0][0] != "failed", reached
    assert reached[0][1] != "memory planner model error", reached
    assert [record for record in with_seam["history"] if record["phase"] == "memory"], with_seam["history"]


def test_automatic_truncated_pipeline_retains_valid_input_provenance(tmp_path) -> None:
    result = run_bun(f'''
      import fs from 'node:fs/promises';
      import register from './packages/continual-learning/extensions/inject-memory.ts';
      import {{resolveMemoryPaths}} from './packages/continual-learning/extensions/memory-paths.ts';
      import {{isLearningPipelineReceipt}} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const cwd={json.dumps(str(tmp_path / 'project'))}; await fs.mkdir(cwd);
      const paths=resolveMemoryPaths(cwd); await fs.mkdir(paths.agentDir,{{recursive:true}});
      await fs.writeFile(paths.agentDir+'/continual-learning.json',JSON.stringify({{jev:false}}));
      await fs.mkdir(paths.harnessDir,{{recursive:true}});
      await fs.writeFile(paths.settingsFile,JSON.stringify({{autoMemory:true,automaticPhases:{{memory:'off',harness:'off',agents:'off'}}}}));
      const hooks=new Map();const notices=[];
      register({{on:(n,f)=>hooks.set(n,f),registerCommand:()=>{{}},sendMessage:()=>{{}},appendEntry:()=>{{}},getCommands:()=>[],exec:async()=>({{stdout:'',stderr:'',code:0}})}});
      const entries=[{{message:{{role:'user',content:'Audit the actual source'}}}},...Array.from({{length:300}},(_,n)=>({{message:{{role:'toolResult',content:'source '+n}}}}))];
      const ctx={{cwd,hasUI:false,ui:{{notify:(x)=>notices.push(x)}},sessionManager:{{getBranch:()=>entries,buildContextEntries:()=>entries}}}};
      await hooks.get('input')({{source:'interactive'}},ctx);
      await hooks.get('agent_settled')({{}},ctx);
      const files=await fs.readdir(paths.runsDir,{{recursive:true}});
      const f=files.find(x=>x.endsWith('learning-pipeline-receipt.json'));
      const receipt=f?JSON.parse(await fs.readFile(paths.runsDir+'/'+f,'utf8')):null;
      console.log(JSON.stringify({{receipt,valid:isLearningPipelineReceipt(receipt),notices}}));
    ''',env={'PI_CODING_AGENT_DIR':str(tmp_path / 'agent')})
    assert result['valid'] is True, result
    assert result['receipt']['input']['source'] == 'current-session'
    assert result['receipt']['input']['entryCount'] == 301
    assert result['receipt']['input']['omittedEvidenceEntries'] > 0
