"""Run a real `pi` process against one install combination.

Everything here is about making "installed alone" mean something. The combination
is resolved from each package's manifest, not from a list written in a test: a
bundle's own entry registers one tool and its *manifest* is what loads the other
two, so a suite that hand-listed the entries would stop proving that the manifest
is what an install relies on.
"""

from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

REPO = Path(__file__).resolve().parents[3]
PACKAGES = REPO / "packages"
# The fixture lives inside the package whose dependencies the install resolves
# through, so a bare specifier in it names the same module instance the
# packages themselves use. A fixture elsewhere would register a role in a
# second copy of the registry and watch the first refuse to find it.
E2E = Path(__file__).resolve().parents[1]
FIXTURE = PACKAGES / "agent-teams" / "tests" / "e2e" / "install-fixture.ts"

# The tool the harness uses to ask the host what it actually registered. It is not
# one of the three, so a suite asserting the surface can tell its own probe apart.
PROBE = "e2e_probe"

# Prefix the scripted provider puts on its final answer. Must match scripted.ts.
REPORT_PREFIX = "E2E_REPORT"

# The one answer a spawned child returns. Deterministic so a suite can assert that
# a prompt reached a real child process rather than only that a process started.
CHILD_ANSWER = "CHILD_READS_THE_EVIDENCE"


def isolated_environment(tmp_path: Path) -> dict[str, str]:
    """Keep credentials, config and temporary writes out of the developer's HOME."""
    env = {name: os.environ[name] for name in (
        "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "SYSTEMROOT",
    ) if name in os.environ}
    home = tmp_path / "home"
    agent_dir = tmp_path / "agent"
    temporary = tmp_path / "tmp"
    xdg = {name: home / suffix for name, suffix in (
        ("XDG_CONFIG_HOME", ".config"), ("XDG_CACHE_HOME", ".cache"),
        ("XDG_DATA_HOME", ".local/share"), ("XDG_STATE_HOME", ".local/state"),
    )}
    for directory in (home, agent_dir, temporary, *xdg.values()):
        directory.mkdir(parents=True, exist_ok=True)
    auth = agent_dir / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")
    auth.chmod(0o600)
    (agent_dir / "settings.json").write_text(
        json.dumps({"theme": "dark", "quietStartup": True}), encoding="utf-8"
    )
    env.update({
        "HOME": str(home), "PI_CODING_AGENT_DIR": str(agent_dir),
        "TMPDIR": str(temporary), "TMP": str(temporary), "TEMP": str(temporary),
        **{name: str(directory) for name, directory in xdg.items()},
        "COREPACK_ENABLE_NETWORK": "0",
        "PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "off",
    })
    return env


def manifest(package: str) -> dict[str, object]:
    return json.loads((PACKAGES / package / "package.json").read_text(encoding="utf-8"))


def loaded_entries(installed: list[str]) -> list[str]:
    """The extension entries a real install of `installed` would load.

    Follows each package's own `pi.extensions` for its own entry, and for a
    bundled dependency resolves the node_modules path back to the local package so
    the suite runs the source this repository actually contains.
    """
    resolved: list[str] = []
    for package in installed:
        declared = manifest(package).get("pi", {}).get("extensions", [])  # type: ignore[union-attr]
        assert declared, f"{package} declares no extension entry"
        assert declared[0] == "./index.ts", f"{package} must load its own root index first"
        for entry in declared:
            if "node_modules" not in entry:
                resolved.append(package)
                continue
            parts = Path(entry).parts
            name = parts[2] if parts[1].startswith("@") else parts[1]
            local = name[3:] if name.startswith("pi-") else name
            assert (PACKAGES / local / "index.ts").is_file(), (
                f"{package} bundles {local}, which has no root index to load"
            )
            assert local not in resolved, f"{package} bundles {local} twice"
            resolved.append(local)
    return resolved


