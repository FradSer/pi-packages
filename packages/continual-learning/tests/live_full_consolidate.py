"""Native TUI acceptance for the user-invoked ``/consolidate full`` flow.

This is an explicit, disposable live check. The planner provider is local and
deterministic; Pi and its real planner child are still the native processes.
"""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import pty
import re
import select
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PACKAGE = Path(__file__).resolve().parents[1]
PROVIDER = "continual-learning-full-loopback"
MODEL = "scripted"
API_KEY = "full-loopback-only"


def text_of(payload: dict[str, object]) -> str:
    values: list[str] = []
    for message in payload.get("messages", []):
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            values.append(content)
        elif isinstance(content, list):
            values.extend(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return "\n".join(values)


def readback_marker_ids(
    messages: list[dict[str, object]],
    body_markers: dict[str, str],
    tool_call_paths: dict[str, str],
    expected_memory_root: str,
) -> set[str]:
    """Return only read calls whose matching tool result contains its body marker."""
    expected: dict[str, str] = {}
    expected_paths = {
        name: os.path.realpath(os.path.join(expected_memory_root, name))
        for name in body_markers
    }
    for name, marker in body_markers.items():
        matching_ids = [
            call_id for call_id, path in tool_call_paths.items()
            if os.path.realpath(path) == expected_paths[name]
        ]
        if len(matching_ids) != 1:
            return set()
        tool_call_id = matching_ids[0]
        expected[tool_call_id] = marker
    matched: set[str] = set()
    for message in messages:
        if message.get("role") != "tool":
            continue
        tool_call_id = message.get("tool_call_id")
        if not isinstance(tool_call_id, str) or tool_call_id not in expected:
            continue
        content = message.get("content")
        content_text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        if expected[tool_call_id] in content_text:
            matched.add(tool_call_id)
    return matched


def read_tool_call_paths(messages: list[dict[str, object]]) -> dict[str, str]:
    """Bind read result ids to the preceding assistant function arguments."""
    paths: dict[str, str] = {}
    for message in messages:
        if message.get("role") != "assistant" or not isinstance(message.get("tool_calls"), list):
            continue
        for call in message["tool_calls"]:
            if not isinstance(call, dict) or call.get("type") != "function":
                continue
            function = call.get("function")
            if not isinstance(function, dict) or function.get("name") != "read":
                continue
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    continue
            if not isinstance(arguments, dict) or not isinstance(arguments.get("path"), str):
                continue
            if isinstance(call.get("id"), str):
                paths[call["id"]] = arguments["path"]
    return paths


def field(text: str, name: str) -> str:
    patterns = (
        rf"(?:^|\n)\s*-\s*`?{re.escape(name)}`?\s*:\s*`?([^`\n]+?)`?\s*$",
        rf'"{re.escape(name)}"\s*:\s*"([^"\\]+)"',
        rf"\b{re.escape(name)}\s*:\s*([A-Za-z0-9._:/-]+)",
    )
    for pattern in patterns:
        matches = re.findall(pattern, text, re.MULTILINE)
        if matches:
            return matches[-1].strip()
    raise AssertionError(f"planner prompt omitted {name}")


def stream(handler: BaseHTTPRequestHandler, content: str, tools: list[dict[str, object]] | None = None) -> None:
    base = {"id": "full-loopback", "object": "chat.completion.chunk", "created": 1, "model": MODEL}
    if tools:
        delta: dict[str, object] = {"role": "assistant", "tool_calls": [
            {"index": index, "id": call["id"], "type": "function",
             "function": {"name": "read", "arguments": json.dumps(call["arguments"], separators=(",", ":"))}}
            for index, call in enumerate(tools)
        ]}
        events = [
            {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
        ]
    else:
        events = [
            {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}]},
            {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.end_headers()
    for event in events:
        handler.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
    handler.wfile.write(b"data: [DONE]\n\n")
    handler.wfile.flush()


class Provider(BaseHTTPRequestHandler):
    requests: list[str] = []
    kinds: list[str] = []
    memory_root: Path | None = None
    body_markers: dict[str, str] = {}
    planner_identities: list[dict[str, str]] = []
    harness_identities: list[dict[str, str]] = []

    def log_message(self, _format: str, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions" or self.headers.get("Authorization") != f"Bearer {API_KEY}":
            self.send_error(403, "full loopback authorization or path mismatch")
            return
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        text = text_of(payload)
        type(self).requests.append(text)
        if "incremental-memory-selection" in text:
            type(self).kinds.append("selector")
        elif "incremental-memory-plan" in text:
            type(self).kinds.append("incremental")
        elif "harness-consolidation-plan" in text:
            type(self).kinds.append("harness")
            identity = {name: field(text, name) for name in ("runId", "scopeDigest", "artifactHash")}
            type(self).harness_identities.append(identity)
            plan = {
                "kind": "harness-consolidation-plan", "version": 1, "schemaVersion": 1,
                "runId": field(text, "runId"), "scopeDigest": field(text, "scopeDigest"),
                "artifactHash": field(text, "artifactHash"), "operations": [], "evidence": [], "report": [],
            }
            stream(self, json.dumps(plan, separators=(",", ":")))
            return
        elif "memory-consolidation-plan" in text:
            tool_messages = [message for message in payload.get("messages", []) if isinstance(message, dict)]
            if type(self).memory_root is None:
                raise AssertionError("full provider memory root was not configured")
            body_read_ids = readback_marker_ids(
                tool_messages,
                type(self).body_markers,
                read_tool_call_paths(payload.get("messages", [])),
                str(type(self).memory_root),
            )
            has_tool_result = body_read_ids == {"read-1", "read-2"}
            type(self).kinds.append("full-memory-readback" if has_tool_result else "full-memory")
            if not has_tool_result:
                if type(self).memory_root is None:
                    raise AssertionError("full provider memory root was not configured")
                memory_root = type(self).memory_root
                stream(self, "", [{"id": f"read-{index}", "arguments": {"path": str(memory_root / name), "offset": 1, "limit": 200}} for index, name in enumerate(["MEMORY.md", "full_fact.md", "full_second.md"])])
                return
            if body_read_ids != {"read-1", "read-2"}:
                raise AssertionError("full provider readback omitted the unique Memory body markers")
            names = ["full_fact.md", "full_second.md"]
            identity = {name: field(text, name) for name in ("runId", "scopeKey", "scopeDigest", "artifactHash", "snapshotDigest")}
            type(self).planner_identities.append(identity)
            plan = {
                "kind": "memory-consolidation-plan", "version": 1, "schemaVersion": 1, **identity,
                "selected": names,
                "operations": [], "newMemories": [],
                "inventory": [{"name": name, "classification": "safe"} for name in names],
                "clusters": [{"name": "project", "files": names}],
                "staleness": [{"name": name, "verdict": "KEEP"} for name in names],
                "grounding": [{"name": name, "status": "VERIFIED", "reason": "repository marker exists", "observations": [{"path": f"src/{name[:-3]}.txt", "status": "found"}]} for name in names],
                "report": [{"name": name, "status": "KEEP", "summary": "durable full-corpus entry"} for name in names],
            }
            stream(self, json.dumps(plan, separators=(",", ":")))
            return
        elif "FULL_SESSION_MARKER" in text:
            type(self).kinds.append("task")
        stream(self, "LOOPBACK_FULL_TASK_DONE")


def wait_for(predicate, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("timed out waiting for native full consolidation")


def run() -> dict[str, object]:
    Provider.requests = []
    Provider.kinds = []
    Provider.memory_root = None
    Provider.planner_identities = []
    Provider.harness_identities = []
    Provider.body_markers = {
        "full_fact.md": "BODY_ONLY_MARKER_ALPHA_9f4c",
        "full_second.md": "BODY_ONLY_MARKER_BETA_3a71",
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="continual-learning-full-native-") as raw:
            root = Path(raw).resolve()
            project = (root / "project").resolve()
            agent = (root / "agent").resolve()
            project.mkdir()
            agent.mkdir(mode=0o700)
            (project / ".pi").mkdir()
            (project / "src").mkdir()
            (project / "src" / "full_fact.txt").write_text("full_fact.md is a settled full corpus fact.\n")
            (project / "src" / "full_second.txt").write_text("full_second.md is a settled full corpus fact.\n")
            (project / "AGENTS.md").write_text("# Project instructions\n\nKeep verification stable.\n")
            (agent / "memory").mkdir()
            scope = "--" + str(project).lstrip("/").replace("/", "-") + "--"
            private = agent / "memory" / scope
            private.mkdir()
            Provider.memory_root = private.resolve()
            names = ["full_fact.md", "full_second.md"]
            descriptions = {
                "full_fact.md": "full_fact.md is a settled full corpus fact.",
                "full_second.md": "full_second.md is a settled full corpus fact.",
            }
            bodies = {
                "full_fact.md": "BODY_ONLY_MARKER_ALPHA_9f4c durable body fact.",
                "full_second.md": "BODY_ONLY_MARKER_BETA_3a71 durable body fact.",
            }
            (private / "MEMORY.md").write_text("# Memory\n\n" + "".join(f"- [{name}]({name}) — {descriptions[name]}\n" for name in names))
            for name in names:
                (private / name).write_text(
                    f"---\ndescription: {descriptions[name]}\ntype: project\n---\n\n{bodies[name]}\n"
                )
            (agent / "settings.json").write_text(json.dumps({"quietStartup": True, "packages": []}))
            (agent / "memory.json").write_text(json.dumps({"provider": PROVIDER, "model": MODEL}))
            (agent / "models.json").write_text(json.dumps({"providers": {
                PROVIDER: {"baseUrl": f"http://127.0.0.1:{server.server_port}/v1", "api": "openai-completions", "apiKey": API_KEY,
                    "models": [{"id": MODEL, "reasoning": False, "input": ["text"], "contextWindow": 200000, "maxTokens": 4096,
                                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]},
            }}))
            (agent / "memory" / "settings.json").write_text(json.dumps({
                "autoMemory": False, "automaticPhases": {"memory": "apply", "harness": "off", "agents": "off"},
                "agentsMd": {"disabled": True},
            }))
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            fixture = root / "full-fixture.ts"
            log = root / "notifications.jsonl"
            fixture.write_text(
                "import { appendFileSync } from 'node:fs';\n"
                "export default function(pi) { pi.on('session_start', (_event, ctx) => {"
                f" const log = {json.dumps(str(log))}; appendFileSync(log, 'READY\\n');"
                " const notify = ctx.ui.notify.bind(ctx.ui); ctx.ui.notify = (message, type) => {"
                " appendFileSync(log, JSON.stringify({message, type}) + '\\n'); notify(message, type); }; }); }\n"
            )
            env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL"}}
            env.update({"HOME": str(root), "PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1", "TERM": "xterm-256color"})
            pi = shutil.which("pi") or "pi"
            session = root / "session.jsonl"
            command = [pi, "--offline", "--no-extensions", "-e", str(fixture), "-e", str(PACKAGE / "index.ts"),
                       "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-approve",
                       "--session", str(session), "--model", f"{PROVIDER}/{MODEL}", "--tools", "read", "--thinking", "off"]
            master, slave = pty.openpty()
            process = subprocess.Popen(command, cwd=project, env=env, stdin=slave, stdout=slave, stderr=slave)
            os.close(slave)
            transcript = bytearray()

            def drain() -> None:
                if not select.select([master], [], [], 0)[0]:
                    return
                try:
                    transcript.extend(os.read(master, 65536))
                except OSError:
                    return

            try:
                def ready() -> bool:
                    drain()
                    return log.exists() and "READY" in log.read_text()

                try:
                    wait_for(ready)
                except AssertionError as error:
                    raise AssertionError(
                        f"{error}; process={process.poll()}; terminal={transcript.decode(errors='replace')[-5000:]}"
                    ) from error
                session_marker = "FULL_SESSION_MARKER full_fact.md is a settled full corpus fact; full_second.md is a settled full corpus fact."
                os.write(master, f"{session_marker}\r".encode())
                wait_for(lambda: "task" in Provider.kinds)
                wait_for(lambda: (drain() or True) and b"LOOPBACK_FULL_TASK_DONE" in transcript)
                os.write(master, b"/consolidate full\r")
                phase_observations: list[dict[str, object]] = []
                phase_deadline = time.monotonic() + 60
                last_observation = ""
                while time.monotonic() < phase_deadline:
                    drain()
                    run_files = sorted(path.name for path in (agent / "memory" / "runs").rglob("*") if path.is_file())
                    observation = json.dumps({"kinds": Provider.kinds, "files": run_files, "process": process.poll()}, sort_keys=True)
                    if observation != last_observation:
                        phase_observations.append(json.loads(observation))
                        last_observation = observation
                    if "harness" in Provider.kinds:
                        break
                    time.sleep(0.05)
                try:
                    assert "full-memory" in Provider.kinds and "full-memory-readback" in Provider.kinds and "harness" in Provider.kinds
                except AssertionError as error:
                    plans = [path.read_text()[-3000:] for path in (agent / "memory" / "runs").rglob("plan.json")]
                    validation = []
                    for plan_path in (agent / "memory" / "runs").rglob("plan.json"):
                        try:
                            result = subprocess.run(
                                ["python3", str(PACKAGE / "scripts" / "validate-consolidate.py"),
                                 "--plan", str(plan_path), "--snapshot", str(plan_path.parent / "snapshot.json"),
                                 "--repo-root", str(project), "--check", "plan", "--mode", "full"],
                                capture_output=True, text=True, timeout=10,
                            )
                            validation.append({"path": str(plan_path.relative_to(root)), "code": result.returncode,
                                               "stdout": result.stdout[-3000:], "stderr": result.stderr[-1000:]})
                        except Exception as validation_error:
                            validation.append({"path": str(plan_path.relative_to(root)), "error": repr(validation_error)})
                    files = []
                    for path in root.rglob("*"):
                        if path.is_file() and (path.name in {
                            "manifest.json", "plan.json", "stdout.jsonl", "stderr.txt",
                            "activity-summary.json", "learning-pipeline-receipt.json",
                            "harness-error.txt", "harness-noop.txt", "harness-post-receipt.json",
                            "harness-pre-receipt.json", "notifications.jsonl",
                        } or path.suffix == ".lock"):
                            try:
                                body = path.read_text(errors="replace")
                            except OSError:
                                body = "<unreadable>"
                            files.append({"path": str(path.relative_to(root)), "tail": body[-3000:]})
                    raise AssertionError(
                        f"{error}; kinds={Provider.kinds}; observations={phase_observations}; plans={plans}; validation={validation}; files={files}; requests={Provider.requests[-3:]}; terminal={transcript.decode(errors='replace')[-12000:]}"
                    ) from error
                run_receipt = None
                run_receipt_file = None

                def receipt_ready() -> bool:
                    nonlocal run_receipt, run_receipt_file
                    drain()
                    files = list((agent / "memory" / "runs").rglob("learning-pipeline-receipt.json"))
                    if not files:
                        return False
                    run_receipt_file = files[-1]
                    run_receipt = json.loads(files[-1].read_text())
                    return run_receipt.get("kind") == "learning-pipeline-receipt" and run_receipt.get("mode") == "full"

                try:
                    wait_for(receipt_ready)
                except AssertionError as error:
                    summary = []
                    for path in root.rglob("*"):
                        if path.is_file() and path.name in {"manifest.json", "plan.json", "stdout.jsonl", "stderr.txt", "activity-summary.json", "harness-task.md", "harness-error.txt", "harness-noop.txt", "harness-post-receipt.json", "harness-pre-receipt.json", "learning-pipeline-receipt.json"}:
                            summary.append({"path": str(path.relative_to(root)), "tail": path.read_text(errors="replace")[-4000:]})
                    raise AssertionError(f"{error}; kinds={Provider.kinds}; receiptFiles={summary}; notifications={log.read_text() if log.exists() else ''}") from error
                result_record = None
                def result_ready() -> bool:
                    nonlocal result_record
                    drain()
                    if not session.exists():
                        return False
                    records = []
                    for line in session.read_text().splitlines():
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(row, dict):
                            continue
                        message = row.get("message") if isinstance(row.get("message"), dict) else row
                        if row.get("type") == "custom_message" and message.get("customType") == "continual-learning-result":
                            records.append(message)
                    if len(records) != 1:
                        return False
                    result_record = records[0]
                    return isinstance(result_record.get("details"), dict) and result_record["details"] == run_receipt

                try:
                    wait_for(result_ready, timeout=30)
                except AssertionError as error:
                    raise AssertionError(
                        f"{error}; receipt={run_receipt}; sessionTail={session.read_text(errors='replace')[-12000:] if session.exists() else '<missing>'}; terminal={transcript.decode(errors='replace')[-12000:]}"
                    ) from error
                os.write(master, b"/quit\r")
                def exited() -> bool:
                    drain()
                    return process.poll() is not None

                wait_for(exited, timeout=30)
                assert process.returncode == 0, transcript.decode(errors="replace")[-6000:]
                assert run_receipt is not None
                assert result_record is not None and result_record.get("details") == run_receipt
                assert run_receipt.get("version") == 1, run_receipt
                assert all(attempt.get("outcome") not in {"failed", "cancelled"} for attempt in run_receipt["attempts"]), run_receipt
                phase_attempts = {phase: [attempt for attempt in run_receipt["attempts"] if attempt.get("phase") == phase] for phase in ("memory", "harness")}
                assert all(len(attempts) == 1 and attempts[0].get("outcome") in {"applied", "noop"} for attempts in phase_attempts.values()), run_receipt
                assert not any(attempt.get("phase") == "agents" for attempt in run_receipt["attempts"]), run_receipt
                assert Provider.kinds.count("selector") == 0, Provider.kinds
                assert Provider.kinds.count("full-memory") == 1 and Provider.kinds.count("full-memory-readback") == 1 and Provider.kinds.count("harness") == 1, Provider.kinds
                planner = next(text for text in Provider.requests if "memory-consolidation-plan" in text)
                assert "snapshotPath" in planner and "scopeKey" in planner, planner
                assert all(marker in "\n".join(Provider.requests) for marker in Provider.body_markers.values()), Provider.requests
                assert run_receipt_file is not None
                snapshot_file = run_receipt_file.parent / "snapshot.json"
                assert snapshot_file.is_file(), str(run_receipt_file)
                snapshot = snapshot_file.read_text()
                assert "FULL_SESSION_MARKER" in snapshot and all(name in snapshot for name in names), snapshot
                manifest_file = run_receipt_file.parent / "manifest.json"
                manifest = json.loads(manifest_file.read_text())
                snapshot_digest = hashlib.sha256(snapshot_file.read_bytes()).hexdigest()
                assert manifest.get("snapshotDigest") == snapshot_digest, manifest
                index_text = (private / "MEMORY.md").read_text()
                for name, marker in Provider.body_markers.items():
                    entry_text = (private / name).read_text()
                    frontmatter, body = entry_text.split("---", 2)[1:]
                    assert marker not in frontmatter and marker not in index_text and marker in body, entry_text
                    entry_digest = hashlib.sha256(entry_text.encode()).hexdigest()
                    assert manifest["sourceHashes"]["harness"][name] == entry_digest
                    assert manifest["sourceHashes"]["public"][name] == entry_digest
                assert len(Provider.harness_identities) == 1 and Provider.harness_identities[0].get("artifactHash") == snapshot_digest, {
                    "harnessIdentities": Provider.harness_identities, "snapshotDigest": snapshot_digest, "manifest": manifest,
                }
                assert manifest.get("runId") == Provider.harness_identities[0].get("runId") and manifest.get("scopeDigest") == Provider.harness_identities[0].get("scopeDigest"), {
                    "harnessIdentities": Provider.harness_identities, "manifest": manifest,
                }
                memory_plan_files = list((agent / "memory" / "runs").rglob("plan.json"))
                assert len(memory_plan_files) >= 1, memory_plan_files
                memory_plan_file = next(path for path in memory_plan_files if json.loads(path.read_text()).get("runId") == Provider.planner_identities[0].get("runId"))
                memory_manifest = json.loads((memory_plan_file.parent / "manifest.json").read_text())
                memory_snapshot_digest = hashlib.sha256((memory_plan_file.parent / "snapshot.json").read_bytes()).hexdigest()
                assert memory_manifest.get("snapshotDigest") == memory_snapshot_digest == Provider.planner_identities[0].get("artifactHash"), {
                    "memoryManifest": memory_manifest, "memoryPlanner": Provider.planner_identities,
                }
                assert memory_manifest.get("runId") == Provider.planner_identities[0].get("runId") and memory_manifest.get("scopeDigest") == Provider.planner_identities[0].get("scopeDigest"), {
                    "memoryPlanner": Provider.planner_identities, "memoryManifest": memory_manifest,
                }
                persisted_plan = json.loads(memory_plan_file.read_text())
                assert persisted_plan.get("selected") == names, persisted_plan
                session_text = session.read_text() if session.exists() else ""
                assert "continual-learning-result" in session_text, session_text[-4000:]
                return {"pi": subprocess.run([pi, "--version"], check=True, capture_output=True, text=True).stdout.strip(),
                        "command": "/consolidate full", "requestKinds": Provider.kinds,
                        "selectorRequests": Provider.kinds.count("selector"), "receipt": {"kind": run_receipt["kind"], "mode": run_receipt["mode"], "attempts": run_receipt["attempts"]},
                        "snapshotFrozen": True, "currentSessionMarker": True, "fullCorpusNames": names, "resultCustomType": True,
                        "deterministicLoopback": True, "nativeTui": True, "roots": "disposable"}
            finally:
                if process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                os.close(master)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False), flush=True)
