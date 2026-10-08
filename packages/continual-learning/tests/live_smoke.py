"""Explicit real-Pi verification in disposable project and agent directories.

Not collected by pytest or CI. Reuses configured authentication without editing
user settings, Memory, or Harness files. Learning failures are never replaced
with fixtures; runtime fixtures are tested separately.
"""

from __future__ import annotations

import json
import re
import os
from collections.abc import Callable
from pathlib import Path
import shutil
import subprocess
import tempfile

from support import read_memory_bodies

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


def run_pi(
    project: Path,
    agent: Path,
    probe: Path,
    prompt: str,
    tools: str,
    *,
    session_name: str = "session.jsonl",
) -> dict:
    """Run a real task and inspect its persisted, synthetic test messages."""
    model = json.loads((agent / "memory.json").read_text())
    session = project.parent / session_name
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


def prepare(base: Path, auto_memory: bool, *, seed_memory: bool = False, agents_md: bool = False, jev_enabled: bool | None = None) -> tuple[Path, Path, Path]:
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
    if jev_enabled is not None:
        (agent / "continual-learning.json").write_text(json.dumps({"jev": jev_enabled}))
    (agent / "memory").mkdir()
    (agent / "memory" / "settings.json").write_text(json.dumps({
        "autoMemory": auto_memory, "agentsMd": {"disabled": not agents_md},
    }))
    # This fixture deliberately owns its legacy-shaped seed. Bind before any
    # entries exist so the runtime need not guess the owner during upgrade.
    canonical = os.path.realpath(project)
    scope = "--" + canonical.lstrip("/").replace("/", "-").replace("\\", "-").replace(":", "-") + "--"
    registry = agent / "memory" / "scopes"; registry.mkdir()
    (registry / f"{scope}.json").write_text(json.dumps({"version":1,"cwd":canonical}))
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


def private_memory_root(agent: Path) -> Path:
    roots = sorted((agent / "memory").glob("--*--"))
    assert len(roots) == 1, f"Expected one canonical private Memory root, found {roots}"
    assert roots[0].is_dir() and not roots[0].is_symlink(), roots[0]
    return roots[0]


def memory_bodies(root: Path) -> dict[str, str]:
    return read_memory_bodies(root)


def shared_surface_leaks(project: Path, marker: str) -> list[Path]:
    """Find private markers or unsafe aliases on project-visible surfaces."""
    memory_root = project / ".memory"
    candidates = [
        memory_root,
        *([] if memory_root.is_symlink() else sorted(memory_root.rglob("*"))),
        project / "AGENTS.md",
        project / ".pi" / "harness.json",
    ]
    leaked: list[Path] = []
    for path in candidates:
        if path.is_symlink():
            leaked.append(path)
            continue
        if not path.is_file():
            continue
        if marker in path.read_text():
            leaked.append(path)
    return leaked


def frontmatter_value(content: str, key: str) -> str:
    match = re.search(r"^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)", content)
    if not match:
        return ""
    prefix = f"{key}:"
    for line in match.group(1).splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip("\"'")
    return ""


def assert_current_memory_command(content: str, old_command: str, current_command: str) -> None:
    """Accept an explicitly superseded old value, never an old current value."""
    description = frontmatter_value(content, "description")
    assert current_command in description, {"description": description}
    frontmatter = re.search(r"^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)", content)
    body = content[frontmatter.end():] if frontmatter else content
    assert current_command in body, content
    history_markers = re.compile(r"superseded|supersede|previous|earlier|updat(?:ed|ing)\s+(?:this\s+entry\s+)?from|formerly|histor(?:y|ical)|replaced|old|stale", re.I)
    for line in content.splitlines():
        if old_command not in line:
            continue
        assert history_markers.search(line), f"Old command remains without an explicit historical marker: {line}"
        assert not re.search(r"settled|current|use|command|verification", line, re.I) or history_markers.search(line), line


def plan_names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return names


def same_canonical_path(left: Path, right: Path) -> bool:
    """Compare paths after resolving macOS aliases such as /var -> /private/var."""
    return left.resolve(strict=False) == right.resolve(strict=False)


