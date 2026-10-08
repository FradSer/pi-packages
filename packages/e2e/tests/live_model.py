from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from pi_cli import isolated_pi_command

PACKAGE = Path(__file__).resolve().parents[1]


def main() -> None:
    """Exercise the installed Pi's real configured model, only in a temp project."""
    node = subprocess.check_output(["node", "-p", "process.execPath"], text=True).strip()
    runner = {"executable": node, "args": [str(PACKAGE / "tests/run-fixture.mjs"), "pass"]}
    with tempfile.TemporaryDirectory(prefix="pi-e2e-model-") as folder:
        cwd = Path(folder)
        (cwd / ".e2e").mkdir()
        (cwd / ".e2e/runner.json").write_text(json.dumps({**runner, "adapterFiles": [str(PACKAGE / "tests/run-fixture.mjs")]}))
        (cwd / "test.feature").write_text("Feature: Test\nScenario: Before\nThen value is true\n")
        prompt = 'In this isolated test project, use write to replace test.feature with "Feature: Test\\nScenario: Works\\nThen value is true\\n" (actual newlines). Then call e2e_verify with feature "test.feature", offline true, and runner ' + json.dumps(runner) + '. This authorized adapter executes a real local HTTP test and emits evidence. Read-only inspection is allowed. Do not modify the adapter or runner configuration. Report the result.'
        result = subprocess.run([
            *isolated_pi_command(), "--no-extensions", "--no-skills", "--no-context-files", "--no-prompt-templates",
            "--offline", "--no-session", "--mode", "json", "--print", "-e", str(PACKAGE / "index.ts"),
            "--tools", "read,write,e2e_verify",
            *(["--model", os.environ["PI_E2E_MODEL"], "--thinking", "off"] if os.environ.get("PI_E2E_MODEL") else []), prompt,
        ], cwd=cwd, env={**os.environ, "PI_TELEMETRY": "0"}, capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, result.stderr + result.stdout[-4000:]
        events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
        calls = [event for event in events if event.get("type") == "tool_execution_end" and event.get("toolName") == "e2e_verify"]
        assert calls, result.stdout[-4000:]
        details = calls[-1]["result"]["details"]
        assert details.get("status") == "fulfilled" and details.get("verifiedRun") is True, details
        final = [event["message"] for event in events if event.get("type") == "message_end" and event.get("message", {}).get("role") == "assistant"][-1]
        print(json.dumps({"runtime": "real Pi --print", "provider": final.get("provider"), "model": final.get("model"), "verdict": details}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
