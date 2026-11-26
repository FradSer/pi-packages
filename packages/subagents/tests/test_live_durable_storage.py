from __future__ import annotations

# --- Merged from test_live_durable_storage.py ---
"""Native loopback proof for one durable identity across two projects."""

import json
import os
import secrets
import subprocess
import uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

import pytest

from native_support import LoopbackServer

REPO = Path(__file__).resolve().parents[3]
PI = REPO / "node_modules" / ".bin" / "pi"
FIXTURE = Path(__file__).with_name("native-durable-storage-fixture.ts")
NAME = "native-durable"
MEMORY_NAME = "native-capability"
MEMORY_MARKER = "NATIVE_CAPABILITY_MARKER"
SCRATCH_MARKER = "NATIVE_SHARED_SCRATCH"
PROJECT_A_MARKER = "NATIVE_PROJECT_A_RELATIVE"
PROJECT_B_MARKER = "NATIVE_PROJECT_B_RELATIVE"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line] if path.exists() else []


class LocalChildModel:
    """Scripted child model; every response is served from loopback only."""

    def __init__(self, root: Path, credential: str) -> None:
        self.root = root
        self.credential = credential
        self.parent_session_id = str(uuid.uuid4())
        self.requests: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.counts: dict[str, int] = {}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: object) -> None:
                pass

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/v1/chat/completions" or self.headers.get("Authorization") != f"Bearer {owner.credential}":
                    self.send_error(403, "unexpected provider request")
                    return
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append(payload)
                messages = payload.get("messages", [])
                serialized = json.dumps(messages, ensure_ascii=False)
                user_messages = [message for message in messages if message.get("role") == "user"]
                latest_user = json.dumps(user_messages[-1], ensure_ascii=False) if user_messages else ""
                if "NATIVE_DURABLE_RESUME_A" in latest_user:
                    phase = "resume-a"
                elif "NATIVE_DURABLE_PROJECT_B" in latest_user:
                    phase = "project-b"
                else:
                    phase = "write-a"
                index = owner.counts.get(phase, 0)
                owner.counts[phase] = index + 1
                if index == 0:
                    expected_history = phase == "resume-a"
                    if phase != "write-a" and ("HISTORY_A" in serialized) != expected_history:
                        owner.errors.append(f"history marker mismatch in {phase}")
                    tool_names = {tool.get("function", {}).get("name") for tool in payload.get("tools", [])}
                    if tool_names != {"read", "write", "agent_memory"}:
                        owner.errors.append(f"grant mismatch in {phase}: {sorted(tool_names)!r}")
                latest_user_index = max((index for index, message in enumerate(messages)
                                         if message.get("role") == "user"), default=-1)
                current_tool_messages = [message for index, message in enumerate(messages)
                                         if index > latest_user_index and message.get("role") == "tool"]
                memory = owner.root / "agent" / "agents" / NAME / "memory" / f"{MEMORY_NAME}.md"
                scratch = owner.root / "agent" / "agents" / NAME / "workspace" / "scratch-marker.txt"
                calls: dict[str, dict[int, tuple[str, dict[str, str]]]] = {
                    "write-a": {
                        0: ("agent_memory", {"action": "append", "name": MEMORY_NAME,
                                               "description": "Native durable capability", "body": MEMORY_MARKER}),
                        1: ("write", {"path": "project-a-marker.txt", "content": PROJECT_A_MARKER}),
                        2: ("write", {"path": str(scratch), "content": SCRATCH_MARKER}),
                        3: ("read", {"path": "project-a-marker.txt"}),
                    },
                    "resume-a": {
                        0: ("read", {"path": str(memory)}),
                        1: ("read", {"path": str(scratch)}),
                        2: ("read", {"path": "project-a-marker.txt"}),
                    },
                    "project-b": {
                        0: ("read", {"path": str(memory)}),
                        1: ("read", {"path": str(scratch)}),
                        2: ("write", {"path": "project-b-marker.txt", "content": PROJECT_B_MARKER}),
                    },
                }
                required: dict[str, list[str]] = {
                    "write-a": [PROJECT_A_MARKER],
                    "resume-a": [MEMORY_MARKER, PROJECT_A_MARKER, SCRATCH_MARKER],
                    "project-b": [MEMORY_MARKER, SCRATCH_MARKER],
                }
                call = calls[phase].get(index)
                final_index = 4 if phase == "write-a" else 3
                if index == final_index:
                    tool_text = json.dumps(current_tool_messages, ensure_ascii=False)
                    for marker in required[phase]:
                        if marker not in tool_text:
                            owner.errors.append(f"missing {marker} in {phase} tool results")
                    if phase == "project-b" and "HISTORY_A" in serialized:
                        owner.errors.append("project B received project A history")
                    call = None
                if call is None:
                    delta: dict[str, Any] = {"role": "assistant", "content": f"NATIVE_{phase.upper().replace('-', '_')}_CHILD_OK"}
                    finish = "stop"
                else:
                    tool, arguments = call
                    delta = {"role": "assistant", "tool_calls": [{"index": 0,
                        "id": f"native-{phase}-{index}", "type": "function",
                        "function": {"name": tool, "arguments": json.dumps(arguments)}}]}
                    finish = "tool_calls"
                base = {"id": "native-durable", "object": "chat.completion.chunk", "created": 1, "model": "scripted"}
                chunks = [
                    {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                    {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
                ]
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                try:
                    for chunk in chunks:
                        self.wfile.write(("data: " + json.dumps({**base, **chunk}) + "\n\n").encode())
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.httpd = LoopbackServer(Handler)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}"

    def close(self) -> None:
        self.httpd.close()


def run_phase(server: LocalChildModel, root: Path, project: Path, phase: str, prompt: str, auth: str) -> dict[str, Any]:
    evidence = root / f"{phase}.json"
    env = {
        "PATH": os.environ["PATH"], "HOME": str(root), "PI_CODING_AGENT_DIR": str(root / "agent"),
        "PI_OFFLINE": "1", "PI_NATIVE_DURABLE_ROOT": str(root), "PI_NATIVE_DURABLE_PROJECT": str(project),
        "PI_NATIVE_DURABLE_EVIDENCE": str(evidence), "PI_NATIVE_DURABLE_PHASE": phase,
        "PI_NATIVE_DURABLE_PROMPT": prompt, "PI_NATIVE_DURABLE_AUTH": auth,
        "PI_NATIVE_DURABLE_PARENT_ID": server.parent_session_id,
    }
    command = [str(PI), "--print", "--no-session", "--session-id", server.parent_session_id,
               "--no-skills", "--no-prompt-templates", "--no-themes",
               "--no-context-files", "--no-approve", "--no-builtin-tools", "--extension", str(FIXTURE),
               "--provider", "native-durable-parent", "--model", "scripted", "Run native durable storage phase"]
    result = subprocess.run(command, cwd=project, env=env, input="", text=True, capture_output=True, timeout=75)
    evidence_data = json.loads(evidence.read_text(encoding="utf-8")) if evidence.exists() else {}
    assert result.returncode == 0, result.stderr + result.stdout + json.dumps(evidence_data)
    assert "NATIVE_DURABLE_OK" in result.stdout, result.stdout + result.stderr
    assert evidence_data.get("phase") == phase
    assert evidence_data.get("project") == str(project)
    assert evidence_data.get("parentSessionId") == server.parent_session_id
    assert len(evidence_data.get("launches", [])) == len(evidence_data.get("closes", [])) == 1, evidence_data
    assert len(evidence_data.get("notices", [])) >= 1, evidence_data
    receipts = evidence_data.get("receipts", [])
    assert [receipt.get("tool") for receipt in receipts] == ["agent_start", "agent_stop"], evidence_data
    assert all(receipt.get("isError") is not True for receipt in receipts), evidence_data
    final_notices = [notice for notice in evidence_data["notices"] if notice.get("customType") == "subagents-session-result"]
    assert len(final_notices) == 1 and final_notices[0].get("kind") == "result", evidence_data
    assert receipts[0].get("session") == final_notices[0].get("session") == receipts[1].get("session"), evidence_data
    assert evidence_data.get("failures") == [], evidence_data
    assert evidence_data.get("frames"), evidence_data
    assert evidence_data["launches"][0].get("cwd") == str(project), evidence_data
    assert evidence_data["closes"][0].get("pid") == evidence_data["launches"][0].get("pid"), evidence_data
    expected_tools = {
        "write-a": ["agent_memory", "write", "write", "read"],
        "resume-a": ["read", "read", "read"],
        "project-b": ["read", "read", "write"],
    }[phase]
    tool_ends = [frame for frame in evidence_data["frames"] if frame.get("type") == "tool_execution_end"]
    assert [frame.get("toolName") for frame in tool_ends] == expected_tools, evidence_data
    assert all(frame.get("isError") is not True for frame in tool_ends), evidence_data
    return evidence_data


@pytest.mark.skipif(not PI.is_file(), reason="Repository Pi CLI is unavailable")
def test_native_durable_storage_across_projects(tmp_path: Path) -> None:
    agent_dir = tmp_path / "agent"
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    for directory in (agent_dir, project_a, project_b):
        directory.mkdir(parents=True)
    auth = secrets.token_hex(24)
    identity = agent_dir / "agents" / NAME
    identity.mkdir(parents=True)
    definition = identity / "agent.md"
    definition.write_text("---\nname: native-durable\ndescription: Native durable storage proof\n"
                          "tools: read, write\nmodel: native-durable-child/scripted\n---\nUse only granted tools.\n", encoding="utf-8")
    (agent_dir / "settings.json").write_text(json.dumps({"quietStartup": True}), encoding="utf-8")
    (agent_dir / "auth.json").write_text("{}\n", encoding="utf-8")
    server = LocalChildModel(tmp_path, auth)
    try:
        (agent_dir / "models.json").write_text(json.dumps({"providers": {"native-durable-child": {
            "api": "openai-completions", "apiKey": auth, "baseUrl": server.url + "/v1",
            "models": [{"id": "scripted", "name": "Native durable child", "reasoning": False,
                        "input": ["text"], "contextWindow": 200000, "maxTokens": 4096,
                        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}}}), encoding="utf-8")
        for private_file in (agent_dir / "auth.json", agent_dir / "models.json"):
            private_file.chmod(0o600)
        token = "HISTORY_A_" + secrets.token_hex(8)
        definition_before = (definition.read_bytes(), definition.stat().st_mtime_ns)
        run_phase(server, tmp_path, project_a, "write-a", f"NATIVE_DURABLE_WRITE_A {token}", auth)
        memory = identity / "memory" / f"{MEMORY_NAME}.md"
        scratch = identity / "workspace" / "scratch-marker.txt"
        assert MEMORY_MARKER in memory.read_text(encoding="utf-8")
        assert scratch.read_text(encoding="utf-8") == SCRATCH_MARKER
        assert scratch.parent.is_dir() and not (scratch.parent / ".git").exists()
        assert (project_a / "project-a-marker.txt").read_text(encoding="utf-8") == PROJECT_A_MARKER
        run_phase(server, tmp_path, project_a, "resume-a", "NATIVE_DURABLE_RESUME_A", auth)
        projects = identity / "projects"
        history_before_b = {path.relative_to(projects).as_posix(): path.read_bytes() for path in projects.rglob("*.jsonl")}
        assert history_before_b
        project_a_before_b = {path.relative_to(project_a).as_posix(): path.read_bytes() for path in project_a.rglob("*") if path.is_file()}
        memory_before_b = memory.read_bytes()
        scratch_before_b = scratch.read_bytes()
        run_phase(server, tmp_path, project_b, "project-b", "NATIVE_DURABLE_PROJECT_B", auth)
        assert (project_b / "project-b-marker.txt").read_text(encoding="utf-8") == PROJECT_B_MARKER
        assert {path.relative_to(project_a).as_posix(): path.read_bytes() for path in project_a.rglob("*") if path.is_file()} == project_a_before_b
        history_after_b = {path.relative_to(projects).as_posix(): path.read_bytes() for path in projects.rglob("*.jsonl")}
        assert {key: history_after_b[key] for key in history_before_b} == history_before_b
        new_history = set(history_after_b) - set(history_before_b)
        assert new_history
        old_projects = {Path(key).parts[0] for key in history_before_b}
        new_projects = {Path(key).parts[0] for key in new_history}
        assert old_projects.isdisjoint(new_projects)
        assert memory.read_bytes() == memory_before_b and scratch.read_bytes() == scratch_before_b
        assert (definition.read_bytes(), definition.stat().st_mtime_ns) == definition_before
        assert server.errors == [], server.errors
        assert server.counts == {"write-a": 5, "resume-a": 4, "project-b": 4}, server.counts
    finally:
        server.close()


# --- Merged from test_live_history_safety.py ---
"""Native Pi must not load or append outside history through private-session links."""

import hashlib
import json
import os
import secrets
import subprocess
import uuid
from pathlib import Path

import pytest

from subagents_helpers import SRC, PACKAGE, run_node


@pytest.mark.parametrize("link", ["symlink", "hard-link"])
def test_native_resume_refuses_linked_history_without_touching_target(tmp_path: Path, link: str) -> None:
    (tmp_path / "project").mkdir()
    script=f"""
      import fs from "node:fs";import path from "node:path";
      import {{SessionManager}} from "@earendil-works/pi-coding-agent";
      import {{agentSessionPath}} from {json.dumps((SRC/"workspace.ts").as_uri())};
      const cwd=process.env.PI_TEST_CWD;
      const outside=path.join(process.env.HOME,"outside-history");fs.mkdirSync(outside);
      const session=SessionManager.create(cwd,outside);
      session.appendMessage({{role:"user",content:"OUTSIDE_PRIVATE_SENTINEL",timestamp:1}});
      const file=session.getSessionFile();
      const dir=agentSessionPath("unsafe-reader",cwd,process.env.PI_HISTORY_SAFETY_PARENT_ID);fs.mkdirSync(dir,{{recursive:true}});
      if({json.dumps(link)}==="symlink")fs.symlinkSync(file,path.join(dir,"linked.jsonl"));else fs.linkSync(file,path.join(dir,"linked.jsonl"));
      console.log(JSON.stringify({{file,dir}}));
    """
    env={"PATH":os.environ["PATH"],"HOME":str(tmp_path),"PI_CODING_AGENT_DIR":str(tmp_path/"agent"),
        "PI_TEST_CWD":str(tmp_path/"project"),"PI_OFFLINE":"1","PI_HISTORY_SAFETY_ROOT":str(tmp_path),
        "PI_HISTORY_SAFETY_AUTH":secrets.token_hex(16),"PI_HISTORY_SAFETY_PARENT_ID":str(uuid.uuid4())}
    setup=run_node(script,env_overrides=env)
    outside=Path(setup["file"]);before=(hashlib.sha256(outside.read_bytes()).hexdigest(),outside.stat().st_mtime_ns)
    definition=tmp_path/"agent"/"agents"/"unsafe-reader"/"agent.md"
    definition.write_text("---\nname: unsafe-reader\ndescription: Linked history fixture\ntools: \n---\nRead-only role.\n")
    cli=PACKAGE.parents[1]/"node_modules"/"@earendil-works"/"pi-coding-agent"/"dist"/"cli.js"
    fixture=PACKAGE.parents[1]/"tests"/"live-history-safety-fixture.ts"
    result=subprocess.run(["node",str(cli),"--print","--no-session","--session-id",env["PI_HISTORY_SAFETY_PARENT_ID"],"--no-extensions",
        "--no-skills","--no-prompt-templates","--no-themes","--no-context-files","--no-approve",
        "--no-builtin-tools","--extension",str(fixture),"--provider","history-safety-fixture",
        "--model","scripted","--thinking","off","Attempt the unsafe private resume"],
        cwd=tmp_path/"project",env=env,input="",text=True,capture_output=True,timeout=20)
    assert result.returncode==0, result.stdout+result.stderr
    assert "HISTORY_SAFETY_REFUSED" in result.stdout, result.stdout+result.stderr
    assert before==(hashlib.sha256(outside.read_bytes()).hexdigest(),outside.stat().st_mtime_ns)
    report=json.loads((tmp_path/"safety-evidence.json").read_text())
    assert report=={"spawns":0,"refused":True,"outsideInContext":False,"code":"workspace-failed"}, report


# --- Merged from test_live_parent_message.py ---
"""Native Pi verification for the child-only agent_message channel."""

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


def _sse(answer: str, *, tool: str | None = None, arguments: str | None = None) -> bytes:
    if tool is not None:
        delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": "child-message-call",
            "type": "function", "function": {"name": tool, "arguments": arguments or "{}"}}]}
        finish = "tool_calls"
    else:
        delta, finish = {"role": "assistant", "content": answer}, "stop"
    chunks = [
        {"id": "parent-message-fixture", "object": "chat.completion.chunk", "created": 1, "model": "fixture",
         "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {"id": "parent-message-fixture", "object": "chat.completion.chunk", "created": 1, "model": "fixture",
         "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
    ]
    return b"".join(("data: " + json.dumps(chunk) + "\n\n").encode() for chunk in chunks) + b"data: [DONE]\n\n"


def _child_response(payload: dict[str, object], granted: bool) -> bytes:
    raw_messages = payload.get("messages", [])
    typed_messages = raw_messages if isinstance(raw_messages, list) else []
    user_indexes = [index for index, item in enumerate(typed_messages)
                    if isinstance(item, dict) and item.get("role") == "user"]
    last_user = user_indexes[-1] if user_indexes else -1
    second = "SECOND INPUT" in json.dumps(typed_messages[last_user:], ensure_ascii=False)
    # A persistent resident session retains the first turn's tool result. Only
    # a result after the current input means that this input's agent_message
    # call has completed.
    tool_result_count = sum(isinstance(item, dict) and item.get("role") == "tool"
                             for item in typed_messages[last_user + 1:])
    if tool_result_count < 2:
        if not granted:
            if tool_result_count > 0:
                return _sse("CHILD_NO_GRANT_FINAL")
            return _sse("", tool="agent_message", arguments=json.dumps({"message": "FORBIDDEN_ATTEMPT"}))
        message = "INTERMEDIATE_B" if second else "INTERMEDIATE_A"
        return _sse("", tool="agent_message", arguments=json.dumps({"message": message}))
    if not granted:
        return _sse("CHILD_NO_GRANT_FINAL")
    return _sse("CHILD_FINAL_B" if second else "CHILD_FINAL_A")


@pytest.mark.parametrize("interface,case", [("print", "granted"), ("tui", "granted"), ("print", "no-grant")])
def test_native_parent_message_is_isolated_fifo_and_explicit(tmp_path: Path, interface: str, case: str) -> None:
    granted = case == "granted"
    requests: list[dict[str, object]] = []
    request_kinds: list[str] = []
    request_trace = tmp_path / "requests.json"
    final_a_gate = threading.Event()
    child_finished = threading.Event()

    class Control(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            if self.path != "/release-final-a":
                self.send_error(404)
                return
            final_a_gate.set()
            self.send_response(204)
            self.end_headers()

        def do_GET(self) -> None:
            if self.path != "/child-finished":
                self.send_error(404)
                return
            child_finished.wait(timeout=35)
            self.send_response(204 if child_finished.is_set() else 504)
            self.end_headers()

    control = LoopbackServer(Control)

    class LocalChildModel(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload)
            typed_messages = payload.get("messages", []) if isinstance(payload.get("messages", []), list) else []
            user_indexes = [index for index, item in enumerate(typed_messages)
                            if isinstance(item, dict) and item.get("role") == "user"]
            last_user = user_indexes[-1] if user_indexes else -1
            current = json.dumps(typed_messages[last_user:], ensure_ascii=False)
            tool_results = sum(isinstance(item, dict) and item.get("role") == "tool"
                               for item in typed_messages[last_user + 1:])
            prefix = "B" if "SECOND INPUT" in current else "A"
            threshold = 2 if granted else 1
            kind = f"tool-{prefix}" if tool_results < threshold else f"final-{prefix}"
            request_kinds.append(kind)
            request_trace.write_text(json.dumps(request_kinds))
            # Keep the first child model request active while the parent issues
            # its already-queued next input. The fixture releases this gate only
            # after Pi reports the real queued receipt.
            if granted and kind == "tool-A" and tool_results == 1 and not final_a_gate.wait(timeout=45):
                self.send_error(504)
                return
            body = _child_response(payload, granted)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            if kind == "final-B" or (not granted and kind == "final-A"):
                # Let the resident consume the complete local stream and emit
                # its Session Result before releasing the parent keepalive.
                time.sleep(0.5)
                child_finished.set()

    server = LoopbackServer(LocalChildModel)
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    credential = secrets.token_hex(16)
    (agent_dir / "settings.json").write_text(json.dumps({"quietStartup": True,
        "packages": [str(REPO / "packages" / "subagents")],
        "extensions": ["-builtin:mcp", "-builtin:llama.cpp", "-builtin:codemode", "-builtin:tool-search"],
        "retry": {"enabled": True, "maxRetries": 1, "baseDelayMs": 0}}))
    (agent_dir / "models.json").write_text(json.dumps({"providers": {
        "parent-message-child": {"baseUrl": f"http://127.0.0.1:{server.server_port}/v1",
            "api": "openai-completions", "apiKey": credential,
            "models": [{"id": "fixture", "reasoning": False, "input": ["text"],
                "contextWindow": 200000, "maxTokens": 4096,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}
    }}))
    evidence = tmp_path / "parent-message-evidence.json"
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(agent_dir),
           "PI_OFFLINE": "1", "PI_PARENT_MESSAGE_AUTH": credential,
           "PI_PARENT_MESSAGE_EVIDENCE": str(evidence), "PI_PARENT_MESSAGE_CONFIGURED": "1",
           "PI_PARENT_MESSAGE_CASE": case, "PI_PARENT_MESSAGE_REQUEST_TRACE": str(request_trace)}
    env["PI_PARENT_MESSAGE_CONTROL_URL"] = f"http://127.0.0.1:{control.server_port}"
    cli = REPO / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
    command = ["node", str(cli), "--no-session", "--no-skills", "--no-prompt-templates", "--no-themes",
               "--no-context-files", "--no-approve", "--no-builtin-tools", "--extension",
               str(Path(__file__).with_name("native-parent-message-fixture.ts")),
               "--provider", "parent-message-parent", "--model", "scripted", "--thinking", "off",
               "Run the isolated parent message fixture"]
    try:
        if interface == "print":
            result = subprocess.run([*command, "--print"], cwd=tmp_path, env=env, input="", capture_output=True,
                                    text=True, timeout=60)
            assert result.returncode == 0, result.stderr + result.stdout
            if granted:
                assert "NATIVE_PARENT_MESSAGE_OK" in result.stdout + result.stderr
        else:
            with NativeTui(command, cwd=tmp_path, env=env, rows=28, columns=70, timeout=60) as tui:
                tui.wait_for(lambda: "NATIVE_PARENT_MESSAGE_OK" in tui.screen())
                collapsed = tui.screen()
                assert "[agent] queued · @native-parent-message" in collapsed, collapsed[-5000:]
                assert "native-parent-message · Idle" not in collapsed, collapsed[-5000:]
                assert "session:subagent-" not in collapsed, collapsed[-5000:]
                tui.send(b"\x0f")
                tui.resize(45)
                tui.send(b"/quit\r")
                tui.wait_for(lambda: tui.process.poll() is not None)
                assert tui.process.returncode == 0, tui.screen()[-5000:]
                for marker in ("INTERMEDIATE_A", "INTERMEDIATE_B", "CHILD_FINAL_A", "CHILD_FINAL_B"):
                    assert marker in tui.screen(), tui.screen()[-5000:]
        assert evidence.is_file()
        report = json.loads(evidence.read_text())
        assert not report.get("failures"), report
        intermediate = [item for item in report["notices"] if item.get("kind") == "intermediate"]
        finals = [item for item in report["notices"] if item.get("kind") == "result"]
        if granted:
            assert [item["text"] for item in intermediate] == ["INTERMEDIATE_A", "INTERMEDIATE_B"], json.dumps(report, ensure_ascii=False)
            assert [item["text"] for item in finals] == ["CHILD_FINAL_A", "CHILD_FINAL_B"], report
            assert len({item["text"] for item in intermediate}) == 2
            assert all(item["session"] == report["receipts"][0]["session"] for item in intermediate + finals)
            assert len(report["receipts"]) == 2 and all(not item["isError"] for item in report["receipts"])
            assert report["receipts"][0]["tool"] == "agent_start"
            assert report["receipts"][1]["tool"] == "agent_input"
            assert report["receipts"][1]["disposition"] == "queued"
            assert report["receipts"][1]["state"] in {"starting", "working"}
            assert report["receipts"][1]["rosterSequenceEnded"] is False
            assert report["receipts"][0].get("inputId") == intermediate[0].get("inputId") == finals[0].get("inputId")
            assert report["receipts"][1].get("inputId") == intermediate[1].get("inputId") == finals[1].get("inputId")
            assert intermediate[0]["inputId"] != intermediate[1]["inputId"]
            assert [item["sequence"] for item in intermediate] == [1, 2]
            assert intermediate[0]["customType"] == intermediate[1]["customType"] == "subagents-parent-message"
            assert all(item["customType"] != intermediate[0]["customType"] for item in finals)
            assert intermediate[0]["order"] < finals[0]["order"] < intermediate[1]["order"] < finals[1]["order"]
            assert json.loads((tmp_path / "requests.json").read_text()) == [
                "tool-A", "tool-A", "final-A", "tool-B", "tool-B", "final-B"]
        else:
            assert not intermediate, report
            assert finals and finals[0]["text"] == "CHILD_NO_GRANT_FINAL", report
            assert report["receipts"] and "agent_message" not in json.dumps(report["receipts"][0].get("grant", []))
            assert any("FORBIDDEN_ATTEMPT" in json.dumps(request) for request in requests)
            assert json.loads((tmp_path / "requests.json").read_text()) == ["tool-A", "final-A"]
    finally:
        server.close()
        control.close()


# --- Merged from test_live_parent_session_history.py ---
"""Native Pi E2E for parent-session-partitioned durable child history."""

import json
import os
import secrets
import signal
import subprocess
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

import pytest

from native_support import LoopbackServer

REPO = Path(__file__).resolve().parents[3]
_m3_PI = REPO / "node_modules" / ".bin" / "pi"
_m3_FIXTURE = Path(__file__).with_name("native-parent-session-history-fixture.ts")
IDENTITY = "native-parent-history"
CHILD_PROVIDER = "native-parent-history-child"
CHILD_MODEL = f"{CHILD_PROVIDER}/scripted"
HISTORY_A = "PARENT_HISTORY_MARKER_A"
HISTORY_B = "PARENT_HISTORY_MARKER_B"


def sse(text: str, *, tool: str | None = None, arguments: dict[str, Any] | None = None, call_id: str = "child-call") -> bytes:
    if tool:
        delta: dict[str, Any] = {"role": "assistant", "tool_calls": [{"index": 0, "id": call_id,
            "type": "function", "function": {"name": tool, "arguments": json.dumps(arguments or {})}}]}
        finish = "tool_calls"
    else:
        delta, finish = {"role": "assistant", "content": text}, "stop"
    base = {"id": "parent-history-child", "object": "chat.completion.chunk", "created": 1, "model": "scripted"}
    chunks = [{"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
              {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}]
    return b"".join(("data: " + json.dumps({**base, **chunk}) + "\n\n").encode() for chunk in chunks) + b"data: [DONE]\n\n"


class ChildModel:
    def __init__(self, scratch: Path, credential: str) -> None:
        self.scratch = scratch
        self.errors: list[str] = []
        self.seen_initial: set[str] = set()
        self.initial_release = threading.Event()
        self.seen_both = threading.Event()
        self._lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: object) -> None:
                pass

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/v1/chat/completions" or self.headers.get("Authorization") != f"Bearer {credential}":
                    self.send_error(403, "Unexpected provider request")
                    return
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                messages = payload.get("messages", []) if isinstance(payload.get("messages", []), list) else []
                serialized = json.dumps(messages, ensure_ascii=False)
                users = [item for item in messages if isinstance(item, dict) and item.get("role") == "user"]
                latest = json.dumps(users[-1], ensure_ascii=False) if users else ""
                is_temp = "TEMPORARY_CHILD_MARKER" in latest
                resume = "REOPEN_PARENT_" in latest
                # Select from fixed fixture markers instead of parsing JSON
                # escaping or trailing prompt text from the serialized user
                # message.
                marker = HISTORY_A if HISTORY_A in latest or "REOPEN_PARENT_A" in latest else HISTORY_B
                last_user = max((index for index, item in enumerate(messages)
                                 if isinstance(item, dict) and item.get("role") == "user"), default=-1)
                tool_count = sum(isinstance(item, dict) and item.get("role") == "tool" for item in messages[last_user + 1:])
                if is_temp:
                    body = sse("TEMPORARY_CHILD_OK")
                elif resume:
                    other = HISTORY_B if marker == HISTORY_A else HISTORY_A
                    old_context = json.dumps(messages[:last_user], ensure_ascii=False)
                    if marker not in old_context or other in old_context:
                        owner.errors.append(f"history cross-read for {marker}: {serialized}")
                    reads = [scratch.parent / "memory" / "shared-a.md", scratch.parent / "memory" / "shared-b.md",
                             scratch / "scratch-A.txt", scratch / "scratch-B.txt"]
                    if tool_count < len(reads):
                        body = sse("", tool="read", call_id=f"resume-{marker}-{tool_count}", arguments={"path": str(reads[tool_count])})
                    else:
                        current_tools = json.dumps(messages[last_user + 1:], ensure_ascii=False)
                        for shared_marker in ["SHARED_MEMORY_A", "SHARED_MEMORY_B", "SHARED_SCRATCH_A", "SHARED_SCRATCH_B"]:
                            if shared_marker not in current_tools:
                                owner.errors.append(f"missing current read for {shared_marker}")
                        body = sse(f"RESUMED_{marker}")
                elif tool_count == 0:
                    with owner._lock:
                        owner.seen_initial.add(marker)
                        if owner.seen_initial == {HISTORY_A, HISTORY_B}:
                            owner.seen_both.set()
                    if not owner.initial_release.wait(timeout=45):
                        owner.errors.append("Initial child overlap gate timed out")
                    body = sse("", tool="agent_memory", call_id=f"memory-{marker}", arguments={
                        "action": "append", "name": f"shared-{marker[-1].lower()}",
                        "description": "Shared parent history fixture", "body": f"SHARED_MEMORY_{marker[-1]}",
                    })
                elif tool_count == 1:
                    body = sse("", tool="write", call_id=f"scratch-{marker}", arguments={
                        "path": str(owner.scratch / f"scratch-{marker[-1]}.txt"), "content": f"SHARED_SCRATCH_{marker[-1]}",
                    })
                else:
                    body = sse(f"INITIAL_{marker}")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                try:
                    self.wfile.write(body)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = LoopbackServer(Handler)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        self.server.close()


def run_parent(tmp_path: Path, server: ChildModel, parent_file: Path, marker: str, phase: str, evidence: Path, auth: str) -> subprocess.Popen[str]:
    agent_dir = tmp_path / "agent"
    env = {
        "PATH": os.environ.get("PATH", os.defpath), "HOME": str(tmp_path), "TMPDIR": str(tmp_path / "tmp"),
        "PI_CODING_AGENT_DIR": str(agent_dir), "PI_OFFLINE": "1",
        "PI_PARENT_HISTORY_ROOT": str(tmp_path), "PI_PARENT_HISTORY_PROJECT": str(tmp_path / "project"),
        "PI_PARENT_HISTORY_EVIDENCE": str(evidence), "PI_PARENT_HISTORY_PHASE": phase,
        "PI_PARENT_HISTORY_MARKER": marker, "PI_PARENT_HISTORY_IDENTITY": IDENTITY,
        "PI_PARENT_HISTORY_CHILD_MODEL": CHILD_MODEL, "PI_PARENT_HISTORY_AUTH": auth,
        "PI_PARENT_HISTORY_CHILD_URL": server.url,
    }
    command = [str(_m3_PI), "--session", str(parent_file), "--session-dir", str(parent_file.parent),
               "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files",
               "--no-approve", "--no-builtin-tools", "--extension", str(_m3_FIXTURE),
               "--provider", "native-parent-history", "--model", "scripted", "--thinking", "off", "--print",
               "Run parent history fixture"]
    return subprocess.Popen(command, cwd=tmp_path / "project", env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)


@pytest.mark.skipif(not _m3_PI.is_file(), reason="Repository Pi CLI is unavailable")
def test_native_parent_session_history_isolated_and_resumable(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (tmp_path / "tmp").mkdir()
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    identity = agent_dir / "agents" / IDENTITY
    identity.mkdir(parents=True)
    (identity / "agent.md").write_text(
        f"---\nname: {IDENTITY}\ndescription: Parent history isolation\ntools: read, write, agent_memory\nmodel: {CHILD_MODEL}\n---\nUse only granted tools.\n",
        encoding="utf-8",
    )
    credential = secrets.token_hex(24)
    (agent_dir / "models.json").write_text(json.dumps({"providers": {
        CHILD_PROVIDER: {"api": "openai-completions", "apiKey": credential,
                         "baseUrl": "PLACEHOLDER", "models": [{"id": "scripted", "name": "child", "reasoning": False,
                         "input": ["text"], "contextWindow": 200000, "maxTokens": 4096,
                         "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}
    }}), encoding="utf-8")
    (agent_dir / "auth.json").write_text("{}\n", encoding="utf-8")
    server = ChildModel(identity / "workspace", credential)
    processes: list[subprocess.Popen[str]] = []
    try:
        models = json.loads((agent_dir / "models.json").read_text(encoding="utf-8"))
        models["providers"][CHILD_PROVIDER]["baseUrl"] = server.url + "/v1"
        (agent_dir / "models.json").write_text(json.dumps(models), encoding="utf-8")
        for private_file in (agent_dir / "models.json", agent_dir / "auth.json"):
            private_file.chmod(0o600)
        parent_root = tmp_path / "parent-sessions"
        parent_root.mkdir()
        parent_a = parent_root / "parent-a.jsonl"
        parent_b = parent_root / "parent-b.jsonl"
        evidence_a = tmp_path / "initial-a.json"
        evidence_b = tmp_path / "initial-b.json"
        process_a = run_parent(tmp_path, server, parent_a, HISTORY_A, "initial", evidence_a, credential)
        processes.append(process_a)
        process_b = run_parent(tmp_path, server, parent_b, HISTORY_B, "initial", evidence_b, credential)
        processes.append(process_b)
        assert server.seen_both.wait(timeout=45), "both parent children did not overlap at the live provider barrier"
        assert process_a.poll() is None and process_b.poll() is None
        server.initial_release.set()
        out_a, err_a = process_a.communicate(timeout=90)
        out_b, err_b = process_b.communicate(timeout=90)
        assert process_a.returncode == 0, err_a + out_a
        assert process_b.returncode == 0, err_b + out_b
        first_a, first_b = json.loads(evidence_a.read_text()), json.loads(evidence_b.read_text())
        assert first_a["parentId"] != first_b["parentId"]
        assert first_a["failures"] == first_b["failures"] == []
        # agent_stop intentionally terminates the RPC child; Pi reports the
        # expected SIGTERM exit as 143. The contract is an observed close with
        # no surviving signal/hang, matching the existing native durable test.
        assert all(item.get("code") in (0, 143) and item.get("signal") is None
                   for item in first_a["closes"] + first_b["closes"])
        durable_a = [item for item in first_a["launches"] if not item["noSession"]]
        durable_b = [item for item in first_b["launches"] if not item["noSession"]]
        assert durable_a and durable_b
        assert durable_a[0]["sessionDir"] != durable_b[0]["sessionDir"]
        temporary_a = [item for item in first_a["launches"] if item["noSession"]]
        temporary_b = [item for item in first_b["launches"] if item["noSession"]]
        assert temporary_a and temporary_b
        assert all(item.get("sessionDir") is None for item in temporary_a)
        assert all(item.get("sessionDir") is None for item in temporary_b)
        assert (identity / "memory" / "shared-a.md").is_file()
        assert (identity / "memory" / "shared-b.md").is_file()
        assert (identity / "workspace" / "scratch-A.txt").read_text(encoding="utf-8") == "SHARED_SCRATCH_A"
        assert (identity / "workspace" / "scratch-B.txt").read_text(encoding="utf-8") == "SHARED_SCRATCH_B"
        evidence_ra = tmp_path / "resume-a.json"
        evidence_rb = tmp_path / "resume-b.json"
        resume_a = run_parent(tmp_path, server, parent_a, HISTORY_A, "resume", evidence_ra, credential)
        processes.append(resume_a)
        out_ra, err_ra = resume_a.communicate(timeout=90)
        resume_b = run_parent(tmp_path, server, parent_b, HISTORY_B, "resume", evidence_rb, credential)
        processes.append(resume_b)
        out_rb, err_rb = resume_b.communicate(timeout=90)
        assert resume_a.returncode == 0, err_ra + out_ra
        assert resume_b.returncode == 0, err_rb + out_rb
        second_a, second_b = json.loads(evidence_ra.read_text()), json.loads(evidence_rb.read_text())
        assert second_a["parentId"] == first_a["parentId"]
        assert second_b["parentId"] == first_b["parentId"]
        assert second_a["parentId"] != second_b["parentId"]
        assert second_a["failures"] == second_b["failures"] == []
        assert [item["sessionDir"] for item in second_a["launches"] if not item["noSession"]] == [durable_a[0]["sessionDir"]]
        assert [item["sessionDir"] for item in second_b["launches"] if not item["noSession"]] == [durable_b[0]["sessionDir"]]
        for evidence, count in [(first_a, 2), (first_b, 2), (second_a, 1), (second_b, 1)]:
            assert len(evidence["launches"]) == len(evidence["closes"]) == count, evidence
            assert {item["pid"] for item in evidence["launches"]} == {item["pid"] for item in evidence["closes"]}
            assert all(item["cwd"] == str(project) for item in evidence["launches"])
            assert all(receipt.get("isError") is not True for receipt in evidence["receipts"])
            assert [receipt["tool"] for receipt in evidence["receipts"]] == ["agent_start", "agent_stop"] * count
            finals = [notice for notice in evidence["notices"] if notice.get("customType") == "subagents-session-result"]
            assert len(finals) == count and all(notice.get("kind") == "result" for notice in finals)
            for index, final in enumerate(finals):
                assert evidence["receipts"][index * 2]["session"] == final["session"] == evidence["receipts"][index * 2 + 1]["session"]
            tool_ends = [frame for frame in evidence["frames"] if frame.get("type") == "tool_execution_end"]
            assert [frame["toolName"] for frame in tool_ends] == (["agent_memory", "write"] if count == 2 else ["read"] * 4)
            assert all(frame.get("isError") is not True for frame in tool_ends)
        a_close = next(item for item in first_a["closes"] if item["pid"] == durable_a[0]["pid"])
        b_close = next(item for item in first_b["closes"] if item["pid"] == durable_b[0]["pid"])
        assert durable_a[0]["spawnedAt"] < b_close["closedAt"] and durable_b[0]["spawnedAt"] < a_close["closedAt"]
        assert "--continue" in second_a["launches"][0]["args"] and "--continue" in second_b["launches"][0]["args"]
        assert server.errors == [], server.errors
    finally:
        server.initial_release.set()
        for process in processes:
            if process.poll() is not None:
                continue
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=5)
        server.close()
