"""Goal runtime contracts.

Success criterion: every scenario in ``features/goal.feature`` is executed
against the real store, scheduler, and auditor-prompt construction — not
against a source-text assertion. The Node harnesses import the production
modules and run the same pi-kit primitives the runtime binds, so a change in
either package fails here rather than diverging silently.

The harnesses print one JSON line of ``ok``/``FAIL`` results. A failing scenario
therefore reports by name, which is what makes a regression readable in CI.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
FEATURES = sorted((PACKAGE / "features").glob("*.feature"))

_PREDICATE_PREFIXES = ("Then the predicate ", "And the predicate ")
_PREDICATE_SUFFIX = " holds for every observed invocation"


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
    """Every scenario in every contract file, with the predicates it states.

    A short title must be unique across the files: two scenarios with the same
    title would otherwise silently share whichever predicates were read last.
    """
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
    """Require the contract file to be exactly what the harness observed.

    A scenario the harness runs but the file does not state is a contract nobody
    wrote down; a predicate that differs is a contract that drifted. Both used to
    be invisible: the file is prose, and nothing compared it with the run.
    """
    harness = PACKAGE / "tests" / name
    if not harness.exists() or "assertion-observer" not in harness.read_text(encoding="utf-8"):
        return  # This harness does not record observations.
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
            f"  feature: {known[title]}\n  observed: {observed}"
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
    """Atomic records, revision conflicts, safe paths and legacy preservation."""
    outcomes = assert_all_pass("goal_store.mts")
    assert len(outcomes) >= 13, f"expected the full storage contract, got {len(outcomes)}"


def test_probe_cleanup_observations() -> None:
    assert_all_pass("goal_probe_cleanup.mts")


def test_sdk_preflight_rejection_contract() -> None:
    """A refused completion while a turn settles must not activate a paused revision.

    This harness runs the real agent session rather than a stub, and it records no
    frame observations, so it is driven directly and its marker is the assertion.
    """
    result = subprocess.run(
        ["node", "--import", "tsx", "packages/goal/tests/goal_native_rejection.mts"],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "GOAL_NATIVE_REJECTION_OK" in result.stdout, result.stdout + result.stderr


def test_scheduling_authorization_contracts() -> None:
    """Claim, dispatch, generations, waits, allowances, and the stop guard.

    Covers the "Scheduling authorization" and "Prompt stability" feature blocks.
    """
    outcomes = assert_all_pass("goal_scheduling.mts")
    assert len(outcomes) >= 20, f"expected the full scheduling contract, got {len(outcomes)}"


def test_run_start_injection_contracts() -> None:
    """Confirmed contract: one run-start contribution, no per-request replay."""
    outcomes = assert_all_pass("goal_live_context.mts")
    assert len(outcomes) == 3, f"expected all run-start scenarios, got {len(outcomes)}"


def test_completion_check_contracts() -> None:
    """One model, no tools, one answer.

    The empty tool grant is the whole guarantee: the child cannot read the
    repository, run the tests, or change anything, so "never modify the work"
    is enforced rather than instructed. Also pinned: the trailing-marker rule, the
    untrusted claim, delimiter safety, and the subprocess boundaries.
    """
    outcomes = assert_all_pass("goal_check.mts")
    assert len(outcomes) >= 6, f"expected the full completion-check contract, got {len(outcomes)}"


def test_live_session_contracts() -> None:
    """The layer that talks to Pi, driven by a real session and a scripted model.

    Everything above this is pure logic and runs without a host. These scenarios
    are the ones that only fail inside one: whether the tools are actually
    registered and gated by lifecycle, whether a completion request really runs
    the auditor and releases the open record, and whether a task list set in one tool call
    is immediately usable by the next. The auditor is injected, so each scenario
    decides the verdict and then asserts on what the goal did about it.

    Covers the "Completion verification" and "Work tools stop the turn" blocks of
    features/goal.feature.
    """
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
    """The session harness must actually observe the two pi-kit surfaces.

    These were previously asserted by reading the source for `notifyPi` and
    `setOwnedTools`, which proved that a helper name appeared in a file and
    nothing about whether a person ever saw a message or whether the model ever
    got the tools. `goal_session.mts` now captures what the UI received and the
    tool set the model was given, so the assertions live there. This check exists
    only to stop those scenarios from being deleted.
    """
    source = (PACKAGE / "tests" / "goal_session.mts").read_text(encoding="utf-8")
    assert "notifications" in source, "the harness must capture what the UI received"
    assert "toolSets" in source, "and the tool set the model was offered"


def test_dashboard_geometry_and_input_contracts() -> None:
    """The panel must fit real widths and own its own keys.

    A panel that overruns its width or emits half an ANSI sequence is broken the
    same way whether a TTY or a test drew it, so the widths here are the ones the
    extension claims to support. Key assertions send what a terminal actually
    sends, because matchesKey compares raw byte sequences, not key names.
    """
    outcomes = assert_all_pass("goal_dashboard.mts")
    # The expanded panel is retired: the surface is one passive row plus the
    # elapsed contract, so the dashboard suite is these two scenarios.
    assert len(outcomes) >= 2, f"expected the dashboard contract, got {len(outcomes)}"



def test_the_live_check_is_opt_in_and_gated() -> None:
    """Reserved for a live run against the real pi binary.

    There is no such test today: the completion check is one tool-less completion,
    and running it for real spends a model call to learn nothing a stand-in CLI
    does not already pin. When one is added it must be gated, because a live test
    that starts running in CI is a surprise with a bill attached.
    """
    assert not (PACKAGE / "tests" / "test_goal_live.py").exists(), "no live test exists yet"


def test_only_the_store_reaches_a_write_primitive() -> None:
    """Only the atomic store may write Goal records."""
    for module in ("record.ts", "scheduler.ts", "prompt.ts", "tools.ts", "commands.ts", "events.ts", "check.ts", "dashboard.ts", "core.ts", "evidence.ts"):
        source = (PACKAGE / "src" / module).read_text(encoding="utf-8")
        for primitive in ("writeJsonAtomic", "appendJsonlLine", "createExclusiveJsonFile", "writeFileSync", "appendFileSync"):
            assert primitive not in source, f"{module} reaches {primitive} outside the store"
    assert "writeJsonAtomic" in (PACKAGE / "src" / "store.ts").read_text(encoding="utf-8")
    assert not (PACKAGE / "src" / "ledger.ts").exists()
