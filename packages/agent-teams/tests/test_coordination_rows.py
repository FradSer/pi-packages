"""Human-facing coordination rows expose names, subjects, and typed text."""

import fcntl
import json
import os
import pty
import secrets
import select
import shutil
import signal
import struct
import subprocess
import termios
import time
from pathlib import Path
from typing import Callable

import pytest

PACKAGE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_coordination_rows_are_readable_without_identifiers(tmp_path: Path) -> None:
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    result = subprocess.run(
        ["node", "tests/coordination-rows-fixture.ts"],
        cwd=PACKAGE,
        env={
            **{key: value for key, value in os.environ.items() if not key.startswith("PI_TEAMMATE_")},
            "PI_CODING_AGENT_DIR": str(agent_dir),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"{result.stderr}\n{result.stdout}"
    assert "COORDINATION_ROWS_OK" in result.stdout


@pytest.fixture
def native_message_fixture(tmp_path: Path) -> tuple[list[str], dict[str, str], Path]:
    pi = shutil.which("pi")
    if pi is None:
        pytest.skip("Pi CLI is required for native message layout verification")
    fixture = tmp_path / "message-layout.ts"
    snapshots = tmp_path / "renders.jsonl"
    source = r'''
import assert from "node:assert/strict";
import { appendFileSync } from "node:fs";
import { stripVTControlCharacters } from "node:util";
import { createAssistantMessageEventStream } from "@earendil-works/pi-ai";
import { initTheme, ToolExecutionComponent } from "@earendil-works/pi-coding-agent";
import { KeybindingsManager, setKeybindings, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { registerLeaderTools } from "__TOOLS__";
import { registerWorkerCapabilities } from "__WORKER__";

const message = "FIRST-CONTENT " + Array.from({ length: 28 }, (_, i) => `evidence-${i}`).join(" ") + " LAST-CONTENT";
const hyperlink = "\u001b]8;;https://example.test\u001b\\LINK-LABEL\u001b]8;;\u001b\\";
const literal = '\nPreserve this JSON: {"value":""}\nLiteral spacing: alpha ; beta !\nTwo quoted lines: "\n"';
const args = { to: "continual-audit-close", message: message + " " + hyperlink + literal };
const result = { content: [{ type: "text", text: "EVENT ROUTING · steered" }], details: { to: args.to, outcome: "steered" }, isError: false };
const expected = `[message] to @${args.to} · steered · ${message} LINK-LABEL${literal}`;
const tools = new Map();
const capture = (prefix) => ({ registerTool: (tool) => tools.set(`${prefix}:${tool.name}`, tool), on() {} });
registerLeaderTools(capture("leader"));
registerWorkerCapabilities(capture("worker"));

export default function (pi) {
  pi.on("session_start", (_event, ctx) => {
    if (ctx.mode === "tui") return;
    initTheme("dark", false);
    setKeybindings(new KeybindingsManager({ "app.tools.expand": { defaultKeys: "ctrl+o" } }));
    for (const surface of ["leader", "worker"]) {
      const component = new ToolExecutionComponent("agent_event", "native-layout", args, {}, tools.get(`${surface}:agent_event`), { requestRender() {} }, ctx.cwd);
      component.updateResult(result);
      const content = (width) => {
        const lines = component.render(width);
        assert.ok(lines.every((line) => visibleWidth(line) <= width));
        return lines.slice(2, -1).map((line) => stripVTControlCharacters(line).slice(1).trimEnd());
      };
      for (const width of [48, 90, 240]) {
        component.setExpanded(false);
        assert.ok(content(width)[0].endsWith(" · ctrl+o to expand"));
        assert.equal(component.handleMouse({ type: "click", button: "left", x: 5, y: 2, width, height: 4 })?.handled, true);
        assert.deepEqual(content(width), wrapTextWithAnsi(expected, width - 2));
        assert.equal(component.handleMouse({ type: "click", button: "left", x: 5, y: 2, width, height: 20 })?.handled, true);
        assert.ok(content(width)[0].endsWith(" · ctrl+o to expand"));
      }
    }
    console.log("NATIVE_MESSAGE_LAYOUT_OK");
  });
  const tool = tools.get("leader:agent_event");
  pi.registerTool({
    ...tool,
    // The original routing execute is never invoked: no peers or team writes.
    async execute() { return result; },
    renderResult(value, options, theme, context) {
      const component = tool.renderResult(value, options, theme, context);
      return {
        invalidate: () => component.invalidate(),
        render(width) {
          const lines = component.render(width);
          appendFileSync(process.env.PI_MESSAGE_LAYOUT_SNAPSHOTS, JSON.stringify({
            width, expanded: options.expanded, lines: lines.map(stripVTControlCharacters), expected,
            expectedLines: wrapTextWithAnsi(expected, width - 2).map((line) => line.trimEnd()),
          }) + "\n");
          return lines;
        },
      };
    },
  });
  let calls = 0;
  pi.registerProvider("message-layout-fixture", {
    api: "message-layout-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_MESSAGE_LAYOUT_AUTH,
    models: [{ id: "deterministic", name: "Message layout fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const first = ++calls === 1;
      const output = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: first ? [{ type: "toolCall", id: "message-row", name: "agent_event", arguments: args }]
          : [{ type: "text", text: "MESSAGE_LAYOUT_READY" }],
        stopReason: first ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: output });
      stream.push({ type: "done", reason: output.stopReason, message: output });
      stream.end();
      return stream;
    },
  });
}
'''
    fixture.write_text(source.replace("__TOOLS__", (Path(PACKAGE) / "src/tools.ts").as_uri())
                       .replace("__WORKER__", (Path(PACKAGE) / "src/worker.ts").as_uri()))
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "settings.json").write_text(json.dumps({"theme": "dark", "quietStartup": True}))
    env = {key: value for key, value in os.environ.items() if not key.startswith("PI_")}
    env.update({
        "HOME": str(tmp_path), "PI_CODING_AGENT_DIR": str(agent_dir), "PI_OFFLINE": "1",
        "PI_MESSAGE_LAYOUT_AUTH": secrets.token_hex(16), "PI_MESSAGE_LAYOUT_SNAPSHOTS": str(snapshots),
        "TERM": "xterm-256color",
    })
    command = [
        pi, "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes",
        "--no-context-files", "--no-approve", "--extension", str(fixture), "--provider", "message-layout-fixture",
        "--model", "deterministic", "--thinking", "off", "--no-builtin-tools", "Render the isolated message fixture",
    ]
    return command, env, snapshots


def test_native_pi_print_message_mouse_expansion_and_resizing(
    native_message_fixture: tuple[list[str], dict[str, str], Path], tmp_path: Path,
) -> None:
    command, env, _snapshots = native_message_fixture
    result = subprocess.run([*command, "--print"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "NATIVE_MESSAGE_LAYOUT_OK" in result.stdout + result.stderr, result.stdout + result.stderr
    assert "MESSAGE_LAYOUT_READY" in result.stdout, result.stdout + result.stderr
    assert "AssertionError" not in result.stderr


def test_native_pi_tui_message_expand_key_and_terminal_resize(
    native_message_fixture: tuple[list[str], dict[str, str], Path], tmp_path: Path,
) -> None:
    command, env, snapshots = native_message_fixture
    master, slave = pty.openpty()
    transcript = bytearray()

    def resize(width: int) -> None:
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 36, width, 0, 0))

    def renders() -> list[dict[str, object]]:
        if not snapshots.exists():
            return []
        lines = snapshots.read_text().splitlines()
        return [json.loads(line) for line in lines if line.endswith("}")]

    resize(90)
    try:
        with subprocess.Popen([*command, "--tui-mode", "fullscreen"], cwd=tmp_path, env=env,
                              stdin=slave, stdout=slave, stderr=slave) as process:
            os.close(slave)

            def wait_for(predicate: Callable[[], bool], timeout: float = 30) -> None:
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if select.select([master], [], [], 0.05)[0]:
                        try:
                            transcript.extend(os.read(master, 65536))
                        except OSError:
                            # The PTY master reports EIO/ENXIO/EBADF once the child
                            # closes its side. PTY closure can precede the
                            # observable exit status, so reap the child before
                            # deciding an exit predicate failed.
                            try:
                                process.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                pass
                            if predicate():
                                return
                            break
                    if predicate():
                        return
                    if process.poll() is not None:
                        break
                raise AssertionError(transcript.decode(errors="replace"))

            def recorded_summary() -> list[tuple[object, object]]:
                return [(row["width"], row["expanded"]) for row in renders()]

            def until(action: Callable[[], None], predicate: Callable[[], bool]) -> None:
                """Drive the real TUI to an observable state, retrying the interaction.

                Synchronization is data-based but never single-shot: the host may
                paint its first frame at its own default width, and a key sent
                while the turn is still settling can be dropped, so each step
                retries until its row is recorded.
                """
                last: AssertionError | None = None
                for _attempt in range(3):
                    action()
                    try:
                        wait_for(predicate, timeout=12)
                        return
                    except AssertionError:
                        last = AssertionError(
                            f"action attempt {_attempt + 1} never reached its row; recorded={recorded_summary()}"
                        )
                raise last or AssertionError("interaction never reached its observable state")

            def matches(width: int, expanded: bool) -> bool:
                return any(row["width"] == width and row["expanded"] == expanded for row in renders())

            try:
                # The host may paint its first frame at its own default width, so
                # startup synchronization is semantic; every width below is then
                # driven explicitly and verified from the recorded rows.
                wait_for(lambda: b"MESSAGE_LAYOUT_READY" in transcript and any(row["expanded"] is False for row in renders()))
                until(lambda: (resize(90), process.send_signal(signal.SIGWINCH)), lambda: matches(90, False))
                until(lambda: os.write(master, b"\x0f"), lambda: matches(90, True))  # Configured Ctrl+O.
                for width in [48, 240]:
                    until(
                        lambda w=width: (resize(w), process.send_signal(signal.SIGWINCH)),
                        lambda w=width: matches(w, True),
                    )
                until(lambda: os.write(master, b"\x0f"), lambda: matches(240, False))
                until(lambda: (resize(48), process.send_signal(signal.SIGWINCH)), lambda: matches(48, False))
                for row in renders():
                    content = [line[1:].rstrip() for line in row["lines"][1:-1]]
                    if row["expanded"]:
                        assert content == row["expectedLines"], content
                        assert " ".join(content).count("FIRST-CONTENT") == 1
                    else:
                        assert content[0].endswith(" · ctrl+o to expand"), content
                # Every resize and both expansion states must have produced a
                # verified row: synchronization above is state-based, so the
                # coverage assertion belongs here, on the recorded data.
                for width in (48, 90, 240):
                    for expanded in (True, False):
                        assert matches(width, expanded), (width, expanded, renders())
                # Quit with the configured key, retrying: an impatient Ctrl+D can
                # arrive while the closing turn is still settling and be ignored.
                for _attempt in range(3):
                    if process.poll() is not None:
                        break
                    try:
                        os.write(master, b"\x04")
                    except OSError:
                        break  # The PTY is already closed: the child exited.
                    try:
                        wait_for(lambda: process.poll() is not None, timeout=10)
                        break
                    except AssertionError:
                        continue
                if process.poll() is None:
                    # The row contract above is already verified; the host's own
                    # quit timing is not this test's subject, so terminate
                    # gracefully instead of failing on it.
                    try:
                        process.terminate()
                    except OSError:
                        pass  # It exited between the check and the signal.
                wait_for(lambda: process.poll() is not None, timeout=10)
                exit_code = process.wait(timeout=5)
                assert exit_code in (0, -signal.SIGTERM), transcript.decode(errors="replace")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    finally:
        os.close(master)
        (tmp_path / "terminal-transcript.txt").write_bytes(transcript)
