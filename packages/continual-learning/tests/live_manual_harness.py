"""Real-provider native authoring and execution check for ``/harness``.

The command is exercised in a disposable project with copied authentication.
The check proves that the default project-shared layer is authored through a
complete JSON write, while global and project-personal layers remain unchanged.
It then starts a fresh native Pi print and verifies one blocked and one safe
real Bash call.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

TESTS = Path(__file__).parent
sys.path.insert(0, str(TESTS))

from live_manual_memory import NativeTui, _prepare, _runtime_env  # noqa: E402
from live_smoke import blocked_tool_call, matched_tool_results, run_pi, same_canonical_path, successful_tool_call  # noqa: E402

PACKAGE = TESTS.parents[0]
BLOCKED = "CL_MANUAL_HARNESS_BLOCKED"
SAFE = "CL_MANUAL_HARNESS_SAFE"


def _session_messages(session: Path) -> list[dict]:
    messages: list[dict] = []
    for line in session.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        message = record.get("message") if isinstance(record, dict) else None
        if isinstance(message, dict):
            messages.append(message)
    return messages


def _arguments(block: dict) -> dict | None:
    value = block.get("arguments")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _path_matches(project: Path, target: Path, arguments: dict) -> bool:
    raw = arguments.get("path")
    if not isinstance(raw, str):
        return False
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = project / candidate
    return same_canonical_path(candidate, target)


def _result_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
    return ""


def _inspect_native_authoring(
    session: Path,
    project: Path,
    target: Path,
    other_layers: tuple[Path, ...],
    expected_predecessor: bytes,
) -> dict[str, object]:
    """Verify the native authoring trace, rather than trusting final bytes."""
    messages = _session_messages(session)
    calls: list[tuple[int, str, str, dict]] = []
    results: dict[str, tuple[int, dict]] = {}
    for index, message in enumerate(messages):
        if message.get("role") == "assistant" and isinstance(message.get("content"), list):
            for block in message["content"]:
                if isinstance(block, dict) and block.get("type") == "toolCall":
                    args = _arguments(block)
                    ident, name = block.get("id"), block.get("name")
                    if isinstance(ident, str) and isinstance(name, str) and args is not None:
                        calls.append((index, ident, name, args))
        if message.get("role") == "toolResult" and isinstance(message.get("toolCallId"), str):
            results.setdefault(message["toolCallId"], (index, message))

    target_writes = [call for call in calls if call[2] == "write" and _path_matches(project, target, call[3])]
    successful_target_writes = [
        call for call in target_writes
        if call[1] in results
        and results[call[1]][0] > call[0]
        and results[call[1]][1].get("toolName") == "write"
        and results[call[1]][1].get("isError") is False
    ]
    assert len(target_writes) == 1 and len(successful_target_writes) == 1, "expected exactly one successful target write"
    target_write = successful_target_writes[0]
    target_content = target_write[3].get("content")
    try:
        parsed_content = json.loads(target_content) if isinstance(target_content, str) else None
    except json.JSONDecodeError:
        parsed_content = None
    assert isinstance(parsed_content, dict) and isinstance(parsed_content.get("rules"), list), "target write was not complete JSON"

    try:
        expected_json = json.loads(expected_predecessor.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AssertionError("expected predecessor is not complete JSON") from error
    matching_predecessor_reads = [
        call for call in calls
        if call[2] == "read"
        and _path_matches(project, target, call[3])
        and call[0] < target_write[0]
        and call[1] in results
        and results[call[1]][0] > call[0]
        and results[call[1]][0] < target_write[0]
        and results[call[1]][1].get("toolName") == "read"
        and results[call[1]][1].get("isError") is False
        and _result_text(results[call[1]][1]).strip()
        and _read_json_equals(_result_text(results[call[1]][1]), expected_json)
    ]
    assert matching_predecessor_reads, "target was not successfully read with the complete predecessor before the target write"
    edit_calls = sum(1 for _, _, name, _ in calls if name == "edit")
    other_layer_writes = sum(
        1 for _, _, name, args in calls
        if name == "write" and any(_path_matches(project, other, args) for other in other_layers)
    )
    assert edit_calls == 0, "native authoring used edit"
    assert other_layer_writes == 0, "native authoring wrote another Harness layer"
    return {
        "targetReadBeforeWrite": True,
        "completePredecessorRead": True,
        "successfulTargetWrites": len(successful_target_writes),
        "completeJsonTargetWrite": True,
        "editCalls": edit_calls,
        "otherLayerWrites": other_layer_writes,
    }


def _read_json_equals(text: str, expected: object) -> bool:
    try:
        actual = json.loads(text)
    except json.JSONDecodeError:
        return False
    return actual == expected


def _validate_authored_rules(target: Path, existing_rule: dict[str, str]) -> dict[str, str]:
    authored = json.loads(target.read_text(encoding="utf-8"))
    rules = authored.get("rules") if isinstance(authored, dict) else None
    assert isinstance(rules, list), "authored Harness JSON has no rules array"
    by_id = {rule.get("id"): rule for rule in rules if isinstance(rule, dict)}
    expected_ids = {existing_rule["id"], "manual-harness-block", "manual-harness-safe"}
    assert set(by_id) == expected_ids, f"authored rule ids differ: {set(by_id)}"
    assert by_id[existing_rule["id"]] == existing_rule, "existing project rule changed"
    block = by_id["manual-harness-block"]
    safe = by_id["manual-harness-safe"]
    assert block.get("action") == "block", "block rule does not use action block"
    assert isinstance(block.get("message"), str) and block["message"], "block rule has no message"
    assert isinstance(safe.get("message"), str) and safe["message"], "safe rule has no message"

    source = (
        f'import {{ mergeLayers, evaluateBash }} from {json.dumps(str(PACKAGE / "extensions/guardrail-engine.ts"))};'
        f'const layer=JSON.parse(await Bun.file({json.dumps(str(target))}).text());'
        'const config=mergeLayers([{...layer,source:"project"}]);'
        f'const commands={json.dumps([f"printf {BLOCKED}", f"printf {BLOCKED}_EXTRA", f"printf {SAFE}", f"printf {SAFE}_EXTRA", "printf CL_MANUAL_HARNESS_UNRELATED"])};'
        'console.log(JSON.stringify(commands.map(command=>{const result=evaluateBash(config,command);return {command,decision:result.decision,ids:result.matchedRules.map(rule=>rule.id)}})));'
    )
    result = subprocess.run(["bun", "-e", source], cwd=PACKAGE.parents[1], text=True, capture_output=True, check=True)
    cases = json.loads(result.stdout)
    by_command = {case["command"]: case for case in cases}
    block_case = by_command[f"printf {BLOCKED}"]
    assert block_case["decision"] == "block" and "manual-harness-block" in block_case["ids"], "block rule did not match"
    assert "manual-harness-block" not in by_command[f"printf {BLOCKED}_EXTRA"]["ids"], "block rule matched an approximate command"
    safe_case = by_command[f"printf {SAFE}"]
    assert safe_case["decision"] == "execute" and "manual-harness-safe" in safe_case["ids"], "safe rule did not match as executable"
    assert "manual-harness-safe" not in by_command[f"printf {SAFE}_EXTRA"]["ids"], "safe rule matched an approximate command"
    assert by_command["printf CL_MANUAL_HARNESS_UNRELATED"]["ids"] == [], "unrelated command matched a requested rule"
    return {"blockRule": "matched", "safeRule": "matched", "negativeCases": "clear"}


def _write_layer(path: Path, content: dict[str, object]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    value = json.dumps(content, indent=2) + "\n"
    path.write_text(value, encoding="utf-8")
    return value.encode("utf-8")


def _fresh_harness_result(project: Path, agent: Path, probe: Path, safe_message: str) -> dict[str, object]:
    result = run_pi(
        project,
        agent,
        probe,
        "Run exactly two harmless Bash commands in order: first `printf "
        f"{BLOCKED}` and then `printf {SAFE}`. Do not substitute commands. "
        "Report both native tool results and stop.",
        "bash",
        session_name="harness-runtime.jsonl",
    )
    messages = result["messages"]
    assert blocked_tool_call(messages, "bash", f"printf {BLOCKED}"), messages
    assert successful_tool_call(
        messages, "bash", lambda arguments: arguments.get("command") == f"printf {SAFE}", SAFE,
    ), messages
    safe_results = matched_tool_results(
        messages, "bash", lambda arguments: arguments.get("command") == f"printf {SAFE}",
    )
    assert any(
        result.get("isError") is False
        and "[harness-bash-note]" in json.dumps(result.get("content"), ensure_ascii=False)
        and safe_message in json.dumps(result.get("content"), ensure_ascii=False)
        for _, result in safe_results
    ), "safe Bash result did not carry the authored Harness message"
    return {"blocked": True, "allowed": True}


def verify() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="continual-learning-manual-harness-") as raw:
        base = Path(raw)
        project, agent, probe = _prepare(base)
        model = json.loads((agent / "memory.json").read_text(encoding="utf-8"))
        provider, model_id = model["provider"], model["model"]

        project_target = project / ".pi" / "harness.json"
        local_target = project / ".pi" / "harness.local.json"
        global_target = agent / "harness.json"
        existing_project_rule = {
            "id": "manual-existing-project",
            "bash": "^printf\\s+MANUAL_EXISTING$",
            "message": "Existing project rule must remain.",
        }
        project_before = _write_layer(project_target, {"rules": [existing_project_rule]})
        local_before = _write_layer(local_target, {"rules": [{
            "id": "manual-existing-local",
            "bash": "^printf\\s+MANUAL_LOCAL$",
            "message": "Existing local rule must remain.",
        }]})
        global_before = _write_layer(global_target, {"rules": [{
            "id": "manual-existing-global",
            "bash": "^printf\\s+MANUAL_GLOBAL$",
            "message": "Existing global rule must remain.",
        }]})

        home = base / "home"
        home.mkdir()
        env = _runtime_env(agent, home)
        pi = shutil.which("pi")
        if not pi:
            raise RuntimeError("Pi CLI is required for native Harness authoring")
        tui = NativeTui([
            pi, "-e", str(probe), "-e", str(PACKAGE / "index.ts"),
            "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files",
            "--no-approve", "--session", str(base / "tui-session.jsonl"),
            "--model", f"{provider}/{model_id}", "--tools", "read,write,bash",
        ], project, env)
        try:
            tui.wait_until(
                lambda: tui.process.poll() is None and (base / "tui-ready").is_file(),
                30,
                "Native Pi TUI did not reach session_start",
            )
            tui.send(
                "/harness In the default project shared Harness layer, create or update exactly two "
                f"flat Bash rules. Rule id manual-harness-block must block exactly the harmless raw "
                f"command `printf {BLOCKED}`. Rule id manual-harness-safe must match exactly "
                f"`printf {SAFE}` and leave it executable while reporting its real output. "
                "Read the current project shared JSON first, preserve every existing rule and field, "
                "then use one complete validated JSON write to the project .pi/harness.json target. "
                "Do not write global or project-personal Harness files, do not use edit, and stop "
                "after the validated write."
            )
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                tui._pump()
                try:
                    parsed = json.loads(project_target.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    parsed = None
                rules = parsed.get("rules", []) if isinstance(parsed, dict) else []
                ids = {rule.get("id") for rule in rules if isinstance(rule, dict)}
                if "manual-harness-block" in ids and "manual-harness-safe" in ids:
                    break
                time.sleep(0.1)
            else:
                raise AssertionError("Native /harness authoring did not produce both requested rules")
        finally:
            tui.close()

        trace = _inspect_native_authoring(
            base / "tui-session.jsonl", project, project_target, (local_target, global_target), project_before,
        )
        project_after = project_target.read_bytes()
        assert project_after != project_before, "Project shared Harness was not authored"
        authored = json.loads(project_after)
        rules = authored.get("rules")
        assert isinstance(rules, list)
        rule_validation = _validate_authored_rules(project_target, existing_project_rule)
        safe_message = next(rule["message"] for rule in rules if rule.get("id") == "manual-harness-safe")
        assert authored.get("learnedRules") in (None, {}), authored
        assert local_target.read_bytes() == local_before
        assert global_target.read_bytes() == global_before
        runtime = _fresh_harness_result(project, agent, probe, safe_message)
        return {
            "provider": provider,
            "model": model_id,
            "scope": "project shared",
            "authoringTrace": trace,
            "ruleValidation": rule_validation,
            "existingProjectRulePreserved": True,
            "otherLayersByteUnchanged": True,
            "runtime": runtime,
        }


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False), flush=True)
