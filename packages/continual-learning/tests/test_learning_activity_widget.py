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


def test_activity_identity_names_the_learner_agent_not_an_action() -> None:
    # Given a TUI learning run, When the above-editor widget renders its row,
    # Then identity names the agent ("learner"), not an action-progress word
    # like "Learning...". The bounded run topic belongs in the activity field,
    # so the identity and progress stay separate in the shared widget language.
    from support import run_bun

    value = run_bun(r"""
      import { stripVTControlCharacters } from 'node:util';
      import { createLiveActivityWidget } from './packages/kit/src/index.ts';
      import { LEARNING_ACTIVITY_IDENTITY } from './packages/continual-learning/extensions/inject-memory.ts';
      let component;
      const ui = { setWidget: (_key, factory) => { component = factory({ requestRender() {} }, { fg: (_c, t) => t, bold: t => t, bg: (_c, t) => t }); } };
      const widget = createLiveActivityWidget({ key: 'continual-learning-activity', fit: (text) => text, activityFormat: 'plain' });
      widget.update({ mode: 'tui', ui }, [{ id: 'learning', identity: LEARNING_ACTIVITY_IDENTITY, status: 'working', activity: 'current task' }]);
      const row = stripVTControlCharacters(component.render(80)[0] ?? '');
      console.log(JSON.stringify({ identity: LEARNING_ACTIVITY_IDENTITY, row }));
    """)
    assert value["identity"] == "learner", value
    assert "learner" in value["row"], value
    assert "· current task" in value["row"], value
    assert "Learning..." not in value["row"], value
    assert "· learning" not in value["row"], value


def test_learner_identity_survives_a_24_column_resize() -> None:
    # Given a live resize of the same widget down to a narrow terminal, When
    # the row renders, Then the complete agent name stays visible and only the
    # bounded activity is ellipsized. The agent name is not progress text.
    from support import run_bun

    value = run_bun(r"""
      import { stripVTControlCharacters } from 'node:util';
      import { truncateToWidth, visibleWidth } from '@earendil-works/pi-tui';
      import { createLiveActivityWidget } from './packages/kit/src/index.ts';
      import { LEARNING_ACTIVITY_IDENTITY } from './packages/continual-learning/extensions/inject-memory.ts';
      let component;
      const ui = { setWidget: (_key, factory) => { component = factory({ requestRender() {} }, { fg: (_c, t) => t, bold: t => t, bg: (_c, t) => t }); } };
      const widget = createLiveActivityWidget({ key: 'continual-learning-activity', fit: truncateToWidth, activityFormat: 'plain' });
      widget.update({ mode: 'tui', ui }, [{ id: 'learning', identity: LEARNING_ACTIVITY_IDENTITY, status: 'working', activity: 'pnpm build and onIdle completion reaction order' }]);
      const rows = [24, 40, 48, 120].map(width => {
        const raw = component.render(width)[0] ?? '';
        return { width, row: stripVTControlCharacters(raw), bounded: visibleWidth(raw) <= width };
      });
      console.log(JSON.stringify({ identity: LEARNING_ACTIVITY_IDENTITY, rows }));
    """)
    assert value["identity"] == "learner", value
    rows = {row["width"]: row for row in value["rows"]}
    for width, entry in rows.items():
        row = entry["row"]
        assert "learner" in row, (width, row)
        assert "lea..." not in row, (width, row)
        assert entry["bounded"], (width, row)
    assert " · " in rows[24]["row"] and rows[24]["row"].rstrip().endswith("..."), rows[24]
    assert "pnpm build and onIdle completion reaction order" in rows[120]["row"], rows[120]
