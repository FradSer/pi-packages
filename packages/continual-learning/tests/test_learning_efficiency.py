from __future__ import annotations

# --- Merged from test_learning_efficiency.py ---
import json

from support import run_bun



def test_receipt_batches_survive_later_and_concurrent_registry_writes(tmp_path):
    value=run_bun(r"""
      import fs from 'node:fs/promises';import path from 'node:path';
      import {buildLearningReceipt,writeLearningReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const root=ROOT,screen={memory:true,harness:false,agents:false,reasons:[]};
      const make=(id,cost)=>buildLearningReceipt('manual',screen,[{phase:'memory',attempt:0,outcome:'noop',operations:0,durationMs:1,
        usage:{input:1,output:0,cacheRead:0,cacheWrite:0,totalTokens:1,cost}}],undefined,'batch_'+id.repeat(32));
      const a=make('a',.1),b=make('b',.2),c=make('c',.3);
      await writeLearningReceipt(root,a);await writeLearningReceipt(root,b);
      const retained=JSON.parse(await fs.readFile(path.join(root,'receipts',a.batchId,'learning-pipeline-receipt.json'),'utf8'));
      await Promise.all([writeLearningReceipt(root,b),writeLearningReceipt(root,c)]);
      const stored=await Promise.all([a,b,c].map(async r=>JSON.parse(await fs.readFile(path.join(root,'receipts',r.batchId,'learning-pipeline-receipt.json'),'utf8'))));
      console.log(JSON.stringify({retained,stored,latest:JSON.parse(await fs.readFile(path.join(root,'learning-pipeline-receipt.json'),'utf8'))}));
    """.replace('ROOT',json.dumps(str(tmp_path/'receipts'))))
    assert value['retained']['totals']['cost']==.1
    assert [row['totals']['cost']for row in value['stored']]==[.1,.2,.3]
    assert value['latest']['batchId'] in [row['batchId']for row in value['stored']]

def test_declined_drafts_are_processed_but_never_reported_as_learning():
    value = run_bun(r'''
      import {buildLearningReceipt,isLearningPipelineReceipt,learningSummarySubject,learningSummaryTone} from './packages/continual-learning/extensions/learning-efficiency.ts';
      import {learningReceiptComplete} from './packages/continual-learning/extensions/learning-replay.ts';
      const usage={input:3,output:2,cacheRead:0,cacheWrite:0,totalTokens:5,cost:.1};
      const screen={memory:true,harness:false,agents:false,reasons:[]};
      const attempt={phase:'memory',attempt:1,outcome:'declined',operations:0,declinedOperations:1,durationMs:4,usage};
      const receipt=buildLearningReceipt('automatic',screen,[attempt]);
      const mixed=buildLearningReceipt('automatic',screen,[{...attempt,outcome:'applied',operations:1}]);
      console.log(JSON.stringify({valid:isLearningPipelineReceipt(receipt),complete:learningReceiptComplete(receipt),operations:receipt.operations,
        subject:learningSummarySubject(receipt),tone:learningSummaryTone(receipt),mixed:learningSummarySubject(mixed),
        pending:learningReceiptComplete({...receipt,attempts:[{...attempt,pendingOperations:1}]}),
        invalid:isLearningPipelineReceipt({...receipt,attempts:[{...attempt,operations:1}]})}));
    ''')
    assert value['valid'] and value['complete'] and value['operations'] == 0
    assert 'not learned' in value['subject'] and value['tone'] == 'warning'
    assert 'applied' in value['mixed'] and 'not learned' in value['mixed']
    assert not value['pending'] and not value['invalid']


def test_automatic_screen_skips_chitchat_and_routes_durable_evidence() -> None:
    result = run_bun("""
      import { screenLearningEntries } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const wrap = text => ({ message: { role: 'user', content: [{ type: 'text', text }] } });
      console.log(JSON.stringify({
        chat: screenLearningEntries([wrap('Thanks, run the tests.')], 'automatic'),
        preference: screenLearningEntries([wrap('For future tasks, I prefer concise updates.')], 'automatic'),
        constraint: screenLearningEntries([wrap('Do not use npm; use pnpm instead.')], 'automatic'),
        agents: screenLearningEntries([wrap('The AGENTS.md workflow instruction is wrong; use BDD instead.')], 'automatic'),
        manual: screenLearningEntries([], 'manual'),
        full: screenLearningEntries([], 'full'),
      }));
    """)
    assert result["chat"]["memory"] is False
    assert result["chat"]["harness"] is False
    assert result["preference"]["memory"] is True
    assert result["constraint"]["memory"] is True
    assert result["constraint"]["harness"] is True
    assert result["agents"]["agents"] is True
    assert result["manual"] == {"memory": True, "harness": True, "agents": True, "reasons": ["manual-incremental"]}
    assert result["full"] == {"memory": True, "harness": True, "agents": True, "reasons": ["manual-full"]}


def test_automatic_screen_keeps_explicit_knowledge_and_validation_opportunities() -> None:
    result = run_bun("""
      import { screenLearningEntries } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const screen = text => screenLearningEntries([{ message: { role: 'user', content: text } }], 'automatic');
      console.log(JSON.stringify({
        knowledge: screen('Remember for future tasks: this project uses pnpm and Node 22.'),
        definition: screen('In this repository, the generated client is the source of truth.'),
        validation: screen('Add a regression test that verifies the lockfile is never rewritten.'),
        question: screen('Should I run the tests now?'),
      }));
    """)
    assert result["knowledge"]["memory"] is True
    assert result["definition"]["memory"] is True
    assert result["validation"]["harness"] is True
    assert result["validation"]["memory"] is True
    assert result["question"]["memory"] is False
    assert result["question"]["harness"] is False


def test_equivalent_durable_prohibitions_route_to_memory_and_harness() -> None:
    result = run_bun("""
      import { screenLearningEntries } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const screen = text => screenLearningEntries([{ message: { role: 'user', content: [{ type: 'text', text }] } }], 'automatic');
      console.log(JSON.stringify({
        never: screen('Never run the retired compiler.'),
        prohibit: screen('Prohibit writes to generated files.'),
        prohibited: screen('The retired compiler is prohibited in this project.'),
        alwaysBlock: screen('Always block shell writes to the lockfile.'),
        asciiApostrophe: screen("Don't invoke npm for this repository."),
        curlyApostrophe: screen('Don’t invoke npm for this repository.'),
        chineseBuyao: screen('不要在这个项目中使用 npm。'),
        chineseJinzhi: screen('禁止修改生成文件。'),
        chineseBude: screen('不得提交密钥。'),
        blockedProgress: screen('Progress was blocked by a temporary network outage.'),
        prohibitionHistory: screen('This document describes the history of prohibition laws.'),
      }));
    """)
    for key in ("never", "prohibit", "prohibited", "alwaysBlock", "asciiApostrophe", "curlyApostrophe", "chineseBuyao", "chineseJinzhi", "chineseBude"):
        assert result[key]["memory"] is True, key
        assert result[key]["harness"] is True, key
    for key in ("blockedProgress", "prohibitionHistory"):
        assert result[key]["memory"] is False, key
        assert result[key]["harness"] is False, key


def test_tool_verified_recovery_routes_memory_without_learning_from_claims() -> None:
    result = run_bun(r"""
      import { screenLearningEntries } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const user = { message: { role: 'user', content: '修复这个构建错误。' } };
      const tool = (content, extra = {}) => ({ message: { role: 'toolResult', toolName: 'bash', content, ...extra } });
      const failed = tool('Error: unsupported runtime version 18', {isError: true});
      const passed = tool('Changed runtime to 22; build succeeded.', {isError: false});
      const screen = entries => screenLearningEntries([user, ...entries], 'automatic');
      console.log(JSON.stringify({
        recovered: screen([failed, passed]),
        unstructured: screen([tool('Error: unsupported runtime version 18'), tool('Build succeeded.')]),
        chinese: screen([tool('编译失败：运行时版本不兼容'), tool('升级后构建通过')]),
        unresolved: screen([failed]),
        backwards: screen([passed, failed]),
        unrelatedRead: screen([failed, {message:{role:'toolResult', toolName:'read', content:'File read successfully.', isError:false}}]),
        assistantClaim: screen([failed, {message:{role:'assistant',content:'Build succeeded.'}}]),
        successOnly: screen([passed]),
        stillFailed: screen([failed, tool('Tests passed: 3; tests failed: 1', {isError:true})]),
      }));
    """)
    for name in ("recovered", "unstructured", "chinese"):
        assert result[name]["memory"] is True, name
        assert result[name]["harness"] is False, name
        assert result[name]["agents"] is False, name
        assert "verified-tool-recovery" in result[name]["reasons"]
    for name in ("unresolved", "backwards", "unrelatedRead", "assistantClaim", "successOnly", "stillFailed"):
        assert result[name]["memory"] is False, name


def test_learning_subject_includes_agents_only_and_mixed_changes() -> None:
    result = run_bun(r"""
      import { buildLearningReceipt, learningSummarySubject } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const attempt = (phase, operations) => ({phase, operations, attempt:0, outcome:'applied', durationMs:1});
      const subject = attempts => learningSummarySubject(buildLearningReceipt('manual', {memory:true,harness:true,agents:true,reasons:[]}, attempts));
      console.log(JSON.stringify({
        single: subject([attempt('agents', 1)]),
        plural: subject([attempt('agents', 2)]),
        mixed: subject([attempt('memory', 1), attempt('harness', 1), attempt('agents', 2)]),
      }));
    """)
    assert result["single"] == "1 AGENTS.md change applied"
    assert result["plural"] == "2 AGENTS.md changes applied"
    assert result["mixed"] == "1 memory and 1 harness change and 2 AGENTS.md changes applied"


def test_current_task_slice_excludes_long_history_and_pending_next_user() -> None:
    result = run_bun("""
      import { currentTaskSlice } from './packages/continual-learning/extensions/incremental-learning.ts';
      const message = (role, text) => ({ message: { role, content: [{ type: 'text', text }] } });
      const entries = [
        message('user', 'old task'), message('assistant', 'old answer'),
        message('user', 'current task'), message('assistant', 'current answer'), message('toolResult', 'current tool'),
        message('user', 'next task already started'),
      ];
      console.log(JSON.stringify(currentTaskSlice(entries)));
    """)
    texts = json.dumps(result)
    assert "current task" in texts and "current answer" in texts and "current tool" in texts
    assert "old task" not in texts
    assert "next task already started" not in texts


def test_retry_economics_are_mode_and_phase_specific() -> None:
    result = run_bun("""
      import { classifyPlannerRetry, shouldRetryPlanner } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const classify = (mode, phase, failure, attempt = 0, mutated = false) => classifyPlannerRetry({ mode, phase, failure, attempt, mutated });
      const retry = (mode, phase, failure, attempt = 0, mutated = false) => shouldRetryPlanner({ mode, phase, failure, attempt, mutated });
      console.log(JSON.stringify({
        automaticMemorySyntax: classify('automatic', 'memory', 'syntax'),
        automaticMemoryValidation: classify('automatic', 'memory', 'validation'),
        manualMemorySyntax: classify('manual', 'memory', 'syntax'),
        manualMemoryValidation: classify('manual', 'memory', 'validation'),
        manualHarnessSyntax: classify('manual', 'harness', 'syntax'),
        fullAgentsValidation: classify('full', 'agents', 'validation'),
        model: classify('manual', 'memory', 'model'),
        timeout: classify('full', 'memory', 'timeout'),
        secondAttempt: classify('manual', 'memory', 'syntax', 1),
        mutated: classify('manual', 'memory', 'syntax', 0, true),
        booleanHelper: retry('manual', 'memory', 'validation'),
      }));
    """)
    assert result == {
        "automaticMemorySyntax": "incremental-memory-repair",
        "automaticMemoryValidation": "incremental-memory-repair",
        "manualMemorySyntax": "incremental-memory-repair",
        "manualMemoryValidation": "incremental-memory-repair",
        "manualHarnessSyntax": "none",
        "fullAgentsValidation": "full-planner-retry",
        "model": "none",
        "timeout": "none",
        "secondAttempt": "none",
        "mutated": "none",
        "booleanHelper": True,
    }


def test_receipt_reports_result_and_cost() -> None:
    result = run_bun("""
      import { buildLearningReceipt, formatLearningSummary } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const receipt = buildLearningReceipt('automatic', { memory: true, harness: true, agents: true, reasons: ['durable-user-evidence'] }, [
        { phase: 'memory', attempt: 0, outcome: 'applied', durationMs: 20, operations: 2, usage: { input: 10, output: 2, cacheRead: 3, cacheWrite: 0, totalTokens: 12, cost: 0.01 } },
        { phase: 'harness', attempt: 0, outcome: 'failed', durationMs: 5, operations: 0 },
        { phase: 'agents', attempt: 0, outcome: 'noop', durationMs: 4, operations: 0 },
      ]);
      console.log(JSON.stringify({ receipt, summary: formatLearningSummary(receipt) }));
    """)
    assert result["receipt"]["operations"] == 2
    assert [attempt["outcome"] for attempt in result["receipt"]["attempts"]] == ["applied", "failed", "noop"]
    assert result["receipt"]["totals"] == {
        "input": 10,
        "output": 2,
        "cacheRead": 3,
        "cacheWrite": 0,
        "totalTokens": 12,
        "cost": 0.01,
    }
    assert result["receipt"]["retries"] == 0
    assert "2 memories applied" in result["summary"]
    assert "input 10" in result["summary"]
    assert "output 2" in result["summary"]
    assert "cacheRead 3" in result["summary"]
    assert "cacheWrite 0" in result["summary"]
    assert "total 12" in result["summary"]
    assert "$0.0100" in result["summary"]


def test_summary_marks_zero_provider_cost_with_nonzero_usage_unavailable() -> None:
    result = run_bun("""
      import { buildLearningReceipt, formatLearningCost, formatLearningSummary } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const screen = { memory: true, harness: false, agents: false, reasons: ['durable-user-evidence'] };
      const unavailable = buildLearningReceipt('manual', screen, [
        { phase: 'memory', attempt: 0, outcome: 'applied', durationMs: 8, operations: 1, usage: { input: 9, output: 2, cacheRead: 4, cacheWrite: 1, totalTokens: 0, cost: 0 } },
      ]);
      const unused = buildLearningReceipt('manual', screen, []);
      console.log(JSON.stringify({
        unavailableCost: formatLearningCost(unavailable.totals),
        unavailableSummary: formatLearningSummary(unavailable),
        unusedCost: formatLearningCost(unused.totals),
        unusedSummary: formatLearningSummary(unused),
      }));
    """)
    assert result["unavailableCost"] == "cost unavailable"
    assert "cost unavailable" in result["unavailableSummary"]
    assert "$0.0000" not in result["unavailableSummary"]
    assert result["unusedCost"] == "$0.0000"
    assert "$0.0000" in result["unusedSummary"]


def test_mixed_priced_and_unavailable_attempts_keep_cost_unavailable() -> None:
    result = run_bun("""
      import { buildLearningReceipt, formatLearningSummary } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const receipt = buildLearningReceipt('manual', { memory: true, harness: true, agents: false, reasons: [] }, [
        { phase: 'selector', attempt: 0, outcome: 'applied', durationMs: 1, operations: 0, usage: { input: 5, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 6, cost: 0.01 } },
        { phase: 'memory', attempt: 0, outcome: 'applied', durationMs: 1, operations: 1, usage: { input: 10, output: 2, cacheRead: 3, cacheWrite: 0, totalTokens: 15, cost: 0 } },
      ]);
      console.log(JSON.stringify({ available: receipt.costAvailable, summary: formatLearningSummary(receipt) }));
    """)
    assert result["available"] is False
    assert "cost unavailable" in result["summary"]
    assert "$0.0100" not in result["summary"]


def test_harness_activity_comes_from_harness_owned_entries_not_file_text() -> None:
    result = run_bun(r"""
      import { screenLearningEntries } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const user = { message: { role: 'user', content: 'Explain the consolidation pipeline for this package.' } };
      const tool = (content, extra = {}) => ({ message: { role: 'toolResult', toolName: 'bash', content, ...extra } });
      const screen = entries => screenLearningEntries(entries, 'automatic');
      console.log(JSON.stringify({
        repositoryText: screen([user, tool('grep -n "policy" extensions/harness-consolidation.ts\n"policies" | "skillPrompts" | "harness.json"\nPOLICY_HARNESS = Path(...)\nblocked|confirm|violation')]),
        failedCommand: screen([user, tool('error: Cannot find module x', { isError: true })]),
        guardrailEntry: screen([user, { type: 'custom', customType: 'harness-event', data: { kind: 'policy-matched', action: 'block' } }]),
        guidanceMessage: screen([user, { type: 'custom_message', customType: 'harness-guidance', content: '[harness:no-npm] Use pnpm.' }]),
        bashNote: screen([user, tool('command output\n[harness-bash-note] Report the actual output.')]),
        scopedGuidance: screen([user, tool('[harness:no-npm] Only for subjects matching "npm"; use pnpm instead.')]),
      }));
    """)
    assert result["repositoryText"]["harness"] is False, result["repositoryText"]
    assert result["repositoryText"]["memory"] is False, result["repositoryText"]
    assert result["failedCommand"]["harness"] is False, result["failedCommand"]
    for name in ("guardrailEntry", "guidanceMessage", "bashNote", "scopedGuidance"):
        assert result[name]["harness"] is True, name
        assert "verified-harness-event" in result[name]["reasons"], name


