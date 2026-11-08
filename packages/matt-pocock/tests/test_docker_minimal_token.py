"""Grading never upgrades an incomplete compact study into a pass."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path

LOCATION = Path(__file__).parent / "docker-study/minimal.py"
SPEC = importlib.util.spec_from_file_location("matt_minimal_grade", LOCATION)
assert SPEC is not None and SPEC.loader is not None
GRADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRADER)


def native_fixture() -> dict:
    return {
        "registered": ["matt_pocock_active", "matt_pocock_ask", "matt_pocock_workflow"],
        "commands": ["matt-pocock"],
        "workflowCommand": {"route": "hard-bug", "procedure": "diagnosing-bugs", "status": "active",
            "request": "Fix receipt quantity", "hasStateContract": True, "textBytes": 100},
        "workflowState": {"status": "active", "workItemId": "item-1"},
        "restore": {"persistedRecordsAdded": 0,
            "activeTools": ["matt_pocock_workflow", "matt_pocock_active", "matt_pocock_ask"]},
        "transition": {"procedure": "implement", "hasStateContract": True,
            "parameters": ["action", "target", "reference", "reason"], "textBytes": 100},
        "ask": {"pending": True, "source": "no_ui"},
        "completed": {"status": "completed", "workItemId": "item-1",
            "activeTools": ["matt_pocock_workflow"]},
        "capability": {"mode": "capability", "hasSource": True, "textBytes": 100},
        "userCapability": {"mode": "user-capability", "textBytes": 100},
        "reference": {"mode": "reference", "hasHeading": True, "textBytes": 100},
        "invalidCapabilityRefused": True,
        "workflowReference": {"action": "load", "textBytes": 100},
        "cancelled": {"status": "cancelled", "reason": "done",
            "activeTools": ["matt_pocock_workflow"]},
        "unknownRouting": {"customType": "matt-pocock-procedure", "textHasRouting": True},
    }


def fixture(root: Path, *, mutate=None, requests: int = 2, errors: int = 0,
            reasoning: str = "none") -> dict:
    native = native_fixture()
    if mutate:
        mutate(native)
    (root / "native.json").write_text(json.dumps(native))
    (root / "parent-tui.json").write_text(json.dumps({"markerObserved": True,
        "gatewayRowObserved": True, "expandRepaintObserved": True, "resizeRepaintObserved": True}))
    return {"requests": requests, "transportErrors": errors, "piVersion": "1.5.0",
        "workspacePiVersions": {"kit": "1.5.0", "matt-pocock": "1.5.0"},
        "modelObservations": [{"reasoningEffortOnWire": reasoning, "toolCount": 2}]
        * requests}


def test_compact_study_passes_only_with_all_native_and_real_model_contracts(tmp_path: Path) -> None:
    metadata = fixture(tmp_path)
    graded = GRADER.grade(tmp_path, metadata)
    assert graded["passed"] is True, [name for name, value in graded["checks"].items() if not value]
    assert graded["nativeInjectedBytes"] == 600


def test_missing_workflow_state_reasoning_or_transport_health_fails_grading(tmp_path: Path) -> None:
    cases = [
        (lambda value: value["workflowState"].update(status="cancelled"), 2, 0, "none"),
        (None, 2, 0, "low"),
        (None, 2, 1, "none"),
        (None, 0, 0, "none"),
    ]
    for index, (mutate, requests, errors, reasoning) in enumerate(cases):
        root = tmp_path / f"case-{index}"
        root.mkdir()
        metadata = fixture(root, mutate=mutate, requests=requests,
            errors=errors, reasoning=reasoning)
        graded = GRADER.grade(root, metadata)
        assert graded["passed"] is False, index
        assert [name for name, value in graded["checks"].items() if not value]


def test_crossover_capability_refusal_is_required(tmp_path: Path) -> None:
    metadata = fixture(tmp_path,
        mutate=lambda value: value.update(invalidCapabilityRefused=False))
    graded = GRADER.grade(tmp_path, metadata)
    assert graded["checks"]["invalidCrossoverRefused"] is False
    assert graded["passed"] is False
