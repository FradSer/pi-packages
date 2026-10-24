"""Real-provider native-TUI acceptance for explicit ``/memory`` requests.

This is an explicit live check and is intentionally not collected by pytest.
It copies the configured Pi authentication into a disposable agent directory,
drives the real TUI through a PTY, waits on parent-owned receipts, and starts a
fresh print session to prove the persisted Memory is retrievable. It never
prints credentials or the captured terminal transcript.

Run manually with::

    python3 packages/continual-learning/tests/live_manual_memory.py
"""

from __future__ import annotations

from continuous_failure_retention import deduplicate_receipt_views

from live_acceptance_support import workspace_pi

import errno
from collections.abc import Callable
import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import subprocess
import tempfile
import time

from support import assert_safe_memory_tree as _assert_safe_memory_tree, read_memory_bodies as _memory_bodies


PACKAGE = Path(__file__).resolve().parents[1]
PROJECT_MARKER = "PROJECT_FACT_LIVE_COBALT"
PRIVATE_MARKER = "PRIVATE_PREF_LIVE_SABLE"


def _model(agent: Path) -> tuple[str, str]:
    value = json.loads((agent / "memory.json").read_text(encoding="utf-8"))
    provider, model = value.get("provider"), value.get("model")
    if not isinstance(provider, str) or not isinstance(model, str) or not provider or not model:
        raise AssertionError("Disposable agent memory.json has no usable provider/model")
    return provider, model


def _prepare(base: Path) -> tuple[Path, Path, Path]:
    """Prepare a project with existing AGENTS and Harness bytes to preserve."""
    # Importing the established helper keeps auth copying and scope setup in one
    # place. The helper never writes to the configured source agent directory.
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from live_smoke import prepare  # noqa: PLC0415

    project, agent, probe = prepare(base, False, agents_md=True)
    settings = json.loads((agent / "memory" / "settings.json").read_text(encoding="utf-8"))
    settings["automaticPhases"] = {"memory": "off", "harness": "off", "agents": "off"}
    (agent / "memory" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    harness = project / ".pi" / "harness.json"
    harness.parent.mkdir(parents=True, exist_ok=True)
    harness.write_text(json.dumps({
        "rules": [{
            "id": "manual-memory-preserve",
            "bash": "^printf\\s+MANUAL_MEMORY_PRESERVE$",
            "action": "block",
            "message": "Preserve this existing Harness declaration.",
        }],
    }, indent=2) + "\n", encoding="utf-8")
    # The helper probe is replaced with a private readiness marker. Waiting for
    # session_start avoids racing the first slash command against extension
    # registration while keeping the PTY wait deadline-driven.
    ready = base / "tui-ready"
    probe.write_text(
        "import fs from 'node:fs'; export default function(pi) {"
        f" pi.on('session_start', () => fs.writeFileSync({json.dumps(str(ready))}, 'ready')); }}",
        encoding="utf-8",
    )
    return project, agent, probe


def _runtime_env(agent: Path, home: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "xdg-config"),
        "XDG_DATA_HOME": str(home / "xdg-data"),
        "XDG_STATE_HOME": str(home / "xdg-state"),
        "PI_CODING_AGENT_DIR": str(agent),
        "PI_TELEMETRY": "0",
        "TERM": "xterm-256color",
    })
    return env


class NativeTui:
    def __init__(self, command: list[str], cwd: Path, env: dict[str, str]) -> None:
        self.master, slave = pty.openpty()
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=slave, stdout=slave, stderr=slave)
        os.close(slave)
        self.transcript = bytearray()

    def _pump(self) -> None:
        if not select.select([self.master], [], [], 0.05)[0]:
            return
        try:
            self.transcript.extend(os.read(self.master, 65_536))
        except OSError as error:
            if error.errno != errno.EIO:
                raise

    def wait_until(self, predicate: Callable[[], bool], timeout: float, message: str) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._pump()
            if predicate():
                return
            if self.process.poll() is not None:
                # Exit can occur between the predicate and this poll.
                if predicate():
                    return
                break
        if self.process.poll() is not None:
            message = f"{message} (native Pi exit={self.process.returncode}, terminalBytes={len(self.transcript)})"
        raise AssertionError(message)

    def send(self, text: str) -> None:
        os.write(self.master, text.encode("utf-8") + b"\r")

    def close(self) -> None:
        if self.process.poll() is None:
            self.send("/quit")
            try:
                self.wait_until(lambda: self.process.poll() is not None, 20, "Native Pi TUI did not exit")
            except AssertionError:
                self.process.send_signal(signal.SIGTERM)
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        os.close(self.master)


