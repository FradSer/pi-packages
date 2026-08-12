from __future__ import annotations

import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SKILLS = PACKAGE / "skills"


def frontmatter(text: str) -> str:
    parts = text.split("---", 2)
    assert len(parts) == 3
    return parts[1]


def test_manifest_declares_native_pi_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"]["skills"] == ["./skills"]


def test_both_registered_skills_have_skill_files() -> None:
    skills = sorted(SKILLS.glob("*/SKILL.md"))
    assert [skill.parent.name for skill in skills] == ["update-changelog", "update-readme"]


def test_supporting_references_remain_beside_skills() -> None:
    assert (SKILLS / "update-readme" / "references" / "template.md").is_file()
    assert (SKILLS / "update-changelog" / "references" / "keepachangelog-format.md").is_file()


def test_claude_only_artifacts_are_not_shipped() -> None:
    assert not (PACKAGE / ".claude-plugin").exists()
    assert not list(PACKAGE.rglob("plugin.json"))
    content = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.rglob("*.md"))
    for forbidden in ("allowed-tools:", "user-invocable:", "CLAUDE_PLUGIN_ROOT", "/utils:"):
        assert forbidden not in content

    for skill in SKILLS.glob("*/SKILL.md"):
        metadata = frontmatter(skill.read_text(encoding="utf-8"))
        assert "name:" in metadata
        assert "description:" in metadata
        assert "disable-model-invocation:" in metadata
