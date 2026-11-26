from __future__ import annotations

# --- Merged from test_live_resident_contract.py ---
"""Q1/Q3 through real Pi print, its production RPC children, and a native PTY.

No ambient environment/config is copied except PATH. The socket guard is inherited
by every real child and fails closed on non-loopback connections. All model input
and evidence in these tests is synthetic and remains under pytest's temporary root.
"""

import json
import os
import secrets
import signal
import subprocess
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from native_support import LoopbackServer, NativeTui, records

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "tests" / "live-resident-contract-fixture.ts"
PROVIDER = "resident-loopback"
MODEL = f"{PROVIDER}/contract"
NAME = "saved-reader"
ROLE = "PINNED_RESIDENT_ROLE: use only the granted tools and return the complete answer."

# Generated inside the temporary test root, never installed into global Node/Pi.
SOCKET_GUARD = r"""
const net = require('node:net');
const fs = require('node:fs');
const path = require('node:path');
const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...args) {
  const first = Array.isArray(args[0]) ? args[0][0] : args[0];
  const options = typeof first === 'object' && first !== null ? first : undefined;
  const host = options?.host ?? (typeof args[1] === 'string' ? args[1] : 'localhost');
  if (options?.path || typeof first === 'string' || !['127.0.0.1', '::1', 'localhost'].includes(host)) {
    fs.appendFileSync(path.join(__dirname, 'network-denied.jsonl'), JSON.stringify({host}) + '\n');
    throw new Error('Offline resident fixture blocked a non-loopback socket');
  }
  return Reflect.apply(connect, this, args);
};
"""




def selected(events: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [event for event in events if event["kind"] == kind]


def file_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()} if root.exists() else {}


