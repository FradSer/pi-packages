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
SUBAGENT_TOOL = REPO / "packages" / "subagents" / "src" / "child-execution.ts"
PACKAGES = REPO / "packages"

# Verb -> what replaced it. `reopen` and `supersede` are still reachable, as a
# `status` value and as a `supersedes` field on an existing action, so a caller
# that remembers the verb has somewhere to be pointed.
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
        ["bun", "-e", textwrap.dedent(script)],
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
    """`agent` belongs to @fradser/pi-subagents and the leader task tools are
    retired. What is left here is `message`."""
    text = (SRC / "tools.ts").read_text(encoding="utf-8")
    assert text.count("pi.registerTool(") == 1
    assert 'name: "message"' in text
    assert 'name: "task"' not in text
    assert 'name: "agent"' not in text