@contextmanager
def child_model() -> Iterator[tuple[str, list[dict[str, object]]]]:
    """The only reachable model endpoint: the loopback child.

    Every `agent_start` takes a prompt, so a spawned child always asks a model.
    The parent's provider is registered in process by the fixture, so this server
    serves child traffic alone, which makes each recorded request proof that a
    prompt reached a real child process.
    """
    requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({
                "path": self.path,
                "model": payload.get("model"),
                "messages": payload.get("messages", []),
            })
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for delta, finish in (({"role": "assistant", "content": CHILD_ANSWER}, None), ({}, "stop")):
                chunk = {"id": "e2e-child", "object": "chat.completion.chunk", "created": 1,
                         "model": payload.get("model", "deterministic"),
                         "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        def log_message(self, _format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@dataclass
class Run:
    completed: subprocess.CompletedProcess[str]
    rpc_events: list[dict[str, object]] = field(default_factory=list)
    model_requests: list[str] = field(default_factory=list)
    live_children: list[int] = field(default_factory=list)

    def child_prompts(self) -> list[str]:
        """The user text each spawned child received, oldest first."""
        prompts: list[str] = []
        for request in self.model_requests:
            messages = request.get("messages")
            for message in messages if isinstance(messages, list) else []:
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                for block in content if isinstance(content, list) else []:
                    if isinstance(block, dict) and block.get("type") == "text":
                        prompts.append(str(block.get("text", "")))
        return prompts

    @property
    def text(self) -> str:
        return self.completed.stdout + self.completed.stderr

    def report(self) -> dict[str, object]:
        """The transcript-derived report the scripted provider emitted.

        The provider builds it by reading the transcript, so every value in it came
        out of a real tool execution rather than out of the fixture.
        """
        for line in self.completed.stdout.splitlines():
            marker = line.strip()
            if marker.startswith(f"{REPORT_PREFIX} "):
                return json.loads(marker[len(REPORT_PREFIX) + 1:])
        raise AssertionError(
            f"no {REPORT_PREFIX} in the run output; the scripted turn never completed:\n{self.text}"
        )

    def surfaces(self) -> list[str]:
        tools = self.report().get("tools")
        return [str(name) for name in tools] if isinstance(tools, list) else []

    def calls(self) -> list[dict[str, object]]:
        calls = self.report().get("calls")
        return list(calls) if isinstance(calls, list) else []

    def calls_named(self, name: str) -> list[dict[str, object]]:
        return [call for call in self.calls() if call.get("name") == name]

    def call(self, name: str) -> dict[str, object]:
        """The one recorded execution of `name`, or a failure naming what ran."""
        matching = self.calls_named(name)
        if len(matching) != 1:
            ran = [str(call.get("name")) for call in self.calls()]
            raise AssertionError(f"expected exactly one {name} call, saw {ran}")
        return matching[0]

    def details(self, name: str) -> dict[str, object]:
        details = self.call(name).get("details")
        return details if isinstance(details, dict) else {}


def run_install(
    tmp_path: Path,
    installed: list[str],
    *,
    scenario: str = "surface",
    tools: str | None = None,
    prompt: str = "Run the install E2E",
    extra_args: list[str] | None = None,
    host: str | None = None,
    timeout: int = 40,
) -> Run:
    """Start a real `pi` process that is exactly `installed`.

    The process runs in its own session so the suite can reap it as a group. A
    suite that starts a child process must not be able to leak one: the report
    arrives on stdout, and a child the scenario did not stop would otherwise keep
    the session alive past the run and into the next test.
    """
    local_pi = REPO / "node_modules" / ".bin" / "pi"
    if not local_pi.is_file():
        pytest.skip("the repository Pi 1.0.0 CLI is required; no global CLI fallback is permitted")
    for package in ("pi-ai", "pi-coding-agent", "pi-tui"):
        core = REPO / "node_modules" / "@earendil-works" / package / "package.json"
        version = json.loads(core.read_text(encoding="utf-8"))["version"]
        assert version == "1.0.0", f"install fixture requires the root 1.0.0 cohort, found {package}@{version}"
    pi = str(local_pi)

    entries = loaded_entries(installed)
    env = isolated_environment(tmp_path)
    agent_dir = Path(env["PI_CODING_AGENT_DIR"])
    trace = agent_dir / "rpc-children.jsonl"
    env.update({
        # The parent's provider is entirely in-process. The child model below
        # exists on disk too, because --no-extensions cannot inherit that provider.
        "PI_E2E_AUTH": secrets.token_hex(16),
        "PI_E2E_PACKAGES": ",".join(entries),
        "PI_E2E_SCENARIO": scenario,
        "PI_E2E_PROBE": PROBE,
        # Whether the fixture publishes the coordinator seam, which is what puts a
        # second participant on the tasks so resource conflicts exist to be refused.
        "PI_E2E_HOST": host or "0",
        "NODE_OPTIONS": f'--require="{E2E / "support" / "rpc-observer.cjs"}"',
    })

    command = [
        pi, "--print", "--no-session", "--no-extensions", "--no-skills",
        "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-approve",
        "--extension", str(FIXTURE),
        "--provider", "e2e-scripted", "--model", "deterministic", "--thinking", "off",
        # No `--tools` filter by default: the point of the surface assertion is which
        # tools the packages registered, and a filter would make that a fact about
        # this harness rather than about the install.
        *(["--tools", tools] if tools else []),
        prompt,
        *(extra_args or []),
    ]
    with child_model() as (base_url, requests):
        # Keep the inherited provider/model resolvable in a bare child without
        # installing any additional package or executable child extension.
        models = agent_dir / "models.json"
        models.write_text(json.dumps({"providers": {
            "e2e-scripted": {
                "api": "openai-completions", "baseUrl": base_url,
                "apiKey": env["PI_E2E_AUTH"],
                "models": [{"id": "deterministic", "reasoning": False, "input": ["text"],
                            "contextWindow": 200000, "maxTokens": 4096}],
            },
        }}), encoding="utf-8")
        models.chmod(0o600)
        process = subprocess.Popen(
            command, cwd=tmp_path, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True,
        )
        output = ""
        timed_out = False
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _reap(process)
            output, _ = process.communicate(timeout=5)
        finally:
            _reap(process)
            events = _rpc_events(trace)
            live_children = _reap_rpc_children(events)
            if process.stdout is not None:
                process.stdout.close()
        completed = subprocess.CompletedProcess(command, 124 if timed_out else process.returncode, output, "")
        return Run(completed, events, list(requests), live_children)


def _reap(process: subprocess.Popen[str]) -> None:
    """Reap this run's process group, including descendants of an exited parent."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        if process.poll() is None:
            process.kill()
    process.wait(timeout=5)


def _rpc_events(trace: Path) -> list[dict[str, object]]:
    if not trace.exists():
        return []
    return [json.loads(line) for line in trace.read_text(encoding="utf-8").split("\n") if line]


def _reap_rpc_children(events: list[dict[str, object]]) -> list[int]:
    """The real spawner uses detached groups; the parent's group cannot reap them."""
    spawned = {int(event["pid"]) for event in events if event.get("type") == "spawn" and event.get("pid")}
    closed = {int(event["pid"]) for event in events if event.get("type") == "close" and event.get("pid")}
    for pid in spawned - closed:
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    live: list[int] = []
    for pid in spawned:
        try:
            os.kill(pid, 0)
            live.append(pid)
        except ProcessLookupError:
            pass
    return live