@dataclass
class NativeResident:
    root: Path
    pi: str
    env: dict[str, str]
    server: ThreadingHTTPServer
    release: threading.Event
    requests: list[dict[str, Any]]
    saved_marker: str
    memory_marker: str
    pi_version: str
    processes: list[subprocess.Popen] = field(default_factory=list)
    runs: list[Path] = field(default_factory=list)

    @property
    def agent_dir(self) -> Path:
        return self.root / "agent"

    @property
    def cwd(self) -> Path:
        return self.root / "project"

    @property
    def definition(self) -> Path:
        return self.agent_dir / "agents" / NAME / "agent.md"

    def seed_memory(self) -> Path:
        root = self.agent_dir / "agents" / NAME / "memory"
        root.mkdir(parents=True, exist_ok=True)
        entry = root / "capability.md"
        entry.write_text("---\nname: capability\ndescription: Check isolated Memory restoration\n"
                         f"type: capability\n---\nReusable verification method: {self.memory_marker}\n",
                         encoding="utf-8")
        return entry

    def seed_definition(self, name: str, *, project: bool = False, memory: bool = False) -> Path:
        root = (self.cwd / ".pi" / "agents" if project else self.agent_dir / "agents") / name
        root.mkdir(parents=True, exist_ok=True)
        definition = root / "agent.md"
        definition.write_text(f"---\nname: {name}\ndescription: Offline resident contract\n"
                              f"tools: {'read' if memory else ''}\nmodel: {MODEL}\n"
                              f"---\n{ROLE}\n",
                              encoding="utf-8")
        return definition

    def command(self, case: str) -> tuple[list[str], dict[str, str], Path]:
        self.release.clear()
        evidence = self.root / f"{case}-{len(self.runs)}.jsonl"
        self.runs.append(evidence)
        env = {**self.env, "PI_LIVE_RESIDENT_CASE": case, "PI_LIVE_RESIDENT_EVIDENCE": str(evidence)}
        command = [self.pi, "--no-session", "--session-id", self.env["PI_LIVE_RESIDENT_PARENT_ID"],
                   "--no-extensions", "--no-skills", "--no-prompt-templates",
                   "--no-themes", "--no-context-files", "--no-approve", "--no-builtin-tools",
                   "--extension", str(FIXTURE), "--provider", "resident-parent-script",
                   "--model", "scripted", "--thinking", "off",
                   "Verify only the authorized offline saved-role and resident steering contracts."]
        return command, env, evidence

    def run_print(self, case: str) -> list[dict[str, Any]]:
        command, env, evidence = self.command(case)
        process = subprocess.Popen([*command, "--print"], cwd=self.cwd, env=env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
        self.processes.append(process)
        try:
            stdout, stderr = process.communicate(input="", timeout=45)
        except subprocess.TimeoutExpired:
            process.terminate()
            stdout, stderr = process.communicate(timeout=10)
            pytest.fail(f"Real pi --print timed out ({case}): {stderr}\n{stdout}\n{records(evidence)[-8:]}")
        assert process.returncode == 0, f"{case}: {stderr}\n{stdout}\n{records(evidence)[-8:]}"
        assert f"LIVE_RESIDENT_RESULT_{case}" in stdout, f"{case}: {stderr}\n{stdout}\n{records(evidence)}"
        events = records(evidence)
        assert not selected(events, "fixture-error"), events
        runtime, = selected(events, "parent-start")
        assert runtime["piVersion"] == self.pi_version, runtime
        assert runtime["sessionId"] == self.env["PI_LIVE_RESIDENT_PARENT_ID"], runtime
        launch, = selected(events, "launch")
        assert launch["piVersion"] == self.pi_version, launch
        assert not (self.root / "network-denied.jsonl").exists(), "A non-loopback network attempt was blocked"
        assert events[-1]["kind"] == "shutdown" and events[-1]["living"] == 0, events[-8:]
        assert len(selected(events, "launch")) == len(selected(events, "child-close")) == 1, events
        assert len(selected(events, "result")) == 1 and not selected(events, "ended"), events
        return events


@pytest.fixture
def native_resident(tmp_path: Path) -> Iterator[NativeResident]:
    assert FIXTURE.is_file(), "RED: the owned real-Pi resident contract fixture is not implemented"
    # Use the repository cohort, never an unrelated user-selected global model
    # or CLI version. This remains a real installed pi executable, not an SDK shim.
    pi = REPO / "node_modules" / ".bin" / "pi"
    if not pi.is_file():
        pytest.skip("Repository Pi CLI is unavailable; no native execution or TUI result is claimed")
    pi_version = json.loads((REPO / "node_modules/@earendil-works/pi-coding-agent/package.json").read_text())["version"]
    agent_dir = tmp_path / "agent"
    cwd = tmp_path / "project"
    for directory in (agent_dir, cwd, tmp_path / "tmp", tmp_path / "cache", tmp_path / "config"):
        directory.mkdir()
    credential = secrets.token_hex(24)
    saved_marker = "saved-" + secrets.token_hex(8)
    memory_marker = "memory-" + secrets.token_hex(8)
    requests: list[dict[str, Any]] = []
    release = threading.Event()

    class ModelHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            if self.path == "/release":
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                release.set()
                self.send_response(204)
                self.end_headers()
                return
            if self.path != "/v1/chat/completions" or self.headers.get("Authorization") != f"Bearer {credential}":
                self.send_error(403, "Only the generated loopback fixture credential is accepted")
                return
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            if not release.wait(timeout=30):
                self.send_error(504, "The real parent did not release the scripted model")
                return
            messages = payload["messages"]
            users = "\n".join(str(message.get("content", "")) for message in messages if message["role"] == "user")
            if "RESUME_KICKOFF" in users:
                if messages[-1]["role"] != "tool":
                    delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": "memory-read",
                        "type": "function", "function": {"name": "read", "arguments": json.dumps({
                            "path": str(agent_dir / "agents" / NAME / "memory" / "capability.md")})}}]}
                    finish = "tool_calls"
                else:
                    delta = {"role": "assistant", "content": f"RESUMED {saved_marker} {memory_marker}"}
                    finish = "stop"
            else:
                text = ("STEERED_FINAL" if "STEER_INPUT" in users else
                        "UNSTEERED_DRAFT" if "FIRST_KICKOFF" in users else
                        "TEMPORARY_FRESH" if "TEMPORARY_KICKOFF" in users else
                        "TUI_FINAL" if "TUI_KICKOFF" in users else
                        "PROJECT_FINAL" if "PROJECT_KICKOFF" in users else f"SAVED {saved_marker}")
                delta = {"role": "assistant", "content": text}
                finish = "stop"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            base = {"id": "offline-resident", "object": "chat.completion.chunk", "created": 1, "model": "contract"}
            try:
                for part, reason in ((delta, None), ({}, finish)):
                    chunk = {**base, "choices": [{"index": 0, "delta": part, "finish_reason": reason}]}
                    self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                # A failed/aborted fixture process must not strand server teardown.
                pass

    server = LoopbackServer(ModelHandler)
    base_url = f"http://127.0.0.1:{server.server_port}"
    (agent_dir / "settings.json").write_text(json.dumps({"theme": "dark", "quietStartup": True,
        "defaultProvider": PROVIDER, "defaultModel": "contract", "defaultThinkingLevel": "off",
        "defaultProjectTrust": "none", "autoCompactionEnabled": False, "autoRetryEnabled": False}), encoding="utf-8")
    (agent_dir / "auth.json").write_text("{}\n", encoding="utf-8")
    (agent_dir / "models.json").write_text(json.dumps({"providers": {PROVIDER: {
        "api": "openai-completions", "apiKey": credential, "baseUrl": base_url + "/v1",
        "models": [{"id": "contract", "name": "Offline resident", "reasoning": False, "input": ["text"],
                    "contextWindow": 200000, "maxTokens": 4096,
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}}}), encoding="utf-8")
    for path in (agent_dir / "auth.json", agent_dir / "models.json"):
        path.chmod(0o600)
    guard = tmp_path / "loopback-only.cjs"
    guard.write_text(SOCKET_GUARD, encoding="utf-8")
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(agent_dir),
           "PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "0",
           "TMPDIR": str(tmp_path / "tmp"), "XDG_CACHE_HOME": str(tmp_path / "cache"),
           "XDG_CONFIG_HOME": str(tmp_path / "config"), "TERM": "xterm-256color", "LANG": "en_US.UTF-8",
           "NODE_OPTIONS": f"--require={guard}", "PI_LIVE_RESIDENT_ROOT": str(tmp_path),
           "PI_LIVE_RESIDENT_URL": base_url, "PI_LIVE_RESIDENT_AUTH": credential,
           "PI_LIVE_RESIDENT_SAVED_MARKER": saved_marker, "PI_LIVE_RESIDENT_PARENT_ID": str(uuid.uuid4())}
    native = NativeResident(tmp_path, str(pi), env, server, release, requests, saved_marker, memory_marker, pi_version)
    try:
        yield native
    finally:
        release.set()
        for process in native.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        # Only orphaned process groups explicitly launched and recorded by this
        # fixture may be cleaned up; never inspect or stop another Pi session.
        for evidence in native.runs:
            events = records(evidence)
            closed = {event["pid"] for event in selected(events, "child-close")}
            for launch in selected(events, "launch"):
                if launch["pid"] in closed:
                    continue
                try:
                    os.killpg(launch["pid"], signal.SIGTERM)
                except ProcessLookupError:
                    pass
        server.close()


def assert_native_start_ack(events: list[dict[str, Any]]) -> None:
    """The start wrote exactly one native prompt, correlated with its receipt."""
    receipt = next(event for event in selected(events, "receipt") if event["action"] == "agent_start")
    assert receipt["details"]["ok"] is True, receipt
    # The start receipt is emitted only after the kickoff acknowledgement, so a
    # prompt write ordered before it is the start's own. Later scenario inputs
    # share the command type and are not part of this call.
    sent = [event for event in selected(events, "rpc-write")
            if event["record"]["type"] == "prompt" and event["order"] < receipt["order"]]
    assert len(sent) == 1, sent
    # Every start takes a prompt, so the role reaches the child with that input.
    assert ROLE in sent[0]["record"]["message"], sent
    schema, = selected(events, "schema")
    params = schema["parameters"]
    assert params["type"] == "object" and params["required"] == ["prompt"] and params["additionalProperties"] is False
    assert not any(key in params for key in ("oneOf", "anyOf", "allOf"))
    assert all(value.get("type") != "object" for value in params["properties"].values())
    assert set(params["properties"]) == {
        "prompt", "identity", "label", "instructions", "tools", "model", "fork",
    }
    accepted = [event for event in selected(events, "rpc-frame")
                if event["record"].get("type") == "response" and event["record"].get("id") == sent[0]["record"]["id"]]
    assert len(accepted) == 1, accepted
    ack = accepted[0]
    assert sent[0]["order"] < ack["order"] < receipt["order"], "Start escaped the actual correlated RPC acknowledgement"
    assert ack["record"]["success"] is True and ack["record"]["command"] == "prompt", ack
    assert ack["record"]["data"]["disposition"] == "started", ack


def probe(events: list[dict[str, Any]], tag: str) -> dict[str, Any]:
    return next(event["data"] for event in selected(events, "probe-state") if event["tag"] == tag)


def assert_result(events: list[dict[str, Any]], text: str) -> dict[str, Any]:
    result, = selected(events, "result")
    assert result["details"]["text"] == text and result["details"]["turn"] == 1, result
    assert result["options"] == {"deliverAs": "followUp", "triggerTurn": True}, result
    start = next(event for event in selected(events, "receipt") if event["action"] == "agent_start")
    assert result["details"]["session"] == start["details"]["session"], result
    assert result["content"].endswith(text + "\n</agent-result>"), result
    # A settled child stays addressable, and this envelope is the only delivery that
    # says so. A Leader that reads no such line spends a whole new process on a
    # follow-up the child it already holds could have taken.
    continuation = [line for line in result["content"].splitlines() if "agent_input" in line]
    assert len(continuation) == 1, result
    assert "IDLE" in continuation[0] and "not acceptance" in continuation[0], result
    return result


def test_disk_definition_resumes_history_and_memory_without_model_creation(native_resident: NativeResident) -> None:
    native = native_resident
    native.seed_definition(NAME, memory=True)
    first = native.run_print("save")
    assert_native_start_ack(first)
    assert_result(first, f"SAVED {native.saved_marker}")
    memory = native.seed_memory()
    definition = (native.definition.read_bytes(), native.definition.stat().st_mtime_ns)
    memory_before = (memory.read_bytes(), memory.stat().st_mtime_ns)
    saved_state = probe(first, "settled")
    saved_file = Path(saved_state["sessionFile"])
    assert saved_file.is_relative_to(native.agent_dir / "agents" / NAME / "projects")
    assert saved_file.parent.name == "session"
    assert records(saved_file)[0]["id"] == saved_state["sessionId"]
    native.requests.clear()
    resumed = native.run_print("resume")
    assert len(selected(resumed, "published-host")) == 1
    assert not selected(resumed, "unexpected-host-start") and not selected(resumed, "unexpected-host-stop")
    assert_native_start_ack(resumed)
    assert_result(resumed, f"RESUMED {native.saved_marker} {native.memory_marker}")
    assert "persistent" not in selected(first, "receipt")[0]["input"]
    assert "persistent" not in selected(resumed, "receipt")[0]["input"]
    assert selected(first, "receipt")[0]["details"]["session"] != selected(resumed, "receipt")[0]["details"]["session"]
    assert probe(resumed, "accepted")["sessionId"] == saved_state["sessionId"]
    assert probe(resumed, "settled")["sessionFile"] == str(saved_file)
    launch, = selected(resumed, "launch")
    assert "--continue" in launch["args"] and "--no-session" not in launch["args"]
    assert len(native.requests) == 2, "Memory must cross a real read tool call, not just a generated answer"
    initial = json.dumps(native.requests[0], ensure_ascii=False)
    assert native.saved_marker in initial and "=== AGENT MEMORY (saved-reader) ===" in initial
    assert "capability.md" in initial and native.memory_marker not in initial
    tools = {tool["function"]["name"] for tool in native.requests[0].get("tools", [])}
    assert tools == {"read", "agent_memory"}
    assert native.memory_marker in json.dumps(native.requests[1]["messages"][-1])
    assert len([event for event in selected(resumed, "rpc-frame")
                if event["record"].get("type") == "tool_execution_end" and event["record"].get("toolName") == "read"
                and not event["record"].get("isError")]) == 1
    receipt = next(event for event in selected(resumed, "receipt") if event["action"] == "agent_start")
    assert receipt["details"]["scope"] == "user"
    assert receipt["details"]["source"] == str(native.definition)
    assert (native.definition.read_bytes(), native.definition.stat().st_mtime_ns) == definition
    assert (memory.read_bytes(), memory.stat().st_mtime_ns) == memory_before
    durable_before = file_snapshot(native.agent_dir / "agents" / NAME / "projects")
    all_memory_before = file_snapshot(native.agent_dir / "agents" / NAME)
    native.requests.clear()
    temporary = native.run_print("temporary")
    assert_native_start_ack(temporary)
    assert_result(temporary, "TEMPORARY_FRESH")
    assert "persistent" not in selected(temporary, "receipt")[0]["input"]
    launch, = selected(temporary, "launch")
    assert "--no-session" in launch["args"] and "--continue" not in launch["args"]
    assert "--session-dir" not in launch["args"]
    # The user-requested stream classification contribution is not Memory or persistence.
    extensions = [Path(launch["args"][index + 1]).name for index, flag in enumerate(launch["args"]) if flag == "--extension"]
    assert extensions == ["stream-recovery.ts"]
    state = probe(temporary, "accepted")
    assert not state.get("sessionFile") and state["sessionId"] != saved_state["sessionId"]
    assert len(native.requests) == 1
    payload = json.dumps(native.requests[0], ensure_ascii=False)
    assert native.saved_marker not in payload and native.memory_marker not in payload and "AGENT MEMORY" not in payload
    assert {tool["function"]["name"] for tool in native.requests[0].get("tools", [])} == set()
    assert (native.definition.read_bytes(), native.definition.stat().st_mtime_ns) == definition
    assert file_snapshot(native.agent_dir / "agents" / NAME / "projects") == durable_before
    assert file_snapshot(native.agent_dir / "agents" / NAME) == all_memory_before
    receipt = next(event for event in selected(temporary, "receipt") if event["action"] == "agent_start")
    assert receipt["details"]["scope"] == "session"
    assert not (native.agent_dir / "agents" / "temporary-reader").exists()
    assert probe(temporary, "settled")["isStreaming"] is False


def test_project_derivation_never_creates_a_user_definition(native_resident: NativeResident) -> None:
    native = native_resident
    definition = native.seed_definition("project-reader", project=True)
    before = (definition.read_bytes(), definition.stat().st_mtime_ns)
    events = native.run_print("project")
    assert_native_start_ack(events)
    assert_result(events, "PROJECT_FINAL")
    assert "persistent" not in selected(events, "receipt")[0]["input"]
    assert not (native.agent_dir / "agents" / "project-reader" / "agent.md").exists()
    assert (definition.read_bytes(), definition.stat().st_mtime_ns) == before
    state = probe(events, "settled")
    assert Path(state["sessionFile"]).is_relative_to(native.agent_dir / "agents" / "project-reader" / "projects")
    receipt = next(event for event in selected(events, "receipt") if event["action"] == "agent_start")
    assert receipt["details"]["scope"] == "project"
    assert receipt["details"]["source"] == str(definition)


def test_real_interrupt_steers_one_turn_and_idle_busy_refusals_never_write(native_resident: NativeResident) -> None:
    native = native_resident
    native.seed_definition("resident-steer")
    events = native.run_print("steer")
    assert_native_start_ack(events)
    assert_result(events, "STEERED_FINAL")
    interrupt = next(event for event in selected(events, "receipt") if event["id"] == "working-interrupt")
    idle = next(event for event in selected(events, "receipt") if event["id"] == "idle-interrupt")
    closed = next(event for event in selected(events, "receipt") if event["id"] == "closed-input")
    assert interrupt["details"]["ok"] is True and interrupt["details"]["disposition"] == "steered", interrupt
    assert idle["details"]["ok"] is False and "delivery" in idle["content"][0]["text"], idle
    assert closed["details"]["ok"] is False and "closed" in closed["content"][0]["text"], closed
    writes = [event["record"] for event in selected(events, "rpc-write")]
    inputs = [command for command in writes if command["type"] == "prompt"]
    # One kickoff prompt and one steer. Neither refusal reaches the stream.
    assert len(inputs) == 2 and [command["streamingBehavior"] for command in inputs] == ["followUp", "steer"], inputs
    assert inputs[1]["message"] == "STEER_INPUT", inputs
    assert all(command["type"] != "new_session" for command in writes)
    steer_ack, = [event["record"] for event in selected(events, "rpc-frame")
                  if event["record"].get("type") == "response" and event["record"].get("id") == inputs[1]["id"]]
    assert steer_ack["success"] is True and steer_ack["data"]["disposition"] == "queued", steer_ack
    ready, active, settled = (probe(events, tag) for tag in ("ready", "steered", "settled"))
    # The kickoff prompt is in flight at the first probe; the steer adds one
    # pending message, and the settled turn leaves none.
    assert ready["isStreaming"] is True and active["isStreaming"] is True
    assert ready["pendingMessageCount"] == 0 and active["pendingMessageCount"] == 1
    assert settled["isStreaming"] is False and settled["pendingMessageCount"] == 0
    assert ready["sessionId"] == active["sessionId"] == settled["sessionId"]
    assert ready["sessionFile"] == active["sessionFile"] == settled["sessionFile"]
    wire = [event["record"] for event in selected(events, "rpc-frame")]
    assert sum(frame.get("type") == "agent_start" for frame in wire) == 1
    assert sum(frame.get("type") == "agent_settled" for frame in wire) == 1
    assert len(native.requests) == 2, "Native steering may add an assistant response inside the same resident turn"
    last = json.dumps(native.requests[-1]["messages"], ensure_ascii=False)
    assert last.count("STEER_INPUT") == 1 and last.count(ROLE) == 1
    assert "CLOSED_REFUSED_INPUT" not in last and "IDLE_REFUSED_INPUT" not in last
    steer_ack_event, = [event for event in selected(events, "rpc-frame")
        if event["record"].get("type") == "response" and event["record"].get("id") == inputs[1]["id"]]
    assert steer_ack_event["order"] < interrupt["order"], "Interrupt success must follow native steering acceptance"
    assert interrupt["resident"]["status"] == "working"
    assert idle["details"]["session"] == interrupt["details"]["session"] == closed["details"]["session"]
    assert closed["resident"]["status"] == "stopped"
    assert native.root.joinpath("network-denied.jsonl").exists() is False


def test_native_tui_ctrl_o_reveals_session_definition_source(native_resident: NativeResident) -> None:
    native = native_resident
    native.seed_definition(NAME, memory=True)
    native.seed_memory()
    command, env, evidence = native.command("tui")
    try:
        tui = NativeTui(command, cwd=native.cwd, env=env, rows=32, columns=200,
                        timeout=40, start_new_session=True)
    except OSError as error:
        pytest.skip(f"Native PTY permission/CLI blocker: {error}; no TUI result is claimed")
    native.processes.append(tui.process)

    try:
        tui.wait_for(lambda: any(event["kind"] == "agent-row" and not event["partial"] for event in records(evidence)))
        events = records(evidence)
        assert_native_start_ack(events)
        receipt = next(event for event in selected(events, "receipt") if event["action"] == "agent_start")
        source = receipt["details"]["source"]
        assert source == str(native.definition) and receipt["details"]["scope"] == "user"
        session = receipt["details"]["session"]
        collapsed = [event for event in selected(events, "agent-row") if not event["expanded"] and not event["partial"]]
        assert collapsed and all(event["bounded"] for event in collapsed), collapsed
        # The collapsed row carries the child's state and its kickoff line only.
        # The row vocabulary states control details, not filesystem provenance;
        # the definition source stays in the receipt the model read.
        assert all(sum(1 for line in event["lines"] if line.strip()) == 2 for event in collapsed), collapsed
        assert all(session not in "\n".join(event["lines"]) for event in collapsed), collapsed
        assert session not in tui.screen(), "The exact control handle belongs to the expanded row"
        tui.send(b"\x0f")
        tui.wait_for(lambda: any(event["kind"] == "agent-row" and event["expanded"] and not event["partial"]
                            for event in records(evidence)))
        expanded = [event for event in selected(records(evidence), "agent-row") if event["expanded"] and not event["partial"]]
        assert expanded and all(event["bounded"] for event in expanded), expanded
        # ctrl+O reveals the startup configuration, never runtime handles.
        for event in expanded:
            body = [line.strip() for line in event["lines"] if line.strip()]
            assert len(body) > 2, event
            joined = "\n".join(body)
            assert f"session · {session}" not in joined, event
            assert session not in joined, event
            assert joined.count("model · resident-loopback/contract") == 1, event
            assert joined.count("tools · read, agent_memory") == 1, event
            assert all(source not in line for line in body), event
        tui.wait_for(lambda: "model · resident-loopback/contract" in tui.screen())
        native.release.set()
        tui.wait_for(lambda: "LIVE_RESIDENT_RESULT_tui" in tui.screen())
        assert_result(records(evidence), "TUI_FINAL")
        tui.send(b"/quit\r")
        tui.wait_for(lambda: tui.process.poll() is not None)
        assert tui.process.returncode == 0
        events = records(evidence)
        assert events[-1]["kind"] == "shutdown" and events[-1]["living"] == 0
        assert len(selected(events, "launch")) == len(selected(events, "child-close")) == 1
        assert selected(events, "parent-start")[0]["piVersion"] == native.pi_version
        assert selected(events, "launch")[0]["piVersion"] == native.pi_version
        assert not selected(events, "fixture-error") and not selected(events, "ended")
        assert not (native.root / "network-denied.jsonl").exists()
    finally:
        native.release.set()
        tui.close()


# --- Merged from test_live_agent_usage.py ---
"""Real Pi print and PTY reproductions backed only by a loopback model server."""

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from native_support import NativeTui, records

REPO = Path(__file__).resolve().parents[3]


SHORT_RESULT = "2"
MULTILINE_RESULT = "FIRST_RESULT_LINE\n\nSECOND_RESULT_LINE"
LONG_RESULT = "word " * 55 + "REQUIRED_RESULT_TAIL"






def test_native_print_returns_once_and_parent_shutdown_closes_temporary_child(native_command: tuple, tmp_path: Path) -> None:
    command, env, snapshots, requests, release = native_command
    release.set()
    result = subprocess.run([*command, '--print'], cwd=tmp_path, env=env,
        input='', text=True, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stderr + result.stdout
    events = records(snapshots)
    receipts = [event for event in events if event['kind'] == 'receipt']
    answers = [event for event in events if event['kind'] == 'result']
    assert len(receipts) == len(answers) == len(requests) == 1, events
    assert 'arrives asynchronously' in receipts[0]['content'][0]['text']
    assert receipts[0]['details']['session'].startswith('session:')
    assert answers[0]['options'] == {'deliverAs': 'followUp', 'triggerTurn': True}
    assert answers[0]['content'].endswith(env['PI_AGENT_RESULT_TEXT'] + '\n</agent-result>')
    assert answers[0]['details']['text'] == env['PI_AGENT_RESULT_TEXT']
    assert answers[0]['details']['turn'] == 1
    assert events[-1] == {'kind': 'shutdown', 'living': 0, 'results': 1}, events
    assert not any(event['kind'] == 'mount' for event in events)
    assert not (tmp_path / 'agent' / 'agents').exists()
    assert not (tmp_path / 'agent' / 'subagent-sessions').exists()


# Formatting axes belong here, not in every lifecycle/control reproduction.
@pytest.mark.parametrize("case,native_command", [
    ("default", SHORT_RESULT), ("default", MULTILINE_RESULT), ("interrupt-expansion", LONG_RESULT),
], indirect=["native_command"], ids=["short", "multiline", "steered-long"])
def test_native_tui_shows_activity_resizes_retains_idle_and_clears_on_shutdown(native_command: tuple, tmp_path: Path, case: str) -> None:
    command, env, snapshots, requests, release = native_command
    steering = "STEER_FIRST_LINE " + "steering " * 45 + "REQUIRED_STEER_TAIL"
    if case == "interrupt-expansion":
        env = {**env, "PI_AGENT_USAGE_CASE": case, "PI_AGENT_STEER_TEXT": steering}
    tui = NativeTui(command, cwd=tmp_path, env=env, rows=28, columns=90)

    def widget_at(width: int) -> bool:
        return any(event['kind'] == 'widget' and event['width'] == width for event in records(snapshots))

    try:
        tui.wait_for(lambda: bool(requests) and 'calculator · Starting...' in tui.screen())
        model = 'subagents-local-fixture/arithmetic'
        collapsed = [event for event in records(snapshots)
            if event['kind'] == 'agent-row' and event.get('action') == 'agent_start' and not event['partial'] and not event['expanded']]
        assert collapsed, 'the native tool must render its settled startup receipt'
        assert all(model not in '\n'.join(event['lines']) for event in collapsed), collapsed
        assert f'model · {model}' not in tui.screen()
        # Native Ctrl+O expansion reveals exactly one model detail, while the
        # original model-facing receipt still contains its own configuration.
        if case == "interrupt-expansion":
            tui.wait_for(lambda: "NATIVE_INTERRUPT_READY" in tui.screen())
            steering_rows = [event for event in records(snapshots) if event['kind'] == 'agent-row'
                and event.get('action') == 'agent_input' and not event['partial'] and not event['expanded']]
            assert steering_rows, 'the steer receipt paints a row'
            # The collapsed steer row is its head line plus the authored headline,
            # so the affordance ends the head rather than the last line.
            for event in steering_rows:
                head = next((line.strip() for line in event['lines'] if line.strip()), '')
                assert head.startswith('[agent] steered · @calculator'), head
                assert re.search(r'to expand$', head), head
                assert 'REQUIRED_STEER_TAIL' not in '\n'.join(event['lines']), event['lines']
        tui.send(b'\x0f')
        tui.wait_for(lambda: any(event['kind'] == 'agent-row' and event.get('action') == 'agent_start' and event['expanded']
            for event in records(snapshots)))
        if case == "interrupt-expansion":
            # The steer row is expanded on screen; the fixture records it once the
            # next render happens, so the terminal is the authority here.
            tui.wait_for(lambda: 'REQUIRED_STEER_TAIL' in tui.screen())
            steering_rows = [event for event in records(snapshots) if event['kind'] == 'agent-row'
                and event.get('action') == 'agent_input' and event['expanded']]
            assert steering_rows and all(event['bounded'] for event in steering_rows)
            payload = [row for row in steering_rows if 'REQUIRED_STEER_TAIL' in '\n'.join(row['lines'])]
            assert payload, 'the expanded steer row carries the steer payload'
            row = '\n'.join(payload[-1]['lines'])
            assert row.count('REQUIRED_STEER_TAIL') == row.count('STEER_FIRST_LINE') == 1, row
            assert row.count('steering') == 45, row
            assert 'state · working' not in row and 'next · runtime' not in row, row
            assert 'session · session:' not in row, row
            steered = next(event for event in records(snapshots)
            if event['kind'] == 'receipt' and event['details'].get('operation') == 'agent_input')
            assert steered['details']['prompt'] == steering and steered['structuredContent']['prompt'] == steering
        expanded = [event for event in records(snapshots)
            if event['kind'] == 'agent-row' and event.get('action') == 'agent_start' and not event['partial'] and event['expanded']]
        assert expanded and all(event['bounded'] for event in expanded)
        for event in expanded:
            row = '\n'.join(event['lines'])
            assert row.count(model) == 1, row
            assert f'model · {model}' in row and 'MODEL ·' not in row, row
        receipt = next(event for event in records(snapshots) if event['kind'] == 'receipt')
        assert f'Model: {model}' in receipt['content'][0]['text']
        assert receipt['details']['model'] == model
        tui.send(b'\x0f')
        for width in (48, 240):
            tui.resize(width)

            tui.wait_for(lambda: widget_at(width))
        events = records(snapshots)
        widgets = [event for event in events if event['kind'] == 'widget']
        assert widgets and all(event['bounded'] for event in widgets)
        assert any(event['kind'] == 'mount' and event['placement'] == 'aboveEditor' for event in events)
        assert all(not re.search(r'session:|[0-9a-f]{8}-[0-9a-f]{4}-', '\n'.join(event['lines'])) for event in widgets)
        tui.resize(90)

        release.set()
        tui.wait_for(lambda: 'SUBAGENT_RESULT_2' in tui.screen())
        # The child settled with its answer delivered, so it leaves the activity
        # area: only work in flight occupies it, and a stale row would imply work.
        # The child settled and its answer was delivered, so it leaves the activity
        # area: the newest widget snapshot must not mention it, and an unmounted
        # area counts as empty.
        def settled() -> bool:
            log = records(snapshots)
            delivered = next((index for index, event in enumerate(log)
                if event['kind'] == 'result'), None)
            if delivered is None:
                return False
            after = [event for event in log[delivered:] if event['kind'] == 'widget']
            return not any('calculator' in line for event in after for line in event['lines'])

        tui.wait_for(settled)
        # Steering can create another assistant response in the same sequence,
        # not a second child/input lifetime. Only the final settlement delivers.
        assert len(requests) == (2 if case == "interrupt-expansion" else 1)
        if case == "interrupt-expansion":
            assert steering in json.dumps(requests[-1], ensure_ascii=False)
        events = records(snapshots)
        assert len([event for event in events if event['kind'] == 'result']) == 1
        widget_events = [event for event in events if event['kind'] == 'widget']
        assert widget_events and all(event['bounded'] for event in widget_events), events
        assert settled(), [event for event in records(snapshots)[-4:]]
        result_text = env['PI_AGENT_RESULT_TEXT']
        answer_lines = [line for line in result_text.splitlines() if line.strip()]
        collapsed_results = [event for event in events if event['kind'] == 'result-row' and not event['expanded']]
        assert collapsed_results and all(event['bounded'] for event in collapsed_results), events
        for event in collapsed_results:
            row = '\n'.join(event['lines'])
            assert 'Session Result' not in row and not re.search(r'turn [0-9]', row), row
            visible = [line.strip() for line in event['lines'] if line.strip()]
            assert len(visible) == 1, visible
            assert visible[0].startswith('[agent] reported · @calculator'), visible
            assert re.search(r'to expand$', visible[0]), visible
            assert not any(line in row for line in answer_lines), 'the answer waits for expansion'
        marker = max((token for line in answer_lines for token in line.split()), key=len)
        # One press asks Pi to expand its newest tool output. Asking twice, before
        # the first render arrives, toggles that same row straight back closed; the
        # terminal is the authority for the expanded body, so the press is awaited
        # here instead of rechecked immediately. Which row the snapshot records is
        # the race, not which row the key reaches.
        tui.send(b'\x0f')
        tui.wait_for(lambda: marker in tui.screen())
        # The terminal is the authority for the expanded body: a steer row and a
        # reported row share one expand key, so which snapshot records it is a race.
        screen = tui.screen()
        assert not re.search(r'\[agent\] reported · @calculator · \S*to expand', screen), screen[-2000:]
        assert all(token in screen for token in answer_lines[-1].split()[-2:]), screen[-2000:]
        expanded_results = [event for event in records(snapshots)
            if event['kind'] == 'result-row' and event['expanded']]
        assert all(event['bounded'] for event in expanded_results), expanded_results
        for event in expanded_results:
            row = '\n'.join(event['lines'])
            assert 'Session Result' not in row and 'to expand' not in row, row
            assert all(token in row for line in answer_lines for token in line.split()), row
        delivered = next(event for event in records(snapshots) if event['kind'] == 'result')
        assert delivered['details']['text'] == result_text and delivered['details']['turn'] == 1
        assert delivered['details']['session'].startswith('session:')
        tui.send(b'/quit\r')
        tui.wait_for(lambda: tui.process.poll() is not None)
        assert tui.process.returncode == 0
        assert any(event['kind'] == 'clear' for event in records(snapshots))
        assert records(snapshots)[-1] == {'kind': 'shutdown', 'living': 0, 'results': 1}
    finally:
        release.set()
        tui.close()


@pytest.mark.parametrize("interface", ["print", "tui"])
@pytest.mark.parametrize("diagnostic,case", [("", "stopped-inspect"),
    ("\x1b[31mNATIVE_ERROR_HEAD\x1b[0m\x07" + " x" * 12000 + "RAW_ERROR_TAIL", "stopped-inspect"),
    ("", "cancel-startup-wait"), ("", "codemode-lifecycle")],
    ids=["without-error", "long-retained-error", "cancel-startup-wait", "codemode-lifecycle"])
def test_native_roster_read_reports_retained_stopped_facts_not_a_failed_row(
    native_command: tuple, tmp_path: Path, interface: str, diagnostic: str, case: str,
) -> None:
    """Native lifecycle after a stop; invented retained error specifically probes
    the roster page's readback bounds. The roster page is a status summary, so it
    carries no per-child output preview: the answer arrives with the Session Result."""
    command, env, snapshots, requests, release = native_command
    env = {**env, "PI_AGENT_USAGE_CASE": case, "PI_AGENT_INSPECT_DIAGNOSTIC": diagnostic}
    release.set()
    if interface == "print":
        result = subprocess.run([*command, "--print"], cwd=tmp_path, env=env,
            input="", text=True, capture_output=True, timeout=45)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "NATIVE_STOPPED_INSPECT_OK" in result.stdout, result.stdout + result.stderr
    else:
        tui = NativeTui(command, cwd=tmp_path, env=env, rows=28, columns=90, timeout=45)
        try:
            tui.wait_for(lambda: "NATIVE_STOPPED_INSPECT_OK" in tui.screen())
            if case == "cancel-startup-wait":
                # No route came back, so no stop or roster row exists: the roster
                # read and the uncertain start row are the whole witness.
                assert "[agent] uncertain · @calculator" in tui.screen(), tui.screen()
                assert "[agent] listed" in tui.screen(), tui.screen()
            elif case != "codemode-lifecycle":
                # A roster carries no child's name and, when the page omitted
                # nothing, no count either: the collapsed row never names the child
                # it read, and "1 of 1" would answer a question nothing asked.
                assert "[agent] listed" in tui.screen(), tui.screen()
                assert "1 of 1" not in tui.screen(), tui.screen()
                assert "[agent] listed · @calculator" not in tui.screen(), tui.screen()
            else:
                # Native codemode uses Pi's own unbracketed title, not pi-kit.
                assert "codemode" in tui.screen() and "Script error:" not in tui.screen(), tui.screen()
            assert "No living session" not in tui.screen(), tui.screen()
            if case != "cancel-startup-wait":
                assert "[agent] failed" not in tui.screen(), tui.screen()
            else:
                assert "cancelled" in tui.screen(), tui.screen()
            if case != "codemode-lifecycle":
                tui.send(b"\x0f")
                tui.wait_for(lambda: any(event["kind"] == "agent-row"
                    and event.get("action") == "agent_list" and event["expanded"]
                    for event in records(snapshots)))
                rows = [event for event in records(snapshots) if event["kind"] == "agent-row"
                    and event.get("action") == "agent_list"]
                assert rows and all(event["bounded"] for event in rows), rows
                assert all("[agent] " in "\n".join(event["lines"]) for event in rows), rows
                # The page keeps the child's own status as expansion detail, naming
                # the child once, and the collapsed subject stays the page.
                collapsed = [event for event in rows if not event["expanded"]]
                assert collapsed and all("@calculator" not in "\n".join(event["lines"]) for event in collapsed), collapsed
                expanded = [event for event in rows if event["expanded"]]
                assert expanded, rows
                headers = [line.strip() for event in expanded for line in event["lines"] if "@calculator · " in line]
                assert headers and all(header.count("@calculator") == 1 for header in headers), headers
                if case != "cancel-startup-wait":
                    assert "@calculator · stopped" in headers, headers
            tui.send(b"/quit\r")
            tui.wait_for(lambda: tui.process.poll() is not None)
            assert tui.process.returncode == 0
        finally:
            tui.close()
    events = records(snapshots)
    receipts = [event for event in events if event["kind"] == "receipt"]
    if case == "cancel-startup-wait":
        # A cancelled start returns no route, so the only follow-up a caller can make
        # is the roster read. It has to show the child the cancellation could not.
        assert [event["details"]["operation"] for event in receipts] == ["agent_start", "agent_list"], receipts
        assert receipts[0]["details"]["disposition"] == "uncertain" and receipts[0]["isError"] is True
        assert receipts[0]["details"]["controlOutcome"] == "uncertain"
        listed, = receipts[1]["details"]["sessions"]
        assert listed["label"] == "calculator", listed
        cancelled, = [event for event in events if event["kind"] == "cancelled-native-start"]
        assert cancelled["living"] == 1 and cancelled["details"]["dispatched"] is True
        assert not receipts[1]["isError"]
        assert events[-1] == {"kind": "shutdown", "living": 0, "results": 1}
        return
    assert [event["details"]["operation"] for event in receipts] == ["agent_start", "agent_stop", "agent_list"], receipts
    assert receipts[0]["details"]["ok"] and not receipts[0]["isError"], receipts
    assert all(event["details"]["ok"] and not event["isError"] for event in receipts[1:]), receipts
    for event in receipts:
        assert event["structuredContent"]["operation"] == event["details"]["operation"]
        assert event["structuredContent"]["disposition"] == event["details"]["disposition"]
        assert event["structuredContent"]["ok"] == event["details"]["ok"]
    started, stopped, listed = [event["details"] for event in receipts]
    view, = listed["sessions"]
    assert view["status"] == "stopped" and view["session"] == started["session"] == stopped["session"]
    assert view["label"] == "calculator", view
    assert view["resultKind"] == "result" and view["sequenceEnded"] is True
    # The roster page is a status summary. It omits the output preview on purpose,
    # because a child's complete answer arrives with its Session Result.
    assert "liveText" not in view and "liveText" in view["truncation"]["omittedFields"], view
    # One page, one child, and the page says which part of the roster it holds.
    assert listed["page"]["returned"] == 1 and listed["page"]["remaining"] == 0, listed["page"]
    assert listed["page"]["totalSessions"] + listed["page"]["totalDefinitions"] == 1, listed["page"]
    preservation, = [event for event in events if event["kind"] == "inspect-preservation"]
    assert preservation == {"kind": "inspect-preservation", "unchanged": True,
        "rawErrorLength": len(diagnostic), "errorRetained": True}
    if diagnostic:
        expected = ("NATIVE_ERROR_HEAD" + " x" * 12000 + "RAW_ERROR_TAIL")[:1000] + "… [diagnostic truncated]"
        assert view["error"] == expected
        listed_event = receipts[-1]
        assert "error · " + expected in listed_event["content"][0]["text"]
        assert "RAW_ERROR_TAIL" not in json.dumps(listed_event)
        assert "\x1b" not in listed_event["content"][0]["text"] and "\x07" not in listed_event["content"][0]["text"]
    else:
        assert "error" not in view
    assert len(requests) == 1, "The roster read must not start another model request or revive the child"
    assert len([event for event in events if event["kind"] == "result"]) == 1
    assert events[-1] == {"kind": "shutdown", "living": 0, "results": 1}
    assert not (tmp_path / "agent" / "agents").exists()
    assert not (tmp_path / "agent" / "subagent-sessions").exists()


# --- Merged from test_live_cancel_authority.py ---
"""Native Pi/RPC authority plus explicitly invented hosted-confirmation faults."""

import os
import subprocess
import time
from pathlib import Path

import pytest

from native_support import NativeTui, records



# Every ownership fault runs through native print/RPC. TUI checks cancellation
# and its late diagnostic; ownership permutations do not change the renderer.
@pytest.mark.parametrize('interface,scenario', [
    ('print', 'stop-pending'), ('print', 'forged-successor'),
    ('print', 'late-control-failure'), ('print', 'reentrant-successor'),
    ('tui', 'stop-pending'), ('tui', 'late-control-failure'),
])
def test_native_controls_keep_exact_owner_after_cancellation(
    native_command: tuple, tmp_path: Path, interface: str, scenario: str,
) -> None:
    """The host's delayed/faulty return is synthetic; actual children and RPC are not."""
    command, env, snapshots, requests, release = native_command
    command = list(command)
    old = str(Path(__file__).resolve().parents[3] / 'tests' / 'live-agent-usage-fixture.ts')
    command[command.index(old)] = str(Path(__file__).resolve().parents[3] / 'tests' / 'live-cancel-authority-fixture.ts')
    env = {**env, 'PI_CANCEL_AUTHORITY_CASE': scenario}
    # Only late-control sends model input. Hold its response through inspect/stop
    # so an actual final answer cannot masquerade as the faulted control outcome.
    if scenario != 'late-control-failure':
        release.set()
    if interface == 'print':
        result = subprocess.run([*command, '--print'], cwd=tmp_path, env=env,
            input='', capture_output=True, text=True, timeout=35)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'NATIVE_AUTHORITY_DONE' in result.stdout, result.stdout + result.stderr
    else:
        tui = NativeTui(command, cwd=tmp_path, env=env, rows=35, columns=100, timeout=35)
        try:
            tui.wait_for(lambda: 'NATIVE_AUTHORITY_DONE' in tui.screen())
            assert '[agent] listed' in tui.screen(), tui.screen()
            assert 'cancelled' in tui.screen(), tui.screen()
            tui.send(b'/quit\r')
            tui.wait_for(lambda: tui.process.poll() is not None)
            assert tui.process.returncode == 0
        finally:
            tui.close()
    events = records(snapshots)
    receipts = [event for event in events if event['kind'] == 'receipt']
    failures = [event for event in receipts if event['isError']]
    assert len(failures) == 1, receipts
    assert failures[0]['details']['code'] == 'cancelled', receipts
    assert failures[0]['details']['disposition'] == 'uncertain', receipts
    cancelled, = [event for event in events if event['kind'] == 'cancelled-native-control']
    assert cancelled['data']['code'] == 'cancelled' and cancelled['data']['disposition'] == 'uncertain', cancelled
    if scenario == 'reentrant-successor':
        assert 'session' not in cancelled['data'] and 'session' not in failures[0]['details']
    else:
        assert cancelled['data']['session'] == failures[0]['details']['session']
    if scenario == 'late-control-failure':
        # A cancelled input keeps its reservation with the runtime. The real
        # native dispatch is the correlated acknowledgement the host recorded.
        assert 'dispatched' not in cancelled['data'], cancelled
    else:
        assert cancelled['data']['dispatched'] is True, cancelled
    closes = [event for event in events if event['kind'] == 'native-close']
    assert all(event['outcome'] in ['closed', 'missing'] for event in closes), closes
    shutdown = events[-1]
    assert shutdown['kind'] == 'shutdown' and shutdown['living'] == 0, events
    assert all(child['pid'] > 1 for child in shutdown['children'])
    assert len(shutdown['children']) == (2 if scenario == 'forged-successor' else 1)
    assert [entry['owner'] for entry in shutdown['hostStops']] == (
        ['original', 'successor'] if scenario == 'forged-successor'
        else ['successor'] if scenario == 'reentrant-successor' else ['original'])
    if scenario == 'forged-successor':
        assert any(event['kind'] == 'successor-preserved' for event in events)
        assert len({entry['session'] for entry in shutdown['hostStops']}) == 2
    elif scenario == 'stop-pending':
        assert any(event['kind'] == 'late-confirmation-refused' for event in events)
        readback, = [event for event in events if event['kind'] == 'roster-readback']
        assert readback['status'] == 'stopped', events
        assert readback['session'].startswith('session:'), events
    elif scenario == 'reentrant-successor':
        assert any(event['kind'] == 'synthetic-reentrant-start' for event in events)
        preserved, = [event for event in events if event['kind'] == 'reentrant-owner-preserved']
        assert shutdown['hostStops'][0]['session'] == preserved['session']
        assert any(event['kind'] == 'native-readiness' and event['owner'] == 'successor' and event['accepted'] for event in events)
        assert any(event['kind'] == 'roster-readback' and event['session'] == preserved['session'] for event in events)
    else:
        assert any(event['kind'] == 'native-input-ack' and event['accepted'] for event in events)
        assert any(event['kind'] == 'late-failure-readback' for event in events)
        # ADR-0008 left no inspection operation, so the roster is the surviving read.
        listed = next(event['details'] for event in receipts if event['details']['operation'] == 'agent_list')
        assert listed['disposition'] == 'listed', listed
        assert 'LATE_NATIVE_CONTROL_FAILURE' in listed['sessions'][0]['error']
    assert len(requests) <= (1 if scenario == 'late-control-failure' else 0)
    assert not (tmp_path / 'agent' / 'agents').exists()
    assert not (tmp_path / 'agent' / 'subagent-sessions').exists()


# --- Merged from test_live_intent.py ---
"""Isolated native Pi print verification for the five-tool model interface."""

import json
import os
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from native_support import LoopbackServer, NativeTui

REPO = Path(__file__).resolve().parents[3]
PROSE_LABEL = "Task SQL measured optimization"
PROSE_LABEL_ENV = {"PI_INTENT_LABEL": PROSE_LABEL}


def assert_confirmed_stop(report: dict[str, object]) -> None:
    stops = [control for control in report["controls"] if control["tool"] == "agent_stop"]
    assert len(stops) == 1, "Every run must record its exact stop outcome."
    stop = stops[0]
    assert not stop["isError"] and stop["details"]["ok"] and stop["details"]["disposition"] == "stopped", "Stop was not confirmed."
    assert stop["details"]["session"] == report["receipts"][0]["session"], "Stop must address the original exact session."
    assert stop["details"]["state"] == "stopped", "The stop receipt must report observed closure."


# Storage selection and retry are protocol assertions, already checked in print.
# TUI retains continuation, steering, pending cancellation and native error rows.
@pytest.mark.parametrize("interface,case,drop_first_stream", [
    ("print", "configured", False), ("print", "configured", True),
    ("print", "stop-pending", False), ("print", "saved-identity", False),
    ("print", "steer", False), ("print", "rejected-stop", False),
    ("print", "prose-label", False), ("tui", "prose-label", False),
    ("tui", "configured", False), ("tui", "stop-pending", False),
    ("tui", "steer", False), ("tui", "rejected-stop", False),
])
def test_native_next_input_keeps_history_and_result_ids(tmp_path: Path, interface: str, case: str, drop_first_stream: bool) -> None:
    requests: list[dict[str, object]] = []
    closed = threading.Event()

    class LocalModel(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            request_index = len(requests)
            if case == "stop-pending":
                closed.wait(timeout=30)
                return
            if request_index == 1:
                time.sleep(0.5)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if drop_first_stream and request_index == 1:
                self.wfile.write(("data: " + json.dumps({"error": {"message":
                    "stream error: stream disconnected before completion: stream closed before response.completed"}}) + "\n\n").encode())
                self.wfile.flush()
                return
            answer = ("INTERMEDIATE" if request_index == 1 else "STEERED_FINAL") if case == "steer" else (
                "FIRST RESULT" if request_index == (2 if drop_first_stream else 1) else "SECOND RESULT")
            for delta, finish in (({"role": "assistant", "content": answer}, None), ({}, "stop")):
                chunk = {"id": "intent-answer", "object": "chat.completion.chunk", "created": 1, "model": "fixture",
                         "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    server = LoopbackServer(LocalModel)
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    credential = secrets.token_hex(16)
    definition = agent_dir / "agents" / "native-saved" / "agent.md"
    if case == "saved-identity":
        definition.parent.mkdir(parents=True)
        definition.write_text("---\nname: native-saved\ndescription: Native saved identity fixture\ntools: []\n---\nSAVED_IDENTITY_INSTRUCTIONS\n")
    (agent_dir / "settings.json").write_text(json.dumps({"quietStartup": True,
        "packages": [str(REPO / "packages" / "subagents")],
        "extensions": ["-builtin:mcp", "-builtin:llama.cpp", "-builtin:codemode", "-builtin:tool-search"],
        "retry": {"enabled": True, "maxRetries": 1, "baseDelayMs": 0}}))
    (agent_dir / "models.json").write_text(json.dumps({"providers": {
        "intent-loopback": {"baseUrl": f"http://127.0.0.1:{server.server_port}/v1", "api": "openai-completions",
                            "apiKey": credential, "models": [{"id": "fixture", "reasoning": False, "input": ["text"],
                            "contextWindow": 200000, "maxTokens": 4096,
                            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}
    }}))
    evidence = tmp_path / "intent-evidence.json"
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(agent_dir),
           "PI_OFFLINE": "1", "PI_INTENT_AUTH": credential, "PI_INTENT_EVIDENCE": str(evidence),
           "PI_INTENT_CONFIGURED": "1", "PI_INTENT_CASE": case,
           **({**PROSE_LABEL_ENV} if case == "prose-label" else {})}
    cli = REPO / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
    screen = ""
    try:
        command = ["node", str(cli), "--no-session", "--no-skills",
                   "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-approve",
                   "--no-builtin-tools", "--extension", str(Path(__file__).with_name("live-intent-fixture.ts")),
                   "--provider", "intent-parent", "--model", "scripted", "--thinking", "off",
                   "Run the authorized native intent fixture"]
        if interface == "print":
            result = subprocess.run([*command, "--print"], cwd=tmp_path, env=env,
                                    input="", capture_output=True, text=True, timeout=40)
            assert result.returncode == 0, result.stderr + result.stdout
            assert "NATIVE_INTENT_OK" in result.stdout
        else:
            with NativeTui(command, cwd=tmp_path, env=env, rows=28, columns=70, timeout=40) as tui:
                tui.wait_for(lambda: "NATIVE_INTENT_OK" in tui.screen())
                # Captured before the resize, so the assertion reads the composer
                # at the width the rows were first painted at.
                screen = tui.screen()
                tui.send(b'\x0f')
                tui.resize(45)
                tui.send(b'/quit\r')
                tui.wait_for(lambda: tui.process.poll() is not None)
                assert tui.process.returncode == 0, tui.screen()[-5000:]
        report = json.loads(evidence.read_text())
        family = {"agent_start", "agent_input", "agent_stop", "agent_list"}
        assert set(report["activeTools"]) & (family | {"agent"}) == family
        assert len(report["receipts"]) == 2
        assert all(receipt["ok"] and not receipt["isError"] for receipt in report["receipts"]), report
        stopped = [control for control in report["controls"] if control["tool"] == "agent_stop"]
        assert len(stopped) == 1, "Every applicable run must record its exact stop outcome."
        exact = report["receipts"][0]["session"]
        stop = stopped[0]
        if case == "rejected-stop":
            assert stop["isError"] and not stop["details"]["ok"] and stop["details"]["disposition"] == "rejected", report
            assert stop["details"]["session"] == exact + "-not-current"
            # The same successful-run acceptance gate must reject this terminal-marker run.
            with pytest.raises(AssertionError, match="Stop was not confirmed"):
                assert_confirmed_stop(report)
        else:
            assert_confirmed_stop(report)
            assert all(control["details"]["ok"] and not control["isError"] for control in report["controls"]), report
        assert report["receipts"][1]["disposition"] == ("steered" if case == "steer" else "queued")
        if case == "steer":
            assert [entry["text"] for entry in report["notices"]] == ["STEERED_FINAL"]
            assert report["receipts"][0]["inputId"] == report["receipts"][1]["inputId"] == report["notices"][0]["inputId"]
            assert len(requests) == 2
            assert json.dumps(requests[-1]["messages"]).count("STEER_INPUT") == 1
        elif case == "stop-pending":
            assert len(report["notices"]) == 1, report
            assert report["notices"][0]["kind"] == "input-cancelled"
            assert report["notices"][0]["inputId"] == report["receipts"][1]["inputId"]
            assert [entry["details"]["disposition"] for entry in report["controls"]] == ["stopped", "listed"]
            stopped_rows, = [row for row in report["controls"][1]["details"]["sessions"] if row["status"] == "stopped"]
            assert stopped_rows["inputId"], "the roster page keeps the stopped incarnation's input"
            assert len(requests) <= 1
            assert all("SECOND INPUT" not in json.dumps(request) for request in requests)
        else:
            assert [entry["text"] for entry in report["notices"]] == ["FIRST RESULT", "SECOND RESULT"]
            assert [entry["inputId"] for entry in report["notices"]] == [entry["inputId"] for entry in report["receipts"]]
            assert len(report["notices"]) == 2
            assert len(requests) == (3 if drop_first_stream else 2)
            assert "FIRST RESULT" in json.dumps(requests[-1]["messages"])
            if drop_first_stream:
                assert "SECOND INPUT" not in json.dumps(requests[1]["messages"]), "Next input cannot enter a retrying sequence"
        if case == "saved-identity":
            assert report["receipts"][0]["identity"] == "native-saved"
            assert report["receipts"][0]["label"] == "native-intent"
            assert all("SAVED_IDENTITY_INSTRUCTIONS" in json.dumps(request) for request in requests)
            home = definition.parent
            assert (home / "memory" / "MEMORY.md").is_file()
            assert list((home / "projects").glob("*/parents/parent-*/session/*.jsonl"))
            assert definition.read_text().endswith("SAVED_IDENTITY_INSTRUCTIONS\n")
        elif case == "prose-label":
            # One real Pi process, one real composer: the display name a row reads
            # is one identifier-shaped token, and the authored phrasing is absent.
            authored = PROSE_LABEL
            projected = "task-sql-measured-optimization"
            assert report["receipts"][0]["label"] == projected, report["receipts"][0]
            assert [notice["name"] for notice in report["notices"]] == [projected] * 2, report["notices"]
            stopped_rows = [row for row in report["controls"][0]["details"].get("sessions", [])
                            if row["status"] == "stopped"]
            assert report["controls"][0]["details"]["state"] == "stopped", report["controls"][0]
            assert report["controls"][0]["details"]["label"] == projected, report["controls"][0]
            assert all(row["label"] == projected for row in stopped_rows), stopped_rows
            if interface == "tui":
                assert f"@{projected}" in screen, screen
                assert authored not in screen, screen
        else:
            assert not (agent_dir / "agents").exists()
    finally:
        closed.set()
        server.close()


# --- Merged from test_live_temporary_resident.py ---
"""Real temporary child remains sendable; two accepted inputs, two results, one process."""

import json
import os
import secrets
import subprocess
from http.server import BaseHTTPRequestHandler

from native_support import LoopbackServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_temporary_agent_retains_history_until_explicit_stop(tmp_path: Path) -> None:
    requests: list[dict[str, object]] = []

    class LocalModel(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            answer = "2" if len(requests) == 1 else "5"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for delta, finish in (({"role":"assistant","content":answer},None),({},"stop")):
                chunk={"id":"temporary-answer","object":"chat.completion.chunk","created":1,"model":"arithmetic",
                    "choices":[{"index":0,"delta":delta,"finish_reason":finish}]}
                self.wfile.write(("data: "+json.dumps(chunk)+"\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()

    server = LoopbackServer(LocalModel)
    agent_dir=tmp_path/"agent";agent_dir.mkdir()
    credential=secrets.token_hex(16)
    (agent_dir/"settings.json").write_text(json.dumps({"quietStartup":True}))
    (agent_dir/"models.json").write_text(json.dumps({"providers":{
        "temporary-loopback":{"baseUrl":f"http://127.0.0.1:{server.server_port}/v1",
            "api":"openai-completions","apiKey":credential,"models":[{"id":"arithmetic",
            "reasoning":False,"input":["text"],"contextWindow":200000,"maxTokens":4096,
            "cost":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0}}]}
    }}))
    evidence=tmp_path/"temporary-evidence.json"
    env={"PATH":os.environ["PATH"],"HOME":str(tmp_path),"PI_CODING_AGENT_DIR":str(agent_dir),
        "PI_OFFLINE":"1","PI_TEMPORARY_AUTH":credential,"PI_TEMPORARY_EVIDENCE":str(evidence)}
    cli=REPO/"node_modules"/"@earendil-works"/"pi-coding-agent"/"dist"/"cli.js"
    try:
        result=subprocess.run(["node",str(cli),"--print","--no-session","--no-extensions",
            "--no-skills","--no-prompt-templates","--no-themes","--no-context-files","--no-approve",
            "--no-builtin-tools","--extension",str(REPO/"tests"/"live-temporary-resident-fixture.ts"),
            "--provider","temporary-parent","--model","scripted","--thinking","off",
            "Run two prompts through the same temporary agent"],cwd=tmp_path,env=env,
            input="",capture_output=True,text=True,timeout=45)
        assert result.returncode == 0, result.stderr+result.stdout
        assert evidence.is_file(), result.stderr + result.stdout
        report=json.loads(evidence.read_text())
        assert report["texts"] == ["2","5"], report
        assert report["turns"] == [1,2], report
        assert report["sameSession"] is True and report["idleAfterFirst"] is True, report
        assert report["stopped"] is True and report["living"] == 0, report
        assert len(requests) == 2
        transcript=json.dumps(requests[1]["messages"],ensure_ascii=False)
        assert "1+1" in transcript and "2+3" in transcript
        assert not (agent_dir/"agents").exists()
        assert not (agent_dir/"subagent-sessions").exists()
        assert not (agent_dir/"workspaces").exists()
    finally:
        server.close()


# --- Merged from test_live_unanswered_results.py ---
"""Real Pi/RPC/loopback cases for empty review output and incomplete final text."""

import json
import os
import secrets
import subprocess
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from native_support import LoopbackServer, NativeTui

REPO = Path(__file__).resolve().parents[3]


# Print covers every parsing/result variation. TUI covers each visible outcome
# and exhausted retry, without repeating whitespace and transport equivalents.
@pytest.mark.parametrize("interface,first_text,finish,reason,retries", [
    ("print", "", "stop", "empty", 0),
    ("print", "  \n\t", "stop", "empty", 0),
    ("print", "Partial review", "length", "length", 0),
    ("print", "", "length", "length", 0),
    ("print", "", "error", "error", 0),
    ("print", "", "stream-close", "error", 0),
    ("print", "", "stream-close", "error", 1),
    ("tui", "", "stop", "empty", 0),
    ("tui", "Partial review", "length", "length", 0),
    ("tui", "", "error", "error", 0),
    ("tui", "", "stream-close", "error", 1),
])
def test_native_blank_or_truncated_review_is_not_a_successful_result(
    tmp_path: Path, first_text: str, finish: str, reason: str, retries: int, interface: str,
) -> None:
    requests: list[dict[str, object]] = []

    class LocalModel(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            first = len(requests) <= 1 + retries
            text = first_text if first else "Complete final review. Static only."
            final_reason = finish if first else "stop"
            if first and finish == "error":
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": {"message": "LOCAL REVIEW PROVIDER ERROR",
                    "type": "invalid_request_error"}}).encode())
                self.wfile.flush()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if first and finish == "stream-close":
                self.wfile.write(("data: " + json.dumps({"error": {"message":
                    "stream error: stream disconnected before completion: stream closed before response.completed"}}) + "\n\n").encode())
                self.wfile.flush()
                return
            for delta, stop in (({"role": "assistant", "content": text}, None), ({}, final_reason)):
                chunk = {"id": "blank-review", "object": "chat.completion.chunk", "created": 1, "model": "reviewer",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": stop}]}
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    server = LoopbackServer(LocalModel)
    agent = tmp_path / "agent"
    agent.mkdir()
    credential = secrets.token_hex(16)
    (agent / "settings.json").write_text(json.dumps({"quietStartup": True,
        "retry": {"enabled": retries > 0, "maxRetries": retries, "baseDelayMs": 0}, "compaction": {"enabled": False}}))
    (agent / "models.json").write_text(json.dumps({"providers": {
        "unanswered-loopback": {"api": "openai-completions", "apiKey": credential,
            "baseUrl": f"http://127.0.0.1:{server.server_port}/v1",
            "models": [{"id": "reviewer", "reasoning": False, "input": ["text"],
                "contextWindow": 200000, "maxTokens": 4096,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}
    }}))
    evidence = tmp_path / "outcomes.json"
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(agent),
        "PI_OFFLINE": "1", "PI_UNANSWERED_AUTH": credential, "PI_UNANSWERED_EVIDENCE": str(evidence), "TERM": "xterm-256color"}
    cli = REPO / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
    try:
        command = ["node", str(cli), "--no-session", "--no-extensions",
            "--no-skills", "--no-prompt-templates", "--no-context-files", "--no-themes", "--no-approve",
            "--no-builtin-tools", "--extension", str(REPO / "tests" / "live-unanswered-result-fixture.ts"),
            "--provider", "unanswered-parent", "--model", "scripted", "--thinking", "off",
            "Reproduce blank review and request one later answer"]
        if interface == "print":
            # Include the 30-second cold-start window and both scripted inputs.
            result = subprocess.run([*command, "--print"], cwd=tmp_path, env=env,
                input="", text=True, capture_output=True, timeout=65)
            assert result.returncode == 0, result.stdout + result.stderr
            assert "UNANSWERED_REPRO_DONE" in result.stdout, result.stdout + result.stderr
        else:
            # A tall terminal keeps the whole native transcript on screen, so the
            # expanded unanswered row stays visible next to the rows below it.
            tui = NativeTui(command, cwd=tmp_path, env=env, rows=60, columns=100, timeout=60)
            try:
                tui.wait_for(lambda: "UNANSWERED_REPRO_DONE" in tui.screen())
                # The collapsed row names the child and the verdict only; the reason
                # is expansion detail, so the reader opens the row to read it.
                assert "[agent] unanswered · @reviewer" in tui.screen(), tui.screen()
                tui.send(b"\x0f")
                tui.wait_for(lambda: "No usable final answer" in tui.screen())
                tui.send(b"/quit\r")
                tui.wait_for(lambda: tui.process.poll() is not None)
                assert tui.process.returncode == 0
            finally:
                tui.close()
        report = json.loads(evidence.read_text())
        first, second = report["notices"]
        assert first["kind"] == "unanswered" and first["reason"] == reason, report
        assert first["text"] == first_text and first["stopReason"] == ("error" if finish == "stream-close" else finish), first
        if finish == "stream-close":
            assert "stream closed before response.completed" in first["errorMessage"], first
            assert "explicit final answer" not in json.dumps(requests[0]["messages"])
        if finish == "error":
            assert "LOCAL REVIEW PROVIDER ERROR" in first["errorMessage"], first
        assert second["kind"] == "result" and second["text"] == "Complete final review. Static only."
        assert first["turn"] == 1 and second["turn"] == 2
        assert report["sameHandle"] is True and report["closed"] is True and report["living"] == 0
        assert len(requests) == 2 + retries, "The native retry budget and one explicit send are the only requests"
        if retries:
            assert "explicit final answer" not in json.dumps(requests[1]["messages"]), "The retry cannot dispatch the later input"
        assert not (agent / "agents").exists()
        assert not (agent / "subagent-sessions").exists()
    finally:
        server.close()
