from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

PKG_DIR = Path(__file__).resolve().parents[1]
REPO = PKG_DIR.parents[1]


@pytest.fixture(params=["direct", "consolidation"])
def guidance(request: pytest.FixtureRequest) -> str:
    if request.param == "consolidation":
        return ' '.join((PKG_DIR / "prompts" / "harness-consolidator.md").read_text(encoding="utf-8").split())
    result = subprocess.run(
        ["bun", "-e", """
        import { buildHarnessRulePrompt } from './packages/continual-learning/extensions/guardrails.ts';
        console.log(JSON.stringify(buildHarnessRulePrompt(
          'Preserve business semantics when updating project documents',
          '/tmp/project/.pi/harness.local.json')));
        """],
        cwd=REPO, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


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
