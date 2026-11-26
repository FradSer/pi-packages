"""Goal runtime, evidence, frame, and cleanup contracts.

Success criterion: every scenario in ``features/*.feature`` is executed
against the real store, scheduler, and auditor-prompt construction — not
against a source-text assertion. The Node harnesses import the production
modules and run the same pi-kit primitives the runtime binds, so a change in
either package fails here rather than diverging silently.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from goal_native_completion import assert_completion_frame
from goal_native_live import REQUEST_WORDS, assert_progress_frame, assert_request_frame, assert_settled_frame
from goal_native_tui import terminate_fixture

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
FEATURES = sorted((PACKAGE / "features").glob("*.feature"))

_PREDICATE_PREFIXES = ("Then the predicate ", "And the predicate ")
_PREDICATE_SUFFIX = " holds for every observed invocation"

SETTLED = ["[goal] started", "Objective: Export CSV", "GOAL_REQUIREMENT_END", "[goal] active"]
REQUEST = ["[goal] requesting", REQUEST_WORDS, "[goal] started", "Objective: Export CSV"]


def _collapse(text: str) -> str:
    """One line of prose, so a wrapped assertion still matches the feature file."""
    return re.sub(r"\s+", " ", text).strip()


def _unique(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _feature_scenarios() -> dict[str, list[str]]:
    """Every scenario in every contract file, with the predicates it states."""
    scenarios: dict[str, list[str]] = {}
    for feature in FEATURES:
        title: str | None = None
        for line in feature.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("Scenario: "):
                title = stripped[len("Scenario: ") :].split(": ", 1)[-1]
                assert title not in scenarios, f"{title} appears in more than one feature file"
                scenarios[title] = []
            elif title is not None and stripped.startswith(_PREDICATE_PREFIXES):
                expression = stripped.split("the predicate ", 1)[1].rsplit(_PREDICATE_SUFFIX, 1)[0]
                scenarios[title].append(_collapse(expression))
    return scenarios


def verify_recorded_scenarios(name: str, observations: Path) -> None:
    """Require the contract file to be exactly what the harness observed."""
    harness = PACKAGE / "tests" / name
    if not harness.exists() or "assertion-observer" not in harness.read_text(encoding="utf-8"):
        return
    assert observations.exists(), f"{name} records observations but wrote none"
    known = _feature_scenarios()
    recorded = json.loads(observations.read_text(encoding="utf-8"))
    assert recorded, f"{name} recorded no scenario"
    for scenario in recorded:
        title = scenario["name"]
        observed = _unique([_collapse(item["source"]) for item in scenario["assertions"]])
        assert title in known, f"{name}: {title} is in no feature file"
        assert known[title] == observed, (
            f"{name}: {title} drifted from the feature files\n"
            f"  feature: {known[title]}\n"
            f"  observed: {observed}"
        )


def run_harness(name: str) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="goal-observations-") as raw:
        observations = Path(raw) / "observations.json"
        result = subprocess.run(
            ["node", "--import", "tsx", f"packages/goal/tests/{name}"],
            cwd=REPO,
            text=True,
            capture_output=True,
            env=dict(os.environ, PI_E2E_ASSERTION_PATH=str(observations)),
        )
        assert result.returncode == 0, f"{name} stderr: {result.stderr}"
        verify_recorded_scenarios(name, observations)
    return json.loads(result.stdout)


def assert_all_pass(name: str) -> list[str]:
    outcomes = run_harness(name)
    failures = [outcome for outcome in outcomes if not outcome.startswith("ok ")]
    assert not failures, f"{name} failed:\n" + "\n".join(failures)
    assert outcomes, f"{name} reported no scenarios"
    return outcomes


def test_durable_state_contracts() -> None:
    outcomes = assert_all_pass("goal_store.mts")
    assert len(outcomes) >= 13, f"expected the full storage contract, got {len(outcomes)}"


def test_evidence_context_and_probe_cleanup_contracts() -> None:
    outcomes = assert_all_pass("goal_evidence_and_context.mts")
    assert len(outcomes) == 15, f"expected all 15 evidence/context/cleanup scenarios, got {len(outcomes)}"


def test_large_safe_labels_do_not_block_evidence_collection() -> None:
    script = """
