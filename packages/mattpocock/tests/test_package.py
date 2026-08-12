from __future__ import annotations

import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SKILLS = PACKAGE / "skills"


def test_manifest_declares_native_pi_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text())
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"]["skills"] == ["./skills/engineering", "./skills/productivity"]


def test_all_registered_skills_have_skill_files() -> None:
    skills = sorted(SKILLS.rglob("SKILL.md"))
    assert len(skills) == 27
    for skill in skills:
        text = skill.read_text()
        assert "name:" in text.split("---", 2)[1]
        assert "description:" in text.split("---", 2)[1]


def test_claude_only_artifacts_are_not_shipped() -> None:
    assert not list(PACKAGE.rglob("openai.yaml"))
    content = "\n".join(p.read_text() for p in PACKAGE.rglob("*.md"))
    for forbidden in ("CLAUDE_PLUGIN_ROOT", "/mattpocock:", "/superdev:", "AskUserQuestion"):
        assert forbidden not in content
