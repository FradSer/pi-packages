"""Native loopback proof for one durable identity across two projects."""
from __future__ import annotations

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
