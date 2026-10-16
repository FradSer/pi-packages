"""The /loop command surface: what each invocation reports synchronously."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
FIXTURE = Path(__file__).with_name("loop-command-fixture.ts")


def run(*scenarios: str) -> dict[str, dict[str, object]]:
    result = subprocess.run(["bun", str(FIXTURE), *scenarios], cwd=REPO, capture_output=True,
                            text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
    return {value["scenario"]: value for line in result.stdout.splitlines() if line.strip()
            for value in [json.loads(line)]}


def value(cases: dict[str, dict[str, object]], name: str) -> dict[str, object]:
    case = cases[name]
    assert case.get("ok") is True, case
    return case["value"]  # type: ignore[return-value]


def messages(rows: list[dict[str, object]]) -> list[str]:
    return [str(row["message"]) for row in rows]


def said(rows: list[dict[str, object]], needle: str) -> bool:
    """One notification carries a report and its usage, so match inside the message."""
    return any(needle in message for message in messages(rows))


def test_starting_a_loop_runs_the_first_repetition_and_announces_it() -> None:
    """A start injects the first repetition at once, and the line reports the plan.

    The notice itself consumes no turn: it is queued and injected at the head of
    the run the first repetition reaches.
    """
    data = value(run("start-flags"), "start-flags")
    assert data["sent"] == ["CHECK THE BUILD"], "the first repetition arrives at start"
    assert data["status"] == ["Looping · every 1h · 1/2"], data["status"]
    assert data["lifecycle"] == [], "the notice must not be appended at start: " + json.dumps(data)
    assert "becomes the schedule" not in str(data["notice"]), \
        "a parameterized start states its own message: " + json.dumps(data)
    assert data["events"] == ["before_agent_start", "agent_end", "agent_settled", "session_start",
                              "session_shutdown"], data["events"]


def test_status_and_stop_report_state_and_clear_the_row() -> None:
    data = value(run("status-and-stop"), "status-and-stop")
    assert said(data["before"]["notifications"], "loop: no loop is running."), data["before"]
    assert said(data["before"]["notifications"], "Usage:"), data["before"]
    assert data["started"]["status"] == ["Looping · every 1h · 1/3"], data["started"]
    assert said(data["status"]["notifications"], "loop: Looping · every 1h · 1/3"), data["status"]
    assert data["stopped"]["status"] == [None], "stopping must clear the row: " + json.dumps(data["stopped"])
    # The first repetition ran at start, so a stop reports one injection.
    assert said(data["stopped"]["notifications"], "stopped after 1 injection (user)"), data["stopped"]
    assert said(data["afterStop"], "loop: no loop is running."), data["afterStop"]


def test_every_refusal_names_the_cause_and_schedules_nothing() -> None:
    data = value(run("refusals-and-usage"), "refusals-and-usage")
    assert said(data["busy"], "already running"), data["busy"]
    assert data["busy"][0]["level"] == "warning"
    for key, needle in (("badDuration", "--every must be a duration"),
                        ("noMessage", "A message is required"),
                        ("unknownFlag", "Unknown option: --bogus"),
                        ("placeholderTypo", "Unknown placeholder: Index"),
                        ("freeWithoutCredential", "needs a decision credential"),
                        ("untilWithoutCredential", "--until needs a decision credential")):
        rows = data[key]
        assert said(rows, needle), (key, rows)
        assert rows[0]["level"] == "error", (key, rows)
    headless = data["headless"]
    assert headless and headless[0]["customType"] == "loop-notice", headless
    assert headless[0]["options"] == {"triggerTurn": False}, headless


def test_the_start_line_states_the_cadence_it_uses() -> None:
    """The notice must describe the cadence the plan actually took.

    The line said "the loop repeats as soon as each repetition settles" while the
    cadence was five minutes, so a reader was told one thing and shown another.
    """
    data = value(run("start-flags"), "start-flags")
    content = str(data["notice"])
    assert "every 1h" in content, content
    assert "as soon as each repetition settles" not in content, content
    assert "/loop stop" in content, content


def test_a_semantic_start_says_what_left_the_message() -> None:
    """The line must say that the count became the schedule, not the message.

    A reader who typed "输入3次Hi" has to learn from the line that the message is
    "输入Hi" and why.
    """
    data = value(run("a-semantic-start-says-what-left-the-message"),
                 "a-semantic-start-says-what-left-the-message")
    assert data["hits"] == ["interval,runs,stop"], data
    assert data["sent"] == ["输入Hi"], data
    content = str(data["notice"])
    assert "Message: 输入Hi." in content, content
    assert "becomes the schedule, not part of the message" in content, content
    assert "Cadence: every 5m" in content, content


def test_a_start_line_does_not_preempt_the_run_it_started() -> None:
    """The start line must not be inserted before a repetition already queued.

    Every `/loop ...` arrives as a user turn, and a repetition is queued behind
    that run. A start line sent at start would preempt the user's own turn, so the
    line belongs to the first repetition's turn instead: the repetition is
    injected, and only then does the run carry the line.
    """
    data = value(run("the-start-line-belongs-to-the-next-run"), "the-start-line-belongs-to-the-next-run")
    assert data["injections"] == ["WATCH"], data
    assert data["fromCommand"] == [], "the start must not preempt the command's own run: " + json.dumps(data)
    # The line waited for the repetition's turn: the injection was queued behind
    # the command's run, so the start line joined the turn the repetition reached
    # and the user's own input kept the turn it started.
    assert data["whileRunning"] == ["loop-lifecycle"], data
    assert data["beforeNextRun"] == [], "the repetition is already queued: " + json.dumps(data)
    assert data["second"] == [], "the line was already injected: " + json.dumps(data)


def test_only_the_loop_own_repetition_is_judged() -> None:
    """A settle that carries no repetition must ask no question and change nothing.

    features/loop.feature: the stopping judgment runs after the injected turn
    settles. Every settled turn reaches the extension, so a turn the user started
    (or one that was already running when the repetition was queued behind it)
    must not spend a decision request on an answer that is not this loop's result.
    """
    data = value(run("only-the-repetition-is-judged"), "only-the-repetition-is-judged")
    assert data["injected"] is True, data
    assert data["repetition"] == "WATCH", data
    assert str(data["running"][-1]).startswith("Looping · every 1s · "), data
    foreign = data["foreign"]
    assert foreign["hits"] == [], "a foreign settle must ask no stopping question: " + json.dumps(foreign)
    assert str(foreign["status"][-1]).startswith("Looping · every 1s · "), foreign
    assert all("stopped" not in row["message"] for row in foreign["notifications"]), foreign
    after = data["after"]
    assert after["hits"] == ["met"], after
    assert data["judged"] is True, data
    assert after["status"][-1] is None, after
    # How many ticks elapsed before the repetition settled is timing, so the
    # report's count is asserted by shape, not by value.
    stopped = str(after["notifications"][-1]["message"])
    assert stopped.startswith("loop: stopped after ") and stopped.endswith("(condition)"), after


def test_a_refused_delivery_is_reported_once_and_clears_the_row() -> None:
    """The command surface must report the delivery the host refused."""
    data = value(run("delivery-failure"), "delivery-failure")
    assert data["reported"] is True, data
    assert len(data["notifications"]) == 1, data
    notice = data["notifications"][0]
    assert notice["level"] == "error", notice
    assert "refused a scheduled injection" in str(notice["message"]), notice
    assert "stale" in str(notice["message"]), notice
    assert data["sent"] == ["WATCH"], "the loop must stop after one refusal: " + json.dumps(data)
    assert data["status"][-1] is None, "the row must clear: " + json.dumps(data)

