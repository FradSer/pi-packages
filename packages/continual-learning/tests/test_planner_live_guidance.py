"""No live planner prompt may instruct a child to call a retired tool."""
from __future__ import annotations

from pathlib import Path

from support import PKG_DIR

# The literal survives in frozen fixtures, the six frozen proofs, evidence
# parsers (TOOL_NAMES.learningRead), and the retained dynamic collector's
# own live prompt (which still legitimately has a learning_read tool).
ALLOWLISTED = {"memory-maintenance-audit.ts"}


def test_live_planner_prompts_never_name_a_deleted_worker_tool() -> None:
    roots = [
        PKG_DIR / "prompts",
        PKG_DIR / "extensions",
    ]
    files = [path for root in roots for path in root.rglob("*") if path.is_file()]
    offenders: list[str] = []
    for path in files:
        if path.name in ALLOWLISTED:
            continue
        if path.suffix not in {".md", ".ts"}:
            continue
        text = path.read_text(encoding="utf-8")
        # `harness_check_cases` no longer exists as a tool anywhere in live
        # production text; `learning_read` survives only as an evidence-marker
        # comparison (TOOL_NAMES.learningRead) or a frozen fixture, never as a
        # callable-tool instruction in a planner prompt.
        if path.suffix == ".md":
            if "harness_check_cases" in text or "learning_read" in text:
                offenders.append(str(path))
    assert offenders == [], offenders


def test_collector_keeps_its_own_scoped_read_tool() -> None:
    # The dynamic current-source collector is deliberately NOT migrated: its
    # live prompt still names learning_read and its registration survives.
    collector = (PKG_DIR / "extensions" / "memory-maintenance-audit.ts").read_text(encoding="utf-8")
    assert "Use learning_read only" in collector
    registration = (PKG_DIR / "extensions" / "planner-read-scope.ts").read_text(encoding="utf-8")
    assert "export function registerPlannerRead" in registration
    assert "name: TOOL_NAMES.learningRead" in registration


def test_tool_bearing_diagnostics_do_not_inject_the_no_tools_system_prompt() -> None:
    # Two opt-in diagnostics grant tools (learning_read / read,grep,find,ls).
    # planner-system.md now describes the no-tools planner contract, so those
    # runners must use their own scoped system prompt instead of injecting it.
    for filename in ("live_harness_repair_diagnostic.py", "live_harness_binding_repair.py"):
        source = (PKG_DIR / "tests" / filename).read_text(encoding="utf-8")
        assert "planner-system.md" not in source, filename
        assert "--tools" in source, filename
        assert "isolated, read-only diagnostic worker" in source, filename
        assert "no tools are available" not in source, filename
