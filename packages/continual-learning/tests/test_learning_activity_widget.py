"""One live activity row above the editor while a learning run is active."""
from __future__ import annotations

from pathlib import Path

from support import run_bun_script


HARNESS = Path(__file__).with_name("learning-policy-harness.ts")


def test_tui_run_mounts_and_clears_one_above_editor_activity_row() -> None:
    # Given a learning run started in the TUI, When the pipeline runs and ends,
    # Then one native live activity widget is mounted above the editor and
    # cleared exactly once at the end, so no stale row outlives the run.
    result = run_bun_script(HARNESS, "manual-full", env={"CL_TUI_MODE": "1"})
    events = result["widgetEvents"]
    assert events, result
    mounted = [row for row in events if row["mounted"]]
    cleared = [row for row in events if not row["mounted"]]
    assert len(mounted) == 1, events
    assert len(cleared) >= 1, events
    assert mounted[0]["key"] == "continual-learning-activity", mounted
    assert mounted[0]["placement"] == "aboveEditor", mounted
    assert events.index(mounted[0]) < events.index(cleared[0]), events


def test_headless_run_never_mounts_an_activity_row() -> None:
    # Given a --print/RPC run, When the pipeline runs, Then no widget is
    # mounted; the live row is strictly a TUI affordance.
    result = run_bun_script(HARNESS, "manual-full")
    assert result["widgetEvents"] == [], result["widgetEvents"]


def test_activity_row_is_cleared_on_a_failed_run() -> None:
    # Given a run that fails, When the pipeline settles, Then the activity row
    # is still cleared; a failure never leaves a spinner above the editor.
    result = run_bun_script(HARNESS, "remember-invalid", env={"CL_TUI_MODE": "1"})
    events = result["widgetEvents"]
    assert any(row["mounted"] for row in events), events
    assert any(not row["mounted"] for row in events), events
