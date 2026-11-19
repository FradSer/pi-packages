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


def test_leader_guidance_explains_internal_work_without_a_task_tool() -> None:
    payload = _guidance()
    for key in ("idle", "active"):
        flat = " ".join(str(payload[key]).split())
        lowered = flat.lower()
        assert "work items are internal" in lowered or "runtime records work internally" in lowered
        for retired in ("create_task", "list_tasks", "get_task", "update_task"):
            assert retired not in flat, f"{key} still teaches the retired {retired} tool"
    active = " ".join(str(payload["active"]).split())
    assert "no leader task tool" in active.lower()