def _receipt_files(agent: Path) -> list[Path]:
    return sorted(
        (agent / "memory" / "runs").glob("**/learning-pipeline-receipt.json"),
        key=lambda path: path.stat().st_mtime_ns,
    )


def _receipt_state(agent: Path) -> dict[Path, tuple[int, int]]:
    return {
        path: (path.stat().st_mtime_ns, path.stat().st_size)
        for path in _receipt_files(agent)
    }


def _read_receipt(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _is_manual_memory_receipt(value: dict | None) -> bool:
    if not value or value.get("kind") != "learning-pipeline-receipt" or value.get("mode") != "manual":
        return False
    screen = value.get("screen")
    if not isinstance(screen, dict) or screen.get("memory") is not True or screen.get("harness") is not False or screen.get("agents") is not False:
        return False
    attempts = value.get("attempts")
    return isinstance(attempts, list) and any(
        isinstance(attempt, dict)
        and attempt.get("phase") == "memory"
        and attempt.get("outcome") in {"applied", "proposed", "noop"}
        for attempt in attempts
    )



def _changed_receipt_views(agent: Path, before: dict[Path, tuple[int,int]]) -> list[dict]:
    files=_receipt_files(agent);all_values=[];changed=[]
    for file in files:
        value=_read_receipt(file)
        if value is None:return []
        all_values.append(value)
        stat=file.stat()
        if before.get(file)!=(stat.st_mtime_ns,stat.st_size):changed.append(value)
    try:
        # An unchanged compatibility copy can still conflict with a new archive.
        deduplicate_receipt_views(all_values)
        return deduplicate_receipt_views(changed)
    except ValueError:return []

def _wait_receipt(tui: NativeTui, agent: Path, before: dict[Path, tuple[int, int]], timeout: float = 480) -> dict:
    def find() -> dict | None:
        matches=[value for value in _changed_receipt_views(agent,before) if _is_manual_memory_receipt(value)]
        return matches[0] if len(matches)==1 else None

    found: list[dict | None] = [None]

    def ready() -> bool:
        found[0] = find()
        return found[0] is not None

    tui.wait_until(ready, timeout, "Timed out waiting for a verified manual Memory receipt")
    assert found[0] is not None
    return found[0]


def _scope_root(agent: Path) -> Path:
    roots = sorted((agent / "memory").glob("--*--"))
    if len(roots) != 1 or not roots[0].is_dir() or roots[0].is_symlink():
        raise AssertionError(f"Expected one safe private Memory root, found {len(roots)}")
    return roots[0]


def _run_fresh_print(project: Path, agent: Path, home: Path, provider: str, model: str, targets: tuple[Path, ...]) -> dict:
    from live_smoke import path_argument_matches_any, successful_tool_call
    session = project.parent / "fresh-print-session.jsonl"
    result = subprocess.run(
        [
            workspace_pi(Path(__file__).resolve().parents[3]),
            "-e", str(PACKAGE / "index.ts"),
            "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files",
            "--no-approve", "--session", str(session), "--print", "--mode", "json",
            "--model", f"{provider}/{model}", "--tools", "read",
            "Read the saved project Memory for this fresh task. Find the entry containing "
            f"{PROJECT_MARKER} by using the Memory index and the read tool, then reply with "
            "the exact marker and its meaning. Do not treat this request itself as evidence.",
        ],
        cwd=project,
        env=_runtime_env(agent, home),
        capture_output=True,
        text=True,
        timeout=480,
    )
    if result.returncode != 0:
        raise AssertionError(f"Fresh Pi print failed with exit code {result.returncode}")
    records = [json.loads(line) for line in session.read_text(encoding="utf-8").splitlines() if line.strip()]
    messages = [entry["message"] for entry in records if entry.get("type") == "message" and isinstance(entry.get("message"), dict)]
    read_saved_fact = successful_tool_call(
        messages, "read", lambda arguments: path_argument_matches_any(project, targets, arguments), PROJECT_MARKER,
    )
    visible = "\n".join(
        block.get("text", "")
        for message in messages if message.get("role") == "assistant"
        for block in message.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    )
    if not read_saved_fact or PROJECT_MARKER not in visible:
        raise AssertionError("Fresh Pi session did not read and answer the saved project Memory marker")
    return {"readToolResult": True, "answeredMarker": True}


def verify() -> dict:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="continual-learning-manual-memory-") as raw:
        base = Path(raw)
        project, agent, probe = _prepare(base)
        provider, model = _model(agent)
        agents_before = (project / "AGENTS.md").read_bytes()
        harness_before = (project / ".pi" / "harness.json").read_bytes()
        home = base / "home"
        home.mkdir()
        env = _runtime_env(agent, home)
        pi = workspace_pi(Path(__file__).resolve().parents[3])
        if not pi:
            raise RuntimeError("Pi CLI is required for the real native-TUI acceptance")
        command = [
            pi, "-e", str(probe), "-e", str(PACKAGE / "index.ts"),
            "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files",
            "--no-approve", "--session", str(base / "tui-session.jsonl"),
            "--model", f"{provider}/{model}", "--tools", "read",
        ]
        tui = NativeTui(command, project, env)
        try:
            tui.wait_until(lambda: tui.process.poll() is None and (base / "tui-ready").is_file(), 30, "Native Pi TUI did not reach session_start")

            before = _receipt_state(agent)
            tui.send(
                f"/memory 记住这个项目事实：{PROJECT_MARKER} 是该项目的发布标记；同时记住我的个人偏好："
                f"{PRIVATE_MARKER}，这是私人偏好，只能保存在私有 Memory，不能出现在共享 Memory。"
            )
            receipt = _wait_receipt(tui, agent, before)
        finally:
            tui.close()

        if agents_before != (project / "AGENTS.md").read_bytes():
            raise AssertionError("Explicit /memory changed existing AGENTS.md bytes")
        if harness_before != (project / ".pi" / "harness.json").read_bytes():
            raise AssertionError("Explicit /memory changed existing Harness bytes")

        private_root = _scope_root(agent)
        public_root = project / ".memory"
        if not public_root.is_dir() or public_root.is_symlink():
            raise AssertionError("Explicit project Memory did not create a safe shared mirror")
        private = _memory_bodies(private_root)
        public = _memory_bodies(public_root)
        project_files = [name for name, content in private.items() if PROJECT_MARKER in content]
        private_files = [name for name, content in private.items() if PRIVATE_MARKER in content]
        if not project_files or not private_files:
            raise AssertionError("Real Memory planners did not persist both requested markers")
        if any(PROJECT_MARKER not in public.get(name, "") or public[name] != private[name] for name in project_files):
            raise AssertionError("Safe project Memory was not mirrored byte-for-byte")
        if any(PRIVATE_MARKER in content for content in public.values()):
            raise AssertionError("Private preference leaked into shared Memory")
        public_index = (public_root / "MEMORY.md").read_text(encoding="utf-8")
        if PRIVATE_MARKER in public_index or any(name in public_index for name in private_files):
            raise AssertionError("Private preference leaked into the shared Memory index")
        private_index = (private_root / "MEMORY.md").read_text(encoding="utf-8")
        if not all(any(name in line and "harness only" in line.lower() for line in private_index.splitlines()) for name in private_files):
            raise AssertionError("Private Memory was not marked harness-only in its canonical index")

        targets = tuple(root / name for name in project_files for root in (private_root, public_root))
        fresh = _run_fresh_print(project, agent, home, provider, model, targets)
        duration = round(time.monotonic() - started, 2)
        return {
            "provider": provider,
            "model": model,
            "durationSeconds": duration,
            "manualMemoryRequests": 1,
            "receipt": {"operations": receipt.get("operations"), "screen": receipt.get("screen")},
            "agentsPreserved": True,
            "harnessPreserved": True,
            "safeMirrorByteIdentical": True,
            "privateOnlyNoSharedLeak": True,
            "freshPrint": fresh,
        }


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False), flush=True)
