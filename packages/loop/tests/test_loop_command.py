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


def test_starting_a_loop_announces_it_without_consuming_a_turn() -> None:
    data = value(run("start-flags"), "start-flags")
    assert data["sent"] == [], "a parameterized start must not inject before the interval"
    assert data["lifecycle"] == [{"customType": "loop-lifecycle", "display": True, "triggerTurn": False}], data
    assert data["status"] == ["Looping · every 1h · 0/2"], data["status"]
    content = str(data["content"])
    assert "CHECK THE BUILD" in content and "1h" in content and "/loop stop" in content, content
    assert data["events"] == ["agent_end", "agent_settled", "session_start", "session_shutdown"], data["events"]


def test_status_and_stop_report_state_and_clear_the_row() -> None:
    data = value(run("status-and-stop"), "status-and-stop")
    assert said(data["before"]["notifications"], "loop: no loop is running."), data["before"]
    assert said(data["before"]["notifications"], "Usage:"), data["before"]
    assert data["started"]["status"] == ["Looping · every 1h · 0/3"], data["started"]
    assert said(data["status"]["notifications"], "loop: Looping · every 1h · 0/3"), data["status"]
    assert data["stopped"]["status"] == [None], "stopping must clear the row: " + json.dumps(data["stopped"])
    assert said(data["stopped"]["notifications"], "stopped after 0 injections (user)"), data["stopped"]
    assert said(data["afterStop"], "loop: no loop is running."), data["afterStop"]


def test_every_refusal_names_the_cause_and_schedules_nothing() -> None:
    data = value(run("refusals-and-usage"), "refusals-and-usage")
    assert said(data["busy"], "already running"), data["busy"]
    assert data["busy"][0]["level"] == "warning"
    for key, needle in (("badDuration", "--every must be a duration"),
                        ("noMessage", "A message is required"),
                        ("unknownFlag", "Unknown option: --bogus"),
                        ("freeWithoutCredential", "needs a decision credential"),
                        ("untilWithoutCredential", "--until needs a decision credential")):
        rows = data[key]
        assert said(rows, needle), (key, rows)
        assert rows[0]["level"] == "error", (key, rows)
    headless = data["headless"]
    assert headless and headless[0]["customType"] == "loop-notice", headless
    assert headless[0]["options"] == {"triggerTurn": False}, headless