def test_manual_selector_decline_survives_tool_only_signals() -> None:
    result = run_bun(r"""
      import { manualIncrementalScreen } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const tool = (content, extra = {}) => ({ message: { role: 'toolResult', toolName: 'bash', content, ...extra } });
      const task = { message: { role: 'user', content: 'Fix the failing build.' } };
      const noise = [tool('grep -n "policy" extensions/harness-consolidation.ts'), tool('Changed the runtime; build succeeded.')];
      const declined = { memory: false, harness: false, agents: false };
      console.log(JSON.stringify({
        noise: manualIncrementalScreen([task, ...noise], declined),
        recovery: manualIncrementalScreen([task, tool('error: bad runtime', { isError: true }), noise[1]], declined),
        constraint: manualIncrementalScreen([{ message: { role: 'user', content: 'Never run the retired compiler.' } }], declined),
        guardrail: manualIncrementalScreen([task, ...noise, { type: 'custom', customType: 'harness-event', data: { kind: 'policy-matched' } }], declined),
        selected: manualIncrementalScreen([task, ...noise], { memory: true, harness: false, agents: true }),
      }));
    """)
    assert result["noise"] == {"memory": False, "harness": False, "agents": False, "reasons": ["manual-incremental", "no-durable-memory-evidence", "no-harness-evidence", "no-agents-evidence"]}, result["noise"]
    assert result["recovery"]["memory"] is False, result["recovery"]
    assert result["recovery"]["reasons"][1] == "selector-declined-memory", result["recovery"]
    assert result["constraint"]["memory"] is True and result["constraint"]["harness"] is True, result["constraint"]
    assert result["guardrail"]["harness"] is True and result["guardrail"]["memory"] is False, result["guardrail"]
    assert result["selected"] == {"memory": True, "harness": False, "agents": True, "reasons": ["manual-incremental", "selector-selected-memory", "no-harness-evidence", "selector-selected-agents"]}, result["selected"]


def test_quiet_learning_subjects_and_details_keep_routine_rows_compact() -> None:
    result = run_bun("""
      import { buildLearningReceipt, learningSummaryDetails, learningSummarySubject } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const screen = { memory: true, harness: false, agents: false, reasons: [] };
      const noop = buildLearningReceipt('automatic', screen, [{ phase: 'selector', attempt: 0, outcome: 'applied', durationMs: 5, operations: 0 }]);
      const changed = buildLearningReceipt('manual', screen, [{ phase: 'memory', attempt: 0, outcome: 'applied', durationMs: 10, operations: 2 }]);
      const failed = buildLearningReceipt('manual', screen, [{ phase: 'memory', attempt: 0, outcome: 'failed', durationMs: 10, operations: 0 }]);
      console.log(JSON.stringify({
        noop: learningSummarySubject(noop), changed: learningSummarySubject(changed), failed: learningSummarySubject(failed), details: learningSummaryDetails(changed),
      }));
    """)
    assert result["noop"] == "no changes written"
    assert result["changed"] == "2 memories applied"
    assert result["failed"] == "finished with issues: memory failed"
    assert any("memory: applied" in line for line in result["details"])


def test_learning_subject_names_memory_and_harness_counts_with_pluralization() -> None:
    result = run_bun("""
      import { buildLearningReceipt, learningSummarySubject } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const screen = { memory: true, harness: true, agents: false, reasons: [] };
      const subject = attempts => learningSummarySubject(buildLearningReceipt('manual', screen, attempts));
      console.log(JSON.stringify({
        singleMemory: subject([{ phase: 'memory', attempt: 0, outcome: 'applied', durationMs: 1, operations: 1 }]),
        mixed: subject([
          { phase: 'memory', attempt: 0, outcome: 'applied', durationMs: 1, operations: 2 },
          { phase: 'harness', attempt: 0, outcome: 'applied', durationMs: 1, operations: 1 },
        ]),
        pluralHarness: subject([{ phase: 'harness', attempt: 0, outcome: 'applied', durationMs: 1, operations: 3 }]),
      }));
    """)
    assert result["singleMemory"] == "1 memory applied"
    assert result["mixed"] == "2 memories and 1 harness change applied"
    assert result["pluralHarness"] == "3 harness changes applied"


def test_selector_is_the_incremental_selection_accounting_phase() -> None:
    result = run_bun("""
      import { buildLearningReceipt, formatLearningSummary } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const receipt = buildLearningReceipt('manual', { memory: true, harness: false, agents: false, reasons: [] }, [
        { phase: 'selector', attempt: 0, outcome: 'applied', durationMs: 3, operations: 0 },
      ]);
      console.log(JSON.stringify({ phase: receipt.attempts[0].phase, summary: formatLearningSummary(receipt) }));
    """)
    assert result["phase"] == "selector"
    assert "no changes written" in result["summary"]
    assert "explorer" not in result["summary"]


def test_usage_aggregation_includes_every_attempt() -> None:
    result = run_bun("""
      import { totalLearningUsage } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const usage = (input, output, cost) => ({ input, output, cacheRead: 2, cacheWrite: 1, totalTokens: input + output, cost });
      console.log(JSON.stringify(totalLearningUsage([
        { phase: 'selector', attempt: 0, outcome: 'applied', durationMs: 10, operations: 0, usage: usage(10, 3, 0.01) },
        { phase: 'memory', attempt: 0, outcome: 'rejected', durationMs: 20, operations: 0, usage: usage(20, 4, 0.02) },
        { phase: 'memory', attempt: 1, outcome: 'applied', durationMs: 20, operations: 1, usage: usage(15, 5, 0.03) },
      ])));
    """)
    assert result == {"input": 45, "output": 12, "cacheRead": 6, "cacheWrite": 3, "totalTokens": 57, "cost": 0.06}


def test_harness_owned_event_summaries_name_the_decision_and_ignore_repository_text() -> None:
    result = run_bun(r"""
      import { harnessOwnedEventSummary } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const tool = (content, extra = {}) => ({ message: { role: 'toolResult', toolName: 'bash', content, ...extra } });
      const behavior = (data) => ({ type: 'custom', customType: 'harness-behavior-observation', data: {
        version: 1, phase: 'decision', sessionId: 'session-fixture',
        toolCallIdDigest: 'a'.repeat(64), inputDigest: 'b'.repeat(64),
        effectiveConfigDigest: 'c'.repeat(64), decision: 'execute',
        revisionCoverage: 'complete', handlerTracking: 'pending', omittedRules: 0,
        taskOutcome: 'unverified', effect: 'cannot-attribute',
        rules: [{ idDigest: 'd'.repeat(64), revision: 'e'.repeat(64), matched: true, enabled: true, action: 'message' }],
        ...data,
      } });
      console.log(JSON.stringify({
        behaviorDecision: harnessOwnedEventSummary(behavior({})) ?? null,
        handlerResult: harnessOwnedEventSummary(behavior({ phase: 'handler-result', decisionEntryId: 'dec1de00',
          handlerInvoked: true, handlerTiming: 'observed', isError: true, durationMs: 17, resultDigest: 'f'.repeat(64) })) ?? null,
        missingTiming: harnessOwnedEventSummary(behavior({ phase: 'handler-result', decisionEntryId: 'dec1de00',
          handlerInvoked: null, handlerTiming: 'absent' })) ?? null,
        invalidTiming: harnessOwnedEventSummary(behavior({ phase: 'handler-result', decisionEntryId: 'dec1de00',
          handlerInvoked: true, handlerTiming: 'observed', durationMs: Infinity, resultDigest: 'SECRET_INVALID_RESULT' })) ?? null,
        unknownDecision: harnessOwnedEventSummary(behavior({ decision: 'helped' })) ?? null,
        invalidVersion: harnessOwnedEventSummary(behavior({ version: 2 })) ?? null,
        unknownPhase: harnessOwnedEventSummary(behavior({ phase: 'helped' })) ?? null,
        fakeCustomRole: harnessOwnedEventSummary({ ...behavior({}), role: 'assistant' }) ?? null,
        badDigest: harnessOwnedEventSummary(behavior({ toolCallIdDigest: 'SECRET_INVALID_DIGEST' })) ?? null,
        invalidOutcome: harnessOwnedEventSummary(behavior({ taskOutcome: 'passed', effect: 'helped' })) ?? null,
        badRule: harnessOwnedEventSummary(behavior({ rules: [{ matched: true, idDigest: 'bad', revision: 'SECRET_INVALID_REVISION' }] })) ?? null,
        fakeAssistant: harnessOwnedEventSummary({ type: 'message', message: { role: 'assistant',
          customType: 'harness-behavior-observation', content: JSON.stringify(behavior({})) } }) ?? null,
        oversized: harnessOwnedEventSummary(behavior({ omittedRules: 4, revisionCoverage: 'incomplete',
          reason: 'SECRET_MUST_NOT_APPEAR'.repeat(2000),
          rules: Array.from({length: 128}, () => ({ idDigest: 'd'.repeat(64), revision: 'e'.repeat(64), matched: true, enabled: true, action: 'message' })) })) ?? null,
        decision: harnessOwnedEventSummary({ type: 'custom', customType: 'harness-event', data: {
          kind: 'policy-matched', policy: 'no-bulk-memory-deletion', action: 'block', tool: 'bash',
          outcome: 'blocked by rule', reason: 'Project memory must not be bulk-deleted.', source: 'project', file: '.pi/harness.json',
        } }),
        note: harnessOwnedEventSummary(tool('total 12\n[harness-bash-note]\n[harness:no-npm] Use pnpm for installs.')),
        guidance: harnessOwnedEventSummary({ type: 'custom_message', customType: 'harness-guidance', content: '[harness:no-npm] Use pnpm for installs.' }),
        repositoryText: harnessOwnedEventSummary(tool('extensions/HARNESS-DESIGN.md\npolicy blocked confirmation violation')) ?? null,
        assistantText: harnessOwnedEventSummary({ message: { role: 'assistant', content: 'The harness policy stage is documented.' } }) ?? null,
      }));
    """)
    behavior = result["behaviorDecision"]
    assert behavior and '"decision":"execute"' in behavior
    assert '"taskOutcome":"unverified"' in behavior and '"effect":"cannot-attribute"' in behavior
    assert "d" * 64 in behavior and "e" * 64 in behavior
    assert '"phase":"handler-result"' in result["handlerResult"]
    assert '"decisionEntryId":"dec1de00"' in result["handlerResult"]
    assert '"isError":true' in result["handlerResult"] and "f" * 64 in result["handlerResult"]
    assert '"handlerInvoked":null' in result["invalidTiming"] and '"handlerTiming":"invalid"' in result["invalidTiming"]
    assert '"resultDigest":null' in result["invalidTiming"] and "SECRET_INVALID_RESULT" not in result["invalidTiming"]
    assert '"handlerInvoked":null' in result["missingTiming"] and '"isError":null' in result["missingTiming"]
    assert result["unknownDecision"] is None and result["invalidVersion"] is None and result["fakeAssistant"] is None
    assert result["badDigest"] is None and result["unknownPhase"] is None and result["fakeCustomRole"] is None
    assert '"taskOutcome":"unknown"' in result["invalidOutcome"] and '"effect":"unknown"' in result["invalidOutcome"]
    assert '"invalidMatchedRules":1' in result["badRule"] and "SECRET_INVALID_REVISION" not in result["badRule"]
    assert result["oversized"] and len(result["oversized"]) <= 1000
    assert "SECRET_MUST_NOT_APPEAR" not in result["oversized"]
    assert '"producerOmittedRules":4' in result["oversized"]
    assert '"omittedMatchedRules":' in result["oversized"]
    assert "blocked by rule" in result["decision"]
    assert "no-bulk-memory-deletion" in result["decision"]
    assert "Project memory must not be bulk-deleted." in result["decision"]
    assert "no-npm" in result["note"] and "Use pnpm for installs." in result["note"]
    assert "total 12" not in result["note"]
    assert "Use pnpm for installs." in result["guidance"]
    assert result["repositoryText"] is None
    assert result["assistantText"] is None


def test_receipt_identifies_a_description_hold_without_printing_arbitrary_fields() -> None:
    result = run_bun(r"""
      import { buildLearningReceipt, learningSummaryDetails } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const outputs=[];
      for(const field of [undefined,'description','UNTRUSTED_FIELD']){
        const jev={stage:'memory',status:'propose',reason:'unsupported',durationMs:1,model:'jev-1.13.0',candidateIndex:0,dimension:'support',field};
        const receipt=buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[{phase:'memory',attempt:0,outcome:'proposed',durationMs:1,operations:0,jev}]);
        outputs.push(learningSummaryDetails(receipt).join('\n'));
      }
      console.log(JSON.stringify(outputs));
    """)
    assert 'candidate 0 support.description' in result[1]
    assert 'candidate 0 support.description' not in result[0]
    assert 'UNTRUSTED_FIELD' not in result[2]


def test_receipt_displays_only_valid_http_error_statuses() -> None:
    value = run_bun(r'''
      import {buildLearningReceipt,learningSummaryDetails} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const rows=[];
      for(const status of [400,429,503,599,399,600,'PRIVATE_DIAGNOSTIC_DO_NOT_LOG']){
        const receipt=buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[
          {phase:'memory',attempt:0,outcome:'proposed',durationMs:1,operations:0,jev:{stage:'memory',status:'propose',reason:'unavailable',durationMs:1,httpStatus:status}}]);
        rows.push({status,lines:learningSummaryDetails(receipt)});
      }console.log(JSON.stringify(rows));
    ''')
    for row in value:
        text = '\n'.join(row['lines'])
        if isinstance(row['status'], int) and 400 <= row['status'] <= 599:
            assert f"HTTP {row['status']}" in text
        else:
            assert 'HTTP ' not in text
        assert 'PRIVATE_DIAGNOSTIC' not in text


def test_partial_application_receipt_separates_applied_and_pending_records() -> None:
    result = run_bun("""
      import {buildLearningReceipt, learningSummarySubject, isLearningPipelineReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const receipt = buildLearningReceipt('manual', {memory:true,harness:false,agents:false,reasons:[]}, [
        {phase:'memory',attempt:0,outcome:'proposed',durationMs:1,operations:0},
        {phase:'memory',attempt:1,outcome:'applied',durationMs:1,operations:2,pendingOperations:1},
      ]);
      const valid = value => isLearningPipelineReceipt({...receipt, attempts:[{...receipt.attempts[1],pendingOperations:value}]});
      console.log(JSON.stringify({subject:learningSummarySubject(receipt),operations:receipt.operations,
        original:isLearningPipelineReceipt(receipt),negative:valid(-1),fraction:valid(.5),text:valid('1')}));
    """)
    assert result['subject'] == '2 memories applied; 1 pending review'
    assert result['operations'] == 2 and result['original'] is True
    assert result['negative'] is False and result['fraction'] is False and result['text'] is False


def test_semantic_receipt_labels_do_not_invent_evidence_window_counts() -> None:
    value = run_bun("""
      import {buildLearningReceipt,learningSummaryDetails} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const rows=['same-batch-relations','standalone-memory'].map(strategy=>learningSummaryDetails(
        buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[
          {phase:'memory',attempt:0,outcome:'noop',durationMs:5,operations:0,
            jev:{stage:'memory',status:'propose',reason:'uncertain',strategy,durationMs:5,model:'jev-1.13.0'}}])).join('\\n'));
      console.log(JSON.stringify(rows));
    """)
    assert all('undefined' not in row and 'full review' not in row for row in value)
    assert 'same-batch relations' in value[0]
    assert 'standalone meaning' in value[1]


def test_learning_summary_details_formats_human_durations_and_disambiguates_retries() -> None:
    result = run_bun("""
      import { buildLearningReceipt, learningSummaryDetails, formatDurationMs } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const receipt = buildLearningReceipt('full', { memory: true, harness: true, agents: true, reasons: [] }, [
        { phase: 'memory', attempt: 0, outcome: 'failed', durationMs: 33746, operations: 0, diagnostic: 'memory planner produced no usable plan' },
        { phase: 'memory', attempt: 1, outcome: 'proposed', durationMs: 909154, operations: 0, diagnostic: 'Jev propose: private-memory-denied',
          jev: { stage: 'memory', status: 'propose', reason: 'private-memory-denied', durationMs: 0 } },
        { phase: 'harness', attempt: 0, outcome: 'noop', durationMs: 14162, operations: 0 },
        { phase: 'agents', attempt: 0, outcome: 'noop', durationMs: 28211, operations: 0 },
      ]);
      const lines = learningSummaryDetails(receipt);
      console.log(JSON.stringify({
        lines,
        durations: [formatDurationMs(33746), formatDurationMs(909154), formatDurationMs(14162), formatDurationMs(28211), formatDurationMs(5)],
      }));
    """)
    assert result["durations"] == ["33.7s", "15m 9s", "14.2s", "28.2s", "5 ms"]
    text = "\n".join(result["lines"])
    assert "memory #1 reason · memory planner produced no usable plan" in text
    assert "memory #2 reason · Jev propose: private-memory-denied" in text
    assert "Jev memory #2 · propose: private-memory-denied" in text
    assert "input unknown" not in text
    assert "output unknown" not in text
    assert "estimated cost unavailable" not in text
    assert "memory #1: failed · 0 change(s) · 33.7s" in text
    assert "memory #2: proposed · 0 change(s) · 15m 9s" in text
    assert "harness: noop · 0 change(s) · 14.2s" in text
    assert "agents: noop · 0 change(s) · 28.2s" in text


def test_receipt_distinguishes_assistant_context_from_primary_evidence_omissions() -> None:
    result = run_bun("""
      import { buildLearningReceipt, learningSummaryDetails, isLearningPipelineReceipt } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const screen = {memory:true,harness:false,agents:false,reasons:[]};
      const receipt = buildLearningReceipt('automatic',screen,[],{source:'current-session',entryCount:130,omittedEntries:34,omittedEvidenceEntries:0});
      const missing = {...receipt,input:{...receipt.input,omittedEvidenceEntries:2}};
      const legacy = {...receipt,input:{source:'current-session',entryCount:130,omittedEntries:34}};
      const invalid = {...receipt,input:{...receipt.input,omittedEvidenceEntries:35}};
      console.log(JSON.stringify({valid:isLearningPipelineReceipt(receipt),invalid:isLearningPipelineReceipt(invalid),
        context:learningSummaryDetails(receipt).join("\\n"), evidence:learningSummaryDetails(missing).join("\\n"), legacy:learningSummaryDetails(legacy).join("\\n")}));
    """)
    assert result['valid'] is True
    assert result['invalid'] is False
    assert '34 assistant context entries omitted' in result['context']
    assert 'proposals only' not in result['context']
    assert '2 evidence entries omitted; proposals only' in result['evidence']
    assert '34 omitted; proposals only' in result['legacy']


