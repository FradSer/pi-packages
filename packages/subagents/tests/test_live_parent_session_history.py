"""Native Pi E2E for parent-session-partitioned durable child history."""
from __future__ import annotations

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
PI = REPO / "node_modules" / ".bin" / "pi"
FIXTURE = Path(__file__).with_name("native-parent-session-history-fixture.ts")
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
    command = [str(PI), "--session", str(parent_file), "--session-dir", str(parent_file.parent),
               "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files",
               "--no-approve", "--no-builtin-tools", "--extension", str(FIXTURE),
               "--provider", "native-parent-history", "--model", "scripted", "--thinking", "off", "--print",
               "Run parent history fixture"]
    return subprocess.Popen(command, cwd=tmp_path / "project", env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)


@pytest.mark.skipif(not PI.is_file(), reason="Repository Pi CLI is unavailable")
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
