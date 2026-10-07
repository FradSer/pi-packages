from __future__ import annotations

import pytest

import live_docker_projects as workflow


def test_memory_failure_preserves_gate_and_runs_harness() -> None:
    # Given held Memory, When collecting independent effects, Then the safe
    # Harness callback runs, recall is missing, and the overall gate still fails.
    calls: list[str] = []
    report: dict = {"checks": {"regressionChanged": True}}

    def memory() -> None:
        calls.append("memory")
        raise AssertionError("No accepted Memory")

    def recall() -> None:
        calls.append("recall")

    def harness() -> None:
        calls.append("harness")
        report["checks"]["nativeBashBlocked"] = True

    with pytest.raises(AssertionError, match="memory"):
        workflow.observe_learning_effects(report, memory, recall, harness)
    assert calls == ["memory", "harness"]
    assert report["checks"]["nativeBashBlocked"] is True
    assert report["phaseObservations"]["memory"]["status"] == "failed"
    assert report["phaseObservations"]["recall"] == {
        "status": "unverified", "reason": "memory-prerequisite-failed",
    }
    assert report["phaseObservations"]["harness"]["status"] == "passed"


def test_recall_failure_does_not_mask_harness_failure() -> None:
    calls: list[str] = []
    report: dict = {}

    def memory() -> None:
        calls.append("memory")

    def recall() -> None:
        calls.append("recall")
        raise AssertionError("No observed full Memory read")

    def harness() -> None:
        calls.append("harness")
        raise AssertionError("No native Bash attempt")

    with pytest.raises(AssertionError, match="recall.*harness"):
        workflow.observe_learning_effects(report, memory, recall, harness)
    assert calls == ["memory", "recall", "harness"]
    assert [report["phaseObservations"][key]["status"] for key in calls] == [
        "passed", "failed", "failed",
    ]


def test_all_effects_pass_and_cancellation_is_not_swallowed() -> None:
    report: dict = {}
    calls: list[str] = []
    workflow.observe_learning_effects(
        report, lambda: calls.append("memory"), lambda: calls.append("recall"),
        lambda: calls.append("harness"),
    )
    assert calls == ["memory", "recall", "harness"]
    assert all(value["status"] == "passed" for value in report["phaseObservations"].values())

    def cancelled() -> None:
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        workflow.observe_learning_effects({}, cancelled, lambda: calls.append("unexpected"), lambda: calls.append("unexpected"))
    assert "unexpected" not in calls


def test_real_workflow_wiring_probes_harness_after_memory_gate_failure(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # This is an offline control-flow integration fixture, not model or native
    # hook quality evidence. No process or external request is dispatched.
    import json
    import os
    from pathlib import Path
    from types import SimpleNamespace

    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "memory.json").write_text('{"provider":"fixture","model":"offline"}')
    results = tmp_path / "results"
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(workflow, "AGENT", agent)
    monkeypatch.setattr(workflow, "RESULTS", results)
    real_path = Path

    def isolated_path(value):
        return {
            "/work": work,
            "/home/node/testbin": tmp_path / "testbin",
            "/home/node/baseline-agent": tmp_path / "baseline-agent",
        }.get(str(value), real_path(value))

    monkeypatch.setattr(workflow, "Path", isolated_path)
    monkeypatch.setattr(workflow, "source_digest", lambda: "fixture-digest")
    commit = next(x["commit"] for x in workflow.PROJECTS if x["name"] == "click")
    monkeypatch.setattr(workflow, "command", lambda args: commit if "rev-parse" in args else "fixture")
    monkeypatch.setattr(workflow, "checked", lambda *args: {"exitCode": 0})
    monkeypatch.setattr(workflow.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=""))
    calls: list[str] = []

    def run_pi(project, prompt, label, **kwargs):
        calls.append(label)
        if label == "learning":
            (project / "tests").mkdir()
            (project / "tests/test_testing.py").write_text("offline changed regression fixture")
            runs = agent / "memory/runs/scope/run"
            runs.mkdir(parents=True)
            (runs / "learning-pipeline-receipt.json").write_text(json.dumps({
                "attempts": [{"phase": "memory", "outcome": "proposed"},
                             {"phase": "harness", "outcome": "applied", "jev": {
                                 "stage": "harness", "status": "decided", "reason": "supported",
                                 "model": "jev-1.13.0", "inputTokens": 12,
                             }}],
            }))
            (project / ".pi").mkdir()
            (project / ".pi/harness.json").write_text('{"rules":[]}')
        elif label == "harness-enforcement":
            assert json.loads((agent / "memory/settings.json").read_text())["autoMemory"] is False
            wrapper = tmp_path / "testbin/git"
            assert wrapper.is_file() and 'if [ "$1" = push ]' in wrapper.read_text()
            assert 'exit 0' in wrapper.read_text()
            assert os.environ["PATH"].split(":")[0] == str(wrapper.parent)
        else:
            pytest.fail("Recall must not run without accepted Memory")
        return {"seconds": 0, "messages": []}

    monkeypatch.setattr(workflow, "run_pi", run_pi)
    monkeypatch.setattr(workflow, "matched_tool_results", lambda *args: [{"isError": True}])
    monkeypatch.setattr(workflow, "learned_block_result", lambda *args: True)
    monkeypatch.setattr(workflow, "successful_tool_call", lambda *args: True)
    # Restore the real process PATH after the fixture; the production callback
    # intentionally changes PATH only inside its disposable Docker process.
    monkeypatch.setenv("PATH", os.environ["PATH"])
    report = workflow.verify_container("click", "fixture-digest", "on")
    assert calls == ["learning", "harness-enforcement"]
    assert report["status"] == "failed"
    assert report["checks"]["nativeBashBlocked"] is True
    assert report["phaseObservations"]["memory"]["status"] == "failed"
    assert report["phaseObservations"]["recall"]["status"] == "unverified"
    assert report["phaseObservations"]["harness"]["status"] == "passed"
    assert "realJevParticipation" not in report["checks"]
    # Label justification: the memory attempt is "proposed" and carries no Jev
    # memory judgment, while the only Jev telemetry belongs to the harness phase.
    # The gate must separate "no memory candidate reached review" from "a memory
    # candidate was judged and unsupported", so it no longer reuses the
    # unsupported-judgment label when no memory review happened at all.
    assert report["phaseObservations"]["memory"]["failedCheck"] == "no-candidate-for-jev-review"