def _tool_result_text(message: dict) -> str:
    return json.dumps(message.get("content", ""), ensure_ascii=False).lower()


def assistant_visible_text(messages: list[dict]) -> str:
    """Collect visible assistant prose, excluding thinking and tool results."""
    return "\n".join(
        block["text"]
        for message in messages
        if message.get("role") == "assistant" and isinstance(message.get("content"), list)
        for block in message["content"]
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    )


def _tool_arguments(block: dict) -> dict | None:
    arguments = block.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return None
    return arguments if isinstance(arguments, dict) else None


def matched_tool_results(
    messages: list[dict], tool_name: str, argument_match: Callable[[dict], bool]
) -> list[tuple[dict, dict]]:
    """Pair assistant calls with native results of the same tool and id."""
    calls: dict[str, dict] = {}
    for message in messages:
        if message.get("role") != "assistant" or not isinstance(message.get("content"), list):
            continue
        for block in message["content"]:
            if not isinstance(block, dict) or block.get("type") != "toolCall":
                continue
            if block.get("name") != tool_name or not isinstance(block.get("id"), str):
                continue
            arguments = _tool_arguments(block)
            if arguments is not None and argument_match(arguments):
                calls[block["id"]] = arguments
    matches: list[tuple[dict, dict]] = []
    for message in messages:
        call_id = message.get("toolCallId")
        if (
            message.get("role") == "toolResult"
            and message.get("toolName") == tool_name
            and isinstance(call_id, str)
            and call_id in calls
        ):
            matches.append((calls[call_id], message))
    return matches


def blocked_tool_call(messages: list[dict], tool_name: str, command: str) -> bool:
    """Require a specified assistant tool call to have its own refusal result."""
    return any(
        result.get("isError") is True
        and re.search(r"block|prohibit|harness|policy|not allowed|refus", _tool_result_text(result))
        for _, result in matched_tool_results(messages, tool_name, lambda args: args.get("command") == command)
    )


def successful_tool_call(
    messages: list[dict], tool_name: str, argument_match: Callable[[dict], bool], text: str
) -> bool:
    """Require an exact assistant call and successful native result containing text."""
    return any(
        result.get("isError") is False and text.casefold() in _tool_result_text(result)
        for _, result in matched_tool_results(messages, tool_name, argument_match)
    )


def path_argument_matches(project: Path, target: Path, arguments: dict) -> bool:
    raw = arguments.get("path")
    if not isinstance(raw, str):
        return False
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = project / candidate
    return same_canonical_path(candidate, target)


def path_argument_matches_any(project: Path, targets: tuple[Path, ...], arguments: dict) -> bool:
    """Match only one of the explicitly supplied private/public mirror paths."""
    return any(path_argument_matches(project, target, arguments) for target in targets)


def verify_learning_artifacts(agent: Path, seed_name: str, private_marker: str, project_marker: str) -> dict:
    """Check that the parent-owned artifacts prove the requested data flow."""
    run_root = agent / "memory" / "runs"
    dossiers = sorted(run_root.glob("**/incremental-learning-dossier.json"), key=lambda path: path.stat().st_mtime)
    assert dossiers, "Learning did not retain the selector dossier"
    dossier = json.loads(dossiers[-1].read_text())
    selected = plan_names(dossier.get("selection", {}).get("selected"))
    assert seed_name in selected, {"selected": selected, "dossier": str(dossiers[-1])}

    plans: list[tuple[Path, dict]] = []
    for path in run_root.glob("**/plan.json"):
        try:
            value = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if value.get("kind") in {"memory-consolidation-plan", "incremental-memory-plan"}:
            plans.append((path, value))
    assert plans, "Learning did not retain a validated Memory plan"
    matching = [(path, value) for path, value in plans if seed_name in plan_names(value.get("selected"))]
    assert matching, {"plans": [str(path) for path, _ in plans], "seed": seed_name}
    plan_path, plan = sorted(matching, key=lambda item: item[0].stat().st_mtime)[-1]
    operations = plan.get("operations")
    assert isinstance(operations, list) and any(
        isinstance(operation, dict) and operation.get("name") == seed_name
        for operation in operations
    ), {"plan": str(plan_path), "operations": operations}
    proposals = plan.get("newMemories")
    assert isinstance(proposals, list)
    assert any(
        isinstance(proposal, dict)
        and proposal.get("classification") == "private"
        and private_marker in str(proposal.get("content", ""))
        for proposal in proposals
    ), {"plan": str(plan_path), "newMemories": proposals}
    assert any(
        isinstance(proposal, dict)
        and proposal.get("classification") == "safe"
        and project_marker in str(proposal.get("content", ""))
        for proposal in proposals
    ), {"plan": str(plan_path), "newMemories": proposals}
    return {"selected": selected, "updated": seed_name, "plan": str(plan_path)}