def test_zero_worker_preflight_receipt_names_its_stage_and_calls() -> None:
    # Given a preflight failure before any attempt existed, When the parent
    # builds the terminal receipt, Then the stage is "preflight" (not selector)
    # and the summary says no model calls instead of unavailable usage/cost.
    result = run_bun(r"""
      import {buildLearningReceipt,formatLearningSummary,isLearningPipelineReceipt,learningSummarySubject} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const attempt={phase:'preflight',attempt:0,outcome:'failed',durationMs:0,operations:0,diagnostic:'Parent preflight failed before any worker started.'};
      const receipt=buildLearningReceipt('automatic',{memory:false,harness:false,agents:false,reasons:['Parent preflight failed']},[attempt]);
      console.log(JSON.stringify({valid:isLearningPipelineReceipt(receipt),phase:receipt.attempts[0].phase,
        subject:learningSummarySubject(receipt),summary:formatLearningSummary(receipt),
        usageAvailable:receipt.usageAvailable,costAvailable:receipt.costAvailable,totals:receipt.totals}));
    """)
    assert result["valid"] is True
    assert result["phase"] == "preflight"
    assert "preflight failed" in result["subject"], result
    assert "no model calls" in result["summary"], result
    assert "unavailable" not in result["summary"], result
    assert result["totals"]["totalTokens"] == 0


def test_sensitive_evidence_startup_hold_design_is_removed() -> None:
    # Given the user directive to remove the startup privacy hold design, When
    # the receipt module is inspected, Then no hold constants remain and an
    # ordinary screen reason reads as an ordinary outcome.
    value = run_bun(r"""
      import * as efficiency from './packages/continual-learning/extensions/learning-efficiency.ts';
      const legacy = {kind:'learning-pipeline-receipt',version:1,mode:'automatic',
        screen:{memory:true,harness:false,agents:false,reasons:['ordinary-evidence']},
        attempts:[],totals:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:0},
        usageAvailable:true,costAvailable:true,operations:0,retries:0};
      console.log(JSON.stringify({
        exports: Object.keys(efficiency).filter(key => key.includes('SENSITIVE') || key.includes('EVIDENCE_HOLD')),
        subject: efficiency.learningSummarySubject(legacy),
        tone: efficiency.learningSummaryTone(legacy),
      }));
    """)
    assert value["exports"] == [], value
    assert value["subject"] == "no changes written", value
    assert value["tone"] == "success", value


def test_zero_write_subject_is_short_factual_and_jargon_free() -> None:
    # Given a normally settled zero-write receipt, When its subject is shown,
    # Then it is one short factual line ("no changes written") rather than the
    # engineering-jargon old "no durable changes" wording, and a pending-review suffix is
    # retained. This is a display-only decision; the receipt is unchanged.
    result = run_bun(r"""
      import { buildLearningReceipt, learningSummarySubject } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const screen = { memory: true, harness: false, agents: false, reasons: [] };
      const noop = buildLearningReceipt('automatic', screen, [{ phase: 'selector', attempt: 0, outcome: 'applied', durationMs: 5, operations: 0 }]);
      const pending = buildLearningReceipt('automatic', screen, [{ phase: 'memory', attempt: 0, outcome: 'noop', durationMs: 5, operations: 0, pendingOperations: 2 }]);
      console.log(JSON.stringify({ noop: learningSummarySubject(noop), pending: learningSummarySubject(pending) }));
    """)
    assert result["noop"] == "no changes written", result
    assert "durable" not in result["noop"], result
    assert "no changes written" in result["pending"] and "2 pending review" in result["pending"], result


def test_new_memory_cap_hold_subject_reports_a_hold_not_a_zero_write() -> None:
    # A cap-held receipt has a proposed attempt with operations=0 and no
    # pending count. It must not fall through to the quiet zero-write subject:
    # the parent saved a grounded plan for review, not a completed check.
    result = run_bun(r"""
      import { buildLearningReceipt, learningSummarySubject, NEW_MEMORY_CAP_HOLD } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const screen = { memory: true, harness: false, agents: false, reasons: [], routing: [NEW_MEMORY_CAP_HOLD] };
      const held = buildLearningReceipt('automatic', screen, [
        { phase: 'selector', attempt: 0, outcome: 'applied', durationMs: 5, operations: 0 },
        { phase: 'memory', attempt: 0, outcome: 'proposed', durationMs: 5, operations: 0 },
      ]);
      const plain = buildLearningReceipt('automatic', { memory: true, harness: false, agents: false, reasons: [] }, [
        { phase: 'memory', attempt: 0, outcome: 'proposed', durationMs: 5, operations: 0 },
      ]);
      console.log(JSON.stringify({ held: learningSummarySubject(held), plain: learningSummarySubject(plain) }));
    """)
    assert result["held"] == "new Memory plan held by per-run limit; proposal saved for review", result
    assert "held" in result["held"] and "review" in result["held"], result
    assert result["plain"] == "no changes written", result


# --- Merged from test_empty_learning.py ---
"""Merged tests from: test_empty_full_learning.py, test_empty_memory_discovery.py, test_empty_memory_routing.py."""


from support import run_bun_script, PKG_DIR, run_bun
import json
from support import run_bun
import tempfile
from support import isolated_run_bun

# --- Merged from test_empty_full_learning.py ---

def test_header_only_full_learning_launches_no_workers() -> None:
    result = run_bun_script(PKG_DIR / "tests" / "learning-policy-harness.ts", "empty-full")
    assert result["selectors"] == 0
    assert result["planners"] == []
    assert result["registryReceipt"]["attempts"] == []
    assert "no-learning-inputs" in result["registryReceipt"]["screen"]["reasons"]
    assert result["history"] == []
    assert result["lock"] is False


def test_empty_full_receipt_is_distinct_from_reviewed_noop() -> None:
    result = run_bun('''
      import {buildLearningReceipt, learningSummarySubject} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const screen = {memory:false,harness:false,agents:false,reasons:['manual-full','no-learning-inputs']};
      console.log(JSON.stringify(learningSummarySubject(buildLearningReceipt('full',screen,[]))));
    ''')
    assert result == "no learning input"


def test_harness_noop_protocol_is_complete_and_keeps_knowledge_in_memory() -> None:
    prompt = (PKG_DIR / "prompts" / "harness-consolidator.md").read_text()
    assert '"operations": [],' in prompt
    assert '"evidence": []' in prompt
    assert "Empty operations are required" in prompt
    assert "response sign-offs" in prompt


def test_new_user_fact_grounding_is_distinct_from_existing_repository_audit() -> None:
    prompt = (PKG_DIR / "prompts" / "memory-consolidator.md").read_text()
    assert "Repository verification above audits existing selected Memory" in prompt
    assert "Shareability and repository verification are separate" in prompt


def test_harness_noop_omits_optional_report_and_repair_targets_report_errors() -> None:
    prompt = (PKG_DIR / "prompts" / "harness-consolidator.md").read_text()
    source = (PKG_DIR / "extensions" / "harness-consolidation.ts").read_text()
    assert "For a no-op, omit report entirely" in prompt
    assert "If validation errors cite report" in source

# --- Merged from test_empty_memory_discovery.py ---

def test_empty_memory_discovery_is_explicit_with_or_without_an_empty_index(tmp_path):
    result = run_bun(f'''
      import fs from 'node:fs/promises';
      import register from './packages/continual-learning/extensions/inject-memory.ts';
      import {{resolveMemoryPaths}} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd={json.dumps(str(tmp_path / 'project'))}; await fs.mkdir(cwd);
      const paths=resolveMemoryPaths(cwd); await fs.mkdir(paths.harnessDir,{{recursive:true}});
      await fs.writeFile(path.join(paths.agentDir,'continual-learning.json'),JSON.stringify({{autoSettledLearning:false,autoContinualLearning:false}}));
      const hooks=new Map(); register({{on:(n,f)=>hooks.set(n,f),registerCommand:()=>{{}},sendMessage:()=>{{}},appendEntry:()=>{{}},getCommands:()=>[],exec:async()=>({{stdout:'',stderr:'',code:0}})}});
      const ctx={{cwd,ui:{{notify:()=>{{}}}}}};
      const options={{promptGuidelines:[],sections:{{project_memory_discovery:'STALE_DISCOVERY',project_memory_auto_learning:'STALE_AUTO',other:'KEEP'}}}};
      const missing=await hooks.get('before_agent_start')({{systemPrompt:'TRUSTED',systemPromptOptions:options}},ctx);
      await fs.writeFile(paths.harnessDir+'/MEMORY.md','# Memory Index\\n\\n');
      const emptyIndex=await hooks.get('before_agent_start')({{systemPrompt:'TRUSTED',systemPromptOptions:options}},ctx);
      console.log(JSON.stringify({{missing:{{...missing,guidance:Object.values(options.sections),sections:options.sections}},emptyIndex:{{...emptyIndex,guidance:Object.values(options.sections),sections:options.sections}}}}));
    ''',env={'PI_CODING_AGENT_DIR':str(tmp_path / 'agent')})
    for state in ('missing','emptyIndex'):
        assert result[state] is not None, 'Empty Memory discovery was omitted'
        assert 'message' not in result[state], 'Empty discovery must not append a placeholder reference'
        assert result[state]['sections']['other'] == 'KEEP'
        assert set(result[state]['sections']) == {'other', 'project_memory_protocol', 'project_memory_auto_learning'}
        assert 'If no established entries are available' in ' '.join(result[state]['guidance'])
        assert 'use the read tool to inspect relevant indexed Memory entries' in result[state]['sections']['project_memory_protocol']
        assert 'do not search guessed or alternative Memory locations' in ' '.join(result[state]['guidance'])
        protocol = result[state]['sections']['project_memory_protocol']
        assert "Respect the task's read and write scope" in protocol
        # The agent trigger is always on: the protocol advertises learn and
        # keeps the Pi-input note, never a retired slash command.
        assert 'uses the learn tool' in protocol
        assert 'slash commands are Pi input for the user' in protocol
        assert 'never a suggestion to type /memory' not in protocol
        assert 'The parent performs automatic maintenance when enabled' in protocol
        assert 'Memory retrieval alone does not authorize configuration discovery or launching another agent' in protocol
        assert 'those need separate task authorization' in protocol
        assert 'Maintain knowledge through /memory or /consolidate.' not in protocol
        assert '/memory or /consolidate' not in protocol
    assert result['missing'] == result['emptyIndex']


def test_automatic_learning_owns_durable_writes_and_remember_does_not_expand_task_scope(tmp_path):
    result = run_bun(f'''
      import fs from 'node:fs/promises';
      import register from './packages/continual-learning/extensions/inject-memory.ts';
      import {{resolveMemoryPaths}} from './packages/continual-learning/extensions/memory-paths.ts';
      const cwd={json.dumps(str(tmp_path / 'project'))};await fs.mkdir(cwd);
      const paths=resolveMemoryPaths(cwd);await fs.mkdir(paths.harnessDir,{{recursive:true}});
      await fs.writeFile(path.join(paths.agentDir,'continual-learning.json'),JSON.stringify({{autoSettledLearning:true,autoContinualLearning:false}}));
      const hooks=new Map();register({{on:(n,f)=>hooks.set(n,f),registerCommand(){{}},sendMessage(){{}},appendEntry(){{}},getCommands:()=>[]}});
      const options={{sections:{{}}}};await hooks.get('before_agent_start')({{systemPromptOptions:options}},{{cwd,ui:{{notify(){{}}}}}});
      console.log(JSON.stringify(options.sections));
    ''',env={'PI_CODING_AGENT_DIR':str(tmp_path / 'agent')})
    guidance = ' '.join(result['project_memory_auto_learning'].split())
    assert 'The parent validates and writes them' in guidance
    assert '"remember" does not authorize writing Memory, Harness, AGENTS.md' in guidance
    assert 'PI.md or agent configuration, or probing enforcement' in guidance
    assert 'explicit authoring requests take precedence' in guidance
    protocol = result['project_memory_protocol']
    assert "Respect the task's read and write scope" in protocol
    # The agent trigger is always on, so the protocol advertises learn.
    assert 'uses the learn tool' in protocol
    assert 'never a suggestion to type /memory' not in protocol

# --- Merged from test_empty_memory_routing.py ---

def test_empty_memory_routes_explicit_evidence_without_model_and_preserves_dossier() -> None:
    with tempfile.TemporaryDirectory(prefix='empty-memory-routing-') as temporary:
        result = isolated_run_bun(r'''
          import {mock} from 'bun:test';
          import fs from 'node:fs';
          import path from 'node:path';
          import {execFileSync} from 'node:child_process';
          const cwd=path.join(process.env.TEST_ROOT,'project');fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);
          let calls=0;
          const kit=await import('./packages/kit/src/index.ts');
          mock.module('./packages/kit/src/index.ts',()=>({...kit,runPiWorker:async()=>{
            calls++;return {text:'INVALID_SELECTOR',exitCode:0,stderr:'',cancelled:false};
          }}));
          const {selectIncrementalLearning}=await import('./packages/continual-learning/extensions/incremental-learning.ts');
          const slice={kind:'learning-task-slice',version:1,entries:[{message:{role:'user',content:
            'Remember for future tasks: the verified command is pnpm test. Never run git push.'}}]};
          const run=(name,taskSlice=slice,extra={})=>selectIncrementalLearning({cwd,taskSlice,contextDigest:'frozen-digest',
            outputDir:path.join(process.env.TEST_ROOT,name),allowEmptyIndexRouting:true,...extra});
          const cold=await run('cold');
          const dossier=cold.dossierPath?JSON.parse(fs.readFileSync(cold.dossierPath,'utf8')):null;
          const coldCalls=calls;
          const requested=await run('requested',{...slice,entries:[{message:{role:'user',content:'A means B.'}}]},{memoryOnly:true});
          const requestCalls=calls;
          const ambiguous=await run('ambiguous',{...slice,entries:[{message:{role:'user',content:'Inspect this task.'}}]});
          fs.mkdirSync(path.join(cwd,'.memory'));
          fs.writeFileSync(path.join(cwd,'.memory','known.md'),'---\nname: known\ndescription: Known project fact\ntype: project\n---\nBody\n');
          const existing=await run('existing');
          const rejected=JSON.parse(fs.readFileSync(path.join(process.env.TEST_ROOT,'ambiguous','selector-rejected.json'),'utf8'));
          const rejectedMode=fs.statSync(path.join(process.env.TEST_ROOT,'ambiguous','selector-rejected.json')).mode&0o777;
          const cancelled=await run('cancelled',slice,{signal:AbortSignal.abort()});
          console.log(JSON.stringify({cold:cold.outcome,coldCalls,dossier,coldUsage:cold.usage??null,
            diagnostic:cold.diagnostic,rejected,rejectedMode,requestCalls,requested:requested.selection,
            ambiguous:ambiguous.outcome,existing:existing.outcome,calls,cancelled:cancelled.outcome}));
        ''', {"TEST_ROOT": temporary})
    assert result['cold'] == 'selected'
    assert result['coldCalls'] == 0 and result['requestCalls'] == 0
    assert result['coldUsage'] is None
    assert result['dossier']['contextDigest'] == 'frozen-digest'
    assert result['dossier']['selectedMemories'] == []
    selection = result['dossier']['selection']
    assert selection['selected'] == [] and selection['memory'] and selection['harness'] and not selection['agents']
    assert result['requested']['memory'] and not result['requested']['harness'] and not result['requested']['agents']
    assert result['ambiguous'] == result['existing'] == 'failed'
    assert result['cancelled'] == 'cancelled' and result['calls'] == 2
    assert result['diagnostic'] == 'empty Memory index; parent-routed explicit evidence'

    assert result['rejected']['output'] == 'INVALID_SELECTOR'
    assert result['rejected']['contextDigest'] == 'frozen-digest'
    assert result['rejectedMode'] == 0o600


# --- Merged from test_failed_planner_output.py ---
from support import isolated_run_bun


def test_failed_or_aborted_assistant_json_is_not_a_plan() -> None:
    result = isolated_run_bun(r'''
      import {extractChildPlan} from './packages/continual-learning/extensions/consolidation-run.ts';
      const kinds=['memory-consolidation-plan','incremental-memory-plan','harness-consolidation-plan','agents-md-consolidation-plan'];
      const rows=kinds.flatMap(kind=>['error','aborted'].map(stopReason=>extractChildPlan(JSON.stringify({type:'message_end',message:{role:'assistant',stopReason,errorMessage:'PRIVATE-DO-NOT-RELAY',content:JSON.stringify({kind})}}))));
      console.log(JSON.stringify(rows));
    ''')
    assert all(row['ok'] is False for row in result)
    assert [row['failure'] for row in result] == ['model-error', 'cancelled'] * 4
    assert all('PRIVATE' not in row['error'] for row in result)


def test_terminal_failure_invalidates_previously_emitted_plan() -> None:
    result = isolated_run_bun(r'''
      import {extractChildPlan} from './packages/continual-learning/extensions/consolidation-run.ts';
      const plan={type:'consolidation_plan',plan:{kind:'harness-consolidation-plan'}};
      const rows=['error','aborted'].map(stopReason=>extractChildPlan([plan,{type:'message_end',message:{role:'assistant',stopReason,content:[]}}].map(JSON.stringify).join('\n')));
      const retry=extractChildPlan([plan,{type:'auto_retry_end',success:false,finalError:'PRIVATE'}].map(JSON.stringify).join('\n'));
      console.log(JSON.stringify([...rows,retry]));
    ''')
    assert all(row['ok'] is False for row in result)
    assert [row['failure'] for row in result] == ['model-error', 'cancelled', 'model-error']


