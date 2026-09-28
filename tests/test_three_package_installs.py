"""The three packages as four real installs, driven through a real `pi` process.

Success criteria 1 and 2 of the three-package split. Everything asserted here is
observed in a live process: the tool surface comes from the host's own registry,
and the state-machine values come from real tool executions whose results the
scripted provider read back out of the transcript. No assertion is about how a
model would phrase a turn, and nothing needs credentials — the only thing replaced
is the model.

Determinism comes from `support/scripted.ts`. Credibility comes from the fact that
the tool calls, schema validation, the coordinator seam and the board's own
refusals are all the shipping code paths.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "e2e" / "support"))

from harness import PROBE, Run, loaded_entries, run_install  # noqa: E402

# The three tools, and the harness's own probe, which is not one of them.
COORDINATION = ("agent", "task", "message")

# What each install must expose. Read as a table so a package gaining or losing a
# tool is a one-line change with a test attached, not a silent drift.
EXPECTED_SURFACE: dict[tuple[str, ...], tuple[str, ...]] = {
    ("subagents",): ("agent",),
    ("tasks",): ("task",),
    ("subagents", "tasks"): ("agent", "task"),
    ("agent-teams",): ("agent", "task", "message"),
}


def coordination_tools(run: Run) -> list[str]:
    return [name for name in run.surfaces() if name in COORDINATION]


# ── Criterion 2: exactly one registrant per tool, per combination ──


@pytest.mark.parametrize("installed,expected", sorted(EXPECTED_SURFACE.items()))
def test_each_install_exposes_exactly_its_own_tools(
    tmp_path: Path, installed: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    run = run_install(tmp_path, list(installed))
    assert run.completed.returncode == 0, run.text
    # Asserted as a set, so a package that quietly added a second tool fails.
    assert set(coordination_tools(run)) == set(expected), run.surfaces()


def test_a_single_package_install_resolves_to_one_entry(tmp_path: Path) -> None:
    """The bundle is what makes one install enough; everything else must work alone."""
    assert loaded_entries(["subagents"]) == ["subagents"]
    assert loaded_entries(["tasks"]) == ["tasks"]
    # The bundle's own entry registers one tool, and its manifest is what loads the
    # other two. Resolved from the manifests, so a manifest that stopped listing a
    # dependency fails here rather than at load time.
    assert loaded_entries(["agent-teams"]) == ["agent-teams", "subagents", "tasks"]


# ── Criterion 1: each install is a working loop, not a manifest claim ──


def test_subagents_alone_runs_a_child_lifecycle(tmp_path: Path) -> None:
    """Spawn, observe and stop a child session, through the tool surface only.

    `start` with no prompt is the idle-resident shape: the child enters the pool
    and waits for work rather than burning a model turn. That is the case a team
    depends on, so it is the one exercised.
    """
    run = run_install(tmp_path, ["subagents"], scenario="agent-lifecycle")
    assert run.completed.returncode == 0, run.text

    starts = run.calls_named("agent")
    assert len(starts) == 4, [call["name"] for call in starts]
    assert all(call["isError"] is False for call in starts), [call["text"] for call in starts]

    started = starts[0]["details"]
    assert started["action"] == "start"
    assert started["outcome"] == "started"
    assert started["prompted"] is False, "no prompt means no kickoff turn"
    handle = started["session"]
    assert isinstance(handle, str) and handle.startswith("session:scout:"), handle

    listed = starts[1]["details"]
    assert listed["count"] == 1
    assert listed["agents"][0]["session"] == handle, "list must report the handle start returned"

    inspected = starts[2]["details"]
    assert inspected["outcome"] == "inspected"
    assert inspected["sessions"][0]["name"] == "scout"

    stopped = starts[3]["details"]
    assert stopped["outcome"] == "stopped"
    assert stopped["session"] == handle
    # A stopped process is not a finished task, and the row says so where a reader
    # would otherwise infer completion from a dead pid.
    assert "not evidence" in str(stopped.get("evidence", ""))


def test_tasks_alone_runs_a_board_loop(tmp_path: Path) -> None:
    """create → list → take → complete, through one tool in one process."""
    run = run_install(tmp_path, ["tasks"], scenario="board-lifecycle")
    assert run.completed.returncode == 0, run.text

    board = run.calls_named("task")
    assert len(board) == 5, [call["name"] for call in board]
    assert all(call["isError"] is False for call in board), [call["text"] for call in board]

    created, claimable, taken, delivered, final = (call["details"] for call in board)
    task_id = created["id"]
    assert created["status"] == "pending"
    # The later calls were handed this id by the harness reading the create result,
    # so the loop acted on the same record rather than a literal in the script.
    assert claimable["claimable"] if "claimable" in claimable else claimable["count"] == 1
    assert taken["id"] == task_id
    assert taken["status"] == "in_progress"
    assert taken["task"]["holder"] == "main", "the caller is the holder; there is no assignee"
    assert delivered["id"] == task_id
    assert delivered["status"] == "completed"
    assert final["tasks"][0]["status"] == "completed"


def test_two_packages_integrate_and_refuse_an_overlapping_take(tmp_path: Path) -> None:
    """A resident joins, a take succeeds, and an overlapping take is refused.

    This is the property that makes a resident's self-serve take safe: whoever acts
    holds the task, and two participants cannot hold overlapping resources at once.
    Without the roster being published to the board, the board would degrade to a
    single session and the overlap would go unnoticed — which is what happened
    before the execution layer published its roster as the board's participant
    registry.
    """
    run = run_install(tmp_path, ["subagents", "tasks"], scenario="resident-takes", host="peer")
    assert run.completed.returncode == 0, run.text

    started = run.calls_named("agent")[0]["details"]
    assert started["outcome"] == "started", started
    assert started["prompted"] is False, "the resident waits for work rather than starting on it"

    # create, list, take, create, take, list.
    board = run.calls_named("task")
    assert len(board) == 6, [call["name"] for call in board]
    assert all(call["isError"] is False for call in board[:4]), [call["text"] for call in board]

    first_take = board[2]["details"]
    assert first_take["action"] == "take"
    assert first_take["status"] == "in_progress"

    # The second create overlaps what the peer holds, so the take must be refused
    # and the refusal must name the holder. A refusal that did not say who blocked
    # you is a dead end rather than a conflict.
    # Asserted on the refusal's own content rather than on the transcript's error
    # flag: the flag is the harness's channel, the refusal is the tool's contract.
    refused = board[4]
    assert refused["details"].get("ok") is False, refused["details"]
    assert "@peer" in refused["text"], refused["text"]
    assert "conflicts" in refused["text"], refused["text"]

    # Nothing moved: the refused task is still pending and still unheld.
    listed = board[5]["details"]["tasks"]
    blocked = next(task for task in listed if task["id"] == board[3]["details"]["id"])
    assert blocked["status"] == "pending"
    assert "holder" not in blocked


def test_bundle_exposes_all_three_and_delivers_peer_mail(tmp_path: Path) -> None:
    """The bundle's whole claim: one install, three tools, and mail that arrives.

    The resident is started with a prompt, which is what gives it an open
    assignment. Mail is work-bound, so a message to a participant holding nothing
    is refused — correctly, and not a delivery failure.
    """
    run = run_install(tmp_path, ["agent-teams"], scenario="bundle", host="team")
    assert run.completed.returncode == 0, run.text
    assert set(coordination_tools(run)) == {"agent", "task", "message"}, run.surfaces()

    started = run.calls_named("agent")[0]["details"]
    assert started["outcome"] == "started", started

    board = run.calls_named("task")
    assert [call["details"]["status"] for call in board] == ["pending", "in_progress"], board

    delivered = run.call("message")["details"]
    assert delivered["to"] == "scout"
    # `steered` is the delivery outcome for a live recipient with an open
    # assignment, as opposed to a queue entry or a refusal.
    assert delivered["outcome"] == "steered", delivered
    assert delivered["kind"] == "request"


def test_a_tool_from_an_absent_package_is_refused_not_merely_absent(tmp_path: Path) -> None:
    """The negative control for every surface assertion above.

    A harness that could not start a process, or that swallowed one, would report
    an empty surface and fail these tests for the wrong reason. So this asks the
    stronger question: with only the board installed, a call to the communication
    tool is *refused in the transcript*, not quietly skipped. That is what makes
    "installed alone" mean the tool is really not there, rather than that the
    scenario happened not to use it.
    """
    run = run_install(tmp_path, ["tasks"], scenario="bundle")
    assert run.completed.returncode == 0, run.text
    # The board half of the bundle scenario ran, so the process is live.
    assert run.calls_named("task"), "the scenario did not reach the board"
    assert "task" in coordination_tools(run)
    # The other two were attempted and the host refused them by name. Asserting the
    # refusal rather than the absence of a call: the script always calls, so an
    # absence would mean the transcript was truncated rather than that the tool is
    # genuinely not installed.
    for absent in ("agent", "message"):
        refused = run.calls_named(absent)
        assert len(refused) == 1, refused
        assert refused[0]["isError"] is True, refused[0]
        assert f"Tool {absent} not found" in refused[0]["text"], refused[0]["text"]
        assert absent not in coordination_tools(run)


def test_the_probe_never_counts_as_a_coordination_tool(tmp_path: Path) -> None:
    """The harness's own tool must not be mistaken for one of the three, or every
    surface assertion above would be off by one."""
    run = run_install(tmp_path, ["tasks"])
    assert PROBE in run.surfaces()
    assert PROBE not in coordination_tools(run)
