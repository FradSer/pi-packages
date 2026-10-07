from __future__ import annotations

import pytest

from support import PKG_DIR, run_bun


@pytest.fixture(params=["direct", "consolidation"])
def guidance(request: pytest.FixtureRequest) -> str:
    if request.param == "consolidation":
        return ' '.join((PKG_DIR / "prompts" / "harness-consolidator.md").read_text(encoding="utf-8").split())
    return run_bun("""
        import { buildHarnessRulePrompt } from './packages/continual-learning/extensions/guardrails.ts';
        console.log(JSON.stringify(buildHarnessRulePrompt(
          'Preserve business semantics when updating project documents',
          '/tmp/project/.pi/harness.local.json')));
        """)


def test_guidance_generalizes_evidence_before_selecting_mechanism(guidance: str) -> None:
    assert "evidence -> reusable error class -> supported mechanism" in guidance
    assert "document tokens, row numbers, or verbatim phrases" in guidance
    assert "explicit resource-specific user requirement" in guidance
    assert "another same-kind document" in guidance
    assert "rephrasing" in guidance
    assert "unrelated actions remain allowed" in guidance
    assert any(text in guidance for text in ("keeping confirmation scoped to the requested action surface", "blanket confirmation of all writes"))


def test_semantic_guidance_does_not_claim_universal_enforcement(guidance: str) -> None:
    # Only the flat skill-rule guidance surface remains.
    assert "skill rule" in guidance
    # Registered/available-skill discipline (wording differs across the two surfaces).
    assert any(text in guidance for text in ("registered skill", "available skill", "invent a skill"))
    assert "expanded skill invocation" in guidance
    assert "plain read of SKILL.md" in guidance
    assert "not global interception" in guidance
    assert "report the limitation" in guidance.lower()
    assert any(text in guidance for text in ("preserve existing rules unchanged", "do not add a rule"))


def test_consolidation_does_not_claim_bare_git_matcher_covers_global_options() -> None:
    # Given a whole-family authorization, when generating a restriction, retain
    # legitimate global-option positives instead of weakening the test cases.
    prompt = (PKG_DIR / "prompts" / "harness-consolidator.md").read_text()
    assert "git -C . push --dry-run" in prompt
    assert "git --no-pager push --dry-run" in prompt
    assert "does not establish whole-family coverage" in prompt
    assert "Do not delete valid positive cases" in prompt
    assert "echo git -C . push --dry-run" in prompt


def test_git_template_preserves_bounded_coverage_and_requires_authorization() -> None:
    prompt = (PKG_DIR / 'prompts' / 'harness-consolidator.md').read_text(encoding='utf-8')
    assert r'^git(?:[ \t]+(?:-C[ \t]+\.|-c[ \t]+core\.quotePath=false|--no-pager))*[ \t]+push(?:[ \t]|$(?![\s\S]))' in prompt
    assert 'only a bounded subset of Git invocations' in prompt
    assert 'never infer authorization from the template' in prompt
