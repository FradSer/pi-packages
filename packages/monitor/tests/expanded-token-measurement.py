"""Expanded native offline token/accuracy matrix; no model or network calls."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import tiktoken

MODULE = Path(__file__).with_name("token-measurement.py")
SPEC = importlib.util.spec_from_file_location("monitor_token_measurement", MODULE)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def scenarios() -> list[dict]:
    cases = []
    for size in (0, 1, 16, 128, 512, 2048, 8192, 24576):
        value = "a" * size
        cases.append(dict(name=f"json-repeat-{size}", command=runner.command(
            f"console.log('DONE '+JSON.stringify({{value:'a'.repeat({size})}}))"),
            result_pattern="^DONE (?<json>.*)$", expected_result={"value": value}))
    for size in (128, 512, 2048, 8192, 24576):
        # Deterministic, nonperiodic ASCII; no random data or private fixtures.
        value = "".join(hashlib.sha256(str(index).encode()).hexdigest()
                        for index in range((size + 63) // 64))[:size]
        code = f"const c=require('node:crypto');let v='';for(let i=0;v.length<{size};i++)v+=c.createHash('sha256').update(String(i)).digest('hex');console.log('DONE '+JSON.stringify({{value:v.slice(0,{size})}}))"
        cases.append(dict(name=f"json-nonperiodic-{size}", command=runner.command(code),
                          result_pattern="^DONE (?<json>.*)$", expected_result={"value": value}))
    for lines in (1, 8, 32, 128, 512, 2048):
        cases.append(dict(name=f"unique-progress-{lines}", command=runner.command(
            f"for(let i=0;i<{lines};i++)console.log('progress '+i+' trace='+(i*7919).toString(16));console.log('DONE')"),
            result_pattern="^DONE$"))
    for name, value in (("false", False), ("null", None), ("zero", 0), ("empty", ""),
                        ("unicode", {"value": "同步完成\u2028下一步\u2029中文😀"}),
                        ("c1", {"value": "start\u0085next\u009b31mend\u009dOSC\u009ctail"})):
        payload = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        cases.append(dict(name=f"json-{name}", command=runner.command(
            f"console.log('DONE '+JSON.stringify({payload}))"),
            result_pattern="^DONE (?<json>[\\s\\S]*)$" if name in ("unicode", "c1") else "^DONE (?<json>.*)$", expected_result=value))
    cases.extend([
        dict(name="stderr-success", command=runner.command("console.error('DONE')"), result_pattern="^DONE$"),
        dict(name="EOF-success", command=runner.command("process.stdout.write('DONE')"), result_pattern="^DONE$"),
        dict(name="empty-capture", command=runner.command("console.log('DONE ' )"), result_pattern="^DONE (?<value>.*)$", expected_captures={"value": ""}),
        dict(name="late-nonzero", command=runner.command("console.log('DONE');process.exitCode=7"), result_pattern="^DONE$", expected_status="failure"),
        dict(name="late-failure", command=runner.command("console.log('DONE');setTimeout(()=>console.error('FAIL code=9'),40)"), result_pattern="^DONE$", failure_pattern="^FAIL code=(?<code>\\d+)$", expected_status="failure", expected_captures={"code": "9"}),
        dict(name="invalid-json", command=runner.command("console.log('DONE {bad}')"), result_pattern="^DONE (?<json>.*)$", expected_status="failure", expected_parse_error=True),
        dict(name="no-output", command=runner.command("process.exitCode=0"), result_pattern="^DONE$", expected_status="result_missing"),
        dict(name="partial-near-match", command=runner.command("process.stdout.write('DONE');setTimeout(()=>console.log('ISH'),40)"), result_pattern="^DONE$", expected_status="result_missing"),
    ])
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--resume", action="store_true", help="Continue a matching partial report without rerunning completed cases")
    parser.add_argument("--case", action="append", help="Select one workload; repeat to select more")
    args = parser.parse_args()
    selected = [case for case in scenarios() if not args.case or case["name"] in args.case]
    assert selected and (not args.case or set(args.case) <= {case["name"] for case in selected}), "Unknown workload"
    encodings = {name: tiktoken.get_encoding(name) for name in ("cl100k_base", "o200k_base")}
    rows = []
    report = {}
    if args.resume:
        previous = json.loads(args.output.read_text())
        report = previous
        assert previous["repeats"] == args.repeats and previous["workloads"] == len(selected)
        rows = previous["cases"]
        assert previous["native_sessions"] == len(rows)
        assert all(row["repeats"] == args.repeats for row in rows)
    completed = {(row["name"], row["route"]) for row in rows}
    assert len(completed) == len(rows), "Duplicate completed cases"
    routes = [("bare-bash", "bash", False, False), ("loaded-bash", "bash", True, False),
              ("compact-exit", "monitor_start", True, False), ("inactive-bash", "bash", True, True)]
    assert completed <= {(case["name"], route[0]) for case in selected for route in routes}, "Unknown completed cases"
    for case in selected:
        for route, tool, loaded, inactive in routes:
            if (case["name"], route) in completed:
                continue
            # Keep the same explicit 5-second deadline and label across monitor routes.
            spec = dict(case, completion="exit", compact=tool == "monitor_start", monitor_inactive=inactive)
            row = runner.measure(spec, tool, loaded, args.repeats, encodings)
            row["route"] = route
            row["terminal_content_sha256"] = [hashlib.sha256(text.encode()).hexdigest()
                                               for text in row.pop("terminal_texts")]
            row["accuracy_oracle"] = {key: value for key, value in case.items() if key.startswith("expected_")}
            if "expected_result" in row["accuracy_oracle"]:
                value = row["accuracy_oracle"].pop("expected_result")
                row["accuracy_oracle"]["expected_result_sha256"] = hashlib.sha256(runner.serialized(value).encode()).hexdigest()
            rows.append(row)
            report = dict(method="Native Pi offline scripted provider; actual serialized input/tools; local estimates, not billing or real-model accuracy. Strict exit completion; full payload equality and native tool-call/RLE assertions. Progress logs intentionally omitted by monitor; required JSON retained.",
                          workloads=len(selected), native_sessions=len(rows), executed_commands=len(rows)*args.repeats,
                          provider_requests=len(rows)*(args.repeats+1), repeats=args.repeats, cases=rows,
                          status="in_progress")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
            print(case["name"], route, row["cumulative_input_estimates"], flush=True)
    report["status"] = "complete"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")


if __name__ == "__main__":
    main()
