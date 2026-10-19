"""The /loop decision seam, exercised against a real loopback endpoint."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
FIXTURE = Path(__file__).with_name("loop-decision-fixture.ts")


def run(scenario: str) -> dict[str, object]:
    result = subprocess.run(["bun", str(FIXTURE), scenario], cwd=REPO, capture_output=True,
                            text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, result.stdout
    return lines[0]


def test_semantic_plan_is_two_bounded_question_sets() -> None:
    case = run("semantic-plan")
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
    case = run("single-candidate")
    assert case["ok"] is True and case["hits"] == 1, case
    assert case["plan"] == {"message": "check the build", "intervalMs": 300000}, case["plan"]


def test_thresholds_and_rejections_fail_closed() -> None:
    low = run("low-confidence")
    assert low["failure"] == "low-confidence" and low["hits"] == 1, low
    # An unnamed cadence is no longer a failure: it takes the default cadence.
    unspecified = run("unspecified-interval")
    assert unspecified["ok"] is True and unspecified["intervalAssumed"] is True, unspecified
    assert unspecified["plan"]["intervalMs"] == 300000, unspecified
    malformed = run("malformed-choice")
    assert malformed["failure"] == "malformed", malformed
    assert "banana" in malformed["message"]
    credential = run("unauthorized")
    assert credential["failure"] == "unauthorized" and credential["hits"] == 1, credential
    missing = run("no-credential")
    assert missing["config"] is None, missing


def test_a_request_with_no_cadence_and_no_count_still_runs() -> None:
    """The request the user reported must run: "检查项目修改，总结".

    Nothing is undetermined once an unnamed cadence has a default, so the command
    decides the plan instead of refusing it. The loop repeats every five minutes
    until the user stops it, and the start notice says the cadence was assumed.
    """
    case = run("no-cadence-no-count")
    assert case["ok"] is True, case
    assert case["plan"] == {"message": "检查项目修改，总结", "intervalMs": 300000}, case["plan"]
    assert case["intervalAssumed"] is True, case
    assert case["mode"] == "semantic" and case["hits"] == 1, case


def test_a_count_with_no_cadence_takes_the_default_interval() -> None:
    """The resolved plan states the default cadence and says it was assumed.

    features/loop.feature: a run count bounds the loop, so a request that names no
    cadence is decided, not refused. The start notice tells the user the cadence
    was assumed.
    """
    case = run("count-without-cadence")
    assert case["ok"] is True, case
    assert case["plan"] == {"message": "输入Hi", "intervalMs": 300000, "maxRuns": 3}, case["plan"]
    assert case["intervalAssumed"] is True, case
    assert case["messageStripped"] is True, case
    # The count is code-matched metadata, so the message needs no judgment: one
    # request set, and no low-confidence refusal.
    assert case["mode"] == "semantic" and case["hits"] == 1, case
    first = case["requests"][0]
    assert first["questions"]["interval"]["criteria"]["unspecified"], first["questions"]["interval"]
    assert sorted(first["questions"]) == ["interval", "runs", "stop"], first["questions"]


def test_a_chinese_hour_cadence_is_listed_and_leaves_the_message() -> None:
    """The reported request: "每 2 个小时，清理一次非必要的文档、代码。"

    It planned every 1h with the cadence still inside the repeated message. Two
    causes, one per assertion: the listed intervals held nothing between 1h and 1d,
    so "2 个小时" resolved to the closest listed cadence, and the schedule pattern
    required the unit to follow the number, so "每 2 个小时" was never stripped.
    """
    case = run("chinese-hour-cadence")
    assert case["ok"] is True, case
    assert case["plan"] == {"message": "清理非必要的文档、代码", "intervalMs": 7200000}, case["plan"]
    assert case["intervalAssumed"] is None, case
    assert case["messageStripped"] is True, case
    # The metadata is code-matched, so the message is not a judgment: one request set.
    assert case["mode"] == "semantic" and case["hits"] == 1, case
    interval_criteria = case["requests"][0]["questions"]["interval"]["criteria"]
    assert "2h" in interval_criteria, interval_criteria
    assert case["requests"][0]["state"]["listed_intervals"] == [
        {"key": key, "seconds": seconds} for key, seconds in
        (("30s", 30), ("1m", 60), ("5m", 300), ("15m", 900), ("30m", 1800), ("1h", 3600),
         ("2h", 7200), ("4h", 14400), ("6h", 21600), ("8h", 28800), ("12h", 43200), ("1d", 86400))], \
        case["requests"][0]["state"]["listed_intervals"]


def test_a_count_segment_is_never_offered_as_a_stopping_condition() -> None:
    """The stop question must not see a segment that only states the run count.

    The real service chose "3 times" as the stopping condition for four count-only
    requests, which gave the plan an unjudgeable condition. Excluding it from the
    candidates is deterministic, so it is checked on the wire here.
    """
    case = run("count-segment")
    assert case["ok"] is True, case
    assert case["plan"] == {"message": "check the build", "intervalMs": 300000, "maxRuns": 3}, case["plan"]
    first = case["requests"][0]
    stop_criteria = first["questions"]["stop"]["criteria"]
    assert "3 times" not in json.dumps(stop_criteria), stop_criteria
    assert set(stop_criteria) == {"none", "segment_0"}, stop_criteria
    assert set(first["state"]["segments"][key]["text"] for key in range(len(first["state"]["segments"]))) == {
        "check the build every 5 minutes", "3 times"}, first["state"]["segments"]
    # The count is metadata code matched itself and no stopping condition came back,
    # so the message needs no judgment: one request set and no low-confidence refusal.
    assert case["hits"] == 1, case
    assert "message" not in first["questions"], first["questions"]


def test_a_count_segment_does_not_renumber_the_stop_keys() -> None:
    """The stop key space must match the segments the model was shown.

    Keys are indexes into `state.segments`, so filtering the list before emitting
    criteria renumbers them: with the count first, `segment_2` named the stopping
    segment in state while the criteria called it `segment_1`, and an answer using
    the key the model could see was rejected as unknown, failing the command.
    """
    case = run("count-not-last")
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
    # Every offered key must name the same text in state and in the criteria.
    for key, text in state_segments.items():
        if key in stop_criteria:
            assert text in str(stop_criteria[key]), (key, text, stop_criteria)
    assert "segment_0" not in stop_criteria, "a count segment must not be offered"


def test_stop_judgment_uses_the_explicit_threshold() -> None:
    met = run("stop-met")
    assert met["ok"] is True and met["verdict"] == {"met": True, "probability": 0.92}, met
    not_met = run("stop-not-met")
    assert not_met["verdict"] == {"met": False, "probability": 0.3}, not_met
    request = met["requests"][0]
    assert request["questions"]["met"]["type"] == "noul"
    assert request["state"]["condition"] == "the deploy is green"
    assert request["state"]["last_assistant_message"] == "The deploy is green in production."

