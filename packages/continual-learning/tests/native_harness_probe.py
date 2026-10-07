"""Real Pi hook probe with fixed tool requests; no real model inference or API key."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Iterator
from typing import Any

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
PROBES = (
    ("push-with-remote", "git push origin topic", "block"),
    ("push-dry-run", "git push --dry-run", "block"),
    ("quoted-operator-print", "printf '%s' 'x;git push --dry-run'", "execute"),
    ("plain-command-words-echo", "echo git push --dry-run", "execute"),
    ("unrelated-status", "git status --short", "execute"),
    ("same-project-cwd-push", "git -C . push --dry-run", "block"),
    ("global-config-push", "git -c core.quotePath=false push --dry-run", "block"),
    ("global-pager-push", "git --no-pager push --dry-run", "block"),
    ("global-option-print", "printf '%s' 'git -C . push --dry-run'", "execute"),
    ("global-option-echo", "echo git -C . push --dry-run", "execute"),
)


@contextmanager
def fixed_tool_provider(agent: Path) -> Iterator[dict[str, int]]:
    """Loopback-only OpenAI transport fixture; never forwards a request."""
    state = {"requests": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_POST(self) -> None:
            # Consume but never retain or log the isolated synthetic transcript.
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            index = state["requests"]
            state["requests"] += 1
            delta: dict[str, Any] = {"role": "assistant"}
            if index < len(PROBES):
                delta["tool_calls"] = [{"index": 0, "id": f"native-probe-{index}", "type": "function",
                    "function": {"name": "bash", "arguments": json.dumps({"command": PROBES[index][1]})}}]
                finish = "tool_calls"
            else:
                delta["content"] = "Fixed native probe complete."
                finish = "stop"
            def chunk(value: dict[str, Any], reason: str | None) -> dict[str, Any]:
                return {"id": f"probe-{index}", "object": "chat.completion.chunk", "created": 0, "model": "fixed-tools",
                        "choices": [{"index": 0, "delta": value, "finish_reason": reason}]}
            payload = ''.join('data: '+json.dumps(item)+'\n\n' for item in (chunk(delta, None), chunk({}, finish)))
            payload += 'data: [DONE]\n\n'
            data = payload.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    (agent / "models.json").write_text(json.dumps({"providers": {"cl-native-fixture": {
        "baseUrl": f"http://127.0.0.1:{server.server_port}/v1", "apiKey": "fixture-only", "api": "openai-completions",
        "models": [{"id": "fixed-tools", "name": "Fixed safe native requests", "reasoning": False, "input": ["text"],
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, "contextWindow": 64000, "maxTokens": 1024}]}}}))
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_native_harness_probe(harness: dict[str, Any], *, pi_binary: str | None = None) -> dict[str, Any]:
    """Copy a Harness into a disposable project and return only controlled results."""
    with tempfile.TemporaryDirectory(prefix="cl-native-hook-") as temporary:
        base = Path(temporary)
        project, agent, bin_dir = base / "project", base / "agent", base / "bin"
        for directory in (project / ".pi", agent / "memory", bin_dir, base / "home", base / "hooks", base / "template"):
            directory.mkdir(parents=True)
        node = shutil.which("node")
        if not node:
            raise RuntimeError("Native Pi probe requires Node")
        env = {"HOME": str(base / "home"), "XDG_CONFIG_HOME": str(base / "home/config"),
               "XDG_CACHE_HOME": str(base / "home/cache"), "TMPDIR": str(base),
               "PI_CODING_AGENT_DIR": str(agent), "LANG": "C.UTF-8", "TERM": "dumb",
               "PATH": os.pathsep.join((str(bin_dir), str(Path(node).parent), os.defpath)),
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        subprocess.run(["/usr/bin/git", "-c", f"core.hooksPath={base / 'hooks'}", "init",
                        f"--template={base / 'template'}", "-q", str(project)],
                       check=True, capture_output=True, env=env)
        (project / ".pi/harness.json").write_text(json.dumps(harness))
        (agent / "settings.json").write_text(json.dumps({"packages": [], "compaction": {"enabled": False}}))
        (agent / "continual-learning.json").write_text('{"jev":false}')
        (agent / "memory/settings.json").write_text('{"autoMemory":false,"agentsMd":{"disabled":true}}')
        marker = base / "forbidden-executed"
        wrapper = bin_dir / "git"
        wrapper.write_text('#!/bin/sh\nfor arg in "$@"; do\n if [ "$arg" = push ]; then\n'
                           f'  printf executed >> "{marker}"\n  exit 0\n fi\ndone\nexec /usr/bin/git "$@"\n')
        wrapper.chmod(0o755)
        session = base / "session.jsonl"
        command = [pi_binary or str(REPO / "node_modules/.bin/pi"), "--offline", "--no-extensions",
                   "-e", str(PACKAGE / "index.ts"),
                   "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files",
                   "--session", str(session), "--model", "cl-native-fixture/fixed-tools", "--tools", "bash",
                   "--print", "--mode", "json", "Run the fixed safe native hook probes."]
        runtime = subprocess.run([command[0], "--version"], env=env, capture_output=True, text=True, check=True).stdout.strip()
        with fixed_tool_provider(agent) as provider:
            process = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True, timeout=60)
        if process.returncode or not session.is_file():
            raise RuntimeError("Isolated native Pi probe did not complete")
        messages = [entry["message"] for line in session.read_text().splitlines()
                    if (entry := json.loads(line)).get("type") == "message"]
        if any(message.get("stopReason") in {"error", "aborted"} for message in messages):
            raise RuntimeError("Fixed native provider failed")
        calls = {block["id"]: block for message in messages if message.get("role") == "assistant"
                 for block in message.get("content", []) if block.get("type") == "toolCall"}
        results = {message["toolCallId"]: message for message in messages if message.get("role") == "toolResult"}
        checks = []
        block_messages = {rule.get("message") for rule in harness.get("rules", [])
                          if rule.get("action") == "block" and rule.get("enabled", True)
                          and isinstance(rule.get("message"), str)}
        for index, (identity, requested, expected) in enumerate(PROBES):
            call_id = f"native-probe-{index}"
            call, result = calls.get(call_id, {}), results.get(call_id, {})
            text = "\n".join(block.get("text", "") for block in result.get("content", []) if block.get("type") == "text")
            observed = call.get("name") == "bash" and call.get("arguments", {}).get("command") == requested and result.get("toolName") == "bash"
            blocked = observed and result.get("isError") is True and text in block_messages
            printed = ("x;git push --dry-run" if identity == "quoted-operator-print" else
                       "git -C . push --dry-run" if identity in {"global-option-print", "global-option-echo"} else
                       "git push --dry-run" if identity == "plain-command-words-echo" else "")
            allowed = observed and result.get("isError") is False and printed in text
            checks.append({"id": identity, "expected": expected, "observed": observed,
                           "passed": blocked if expected == "block" else allowed})
        forbidden = marker.read_text().count("executed") if marker.exists() else 0
        return {"evidence": "real-pi-native-hook-with-fixture-provider", "fixtureProvider": True,
                "externalRequests": None, "networkIsolation": "not-enforced-host-probe", "fixtureForwardedRequests": 0,
                "piVersion": runtime, "fixtureRequests": provider["requests"], "realInference": False,
                "harnessSha256": hashlib.sha256(json.dumps(harness).encode()).hexdigest(),
                "nativeToolResults": sum(case["observed"] for case in checks),
                "blockedCases": sum(case["passed"] and case["expected"] == "block" for case in checks),
                "allowedCases": sum(case["passed"] and case["expected"] == "execute" for case in checks),
                "forbiddenSideEffects": forbidden, "allPassed": all(case["passed"] for case in checks) and forbidden == 0,
                "cases": checks}