def test_recovery_accepts_only_successful_reply_and_keeps_legacy_protocol() -> None:
    result = isolated_run_bun(r'''
      import {extractChildPlan} from './packages/continual-learning/extensions/consolidation-run.ts';
      const reply=(stopReason,id)=>({type:'message_end',message:{role:'assistant',stopReason,content:JSON.stringify({kind:'incremental-memory-plan',id})}});
      const recovered=extractChildPlan([reply('error','partial'),reply('stop','recovered')].map(JSON.stringify).join('\n'));
      const legacy=extractChildPlan(JSON.stringify({type:'consolidation_plan',plan:{kind:'harness-consolidation-plan'}}));
      console.log(JSON.stringify({recovered,legacy}));
    ''')
    assert result['recovered']['ok'] is True
    assert result['recovered']['plan']['id'] == 'recovered'
    assert result['legacy']['ok'] is True


def test_plan_emitted_during_failure_is_not_restored_by_empty_success() -> None:
    result = isolated_run_bun(r'''
      import {extractChildPlan} from './packages/continual-learning/extensions/consolidation-run.ts';
      const events=[
        {type:'message_end',message:{role:'assistant',stopReason:'error',content:[]}},
        {type:'consolidation_plan',plan:{kind:'harness-consolidation-plan',id:'failed-state'}},
        {type:'message_end',message:{role:'assistant',stopReason:'stop',content:[]}},
      ];console.log(JSON.stringify(extractChildPlan(events.map(JSON.stringify).join('\n'))));
    ''')
    assert result['ok'] is False


def test_failed_incremental_fallback_never_clears_model_error_evidence() -> None:
    result = isolated_run_bun(r'''
      import {createConsolidationEvidence,recordConsolidationEvent} from './packages/continual-learning/extensions/inject-memory.ts';
      const rows=['error','aborted'].map(stopReason=>{
        const e=createConsolidationEvidence();
        recordConsolidationEvent(e,{type:'message_end',message:{role:'assistant',stopReason,errorMessage:'Provider unavailable',content:JSON.stringify({kind:'incremental-memory-plan'})}});
        return {plans:e.planCount,hasPlan:e.finalPlan!==undefined,failed:!!e.plannerModelError};
      });console.log(JSON.stringify(rows));
    ''')
    assert result == [{'plans': 0, 'hasPlan': False, 'failed': True}] * 2


def test_failed_harness_json_stops_before_repair_judgment_and_application() -> None:
    from pathlib import Path
    from support import run_bun_script

    fixture = Path(__file__).with_name('harness-repair-harness.ts')
    for scenario, outcome in [('initial-failed-json', 'failed'), ('initial-aborted-json', 'cancelled'), ('initial-aborted-retry-json', 'cancelled')]:
        result = run_bun_script(fixture, scenario)
        assert result['ok'] is False, result
        assert result['spawned'] == 1, result
        assert result['repairRequested'] is False, result
        assert result['semanticCalls'] == 0, result
        assert result['targetExists'] is False, result
        assert result['operations'] == 0, result
        assert result['attempts'][0]['outcome'] == outcome, result
        assert 'PRIVATE' not in result['detail'], result


def test_retry_bookkeeping_never_clears_aborted_terminal_state() -> None:
    result = isolated_run_bun(r'''
      import {extractChildPlan} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {createConsolidationEvidence,recordConsolidationEvent} from './packages/continual-learning/extensions/inject-memory.ts';
      const reply=stopReason=>({type:'message_end',message:{role:'assistant',stopReason,content:[]}});
      const rows=[true,false].map(success=>{
        const events=[reply('error'),reply('aborted'),{type:'auto_retry_end',success,finalError:'unavailable'}];
        const evidence=createConsolidationEvidence();events.forEach(event=>recordConsolidationEvent(evidence,event));
        return {parsed:extractChildPlan(events.map(JSON.stringify).join('\n')),failed:!!evidence.plannerModelError};
      });console.log(JSON.stringify(rows));
    ''')
    assert all(row['parsed'].get('failure') == 'cancelled' and row['failed'] for row in result)


def test_failed_memory_usage_is_unknown_including_after_retry_recovery() -> None:
    result = isolated_run_bun(r'''
      import {createConsolidationEvidence,recordConsolidationEvent} from './packages/continual-learning/extensions/inject-memory.ts';
      const e=createConsolidationEvidence();
      recordConsolidationEvent(e,{type:'message_end',message:{role:'assistant',stopReason:'error',content:[],usage:{input:0,output:0,totalTokens:0,cost:{total:0}}}});
      const failedKnown=e.attemptUsage!==undefined;
      recordConsolidationEvent(e,{type:'message_end',message:{role:'assistant',stopReason:'stop',content:[],usage:{input:10,output:1,totalTokens:11,cost:{total:.01}}}});
      console.log(JSON.stringify({failedKnown,recoveredTotalKnown:e.attemptUsage!==undefined}));
    ''')
    assert result == {'failedKnown': False, 'recoveredTotalKnown': False}


def test_memory_repair_rejects_a_real_childs_failed_json_before_retention() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'failed-memory-repair-')),pkg=path.join(root,'package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({name:'@earendil-works/pi-coding-agent'}));
      const cli=path.join(pkg,'cli.mjs'),prior=process.argv[1];process.argv[1]=cli;
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'run-failed-repair',scopeKey:'scope',scopeDigest:'digest',artifactHash:'artifact',snapshotDigest:'artifact'};
      const plan={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[]};
      const rows=[];
      for(const stopReason of ['stop','error','aborted']){
        const event={type:'message_end',message:{role:'assistant',stopReason,errorMessage:'PRIVATE',content:[{type:'text',text:JSON.stringify(plan)}]}};
        fs.writeFileSync(cli,'console.log('+JSON.stringify(JSON.stringify(event))+');');
        const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:plan,errors:['bounded error'],selectedNames:[]});
        rows.push({outcome:result.outcome,hasPlan:result.plan!==undefined,knownUsage:result.usage!==undefined});
      }
      process.argv[1]=prior;fs.rmSync(root,{recursive:true,force:true});console.log(JSON.stringify(rows));
    ''')
    assert [row['outcome'] for row in result] == ['repaired', 'failed', 'cancelled']
    assert [row['hasPlan'] for row in result] == [True, False, False]
    assert all(row['knownUsage'] is False for row in result)


def test_receipt_never_formats_unknown_failed_usage_as_zero_or_free() -> None:
    result = isolated_run_bun(r'''
      import {buildLearningReceipt,learningSummaryDetails,formatLearningSummary,learningSummarySubject,isLearningPipelineReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const screen={memory:true,harness:false,agents:false,reasons:[]};
      const failed={phase:'memory',attempt:0,outcome:'failed',durationMs:1,operations:0};
      const known={phase:'harness',attempt:0,outcome:'applied',durationMs:1,operations:1,usage:{input:10,output:1,cacheRead:0,cacheWrite:0,totalTokens:11,cost:.01}};
      const rows=[[failed],[known,failed],[{...failed,outcome:'cancelled'}]].map(attempts=>{
        const receipt=buildLearningReceipt('manual',screen,attempts);
        return {available:receipt.costAvailable,usageAvailable:receipt.usageAvailable,summary:formatLearningSummary(receipt),details:learningSummaryDetails(receipt),subject:learningSummarySubject(receipt)};
      });
      const skipped=buildLearningReceipt('manual',screen,[{...failed,outcome:'skipped'}]);
      const legacy=buildLearningReceipt('manual',screen,[failed]);delete legacy.usageAvailable;
      const invalid={...legacy,usageAvailable:'yes'};
      console.log(JSON.stringify({rows,skippedAvailable:skipped.costAvailable,legacyValid:isLearningPipelineReceipt(legacy),legacySummary:formatLearningSummary(legacy),invalidValid:isLearningPipelineReceipt(invalid)}));
    ''')
    assert all(row['available'] is False and row['usageAvailable'] is False for row in result['rows'])
    assert all('cost unavailable' in row['summary'] and '$0.0000' not in row['summary'] for row in result['rows'])
    assert 'usage unavailable' in result['rows'][0]['summary']
    assert 'known subtotal' in result['rows'][1]['summary']
    assert result['rows'][2]['subject'] == 'finished with issues: memory cancelled'
    assert result['skippedAvailable'] is True
    assert result['legacyValid'] is True and 'cost unavailable' in result['legacySummary']
    assert result['invalidValid'] is False


def test_complete_plan_cannot_hide_truncated_or_unmatched_second_object() -> None:
    from support import isolated_run_bun
    result=isolated_run_bun(r'''
      import {extractChildPlan} from './packages/continual-learning/extensions/consolidation-run.ts';
      const plan=JSON.stringify({kind:'incremental-memory-plan',version:1,operations:[],newMemories:[]});
      const tails=['\n{"kind":"incremental-memory-plan","operations":[','\n}','\n{"kind":"harness-consolidation-plan"','\n{"kind":"incremental-memory-plan","operations":[],}','\n{"kind":"incremental-memory-plan" "operations":[]}','\n{"kind":"harness-consolidation-plan","operations":[]}'];
      console.log(JSON.stringify(tails.map(tail=>extractChildPlan(JSON.stringify({type:'message_end',message:{role:'assistant',stopReason:'stop',content:[{type:'text',text:plan+tail}]}})).ok)));
    ''')
    assert result==[False]*6


def test_failed_planner_keeps_known_cost_without_claiming_complete_usage() -> None:
    value = isolated_run_bun(r'''
      import {createConsolidationEvidence,recordConsolidationEvent} from './packages/continual-learning/extensions/inject-memory.ts';
      const evidence=createConsolidationEvidence();
      recordConsolidationEvent(evidence,{type:'message_end',message:{role:'assistant',stopReason:'toolUse',content:[],usage:{input:10,output:2,cacheRead:0,cacheWrite:0,totalTokens:12,cost:{total:.03}}}});
      recordConsolidationEvent(evidence,{type:'message_end',message:{role:'assistant',stopReason:'error',content:[],usage:{input:0,output:0}}});
      console.log(JSON.stringify(evidence));
    ''')
    assert 'attemptUsage' not in value
    assert value['usageLedger']['knownUsage']['cost'] == .03
    assert value['usageLedger']['knownUsage']['totalTokens'] == 12
    assert not value['usageLedger']['complete']


def test_successful_reply_with_missing_usage_does_not_claim_complete_cost() -> None:
    value = isolated_run_bun(r'''
      import {createConsolidationEvidence,recordConsolidationEvent} from './packages/continual-learning/extensions/inject-memory.ts';
      const evidence=createConsolidationEvidence();
      recordConsolidationEvent(evidence,{type:'message_end',message:{role:'assistant',stopReason:'stop',content:[],usage:{input:7,output:2,cost:{total:.04}}}});
      console.log(JSON.stringify(evidence));
    ''')
    assert 'attemptUsage' not in value
    assert value['usageLedger']['knownUsage']['cost'] == .04
    assert not value['usageLedger']['complete']


def test_retry_failure_without_text_keeps_prefix_but_cannot_claim_complete_usage() -> None:
    value = isolated_run_bun(r'''
      import {createConsolidationEvidence,recordConsolidationEvent} from './packages/continual-learning/extensions/inject-memory.ts';
      const evidence=createConsolidationEvidence();
      recordConsolidationEvent(evidence,{type:'message_end',message:{role:'assistant',stopReason:'toolUse',content:[],usage:{input:10,output:2,totalTokens:12,cost:{total:.03}}}});
      recordConsolidationEvent(evidence,{type:'auto_retry_end',success:false});
      console.log(JSON.stringify(evidence));
    ''')
    assert 'attemptUsage' not in value
    assert value['usageLedger']['knownUsage']['cost'] == .03
    assert not value['usageLedger']['complete']


# --- Merged from test_failure_distillation_preservation.py ---
from support import isolated_run_bun


def test_actual_repaired_failure_body_and_sources_survive_optional_distillation() -> None:
    # Given a historical real correction scopes failure to the last observed source state,
    # When optional distillation runs with the original description's checklist,
    # Then the corrected body and citations survive rather than reverting to
    # the original causal description. Replay the exact historical candidates,
    # not current admission: their self-citations are now rejected below.
    # This proves preservation only, never semantics or mutation authority.
    result = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {distillReviewedNewMemory} from './packages/continual-learning/extensions/inject-memory.ts';
      const f=await Bun.file('./packages/continual-learning/tests/fixtures/real-failure-distillation-overwrite.json').json();
      const candidates=[...f.originalPlan.operations,...f.originalPlan.newMemories];
      const digest=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
      const name='onidle_absent_from_index_d_ts.md';
      const repaired=f.repairResponse.newMemories.find(x=>x.name===name);
      const original=candidates.find(x=>x.name===name);
      const run=item=>distillReviewedNewMemory({operations:[],newMemories:[item]},candidates,f.review,f.snapshot,f.existingMemories,11);
      const changed=run(repaired), unchanged=run(original);
      const citationOnly=run({...original,evidence:repaired.evidence});
      console.log(JSON.stringify({boundCandidates:digest(candidates)===f.review.candidatesDigest,
        boundEvidence:digest(f.snapshot)===f.review.evidenceDigest,boundExisting:digest(f.existingMemories)===f.review.existingDigest,
        original,repaired,changed,unchanged,citationOnly,actual:f.actualDistilledPlan.newMemories.find(x=>x.name===name)}));
    ''')
    assert result['boundCandidates'] and result['boundEvidence'] and result['boundExisting']
    assert 'last observed state' in result['repaired']['content']
    assert 'last observed state' not in result['actual']['content']
    assert result['changed']['names'] == []
    assert result['changed']['plan']['newMemories'][0] == result['repaired']
    assert result['citationOnly']['names'] == []
    assert result['citationOnly']['plan']['newMemories'][0]['evidence'] == result['repaired']['evidence']
    assert result['unchanged']['names'] == []
    assert result['unchanged']['plan']['newMemories'][0] == result['original']


def test_historical_full_failure_plan_is_rejected_for_memory_self_evidence() -> None:
    # Given the unchanged original v14 plan and repair now fail provenance,
    # When current parent admission runs, Then no old review or positive fake
    # judge can authorize them. Do not change citations or drop failing cases
    # to revive the former positive coverage claim.
    result = isolated_run_bun(r'''
      import {createHash} from 'node:crypto';
      import {normalizeNewMemoryProposals} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {resolveMemoryPlanCitations} from './packages/continual-learning/extensions/memory-citation-locations.ts';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const file='./packages/continual-learning/tests/fixtures/real-failure-distillation-overwrite.json';
      const bytes=await Bun.file(file).text(),f=JSON.parse(bytes);
      let originalError,repairError;
      try{normalizeNewMemoryProposals(f.originalPlan,f.snapshot)}catch(e){originalError=e.message}
      try{resolveMemoryPlanCitations(f.repairResponse,f.snapshot)}catch(e){repairError=e.message}
      let calls=0;const judge=createJevJudge({enabled:true,apiKey:'fixture',fetch:async()=>{calls++;throw Error('Must reject before transport')}});
      const verdict=await judge.validate('memory',f.snapshot,[...f.originalPlan.operations,...f.originalPlan.newMemories],f.existingMemories);
      const digest=text=>createHash('sha256').update(text).digest('hex');
      console.log(JSON.stringify({originalError,repairError,calls,verdict:verdict.decision,reason:verdict.telemetry.reason,unchanged:digest(bytes)===digest(await Bun.file(file).text()),entries:f.snapshot.entries.length,candidates:f.originalPlan.operations.length+f.originalPlan.newMemories.length}));
    ''')
    assert 'Memory readback is context, not independent evidence' in result['originalError']
    assert 'memory-reference-not-independent' in result['repairError']
    assert result['calls'] == 0 and result['verdict'] != 'allow'
    assert result['reason'] == 'invalid-response' and result['unchanged']
    assert result['entries'] == 51 and result['candidates'] > 0


# --- Merged from test_json_string_whitespace.py ---
"""Only lossless string-whitespace serialization may recover a repair response."""
from support import isolated_run_bun


def test_whitespace_normalization_preserves_literal_values_and_refuses_other_damage():
    result = isolated_run_bun(r'''
      import {normalizeJsonStringWhitespace} from './packages/continual-learning/extensions/json-string-whitespace.ts';
      const normalize=text=>normalizeJsonStringWhitespace(text,4096);
      const expected='one\n\ttwo\rthree\\n escaped "quoted" 文';
      const raw=JSON.stringify({kind:'incremental-memory-amendment',body:expected}).replace('\\n','\n').replace('\\t','\t').replace('\\r','\r');
      const corrected=normalize(raw),value=corrected?JSON.parse(corrected.text):null;
      const invalid=[JSON.stringify({body:'valid\nwhitespace'}),'{"body":"unterminated\n',
        '{"body":"a\n"}{"body":"b"}','[{"body":"a\n"}]',
        'prose {"body":"a\n"}','{"body":"a\n",}',
        '{"body":"a\n\\q"}','{"body":"a\\\nb"}',
        '{"body":"a\n\u0000b"}','{"body":"a\n\u0001b"}',
        '{"body":"a\n"} trailing','{"body":"a\n","missing":}'];
      const big='{"body":"'+'\n'.repeat(40)+'"}';
      console.log(JSON.stringify({corrected,value,invalid:invalid.map(normalize),rawBound:normalizeJsonStringWhitespace(raw,10),expandedBound:normalizeJsonStringWhitespace(big,60)}));
    ''')
    assert result['value']['body'] == 'one\n\ttwo\rthree\\n escaped "quoted" 文'
    assert result['corrected']['counts'] == {'newline': 1, 'carriageReturn': 1, 'tab': 1}
    assert all(item is None for item in result['invalid'])
    assert result.get('rawBound') is None and result.get('expandedBound') is None


# --- Merged from test_learning_activity_widget.py ---
"""One live activity row above the editor while a learning run is active."""

from pathlib import Path

from support import run_bun_script


_m5_HARNESS = Path(__file__).with_name("learning-policy-harness.ts")


