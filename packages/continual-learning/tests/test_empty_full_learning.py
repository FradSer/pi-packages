from __future__ import annotations

from support import run_bun_script, PKG_DIR, run_bun


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
