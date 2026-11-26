"""Deterministic, command, decision, and typecheck /loop contracts."""
from __future__ import annotations

import functools
import json
import subprocess
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
FIXTURE = Path(__file__).with_name("loop-core-fixture.ts")
COMMAND_FIXTURE = Path(__file__).with_name("loop-command-fixture.ts")
DECISION_FIXTURE = Path(__file__).with_name("loop-decision-fixture.ts")


@functools.lru_cache(maxsize=1)
def _all_core_cases() -> dict[str, dict[str, object]]:
    result = subprocess.run(["bun", str(FIXTURE)], cwd=REPO, capture_output=True,
                            text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
    return {value["scenario"]: value for line in result.stdout.splitlines() if line.strip()
            for value in [json.loads(line)]}


def run(*scenarios: str) -> dict[str, dict[str, object]]:
    cached = _all_core_cases()
    if all(name in cached for name in scenarios):
        return {name: cached[name] for name in scenarios}
    result = subprocess.run(["bun", str(FIXTURE), *scenarios], cwd=REPO, capture_output=True,
                            text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
    return {value["scenario"]: value for line in result.stdout.splitlines() if line.strip()
            for value in [json.loads(line)]}


@functools.lru_cache(maxsize=None)
def run_command_scenario(scenario: str) -> dict[str, object]:
    result = subprocess.run(["bun", str(COMMAND_FIXTURE), scenario], cwd=REPO, capture_output=True,
                            text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
    rows = {value["scenario"]: value for line in result.stdout.splitlines() if line.strip()
            for value in [json.loads(line)]}
    case = rows[scenario]
    assert case.get("ok") is True, case
    return case["value"]  # type: ignore[return-value]


def run_decision_scenario(scenario: str) -> dict[str, object]:
    result = subprocess.run(["bun", str(DECISION_FIXTURE), scenario], cwd=REPO, capture_output=True,
                            text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, result.stdout
    return lines[0]


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


def test_package_typecheck_covers_the_test_harnesses() -> None:
    config = (PACKAGE / "tsconfig.tests.json").read_text(encoding="utf-8")
    assert "tests/**/*.ts" in config, "test harnesses must be part of a type check"
    result = subprocess.run(
        ["bun", "x", "tsc", "--noEmit", "-p", "packages/loop/tsconfig.tests.json"],
        cwd=REPO, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _messages(rows: list[dict[str, object]]) -> list[str]:
    return [str(row["message"]) for row in rows]


def _said(rows: list[dict[str, object]], needle: str) -> bool:
    return any(needle in message for message in _messages(rows))


def test_starting_a_loop_runs_the_first_repetition_and_announces_it() -> None:
    data = run_command_scenario("start-flags")
    assert data["sent"] == ["CHECK THE BUILD"], "the first repetition arrives at start"
    assert data["status"] == ["Looping · every 1h · 1/2"], data["status"]
    assert data["lifecycle"] == [], "the notice must not be appended at start: " + json.dumps(data)
    content = str(data["notice"])
    assert "becomes the schedule" not in content, "a parameterized start states its own message: " + json.dumps(data)
    assert "every 1h" in content, content
    assert "as soon as each repetition settles" not in content, content
    assert "/loop stop" in content, content
    assert data["events"] == ["before_agent_start", "agent_end", "agent_settled", "session_start",
                              "session_shutdown"], data["events"]


def test_status_and_stop_report_state_and_clear_the_row() -> None:
    data = run_command_scenario("status-and-stop")
    assert _said(data["before"]["notifications"], "loop: no loop is running."), data["before"]
    assert _said(data["before"]["notifications"], "Usage:"), data["before"]
    assert data["started"]["status"] == ["Looping · every 1h · 1/3"], data["started"]
    assert _said(data["status"]["notifications"], "loop: Looping · every 1h · 1/3"), data["status"]
    assert data["stopped"]["status"] == [None], "stopping must clear the row: " + json.dumps(data["stopped"])
    assert _said(data["stopped"]["notifications"], "stopped after 1 injection (user)"), data["stopped"]
    assert _said(data["afterStop"], "loop: no loop is running."), data["afterStop"]


def test_every_refusal_names_the_cause_and_schedules_nothing() -> None:
    data = run_command_scenario("refusals-and-usage")
    assert _said(data["busy"], "already running"), data["busy"]
    assert data["busy"][0]["level"] == "warning"
    for key, needle in (("badDuration", "--every must be a duration"),
                        ("noMessage", "A message is required"),
                        ("unknownFlag", "Unknown option: --bogus"),
                        ("placeholderTypo", "Unknown placeholder: Index"),
                        ("freeWithoutCredential", "needs a decision credential"),
                        ("untilWithoutCredential", "--until needs a decision credential")):
        rows = data[key]
        assert _said(rows, needle), (key, rows)
        assert rows[0]["level"] == "error", (key, rows)
    headless = data["headless"]
    assert headless and headless[0]["customType"] == "loop-notice", headless
    assert headless[0]["options"] == {"triggerTurn": False}, headless


def test_a_free_request_echoes_the_request_then_analyzes() -> None:
    data = run_command_scenario("a-free-request-echoes-then-analyzes")
    assert data["messages"][0] == {"customType": "loop-request", "content": "输入3次Hi"}, data
    assert data["status"] == ["Analyzing · 输入3次Hi", "Looping · every 5m · 1/3"], data
    flags = run_command_scenario("start-flags")
    assert all(row["customType"] != "loop-request" for row in flags["lifecycle"] + [
        {"customType": None}]), flags
    assert data["status"][0].startswith("Analyzing ·"), data


def test_a_semantic_start_says_what_left_the_message() -> None:
    data = run_command_scenario("a-semantic-start-says-what-left-the-message")
    assert data["hits"] == ["interval,runs,stop"], data
    assert data["sent"] == ["输入Hi"], data
    content = str(data["notice"])
    assert "Message: 输入Hi." in content, content
    assert "becomes the schedule, not part of the message" in content, content
    assert "Cadence: every 5m" in content, content


def test_a_start_line_does_not_preempt_the_run_it_started() -> None:
    data = run_command_scenario("the-start-line-belongs-to-the-next-run")
    assert data["injections"] == ["WATCH"], data
    assert data["fromCommand"] == [], "the start must not preempt the command's own run: " + json.dumps(data)
    assert data["whileRunning"] == ["loop-lifecycle"], data
    assert data["beforeNextRun"] == [], "the repetition is already queued: " + json.dumps(data)
    assert data["second"] == [], "the line was already injected: " + json.dumps(data)


def test_only_the_loop_own_repetition_is_judged() -> None:
    data = run_command_scenario("only-the-repetition-is-judged")
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
    stopped = str(after["notifications"][-1]["message"])
    assert stopped.startswith("loop: stopped after ") and stopped.endswith("(condition)"), after


def test_a_refused_delivery_is_reported_once_and_clears_the_row() -> None:
    data = run_command_scenario("delivery-failure")
    assert data["reported"] is True, data
    assert len(data["notifications"]) == 1, data
    notice = data["notifications"][0]
    assert notice["level"] == "error", notice
    assert "refused a scheduled injection" in str(notice["message"]), notice
    assert "stale" in str(notice["message"]), notice
    assert data["sent"] == ["WATCH"], "the loop must stop after one refusal: " + json.dumps(data)
    assert data["status"][-1] is None, "the row must clear: " + json.dumps(data)


def test_semantic_plan_is_two_bounded_question_sets() -> None:
    case = run_decision_scenario("semantic-plan")
    assert case["ok"] is True, case
    assert case["plan"] == {"message": "check the deploy", "intervalMs": 300000,
                             "until": "stop when it is green"}, case["plan"]
    assert case["mode"] == "semantic" and case["hits"] == 2
    report = case["report"]
    assert report["model"] == "jev-1.13.0" and report["inputTokens"] == 18
    requests = case["requests"]
    first = requests[0]
    questions = first["questions"]
    assert sorted(questions) == ["interval", "runs", "stop"]
    for question in questions.values():
        assert question["type"] in {"noul", "choice", "score"}
    assert len(first["state"]["segments"]) == 2
    assert first["state"]["request"].startswith("check the deploy")
    interval_criteria = questions["interval"]["criteria"]
    assert "unspecified" in interval_criteria and "5m" in interval_criteria
    stop_criteria = questions["stop"]["criteria"]
    assert set(stop_criteria) == {"none", "segment_0", "segment_1"}
    assert "stop when it is green" in stop_criteria["segment_1"]
    message_criteria = requests[1]["questions"]["message"]["criteria"]
    assert "without_schedule_and_stop" in message_criteria
    assert requests[1]["state"]["stop_condition"] == "stop when it is green"


def test_one_candidate_needs_no_message_judgment() -> None:
    case = run_decision_scenario("single-candidate")
    assert case["ok"] is True and case["hits"] == 1, case
    assert case["plan"] == {"message": "check the build", "intervalMs": 300000}, case["plan"]


def test_thresholds_and_rejections_fail_closed() -> None:
    low = run_decision_scenario("low-confidence")
    assert low["failure"] == "low-confidence" and low["hits"] == 1, low
    unspecified = run_decision_scenario("unspecified-interval")
    assert unspecified["ok"] is True and unspecified["intervalAssumed"] is True, unspecified
    assert unspecified["plan"]["intervalMs"] == 300000, unspecified
    malformed = run_decision_scenario("malformed-choice")
    assert malformed["failure"] == "malformed", malformed
    assert "banana" in malformed["message"]
    credential = run_decision_scenario("unauthorized")
    assert credential["failure"] == "unauthorized" and credential["hits"] == 1, credential
    missing = run_decision_scenario("no-credential")
    assert missing["config"] is None, missing


def test_a_request_with_no_cadence_and_no_count_still_runs() -> None:
    case = run_decision_scenario("no-cadence-no-count")
    assert case["ok"] is True, case
    assert case["plan"] == {"message": "检查项目修改，总结", "intervalMs": 300000}, case["plan"]
    assert case["intervalAssumed"] is True, case
    assert case["mode"] == "semantic" and case["hits"] == 1, case


def test_a_count_with_no_cadence_takes_the_default_interval() -> None:
    case = run_decision_scenario("count-without-cadence")
    assert case["ok"] is True, case
    assert case["plan"] == {"message": "输入Hi", "intervalMs": 300000, "maxRuns": 3}, case["plan"]
    assert case["intervalAssumed"] is True, case
    assert case["messageStripped"] is True, case
    assert case["mode"] == "semantic" and case["hits"] == 1, case
    first = case["requests"][0]
    assert first["questions"]["interval"]["criteria"]["unspecified"], first["questions"]["interval"]
    assert sorted(first["questions"]) == ["interval", "runs", "stop"], first["questions"]


def test_a_chinese_hour_cadence_is_listed_and_leaves_the_message() -> None:
    case = run_decision_scenario("chinese-hour-cadence")
    assert case["ok"] is True, case
    assert case["plan"] == {"message": "清理非必要的文档、代码", "intervalMs": 7200000}, case["plan"]
    assert case["intervalAssumed"] is None, case
    assert case["messageStripped"] is True, case
    assert case["mode"] == "semantic" and case["hits"] == 1, case
    interval_criteria = case["requests"][0]["questions"]["interval"]["criteria"]
    assert "2h" in interval_criteria, interval_criteria
    assert case["requests"][0]["state"]["listed_intervals"] == [
        {"key": key, "seconds": seconds} for key, seconds in
        (("30s", 30), ("1m", 60), ("5m", 300), ("15m", 900), ("30m", 1800), ("1h", 3600),
         ("2h", 7200), ("4h", 14400), ("6h", 21600), ("8h", 28800), ("12h", 43200), ("1d", 86400))], \
        case["requests"][0]["state"]["listed_intervals"]


def test_a_count_segment_is_never_offered_as_a_stopping_condition() -> None:
    case = run_decision_scenario("count-segment")
    assert case["ok"] is True, case
    assert case["plan"] == {"message": "check the build", "intervalMs": 300000, "maxRuns": 3}, case["plan"]
    first = case["requests"][0]
    stop_criteria = first["questions"]["stop"]["criteria"]
    assert "3 times" not in json.dumps(stop_criteria), stop_criteria
    assert set(stop_criteria) == {"none", "segment_0"}, stop_criteria
    assert set(first["state"]["segments"][key]["text"] for key in range(len(first["state"]["segments"]))) == {
        "check the build every 5 minutes", "3 times"}, first["state"]["segments"]
    assert case["hits"] == 1, case
    assert "message" not in first["questions"], first["questions"]


def test_a_count_segment_does_not_renumber_the_stop_keys() -> None:
    case = run_decision_scenario("count-not-last")
    assert case["ok"] is True, case
    assert case["plan"] == {
        "message": "check the deploy", "intervalMs": 300000, "maxRuns": 3,
        "until": "stop when green"}, case["plan"]
    first = case["requests"][0]
    state_segments = {row["key"]: row["text"] for row in first["state"]["segments"]}
    assert state_segments == {
        "segment_0": "3 times",
        "segment_1": "check the deploy every 5 minutes",
        "segment_2": "stop when green"}, state_segments
    stop_criteria = first["questions"]["stop"]["criteria"]
    for key, text in state_segments.items():
        if key in stop_criteria:
            assert text in str(stop_criteria[key]), (key, text, stop_criteria)
    assert "segment_0" not in stop_criteria, "a count segment must not be offered"


def test_stop_judgment_uses_the_explicit_threshold() -> None:
    met = run_decision_scenario("stop-met")
    assert met["ok"] is True and met["verdict"] == {"met": True, "probability": 0.92}, met
    not_met = run_decision_scenario("stop-not-met")
    assert not_met["verdict"] == {"met": False, "probability": 0.3}, not_met
    request = met["requests"][0]
    assert request["questions"]["met"]["type"] == "noul"
    assert request["state"]["condition"] == "the deploy is green"
    assert request["state"]["last_assistant_message"] == "The deploy is green in production."

