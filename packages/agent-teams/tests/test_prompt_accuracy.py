"""Leader prompt accuracy: guidance and tool disclosure teach only leader Work actions."""

from __future__ import annotations

from test_teammate_package import PACKAGE, SRC, run_node  # noqa: F401  (shared helpers)

# One vocabulary for every participant. The leader/worker split is gone, so
# there is no longer a separate leader action list to keep in step.
TASK_ACTIONS = ["create", "list", "update", "complete", "reopen"]


def _guidance() -> dict[str, object]:
    return run_node(
        f'''\
        import {{ buildIdleLeaderGuidance, buildTeamLeaderGuidance }} from "{(SRC / "guidance.ts").as_uri()}";
        console.log(JSON.stringify({{ idle: buildIdleLeaderGuidance(), active: buildTeamLeaderGuidance() }}));
        '''
    )


def _task_tool() -> dict[str, object]:
    return run_node(
        f'''\
        import {{ publishTeamHost, registerComposedTools }} from "./tests/composed-tools.ts";
        const tools = new Map();
        registerComposedTools({{ registerTool(tool) {{ tools.set(tool.name, tool); }}, getActiveTools() {{ return []; }}, setActiveTools() {{}} }});
        const task = tools.get("task");
        console.log(JSON.stringify({{ description: task.description, promptSnippet: task.promptSnippet }}));
        '''
    )


def test_leader_guidance_names_every_task_action() -> None:
    payload = _guidance()
    for key in ("idle", "active"):
        guidance = str(payload[key])
        lowered = guidance.lower()
        task_lines = [
            line for line in guidance.splitlines()
            if "task" in line.lower() and ("create" in line.lower() or "lifecycle" in line.lower())
        ]
        assert task_lines, f"{key} guidance names no task actions"
        for action in TASK_ACTIONS:
            assert action in lowered, f"{key} guidance omits task action {action}"
    active = str(payload["active"])
    task_bullet = next(line for line in active.splitlines() if line.strip().startswith("- `task`"))
    # The board states what must be done, never who must do it. That is the
    # property the guidance has to teach, so it is asserted rather than trusted.
    # The board states what must be done, never who must do it. That is the
    # property the guidance has to teach, so it is asserted rather than trusted.
    # Collapsed first: the guidance is wrapped prose, so a phrase may straddle a
    # line break and a substring check over the raw text would be testing
    # formatting.
    flat = " ".join(active.split())
    assert "a Task names no owner" in flat
    for removed in ("assign", "claim", "release", "abandon", "reclaim", "submit"):
        assert f"action: \"{removed}\"" not in active
        assert f"`{removed}`" not in task_bullet


def test_task_tool_disclosure_names_every_authorized_action() -> None:
    tool = _task_tool()
    for action in TASK_ACTIONS:
        assert action in str(tool["description"]).lower(), f"task description omits {action}"
    # `promptSnippet` is a routing hint, not a second copy of the description. A
    # model chooses a tool by it, so it has to be short enough to read and long
    # enough to identify the tool; policy belongs in the description.
    snippet = str(tool["promptSnippet"])
    assert 0 < len(snippet) <= 80, snippet
    assert "task" in snippet.lower()
    # The description has to say what the tool does *not* do, or a model reaches
    # for it to start an agent or to hand work to a named participant.
    for forbidden in ("never starts or stops an agent", "never dispatches work"):
        assert forbidden in str(tool["description"]).lower()
