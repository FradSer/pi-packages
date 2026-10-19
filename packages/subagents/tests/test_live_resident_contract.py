"""Q1/Q3 through real Pi print, its production RPC children, and a native PTY.

No ambient environment/config is copied except PATH. The socket guard is inherited
by every real child and fails closed on non-loopback connections. All model input
and evidence in these tests is synthetic and remains under pytest's temporary root.
"""
from __future__ import annotations

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
        # ctrl+O adds each control detail exactly once on top of the collapsed row.
        for event in expanded:
            body = [line.strip() for line in event["lines"] if line.strip()]
            assert len(body) > 2, event
            joined = "\n".join(body)
            assert joined.count(f"session · {session}") == 1, event
            assert joined.count("model · resident-loopback/contract") == 1, event
            assert joined.count("tools · read, agent_memory") == 1, event
            assert all(source not in line for line in body), event
        tui.wait_for(lambda: f"session · {session}" in tui.screen())
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
