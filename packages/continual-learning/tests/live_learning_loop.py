"""Offline Pi v1 end-to-end learning and runtime verification.

This is an explicit live check, not a pytest test.  It starts a local
OpenAI-compatible SSE provider, gives Pi disposable project and agent roots,
and drives the real package and real planner child processes.  The provider
returns deterministic, identity-bound plans only after seeing the planner's
actual prompt; it never reads credentials or contacts an external service.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from live_acceptance_support import isolated_environment, workspace_pi

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
SAFE_COMMAND = "printf CL_OFFLINE_SAFE"
BLOCKED_COMMAND = "printf CL_OFFLINE_BLOCKED"
MEMORY_QUOTE = "LOOPBACK_MEMORY_FACT"
HARNESS_QUOTE = "LOOPBACK_HARNESS_RULE"
PROVIDER = "continual-learning-loopback"
MODEL = "scripted"
API_KEY = "loopback-fixture-only"


def message_text(payload: dict[str, object]) -> str:
    values: list[str] = []
    for message in payload.get("messages", []):
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            values.append(content)
        elif isinstance(content, list):
            values.extend(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
    return "\n".join(values)


def field(text: str, name: str) -> str:
    bullet_pattern = rf"(?:^|\n)\s*-\s*`?{re.escape(name)}`?\s*:\s*`?([^`\n]+?)`?\s*$"
    bullets = re.findall(bullet_pattern, text, re.MULTILINE)
    if bullets:
        return bullets[-1].strip()
    patterns = (
        rf'"{re.escape(name)}"\s*:\s*"([^"\\]+)"',
        rf"\b{re.escape(name)}\s*:\s*([A-Za-z0-9._:/-]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    raise AssertionError(f"loopback planner prompt omitted {name}")


def stream_response(handler: BaseHTTPRequestHandler, content: str | list[dict[str, object]]) -> None:
    if isinstance(content, list):
        delta: dict[str, object] = {
            "role": "assistant",
            "tool_calls": [
                {
                    "index": 0,
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": json.dumps(call["arguments"], separators=(",", ":")),
                    },
                }
                for call in content
            ],
        }
        finish = "tool_calls"
    else:
        delta = {"role": "assistant", "content": content}
        finish = "stop"
    base = {"id": "continual-learning-loopback", "object": "chat.completion.chunk", "created": 1, "model": MODEL}
    events = [
        {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
    ]
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.end_headers()
    for event in events:
        handler.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
    handler.wfile.write(b"data: [DONE]\n\n")
    handler.wfile.flush()


def runtime_events(output: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") in {"tool_execution_start", "tool_execution_end"}:
            events.append({key: event[key] for key in ("type", "toolName", "args", "isError", "result") if key in event})
    return events


class LoopbackProvider(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []
    responses: list[str] = []
    runtime_request_texts: list[str] = []
    runtime_calls: int = 0
    raw_memory_json: bool = False

    def log_message(self, _format: str, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions" or self.headers.get("Authorization") != f"Bearer {API_KEY}":
            self.send_error(403, "loopback fixture authorization or path mismatch")
            return
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append(payload)
        text = message_text(payload)
        if "incremental-memory-selection" in text and "Context digest:" in text:
            self.responses.append("selection")
            answer = {
                "kind": "incremental-memory-selection",
                "version": 1,
                "contextDigest": field(text, "Context digest"),
                "selected": [],
                "memory": True,
                "harness": True,
                "agents": False,
                "reason": "The offline loopback task carries durable Memory and executable Harness evidence.",
            }
            stream_response(self, json.dumps(answer, separators=(",", ":")))
            return
        if "incremental-memory-plan" in text:
            repairing = "repair one rejected incremental Memory delta plan" in text
            self.responses.append("memory-plan-repair" if repairing else "memory-plan")
            answer = {
                "kind": "incremental-memory-plan",
                "version": 1,
                "schemaVersion": 1,
                "runId": field(text, "runId"),
                "scopeKey": field(text, "scopeKey"),
                "scopeDigest": field(text, "scopeDigest"),
                "artifactHash": field(text, "artifactHash"),
                "snapshotDigest": field(text, "snapshotDigest"),
                "operations": [],
                "newMemories": [{
                    "name": "loopback_memory_fact.md",
                    "kind": "project",
                    "classification": "safe",
                    "content": "---\ndescription: The offline loopback verification marker is a settled project fact\ntype: project\n---\n\nThe settled local verification command is `printf CL_OFFLINE_SAFE`.\n",
                    "evidence": [{"index": 0, "quote": MEMORY_QUOTE}],
                }],
            }
            encoded = json.dumps(answer, separators=(",", ":"))
            if self.raw_memory_json:
                encoded = encoded.replace("\\n", "\n").replace("\\t", "\t")
            stream_response(self, encoded)
            return
        if "harness-consolidation-plan" in text:
            self.responses.append("harness-plan")
            answer = {
                "kind": "harness-consolidation-plan",
                "version": 1,
                "schemaVersion": 1,
                "runId": field(text, "runId"),
                "scopeDigest": field(text, "scopeDigest"),
                "artifactHash": field(text, "artifactHash"),
                "operations": [{
                    "op": "addRule",
                    "rule": {
                        "id": "offline-loopback-block-marker",
                        "bash": r"^printf\s+CL_OFFLINE_BLOCKED$",
                        "action": "block",
                        "message": "The offline blocked marker is prohibited in this project.",
                    },
                    "cases": {
                        "positive": [{"bash": BLOCKED_COMMAND, "expected": "block"}],
                        "negative": [{"bash": SAFE_COMMAND}],
                    },
                }],
                "evidence": [{"index": 0, "source": "user", "quote": HARNESS_QUOTE, "count": 1}],
                "report": [{"index": 0, "summary": "Blocked marker is rejected while the safe marker remains executable."}],
            }
            stream_response(self, json.dumps(answer, separators=(",", ":")))
            return
        if "LOOPBACK_RUNTIME" in text:
            type(self).runtime_request_texts.append(text)
            type(self).runtime_calls += 1
            if type(self).runtime_calls == 1:
                self.responses.append("runtime-read-memory")
                memory_root = re.search(r'^Read roots \(first wins\): (\[[^\n]*\])$', text, re.MULTILINE)
                if not memory_root or "- loopback_memory_fact.md" not in text:
                    stream_response(self, "LOOPBACK_MEMORY_INDEX_MISSING")
                    return
                stream_response(self, [{"id": "runtime-read-memory", "name": "read", "arguments": {
                    "path": str(Path(json.loads(memory_root.group(1))[0]) / "loopback_memory_fact.md"),
                    "offset": 1, "limit": 100,
                }}])
            elif type(self).runtime_calls == 2:
                self.responses.append("runtime-blocked")
                stream_response(self, [{"id": "runtime-blocked", "name": "bash", "arguments": {"command": BLOCKED_COMMAND}}])
            elif type(self).runtime_calls == 3:
                self.responses.append("runtime-safe")
                stream_response(self, [{"id": "runtime-safe", "name": "bash", "arguments": {"command": SAFE_COMMAND}}])
            else:
                self.responses.append("runtime-done")
                stream_response(self, "LOOPBACK_RUNTIME_DONE")
            return
        self.responses.append("task-done")
        stream_response(self, "LOOPBACK_TASK_DONE")


def run_pi(project: Path, agent: Path, session: Path, prompt: str, port: int) -> subprocess.CompletedProcess[str]:
    pi = workspace_pi(REPO)
    disposable_home = agent.parent
    try:
        return subprocess.run(
            [
                pi,
                "--offline",
                "--no-extensions",
                "-e",
                str(PACKAGE / "index.ts"),
                "--no-skills",
                "--no-prompt-templates",
                "--no-themes",
                "--no-context-files",
                "--no-approve",
                "--session",
                str(session),
                "--print",
                "--mode",
                "json",
                "--model",
                f"{PROVIDER}/{MODEL}",
                "--tools",
                "read,bash",
                prompt,
            ],
            cwd=project,
            env=isolated_environment(disposable_home, agent),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired as error:
        raise AssertionError(
            f"Pi live run timed out; provider responses={LoopbackProvider.responses}, "
            f"requests={len(LoopbackProvider.requests)}"
        ) from error


def run() -> dict[str, object]:
    LoopbackProvider.requests = []
    LoopbackProvider.responses = []
    LoopbackProvider.runtime_request_texts = []
    LoopbackProvider.runtime_calls = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), LoopbackProvider)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="continual-learning-pi-v1-loop-") as raw:
            root = Path(raw)
            project, agent = root / "project", root / "agent"
            project.mkdir()
            agent.mkdir(mode=0o700)
            (project / ".pi").mkdir()
            (agent / "memory").mkdir()
            (agent / "settings.json").write_text(json.dumps({"quietStartup": True, "packages": []}))
            (agent / "continual-learning.json").write_text(json.dumps({"jev": False}))
            (agent / "memory.json").write_text(json.dumps({"provider": PROVIDER, "model": MODEL}))
            (agent / "models.json").write_text(json.dumps({"providers": {
                PROVIDER: {"baseUrl": f"http://127.0.0.1:{server.server_port}/v1", "api": "openai-completions", "apiKey": API_KEY,
                    "models": [{"id": MODEL, "reasoning": False, "input": ["text"], "contextWindow": 200000, "maxTokens": 4096,
                                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]},
            }}))
            (agent / "memory" / "settings.json").write_text(json.dumps({
                "autoMemory": True,
                "automaticPhases": {"memory": "apply", "harness": "apply", "agents": "off"},
                "agentsMd": {"disabled": True},
            }))
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            session = root / "session.jsonl"
            prompt = (
                "LOOPBACK_MEMORY_FACT: This project uses printf CL_OFFLINE_SAFE as its settled local verification command. "
                "LOOPBACK_HARNESS_RULE: Never run printf CL_OFFLINE_BLOCKED; that marker is prohibited in this project. "
                "Reply only LOOPBACK_TASK_DONE."
            )
            first = run_pi(project, agent, session, prompt, server.server_port)
            if first.returncode != 0:
                raise AssertionError(first.stderr[-3000:] or first.stdout[-3000:])

            harness_file = project / ".pi" / "harness.json"
            if not harness_file.is_file():
                raise AssertionError("real learning did not write project .pi/harness.json")
            harness = json.loads(harness_file.read_text())
            if not harness.get("learnedRules") or not harness.get("rules"):
                raise AssertionError(f"learned Harness ownership missing: {harness}")
            memory_files = list(project.glob(".memory/*.md")) + list(agent.glob("memory/*/*.md"))
            if not any("CL_OFFLINE_SAFE" in file.read_text() for file in memory_files):
                raise AssertionError("real learning did not persist the offline Memory fact")
            receipts = list(agent.glob("memory/runs/*/*/learning-pipeline-receipt.json"))
            if not receipts:
                raise AssertionError("learning pipeline receipt was not written")
            receipt = json.loads(receipts[-1].read_text())
            attempts = {(attempt["phase"], attempt["outcome"]) for attempt in receipt.get("attempts", [])}
            if {("memory", "applied"), ("harness", "applied")} - attempts:
                raise AssertionError(f"receipt lacks applied memory and Harness phases: {receipt}")
            harness_receipts = list(receipts[-1].parent.glob("harness-*-receipt.json"))
            if len(harness_receipts) < 2:
                raise AssertionError("Harness pre/post receipts were not written")
            # Empty-index selection is parent-routed; no generative selector call.
            selectors = [attempt for attempt in receipt["attempts"] if attempt["phase"] == "selector"]
            if not selectors or not any(attempt.get("outcome") == "applied" and "empty Memory index" in attempt.get("diagnostic", "") for attempt in selectors):
                raise AssertionError("empty-index parent routing lacks its selector receipt")
            expected_learning_responses = ["task-done", "memory-plan", "harness-plan"]
            if LoopbackProvider.responses != expected_learning_responses:
                raise AssertionError(f"first run needed an unexpected learning retry: {LoopbackProvider.responses}")

            evaluator = subprocess.run(
                ["bun", "-e", (
                    f'import {{mergeLayers,evaluateBash}} from {json.dumps(str(PACKAGE / "extensions/guardrail-engine.ts"))};'
                    f'const c=mergeLayers([{{...JSON.parse(await Bun.file({json.dumps(str(harness_file))}).text()),source:"project"}}]);'
                    f'console.log(JSON.stringify({{blocked:evaluateBash(c,{json.dumps(BLOCKED_COMMAND)}).decision,allowed:evaluateBash(c,{json.dumps(SAFE_COMMAND)}).decision}}));'
                )],
                cwd=REPO,
                check=True,
                capture_output=True,
                text=True,
            )
            decisions = json.loads(evaluator.stdout.strip().splitlines()[-1])
            if decisions != {"blocked": "block", "allowed": "execute"}:
                raise AssertionError(f"parent evaluator produced unexpected decisions: {decisions}")

            first_response_count = len(LoopbackProvider.responses)
            (agent / "memory" / "settings.json").write_text(json.dumps({"autoMemory": False, "agentsMd": {"disabled": True}}))
            second_session = root / "second-session.jsonl"
            second = run_pi(project, agent, second_session, "LOOPBACK_RUNTIME: run the blocked marker and then the safe marker.", server.server_port)
            if second.returncode != 0:
                raise AssertionError(second.stderr[-3000:] or second.stdout[-3000:])
            if "LOOPBACK_RUNTIME_DONE" not in second.stdout:
                raise AssertionError("runtime loop did not settle after the real block/allow sequence")
            execution_events = runtime_events(second.stdout)
            if len(LoopbackProvider.runtime_request_texts) < 2 or (
                "The settled local verification command is `printf CL_OFFLINE_SAFE`."
                not in LoopbackProvider.runtime_request_texts[1]
            ):
                raise AssertionError("the future model did not read the persisted Memory body before Bash")
            future_responses = LoopbackProvider.responses[first_response_count:]
            if future_responses != ["runtime-read-memory", "runtime-blocked", "runtime-safe", "runtime-done"]:
                raise AssertionError(f"autoMemory=false still caused learning calls: {future_responses}")
            first_runtime_request = LoopbackProvider.runtime_request_texts[0]
            if "# Project memories" not in first_runtime_request or "- loopback_memory_fact.md" not in first_runtime_request:
                raise AssertionError("persisted Memory index was not injected into the first future request")
            if "The settled local verification command is `printf CL_OFFLINE_SAFE`." in first_runtime_request:
                raise AssertionError("the future request unexpectedly injected the full Memory body")
            read_ends = [event for event in execution_events if event.get("type") == "tool_execution_end" and event.get("toolName") == "read"]
            if len(read_ends) != 1 or read_ends[0].get("isError") is not False or "CL_OFFLINE_SAFE" not in json.dumps(read_ends[0].get("result", {})):
                raise AssertionError("the real Pi read did not return the learned Memory body")
            bash_events = [event for event in execution_events if event.get("toolName") == "bash"]
            starts = [
                event.get("args", {}).get("command")
                for event in bash_events
                if event.get("type") == "tool_execution_start" and isinstance(event.get("args"), dict)
            ]
            ends = [event for event in bash_events if event.get("type") == "tool_execution_end"]
            if starts != [BLOCKED_COMMAND, SAFE_COMMAND] or len(ends) != 2:
                raise AssertionError(f"unexpected runtime Bash sequence: {execution_events}")
            if ends[0].get("isError") is not True or ends[1].get("isError") is not False:
                raise AssertionError(f"Harness did not block/allow the expected Bash calls: {execution_events}")
            if BLOCKED_COMMAND in json.dumps(ends[0].get("result", {})):
                raise AssertionError("blocked Bash command produced an execution result")
            if "CL_OFFLINE_SAFE" not in json.dumps(ends[1].get("result", {})):
                raise AssertionError("safe Bash command did not produce its execution result")
            return {
                "pi": pi_version(),
                "providerRequests": len(LoopbackProvider.requests),
                "providerResponses": LoopbackProvider.responses,
                "futureProviderResponses": future_responses,
                "memoryInjected": True,
                "memoryInjectedInRuntime": True,
                "memoryBodyRead": True,
                "receiptAttempts": sorted([list(item) for item in attempts]),
                "harnessDecisions": decisions,
                "runtimeEvents": execution_events,
                "blockedExecution": False,
                "safeExecution": True,
                "runtimeSettled": True,
                "externalNetwork": False,
                "roots": "disposable",
            }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def pi_version() -> str:
    result = subprocess.run([workspace_pi(REPO), "--version"], check=True, capture_output=True, text=True)
    return result.stdout.strip()


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False), flush=True)
