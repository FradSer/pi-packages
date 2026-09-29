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


def prepare(base: Path, auto_memory: bool, *, seed_memory: bool = False, agents_md: bool = False) -> tuple[Path, Path, Path]:
    """Copy auth privately so runtime refreshes cannot alter source files.

    ``seed_memory`` writes a few private entries so the selector has something to
    select, which is what makes the Memory plan's operations on *existing*
    entries observable at all — without them the run only proposes new entries.
    ``agents_md`` enables the AGENTS.md phase, which is off by default here.
    """
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
        "autoMemory": auto_memory, "agentsMd": {"disabled": not agents_md},
    }))
    if seed_memory:
        # The scope key is the canonical project path with separators replaced,
        # which is how the package names its private Memory root.
        canonical = os.path.realpath(project)
        scope = "--" + canonical.lstrip("/").replace("/", "-").replace("\\", "-").replace(":", "-") + "--"
        private = agent / "memory" / scope
        private.mkdir(parents=True)
        entries = {
            "project_smoke_build_command.md":
                "The settled build and verification command for this project is `bun run check`.",
            "feedback_smoke_progress_line.md":
                "Progress updates in this project are reported as one short status line.",
        }
        (private / "MEMORY.md").write_text(
            "# Memory\n\n" + "".join(f"- [{name}]({name})\n" for name in entries))
        for name, description in entries.items():
            (private / name).write_text(
                f"---\nname: {name[:-3]}\ndescription: {description}\ntype: project\n---\n\n{description}\n")
    if agents_md:
        # The AGENTS.md phase consolidates against an existing project document.
        # Without one it reports "nothing to consolidate", which is a correct
        # outcome but leaves the surface unjudged.
        (project / "AGENTS.md").write_text(
            "# Project instructions\n\n"
            "## Progress reporting\n\n"
            "Report progress as a paragraph describing what changed and why.\n\n"
            "## Build\n\n"
            "Use the settled build command recorded in Memory.\n",
            encoding="utf-8",
        )
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


def verify_judgment_shadow(project: Path, agent: Path) -> dict:
    """Require a real Judgment observation, when Judgment is configured.

    ``verify_learning`` already exercises the whole pipeline against a real
    provider, and this function runs inside it, so the observation here was
    produced by the live service rather than a fixture. It is conditional
    because Judgment is opt-in: with no configured key there is nothing to
    assert, and that is itself the correct behaviour.
    """
    if not (os.environ.get("TYPESAFE_API_KEY") or "").strip():
        return {"configured": False}
    # Ask the package where the log lives rather than guessing a layout. The
    # first version of this check hardcoded the Memory root and went on asserting
    # nothing existed, which would have hidden a broken Judgment path.
    located = subprocess.run(
        ["bun", "-e",
         f'import {{ judgmentObservationFile }} from {json.dumps(str(PACKAGE / "extensions/judgment-observations.ts"))};'
         'console.log(judgmentObservationFile(process.argv[2], process.argv[3]));',
         "observation-file", str(project), str(agent)],
        cwd=REPO, text=True, capture_output=True, check=True)
    log = Path(located.stdout.strip().splitlines()[-1])
    assert log.exists(), f"No Judgment observation at {log}"
    raw = log.read_text()
    records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    assert records, "Judgment observation log is empty"
    observed = [record for record in records if record.get("judged")]
    assert observed, f"No Judgment observation answered; records={json.dumps(records)[:1500]}"
    # Both phases, not just one. The selector record alone satisfied this check
    # before, which meant a completely broken proposal hook would still pass.
    phases = {record.get("phase") for record in observed}
    assert "selector" in phases, f"Selector phase was never judged; phases={sorted(phases)}"
    assert "proposals" in phases, (
        "The Memory plan's proposals were never judged. The real run learned a "
        f"preference, so a plan proposed new entries and the hook in "
        f"inject-memory.ts should have run. phases={sorted(phases)}"
    )
    # Every remaining surface, not just one. The selector and proposal records
    # alone satisfied this check before, so a completely broken hook for the
    # Memory, Harness, or AGENTS.md surfaces would have passed unnoticed.
    surfaces_seen = {
        record.get("surface") for record in observed if record.get("phase") == "operations"
    }
    required_surfaces = {"memory-operations", "harness-operations", "agents-operations"}
    missing = required_surfaces - surfaces_seen
    assert not missing, (
        f"Judgment did not reach every learning surface. Missing {sorted(missing)}; "
        f"judged surfaces were {sorted(s for s in surfaces_seen if s)}. "
        f"phases={sorted(phases)}"
    )
    proposals = [record for record in observed if record.get("phase") == "proposals"]
    for record in proposals:
        assert record.get("proposed", 0) > 0, record
        assert "confidence" in record or record.get("confidences"), record
    phases_seen = sorted(phases)
    record = observed[0]
    # The whole point of an observation: verdicts, the selector's own answer,
    # and agreement — with no user content anywhere in it.
    for needle in ("concise progress updates", "retired-smoke-compiler", "acknowledged"):
        assert needle not in raw, f"Observation leaked request content: {needle!r}"
    key = os.environ["TYPESAFE_API_KEY"]
    assert key not in raw, "Observation leaked the API key"
    assert not any(key_id.endswith(".md") for key_id in record.get("values", {})), record
    assert record.get("model"), "Observation did not record the answering model"
    assert isinstance(record.get("selectorSelected"), list), record
    return {
        "configured": True,
        "model": record["model"],
        "phases": phases_seen,
        "surfaces": sorted({
            str(record.get("surface"))
            for record in observed
            if record.get("phase") == "operations"
        }),
        "proposalsJudged": len(proposals),
        "wouldKeep": proposals[0].get("kept") if proposals else None,
        "proposalConfidences": len(proposals[0].get("confidences", {})) if proposals else 0,
        "unanswered": [
            {"phase": r.get("phase"), "surface": r.get("surface"), "outcome": r.get("outcome"),
             "reason": (r.get("reason") or "")[:160], "operations": r.get("operations")}
            for r in records if not r.get("judged")
        ],
        "log": str(log).replace(str(agent), "<agent>"),
        "observations": len(records),
        "judged": len(observed),
        "agreeRate": round(sum(1 for entry in observed if entry.get("agrees")) / len(observed), 3),
        "leakFree": True,
    }


