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
    # A listed cadence the free form can plan must be a cadence the flag form can
    # state, and the two must agree on its length.
    listed = data["listed"]  # type: ignore[union-attr]
    assert [row["key"] for row in listed] == ["30s", "1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"], listed
    for row in listed:
        assert row["parsed"] == row["ms"], row
        assert 1000 <= row["ms"] <= 86400000, row


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
    # A Chinese cadence is not always 每<number><unit>: the measure word and the 隔
    # form are the same cadence, and a pattern that missed them left the cadence
    # inside the repeated message.
    assert stripped["每 2 个小时，清理一次非必要的文档、代码。"] == "清理一次非必要的文档、代码"
    assert stripped["每2个小时，清理非必要的文档、代码"] == "清理非必要的文档、代码"
    assert stripped["每隔2个小时跑一次"] == "跑一次"
    assert stripped["每两个小时检查"] == "检查"
    assert data["segments"] == ["check the deploy every 10 minutes", "stop when it is green"]
    keys = [row["key"] for row in data["withoutStop"]]  # type: ignore[union-attr]
    assert "without_schedule_and_stop" in keys
    assert all("stop when it is green" not in row["text"] for row in data["withoutStop"] if row["key"] != "full")  # type: ignore[union-attr]
    assert [row["key"] for row in data["singleCandidate"]] == ["full"]  # type: ignore[union-attr]


def test_a_run_count_is_not_a_stopping_condition() -> None:
    """A count segment is the run limit, not a condition Pi can judge.

    Measured against the real service: four count-only requests had "3 times",
    "5 times", "20 times" or "10 times" chosen as the stopping condition, which
    left the plan with an unjudgeable condition and one decision request per
    settled turn. The count stays the `runs` question's job, and the message drops
    it.
    """
    data = value(run("candidates"), "candidates")
    counts = {row["input"]: row["isCount"] for row in data["counts"]}  # type: ignore[union-attr]
    for text in ("3 times", "five times", "20 x", "10 次", "twice"):
        assert counts[text] is True, (text, counts)
    for text in ("3 times a day", "3", "times", "check the build", "每5分钟"):
        assert counts[text] is False, (text, counts)
    assert data["counted"] == ["check the build every 5 minutes", "3 times"], data["counted"]
    # The count is stripped from the message, and a candidate is never the bare count
    # itself: the count segment is code-matched metadata, so it leaves one candidate
    # and no message question.
    texts = [row["text"] for row in data["withoutCount"]]  # type: ignore[union-attr]
    assert texts == ["check the build"], texts
    assert [row["key"] for row in data["withoutCount"]] == ["without_count"], data["withoutCount"]
    # A count that is not last must be dropped just the same, and the stop segment
    # it precedes must still be identifiable by its position in the full list.
    assert data["countedFirst"] == ["3 times", "check the deploy every 5 minutes", "stop when green"], data["countedFirst"]
    first = [row["text"] for row in data["withoutCountFirst"]]  # type: ignore[union-attr]
    assert first[0] == "check the deploy", first
    assert all(text != "3 times" for text in first), first


