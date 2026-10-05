"""Compare alternative report and full-payload orchestration designs offline."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import tiktoken


def load_runner(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(filename, Path(__file__).with_name(filename))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch", action="store_true")
    args = parser.parse_args()
    runner = load_runner("token-measurement.py")
    expanded = load_runner("expanded-token-measurement.py")
    cases = {case["name"]: case for case in expanded.scenarios()}
    cases["quick-small"] = runner.scenarios()[0]
    encodings = {name: tiktoken.get_encoding(name) for name in ("cl100k_base", "o200k_base")}
    names = ("quick-small", "json-repeat-512", "json-nonperiodic-2048") if args.batch else (
        "json-false", "json-repeat-512", "json-repeat-8192", "json-nonperiodic-24576", "late-failure", "invalid-json")
    rows = []
    for name in names:
        routes = [("bash", "bash", False, None), ("monitor", "monitor_start", True, None),
                  ("batch-full", "codemode", True, None), ("batch-bash", "bash", False, None)] if args.batch else [
                      ("bash", "bash", False, None), ("full-metadata", "monitor_start", True, "full-metadata"),
                      ("native-envelope", "monitor_start", True, "native-envelope")]
        for route, tool, loaded, variant in routes:
            case = dict(cases[name], compact=tool != "bash", completion="exit")
            if variant:
                case["report_variant"] = variant
            if route == "batch-full":
                case["batch_jobs"] = 8
            if route == "batch-bash":
                original = case["command"]
                code = f"const c=require('node:child_process');for(let i=0;i<8;i++){{const r=c.spawnSync({json.dumps(original)},{{shell:true,encoding:'utf8',timeout:5000,maxBuffer:1048576}});process.stdout.write(r.stdout||'');if(r.status!==0){{process.stderr.write(r.stderr||'');process.exit(r.status||1);}}}}"
                case.update(command=runner.command(code),batch_bash=True,timeout_ms=40000)
            repeats = 1 if route in ("batch-full", "batch-bash") else 8 if args.batch else 3
            row = runner.measure(case, tool, loaded, repeats, encodings)
            row["route"] = route
            row["equivalence"] = ("Eight real command executions per route; every required JSON payload validated. Direct routes use eight calls/nine provider requests. Codemode uses one call/two requests and Promise.all; grouped bash uses one call/two requests and sequential child execution with individual 5-second deadlines and an outer 40-second timer. Scheduling and outer timers differ. Full payloads returned; no lossy summary." if args.batch else "Three real executions/four provider requests per route, identical commands, labels and explicit five-second deadlines. Compare full metadata with native-envelope success presentation; all payloads/captures/statuses preserved. Failures and integrity warnings retain metadata.")
            row["executed_commands"] = 8 if args.batch else 3
            row["provider_requests"] = repeats + 1
            row["terminal_content_sha256"] = [hashlib.sha256(text.encode()).hexdigest()
                                               for text in row.pop("terminal_texts")]
            rows.append(row)
            report = dict(method="Native offline Pi provider contexts. Local tokenizer estimates, not billing or real-model evaluations. Same explicit deadlines and required complete JSON. Native-envelope removes eligible success metadata only. Batch runs eight jobs in one codemode call, validates terminal integrity and returns all required payloads; no lossy summary.",
                          experiment="batch-full-payload" if args.batch else "native-success-envelope",
                          cases=rows, native_sessions=len(rows),
                          executed_commands=sum(item["executed_commands"] for item in rows),
                          provider_requests=sum(item["provider_requests"] for item in rows), status="in_progress")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
            print(name, route, row["cumulative_input_estimates"], flush=True)
    report["status"] = "complete"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")


if __name__ == "__main__":
    main()
