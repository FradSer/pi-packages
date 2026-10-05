"""Shared PTY driving for isolated native Pi reproductions."""
from __future__ import annotations

import errno
import json
import secrets
import threading
import fcntl
import os
import pty
import re
import select
import signal
import struct
import subprocess
import termios
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from subagents_helpers import REPO

ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


class LoopbackServer(ThreadingHTTPServer):
    """Own the repeated local HTTP server/thread lifecycle."""

    def __init__(self, handler: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(("127.0.0.1", 0), handler)
        self.daemon_threads = True
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.shutdown()
        self.server_close()
        self.thread.join(timeout=5)


class NativeTui:
    """Own one terminal/process; each scenario still owns its input and assertions."""

    def __init__(self, command: list[str], *, cwd: Path, env: dict[str, str],
                 rows: int = 35, columns: int = 100, timeout: float = 45,
                 start_new_session: bool = False) -> None:
        self.rows = rows
        self.timeout = timeout
        self.transcript = bytearray()
        self.master, slave = pty.openpty()
        try:
            fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
            self.process = subprocess.Popen(command, cwd=cwd, env=env,
                stdin=slave, stdout=slave, stderr=slave, start_new_session=start_new_session)
        except BaseException:
            os.close(self.master)
            raise
        finally:
            os.close(slave)

    def screen(self) -> str:
        return ANSI.sub("", self.transcript.decode(errors="replace"))

    def send(self, data: bytes) -> None:
        os.write(self.master, data)

    def resize(self, columns: int) -> None:
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", self.rows, columns, 0, 0))
        self.process.send_signal(signal.SIGWINCH)

    def wait_for(self, predicate: Callable[[], bool]) -> None:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if select.select([self.master], [], [], 0.05)[0]:
                try:
                    data = os.read(self.master, 65536)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    data = b""
                if not data:
                    # macOS can report PTY EOF just before waitpid observes exit.
                    self.process.wait(timeout=5)
                    if predicate():
                        return
                    break
                self.transcript.extend(data)
            if predicate():
                return
            if self.process.poll() is not None:
                if predicate():
                    return
                break
        raise AssertionError(self.screen()[-7000:])

    def close(self) -> None:
        try:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        finally:
            os.close(self.master)

    def __enter__(self) -> NativeTui:
        return self

    def __exit__(self, *_exception: object) -> None:
        self.close()


@pytest.fixture
def native_command(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[tuple[list[str], dict[str, str], Path, list[dict[str, Any]], threading.Event]]:
    pi = REPO / 'node_modules' / '.bin' / 'pi'
    if not pi.is_file():
        pytest.skip('Repository Pi CLI is required for native subagent verification')
    for core in ('pi-ai', 'pi-coding-agent', 'pi-tui'):
        manifest = REPO / 'node_modules' / '@earendil-works' / core / 'package.json'
        version = json.loads(manifest.read_text(encoding='utf-8'))['version']
        assert version == '1.0.0', f'Native verification requires {core}@1.0.0, found {version}'
    requests: list[dict[str, Any]] = []
    release = threading.Event()
    result_text = str(getattr(request, "param", "2"))

    class ModelHandler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(payload)
            if not release.wait(timeout=30):
                self.send_error(504, 'Offline fixture was not released')
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            base = {'id': 'offline-arithmetic', 'object': 'chat.completion.chunk',
                    'created': 1, 'model': 'arithmetic'}
            for delta, finish in (({'role': 'assistant', 'content': result_text}, None), ({}, 'stop')):
                chunk = {**base, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}
                self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
                self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n')
            self.wfile.flush()

    server = LoopbackServer(ModelHandler)
    agent_dir = tmp_path / 'agent'
    agent_dir.mkdir()
    (agent_dir / 'settings.json').write_text(json.dumps({'theme': 'dark', 'quietStartup': True}))
    # These are generated fixture credentials, never the user's auth/config.
    credential = secrets.token_hex(16)
    (agent_dir / 'models.json').write_text(json.dumps({'providers': {
        'subagents-local-fixture': {'api': 'openai-completions', 'apiKey': credential,
            'baseUrl': f'http://127.0.0.1:{server.server_port}/v1',
            'models': [{'id': 'arithmetic', 'name': 'Offline arithmetic', 'reasoning': False,
                'input': ['text'], 'contextWindow': 200000, 'maxTokens': 4096,
                'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}]}
    }}))
    snapshots = tmp_path / 'agent-usage.jsonl'
    env = {'PATH': os.environ['PATH']}
    env.update({'HOME': str(tmp_path), 'PI_CODING_AGENT_DIR': str(agent_dir), 'PI_OFFLINE': '1',
        'PI_AGENT_USAGE_AUTH': credential, 'PI_AGENT_USAGE_SNAPSHOTS': str(snapshots),
        'PI_AGENT_RESULT_TEXT': result_text, 'TERM': 'xterm-256color'})
    command = [str(pi), '--no-session', '--no-extensions', '--no-skills', '--no-prompt-templates',
        '--no-themes', '--no-context-files', '--no-approve', '--no-builtin-tools',
        '--extension', str(Path(__file__).resolve().parents[3] / 'tests' / 'live-agent-usage-fixture.ts'),
        '--provider', 'subagents-parent-fixture', '--model', 'scripted', '--thinking', 'off',
        'Start one agent to calculate 1+1, then rely on its automatic result.']
    try:
        yield command, env, snapshots, requests, release
    finally:
        release.set()
        server.close()


def records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]