def test_tui_run_mounts_and_clears_one_above_editor_activity_row() -> None:
    # Given a learning run started in the TUI, When the pipeline runs and ends,
    # Then one native live activity widget is mounted above the editor and
    # cleared exactly once at the end, so no stale row outlives the run.
    result = run_bun_script(_m5_HARNESS, "manual-full", env={"CL_TUI_MODE": "1"})
    events = result["widgetEvents"]
    assert events, result
    mounted = [row for row in events if row["mounted"]]
    cleared = [row for row in events if not row["mounted"]]
    assert len(mounted) == 1, events
    assert len(cleared) >= 1, events
    assert mounted[0]["key"] == "continual-learning-activity", mounted
    assert mounted[0]["placement"] == "aboveEditor", mounted
    assert events.index(mounted[0]) < events.index(cleared[0]), events


def test_headless_run_never_mounts_an_activity_row() -> None:
    # Given a --print/RPC run, When the pipeline runs, Then no widget is
    # mounted; the live row is strictly a TUI affordance.
    result = run_bun_script(_m5_HARNESS, "manual-full")
    assert result["widgetEvents"] == [], result["widgetEvents"]


def test_activity_row_is_cleared_on_a_failed_run() -> None:
    # Given a run that fails, When the pipeline settles, Then the activity row
    # is still cleared; a failure never leaves a spinner above the editor.
    result = run_bun_script(_m5_HARNESS, "remember-invalid", env={"CL_TUI_MODE": "1"})
    events = result["widgetEvents"]
    assert any(row["mounted"] for row in events), events
    assert any(not row["mounted"] for row in events), events


def test_activity_identity_names_the_learner_agent_not_an_action() -> None:
    # Given a TUI learning run, When the above-editor widget renders its row,
    # Then identity names the agent ("learner"), not an action-progress word
    # like "Learning...". The bounded run topic belongs in the activity field,
    # so the identity and progress stay separate in the shared widget language.
    from support import run_bun

    value = run_bun(r"""
      import { stripVTControlCharacters } from 'node:util';
      import { createLiveActivityWidget } from './packages/kit/src/index.ts';
      import { LEARNING_ACTIVITY_IDENTITY } from './packages/continual-learning/extensions/inject-memory.ts';
      let component;
      const ui = { setWidget: (_key, factory) => { component = factory({ requestRender() {} }, { fg: (_c, t) => t, bold: t => t, bg: (_c, t) => t }); } };
      const widget = createLiveActivityWidget({ key: 'continual-learning-activity', fit: (text) => text, activityFormat: 'plain' });
      widget.update({ mode: 'tui', ui }, [{ id: 'learning', identity: LEARNING_ACTIVITY_IDENTITY, status: 'working', activity: 'current task' }]);
      const row = stripVTControlCharacters(component.render(80)[0] ?? '');
      console.log(JSON.stringify({ identity: LEARNING_ACTIVITY_IDENTITY, row }));
    """)
    assert value["identity"] == "learner", value
    assert "learner" in value["row"], value
    assert "· current task" in value["row"], value
    assert "Learning..." not in value["row"], value
    assert "· learning" not in value["row"], value


def test_learner_identity_survives_a_24_column_resize() -> None:
    # Given a live resize of the same widget down to a narrow terminal, When
    # the row renders, Then the complete agent name stays visible and only the
    # bounded activity is ellipsized. The agent name is not progress text.
    from support import run_bun

    value = run_bun(r"""
      import { stripVTControlCharacters } from 'node:util';
      import { truncateToWidth, visibleWidth } from '@earendil-works/pi-tui';
      import { createLiveActivityWidget } from './packages/kit/src/index.ts';
      import { LEARNING_ACTIVITY_IDENTITY } from './packages/continual-learning/extensions/inject-memory.ts';
      let component;
      const ui = { setWidget: (_key, factory) => { component = factory({ requestRender() {} }, { fg: (_c, t) => t, bold: t => t, bg: (_c, t) => t }); } };
      const widget = createLiveActivityWidget({ key: 'continual-learning-activity', fit: truncateToWidth, activityFormat: 'plain' });
      widget.update({ mode: 'tui', ui }, [{ id: 'learning', identity: LEARNING_ACTIVITY_IDENTITY, status: 'working', activity: 'pnpm build and onIdle completion reaction order' }]);
      const rows = [24, 40, 48, 120].map(width => {
        const raw = component.render(width)[0] ?? '';
        return { width, row: stripVTControlCharacters(raw), bounded: visibleWidth(raw) <= width };
      });
      console.log(JSON.stringify({ identity: LEARNING_ACTIVITY_IDENTITY, rows }));
    """)
    assert value["identity"] == "learner", value
    rows = {row["width"]: row for row in value["rows"]}
    for width, entry in rows.items():
        row = entry["row"]
        assert "learner" in row, (width, row)
        assert "lea..." not in row, (width, row)
        assert entry["bounded"], (width, row)
    assert " · " in rows[24]["row"] and rows[24]["row"].rstrip().endswith("..."), rows[24]
    assert "pnpm build and onIdle completion reaction order" in rows[120]["row"], rows[120]


# --- Merged from test_learning_backlog.py ---
"""The learning backlog: settled work that was never learned from.

Learning is opportunistic today. A task is learned when it settles, if
auto-learning is on and the zero-token screen finds durable evidence. Everything
else is dropped, and a heuristic screen making an irreversible discard is the gap
this closes.

Two properties matter and are asserted rather than assumed. The backlog stores
**references, not content** — a session file and entry indices, never the text —
so it is an index over conversations rather than a second copy of them. And an
entry whose session file has been removed is **reported as unlearnable**, never
silently dropped or reconstructed, because a backlog that looks drained when it
was not is worse than one that never existed.
"""


from support import isolated_run_bun

SNIPPET = r"""
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const B = await import('./packages/continual-learning/extensions/learning-backlog.ts');
      const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'backlog-')));
      const cwd = path.join(root,'project'), agent = path.join(root,'agent');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(agent,{recursive:true});
      const session = path.join(root,'session.jsonl');
      const writeSession = (lines) => fs.writeFileSync(session, lines.join('\n')+'\n');
      writeSession([JSON.stringify({message:{role:'user',content:'a'}})]);

      // Two tasks queued while their session existed.
      B.enqueueBacklog({cwd, sessionFile:session, from:0, to:2, digest:'d1', reason:'screen-found-nothing', agentDir:agent});
      B.enqueueBacklog({cwd, sessionFile:session, from:3, to:5, digest:'d2', reason:'settled-learning-off', agentDir:agent});
      // One whose session file will not survive.
      const gone = path.join(root,'deleted.jsonl');
      fs.writeFileSync(gone, '{}\n');
      B.enqueueBacklog({cwd, sessionFile:gone, from:0, to:1, digest:'d3', reason:'settled-learning-off', agentDir:agent});
      fs.unlinkSync(gone);

      const beforeCursor = B.backlogStatus(cwd, agent);
      const raw = fs.readFileSync(B.backlogFile(cwd, agent), 'utf-8');
      B.advanceCursor(cwd, 1, agent);
      const afterCursor = B.backlogStatus(cwd, agent);
      // An entry with no session reference is refused rather than queued blind.
      const noSession = B.enqueueBacklog({cwd, sessionFile:undefined, from:0, to:1, digest:'d4', reason:'no-session-reference', agentDir:agent});
      const insideMemoryRoot = B.backlogFile(cwd, agent).includes(path.join('memory', path.sep));
      console.log(JSON.stringify({
        beforeCursor, afterCursor, noSession,
        insideMemoryRoot,
        relative: path.relative(agent, B.backlogFile(cwd, agent)),
        // The decisive property: no conversation text anywhere in the file.
        carriesContent: /"content"|"message"|"role"/.test(raw),
        entryKeys: Object.keys(JSON.parse(raw.split('\n')[0])),
        reasons: raw.split('\n').filter(Boolean).map((l) => JSON.parse(l).reason),
      }));
"""


def test_the_backlog_stores_references_and_never_content() -> None:
    value = isolated_run_bun(SNIPPET)
    # An index over conversations, not a copy of them.
    assert value["carriesContent"] is False, value
    assert value["entryKeys"] == ["version", "sessionFile", "from", "to", "digest", "reason", "queuedAt", "scopeKey"], value
    # A task with no session reference cannot be queued blind.
    assert value["noSession"] is False, value


def test_a_missing_session_file_is_reported_not_silently_dropped() -> None:
    value = isolated_run_bun(SNIPPET)
    assert value["beforeCursor"]["unlearnable"] == 1, value
    assert value["beforeCursor"]["pending"] == 2, value
    assert value["beforeCursor"]["reason"] == "ready", value


def test_the_cursor_advances_without_losing_or_re_queuing() -> None:
    value = isolated_run_bun(SNIPPET)
    assert value["afterCursor"]["consumed"] == 1, value
    # Consumed entries are not deleted: the backlog is evidence, and re-reading
    # it must still show what was there.
    assert value["afterCursor"]["unlearnable"] == 1, value


def test_the_backlog_never_lands_inside_a_memory_root() -> None:
    value = isolated_run_bun(SNIPPET)
    # A Memory root admits only regular `.md` children; a JSONL backlog beside
    # them fails privacy validation and aborts consolidation.
    assert value["insideMemoryRoot"] is False, value
    assert value["relative"].startswith("learning/"), value


def test_legacy_reason_rows_do_not_disable_replay_binding_for_other_scopes() -> None:
    # Given a global backlog file with old "auto-memory-off" rows from a 2026-11-03
    # rename, When the current scope has no malformed rows, Then replay binding
    # stays available. A genuinely malformed row in the SAME scope still fails
    # closed, so the compatibility read never weakens the fail-closed gate.
    value = isolated_run_bun(r"""
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const B = await import('./packages/continual-learning/extensions/learning-backlog.ts');
      const R = await import('./packages/continual-learning/extensions/learning-replay.ts');
      const {resolveMemoryPaths} = await import('./packages/continual-learning/extensions/memory-paths.ts');
      const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'backlog-legacy-')));
      const cwd=path.join(root,'project'),agent=path.join(root,'agent');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(agent,{recursive:true});
      const session=path.join(root,'session.jsonl');
      fs.writeFileSync(session,JSON.stringify({message:{role:'user',content:'a'}})+'\n');
      const file=B.backlogFile(cwd,agent);fs.mkdirSync(path.dirname(file),{recursive:true});
      const scope=resolveMemoryPaths(cwd,agent).scopeKey;
      const other='--other--';
      const legacy=row=>JSON.stringify({version:1,sessionFile:session,from:0,to:1,digest:row,reason:'auto-memory-off',queuedAt:new Date().toISOString(),scopeKey:other});
      fs.writeFileSync(file,[legacy('one'),legacy('two')].join('\n')+'\n');
      const clean=B.readBacklog(cwd,agent),status=B.backlogStatus(cwd,agent);
      // A current-scope pending row must still bind and be retryable.
      const input={cwd,sessionFile:session,from:2,to:3,digest:'current-task',reason:'settled-learning-off',agentDir:agent};
      const queued=B.enqueueBacklog(input),pending=B.readBacklog(cwd,agent).pendingEntries.map(({entry})=>entry);
      const bound=pending.length?R.beginBacklogAttempt(cwd,pending[0],agent):false;
      // A genuinely malformed row in the SAME scope still fails closed.
      fs.appendFileSync(file,'{ not json\n');
      const broken=B.readBacklog(cwd,agent);
      const boundAfter=bound?R.beginBacklogAttempt(cwd,pending[0],agent):false;
      console.log(JSON.stringify({cleanMalformed:clean.malformed,cleanError:clean.error??null,
        quarantined:clean.quarantined,legacyPending:clean.pending,scope,
        statusMalformed:status.malformed,queued,pendingCount:pending.length,bound,boundAfter,
        brokenMalformed:broken.malformed}));
    """)
    assert value["cleanMalformed"] == 0, value
    assert value["cleanError"] is None, value
    assert value["quarantined"] == 2, value
    assert value["legacyPending"] == 0, value
    assert value["statusMalformed"] == 0, value
    assert value["queued"] is True and value["pendingCount"] == 1, value
    assert value["bound"] is True, value
    assert value["brokenMalformed"] >= 1, value
    assert value["boundAfter"] is False, value


# --- Merged from test_learning_batches.py ---
from support import run_bun


def test_exact_pipeline_batches_preserve_legacy_and_concurrent_identity():
    result = run_bun('''
      import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
      import {withLearningBatch,recordLearningMutation,listLearningHistory} from './packages/continual-learning/extensions/learning-history.ts';
      const root=await fs.mkdtemp(path.join(os.tmpdir(),'cl-batches-'));
      process.env.PI_CODING_AGENT_DIR=path.join(root,'agent');await fs.mkdir(process.env.PI_CODING_AGENT_DIR);
      const cwd=path.join(root,'project');await fs.mkdir(path.join(cwd,'.pi'),{recursive:true});
      const target=path.join(cwd,'.pi/harness.json');
      try {
        await recordLearningMutation(cwd,'harness',[target],async()=>{await fs.writeFile(target,'legacy')});
        await withLearningBatch(async()=>{
          await recordLearningMutation(cwd,'harness',[target],async()=>{await fs.writeFile(target,'one')});
          await Promise.resolve();
          await recordLearningMutation(cwd,'harness',[target],async()=>{await fs.writeFile(target,'two')});
        });
        const records=await listLearningHistory(cwd);
        const ids=await Promise.all([1,2].map(n=>withLearningBatch(async()=>{
          const {currentLearningBatch}=await import('./packages/continual-learning/extensions/learning-history.ts');
          await Promise.resolve();return currentLearningBatch();
        })));
        console.log(JSON.stringify({legacy:records.filter(r=>!r.batchId).length,batches:records.filter(r=>r.batchId).map(r=>r.batchId),ids}));
      } finally {await fs.rm(root,{recursive:true,force:true})}
    ''')
    assert result['legacy'] == 1
    assert len(result['batches']) == 2 and len(set(result['batches'])) == 1
    assert len(set(result['ids'])) == 2


def test_batch_menu_keeps_exact_change_confirmation_and_index_label():
    result = run_bun('''
      import {openMemoryMenu} from './packages/continual-learning/extensions/memory-menu.ts';
      const menus=[];const choices=['Recent learning',undefined,'Close'];let opened=false;
      const records=[{id:'a',batchId:'batch_0123456789abcdef0123456789abcdef',phase:'memory',status:'applied',createdAt:'2026-10-10T01:00:00Z',changes:[{target:{name:'fact.md'}}]},
        {id:'b',batchId:'batch_0123456789abcdef0123456789abcdef',phase:'memory',status:'applied',createdAt:'2026-10-10T01:00:00Z',changes:[{target:{name:'MEMORY.md'},before:null}]}];
      await openMemoryMenu({cwd:'/fixture',hasUI:true,ui:{notify(){},select:async(title,options)=>{menus.push({title,options});if(title.startsWith('Learning batches')){if(opened)return 'Back';opened=true;return options[0]}return choices.shift()}}},{
        status:async()=>({autoSettledLearning:false,autoContinualLearning:false,model:'fixture/model',entries:1}),loadMemories:async()=>({entries:[]}),listHistory:async()=>records,
        manage:async()=>{throw Error('No batch mutation')},selectModel:async()=>{},toggleAutoMemory:async()=>{},isBusy:()=>false});
      console.log(JSON.stringify(menus));
    ''')
    assert 'Learning batches' in result[1]['title']
    assert 'fact.md' in result[1]['options'][0] and '2 applied' in result[1]['options'][0][:48]
    assert any('Index setup' in option for menu in result for option in menu['options'])
    assert all('Undo batch' not in option for menu in result for option in menu['options'])


# --- Merged from test_learning_evidence_projection.py ---
from support import run_bun


def test_incremental_evidence_excludes_reasoning_without_changing_human_or_tool_quotes() -> None:
    result = run_bun(r'''
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      const entries=[
        {type:'message',id:'user',message:{role:'user',content:'Remember the exact project fact: 界 means boundary.',timestamp:1}},
        {type:'message',id:'assistant',message:{role:'assistant',api:'api',provider:'provider',model:'model',
          usage:{transport:'TRANSPORT_MARKER'.repeat(1000)},timestamp:2,content:[
            {type:'thinking',thinking:'THOUGHT_MARKER'.repeat(10000),thinkingSignature:'private-signature'},
            {type:'toolCall',id:'read1',name:'read',arguments:{path:'src/index.ts'},thoughtSignature:'signature'},
            {type:'text',text:'Checking the source.',textSignature:'signature'}]}},
        {type:'message',id:'tool',message:{role:'toolResult',toolCallId:'read1',toolName:'read',isError:false,
          content:[{type:'text',text:'Exact tool evidence: the verified boundary is 4.'}],details:{exitCode:0},timestamp:3}},
      ];
      const original=JSON.stringify(entries),slice=currentTaskSlice(entries),encoded=JSON.stringify(slice);
      console.log(JSON.stringify({reasoningRetained:encoded.includes('THOUGHT_MARKER'),transportRetained:encoded.includes('TRANSPORT_MARKER'),
        unchanged:original===JSON.stringify(entries),userUnchanged:JSON.stringify(slice.entries[0])===JSON.stringify(entries[0]),
        toolUnchanged:JSON.stringify(slice.entries[2])===JSON.stringify(entries[2]),count:slice.entries.length,
        call:slice.entries[1].message.content.find(block=>block.type==='toolCall'),
        sizeRatio:Buffer.byteLength(encoded)/Buffer.byteLength(original)}));
    ''')
    assert result["reasoningRetained"] is False
    assert result["transportRetained"] is False
    assert result["unchanged"] and result["userUnchanged"] and result["toolUnchanged"]
    assert result["count"] == 3
    assert result["call"] == {"type": "toolCall", "id": "read1", "name": "read", "arguments": {"path": "src/index.ts"}}
    assert result["sizeRatio"] < 0.1


