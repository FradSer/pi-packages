"""Leader prompt accuracy: guidance and tool disclosure teach only leader Work actions."""

from __future__ import annotations

from test_agent_package import PACKAGE, SRC, run_node  # noqa: F401  (shared helpers)

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
        import {{ TASK_CAPABILITY_TOOLS }} from "@fradser/pi-tasks";
        const tools = new Map();
        registerComposedTools({{ registerTool(tool) {{ tools.set(tool.name, tool); }}, getActiveTools() {{ return []; }}, setActiveTools() {{}} }});
        // Four tools, so the disclosure a model reads is four descriptions and
        // four one-liners rather than one of each. The names come from the
        // package rather than a prefix guess, so a rename cannot leave this
        // test quietly asserting against an empty set.
        const names = [...TASK_CAPABILITY_TOOLS].filter((name) => tools.has(name));
        console.log(JSON.stringify({{
          names,
          descriptions: Object.fromEntries(names.map((name) => [name, tools.get(name).description])),
          snippets: Object.fromEntries(names.map((name) => [name, tools.get(name).promptSnippet])),
        }}));
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
    # The task store states what must be done, never who must do it. That is the
    # property the guidance has to teach, so it is asserted rather than trusted.
    # The task store states what must be done, never who must do it. That is the
    # property the guidance has to teach, so it is asserted rather than trusted.
    # Collapsed first: the guidance is wrapped prose, so a phrase may straddle a
    # line break and a substring check over the raw text would be testing
    # formatting.
    flat = " ".join(active.split())
    assert "a Task names no owner" in flat
    for removed in ("assign", "claim", "release", "abandon", "reclaim", "submit"):
        assert f"action: \"{removed}\"" not in active
        assert f"`{removed}`" not in task_bullet


def test_each_task_tool_disclosure_names_what_it_does() -> None:
    """Four tools, so four disclosures. A model picks one by its name and its
    snippet, so each has to say what that one operation is and no more."""
    surface = _task_tool()
    assert sorted(surface["names"]) == ["create_task", "get_task", "list_tasks", "update_task"], surface["names"]
    for name in surface["names"]:
        description = str(surface["descriptions"][name])
        snippet = str(surface["snippets"][name])
        # `promptSnippet` is a routing hint, not a second copy of the description.
        # A model chooses a tool by it, so it has to be short enough to read and
        # long enough to identify the tool; policy belongs in the description.
        assert 0 < len(snippet) <= 80, f"{name}: {snippet}"
        assert "task" in snippet.lower(), f"{name}: {snippet}"
        assert len(description) > len(snippet), f"{name}: the snippet is a copy of the description"
    # update_task is the one that has to say what it does *not* do, or a model
    # reaches for it to start a participant or to hand work to a named one.
    update = str(surface["descriptions"]["update_task"]).lower()
    for forbidden in ("never starts or stops a participant", "never dispatches work"):
        assert forbidden in update, forbidden
    # The supersession route is a field, not a verb, and create_task says so.
    assert "supersedes" in str(surface["descriptions"]["create_task"]).lower()
