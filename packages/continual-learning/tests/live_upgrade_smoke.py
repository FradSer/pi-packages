"""Explicit real-Pi upgrade regression, not collected by pytest.

Only disposable project/agent roots are writable. Existing auth/model files are
copied (never symlinked), so refreshes cannot mutate the user's credentials.
No simulated provider or fixture result substitutes for real Pi tool execution.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from test_harness_upgrade_compatibility import LEGACY

PACKAGE = Path(__file__).resolve().parents[1]


def verify_upgrade() -> dict[str, object]:
    source = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi/agent"))
    provider, model = os.environ.get("PI_PROVIDER"), os.environ.get("PI_MODEL")
    if not provider or not model:
        configured = json.loads((source / "memory.json").read_text())
        provider, model = configured["provider"], configured["model"]
    with tempfile.TemporaryDirectory(prefix="harness-upgrade-live-") as directory:
        base = Path(directory)
        project, agent = base / "project", base / "agent"
        project.mkdir()
        agent.mkdir(mode=0o700)
        for name in ("auth.json", "models.json"):
            if (source / name).is_file():
                shutil.copyfile(source / name, agent / name)
                (agent / name).chmod(0o600)
        (agent / "settings.json").write_text(json.dumps({"packages": [], "defaultProvider": provider, "defaultModel": model}))
        (agent / "memory").mkdir()
        (agent / "memory/settings.json").write_text('{"autoMemory":false,"agentsMd":{"disabled":true}}')
        (project / ".pi").mkdir()
        target = project / ".pi/harness.local.json"
        before = json.dumps(LEGACY, indent=2) + "\n"
        target.write_text(before)
        (project / "packages/kit/src").mkdir(parents=True)
        helper = project / "packages/kit/src/fixture.ts"
        helper.write_text("const fixture = true;\n")
        session = base / "session.jsonl"
        prompt = (
            "This disposable project is an authorized Harness compatibility regression. "
            "Use exactly these native tools; never bypass any blocked call or change configuration. "
            "1. bash command `printf HARNESS_UPGRADE_BASH_OK`. "
            "2. write path `.memory.local/fixture.md` content `synthetic fixture`; this must be denied. "
            "3. edit path `packages/kit/src/fixture.ts`, oldText `const fixture = true;`, "
            "newText `createPackageAgentRun();`; this must be denied. "
            "4. write path `allowed.txt` content `HARNESS_UPGRADE_WRITE_OK`. "
            "These are synthetic test strings, not real Memory or source; attempts are explicitly authorized. "
            "After receiving all four tool results report them briefly and stop. Do not call read or other tools."
        )
        result = subprocess.run([
            "pi", "--offline", "--no-extensions", "-e", str(PACKAGE / "index.ts"),
            "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files",
            "--session", str(session), "--print", "--mode", "json", "--model", f"{provider}/{model}",
            "--tools", "bash,write,edit", prompt,
        ], cwd=project, env={**os.environ, "PI_CODING_AGENT_DIR": str(agent)}, text=True, capture_output=True, timeout=180)
        assert result.returncode == 0, result.stderr[-2000:]
        records = [json.loads(line) for line in session.read_text().splitlines() if line.strip()]
        messages = [entry["message"] for entry in records if entry.get("type") == "message"]
        errors = [message.get("errorMessage") for message in messages if message.get("stopReason") == "error"]
        assert not errors, errors
        results = [message for message in messages if message.get("role") == "toolResult"]
        def contains(tool: str, token: str, is_error: bool) -> bool:
            return any(message.get("toolName") == tool and message.get("isError") is is_error and token in json.dumps(message.get("content")) for message in results)
        assert contains("bash", "HARNESS_UPGRADE_BASH_OK", False), results
        assert contains("write", "canonical private memory root", True), results
        assert contains("edit", "approved structured run API", True), results
        assert contains("write", "Successfully wrote", False), results
        assert target.read_text() == before
        assert not (project / ".memory.local/fixture.md").exists()
        assert helper.read_text() == "const fixture = true;\n"
        assert (project / "allowed.txt").read_text() == "HARNESS_UPGRADE_WRITE_OK"
        return {"realPiPrint": True, "realBashAllowed": True, "legacyWriteBlocked": True,
                "legacyBatchedEditBlocked": True, "unrelatedWriteAllowed": True, "configBytesUnchanged": True,
                "toolResults": len(results), "model": f"{provider}/{model}"}


if __name__ == "__main__":
    print(json.dumps(verify_upgrade()))
