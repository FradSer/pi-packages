"""Deterministic /loop contracts, checked on the real modules."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
FIXTURE = Path(__file__).with_name("loop-core-fixture.ts")


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


def test_duration_parsing_and_bounds() -> None:
    data = value(run("duration"), "duration")
    assert data["min"] == 1000 and data["max"] == 86400000
    for row in data["parsed"]:  # type: ignore[union-attr]
        expected = None if row["expected"] is None else row["expected"]
        assert row.get("actual") == expected, row
    for row in data["formatted"]:  # type: ignore[union-attr]
        assert row["actual"] == row["expected"], row


def test_template_expansion_and_unknown_placeholder() -> None:
    data = value(run("template"), "template")
    assert data["clock"] == {"time": "03:04:05", "date": "2026-01-02"}, data["clock"]
    assert data["bounded"] == "status 2 of 2"
    assert data["unbounded"] == "3/unbounded unbounded"
    assert data["remaining"] == "4"
    assert data["spaced"] == "7"
    assert data["unknown"] == "bogus" and data.get("none") is None
    # The refusal covers every brace token, not only lowercase typos: a name the
    # set does not know is reported as written, and an unnamed token quotes itself.
    assert data["unknownCased"] == "Index", data["unknownCased"]
    assert data["unknownNumeric"] == "1", data["unknownNumeric"]
    assert data["unknownSpacedName"] == "index_2", data["unknownSpacedName"]
    assert data["unknownEmpty"] == "{{}}", data["unknownEmpty"]
    assert data["unclosed"] == "compare {{ before", data["unclosed"]
    threw = data["threw"]
    assert threw["threw"] is True and threw["name"] == "TemplateError"
    cased = data["threwCased"]
    assert cased["threw"] is True and cased["name"] == "TemplateError", cased


def test_flag_parsing_equivalence_classes() -> None:
    cases = {row["input"]: row["result"] for row in value(run("params"), "params")["cases"]}  # type: ignore[union-attr]
    plan = cases["--every 5m --times 3 check the build"]
    assert plan["kind"] == "plan" and plan["plan"] == {"message": "check the build", "intervalMs": 300000, "maxRuns": 3}
    until = cases['--every 30s --until "tests pass" run the suite']
    assert until["plan"]["until"] == "tests pass" and until["plan"]["message"] == "run the suite"
    assert cases["--every=1m --message \"hi there\""]["plan"]["message"] == "hi there"
    assert cases["-e 2h -t 2 -m report"]["plan"] == {"message": "report", "intervalMs": 7200000, "maxRuns": 2}
    assert cases['--every 5m "quoted message"']["plan"]["message"] == "quoted message"
    assert cases["--every 5m -- everything --weird"]["plan"]["message"] == "everything --weird"
    for bad in ["--every 5m", "--every banana x", "--every 5m --times 0 x", "--every 5m --times two x",
                "--every 5m --bogus x", "--every 5m {{bogus}}", "--every 5m {{Index}}", "--every 5m {{}}",
                "--every 5m --message a b", '--every "5m']:
        assert cases[bad]["kind"] == "invalid", (bad, cases[bad])
        assert cases[bad]["error"]
    # A brace group that never closes is literal text, not a refused placeholder.
    assert cases["--every 5m compare {{ before"]["plan"]["message"] == "compare {{ before"
    for plain in ["check the build every 5 minutes", "keep an eye on the deploy"]:
        assert cases[plain]["kind"] == "not-parameterized", (plain, cases[plain])


def test_segmentation_and_schedule_phrase_stripping() -> None:
    data = value(run("candidates"), "candidates")
    stripped = {row["input"]: row["stripped"] for row in data["stripped"]}  # type: ignore[union-attr]
    assert stripped["keep an eye on the deploy every ten minutes"] == "keep an eye on the deploy"
    assert stripped["check the deploy every 10 minutes"] == "check the deploy"
    assert stripped["每5分钟检查部署"] == "检查部署"
    assert stripped["每小时汇报一次"] == "汇报一次"
    assert stripped["check the build"] is None
    assert stripped["report once a minute"] == "report"
    assert data["segments"] == ["check the deploy every 10 minutes", "stop when it is green"]
    keys = [row["key"] for row in data["withoutStop"]]  # type: ignore[union-attr]
    assert "without_schedule_and_stop" in keys
    assert all("stop when it is green" not in row["text"] for row in data["withoutStop"] if row["key"] != "full")  # type: ignore[union-attr]
    assert [row["key"] for row in data["singleCandidate"]] == ["full"]  # type: ignore[union-attr]


def test_scheduler_limit_skip_and_stop() -> None:
    data = value(run("scheduler"), "scheduler")
    assert data["beforeFirst"] == {"sent": [], "pending": 1}
    assert data["afterLimit"]["sent"] == ["tick 1/2", "tick 2/2"]
    assert data["afterLimit"]["active"] is False and data["afterLimit"]["pending"] == 0
    assert data["afterLimit"]["events"] == ["injected:1", "injected:2", "stopped:limit"]
    busy = data["whileBusy"]
    assert busy["sent"] == ["go"] and busy["skipped"] == 3 and busy["awaitingSettle"] is True
    after = data["afterSettle"]
    assert after["sent"] == ["go", "go"] and after["injections"] == 2 and after["skipped"] == 3
    stopped = data["afterStop"]
    assert stopped["sent"] == ["go"] and stopped["active"] is False and stopped["pending"] == 0
    assert data["restart"]["threw"] is True, "a stopped loop must not re-arm"
    assert data["firstStart"]["threw"] is True


def test_a_refused_injection_ends_the_loop_without_a_timer() -> None:
    """A delivery the host refuses is reported, and no timer survives it.

    `pi.sendUserMessage` returns void: Pi reports a turn that fails after it
    accepts the message on its own error channel, so the only refusal the loop
    can see is the synchronous throw raised for a captured extension API that has
    gone stale. The loop must never stay active with nothing pending.
    """
    data = value(run("delivery"), "delivery")
    assert data["events"] == ["undelivered:1", "stopped:delivery"], data
    assert data["sent"] == ["go"], data
    assert data["injections"] == 1, data
    assert data["active"] is False and data["pending"] == 0, data
    assert "stale" in str(data["undelivered"]), data

