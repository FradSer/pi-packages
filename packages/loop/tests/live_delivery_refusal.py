"""Explicit-run probe: can a tick ever reach a stale captured extension API?

Run from the repository root:

    uv run --no-project python packages/loop/tests/live_delivery_refusal.py

What it establishes: with the installed `pi` CLI, both session replacements that
invalidate a captured extension API (`ctx.reload()` and `ctx.newSession()`)
deliver a `session_shutdown` row to the loop before it is invalidated, with no
delivery attempt after that row, and the loop itself reports a stop with reason
`shutdown`. Both observations are required: the row shows which handler ran, and
the loop's own notice shows that handler stopped the runner. The control case
shows the loop still injecting when the replacement happens, and it must carry no
`session_shutdown` row, which is what makes the predicate discriminating.

What it does not establish: `ctx.fork()` and `ctx.switchSession()` are not
exercised, and a host that invalidates without a preceding `session_shutdown`
would make the loop's defensive refusal report load-bearing. Real-model and
remote-service behaviour is out of scope.

RPC mode is used because an extension `notify` becomes a structured record, so
the loop's own report is the evidence instead of a scraped screen. The trace and
the raw RPC records stay in the printed run directory.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time

PACKAGE = pathlib.Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
FIXTURE = pathlib.Path(__file__).with_name("delivery-refusal-fixture.ts")
LOOP_COMMAND = "/loop --every 1s --times 20 PROBE"


def run_case(root: pathlib.Path, name: str, replacement: str | None, observe: float) -> dict:
    trace = root / f"{name}.trace.jsonl"
    records_path = root / f"{name}.records.jsonl"
    env = dict(os.environ, HOME=str(root / f"{name}-home"), PI_CODING_AGENT_DIR=str(root / f"{name}-agent"),
               PI_OFFLINE="1", LOOP_REFUSAL_TRACE=str(trace), TERM="dumb")
    env.pop("TYPESAFE_API_KEY", None)
    for directory in (root / f"{name}-home", root / f"{name}-agent"):
        directory.mkdir(parents=True, exist_ok=True)
    child = subprocess.Popen(
        ["pi", "--mode", "rpc", "--no-session", "-ne", "-ns", "-np", "-nc",
         "-e", str(FIXTURE), "--model", "loop-probe/scripted"],
        cwd=REPO, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1,
    )
    records: list[dict] = []
    errors: list[str] = []

    def drain(stream, sink) -> None:  # type: ignore[no-untyped-def]
        for line in stream:
            line = line.strip()
            if not line:
                continue
            if sink is records:
                try:
                    sink.append(json.loads(line))
                    continue
                except json.JSONDecodeError:
                    pass
            sink.append(line)

    threading.Thread(target=drain, args=(child.stdout, records), daemon=True).start()
    threading.Thread(target=drain, args=(child.stderr, errors), daemon=True).start()

    def send(record: dict) -> None:
        child.stdin.write(json.dumps(record) + "\n")  # type: ignore[union-attr]
        child.stdin.flush()  # type: ignore[union-attr]

    def traced() -> list[dict]:
        if not trace.exists():
            return []
        return [json.loads(line) for line in trace.read_text().splitlines() if line.strip()]

    def attempts() -> int:
        return len([row for row in traced()
                    if row.get("kind") == "turn_start" and row.get("prompt") == "PROBE"])

    def wait_for(predicate, seconds: float) -> bool:  # type: ignore[no-untyped-def]
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.2)
        return predicate()

    case: dict = {"case": name}
    try:
        case["fixture_loaded"] = wait_for(lambda: any(row.get("kind") == "session_start" for row in traced()), 60)
        send({"id": "p1", "type": "prompt", "message": LOOP_COMMAND})
        case["delivered_before"] = attempts()
        case["two_turns"] = wait_for(lambda: attempts() >= 2, 45)
        case["delivered_before"] = attempts()
        if replacement:
            send({"id": "p2", "type": "prompt", "message": "/" + replacement})
        time.sleep(observe)
        case["delivered_after"] = attempts()
        # Snapshot before the child is terminated, so the teardown's own
        # session_shutdown row cannot appear in the control case's trace.
        case["trace"] = traced()
    finally:
        child.terminate()
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            child.kill()

    notices = [str(row.get("message", "")) for row in records
               if row.get("type") == "extension_ui_request" and row.get("method") == "notify"]
    case["notices"] = notices
    case["refused"] = [text for text in notices if "refused a scheduled injection" in text]
    case["stopped"] = [text for text in notices if "stopped after" in text]
    case["record_types"] = sorted({str(row.get("type")) + "/" + str(row.get("method", "")) for row in records})
    case["stderr_tail"] = errors[-8:]
    records_path.write_text("".join(json.dumps(row) + "\n" for row in records))
    return case


def judge(case: dict) -> list[str]:
    """Assert the mechanism, not just its symptom.

    The loop renders "stopped after ... (shutdown)" from both `session_shutdown`
    and `session_start` (src/index.ts:241 and :247), so a notice alone cannot show
    which handler stopped it. The distinguishing row is the fixture's
    `session_shutdown` entry, and the control case proves the predicate can fail:
    nothing stops that loop, so the row must be absent there.
    """
    failures: list[str] = []
    if not case["fixture_loaded"]:
        failures.append("the fixture never started")
    if not case["two_turns"]:
        failures.append("the control loop never delivered two turns, so the case is vacuous")
    kinds = [row.get("kind") for row in case["trace"]]
    shutdown = [index for index, kind in enumerate(kinds) if kind == "session_shutdown"]
    turns = [index for index, kind in enumerate(kinds) if kind == "turn_start"]
    if case["case"] == "control":
        if shutdown:
            failures.append("the control loop was stopped by session_shutdown: "
                            + json.dumps(case["trace"][-5:]))
        return failures
    # Two independent observations, both required. The fixture's row proves the
    # shutdown arrived through the right handler; the loop's own notice proves that
    # handler stopped the runner. A replacement that lands during an in-flight turn
    # leaves the runner busy, and the busy gate skips every later tick, so the row
    # check alone can pass while the loop never stopped.
    if not any("(shutdown)" in text for text in case["stopped"]):
        failures.append("the loop never reported a shutdown stop: " + json.dumps(case["notices"]))
    if not shutdown:
        failures.append("no session_shutdown row, so the loop cannot have stopped through it: "
                        + json.dumps(case["trace"][-5:]))
    elif turns and turns[-1] > shutdown[0]:
        failures.append("a delivery was attempted after session_shutdown: "
                        + json.dumps(case["trace"][-5:]))
    if case["refused"]:
        failures.append("a tick reached the invalidated API: " + json.dumps(case["refused"]))
    if case["delivered_after"] > case["delivered_before"]:
        failures.append("the loop kept injecting after the replacement: "
                        f"{case['delivered_before']} -> {case['delivered_after']}")
    return failures


def main() -> int:
    if shutil.which("pi") is None:
        print(json.dumps({"error": "the pi CLI is not installed"}))
        return 1
    root = pathlib.Path(tempfile.mkdtemp(prefix="loop-refusal-"))
    planned = [("control", None, 6.0), ("reload", "probe-reload", 12.0),
               ("new-session", "probe-new-session", 12.0)]
    wanted = sys.argv[1:]
    failures: list[str] = []
    for name, replacement, observe in planned:
        if wanted and name not in wanted:
            continue
        case = run_case(root, name, replacement, observe)
        case["failures"] = judge(case)
        failures.extend(f"{name}: {item}" for item in case["failures"])
        print(json.dumps({key: value for key, value in case.items() if key != "trace"}))
    print(json.dumps({"outputDir": str(root), "failures": failures}))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())