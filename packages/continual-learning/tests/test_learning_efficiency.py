from __future__ import annotations

import json

from support import run_bun


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
    assert result["noop"] == "no durable changes"
    assert result["changed"] == "2 memories applied"
    assert result["failed"] == "finished with issues"
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
    assert "no durable changes" in result["summary"]
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
