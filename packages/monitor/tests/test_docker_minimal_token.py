"""Grading never upgrades an incomplete compact monitor study into a pass."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path

LOCATION = Path(__file__).parent / "docker-study/minimal.py"
SPEC = importlib.util.spec_from_file_location("monitor_minimal_grade", LOCATION)
assert SPEC is not None and SPEC.loader is not None
GRADER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRADER)


def native_fixture() -> dict:
    return {
        "registered": ["monitor_start", "monitor_stop"],
        "commands": ["monitor"],
        "renderers": ["monitor-result"],
        "startBaseline": {"activeTools": ["monitor_start", "bash"], "setActiveCalls": 1},
        "headlessSuccess": {"status": "success", "resultStatus": "success",
            "monitorId": "monitor_1", "hasResult": True, "textBytes": 159, "stoppedBy": "match"},
        "exitJson": {"status": "success", "result": {"ok": True, "value": 7},
            "captures": {"json": '{"ok":true,"value":7}'}, "completion": "exit", "exitCode": 0},
        "failure": {"status": "failure", "stoppedBy": "failure_match", "matched": "FAIL_NOW"},
        "resultMissing": {"status": "result_missing", "exit": 0},
        "timeout": {"status": "timeout", "timeoutMs": 300},
        "asyncUi": {"status": "running", "terminate": True, "monitorId": "monitor_2",
            "activeTools": ["monitor_start", "bash", "monitor_stop"]},
        "asyncDelivery": {"sent": 1, "lastCustom": "monitor-result", "deliverAs": "steer",
            "trigger": True, "lastStatus": "success",
            "activeTools": ["monitor_start", "bash"], "widgets": 12},
        "stop": {"invalidRefused": True, "stopped": 1, "content": "Stopped 1 monitor(s)."},
        "guidance": {"section": ["monitor_policy"], "bytes": 643,
            "hasBash": True, "hasMonitor": True},
        "shutdown": {"activeTools": ["monitor_start", "bash"], "widgetsCleared": True},
    }


def fixture(root: Path, *, mutate=None, requests: int = 2, errors: int = 0,
            reasoning: str = "none") -> dict:
    native = native_fixture()
    if mutate:
        mutate(native)
    (root / "native.json").write_text(json.dumps(native))
    (root / "parent-tui.json").write_text(json.dumps({"markerObserved": True,
        "monitorRowObserved": True, "expandRepaintObserved": True,
        "resizeRepaintObserved": True}))
    return {"requests": requests, "transportErrors": errors, "piVersion": "1.5.0",
        "workspacePiVersions": {"kit": "1.5.0", "monitor": "1.5.0"},
        "modelObservations": [{"reasoningEffortOnWire": reasoning, "toolCount": 2}]
        * requests}


def test_compact_study_passes_only_with_all_native_and_real_model_contracts(tmp_path: Path) -> None:
    metadata = fixture(tmp_path)
    graded = GRADER.grade(tmp_path, metadata)
    assert graded["passed"] is True, [name for name, value in graded["checks"].items() if not value]
    assert graded["nativeInjectedBytes"] == 802


def test_missing_terminal_contract_reasoning_or_transport_health_fails_grading(tmp_path: Path) -> None:
    cases = [
        (lambda value: value["resultMissing"].update(status="success"), 2, 0, "none"),
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


def test_asynchronous_delivery_and_tool_disclosure_are_required(tmp_path: Path) -> None:
    for mutate in (
        lambda value: value["asyncDelivery"].update(deliverAs="followUp"),
        lambda value: value["asyncUi"].update(terminate=False),
    ):
        root = tmp_path / "case"
        root.mkdir(exist_ok=True)
        metadata = fixture(root, mutate=mutate)
        graded = GRADER.grade(root, metadata)
        assert graded["passed"] is False
        (root / "native.json").unlink()
