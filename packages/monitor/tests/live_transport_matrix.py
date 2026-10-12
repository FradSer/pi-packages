"""Explicit native CLI/RPC/codemode accuracy matrix; all commands are synthetic."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import select
import shlex
import sys
import subprocess
import tempfile
import time

from live_monitor import pi_command, private_env, probe_directory, read_trace, stop

FIXTURE = Path(__file__).with_name("transport-matrix-fixture.ts")
REPO = Path(__file__).resolve().parents[3]


def job(code: str, pattern: str = "^DONE$", **options: object) -> dict:
    encoded = base64.b64encode(code.encode()).decode()
    return {"command": f"node -e 'eval(Buffer.from(\"{encoded}\",\"base64\").toString())'",
            "result_pattern": pattern, "timeout_ms": 3000, **options}


def cases() -> list[dict]:
    compiler = " ".join(shlex.quote(value) for value in [pi_command()[0], str(REPO / "node_modules/typescript/bin/tsc")])
    python = shlex.quote(sys.executable)
    success = job("for(let i=0;i<600;i++)console.log('PRIVATE_TRANSPORT_LOG '+i);console.log('DONE')")
    failure = job("console.error('FAIL code=7');process.exitCode=7", failure_pattern="^FAIL code=(?<code>\\d+)$")
    missing = job("console.log('DONEISH')")
    bad_json = job("console.log('RESULT {bad}')", "^RESULT (?<json>.*)$")
    good_json = job("console.log('RESULT '+JSON.stringify({count:7,value:false}))", "^RESULT (?<json>.*)$")
    examples = [
        ("success", success, "success"), ("failure", failure, "failure"),
        ("missing", missing, "result_missing"), ("invalid-json", bad_json, "success"),
        ("json-primitives", good_json, "success"),
        ("timeout", job("console.error('working');setTimeout(()=>{},10000)", timeout_ms=200), "timeout"),
    ]
    result = [{"name": f"rpc-{name}", "mode": "rpc", "route": "direct", "jobs": [args], "expected": [status]}
              for name, args, status in examples]
    for name, args, status in examples[:3]:
        result.append({"name": f"rpc-mixed-{name}", "mode": "rpc", "route": "mixed", "jobs": [args], "expected": [status]})
    for name, args, status in [examples[0], examples[1], examples[4]]:
        result.append({"name": f"rpc-nested-{name}", "mode": "rpc", "route": "nested", "jobs": [args], "expected": [status]})
    parallel = [job(f"setTimeout(()=>console.log('{token}'),{delay})", failure_pattern="^FAIL$")
                for token, delay in [("DONE", 70), ("FAIL", 240), ("DONE", 420)]]
    for mode in ["rpc", "print"]:
        result.append({"name": f"{mode}-parallel", "mode": mode, "route": "direct", "jobs": parallel, "expected": ["success", "failure", "success"]})
        result.append({"name": f"{mode}-codemode-parallel", "mode": mode, "route": "codemode", "jobs": parallel, "expected": ["success", "failure", "success"]})
    result.append({"name": "rpc-stop", "mode": "rpc", "route": "stop", "jobs": [job("setTimeout(()=>{},10000)")], "expected": ["stopped"]})
    for name, workflow, expected in [
        ("monitor-typecheck", f"{compiler} --noEmit --target ES2022 --module ESNext --moduleResolution bundler --allowImportingTsExtensions --strict --skipLibCheck packages/monitor/index.ts", "success"),
        ("monitor-regressions", f"{python} -m pytest packages/monitor/tests/test_monitor_token_boundary.py -q", "success"),
        ("compiler-diagnostic", f"{compiler} --noEmit --strict --skipLibCheck __INVALID_FIXTURE__", "failure"),
    ]:
        command = f"if (cd '{REPO}' && {workflow}); then printf 'FINAL {{\"ok\":true}}\\n'; else code=$?; printf 'FAILED {{\"ok\":false,\"exitCode\":%s}}\\n' \"$code\"; exit \"$code\"; fi"
        result.append({"name": f"print-real-{name}", "mode": "print", "route": "direct", "expected": [expected],
                       "jobs": [{"command": command, "result_pattern": "^FINAL (?<json>.*)$", "failure_pattern": "^FAILED (?<json>.*)$", "timeout_ms": 20000}]})
    strict = [
        ("half-line", job("process.stdout.write('DONE');setTimeout(()=>process.stdout.write('ISH\\n'),350)"), "result_missing"),
        ("late-nonzero", job("console.log('DONE');process.exitCode=7"), "failure"),
        ("invalid-json", bad_json, "failure"),
        ("json-primitives", good_json, "success"),
        ("late-failure", job("console.log('DONE');setTimeout(()=>console.error('FAIL'),100)", failure_pattern="^FAIL$"), "failure"),
        ("candidate-timeout", job("console.log('DONE');setTimeout(()=>{},10000)", timeout_ms=300), "timeout"),
        ("EOF", job("process.stdout.write('DONE')"), "success"),
        ("signal", job("console.log('DONE');process.kill(process.pid,'SIGTERM')"), "failure"),
    ]
    for mode in ["rpc", "print"]:
        for name, args, expected in strict:
            result.append({"name": f"{mode}-exit-{name}", "mode": mode, "route": "direct", "expected": [expected],
                           "jobs": [{**args, "completion": "exit"}]})
    return result


def run_case(spec: dict) -> dict:
    with probe_directory(prefix="monitor-transport-") as raw:
        root = Path(raw)
        agent = root / "agent"
        agent.mkdir()
        spec = json.loads(json.dumps(spec))
        if spec["name"] == "print-real-compiler-diagnostic":
            invalid = root / "intentionally-invalid.ts"
            invalid.write_text('const value: number = "invalid type";\n')
            spec["jobs"][0]["command"] = spec["jobs"][0]["command"].replace("__INVALID_FIXTURE__", str(invalid))
        config = root / "spec.json"
        config.write_text(json.dumps(spec))
        trace = root / "trace.jsonl"
        env = {**private_env(root),
               "MONITOR_TRANSPORT_SPEC": str(config), "MONITOR_TRANSPORT_TRACE": str(trace)}
        args = pi_command() + ["--offline", "--no-approve", "-ne", "-ns", "-np", "-nc", "--no-session", "-e", str(FIXTURE),
                "--model", "monitor-transport-offline/scripted"]
        if spec["route"] == "codemode":
            args += ["-e", "builtin:codemode", "--tools", "monitor_start,codemode"]
        args += ["--mode", "rpc"] if spec["mode"] == "rpc" else ["--print", "Verify the synthetic outcome."]
        child = subprocess.Popen(args, cwd=root, env=env, stdin=subprocess.PIPE if spec["mode"] == "rpc" else subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        output = bytearray()
        try:
            if spec["mode"] == "rpc":
                child.stdin.write(b'{"type":"prompt","message":"Verify the synthetic outcome."}\n')
                child.stdin.flush()
                deadline = time.monotonic() + 30
                stopped = False
                while time.monotonic() < deadline:
                    if select.select([child.stdout], [], [], 0.03)[0]:
                        chunk = os.read(child.stdout.fileno(), 65536)
                        if not chunk:
                            break
                        output.extend(chunk)
                    records = read_trace(trace)
                    starts = [r for r in records if r["kind"] == "tool_result" and r["event"]["toolName"] == "monitor_start"]
                    if spec["route"] == "stop" and starts and not stopped:
                        child.stdin.write(b'{"type":"prompt","message":"Stop the synthetic monitor."}\n')
                        child.stdin.flush()
                        stopped = True
                    terminals = [r for r in records if r["kind"] == "send"]
                    requests = [r for r in records if r["kind"] == "request"]
                    expected_requests = 3 if spec["route"] == "stop" else 2
                    background = spec["route"] == "direct"
                    if len(requests) >= expected_requests and (not background or len(terminals) == len(spec["jobs"])):
                        time.sleep(0.15)
                        break
                else:
                    raise AssertionError(f"RPC watchdog: {spec['name']}")
            else:
                stdout, stderr = child.communicate(timeout=30)
                output.extend(stdout)
                (root / "stderr.bin").write_bytes(stderr)
                assert child.returncode == 0, stderr.decode(errors="replace")
                assert b"TRANSPORT_MATRIX_READY" in stdout
            records = read_trace(trace)
            requests = [r for r in records if r["kind"] == "request"]
            sends = [r["message"] for r in records if r["kind"] == "send"]
            results = [r["event"] for r in records if r["kind"] == "tool_result" and r["event"]["toolName"] == "monitor_start"]
            assert len(results) == len(spec["jobs"]), (spec["name"], records)
            assert all(not result["isError"] for result in results), results
            if spec["route"] == "stop":
                controls = [r["event"] for r in records if r["kind"] == "tool_result" and r["event"]["toolName"] == "monitor_stop"]
                assert controls[0]["details"]["stopped"] == 1 and not sends
                assert len(requests) == 3
            else:
                asynchronous = spec["mode"] == "rpc" and spec["route"] == "direct"
                terminal = [message["details"] for message in sends] if asynchronous else [result["details"] for result in results]
                assert len(terminal) == len(spec["jobs"])
                identities = [item["monitorId"] for item in terminal]
                assert len(set(identities)) == len(identities)
                observed = {item["monitorId"]: item["result"] for item in terminal}
                for result in results:
                    # Nested concurrent tools finish in any order; correlate
                    # the contract input and stable ID rather than list position.
                    index = next(i for i, args in enumerate(spec["jobs"]) if args["command"] == result["input"]["command"])
                    expected = spec["expected"][index]
                    value = observed[result["details"]["monitorId"]]
                    assert value["status"] == expected, (spec["name"], value)
                    if "invalid-json" in spec["name"]:
                        assert value["resultParseError"] and "result" not in value
                    if "json-primitives" in spec["name"]:
                        assert value["result"] == {"count": 7, "value": False}
                    if spec["name"].startswith("print-real-"):
                        assert value["result"]["ok"] == (expected == "success")
                        if expected == "failure":
                            assert value["result"]["exitCode"] != 0
                            assert "TS2322" in json.dumps(value["output"]), value
                assert len(sends) == (len(spec["jobs"]) if asynchronous else 0)
                if asynchronous:
                    assert 2 <= len(requests) <= len(spec["jobs"]) + 1
                else:
                    assert len(requests) == 2
                if spec["expected"] == ["success"]:
                    result_context = [m["content"] for r in requests[1:] for m in r["messages"] if m["role"] != "assistant"]
                    assert "PRIVATE_TRANSPORT_LOG" not in json.dumps(result_context), spec["name"]
            return {"name": spec["name"], "passed": True, "provider_requests": len(requests),
                    "monitors": len(spec["jobs"]), "custom_terminal_messages": len(sends)}
        finally:
            stop(child)
            if spec["mode"] != "rpc":
                stdout, stderr = child.communicate()
                output = bytearray(stdout)
                (root / "stderr.bin").write_bytes(stderr)
            (root / "stdout.bin").write_bytes(output)
            if spec["mode"] == "rpc":
                assert child.stderr is not None
                (root / "stderr.bin").write_bytes(child.stderr.read())


def run_matrix() -> dict:
    outcomes = []
    for spec in cases():
        row = run_case(spec)
        outcomes.append(row)
        print(json.dumps(row), flush=True)
    return {"cases": len(outcomes), "monitors": sum(row["monitors"] for row in outcomes), "observed": outcomes}


if __name__ == "__main__":
    report = run_matrix()
    Path(__file__).with_name("transport-results-current.json").write_text(json.dumps(report, indent=2) + "\n")
