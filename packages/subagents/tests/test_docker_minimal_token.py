"""Grading never upgrades an incomplete compact study into a pass."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path

LOCATION = Path(__file__).parent / "docker-study/minimal.py"
SPEC = importlib.util.spec_from_file_location("docker_minimal_grade", LOCATION)
assert SPEC is not None and SPEC.loader is not None
GRADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRADER)


def fixture(root: Path, *, complete: bool, reasoning: bool, errors: int = 0, tokens: bool = True) -> dict:
    study = {"model": "magpie-hy4/hunyuan-eval/hy4-dev", "piVersion": "1.5.0",
        "completed": complete, "finalRoster": [{"name": "resident", "status": "stopped"}],
        "temporary": {"first": {"kind": "result", "text": "FIRST_OK", "usage": {"input": 1, "output": 1, "totalTokens": 2}},
            "second": {"kind": "result", "text": "SECOND_OK"}, "idle": "idle",
            "stop": {"ok": True}, "stale": {"ok": False}},
        "saved": {"started": {"ok": True}, "notice": {"kind": "result"},
            "restart": {"notice": {"kind": "result"}}},
        "invalidIdentity": {"ok": False}, "identityWithInstructions": {"ok": False},
        "readonly": {"notice": {"kind": "result"}, "proposals": ["candidate.md"]},
        "writer": {"first": {"kind": "result"}, "second": {"kind": "result"},
            "memoryFiles": [{"file": "contract.md", "body": "entry"}]}}
    notices = [study["temporary"]["first"]]
    receipts = [{"name": name} for name in ("agent_start", "agent_input", "agent_stop", "agent_list")]
    (root / "study.json").write_text(json.dumps(study))
    (root / "notices.jsonl").write_text("\n".join(json.dumps(n) for n in notices) + "\n")
    (root / "receipts.json").write_text(json.dumps(receipts))
    (root / "spawns.json").write_text("[]")
    (root / "child-1.jsonl").write_text("\n".join(json.dumps(event) for event in (
        {"event": "system", "memory": "index"},
        {"event": "result", "tool": "agent_memory", "id": "a", "error": True},
        {"event": "result", "tool": "agent_memory", "id": "b", "error": False})) + "\n")
    (root / "parent-tui.json").write_text(json.dumps({"markerObserved": True,
        "expandRepaintObserved": True, "resizeRepaintObserved": True}))
    metadata = {"requests": 1, "transportErrors": errors,
        "modelObservations": [{"reasoningEffortOnWire": "none" if reasoning else "low", "toolCount": 0}]}
    return metadata


def test_compact_study_passes_only_with_all_contracts_and_reasoning_off(tmp_path: Path) -> None:
    metadata = fixture(tmp_path, complete=True, reasoning=True)
    assert GRADER.grade(tmp_path, metadata)["passed"] is True


def test_missing_completion_reasoning_or_transport_health_fails_grading(tmp_path: Path) -> None:
    for complete, reasoning, errors in ((False, True, 0), (True, False, 0), (True, True, 1)):
        root = tmp_path / f"case-{complete}-{reasoning}-{errors}"
        root.mkdir()
        metadata = fixture(root, complete=complete, reasoning=reasoning, errors=errors)
        graded = GRADER.grade(root, metadata)
        assert graded["passed"] is False, (complete, reasoning, errors)
        failed = [name for name, passed in graded["checks"].items() if not passed]
        assert failed


def test_unpriced_result_notice_never_counts_as_measured_tokens(tmp_path: Path) -> None:
    metadata = fixture(tmp_path, complete=True, reasoning=True)
    (tmp_path / "notices.jsonl").write_text(json.dumps({"kind": "result", "text": "FIRST_OK"}) + "\n")
    graded = GRADER.grade(tmp_path, metadata)
    assert graded["checks"]["tokenUsageObserved"] is False
    assert graded["passed"] is False