def verify_learning() -> dict:
    """Learn a private preference and a project rule, with verified receipts.

    The task also carries the two signals that make every Judgment surface
    reachable in a real run: it references seeded Memory, so the plan operates
    on *existing* entries, and it corrects an AGENTS.md workflow, so the
    AGENTS.md phase runs instead of being skipped.
    """
    with tempfile.TemporaryDirectory(prefix="continual-learning-live-") as raw:
        project, agent, probe = prepare(Path(raw), True, seed_memory=True, agents_md=True)
        result = run_pi(project, agent, probe,
                       "For this project, I prefer concise progress updates. Also, never run "
                       "retired-smoke-compiler through bash: it is prohibited in this project. "
                       "Use the project build command Memory entry when you build; that is the "
                       "settled way. Also, our AGENTS.md instruction is wrong: the progress "
                       "reporting workflow is instead one short status line, not a paragraph. "
                       "All of these are durable requirements for future tasks. "
                       "Reply only: acknowledged.", "read")
        memories = [file for file in (agent / "memory").glob("*/*.md") if file.name != "MEMORY.md"]
        assert any("concise" in file.read_text().lower() for file in memories), result["notifications"]
        assert not any("concise" in file.read_text().lower() for file in (project / ".memory").glob("*.md")), "Preference leaked into shared memory"
        receipts = [json.loads(file.read_text()) for file in (agent / "memory" / "runs").glob("*/*/learning-pipeline-receipt.json")]
        # Read the Judgment observation first, before any Harness assertion. The
        # Harness planner's output is nondeterministic and it has flaked on both
        # a malformed plan and a negative case that must stay unmatched, so a
        # check placed after it would only report when both surfaces were lucky.
        judgment = verify_judgment_shadow(project, agent)
        try:
            decisions = verify_learned_rule(project)
        except AssertionError as error:
            diagnostics = [file.read_text()[:2000] for file in (agent / "memory" / "runs").glob("*/*/harness-error.txt")]
            raise AssertionError(f"{error}; judgment={json.dumps(judgment)}; diagnostics={diagnostics}; notifications={result['notifications']}; receipts={json.dumps(receipts)}") from error
        assert receipts, result["notifications"]
        attempts = {(attempt["phase"], attempt["outcome"]) for attempt in receipts[-1]["attempts"]}
        assert {("memory", "applied"), ("harness", "applied")} <= attempts, receipts[-1]
        assert receipts[-1]["operations"] >= 2, receipts[-1]
        return {"privatePreference": True, "learnedConstraint": decisions,
                "verifiedReceipts": True, "judgment": judgment}


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