def test_a_count_with_no_cadence_still_runs() -> None:
    """A bounded request that names no cadence must run, and lose the count.

    A request such as "输入3次Hi" states a run count and nothing else. Refusing it
    made the common "do this N times" request unusable. The count already bounds
    the loop, so the default cadence cannot flood the session, and the count is
    scheduling metadata: the message keeps the user's own task words.
    """
    data = value(run("candidates"), "candidates")
    inline = {row["input"]: row["candidates"] for row in data["inlineCount"]}
    # Code matched the metadata, so the metadata-free text is the message and no
    # judgment is asked. Offering the request back invited a low-confidence answer
    # that refused the whole command.
    assert inline["输入3次Hi"] == [{"key": "without_count", "text": "输入Hi"}], inline["输入3次Hi"]
    assert inline["check the build 3 times"] == [{"key": "without_count", "text": "check the build"}], \
        inline["check the build 3 times"]
    assert inline["check the build"] == [{"key": "full", "text": "check the build"}], inline["check the build"]
    # A multiplier states the count too: "say hi * 3" repeats "say hi".
    assert inline["say hi * 3"] == [{"key": "without_count", "text": "say hi"}], inline["say hi * 3"]
    # A cadence and a count in one request both leave: the message is the task.
    assert inline["每 2 个小时，清理一次非必要的文档、代码。"] == [
        {"key": "without_count", "text": "清理非必要的文档、代码"}], \
        inline["每 2 个小时，清理一次非必要的文档、代码。"]
    # The measured request behind that rule: a schedule phrase and a count segment,
    # and no stopping condition. It was refused at 0.27 < 0.30 against the live
    # service, because the count segment put the raw request back as a choice.
    assert inline["watch the logs every minute, 10 times"] == [
        {"key": "without_count", "text": "watch the logs"}], \
        inline["watch the logs every minute, 10 times"]

    cases = {row["input"]: row["result"] for row in value(run("params"), "params")["cases"]}
    assert cases["--times 3 Hi"]["plan"] == {"message": "Hi", "intervalMs": 300000, "maxRuns": 3}, cases["--times 3 Hi"]
    assert cases["--times 3"]["kind"] == "invalid", cases["--times 3"]
    # The flag form takes the same default: no --every and no --times still runs.
    until = cases['--until "green" HI']
    assert until["kind"] == "plan" and until["plan"]["intervalMs"] == 300000, until
    assert until["plan"]["until"] == "green" and until["plan"]["message"] == "HI", until


# One row per cadence rule: input, intervalMs, maxRuns, until.
CADENCE_CASES: list[tuple[str, int, int | None, str | None]] = [
    ("--every 5m --times 3 check the build", 300000, 3, None),
    ("--every 30s --until \"tests pass\" run the suite", 30000, None, "tests pass"),
    ("-e 2h -t 2 -m report", 7200000, 2, None),
    ("--times 3 Hi", 300000, 3, None),
    ('--until "green" HI', 300000, None, "green"),
    ("--message HI", 300000, None, None),
    ("-m HI", 300000, None, None),
    ("--every 5m --message HI", 300000, None, None),
]

# A flag set that states no usable plan stays refused.
REFUSED_CASES = [
    "--times 0 x",
    "--times two x",
    "--every banana x",
    "--every 5m",
    "--message a b",
    "--every 5m --times 3 {{bogus}}",
    "--every 5m --times 3 {{}}",
    '--every "5m',
]


def test_every_cadence_case_is_decided_or_refused() -> None:
    """The cadence rule, one row per case the user can write.

    A cadence the user states is used. A cadence the user leaves out takes the
    five-minute default, whatever else the request states, and the plan reports
    that it was assumed. A flag set that cannot produce a plan is still refused.
    """
    cases = {row["input"]: row["result"] for row in value(run("params"), "params")["cases"]}
    for text, interval_ms, max_runs, until in CADENCE_CASES:
        result = cases[text]
        assert result["kind"] == "plan", (text, result)
        plan = result["plan"]
        assert plan["intervalMs"] == interval_ms, (text, plan)
        assert plan.get("maxRuns") == max_runs, (text, plan)
        assert plan.get("until") == until, (text, plan)
        assumed = result.get("intervalAssumed") is True
        assert assumed == ("--every" not in text and "-e" not in text), (text, result)
    for text in REFUSED_CASES:
        assert cases[text]["kind"] == "invalid", (text, cases[text])
        assert cases[text]["error"], (text, cases[text])


def test_scheduler_limit_skip_and_stop() -> None:
    data = value(run("scheduler"), "scheduler")
    # The first repetition arrives at start: a user who writes a loop expects to
    # see it run, not to wait one interval for evidence that it did.
    assert data["beforeFirst"] == {"sent": ["tick 1/2"], "pending": 1}
    assert data["afterLimit"]["sent"] == ["tick 1/2", "tick 2/2"]
    assert data["afterLimit"]["active"] is False and data["afterLimit"]["pending"] == 0
    # The second repetition still waits for the interval, and the tick that
    # arrives while the first one is unsettled is skipped and counted.
    assert data["afterLimit"]["events"] == ["injected:1", "skipped:2", "injected:2", "stopped:limit"]
    busy = data["whileBusy"]
    assert busy["sent"] == ["go"] and busy["skipped"] == 4 and busy["awaitingSettle"] is True
    after = data["afterSettle"]
    assert after["sent"] == ["go", "go"] and after["injections"] == 2 and after["skipped"] == 4
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

