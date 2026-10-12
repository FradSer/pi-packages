"""The cutover: every removed verb is refused, with its replacement named.

Success criterion 5 of the goal. These exist because deleting a verb is only half
the work — the other half is proving the old name cannot quietly come back. Each
removal is asserted twice: against the schema, so the name is not even offered,
and against a live call, so a caller passing it anyway gets a refusal rather than
silence.
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SRC = PACKAGE / "src"
REPO = PACKAGE.parents[1]
TASK_TOOL = REPO / "packages" / "tasks" / "src" / "tool.ts"
SUBAGENT_TOOL = REPO / "packages" / "subagents" / "src" / "child-execution.ts"
PACKAGES = REPO / "packages"

# Verb -> what replaced it. `reopen` and `supersede` are still reachable, as a
# `status` value and as a `supersedes` field on an existing action, so a caller
# that remembers the verb has somewhere to be pointed.
REMOVED_LEADER_VERBS = {
    "assign": "update status=in_progress",
    "claim": "update status=in_progress",
    "release": "completion, process exit, or agent stop",
    "abandon": "complete outcome=failed",
    "reclaim": "agent stop",
    "submit": "complete outcome=success",
    "reopen": "update status=pending",
    "supersede": "create with supersedes",
    "get": "list with id",
}

REMOVED_AGENT_VERBS = {
    "delegate": "start with a prompt",
    "team": "list",
}

# Two of the removed leader verbs survive as *fields* rather than verbs: a task is
# reopened with `update status=pending` and replaced with `create supersedes`, so
# they must be absent from the action enum while remaining reachable. A test that
# swept them into the enum check would forbid the only spelling that works.
REMOVED_VERBS_REACHABLE_AS_FIELDS = {"reopen", "supersede"}


def run_node(script: str) -> dict[str, object]:
    """Run an inline ES module and parse its last stdout line as JSON.

    `PI_TEAMMATE_*` is stripped so a coordination binding left over in the
    developer's shell cannot make a spawned child believe it is a worker.
    """
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_TEAMMATE_")}
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script)],
        cwd=PACKAGE,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def package_sources() -> list[Path]:
    """Every shipped source file of the three packages, tests excluded."""
    files: list[Path] = []
    for package in ("agent-teams", "subagents", "tasks"):
        for path in (PACKAGES / package).rglob("*.ts"):
            if "node_modules" in path.parts or "tests" in path.parts:
                continue
            files.append(path)
    return files


# ── No removed verb is offered ──


def test_no_removed_verb_appears_in_any_schema() -> None:
    """Only the action enum matters. A removed verb may still appear in a comment
    explaining why it is gone, and must not be banned from doing so."""
    for path, verbs in ((TASK_TOOL, REMOVED_LEADER_VERBS), (SUBAGENT_TOOL, REMOVED_AGENT_VERBS)):
        text = path.read_text(encoding="utf-8")
        for verb in verbs:
            if path is TASK_TOOL and verb in REMOVED_VERBS_REACHABLE_AS_FIELDS:
                continue
            offered = next(
                (line for line in text.splitlines() if "enum:" in line and f'"{verb}"' in line),
                None,
            )
            assert offered is None, f"{path.name} still offers removed verb {verb}: {offered}"


def test_the_two_absorbed_verbs_are_reachable_as_fields() -> None:
    """Deleting a verb is only half a cutover: the capability has to survive under
    a name that works. Reopening is `status: "pending"` on update_task; superseding
    is a `supersedes` field on create_task. Each now lives on the one tool that
    performs it, rather than both on an `update` that meant three things."""
    result = run_node(
        f"""
        import {{ TASK_UPDATE_PARAMS, TASK_CREATE_PARAMS }} from {json.dumps(TASK_TOOL.as_uri())};
        console.log(JSON.stringify({{
          reopenAsStatus: TASK_UPDATE_PARAMS.properties.status.enum,
          supersedeAsField: "supersedes" in TASK_CREATE_PARAMS.properties,
          supersededIsNotAStatus: !TASK_UPDATE_PARAMS.properties.status.enum.includes("superseded"),
        }}));
        """
    )
    assert result["reopenAsStatus"] == ["in_progress", "completed", "pending", "blocked", "cancelled"]
    assert result["supersedeAsField"] is True
    assert result["supersededIsNotAStatus"] is True, (
        "supersession is a creation, not something a caller moves a task to"
    )


def test_the_task_surface_is_exactly_four_tools() -> None:
    """The action enum is gone with the single tool it belonged to. What is pinned
    now is the four names, read from the package rather than restated here."""
    result = run_node(
        f"""
        import {{ TASK_CAPABILITY_TOOLS }} from {json.dumps(TASK_TOOL.as_uri())};
        console.log(JSON.stringify([...TASK_CAPABILITY_TOOLS]));
        """
    )
    assert result == ["create_task", "get_task", "list_tasks", "update_task"]


def test_the_child_operation_enum_is_exactly_four() -> None:
    """The set the executor implements, no more and no less: one operation per
    intent tool, with `agent_input` carrying its own delivery. The vocabulary is
    checked against the registration rather than against a remembered list."""
    result = run_node(
        f"""
        import {{ CHILD_OPERATIONS }} from {json.dumps(SUBAGENT_TOOL.as_uri())};
        console.log(JSON.stringify(CHILD_OPERATIONS));
        """
    )
    assert result == ["start", "input", "list", "stop"]


# ── And a caller passing one anyway is told, not ignored ──


def test_every_removed_leader_verb_is_refused_by_a_live_call() -> None:
    """Silence reads as success to a model, which is how a removed action comes
    back. Each refusal has to name the surviving path."""
    result = run_node(
        f"""
        import {{ executeTaskUpdate }} from {json.dumps(TASK_TOOL.as_uri())};
        const removed = {json.dumps(sorted(REMOVED_LEADER_VERBS))};
        const out = {{}};
        for (const action of removed) {{
          const r = await executeTaskUpdate({{ id: "whatever", status: action }});
          out[action] = {{ refused: r.details.ok === false, text: r.content[0].text }};
        }}
        console.log(JSON.stringify(out));
        """
    )
    for verb in REMOVED_LEADER_VERBS:
        assert result[verb]["refused"] is True, f"{verb} was not refused"
    # A status outside the three routes names them, so a model that remembers an
    # older verb learns what replaced it.
    for verb in ("release", "abandon", "assign"):
        assert verb in result[verb]["text"], f"the {verb} refusal does not quote it"
    for route in ("in_progress", "completed", "pending"):
        assert route in result["release"]["text"], f"the release refusal omits {route}"


def test_every_removed_agent_verb_is_refused_by_a_live_call() -> None:
    result = run_node(
        f"""
        import {{ executeChildIntent }} from {json.dumps(SUBAGENT_TOOL.as_uri())};
        const removed = {json.dumps(sorted(REMOVED_AGENT_VERBS))};
        const out = {{}};
        for (const action of removed) {{
          const r = await executeChildIntent({{ action, name: "x" }});
          out[action] = {{ refused: r.details.ok === false }};
        }}
        console.log(JSON.stringify(out));
        """
    )
    for verb in REMOVED_AGENT_VERBS:
        assert result[verb]["refused"] is True, f"{verb} was not refused"


# ── And the old tool names are gone entirely ──


def test_the_removed_tool_names_are_gone_from_every_package() -> None:
    """`work` and `agent_event` were the tool names before the cutover. A
    remaining registration would mean some install combination still answers to
    them, which is the double-registrant problem the split exists to remove."""
    offenders: list[str] = []
    for path in package_sources():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if 'name: "work"' in line or 'name: "agent_event"' in line:
                offenders.append(f"{path.relative_to(PACKAGES)}:{number}")
    assert offenders == []


def test_the_claimed_status_value_is_gone() -> None:
    """`claimed` became `in_progress`: a Task has no declared owner, so moving it
    into progress *is* taking it. The literal must not survive as a status, though
    the field `claimedBy` legitimately keeps its name."""
    offenders = [
        str(path.relative_to(PACKAGES))
        for path in package_sources()
        if '"claimed"' in path.read_text(encoding="utf-8")
        or "'claimed'" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


# ── And the wiring that served the removed tool is not left behind ──


def test_the_removed_coordinator_wrappers_have_no_callers() -> None:
    """The four orchestration wrappers existed only to serve the removed tool. A
    caller left behind would take a path the tasks no longer goes through, and
    would silently skip the notice and wake-up the event subscriber performs."""
    tools = (SRC / "tools.ts").read_text(encoding="utf-8")
    for wrapper in ("createCoordinatedTask", "assignExistingWork", "releaseExistingWork", "reopenExistingWork"):
        assert f"{wrapper}(" not in tools, f"{wrapper} is still called by the tool layer"


def test_this_package_registers_exactly_one_tool() -> None:
    """`task` now belongs to @fradser/pi-tasks and `agent` to
    @fradser/pi-subagents. What is left here is `message`."""
    text = (SRC / "tools.ts").read_text(encoding="utf-8")
    assert text.count("pi.registerTool(") == 1
    assert 'name: "message"' in text
    assert 'name: "task"' not in text
    assert 'name: "agent"' not in text