def test_explicit_request_projects_direct_assistant_entries_without_mutation() -> None:
    result = run_bun(r'''
      import {requestedMemoryTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      const entries=[{role:'user',content:'Original task'},
        {role:'assistant',id:'assistant-id',parentId:'user-id',provider:'transport',content:[
          {type:'thinking',thinking:'PRIVATE_REASONING'}, {type:'text',text:'Visible result'}]}];
      const original=JSON.stringify(entries),slice=requestedMemoryTaskSlice('Remember the settled fact.',entries);
      console.log(JSON.stringify({unchanged:original===JSON.stringify(entries),slice}));
    ''')
    assert result["unchanged"]
    entries = result["slice"]["entries"]
    assert len(entries) == 3
    # The real slash-command request happened after this source task. Keeping
    # its user entry last prevents old task restrictions from looking newer.
    assert entries[0] == {"role": "user", "content": "Original task"}
    assert entries[1] == {"role": "assistant", "id": "assistant-id", "parentId": "user-id",
                           "content": [{"type": "text", "text": "Visible result"}]}
    assert entries[2]["message"]["content"] == "Remember the settled fact."
    assert result["slice"]["memoryRequest"] == {"entryIndex": 2}


# --- Merged from test_learning_recovery.py ---
from pathlib import Path

import pytest

from support import run_bun_script

_m9_HARNESS = Path(__file__).with_name("learning-recovery-harness.ts")


@pytest.mark.parametrize("scenario", ["invalid", "cancelled", "failed", "throw", "noop", "dossier-read-error"])
def test_manual_selection_releases_locks_and_can_run_again(scenario: str) -> None:
    value = run_bun_script(_m9_HARNESS, scenario)
    assert value["selectors"] == 2, value
    assert value["planners"] == 0, value
    assert value["locks"] == [False, False], value
    assert value["shutdownLock"] is False, value
    assert not any("already running" in notice for notice in value["notices"]), value
    if scenario == "noop":
        assert value["notices"] == [], value
        assert len(value["receipts"]) == 2
        assert all([attempt["phase"] for attempt in receipt["attempts"]] == ["selector"] for receipt in value["receipts"])


# --- Merged from test_learning_task_evaluation.py ---
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate-learning.py"


