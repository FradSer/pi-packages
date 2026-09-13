"""Explicit live Pi verification; never collected by pytest or run in CI.

Uses the configured memory model and existing authentication in isolated temporary
project/agent directories. No user memory, settings, or harness policy is edited.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


def run_pi(project: Path, agent: Path, probe: Path, prompt: str, tools: str) -> dict:
    """Run one real Pi task and retain only synthetic test diagnostics."""
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
        capture_output=True, text=True, timeout=240,
    )
    assert result.returncode == 0, result.stderr[-1500:]
    records = [json.loads(line) for line in session.read_text().splitlines() if line.strip()]
    messages = [entry["message"] for entry in records if entry.get("type") == "message"]
    errors = [message.get("errorMessage") for message in messages if message.get("stopReason") == "error"]
    assert not errors, errors
    assistant = [message for message in messages if message.get("role") == "assistant"]
    checks = [entry["data"] for entry in records if entry.get("customType") == "harness-check"]
    final = "\n".join(block.get("text", "") for block in assistant[-1]["content"] if block.get("type") == "text")
    log = project.parent / "notifications.jsonl"
    return {"final": final, "checks": checks, "stderr": result.stderr[-1500:],
            "notifications": log.read_text() if log.exists() else "No extension notifications"}


def prepare(base: Path, auto_memory: bool) -> tuple[Path, Path, Path]:
    """Isolate generated files while reusing configured provider authentication."""
    project, agent = base / "project", base / "agent"
    project.mkdir(); agent.mkdir(mode=0o700)
    source = Path.home() / ".pi" / "agent"
    for name in ("auth.json", "models.json"):
        if (source / name).exists():
            (agent / name).symlink_to(source / name)
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


def verify_learning() -> dict:
    """Learn a private preference and a working tool constraint from empty state."""
    with tempfile.TemporaryDirectory(prefix="continual-learning-live-") as raw:
        base = Path(raw)
        project, agent, probe = prepare(base, True)
        result = run_pi(project, agent, probe,
               "For this project, I prefer concise progress updates. Also, never run "
               "retired-smoke-compiler through bash: it is prohibited in this project. "
               "Both statements are durable requirements for future tasks. Reply only: acknowledged.", "read")
        memories = [file for file in (agent / "memory").glob("*/*.md") if file.name != "MEMORY.md"]
        assert any("concise" in file.read_text().lower() for file in memories), result
        assert not any("concise" in file.read_text().lower() for file in (project / ".memory").glob("*.md")), "Preference leaked into shared memory"
        policy_file = project / ".pi" / "harness.local.json"
        assert policy_file.exists(), result
        source = (
            f'import {{ mergeLayers, evaluate }} from {json.dumps(str(PACKAGE / "extensions/guardrail-engine.ts"))};'
            f'const layer=JSON.parse(await Bun.file({json.dumps(str(policy_file))}).text());'
            'const config=mergeLayers([{...layer,source:"project.local"}]);'
            'console.log(JSON.stringify({blocked:evaluate(config,{toolName:"bash",args:{command:"retired-smoke-compiler build"}})?.action,'
            'allowed:evaluate(config,{toolName:"bash",args:{command:"printf safe"}})===null}));'
        )
        result = subprocess.run(["bun", "-e", source], cwd=REPO, text=True, capture_output=True, check=True)
        decisions = json.loads(result.stdout)
        assert decisions == {"blocked": "block", "allowed": True}, decisions
        return {"privatePreference": True, "learnedConstraint": decisions}


def verify_post_generation(phase: str) -> dict:
    """Exercise a real post-generation correction and inspect persisted checks."""
    with tempfile.TemporaryDirectory(prefix=f"continual-{phase}-live-") as raw:
        project, agent, probe = prepare(Path(raw), False)
        (project / ".pi").mkdir()
        policy = {"name": f"no-smoke-{phase}", "phase": phase, "pattern": "SMOKE_PROHIBITED", "action": "block", "reason": "Replace SMOKE_PROHIBITED with SAFE_RESPONSE."}
        if phase == "artifact":
            policy.update({"tools": ["write", "edit", "bash"], "artifactPaths": ["demo.txt"]})
            prompt = "Write demo.txt containing exactly SMOKE_PROHIBITED. If a harness check requests a correction, make that correction."
            tools = "read,write,edit,bash"
        else:
            prompt, tools = "Reply with exactly SMOKE_PROHIBITED.", "read"
        (project / ".pi" / "harness.json").write_text(json.dumps({"policies": [policy]}))
        result = run_pi(project, agent, probe, prompt, tools)
        violations = [entry for entry in result["checks"] if entry.get("phase") == phase and entry.get("status") == "violated"]
        assert violations, result
        assert max(entry["repairAttempt"] for entry in violations) <= 2
        content = (project / "demo.txt").read_text() if phase == "artifact" else result["final"]
        assert "SMOKE_PROHIBITED" not in content, result
        return {"phase": phase, "violations": len(violations), "corrected": True}


if __name__ == "__main__":
    for check in (verify_learning, lambda: verify_post_generation("artifact"), lambda: verify_post_generation("output")):
        print(json.dumps(check()), flush=True)