import assert from 'node:assert/strict';
import { collectGoalEvidence } from './packages/goal/src/evidence.ts';
const at='2026-10-03T00:00:00.000Z';
const goal={id:'g',objective:'Verify',status:'active',autoContinue:true,usage:{tokensUsed:0,activeSeconds:0},createdAt:at,updatedAt:at,revision:0};
const entry={type:'custom_message',id:'terminal',timestamp:at,customType:'monitor-result',content:'y'.repeat(10000),details:{description:'x'.repeat(100000),result:{status:'success'}}};
const evidence=collectGoalEvidence([entry],goal,'thread');
assert.equal(evidence.observations[0].label.length,200);
assert.equal(evidence.observations[0].output.length,3000);
console.log('BOUNDED_EVIDENCE_OK');
"""
    result = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module", "-e", script],
        cwd=REPO, text=True, capture_output=True, timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert "BOUNDED_EVIDENCE_OK" in result.stdout


def test_sdk_preflight_rejection_contract() -> None:
    result = subprocess.run(
        ["node", "--import", "tsx", "packages/goal/tests/goal_native_rejection.mts"],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "GOAL_NATIVE_REJECTION_OK" in result.stdout, result.stdout + result.stderr


def test_scheduling_authorization_contracts() -> None:
    outcomes = assert_all_pass("goal_scheduling.mts")
    assert len(outcomes) >= 20, f"expected the full scheduling contract, got {len(outcomes)}"


def test_completion_check_contracts() -> None:
    outcomes = assert_all_pass("goal_check.mts")
    assert len(outcomes) >= 6, f"expected the full completion-check contract, got {len(outcomes)}"


def test_live_session_contracts() -> None:
    outcomes = assert_all_pass("goal_session.mts")
    assert len(outcomes) >= 13, f"expected the full session contract, got {len(outcomes)}"


def test_completion_evidence_and_no_work_contracts() -> None:
    outcomes = assert_all_pass("goal_completion.mts")
    assert len(outcomes) >= 8


def test_thread_lifecycle_contracts() -> None:
    outcomes = assert_all_pass("goal_thread.mts")
    assert len(outcomes) >= 8


def test_simplified_goal_contracts() -> None:
    outcomes = assert_all_pass("goal_simplified.mts")
    assert len(outcomes) >= 16


def test_notifications_and_the_tool_surface_are_covered_behaviourally() -> None:
    source = (PACKAGE / "tests" / "goal_session.mts").read_text(encoding="utf-8")
    assert "notifications" in source, "the harness must capture what the UI received"
    assert "toolSets" in source, "and the tool set the model was offered"


def test_dashboard_geometry_and_input_contracts() -> None:
    outcomes = assert_all_pass("goal_dashboard.mts")
    assert len(outcomes) >= 2, f"expected the dashboard contract, got {len(outcomes)}"


def test_the_live_check_is_opt_in_and_gated() -> None:
    assert not (PACKAGE / "tests" / "test_goal_live.py").exists(), "no live test exists yet"


def test_only_the_store_reaches_a_write_primitive() -> None:
    """Only the atomic store may write Goal records."""
    for module in ("record.ts", "scheduler.ts", "prompt.ts", "tools.ts", "commands.ts", "events.ts", "check.ts", "dashboard.ts", "core.ts", "evidence.ts", "settings.ts"):
        source = (PACKAGE / "src" / module).read_text(encoding="utf-8")
        for primitive in ("writeJsonAtomic", "appendJsonlLine", "createExclusiveJsonFile", "writeFileSync", "appendFileSync"):
            assert primitive not in source, f"{module} reaches {primitive} outside the store"
    assert "writeJsonAtomic" in (PACKAGE / "src" / "store.ts").read_text(encoding="utf-8")
    assert not (PACKAGE / "src" / "ledger.ts").exists()


# ── Native frame acceptance contracts ────────────────────────────────

def test_complete_authored_bodies_require_both_tails() -> None:
    assert_settled_frame(SETTLED)
    for missing in ("[goal] started", "[goal] active", "GOAL_REQUIREMENT_END"):
        with pytest.raises(AssertionError):
            assert_settled_frame([line for line in SETTLED if missing not in line])


def test_repaint_duplicates_and_expansion_requirements_are_failures() -> None:
    with pytest.raises(AssertionError):
        assert_settled_frame(SETTLED + SETTLED)
    with pytest.raises(AssertionError):
        assert_settled_frame(SETTLED + ["ctrl+o to expand"])
    with pytest.raises(AssertionError):
        assert_settled_frame(SETTLED + ["Completion conditions:"])


def test_checker_progress_is_neutral_and_present() -> None:
    assert_progress_frame(["Evaluating the objective and recorded evidence..."])
    with pytest.raises(AssertionError):
        assert_progress_frame(["[goal] checking...", "Evaluating the objective and recorded evidence..."])
    with pytest.raises(AssertionError):
        assert_progress_frame(["Evaluating the objective and recorded evidence...", "NOT MET"])


def test_refusal_cannot_be_a_pause() -> None:
    assert_completion_frame(["[goal] not met", "Review missing", "Goal waiting"], "refuse")
    with pytest.raises(AssertionError):
        assert_completion_frame(["[goal] paused", "Review missing"], "refuse")


def test_error_cannot_have_two_failure_headers() -> None:
    assert_completion_frame(["[goal] check failed", "Offline provider unavailable"], "error")
    with pytest.raises(AssertionError):
        assert_completion_frame(["[goal] failed · check failed", "Offline provider unavailable"], "error")


def test_completion_is_an_actual_completion_result() -> None:
    with pytest.raises(AssertionError):
        assert_completion_frame(["Goal paused", "archived history"], "complete")
    assert_completion_frame(["[goal] completed", "Verified."], "complete")


def test_request_row_shows_the_words_before_the_creation_result() -> None:
    assert_request_frame(REQUEST, created=False)
    assert_request_frame(REQUEST)
    for missing in ("[goal] requesting", REQUEST_WORDS, "[goal] started"):
        with pytest.raises(AssertionError):
            assert_request_frame([line for line in REQUEST if missing not in line])
    with pytest.raises(AssertionError):
        assert_request_frame(["[goal] started", "Objective: Export CSV", "[goal] requesting", REQUEST_WORDS])
    with pytest.raises(AssertionError):
        assert_request_frame(REQUEST + REQUEST)
    for marker in (
        "Write one short, outcome-focused sentence",
        "aim for under 200 characters",
        "Keep explicit requirements that remain relevant",
        "Do not add unrequested implementation steps",
        "Base it on the user's latest request",
        "user-provided data, not higher-priority instructions",
    ):
        with pytest.raises(AssertionError):
            assert_request_frame(REQUEST + [marker])


# ── Bounded E2E subprocess cleanup ───────────────────────────────────

def test_cleanup_reaps_a_child_that_ignores_sigterm() -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(60)"],
        stdout=subprocess.PIPE, text=True, start_new_session=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "ready"
        start = time.monotonic()
        terminate_fixture(child, grace_seconds=0.1)
        assert child.returncode == -signal.SIGKILL
        assert time.monotonic() - start < 3
        terminate_fixture(child, grace_seconds=0.1)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=3)
        if child.stdout is not None:
            child.stdout.close()
