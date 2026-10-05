"""Native Pi provider-boundary measurements, no network/model calls.

Run: uv run --no-project --with tiktoken python packages/monitor/tests/token-measurement.py --output /tmp/monitor-token.json
Counts are local tokenizer estimates of serialized Responses input/tools, not API billing.
All settings, command output and sessions are isolated in task-created temp directories.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

import tiktoken

from live_monitor import read_trace, stop

FIXTURE = Path(__file__).with_name("token-provider-fixture.ts")


def command(code: str) -> str:
    return "node -e " + shlex.quote(code)


def scenarios() -> list[dict]:
    noise = "for(let i=0;i<2000;i++)console.log('progress '+i+' '+('x'.repeat(70)));"
    return [
        dict(name="quick-small", command=command("console.log('DONE')"), result_pattern="^DONE$"),
        dict(name="noisy-success", command=command(noise + "console.log('DONE')"), result_pattern="^DONE$"),
        dict(name="noisy-failure", command=command(noise + "console.log('FAIL code=17');process.exitCode=17"),
             result_pattern="^DONE$", failure_pattern="^FAIL code=(?<code>\\d+)$"),
        dict(name="unique-10k-failure", command=command("for(let i=0;i<10000;i++)console.log('diagnostic '+i+' trace='+(i*7919).toString(16));console.log('FAIL code=23');process.exitCode=23"), result_pattern="^DONE$", failure_pattern="^FAIL code=(?<code>\\d+)$"),
        dict(name="result-missing", command=command(noise), result_pattern="^DONE$"),
        dict(name="timeout", command=command("console.log('still working');setTimeout(()=>{},10000)"),
             result_pattern="^DONE$", timeout_ms=100),
        dict(name="json-8k", command=command("console.log('DONE '+JSON.stringify({value:'a'.repeat(8192)}))"),
             result_pattern="^DONE (?<json>.*)$"),
        dict(name="json-24k", command=command("console.log('DONE '+JSON.stringify({value:'a'.repeat(24576)}))"),
             result_pattern="^DONE (?<json>.*)$"),
        dict(name="json-near-32k", command=command("console.log('DONE '+JSON.stringify({value:'a'.repeat(32730)}))"), result_pattern="^DONE (?<json>.*)$"),
        dict(name="json-escape-near-32k", command=command("console.log('DONE '+JSON.stringify({value:String.fromCharCode(92).repeat(16350)}))"), result_pattern="^DONE (?<json>.*)$"),
        dict(name="ordinary-captures-duplicated", command=command("console.log('a'.repeat(4096))"), result_pattern="^" + "".join(f"(?<c{i}>" for i in range(30)) + "a+" + ")" * 30 + "$"),
        dict(name="ansi-success", command=command("for(let i=0;i<2000;i++)console.log('\\x1b[31mwarning\\x1b[0m '+i);console.log('DONE')"), result_pattern="^DONE$"),
        dict(name="repeated-identical-tail", command=command("for(let i=0;i<2000;i++)console.log('retry transient connection failure');process.exitCode=2"),
             result_pattern="^DONE$"),
        dict(name="unicode-noisy-success", command=command("for(let i=0;i<2000;i++)console.log('处理中 '+i+' 数据同步尚未结束');console.log('DONE')"), result_pattern="^DONE$"),
    ]


def serialized(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def metrics(value: object, encodings: dict) -> dict:
    payload = serialized(value)
    return {"utf8_bytes": len(payload.encode()), **{name: len(enc.encode(payload)) for name, enc in encodings.items()}}


def measure(spec: dict, tool: str, loaded: bool, repeats: int, encodings: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="monitor-token-") as raw:
        root = Path(raw)
        tasktmp = root / "tasktmp"
        tasktmp.mkdir()
        agent = root / "agent"
        agent.mkdir()
        trace = root / "trace.jsonl"
        config = dict(spec, tool=tool, loaded=loaded, repeats=repeats)
        config["expected_status"] = spec.get("expected_status") or ("failure" if spec.get("failure_pattern") else "timeout" if spec["name"] == "timeout" else "failure" if spec["name"] == "repeated-identical-tail" else "result_missing" if spec["name"] == "result-missing" else "success")
        config["expected_length"] = {"json-8k": 8192, "json-24k": 24576, "json-near-32k": 32730, "json-escape-near-32k": 16350}.get(spec["name"])
        config["expected_parse_error"] = spec.get("expected_parse_error", spec["name"] == "json-escape-near-32k")
        if spec.get("completion") == "exit" and config["expected_parse_error"]:
            config["expected_status"] = "failure"
        config["expected_capture_truncation"] = spec["name"] in ("ordinary-captures-duplicated", "json-escape-near-32k")
        env = dict(os.environ, PI_CODING_AGENT_DIR=str(agent), PI_OFFLINE="1", PI_TELEMETRY="0",
                   TMPDIR=str(tasktmp), PI_MONITOR_TOKEN_SPEC=serialized(config), PI_MONITOR_TOKEN_TRACE=str(trace))
        args = ["pi", "--offline", "-ne", "-ns", "-np", "-nc", "--no-session", "-e", str(FIXTURE),
                "--model", "monitor-token-offline/scripted", "--tools", "bash,monitor_start" if loaded else "bash", "--print", "Verify the command outcome."]
        if tool == "codemode":
            args[args.index("--tools") + 1] = "bash,monitor_start,codemode"
            args.extend(["-e", "builtin:codemode"])
        child = subprocess.Popen(args, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            stdout, stderr = child.communicate(timeout=35)
            assert child.returncode == 0, stderr.decode(errors="replace")
            assert b"TOKEN_MEASUREMENT_COMPLETE" in stdout, stdout.decode(errors="replace")
            requests = read_trace(trace)
            assert len(requests) == repeats + 1, (spec["name"], tool, len(requests))
            assert all(request["hiddenFieldsExcluded"] for request in requests)
            results = [msg for msg in requests[-1]["messages"] if msg["role"] == "toolResult"]
            assert len(results) == repeats, (spec["name"], tool, results)
            if tool == "monitor_start":
                assert all("status=" in serialized(msg["content"]) for msg in results), results
            if tool == "codemode":
                assert all(not msg.get("isError") for msg in results), results
                assert all('"status"' in serialized(msg["content"]).replace('\\"', '"') for msg in results), results
            per_request = [metrics({"input": req["input"], "tools": req["tools"]}, encodings) for req in requests]
            generated = metrics([event["generated_content"] for event in requests], encodings)
            cumulative = {key: sum(req[key] for req in per_request) for key in per_request[0]}
            return {"name": spec["name"], "tool": tool, "plugin_loaded": loaded, "completion": spec.get("completion", "match"), "compact": spec.get("compact", False), "minimal_arguments": spec.get("minimal_arguments", False), "monitor_inactive": spec.get("monitor_inactive", False), "repeats": repeats,
                    "initial_request": per_request[0], "final_request": per_request[-1],
                    "equivalence": f"{repeats} real repeat executions; no polling savings inferred. When measured, the timeout scenario requests the same 100ms limit in both tools; monitor deadline includes startup/worker cost whereas bash timer covers process execution. Codemode validates required status/JSON integrity then emits a lossy predefined summary; escaped over-budget JSON is explicitly unparsed, not counted as lossless savings.",
                    "cumulative_input_estimates": cumulative,
                    "generated_assistant_content_estimates": generated,
                    "combined_input_output_estimates": {key: cumulative[key] + generated[key] for key in cumulative},
                    "tool_schemas": metrics(requests[0]["tools"], encodings),
                    "tool_results": metrics([msg["content"] for msg in results], encodings),
                    "terminal_texts": ["\n".join(block["text"] for block in msg["content"] if block["type"] == "text") for msg in results],
                    "tool_call_arguments": metrics([msg["content"] for msg in requests[-1]["messages"] if msg["role"] == "assistant"], encodings)}
        finally:
            stop(child)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--only-codemode", action="store_true")
    parser.add_argument("--strict-representative", action="store_true")
    parser.add_argument("--compact-six", action="store_true")
    parser.add_argument("--tiny-routes", action="store_true")
    args = parser.parse_args()
    if args.compact_six and (args.only_codemode or args.strict_representative):
        parser.error("--compact-six is a separate paired comparison")
    if args.tiny_routes and (args.only_codemode or args.strict_representative or args.compact_six):
        parser.error("--tiny-routes is a separate short-output comparison")
    encodings = {name: tiktoken.get_encoding(name) for name in ("cl100k_base", "o200k_base")}
    rows = []
    selected = scenarios()
    if args.tiny_routes:
        selected = [spec for spec in selected if spec["name"] == "quick-small"]
    if args.compact_six:
        selected = [spec for spec in selected if spec["name"] in (
            "quick-small", "noisy-success", "unique-10k-failure", "json-24k",
            "ordinary-captures-duplicated", "unicode-noisy-success")]
    if args.strict_representative:
        selected = [dict(spec, completion="exit") for spec in selected
                    if spec["name"] in ("quick-small", "noisy-success", "noisy-failure", "json-24k", "json-escape-near-32k")]
    routes = [("bash", False), ("monitor_start", True)] if args.compact_six else (
        [("codemode", True)] if args.only_codemode else [("bash", False), ("bash", True), ("monitor_start", True), ("codemode", True)])
    if args.tiny_routes:
        routes = [("bash", False), ("bash", True), ("monitor_start", True), ("monitor_start", True), ("monitor_start", True), ("bash", True)]
    for spec in selected:
        for route_index, (tool, loaded) in enumerate(routes):
            measured = dict(spec, compact=loaded) if args.compact_six else spec
            if args.tiny_routes:
                measured = dict(spec, compact=tool == "monitor_start", minimal_arguments=route_index in (3, 4), monitor_inactive=route_index == 5)
                if route_index == 4:
                    measured["completion"] = "exit"
            row = measure(measured, tool, loaded, args.repeats, encodings)
            if args.tiny_routes:
                row["route"] = ["bare-bash", "loaded-bash", "compact-monitor", "minimal-arguments-monitor", "minimal-arguments-exit", "inactive-bash"][route_index]
            rows.append(row)
            print(spec["name"], tool, loaded, row["cumulative_input_estimates"], flush=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"cases": rows, "status": "in_progress"}, ensure_ascii=False, indent=2) + "\n")
    report = {"method": "Native Pi 1.0 offline CLI; actual provider context; installed pi-ai Responses serializers; local tiktoken estimates of serialized input/tools, not billed tokens; no caching discount or real model routing evaluated.",
              "cases": rows, "encodings": list(encodings), "repeats": args.repeats}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
