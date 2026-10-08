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
import subprocess
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


def run_harness(name: str) -> list[str]:
    result = subprocess.run(
        ["node", "--import", "tsx", f"packages/goal/tests/{name}"],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, f"{name} stderr: {result.stderr}"
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


def test_scheduling_authorization_contracts() -> None:
    """Claim, dispatch, generations, waits, allowances, and the stop guard.

    Covers the "Scheduling authorization" and "Prompt stability" feature blocks.
    """
    outcomes = assert_all_pass("goal_scheduling.mts")
    assert len(outcomes) >= 20, f"expected the full scheduling contract, got {len(outcomes)}"


def test_prefix_stability_contracts() -> None:
    """Consecutive requests must nest: request N is a true prefix of request N+1.

    Naive tail injection breaks this at the first injection point, which is the
    exact failure the provider's implicit prompt cache cannot tolerate. Each
    scenario builds two requests and compares them rather than inspecting one
    injection in isolation.

    Covers the "Injected state is prefix-stable" feature block.
    """
    outcomes = assert_all_pass("goal_live_context.mts")
    assert len(outcomes) >= 11, f"expected the full prefix contract, got {len(outcomes)}"


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
    for module in ("record.ts", "scheduler.ts", "prompt.ts", "tools.ts", "commands.ts", "events.ts", "check.ts", "dashboard.ts", "core.ts", "live-context.ts", "evidence.ts"):
        source = (PACKAGE / "src" / module).read_text(encoding="utf-8")
        for primitive in ("writeJsonAtomic", "appendJsonlLine", "createExclusiveJsonFile", "writeFileSync", "appendFileSync"):
            assert primitive not in source, f"{module} reaches {primitive} outside the store"
    assert "writeJsonAtomic" in (PACKAGE / "src" / "store.ts").read_text(encoding="utf-8")
    assert not (PACKAGE / "src" / "ledger.ts").exists()