def verify_learning() -> dict:
    """Learn a private preference and a project rule, with verified receipts.

    The task also references seeded Memory, so the plan operates on *existing*
    entries, and it corrects an AGENTS.md workflow, so the AGENTS.md phase runs
    instead of being skipped.
    """
    private_marker = "PRIVATE_PREF_QUARTZ"
    project_marker = "PROJECT_FACT_CALDERA"
    seed_name = "project_smoke_build_command.md"
    with tempfile.TemporaryDirectory(prefix="continual-learning-live-") as raw:
        project, agent, probe = prepare(Path(raw), True, seed_memory=True, agents_md=True, jev_enabled=False)
        before_agents = (project / "AGENTS.md").read_text() if (project / "AGENTS.md").exists() else ""
        result = run_pi(project, agent, probe,
                       f"For my personal replies, I prefer the sign-off marker {private_marker}; this is "
                       "private preference data and must never become a project Memory entry. Also record "
                       f"this project fact as settled shared knowledge: {project_marker} is the release "
                       "marker for this project. The existing project_smoke_build_command.md Memory entry "
                       "is stale: update it from `bun run check` to `bun run verify`, and use the updated "
                       "command in future tasks. Also, never run "
                       "retired-smoke-compiler through bash: it is prohibited in this project. "
                       "Our AGENTS.md instruction is wrong: the progress "
                       "reporting workflow is instead one short status line, not a paragraph. "
                       "All of these are durable requirements for future tasks. "
                       "Reply only: acknowledged.", "read")
        try:
            decisions = verify_learned_rule(project)
        except AssertionError as error:
            diagnostics = [file.read_text()[:2000] for file in (agent / "memory" / "runs").rglob("harness-error.txt")]
            receipts = [json.loads(file.read_text()) for file in (agent / "memory" / "runs").rglob("learning-pipeline-receipt.json")]
            raise AssertionError(f"{error}; diagnostics={diagnostics}; notifications={result['notifications']}; receipts={json.dumps(receipts)}") from error

        private_root = private_memory_root(agent)
        private = memory_bodies(private_root)
        public_root = project / ".memory"
        public = memory_bodies(public_root)
        private_index = (private_root / "MEMORY.md").read_text()
        private_preference_names = {
            name for name in private
            if private_marker in private[name]
            and any(name in line and re.search(r"harness[ _-]+only", line, re.I) for line in private_index.splitlines())
        }
        if not private_preference_names:
            plans = [json.loads(file.read_text()) for file in (agent / "memory" / "runs").rglob("plan.json")]
            summary = [{"kind": plan.get("kind"), "selected": plan.get("selected"),
                        "newMemories": [{"name": item.get("name"), "kind": item.get("kind"), "classification": item.get("classification")}
                                        for item in plan.get("newMemories", []) if isinstance(item, dict)]}
                       for plan in plans if plan.get("kind") in {"incremental-memory-plan", "memory-consolidation-plan"}]
            raise AssertionError({"missingPrivatePreference": True, "private": list(private), "plans": summary})
        assert not shared_surface_leaks(project, private_marker), "Shared surface contains a private marker or unsafe symbolic link"
        assert not private_preference_names.intersection(public), {
            "privatePreferenceNames": sorted(private_preference_names), "public": list(public),
        }
        project_files = [name for name, text in public.items() if project_marker in text]
        assert project_files, {"public": public}
        assert any(name in private and private[name] == public[name] for name in project_files), {
            "projectFiles": project_files, "private": list(private),
        }
        assert seed_name in private, private
        assert seed_name in public and public[seed_name] == private[seed_name], public.get(seed_name)
        assert_current_memory_command(private[seed_name], "bun run check", "bun run verify")
        artifacts = verify_learning_artifacts(agent, seed_name, private_marker, project_marker)

        receipt_files = sorted(
            (agent / "memory" / "runs").rglob("learning-pipeline-receipt.json"),
            key=lambda path: path.stat().st_mtime,
        )
        receipts = [json.loads(file.read_text()) for file in receipt_files]
        assert receipts, result["notifications"]
        receipt = receipts[-1]
        attempts = {(attempt["phase"], attempt["outcome"]) for attempt in receipt["attempts"]}
        assert receipt.get("screen", {}).get("agents") is True, receipt
        assert {("memory", "applied"), ("harness", "applied"), ("agents", "applied")} <= attempts, receipt
        assert receipt["operations"] >= 4, receipt
        after_agents = (project / "AGENTS.md").read_text()
        assert after_agents != before_agents, "AGENTS.md phase reported without changing the project document"
        assert "Report progress as a paragraph" not in after_agents
        assert "one short status line" in after_agents
        agents_receipts = sorted(agent.glob("memory/runs/**/agents-post-receipt.json"), key=lambda path: path.stat().st_mtime)
        assert agents_receipts, "AGENTS.md post receipt was not written"
        agents_receipt = json.loads(agents_receipts[-1].read_text())
        target_file = agents_receipt.get("targetFile")
        assert agents_receipt.get("phase") == "post" and isinstance(target_file, str) and same_canonical_path(
            Path(target_file), project / "AGENTS.md"
        )
        assert agents_receipt.get("applied"), agents_receipt

        (agent / "memory" / "settings.json").write_text(json.dumps({"autoMemory": False, "agentsMd": {"disabled": True}}))
        fresh = run_pi(
            project, agent, probe,
            "This is a fresh Pi session. Use the read tool to read both "
            f".memory/{seed_name} and .memory/{project_files[0]} in full; their descriptions "
            "are indexes rather than evidence of a body read. Report the updated build command "
            "and this project's release marker from those files. Then attempt `retired-smoke-compiler build` "
            "with bash once, followed by `printf CL_RUNTIME_FRESH_OK` with bash once. Report each result.",
            "read,bash", session_name="fresh-session.jsonl",
        )
        seed_target = public_root / seed_name
        seed_targets = (private_root / seed_name, seed_target)
        assert successful_tool_call(
            fresh["messages"], "read",
            lambda arguments: path_argument_matches_any(project, seed_targets, arguments),
            "bun run verify",
        ), "Fresh Pi session did not read the updated seeded Memory body"
        assert any(
            successful_tool_call(
                fresh["messages"], "read",
                lambda arguments, targets=(private_root / name, public_root / name): path_argument_matches_any(project, targets, arguments),
                project_marker,
            )
            for name in project_files
        ), "Fresh Pi session did not read the persisted shared project fact"
        assert blocked_tool_call(fresh["messages"], "bash", "retired-smoke-compiler build"), (
            "Fresh Pi session did not enforce the learned Harness block for the requested command"
        )
        assert successful_tool_call(
            fresh["messages"], "bash",
            lambda arguments: arguments.get("command") == "printf CL_RUNTIME_FRESH_OK",
            "CL_RUNTIME_FRESH_OK",
        ), "Fresh Pi session did not execute the allowed Bash command"
        visible = assistant_visible_text(fresh["messages"])
        assert "bun run verify" in visible and project_marker in visible, visible
        return {"privatePreference": True, "sharedFact": True, "updatedSeed": True,
                "learnedConstraint": decisions, "agentsApplied": True,
                "freshSessionRead": True, "freshHarnessEnforcement": True,
                "verifiedReceipts": True, "artifacts": artifacts}


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