def test_arbitrary_sensitive_exception_text_is_not_serialized() -> None:
    import json
    report: dict = {}

    def secret_error() -> None:
        raise RuntimeError("private fixture text must not enter the report")

    with pytest.raises(AssertionError):
        workflow.observe_learning_effects(report, secret_error, lambda: None, lambda: None)
    assert "private fixture text" not in json.dumps(report)
    assert report["phaseObservations"]["memory"]["failedCheck"] == "phase-callback-error"


@pytest.mark.parametrize("jev_mode,harness_outcome,failed_check,other_failure", [
    ("off", "proposed", "harness-not-applied", None),
    ("on", "proposed", "harness-not-applied", None),
    ("on", "applied", "missing-supported-harness-judgment", None),
    ("off", "applied", None, ("selector", "failed")),
    ("off", "applied", None, ("agents", "cancelled")),
])
def test_held_harness_does_not_hide_applied_memory_recall(
    tmp_path, monkeypatch, jev_mode, harness_outcome, failed_check, other_failure,
) -> None:
    # Given applied Memory and proposed Harness, When the real workflow runs,
    # Then recall is observed independently while overall acceptance still fails.
    # Offline wiring only: every process and model dispatch is replaced.
    import hashlib
    import json
    from pathlib import Path
    from types import SimpleNamespace

    agent = tmp_path / "agent"
    agent.mkdir()
    for name in ("memory.json", "models.json", "settings.json"):
        (agent / name).write_text('{"provider":"fixture","model":"offline"}')
    results = tmp_path / "results"
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(workflow, "AGENT", agent)
    monkeypatch.setattr(workflow, "RESULTS", results)
    real_path = Path
    monkeypatch.setattr(workflow, "Path", lambda value: {
        "/work": work, "/home/node/testbin": tmp_path / "testbin",
        "/home/node/baseline-agent": tmp_path / "baseline-agent",
    }.get(str(value), real_path(value)))
    monkeypatch.setattr(workflow, "source_digest", lambda: "fixture-digest")
    commit = next(x["commit"] for x in workflow.PROJECTS if x["name"] == "click")
    marker = "PRIVATE_REPORT_" + hashlib.sha256(("click" + commit).encode()).hexdigest()[:12].upper()
    monkeypatch.setattr(workflow, "command", lambda args: commit if "rev-parse" in args else "fixture")
    monkeypatch.setattr(workflow, "checked", lambda *args: {"exitCode": 0})
    monkeypatch.setattr(workflow.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=""))
    calls = []

    def run_pi(project, prompt, label, **kwargs):
        calls.append(label)
        if label == "learning":
            (project / "tests").mkdir()
            (project / "tests/test_testing.py").write_text("offline changed regression fixture")
            runs = agent / "memory/runs/scope/run"
            runs.mkdir(parents=True)
            attempts = [
                {"phase": "memory", "outcome": "applied", "jev": {
                    "stage": "memory", "status": "decided", "reason": "supported",
                    "model": "jev-1.13.0", "inputTokens": 12,
                }},
                {"phase": "harness", "outcome": harness_outcome},
            ]
            if other_failure:
                attempts.append({"phase": other_failure[0], "outcome": other_failure[1]})
            (runs / "learning-pipeline-receipt.json").write_text(json.dumps({"attempts": attempts}))
            (project / ".pi").mkdir()
            (project / ".pi/harness.json").write_text('{"rules":[]}')
        return {"seconds": 0, "messages": [], "visible": marker}

    monkeypatch.setattr(workflow, "run_pi", run_pi)
    fact = "uv run --no-sync pytest -q"
    monkeypatch.setattr(workflow, "memory_bodies", lambda root: {"command.md": fact}
        if root.name == ".memory" else {"command.md": fact, "preference.md": marker})
    monkeypatch.setattr(workflow, "shared_surface_leaks", lambda *args: False)
    monkeypatch.setattr(workflow, "full_memory_read", lambda *args: True)
    monkeypatch.setattr(workflow, "matched_tool_results", lambda *args: [{"isError": True}])
    monkeypatch.setattr(workflow, "learned_block_result", lambda *args: True)
    monkeypatch.setattr(workflow, "successful_tool_call", lambda *args: True)
    monkeypatch.setenv("PATH", workflow.os.environ["PATH"])
    report = workflow.verify_container("click", "fixture-digest", jev_mode)
    assert report["phaseObservations"]["memory"]["status"] == "passed"
    assert report["phaseObservations"]["recall"]["status"] == "passed"
    assert "baseline-recall" in calls and "fresh-recall" in calls
    assert report["phaseObservations"]["harness"]["status"] == ("failed" if failed_check else "passed")
    if failed_check:
        assert report["phaseObservations"]["harness"]["failedCheck"] == failed_check
    assert "realJevParticipation" not in report["checks"]
    if jev_mode == "on":
        assert report["checks"]["realJevMemoryParticipation"] is True
    assert report["status"] == "failed"
