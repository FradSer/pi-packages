"""Leader prompt accuracy: guidance and tool disclosure teach only leader Work actions."""

from __future__ import annotations

from test_teammate_package import PACKAGE, SRC, run_node  # noqa: F401  (shared helpers)

LEADER_ACTIONS = ["create", "list", "assign", "release", "reopen", "supersede"]


def _guidance() -> dict[str, object]:
    return run_node(
        f'''\
        import {{ buildIdleLeaderGuidance, buildTeamLeaderGuidance }} from "{(SRC / "guidance.ts").as_uri()}";
        console.log(JSON.stringify({{ idle: buildIdleLeaderGuidance(), active: buildTeamLeaderGuidance() }}));
        '''
    )


def _work_tool() -> dict[str, object]:
    return run_node(
        f'''\
        import {{ registerLeaderTools }} from "{(SRC / "tools.ts").as_uri()}";
        const tools = new Map();
        registerLeaderTools({{ registerTool(tool) {{ tools.set(tool.name, tool); }}, getActiveTools() {{ return []; }}, setActiveTools() {{}} }});
        const work = tools.get("work");
        console.log(JSON.stringify({{ description: work.description, promptSnippet: work.promptSnippet }}));
        '''
    )


def test_leader_guidance_names_only_leader_work_actions() -> None:
    payload = _guidance()
    for key in ("idle", "active"):
        guidance = str(payload[key])
        lowered = guidance.lower()
        work_lines = [line for line in guidance.splitlines() if "work" in line.lower() and ("create" in line.lower() or "work lifecycle" in line.lower())]
        assert work_lines, f"{key} guidance names no work actions"
        for action in LEADER_ACTIONS:
            assert action in lowered, f"{key} guidance omits leader work action {action}"
    active = str(payload["active"])
    work_bullet = next(line for line in active.splitlines() if line.strip().startswith("- `work`"))
    assert "not leader action" in work_bullet
    for listed in ("assign, claim", "claim, submit", ", submit,", "submit, release"):
        assert listed not in work_bullet
    assert "claim" in active and "submit" in active  # worker ownership still stated


def test_leader_work_tool_disclosure_names_every_authorized_action() -> None:
    tool = _work_tool()
    for field in ("description", "promptSnippet"):
        text = str(tool[field]).lower()
        for action in LEADER_ACTIONS:
            assert action in text, f"work {field} omits {action}"
