from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from pi_cli import isolated_pi_command

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


def main() -> None:
    """Run real Pi loops against isolated projects; the provider is scripted."""
    node = subprocess.check_output(["node", "-p", "process.execPath"], text=True).strip()
    results: dict[str, object] = {}
    for mode in ("fresh", "inline", "failed", "retry"):
        with tempfile.TemporaryDirectory(prefix="pi-e2e-live-") as folder:
            cwd = Path(folder)
            (cwd / ".e2e").mkdir()
            (cwd / ".e2e/runner.json").write_text(json.dumps({"executable": node, "args": [str(PACKAGE / "tests/run-fixture.mjs"), "pass"], "adapterFiles": [str(PACKAGE / "tests/run-fixture.mjs")]}))
            if mode == "retry":
                (cwd / "adapter.mjs").write_text(f'process.argv[2]="unmet"; await import({json.dumps((PACKAGE / "tests/run-fixture.mjs").as_uri())});')
                (cwd / ".e2e/runner.json").write_text(json.dumps({"executable":node,"args":["adapter.mjs"],"adapterFiles":["adapter.mjs",str(PACKAGE / "tests/run-fixture.mjs")]}))
            (cwd / "test.feature").write_text("Feature: Test\nScenario: Before\nThen value is true\n")
            env = {**os.environ, "PI_E2E_CASE": mode, "PI_E2E_AUTH": "isolated-test-provider", "PI_TELEMETRY": "0"}
            process = subprocess.run([
                *isolated_pi_command(), "--no-extensions", "--no-skills", "--no-context-files",
                "--no-prompt-templates", "--no-session", "--offline", "--thinking", "off", "--mode", "json", "--print",
                "-e", str(PACKAGE / "index.ts"), "-e", str(PACKAGE / "tests/live-fixture.ts"),
                "--provider", "e2e-gate-scripted", "--model", "deterministic", "--tools", "write,e2e_verify,e2e_gate_probe",
                "Update this feature and verify its e2e acceptance.",
            ], cwd=cwd, env=env, capture_output=True, text=True, timeout=90)
            assert process.returncode == 0, process.stderr + process.stdout[-2000:]
            events = [json.loads(line) for line in process.stdout.splitlines() if line.startswith("{")]
            calls = [event for event in events if event.get("type") == "tool_execution_end" and event.get("toolName") == "e2e_verify"]
            assert len(calls) == (4 if mode == "retry" else 1), process.stdout[-4000:]
            details = calls[-1]["result"]["details"]
            if mode == "retry":
                assert [call["result"]["details"]["status"] for call in calls] == ["not_fulfilled","fulfilled","fulfilled","fulfilled"]
                assert all(call["result"]["details"]["verifiedRun"] for call in calls)
            boundaries = [json.loads(line) for line in (cwd / "boundaries.jsonl").read_text().splitlines()]
            checkpoints = [entry for boundary in boundaries for entry in boundary["entries"] if entry.get("customType") == "pi-e2e-checkpoint"]
            assert len(checkpoints) == (0 if mode in {"fresh","retry"} else 1), boundaries
            if mode == "failed":
                assert all("Inspect the current project instructions" in entry["content"] and "not_fulfilled" in entry["content"] for entry in checkpoints)
            assert details["verifiedRun"] is (mode in {"fresh","retry"}), details
            results[mode] = {"status": details["status"], "verifiedRun": details["verifiedRun"], "calls":len(calls), "checkpoints": len(checkpoints), "piExit": process.returncode}
    print(json.dumps({"provider": "scripted", "runtime": "real Pi --print", "results": results}, indent=2))


if __name__ == "__main__":
    main()
