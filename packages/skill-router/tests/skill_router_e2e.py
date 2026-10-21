"""End-to-end acceptance for pi-skill-router against a real Pi process.

Two assemblies run the extension the host actually loaded:

- `codemode`: codemode is active, so the model-side script searches the tools and
  calls the matched skill tool. The result must carry the skill's instructions,
  its directory and an untruncated body, and the routing suggestion must be absent.
- `fallback`: codemode is not active, so the same prompt must instead produce the
  routing suggestion naming the leaf instruction file.

Everything asserted here came out of a real tool execution: the script's return
value is read from the codemode result in Pi's JSONL, and the gate decision is read
from the trace the fixture writes in `before_agent_start`.

Usage:
  python3 skill_router_e2e.py --mode codemode|fallback --agent-dir DIR --cwd DIR
                              --fixture FILE --tool NAME [--token TOKEN]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

MODEL = "skill-router-e2e/scripted"


def run(agent_dir: Path, cwd: Path, fixture: Path, tool: str, mode: str, trace: Path) -> tuple[str, str]:
    command = [
        os.environ.get("PI_BIN", "pi"),
        "--print", "--mode", "json",
        "--provider", "skill-router-e2e", "--model", "scripted",
        "--no-mcp", "--no-context-files", "--no-session",
        "--no-prompt-templates",
        "--extension", str(fixture),
        # A real user turn: the scripted provider ignores its content, and the
        # routing terms in it are what the fallback assembly matches.
        "please audit the SEO of this site",
    ]
    if mode == "fallback":
        # An allowlist that names only `read`: codemode is inactive and the skill
        # tools are removed from the session, so the suggestion is the only path.
        command += ["--tools", "read"]
    completed = subprocess.run(
        command,
        cwd=cwd,
        env={
            **os.environ,
            "PI_CODING_AGENT_DIR": str(agent_dir),
            # An isolated home: no user skills, context files or templates leak in,
            # and the gateway the fallback asserts on is the one this run installed.
            "HOME": str(agent_dir.parent),
            "PI_OFFLINE": "1",
            "PI_SKILL_ROUTER_TRACE": str(trace),
            "PI_SKILL_ROUTER_TOOL": tool,
            "PI_SKILL_ROUTER_ASSEMBLY": mode,
        },
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed.stdout, completed.stderr


def events(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip().startswith("{")]


def tool_results(parsed: list[dict], name: str) -> list[dict]:
    return [
        event
        for event in parsed
        if event.get("type") == "tool_execution_end" and event.get("toolName") == name
    ]


def result_text(event: dict) -> str:
    result = event.get("result") or {}
    return "\n".join(part.get("text", "") for part in result.get("content", []) if part.get("type") == "text")


def gate_lines(trace: Path) -> list[dict]:
    if not trace.exists():
        return []
    return [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines() if line.strip()]


def final_text(parsed: list[dict]) -> str:
    for event in reversed(parsed):
        if event.get("type") != "message_end":
            continue
        message = event.get("message") or {}
        if message.get("role") != "assistant":
            continue
        text = "".join(part.get("text", "") for part in message.get("content", []) if part.get("type") == "text")
        if text.strip():
            return text
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["codemode", "fallback"], required=True)
    parser.add_argument("--agent-dir", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--token", default="UNIQUE-TOKEN-SEO-7742")
    args = parser.parse_args()

    agent_dir, cwd, fixture = Path(args.agent_dir), Path(args.cwd), Path(args.fixture)
    trace = agent_dir / f"e2e-{args.mode}.jsonl"
    if trace.exists():
        trace.unlink()

    stdout, stderr = run(agent_dir, cwd, fixture, args.tool, args.mode, trace)
    parsed = events(stdout)
    gates = [line for line in gate_lines(trace) if line.get("kind") == "gate"]
    assert gates, f"the fixture recorded no gate decision:\n{stdout[-2000:]}\n{stderr[-2000:]}"
    gate = gates[-1]
    assert gate["tool"] == args.tool, gate

    if args.mode == "codemode":
        # The host declares codemode because the settings ask for it, and the
        # tools channel therefore applies: no routing suggestion for this skill.
        assert gate["suggestion"] is None, gate
        assert "codemode" in gate["activeTools"], gate
        calls = tool_results(parsed, "codemode")
        assert calls, stdout[-2000:]
        assert not any(event.get("isError") for event in calls), [result_text(call) for call in calls]
        payload = None
        for call in calls:
            text = result_text(call)
            start = text.find("{")
            if start < 0:
                continue
            try:
                payload = json.loads(text[start:])
            except json.JSONDecodeError:
                continue
        assert payload, [result_text(call)[:400] for call in calls]
        assert args.tool in payload["found"], payload["found"]
        call = payload["call"]
        assert call["ok"] is True, call
        assert call["tool"] == args.tool, call
        assert call["truncated"] is False, call
        assert args.token in call["body"], call["body"][:200]
        assert call["directory"].endswith(f"leaves/{args.tool.split('__')[-1].replace('_', '-')}") or "leaves/" in call["directory"], call
        assert Path(call["skillFile"]).is_file(), call["skillFile"]
        assert "E2E_SKILL_ROUTER_END" in final_text(parsed), final_text(parsed)
        print(
            "PASS codemode E2E: searchTools returned "
            f"{payload['found']} · call ok={call['ok']} truncated={call['truncated']} "
            f"body={len(call['body'])} chars · directory={call['directory']} · suggestion absent",
            flush=True,
        )
    else:
        suggestion = gate["suggestion"]
        assert suggestion, gate
        assert args.token not in suggestion, suggestion
        assert "SKILL.md" in suggestion and args.tool.split("__")[-1].replace("_", "-") in suggestion, suggestion
        assert not tool_results(parsed, "codemode"), "codemode ran while it was inactive"
        assert not [event for event in parsed if event.get("type") == "tool_execution_start"], "a tool ran in the fallback assembly"
        assert "E2E_SKILL_ROUTER_END" in final_text(parsed), final_text(parsed)
        print(
            "PASS fallback E2E: suggestion names the leaf instruction file; codemode ran "
            f"{len(tool_results(parsed, 'codemode'))} times",
            flush=True,
        )
    print("SKILL_ROUTER_E2E_OK", flush=True)


if __name__ == "__main__":
    main()