from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def run_bun(source: str) -> dict:
    result = subprocess.run(["bun", "-e", source], cwd=REPO, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


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
      }));
    """)
    assert result["chat"]["memory"] is False
    assert result["chat"]["harness"] is False
    assert result["preference"]["memory"] is True
    assert result["constraint"]["harness"] is True
    assert result["agents"]["agents"] is True
    assert result["manual"] == {"memory": True, "harness": True, "agents": True, "reasons": ["manual-full"]}


def test_retry_economics_are_mode_and_phase_specific() -> None:
    result = run_bun("""
      import { shouldRetryPlanner } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const retry = (mode, phase, failure, attempt = 0, mutated = false) => shouldRetryPlanner({ mode, phase, failure, attempt, mutated });
      console.log(JSON.stringify({
        automaticMemorySyntax: retry('automatic', 'memory', 'syntax'),
        automaticMemoryValidation: retry('automatic', 'memory', 'validation'),
        automaticHarnessSyntax: retry('automatic', 'harness', 'syntax'),
        manualValidation: retry('manual', 'agents', 'validation'),
        model: retry('manual', 'memory', 'model'),
        timeout: retry('manual', 'memory', 'timeout'),
        secondAttempt: retry('manual', 'memory', 'syntax', 1),
        mutated: retry('manual', 'memory', 'syntax', 0, true),
      }));
    """)
    assert result == {
        "automaticMemorySyntax": True,
        "automaticMemoryValidation": False,
        "automaticHarnessSyntax": False,
        "manualValidation": True,
        "model": False,
        "timeout": False,
        "secondAttempt": False,
        "mutated": False,
    }


def test_receipt_reports_result_and_cost() -> None:
    result = run_bun("""
      import { buildLearningReceipt, formatLearningSummary } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const receipt = buildLearningReceipt('automatic', { memory: true, harness: false, agents: false, reasons: ['durable-user-evidence'] }, [
        { phase: 'memory', attempt: 0, outcome: 'applied', durationMs: 20, operations: 1, usage: { input: 10, output: 2, cacheRead: 3, cacheWrite: 0, totalTokens: 12, cost: 0.01 } },
      ]);
      console.log(JSON.stringify({ receipt, summary: formatLearningSummary(receipt) }));
    """)
    assert result["receipt"]["operations"] == 1
    assert result["receipt"]["totals"]["totalTokens"] == 12
    assert result["receipt"]["retries"] == 0
    assert "1 call(s)" in result["summary"]
    assert "12 token(s)" in result["summary"]


def test_usage_aggregation_includes_every_attempt() -> None:
    result = run_bun("""
      import { totalLearningUsage } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const usage = (input, output, cost) => ({ input, output, cacheRead: 2, cacheWrite: 1, totalTokens: input + output, cost });
      console.log(JSON.stringify(totalLearningUsage([
        { phase: 'explorer', attempt: 0, outcome: 'applied', durationMs: 10, operations: 0, usage: usage(10, 3, 0.01) },
        { phase: 'memory', attempt: 0, outcome: 'rejected', durationMs: 20, operations: 0, usage: usage(20, 4, 0.02) },
        { phase: 'memory', attempt: 1, outcome: 'applied', durationMs: 20, operations: 1, usage: usage(15, 5, 0.03) },
      ])));
    """)
    assert result == {"input": 45, "output": 12, "cacheRead": 6, "cacheWrite": 3, "totalTokens": 57, "cost": 0.06}
