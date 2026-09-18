"""Explicit real-Pi verification in disposable project and agent directories.

Not collected by pytest or CI. Reuses configured authentication without editing
user settings, Memory, or Harness files. Learning failures are never replaced
with fixtures; runtime fixtures are tested separately.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


def run_pi(project: Path, agent: Path, probe: Path, prompt: str, tools: str) -> dict:
    """Run a real task and inspect its persisted, synthetic test messages."""
    model = json.loads((agent / "memory.json").read_text())
    session = project.parent / "session.jsonl"
    result = subprocess.run(
        [
            "pi", "--offline", "--no-extensions", "-e", str(probe),
            "-e", str(PACKAGE / "index.ts"), "--no-skills", "--no-prompt-templates",
            "--no-themes", "--no-context-files", "--session", str(session),
            "--print", "--mode", "json", "--model", f"{model['provider']}/{model['model']}",
            "--tools", tools, prompt,
        ],
        cwd=project, env={**os.environ, "PI_CODING_AGENT_DIR": str(agent)},
        capture_output=True, text=True, timeout=480,
    )
    assert result.returncode == 0, result.stderr[-1500:]
    records = [json.loads(line) for line in session.read_text().splitlines() if line.strip()]
    messages = [entry["message"] for entry in records if entry.get("type") == "message"]
    errors = [message.get("errorMessage") for message in messages if message.get("stopReason") == "error"]
    assert not errors, errors
    assistant = [message for message in messages if message.get("role") == "assistant"]
    assert assistant, "No assistant response from live Pi"
    final = "\n".join(block.get("text", "") for block in assistant[-1]["content"] if block.get("type") == "text")
    log = project.parent / "notifications.jsonl"
    return {"final": final, "records": records, "messages": messages,
            "notifications": log.read_text() if log.exists() else "No extension notifications"}


def prepare(base: Path, auto_memory: bool) -> tuple[Path, Path, Path]:
    """Copy auth privately so runtime refreshes cannot alter source files."""
    project, agent = base / "project", base / "agent"
    project.mkdir()
    agent.mkdir(mode=0o700)
    source = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi" / "agent"))
    for name in ("auth.json", "models.json"):
        if (source / name).is_file():
            shutil.copyfile(source / name, agent / name)
            (agent / name).chmod(0o600)
    model = json.loads((source / "memory.json").read_text())
    (agent / "memory.json").write_text(json.dumps({"provider": model["provider"], "model": model["model"]}))
    (agent / "settings.json").write_text(json.dumps({
        "defaultProvider": model["provider"], "defaultModel": model["model"], "packages": [],
    }))
    (agent / "memory").mkdir()
    (agent / "memory" / "settings.json").write_text(json.dumps({
        "autoMemory": auto_memory, "agentsMd": {"disabled": True},
    }))
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    log = base / "notifications.jsonl"
    probe = base / "notifications.ts"
    probe.write_text(
        'import fs from "node:fs"; export default function(pi) {'
        ' pi.on("session_start", (_event, ctx) => {'
        ' const original = ctx.ui.notify; ctx.ui.notify = (message, type) => {'
        f' fs.appendFileSync({json.dumps(str(log))}, JSON.stringify({{message,type}}) + "\\n");'
        ' original(message, type); }; }); }'
    )
    return project, agent, probe


def verify_learned_rule(project: Path) -> dict:
    """Require a real learned declaration and execute harmless evaluator cases."""
    rule_file = project / ".pi" / "harness.json"
    assert rule_file.exists(), "Learning did not write project harness.json"
    config = json.loads(rule_file.read_text())
    assert config.get("rules"), "Learning did not produce flat project harness rules"
    assert config.get("learnedRules"), "Learning did not bind rule ownership"
    assert not (project / ".pi" / "harness.local.json").exists(), "Learning wrote personal configuration"
    source = (
        f'import {{ mergeLayers, evaluateBash }} from {json.dumps(str(PACKAGE / "extensions/guardrail-engine.ts"))};'
        f'const layer=JSON.parse(await Bun.file({json.dumps(str(rule_file))}).text());'
        'const config=mergeLayers([{...layer,source:"project"}]);'
        'console.log(JSON.stringify({blocked:evaluateBash(config,"retired-smoke-compiler build").decision,'
        'allowed:evaluateBash(config,"printf safe").decision}));'
    )
    result = subprocess.run(["bun", "-e", source], cwd=REPO, text=True, capture_output=True, check=True)
    decisions = json.loads(result.stdout)
    assert decisions == {"blocked": "block", "allowed": "execute"}, decisions
    return decisions


def verify_learning() -> dict:
    """Learn a private preference and a project rule, with verified receipts."""
    with tempfile.TemporaryDirectory(prefix="continual-learning-live-") as raw:
        project, agent, probe = prepare(Path(raw), True)
        result = run_pi(project, agent, probe,
                       "For this project, I prefer concise progress updates. Also, never run "
                       "retired-smoke-compiler through bash: it is prohibited in this project. "
                       "Both statements are durable requirements for future tasks. Reply only: acknowledged.", "read")
        memories = [file for file in (agent / "memory").glob("*/*.md") if file.name != "MEMORY.md"]
        assert any("concise" in file.read_text().lower() for file in memories), result["notifications"]
        assert not any("concise" in file.read_text().lower() for file in (project / ".memory").glob("*.md")), "Preference leaked into shared memory"
        receipts = [json.loads(file.read_text()) for file in (agent / "memory" / "runs").glob("*/*/learning-pipeline-receipt.json")]
        try:
            decisions = verify_learned_rule(project)
        except AssertionError as error:
            raise AssertionError(f"{error}; notifications={result['notifications']}; receipts={json.dumps(receipts)}") from error
        assert receipts, result["notifications"]
        attempts = {(attempt["phase"], attempt["outcome"]) for attempt in receipts[-1]["attempts"]}
        assert {("memory", "applied"), ("harness", "applied")} <= attempts, receipts[-1]
        assert receipts[-1]["operations"] >= 2, receipts[-1]
        return {"privatePreference": True, "learnedConstraint": decisions, "verifiedReceipts": True}


def verify_runtime() -> dict:
    """Exercise flat text guidance and a real, harmless Bash result."""
    with tempfile.TemporaryDirectory(prefix="continual-runtime-live-") as raw:
        project, agent, probe = prepare(Path(raw), False)
        (project / ".pi").mkdir()
        (project / ".pi" / "harness.json").write_text(json.dumps({"rules": [
            {"id": "smoke-context", "text": "SMOKE_CONTEXT", "instructions": "For SMOKE_CONTEXT, report the command output accurately."},
            {"id": "smoke-bash", "bash": "^printf", "message": "Report the harmless smoke command's actual output."},
        ]}))
        result = run_pi(project, agent, probe,
                       "SMOKE_CONTEXT: Run the harmless command `printf CL_RUNTIME_OK` once with bash and report its output.", "bash")
        guidance = [entry for entry in result["records"] if entry.get("customType") == "harness-guidance"]
        assert guidance and "Only for subjects matching" in guidance[0]["content"], result["notifications"]
        tool_results = [message for message in result["messages"] if message.get("role") == "toolResult"]
        assert any("CL_RUNTIME_OK" in json.dumps(message["content"]) and "[harness-bash-note]" in json.dumps(message["content"]) for message in tool_results), "No real Bash result with guidance"
        return {"scopedGuidance": True, "realBashResult": True}


if __name__ == "__main__":
    for check in (verify_learning, verify_runtime):
        print(json.dumps(check()), flush=True)
