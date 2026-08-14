from __future__ import annotations

import json
import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SKILLS = PACKAGE / "skills"


def test_manifest_declares_native_pi_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text())
    assert "pi-package" in manifest["keywords"]
    assert manifest["pi"]["skills"] == ["./skills/engineering", "./skills/productivity"]
    assert f"**Package version:** {manifest['version']}" in (PACKAGE / "README.md").read_text()


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


def test_cross_skill_handoff_reference_uses_pi_skill_invocation() -> None:
    content = "\n".join(path.read_text() for path in SKILLS.rglob("*.md"))
    assert not re.findall(r"(?<![\w.:-])/handoff\b", content)
    assert "`/skill:handoff`" in content


def test_handoff_writes_only_a_portable_document() -> None:
    handoff = (SKILLS / "productivity" / "handoff" / "SKILL.md").read_text()
    phase_boundaries = (SKILLS / "engineering" / "ask-matt" / "PHASE-BOUNDARIES.md").read_text()
    ask_matt = (SKILLS / "engineering" / "ask-matt" / "SKILL.md").read_text()
    productivity_readme = (SKILLS / "productivity" / "README.md").read_text()
    content = "\n".join(path.read_text() for path in PACKAGE.rglob("*.md"))

    assert "only writes the document" in handoff
    assert "does not create, fork, or seed a session" in handoff
    assert "does not create, fork, or seed a session" in phase_boundaries
    assert "does not create, fork, or seed a session" in ask_matt
    assert "does not create the session" in productivity_readme
    for stale_instruction in (
        "seed a session anywhere with it",
        "`/skill:handoff` forks",
    ):
        assert stale_instruction not in content


def test_readme_does_not_claim_an_unpublished_npm_release() -> None:
    readme = (PACKAGE / "README.md").read_text()
    assert "# published" not in readme
    assert "has not yet been released to npm" in readme
    assert "pi install /path/to/pi-packages/packages/mattpocock" in readme


def test_skills_use_native_pi_interaction_and_collaboration() -> None:
    content = "\n".join(p.read_text() for p in SKILLS.rglob("*.md"))
    forbidden = (
        "ask-the-user",
        "use the ask the user",
        "via the ask the user",
        "the ask the user",
        "built-in \"Other\"",
        "tool's \"Other\" field",
        "two `Agent` tool calls",
        "Agent tool calls",
        "isolated context",
        "isolated-context",
        "`/clear`",
    )
    for pattern in forbidden:
        assert pattern not in content

    assert "ask directly in the conversation" in content
    assert "wait for the reply" in content
    assert "teammate facility is available" in content


def test_skills_follow_project_instruction_and_commit_conventions() -> None:
    content = "\n".join(p.read_text() for p in SKILLS.rglob("*.md"))
    assert "If `AGENTS.md` exists, edit it." in content
    assert "Else if `CLAUDE.md` exists, edit it." in content
    assert "git-agent workflow" in content

    for forbidden in (
        "git add ",
        "git commit ",
        "Commit your work to the current branch.",
        "Stage everything and commit.",
        "commit it to a throwaway branch",
        "Commit it only when",
    ):
        assert forbidden not in content