def test_task_evaluation_scoring_and_validation() -> None:
    spec = importlib.util.spec_from_file_location("learning_task_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = {"id": "held-out", "prompt": "Where?", "required": ["canary-a"], "forbidden": ["production"]}
    assert module.score_case(case, "Use canary-a.") is True
    assert module.score_case(case, "Use canary-a in production.") is False
    assert module.score_case(case, "Unknown.") is False
    suite = {"version": 1, "baseline": {"memories": {}}, "candidate": {"memories": {}}, "cases": [case]}
    module.validate_suite(suite)
    suite["candidate"]["harness"] = {"rules": []}
    with pytest.raises(ValueError, match="only memories"):
        module.validate_suite(suite)
    del suite["candidate"]["harness"]
    suite["candidate"]["memories"] = {"../escape.md": "bad"}
    try:
        module.validate_suite(suite)
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe fixture Memory path was accepted")


def test_exact_answer_scoring_rejects_ambiguous_substrings() -> None:
    spec = importlib.util.spec_from_file_location("learning_task_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = {"id": "exact", "prompt": "Channel?", "required": ["canary"], "exact": "canary"}
    assert module.score_case(case, "canary") is True
    assert module.score_case(case, "unknown; canary") is False
    assert module.score_case(case, "canaryish") is False
    assert module.score_case(case, "not canary") is False


def test_effectiveness_rejects_failed_provider_arms() -> None:
    live_script = SCRIPT.parent.parent / "tests" / "live_effectiveness.py"
    spec = importlib.util.spec_from_file_location("live_effectiveness", live_script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = {
        "baseline": {"successRate": 0.0, "results": [{"id": "one", "passed": False, "error": "provider failed"}]},
        "candidate": {"successRate": 1.0, "results": [{"id": "one", "passed": True, "error": None}]},
        "regressions": [],
    }
    with pytest.raises(AssertionError, match="execute"):
        module.assert_effectiveness_report(report)


def test_read_body_evidence_requires_successful_native_read() -> None:
    spec = importlib.util.spec_from_file_location("learning_task_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = {"readBody": {"path": "orbit.md", "required": "BODY_MARKER"}}
    memory_root = Path("/tmp/project/.memory")
    assert module.read_body_matches(case, [{"path": "/tmp/project/.memory/orbit.md", "isError": False, "result": "BODY_MARKER"}], memory_root) is True
    assert module.read_body_matches(case, [{"path": ".memory/orbit.md", "isError": False, "result": "BODY_MARKER"}], memory_root) is True
    assert module.read_body_matches(case, [{"path": "orbit.md", "isError": False, "result": "BODY_MARKER"}], memory_root) is False
    assert module.read_body_matches(case, [{"path": "/tmp/project/other/orbit.md", "isError": False, "result": "BODY_MARKER"}], memory_root) is False
    assert module.read_body_matches(case, [{"path": "/tmp/project/.memory/nested/orbit.md", "isError": False, "result": "BODY_MARKER"}], memory_root) is False
    assert module.read_body_matches(case, [{"path": "/tmp/project/.memory/orbit.md", "isError": True, "result": "BODY_MARKER"}], memory_root) is False
    assert module.read_body_matches(case, [{"path": "/tmp/project/.memory/orbit.md", "isError": False, "result": "wrong body"}], memory_root) is False


def test_read_events_require_matching_native_call_ids() -> None:
    spec = importlib.util.spec_from_file_location("learning_task_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    start = {"type": "tool_execution_start", "toolName": "read", "toolCallId": "read-1", "args": {"path": ".memory/orbit.md"}}
    end = {"type": "tool_execution_end", "toolName": "read", "toolCallId": "read-1", "isError": False, "result": "BODY_MARKER"}
    assert module._read_events((json.dumps(start) + "\n" + json.dumps(end)).encode()) == [
        {"path": ".memory/orbit.md", "isError": False, "result": "BODY_MARKER"}
    ]
    no_id_end = {**end, "toolCallId": None, "args": {"path": "/tmp/project/.memory/orbit.md"}}
    mismatched_end = {**end, "toolCallId": "read-2", "args": {"path": "/tmp/project/.memory/orbit.md"}}
    assert module._read_events((json.dumps({**start, "toolCallId": None}) + "\n" + json.dumps(no_id_end)).encode()) == []
    assert module._read_events((json.dumps(start) + "\n" + json.dumps(mismatched_end)).encode()) == []


def test_provider_config_snapshot_is_private_and_detaches_symlinks(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("learning_task_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "agent"
    source.mkdir()
    auth_target = source / "auth-target.json"
    auth_target.write_text('{"fixture":"auth"}')
    (source / "auth.json").symlink_to(auth_target)
    (source / "models.json").write_text('{"fixture":"models"}')
    temporary, snapshot, fingerprint = module._snapshot_provider_config(source)
    try:
        assert snapshot.stat().st_mode & 0o777 == 0o700
        assert all((snapshot / name).stat().st_mode & 0o777 == 0o600 for name in ("auth.json", "models.json"))
        assert not (snapshot / "auth.json").is_symlink()
        (snapshot / "auth.json").write_text('{"fixture":"local-refresh"}')
        assert auth_target.read_text() == '{"fixture":"auth"}'
        assert fingerprint
    finally:
        temporary.cleanup()


def test_shipped_task_evaluation_suite_validates_without_authentication(tmp_path: Path) -> None:
    suite = SCRIPT.parent.parent / "examples" / "learning-task-evaluation.json"
    result = subprocess.run([sys.executable, str(SCRIPT), str(suite), "--validate"], cwd=tmp_path, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"valid": True, "cases": 1}


def test_task_arms_are_isolated_and_missing_prices_are_not_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = importlib.util.spec_from_file_location("learning_task_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "agent"
    source.mkdir()
    (source / "auth.json").write_text('{"fixture":"synthetic"}')
    roots: list[Path] = []
    copied_auth: list[str] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 0)
        assert command[command.index("--tools") + 1] == "read"
        assert "--no-extensions" in command and "--no-session" in command
        project = kwargs["cwd"]
        assert isinstance(project, Path)
        roots.append(project)
        agent = Path(kwargs["env"]["PI_CODING_AGENT_DIR"])
        assert agent != source
        assert (agent / "auth.json").stat().st_mode & 0o777 == 0o600
        assert json.loads((agent / "continual-learning.json").read_text()) == {"autoSettledLearning": False, "autoContinualLearning": False}
        copied_auth.append((agent / "auth.json").read_text())
        if len(copied_auth) == 1:
            (source / "auth.json").write_text('{"fixture":"changed-after-snapshot"}')
        (agent / "auth.json").write_text("local refresh")
        answer = "canary-a" if (project / ".memory/orbit.md").exists() else "unknown"
        kwargs["stdout"].write((json.dumps({"type": "message_end", "message": {
            "role": "assistant", "content": [{"type": "text", "text": answer}], "stopReason": "stop",
            "usage": {"input": 10, "output": 2, "totalTokens": 12, "cost": {"total": 0}},
        }}) + "\n").encode())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", run)
    suite = {"version": 1, "baseline": {"memories": {}}, "candidate": {"memories": {"orbit.md": "canary-a"}},
             "cases": [{"id": "held-out", "prompt": "Channel?", "required": ["canary-a"]}]}
    report = module.evaluate_suite(suite, "fixture/model", source)
    assert report["baseline"]["successRate"] == 0 and report["candidate"]["successRate"] == 1
    assert report["candidate"]["usage"]["totalTokens"] == 12
    assert report["baseline"]["cost"] is None and report["candidate"]["cost"] is None
    assert len(set(roots)) == 2 and all(not root.exists() for root in roots)
    assert copied_auth == ['{"fixture":"synthetic"}', '{"fixture":"synthetic"}']
    assert (source / "auth.json").read_text() == '{"fixture":"changed-after-snapshot"}'
    assert report["configSnapshot"]["files"] == ["auth.json"]


@pytest.mark.parametrize("include_read", [False, True])
def test_candidate_requires_native_read_body_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, include_read: bool) -> None:
    spec = importlib.util.spec_from_file_location("learning_task_eval", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "agent"
    source.mkdir()

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 0)
        project = kwargs["cwd"]
        assert isinstance(project, Path)
        candidate = (project / ".memory/orbit.md").exists()
        events: list[dict[str, object]] = []
        if candidate and include_read:
            events.extend([
                {"type": "tool_execution_start", "toolName": "read", "toolCallId": "read-1", "args": {"path": str(project / ".memory/orbit.md")}},
                {"type": "tool_execution_end", "toolName": "read", "toolCallId": "read-1", "isError": False, "result": "BODY_MARKER"},
            ])
        answer = "canary" if candidate else "unknown"
        events.append({"type": "message_end", "message": {
            "role": "assistant", "content": [{"type": "text", "text": answer}], "stopReason": "stop",
            "usage": {"input": 1, "output": 1, "totalTokens": 2, "cost": {"total": 0}},
        }})
        kwargs["stdout"].write(("\n".join(json.dumps(event) for event in events) + "\n").encode())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", run)
    suite = {"version": 1, "baseline": {"memories": {}}, "candidate": {"memories": {"orbit.md": "body"}},
             "cases": [{"id": "held-out", "prompt": "Channel?", "required": ["canary"], "exact": "canary",
                         "readBody": {"path": "orbit.md", "required": "BODY_MARKER"}}]}
    report = module.evaluate_suite(suite, "fixture/model", source)
    assert report["baseline"]["results"][0]["passed"] is False
    assert report["candidate"]["results"][0]["passed"] is include_read


# --- Merged from test_legacy_output_checks.py ---
from support import isolated_run_bun as run_bun


def test_policy_phases_and_post_execution_checks_are_explicit() -> None:
    source = r'''
      import fs from "node:fs";
      import os from "node:os";
      import path from "node:path";
      import { mergeLayers } from "./packages/continual-learning/extensions/guardrail-engine.ts";
      import { evaluateLegacyTools, evaluateLegacyPhase as evaluatePhase } from "./packages/continual-learning/extensions/legacy-harness.ts";
      import registerOutputChecks from "./packages/continual-learning/extensions/output-checks.ts";

      const hooks = {};
      const entries = [];
      const repairs = [];
      const pi = {
        on: (name, fn) => (hooks[name] ??= []).push(fn),
        appendEntry: (customType, data) => entries.push({ customType, data }),
        sendMessage: (message, options) => repairs.push({ message, options }),
        registerEntryRenderer: () => {},
      };
      const config = mergeLayers([{
        source: "project",
        policies: [
          { name: "tool-default", tools: ["bash"], paths: ["command"], pattern: "legacy-secret", reason: "Keep tool-call rule." },
          { name: "output-secret", phase: "output", pattern: "DO_NOT_SAY", reason: "Do not disclose this output." },
          { name: "artifact-secret", phase: "artifact", tools: ["write", "edit"], pattern: "DO_NOT_WRITE", reason: "Remove this artifact content." },
          { name: "bash-artifact-secret", phase: "artifact", tools: ["bash"], artifactPaths: ["generated.txt"], pattern: "DO_NOT_WRITE", reason: "Remove this command-produced content." },
        ],
      }]);
      const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "guard-output-"));
      const cwd = path.join(tmp, "project");
      const agentDir = path.join(tmp, "agent");
      fs.mkdirSync(agentDir, { recursive: true });
      process.env.PI_CODING_AGENT_DIR = agentDir;
      fs.mkdirSync(path.join(cwd, ".pi"), { recursive: true });
      fs.writeFileSync(path.join(cwd, ".pi", "harness.json"), JSON.stringify({ policies: [
        { name: "output-secret", phase: "output", pattern: "DO_NOT_SAY", reason: "Do not disclose this output." },
        { name: "artifact-secret", phase: "artifact", tools: ["write", "edit"], pattern: "DO_NOT_WRITE", reason: "Remove this artifact content." },
        { name: "bash-artifact-secret", phase: "artifact", tools: ["bash"], artifactPaths: ["generated.txt"], pattern: "DO_NOT_WRITE", reason: "Remove this command-produced content." },
      ] }));
      const ctx = { cwd, hasUI: false };
      registerOutputChecks(pi);

      const defaultDecision = evaluateLegacyTools(config.legacy, "bash", { command: "legacy-secret" }).matches[0];
      const outputDecision = evaluatePhase(config.legacy, { phase: "output", text: "DO_NOT_SAY" });
      const artifactDecision = evaluatePhase(config.legacy, { phase: "artifact", toolName: "write", text: "DO_NOT_WRITE" });

      const outputHandler = hooks.message_end[0];
      await outputHandler({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "DO_NOT_SAY" }] } }, { ...ctx });
      const outputRepairsAfterFirst = repairs.length;
      hooks.input[0]({ type: "input", source: "extension", text: "extension correction" }, { ...ctx });
      await outputHandler({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "DO_NOT_SAY" }] } }, { ...ctx });
      await outputHandler({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "DO_NOT_SAY" }] } }, { ...ctx });

      hooks.input[0]({ type: "input", source: "interactive", text: "interrupted task" }, { ...ctx });
      fs.writeFileSync(path.join(cwd, "generated.txt"), "DO_NOT_WRITE");
      const repairsBeforeInterrupted = repairs.length;
      await outputHandler({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "DO_NOT_SAY" }], stopReason: "aborted" } }, { ...ctx });
      await outputHandler({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "DO_NOT_SAY" }], stopReason: "error" } }, { ...ctx });
      const interruptedDidNotRepair = repairs.length === repairsBeforeInterrupted;

      const artifactHandler = hooks.tool_result[0];
      hooks.input[0]({ type: "input", source: "interactive", text: "start a new task" }, { ...ctx });
      const safePath = path.join(cwd, "safe.txt");
      fs.writeFileSync(safePath, "safe artifact");
      await artifactHandler({ type: "tool_result", toolCallId: "1", toolName: "write", input: { path: "safe.txt", content: "DO_NOT_WRITE" }, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const matchingPath = path.join(cwd, "matching.txt");
      fs.writeFileSync(matchingPath, "DO_NOT_WRITE");
      await artifactHandler({ type: "tool_result", toolCallId: "2", toolName: "write", input: { path: "matching.txt", content: "safe argument" }, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const repairsAfterMatchingArtifact = repairs.length;
      await artifactHandler({ type: "tool_result", toolCallId: "2-repeat", toolName: "write", input: { path: "matching.txt", content: "safe argument" }, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const unchangedArtifactDeduped = repairs.length === repairsAfterMatchingArtifact;
      const generatedPath = path.join(cwd, "generated.txt");
      fs.writeFileSync(generatedPath, "DO_NOT_WRITE");
      await artifactHandler({ type: "tool_result", toolCallId: "bash-1", toolName: "bash", input: { command: "generate safe artifact" }, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const repairsBeforeUnsupported = repairs.length;
      await artifactHandler({ type: "tool_result", toolCallId: "3", toolName: "write", input: {}, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const outside = path.join(tmp, "outside.txt");
      fs.writeFileSync(outside, "DO_NOT_WRITE");
      await artifactHandler({ type: "tool_result", toolCallId: "4", toolName: "write", input: { path: "../outside.txt" }, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const target = path.join(cwd, "target.txt");
      fs.writeFileSync(target, "safe");
      fs.symlinkSync(target, path.join(cwd, "link.txt"));
      await artifactHandler({ type: "tool_result", toolCallId: "5", toolName: "write", input: { path: "link.txt" }, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const large = path.join(cwd, "large.txt");
      fs.writeFileSync(large, "x".repeat(1_000_001));
      await artifactHandler({ type: "tool_result", toolCallId: "6", toolName: "write", input: { path: "large.txt" }, content: [{ type: "text", text: "ok" }], isError: false }, { ...ctx });
      const unsupportedDidNotRepair = repairs.length === repairsBeforeUnsupported;
      await outputHandler({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "done" }], stopReason: "stop" } }, { ...ctx });

      console.log(JSON.stringify({
        phases: config.legacy.policies.map((policy) => [policy.name, policy.phase]),
        defaultMatchesToolCall: defaultDecision?.policyName === "tool-default",
        outputMatches: outputDecision?.policyName === "output-secret",
        artifactMatches: artifactDecision?.policyName === "artifact-secret",
        outputRepairsBounded: outputRepairsAfterFirst === 1 && entries.filter((entry) => entry.data?.phase === "output" && entry.data?.status === "violated").length === 2,
        interruptedDidNotRepair,
        unchangedArtifactDeduped,
        outputViolation: entries.some((entry) => entry.data?.phase === "output" && entry.data?.status === "violated"),
        outputExhausted: entries.some((entry) => entry.data?.phase === "output" && entry.data?.status === "repair-exhausted"),
        argsOnlyDoesNotMatchArtifact: !entries.some((entry) => entry.data?.path === "safe.txt" && entry.data?.status === "violated"),
        actualArtifactMatches: entries.some((entry) => entry.data?.path === "matching.txt" && entry.data?.status === "violated"),
        bashArtifactMatches: entries.some((entry) => entry.data?.path === "generated.txt" && entry.data?.status === "violated"),
        unsupportedMissing: entries.some((entry) => entry.data?.path === undefined && entry.data?.status === "unsupported"),
        unsupportedOutside: entries.some((entry) => entry.data?.path === "../outside.txt" && entry.data?.status === "unsupported"),
        unsupportedSymlink: entries.some((entry) => entry.data?.path === "link.txt" && entry.data?.status === "unsupported"),
        unsupportedLarge: entries.some((entry) => entry.data?.path === "large.txt" && entry.data?.status === "unsupported"),
        unsupportedDidNotRepair,
        finalArtifactRecheckDeduped: entries.filter((entry) => entry.data?.path === "matching.txt" && entry.data?.status === "violated").length === 1,
        finalBashRecheckDeduped: entries.filter((entry) => entry.data?.path === "generated.txt" && entry.data?.status === "violated").length === 1,
      }));
    '''
    result = run_bun(source)
    assert result["phases"] == [["tool-default", "tool-call"], ["output-secret", "output"], ["artifact-secret", "artifact"], ["bash-artifact-secret", "artifact"]]
    assert result["defaultMatchesToolCall"]
    assert result["outputMatches"] and result["artifactMatches"]
    assert result["outputRepairsBounded"] and result["outputViolation"] and result["outputExhausted"]
    assert result["interruptedDidNotRepair"] and result["unchangedArtifactDeduped"]
    assert result["argsOnlyDoesNotMatchArtifact"] and result["actualArtifactMatches"] and result["bashArtifactMatches"]
    assert result["unsupportedMissing"] and result["unsupportedOutside"] and result["unsupportedSymlink"] and result["unsupportedLarge"]
    assert result["unsupportedDidNotRepair"]
    assert result["finalArtifactRecheckDeduped"] and result["finalBashRecheckDeduped"]


def test_harness_guidance_is_registered_separately_from_guardrail_enforcement() -> None:
    source = r'''
      import fs from "node:fs";
      import os from "node:os";
      import path from "node:path";
      import registerGuardrails from "./packages/continual-learning/extensions/guardrails.ts";
      import registerHarnessGuidance from "./packages/continual-learning/extensions/harness-guidance.ts";

      const hooks = {};
      const entries = [];
      const pi = {
        on: (name, fn) => (hooks[name] ??= []).push(fn),
        appendEntry: (customType, data) => entries.push({ customType, data }),
        registerEntryRenderer: () => {},
        registerCommand: () => {},
        getCommands: () => [{ name: "skill:review", source: "skill" }],
      };
      const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "guard-context-"));
      const cwd = path.join(tmp, "project");
      fs.mkdirSync(path.join(cwd, ".pi"), { recursive: true });
      fs.writeFileSync(path.join(cwd, ".pi", "harness.json"), JSON.stringify({ skillPrompts: { review: { prompt: "use the review checklist", target: "system" } } }));
      const event = { type: "before_agent_start", prompt: '<skill name="review" location="/tmp/review/SKILL.md">\ncheck\n</skill>', systemPrompt: "base", systemPromptOptions: {sections:{other:"KEEP"},promptGuidelines:[],skills:[{name:"review"}]} };
      const ctx = { cwd, hasUI: false, sessionManager: { buildContextEntries: () => [], getBranch: () => [] } };
      registerGuardrails(pi);
      const guardrailBefore = hooks.before_agent_start?.length ?? 0;
      registerHarnessGuidance(pi);
      const guidanceResult = await hooks.before_agent_start[0](event, ctx);
      console.log(JSON.stringify({ guardrailBefore, guidanceResult:guidanceResult??null, options:event.systemPromptOptions, eventCount: entries.filter(entry=>entry.data?.kind==='skill-prompt').length }));
    '''
    result = run_bun(source)
    assert result["guardrailBefore"] == 0
    # The required contract delivers legacy guidance through additive sections.
    assert result["guidanceResult"] is None
    # Legacy guidance has the same explicit task boundary as flat skill guidance.
    assert result["options"]["sections"]["harness_guidance"] == (
        "[harness:legacy-skill] Only for this /skill:review task; retained history does not extend its scope.\n"
        "use the review checklist"
    )
    assert result["options"]["sections"]["other"] == "KEEP"
    assert result["eventCount"] == 1


def test_post_generation_policy_rejects_retroactive_confirmation_and_wrong_subject_fields() -> None:
    source = r'''
      import {mergeLayers} from "./packages/continual-learning/extensions/guardrail-engine.ts";
      const validatePolicyDeclaration=policy=>mergeLayers([{source:'fixture',policies:[policy]}]).errors;
      console.log(JSON.stringify({
        output: validatePolicyDeclaration({ name: "output", phase: "output", tools: ["write"], paths: ["content"], action: "confirm", pattern: "x", reason: "x" }),
        artifact: validatePolicyDeclaration({ name: "artifact", phase: "artifact", paths: ["content"], require: { path: "path", pattern: "x" }, action: "confirm", pattern: "x", reason: "x" }),
        validArtifact: validatePolicyDeclaration({ name: "artifact-ok", phase: "artifact", tools: ["bash"], artifactPaths: ["dist/out.txt"], pattern: "x", reason: "x" }),
      }));
    '''
    result = run_bun(source)
    output_errors = " ".join(result["output"])
    artifact_errors = " ".join(result["artifact"])
    assert "confirm action is unavailable" in output_errors
    assert "tools is only supported" in output_errors
    assert "paths is only supported" in output_errors
    assert "confirm action is unavailable" in artifact_errors
    assert "paths is only supported" in artifact_errors
    assert "require.path is only supported" in artifact_errors
    assert result["validArtifact"] == []


# --- Merged from test_recent_learning_input.py ---
from support import run_bun


def test_actual_pi12_empty_timeout_removal_keeps_exact_failed_task_replay(tmp_path) -> None:
    import json
    # Given the actual V53 retry log, When Pi removes only an empty failed
    # assistant reply, Then exact replay remains digest-bound and retains the
    # failure without reviving deleted message content.
    result = run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {recentProjectLearningInput} from './packages/continual-learning/extensions/learning-input.ts';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest,containsSensitiveMemoryMaterial} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {successfulFailureObservationReady} from './packages/continual-learning/tests/failure-observation-proof.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-pi12-timeout-context-edit.json','utf8'));
      const root=ROOT,cwd=path.join(root,'project'),agent=path.join(root,'agent'),dir=path.join(agent,'sessions','scope');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(dir,{recursive:true});
      const original=f.files['orientation/without-learning/verifier-feedback/session.jsonl'].text;
      const rows=original.trimEnd().split('\n').map(JSON.parse);rows[0].cwd=cwd;
      const file=path.join(dir,'stage-0.jsonl'),text=rows.map(JSON.stringify).join('\n')+'\n';fs.writeFileSync(file,text);
      const source=await recentProjectLearningInput({cwd,agentDir:agent,sessionDir:dir,requestedSessionFile:file});
      const task=source?.contextEntries?currentTaskSlice(source.contextEntries.slice(f.queued.from,f.queued.to+1)):undefined;
      const read=rows.filter(row=>row.message?.role==='toolResult'&&row.message.toolName==='read').at(-1);
      const proof=successfulFailureObservationReady({
        originalSession:f.files['orientation/without-learning/session.jsonl'].text,currentSession:original,
        verifierText:read.message.content[0].text,verifierPath:'/home/node/project-verification.json',
        sourceBefore:f.observation.sourceHashes,sourceAfter:f.observation.sourceHashes,queued:f.queued,explicitBackfills:0});
      console.log(JSON.stringify({proof,accepted:!!source,rawUnchanged:fs.readFileSync(file,'utf8')===text,
        sourceBound:source?.sourceDigest===sha256Digest(text),taskDigest:task?sha256Digest(JSON.stringify(task)):null,expectedDigest:f.queued.digest,
        removedReplyProjected:source?!source.entries.some(x=>x.id==='00be88a8'):false,
        sensitive:containsSensitiveMemoryMaterial(JSON.stringify(f)),historicalFailure:f.provenance.status}));
    '''.replace('ROOT', json.dumps(str(tmp_path))))
    assert result['rawUnchanged'] and not result['sensitive'] and result['historicalFailure'] == 'failed'
    assert result['accepted'] and result['sourceBound'] and result['removedReplyProjected']
    assert result['taskDigest'] == result['expectedDigest']
    assert result['proof']['ready'], result['proof']


def test_exact_replay_sanitizes_removed_error_metadata_and_refuses_meaningful_edits(tmp_path) -> None:
    import json
    result = run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {recentProjectLearningInput} from './packages/continual-learning/extensions/learning-input.ts';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {sha256Digest} from './packages/continual-learning/extensions/consolidation-run.ts';
      const f=JSON.parse(fs.readFileSync('./packages/continual-learning/tests/fixtures/real-pi12-timeout-context-edit.json','utf8'));
      const root=ROOT,cwd=path.join(root,'project'),agent=path.join(root,'agent'),dir=path.join(agent,'sessions','scope');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(dir,{recursive:true});
      const original=f.files['orientation/without-learning/verifier-feedback/session.jsonl'].text.trimEnd().split('\n').map(JSON.parse);
      const file=path.join(dir,'source.jsonl'),results={};let sanitized,digest;
      const changes={metadata:(target,edit)=>{target.message.errorMessage='REMOVED_PRIVATE_ERROR';target.message.provider='REMOVED_PRIVATE_PROVIDER';target.message.model='REMOVED_PRIVATE_MODEL'},
        text:target=>target.message.content=[{type:'text',text:'REMOVED_PRIVATE_TEXT'}],
        thinking:target=>target.message.content=[{type:'thinking',thinking:'REMOVED_PRIVATE_THOUGHT'}],
        user:target=>target.message={role:'user',content:'REMOVED_PRIVATE_USER'},
        tool:target=>target.message={role:'toolResult',toolName:'read',toolCallId:'removed',content:[{type:'text',text:'REMOVED_PRIVATE_TOOL'}]},
        summary:target=>{delete target.message;target.type='compaction';target.summary='REMOVED_PRIVATE_SUMMARY'},
        replacement:(_target,edit)=>edit.replacement={role:'assistant',content:[{type:'text',text:'Replacement'}]},
        aborted:target=>target.message.stopReason='aborted',successful:target=>target.message.stopReason='stop',
        unknownTarget:(_target,edit)=>edit.targetId='missing',extraWrapper:target=>target.privateNote='REMOVED_PRIVATE_OUTER',
        extraEdit:(_target,edit)=>edit.privateNote='REMOVED_PRIVATE_EDIT',timestamp:target=>target.message.timestamp='REMOVED_PRIVATE_TIMESTAMP',
        outerTimestamp:target=>target.timestamp={privateNote:'REMOVED_PRIVATE_OUTER_TIMESTAMP'},
        outerTimestampText:target=>target.timestamp='REMOVED_PRIVATE_OUTER_TIMESTAMP',
        editTimestamp:(_target,edit)=>edit.timestamp={privateNote:'REMOVED_PRIVATE_EDIT_TIMESTAMP'}};
      for(const [name,change] of Object.entries(changes)){
        const rows=structuredClone(original);rows[0].cwd=cwd;
        const edit=rows.find(x=>x.type==='context_edit'),target=rows.find(x=>x.id===edit.targetId);change(target,edit);
        fs.writeFileSync(file,rows.map(JSON.stringify).join('\n')+'\n');
        const source=await recentProjectLearningInput({cwd,agentDir:agent,sessionDir:dir,requestedSessionFile:file});results[name]=!!source;
        if(name==='metadata'&&source){
          sanitized=!JSON.stringify({entries:source.entries,context:source.contextEntries}).includes('REMOVED_PRIVATE_');
          digest=sha256Digest(JSON.stringify(currentTaskSlice(source.contextEntries.slice(f.queued.from,f.queued.to+1))));
        }
      }
      console.log(JSON.stringify({results,sanitized,digest,expected:f.queued.digest}));
    '''.replace('ROOT', json.dumps(str(tmp_path))))
    assert result['results'].pop('metadata') and result['sanitized']
    assert not any(result['results'].values()), result['results']
    assert result['digest'] == result['expected']


def test_recent_project_input_uses_active_context_without_mutating_source() -> None:
    result = run_bun(r'''
      import fs from 'node:fs'; import path from 'node:path';
      import {recentProjectLearningInput} from './packages/continual-learning/extensions/learning-input.ts';
      const root=process.env.TEST_ROOT, cwd=path.join(root,'project'), agent=path.join(root,'agent'), dir=path.join(agent,'sessions','scope');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(dir,{recursive:true});
      const rows=[{type:'session',version:3,id:'previous',cwd,timestamp:new Date().toISOString()},
        {type:'message',id:'u',parentId:null,timestamp:new Date().toISOString(),message:{role:'user',content:'This project uses pnpm.'}},
        {type:'message',id:'a',parentId:'u',timestamp:new Date().toISOString(),message:{role:'assistant',content:[]}}];
      const file=path.join(dir,'previous.jsonl'), original=rows.map(JSON.stringify).join('\n')+'\n';fs.writeFileSync(file,original);
      const result=await recentProjectLearningInput({cwd,agentDir:agent,sessionDir:dir,currentSessionFile:path.join(dir,'current.jsonl')});
      console.log(JSON.stringify({result,unchanged:fs.readFileSync(file,'utf8')===original}));
    ''', temp_dirs=("TEST_ROOT",))
    assert result["unchanged"] is True
    assert result["result"]["sessionId"] == "previous"
    assert len(result["result"]["sourceDigest"]) == 64
    assert result["result"]["entries"][0]["message"]["content"] == "This project uses pnpm."


def test_recent_project_input_rejects_wrong_scope_aliases_and_removed_context() -> None:
    result = run_bun(r'''
      import fs from 'node:fs'; import path from 'node:path';
      import {recentProjectLearningInput} from './packages/continual-learning/extensions/learning-input.ts';
      const root=process.env.TEST_ROOT,cwd=path.join(root,'project'),agent=path.join(root,'agent'),dir=path.join(agent,'sessions','scope');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(dir,{recursive:true});
      const header=project=>({type:'session',version:3,id:'fixture',cwd:project,timestamp:new Date().toISOString()});
      const user={type:'message',id:'u',parentId:null,timestamp:new Date().toISOString(),message:{role:'user',content:'Private project fact'}};
      const write=(file,rows)=>fs.writeFileSync(file,rows.map(JSON.stringify).join('\n')+'\n');
      write(path.join(dir,'wrong.jsonl'),[header(path.join(root,'other')),user]);
      const outside=path.join(root,'outside.jsonl');write(outside,[header(cwd),user]);fs.symlinkSync(outside,path.join(dir,'linked.jsonl'));
      write(path.join(dir,'removed.jsonl'),[header(cwd),user,{type:'context_edit',id:'edit',parentId:'u',targetId:'u',replacement:null,timestamp:new Date().toISOString()}]);
      const value=await recentProjectLearningInput({cwd,agentDir:agent,sessionDir:dir});
      console.log(JSON.stringify(value??null));
    ''', temp_dirs=("TEST_ROOT",))
    assert result is None


def test_recent_input_rejects_cycles_duplicate_ids_and_missing_parents() -> None:
    result = run_bun(r'''
      import fs from 'node:fs'; import path from 'node:path';
      import {recentProjectLearningInput} from './packages/continual-learning/extensions/learning-input.ts';
      const root=process.env.TEST_ROOT,cwd=path.join(root,'project'),agent=path.join(root,'agent'),dir=path.join(agent,'sessions','scope');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(dir,{recursive:true});
      const header={type:'session',version:3,id:'fixture',cwd,timestamp:new Date().toISOString()};
      const user={type:'message',id:'u',parentId:null,timestamp:new Date().toISOString(),message:{role:'user',content:'This project uses pnpm.'}};
      const cases=[[{...user,parentId:'u'}],[user,{...user}], [{...user,parentId:'missing'}],
        [{...user,parentId:'b'},{...user,id:'b',parentId:'u'}]];
      const results=[];
      for(const rows of cases){fs.writeFileSync(path.join(dir,'source.jsonl'),[header,...rows].map(JSON.stringify).join('\n')+'\n');
        results.push((await recentProjectLearningInput({cwd,agentDir:agent,sessionDir:dir}))??null);}
      console.log(JSON.stringify(results));
    ''', temp_dirs=("TEST_ROOT",), timeout=2)
    assert result == [None] * 4



def test_v1_projection_never_revives_removed_summaries_or_user_messages() -> None:
    result = run_bun(r''' 
      import {mock} from 'bun:test';
      const sdk=await import('./node_modules/@earendil-works/pi-coding-agent/dist/index.js');
      const exports={...sdk};mock.module('./packages/continual-learning/node_modules/@earendil-works/pi-coding-agent/dist/index.js',()=>exports);
      const {recentProjectLearningInput}=await import('./packages/continual-learning/extensions/learning-input.ts');
      const fs=await import('node:fs'),path=await import('node:path');
      const root=process.env.TEST_ROOT,cwd=path.join(root,'project'),agent=path.join(root,'agent'),dir=path.join(agent,'sessions','scope');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(dir,{recursive:true});
      const timestamp=new Date().toISOString();
      const rows=[{type:'session',version:3,id:'fixture',cwd,timestamp},
        {type:'message',id:'old',parentId:null,timestamp,message:{role:'user',content:'REMOVED_PRIVATE_USER'}},
        {type:'compaction',id:'summary',parentId:'old',timestamp,summary:'REMOVED_PRIVATE_SUMMARY',firstKeptEntryId:'old',tokensBefore:1},
        {type:'context_edit',id:'edit1',parentId:'summary',timestamp,targetId:'summary',replacement:null},
        {type:'context_edit',id:'edit2',parentId:'edit1',timestamp,targetId:'old',replacement:null},
        {type:'message',id:'new',parentId:'edit2',timestamp,message:{role:'user',content:'Retain this project fact.'}}];
      const file=path.join(dir,'source.jsonl'),original=rows.map(JSON.stringify).join('\n')+'\n';fs.writeFileSync(file,original);
      const value=await recentProjectLearningInput({cwd,agentDir:agent,sessionDir:dir});
      console.log(JSON.stringify({value,unchanged:fs.readFileSync(file,'utf8')===original}));
    ''', temp_dirs=("TEST_ROOT",))
    assert result["unchanged"] is True
    assert len(result["value"]["entries"]) == 1
    assert result["value"]["entries"][0]["message"]["content"] == "Retain this project fact."


def test_recent_input_bounds_cancellation_and_current_source_exclusion() -> None:
    result = run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {recentProjectLearningInput} from './packages/continual-learning/extensions/learning-input.ts';
      const root=process.env.TEST_ROOT,cwd=path.join(root,'project'),agent=path.join(root,'agent'),dir=path.join(agent,'sessions','scope');
      fs.mkdirSync(cwd,{recursive:true});fs.mkdirSync(dir,{recursive:true});
      const rows=[{type:'session',version:3,id:'fixture',cwd,timestamp:new Date().toISOString()},
        {type:'message',id:'u',parentId:null,message:{role:'user',content:'Use pnpm.'}}];
      const file=path.join(dir,'source.jsonl'),data=rows.map(JSON.stringify).join('\n')+'\n',args={cwd,agentDir:agent,sessionDir:dir};
      const results=[];fs.writeFileSync(file,data);
      results.push(await recentProjectLearningInput({...args,currentSessionFile:file})??null);
      results.push(await recentProjectLearningInput({...args,signal:AbortSignal.abort()})??null);
      fs.writeFileSync(file,data+'broken json\n');results.push(await recentProjectLearningInput(args)??null);
      fs.writeFileSync(file,data);fs.utimesSync(file,new Date(0),new Date(0));results.push(await recentProjectLearningInput(args)??null);
      fs.writeFileSync(file,' '.repeat(8*1024*1024+1));results.push(await recentProjectLearningInput(args)??null);
      const alias=path.join(agent,'sessions','alias');fs.symlinkSync(dir,alias);results.push(await recentProjectLearningInput({...args,sessionDir:alias})??null);
      console.log(JSON.stringify(results));
    ''', temp_dirs=("TEST_ROOT",))
    assert result == [None] * 6


# --- Merged from test_run_start.py ---
"""Merged tests from: test_run_start_guidance_preservation.py, test_run_start_harness_guidance.py, test_run_start_prompt_composition.py, test_run_start_section.py."""

import json
from support import run_bun
import os
from pathlib import Path
import pytest

# --- Merged from test_run_start_guidance_preservation.py ---

def test_malformed_config_preserves_complete_scoped_branch_delivery(tmp_path):
    value = run_bun(f'''
      import fs from 'node:fs';
      import register from './packages/continual-learning/extensions/harness-guidance.ts';
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(cwd+'/.pi');
      fs.writeFileSync(cwd+'/.pi/harness.json','{{malformed');
      const scoped='[harness:saved] Only for subjects matching "needle"; a historical match does not extend this guidance to unrelated tasks.\\nCOMPLETE_SCOPED_GUIDANCE';
      const branch=[{{type:'custom',customType:'harness-guidance-delivery',data:{{entries:[{{id:'saved',revision:'old',status:'active',text:scoped,source:'project'}}]}}}}];
      const hooks={{}},appended=[];register({{on:(n,h)=>hooks[n]=h,registerEntryRenderer(){{}},appendEntry:(customType,data)=>appended.push({{customType,data}})}});
      const options={{sections:{{}},skills:[]}};
      const returned=hooks.before_agent_start({{prompt:'plain',systemPromptOptions:options}},{{cwd,sessionManager:{{getBranch:()=>branch,buildContextEntries:()=>[]}}}});
      console.log(JSON.stringify({{options,returned:returned??null,appended,scoped}}));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    assert value['returned'] is None
    assert value['options']['sections']['harness_guidance'] == value['scoped']
    assert any(entry['data'].get('kind') == 'text-incomplete' for entry in value['appended'])
    delivery = next(entry['data'] for entry in value['appended'] if entry['customType'] == 'harness-guidance-delivery')
    assert delivery['entries'][0]['text'] == value['scoped']
    assert delivery['entries'][0]['status'] == 'active'


def test_overbudget_scan_never_reintroduces_old_unscoped_guidance(tmp_path):
    value = run_bun(f'''
      import fs from 'node:fs';
      import register from './packages/continual-learning/extensions/harness-guidance.ts';
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(cwd+'/.pi');
      fs.writeFileSync(cwd+'/.pi/harness.json',JSON.stringify({{rules:[{{id:'old',text:'needle',instructions:'CURRENT_SCOPED_GUIDANCE'}}]}}));
      const scoped='[harness:valid] Only for subjects matching "other"; a historical match does not extend this guidance to unrelated tasks.\\nVALID_SCOPED_GUIDANCE';
      const branch=[{{type:'custom_message',customType:'harness-guidance',details:{{entries:[{{id:'old',revision:'old',status:'active',text:'UNSCOPED OLD GUIDANCE'}},{{id:'valid',revision:'saved',status:'active',text:scoped}}]}}}}];
      const hooks={{}},appended=[];register({{on:(n,h)=>hooks[n]=h,registerEntryRenderer(){{}},appendEntry:(customType,data)=>appended.push({{customType,data}})}});
      const options={{sections:{{}},skills:[]}};
      hooks.before_agent_start({{prompt:'x'.repeat(2000001),systemPromptOptions:options}},{{cwd,sessionManager:{{getBranch:()=>branch,buildContextEntries:()=>[]}}}});
      console.log(JSON.stringify({{options,appended,scoped}}));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    section = value['options']['sections'].get('harness_guidance', '')
    assert 'UNSCOPED OLD GUIDANCE' not in section
    assert value['scoped'] in section
    notices = [entry['data']['prompt'] for entry in value['appended'] if entry['data'].get('kind') == 'text-incomplete']
    assert any('scope' in notice.lower() for notice in notices)


def test_legacy_skill_guidance_has_task_scope_and_plain_read_does_not_invoke(tmp_path):
    value = run_bun(f'''
      import fs from 'node:fs';
      import register from './packages/continual-learning/extensions/harness-guidance.ts';
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(cwd+'/.pi');
      fs.writeFileSync(cwd+'/.pi/harness.json',JSON.stringify({{skillPrompts:{{review:{{prompt:'LEGACY_BODY',target:'user'}}}}}}));
      const hooks={{}};register({{on:(n,h)=>hooks[n]=h,registerEntryRenderer(){{}},appendEntry(){{}}}});
      const ctx={{cwd,sessionManager:{{getBranch:()=>[],buildContextEntries:()=>[]}}}};
      const start=prompt=>{{const options={{sections:{{}},skills:[{{name:'review'}}]}};const returned=hooks.before_agent_start({{prompt,systemPromptOptions:options}},ctx);return {{options,returned:returned??null}};}};
      console.log(JSON.stringify({{invoked:start('<skill name="review" location="/fixture/SKILL.md">\\nbody\\n</skill>\\n\\ntask'),plain:start('Read /fixture/SKILL.md')}}));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    section = value['invoked']['options']['sections']['harness_guidance']
    assert 'Only for this /skill:review task; retained history does not extend its scope.\nLEGACY_BODY' in section
    assert value['invoked']['returned'] is None
    assert 'harness_guidance' not in value['plain']['options']['sections']

# --- Merged from test_run_start_harness_guidance.py ---

def test_guidance_is_additive_repeated_and_old_injections_are_filtered(tmp_path):
    result = run_bun(f'''
      import fs from 'node:fs';
      import register from './packages/continual-learning/extensions/harness-guidance.ts';
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(cwd+'/.pi');
      fs.writeFileSync(cwd+'/.pi/harness.json',JSON.stringify({{rules:[{{id:'text',text:'needle',instructions:'SCOPED_TEXT'}},{{id:'skill',skill:'review',instructions:'SCOPED_SKILL'}}],skillPrompts:{{review:{{prompt:'LEGACY_GUIDANCE',target:'system'}}}}}}));
      const hooks={{}},entries=[];register({{on:(n,h)=>hooks[n]=h,registerEntryRenderer(){{}},appendEntry:(customType,data)=>entries.push({{type:'custom',customType,data}})}});
      const ctx={{cwd,sessionManager:{{buildContextEntries:()=>[],getBranch:()=>entries}}}};
      const start=()=>{{const options={{skills:[{{name:'review'}}],sections:{{other:'OTHER_MARKER'}},promptGuidelines:['EXISTING']}};const returned=hooks.before_agent_start({{prompt:'<skill name="review" location="/fixture/SKILL.md">\\nbody\\n</skill>\\n\\nneedle',systemPromptOptions:options}},ctx);return {{options,returned:returned??null}};}};
      const first=start(),second=start();
      ctx.sessionManager.buildContextEntries=()=>{{throw Error('incomplete')}};
      const incomplete=start();
      const filtered=hooks.context({{messages:[{{role:'custom',customType:'harness-guidance',content:'OLD'}},{{role:'custom',customType:'skill-prompt-guidance',content:'OLD'}},{{role:'custom',customType:'workflow',content:'KEEP'}}]}});
      console.log(JSON.stringify({{first,second,incomplete,entries,filtered}}));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    for run in ('first', 'second', 'incomplete'):
        assert result[run]['returned'] is None
        section = result[run]['options']['sections']['harness_guidance']
        assert all(marker in section for marker in ('SCOPED_TEXT', 'SCOPED_SKILL', 'LEGACY_GUIDANCE')), (run, result)
        assert result[run]['options']['sections']['other'] == 'OTHER_MARKER'
        assert result[run]['options']['promptGuidelines'] == ['EXISTING']
    assert result['filtered']['messages'] == [{'role': 'custom', 'customType': 'workflow', 'content': 'KEEP'}]
    assert any(entry['data'].get('entries') for entry in result['entries'])
    text_events = [entry for entry in result['entries'] if entry['data'].get('kind') == 'text-rule']
    assert len(text_events) == 1

# --- Merged from test_run_start_prompt_composition.py ---

def test_memory_and_goal_compose_with_pi_12_prompt_builder(tmp_path):
    configured = os.environ.get("PI_12_PACKAGE_DIR")
    if not configured:
        pytest.skip("Set PI_12_PACKAGE_DIR to a provisioned Pi 1.2 package directory")
    package = Path(configured).resolve()
    version = json.loads((package / "package.json").read_text())["version"]
    assert version.startswith("1.2."), f"Expected Pi 1.2, got {version}"
    builder = (package / "dist/core/system-prompt.js").as_uri()
    result = run_bun(f'''
      import fs from 'node:fs/promises';
      import registerMemory from './packages/continual-learning/extensions/inject-memory.ts';
      import {{registerGoalEvents}} from './packages/goal/src/events.ts';
      import {{normalizeGoalRecord}} from './packages/goal/src/record.ts';
      import {{normalizeBuildSystemPromptOptions,buildSystemPrompt}} from {json.dumps(builder)};
      const cwd={json.dumps(str(tmp_path / 'project'))};await fs.mkdir(cwd);
      const {{resolveMemoryPaths}}=await import('./packages/continual-learning/extensions/memory-paths.ts');
      const paths=resolveMemoryPaths(cwd);await fs.mkdir(paths.harnessDir,{{recursive:true}});
      await fs.writeFile(paths.harnessDir+'/fixture.md','---\\nname: fixture\\ndescription: DISCOVERY_MARKER\\ntype: project\\n---\\nBODY_NOT_INJECTED');
      const memoryHooks=new Map(); const goalHooks=new Map();
      const api=hooks=>({{on:(n,h)=>hooks.set(n,h),registerCommand(){{}},sendMessage(){{}},appendEntry(){{}},getCommands:()=>[],exec:async()=>({{stdout:'',stderr:'',code:0}})}});
      registerMemory(api(memoryHooks));
      let goal;
      registerGoalEvents({{pi:api(goalHooks),get goal(){{return goal}},acceptGoalSetting(){{}},settings:()=>({{}}),currentUnmet:()=>undefined}});
      const rows=[];
      for(const active of [false,true]) for(const reverse of [false,true]) for(const custom of [false,true]) {{
        goal=active?normalizeGoalRecord({{id:'fixture',objective:'ACTIVE_GOAL_MARKER',status:'active'}}):undefined;
        const options=normalizeBuildSystemPromptOptions({{cwd,contextFiles:[],skills:[],...(custom?{{customPrompt:'CUSTOM_OWNER'}}:{{}}),sections:{{fixture:'OTHER_SECTION'}}}});
        const event={{messageType:'custom',systemPromptOptions:options}};
        const handlers=[memoryHooks.get('before_agent_start'),goalHooks.get('before_agent_start')];
        if(reverse)handlers.reverse();
        const results=[];for(const handler of handlers)results.push(await handler(event,{{cwd,ui:{{notify(){{}}}}}}));
        const wire=buildSystemPrompt(options);
        rows.push({{active,reverse,custom,owner:wire.includes('CUSTOM_OWNER'),discovery:wire.includes('DISCOVERY_MARKER'),auto:wire.includes('After this user task settles'),body:wire.includes('BODY_NOT_INJECTED'),capability:wire.includes('[pi-goal capability]'),memory:wire.includes('Project Memory discovery'),state:wire.includes('ACTIVE_GOAL_MARKER'),forced:results.some(r=>r?.systemPrompt!==undefined),customInjection:results.some(r=>r?.message!==undefined),other:wire.includes('OTHER_SECTION'),forceOption:options.forceSystemPrompt!==undefined}});
      }}
      console.log(JSON.stringify(rows));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    assert len(result) == 8
    for row in result:
        assert row['capability'] and row['memory']
        assert row['state'] == row['active']
        assert not row['forced'] and not row['forceOption'] and not row['customInjection']
        assert row['other']
        assert row['owner'] == row['custom']
        assert row['discovery'] and row['auto'] and not row['body']

# --- Merged from test_run_start_section.py ---

def test_missing_sections_fails_clearly_without_mutating_guidelines():
    value = run_bun('''
      import {setRunStartSection} from './packages/continual-learning/extensions/run-start-section.ts';
      const rows=[];
      for(const sections of [undefined,null,[],"invalid"]) {
        const options={customPrompt:'OWNER',promptGuidelines:['KEEP'],...(sections===undefined?{}:{sections})};
        let error='';try {setRunStartSection(options,'required','GUIDANCE')} catch(e) {error=e.message}
        rows.push({error,options});
      }
      console.log(JSON.stringify(rows));
    ''')
    for row in value:
        assert row['error'] == 'Continual-learning requires Pi 1.2 structured prompt sections.'
        assert row['options']['promptGuidelines'] == ['KEEP']
        assert row['options']['customPrompt'] == 'OWNER'


# --- Merged from test_worker_model_preflight.py ---
from support import run_bun


def test_preflight_matches_only_the_exact_catalog_row_and_memoizes():
    result = run_bun(r'''
      import { catalogListsModel, createWorkerModelPreflight } from './packages/continual-learning/extensions/worker-model-preflight.ts';
      const table = [
        'provider       model                          context  max-out  thinking  images',
        'cliproxyapi    bailian/deepseek-v4-flash      1M       384K     yes       no',
        'cliproxyapi    gpt-6.1-sol                    256K     64K      yes       yes',
      ].join('\n');
      const calls = [];
      const preflight = createWorkerModelPreflight({
        timeoutMs: 2500,
        listModels: async (command, args, timeout) => { calls.push({ command, args: [...args], timeout }); return { stdout: table }; },
      });
      const exact = await preflight.check('cliproxyapi/bailian/deepseek-v4-flash');
      const repeated = await preflight.check('cliproxyapi/bailian/deepseek-v4-flash');
      const extensionOnly = await preflight.check('cli-proxy/bailian/qwen3.8-flash');
      const prefixOnly = await preflight.check('cliproxyapi/bailian/deepseek');
      const noSeparator = await preflight.check('gpt-6.1-sol');
      console.log(JSON.stringify({ exact, repeated, extensionOnly, prefixOnly, noSeparator,
        parser: { row: catalogListsModel(table, 'cliproxyapi/gpt-6.1-sol'), otherProvider: catalogListsModel(table, 'magpie/gpt-6.1-sol') },
        calls }));
    ''')
    assert result["exact"] is True
    assert result["repeated"] is True
    assert result["extensionOnly"] is False
    assert result["prefixOnly"] is False
    assert result["noSeparator"] is False
    assert result["parser"] == {"row": True, "otherProvider": False}
    # One list call per distinct model; repeats reuse the memoized answer.
    assert len(result["calls"]) == 4, result["calls"]
    for call in result["calls"]:
        # The child's own view: no extensions, then the catalog listing.
        assert call["args"][-2:] == ["-ne", "--list-models"], call
        assert call["timeout"] == 2500, call


def test_preflight_unknown_result_does_not_block_and_is_memoized():
    result = run_bun(r'''
      import { createWorkerModelPreflight } from './packages/continual-learning/extensions/worker-model-preflight.ts';
      let calls = 0;
      const preflight = createWorkerModelPreflight({ listModels: async () => { calls += 1; throw new Error('cli unavailable'); } });
      const first = await preflight.check('session/active');
      const second = await preflight.check('session/active');
      console.log(JSON.stringify({ first: first ?? null, second: second ?? null, calls }));
    ''')
    # An unavailable preflight reports "unknown", never a false block.
    assert result == {"first": None, "second": None, "calls": 1}
