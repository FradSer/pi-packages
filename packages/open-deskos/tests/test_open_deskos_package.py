from __future__ import annotations

import json
import os
import pytest
import re
import subprocess
import tempfile
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
SRC = PACKAGE / "src"


def run_typescript(script: str) -> subprocess.CompletedProcess[str]:
    # Node 24 can run these fixtures without tsx on an isolated verification host.
    loader = [] if os.environ.get("ODK_TEST_NATIVE_TS") == "1" else ["--import", "tsx"]
    with tempfile.TemporaryDirectory(prefix="desk-test-registry-") as registry:
        env = dict(os.environ, PI_DIRECTORY_SESSIONS_DIR=registry)
        env.pop("ODK_DESK_LINK_ADDRESS", None)
        env.pop("ODK_DESK_LINK_TOKEN", None)
        result = subprocess.run(
            ["node", *loader, "--input-type=module"],
            cwd=REPO,
            env=env,
            input=textwrap.dedent(script),
            text=True,
            capture_output=True,
            check=False,
        )
    assert result.returncode == 0, f"TypeScript runtime check failed:\n{result.stderr}\n{result.stdout}"
    return result


def report(script: str) -> dict:
    """Run a harness whose last line is a JSON report."""
    result = run_typescript(script)
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    assert lines, f"harness printed no JSON report:\n{result.stdout}"
    return json.loads(lines[-1])


# ── Package contract ────────────────────────────────────────────────

def test_manifest_declares_native_pi_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "pi-package" in manifest["keywords"]
    assert manifest["name"] == "pi-open-deskos"
    assert manifest["pi"]["extensions"] == ["./index.ts"]
    assert set(manifest["files"]) >= {"index.ts", "src", "fixtures", "README.md", "README.zh-CN.md"}
    fixture = json.loads((PACKAGE / "fixtures" / "control-v2.json").read_text(encoding="utf-8"))
    assert fixture["handshake"]["transcript"] == "open-deskos-control-v2\n2\nnonce-fixture\ndesk-mac\nconsole-session"
    assert fixture["requests"]["attachFresh"]["after"] is None


def test_control_contract_fixture_matches_the_desk_copy() -> None:
    """The v2 control contract ships in both repositories; drift must be loud wherever both exist."""
    desk = PACKAGE.parents[2] / "open-deskos" / "runtime" / "linux" / "tests" / "fixtures" / "control-v2.json"
    if not desk.is_file():
        pytest.skip("sibling open-deskos checkout is not present")
    assert (PACKAGE / "fixtures" / "control-v2.json").read_bytes() == desk.read_bytes(), (
        "the Console and desk control fixtures must stay byte-identical"
    )


def test_extension_entry_points_exist() -> None:
    assert (PACKAGE / "index.ts").is_file(), "Package-root extension entry index.ts is missing"
    for name in ("index.ts", "types.ts", "events.ts", "reporter.ts", "transport.ts", "config.ts", "control-transport.ts", "console-client.ts", "console-extension.ts"):
        assert (SRC / name).is_file(), f"Extension source {name} is missing"


def test_extension_declares_kits_as_dependencies_and_pi_core_as_peers() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert manifest["dependencies"]["@fradser/pi-kit"] == "workspace:*"
    assert "@fradser/pi-kit" not in manifest.get("peerDependencies", {})
    for peer in ("@earendil-works/pi-coding-agent", "@earendil-works/pi-tui", "typebox"):
        assert peer in manifest["peerDependencies"], f"{peer} must stay a peer dependency"


def test_every_documented_install_command_can_actually_work() -> None:
    """The documented install path must exist: an unpublished npm name silently
    sends an operator to a 404."""
    with tempfile.TemporaryDirectory(prefix="desk-install-test-") as temporary:
        root = Path(temporary)
        checkout = root / "checkout with spaces"
        package = checkout / "packages" / "open-deskos"
        package.mkdir(parents=True)
        (package / "package.json").write_bytes((PACKAGE / "package.json").read_bytes())
        home = root / "unrelated home"
        (home / ".pi" / "agent").mkdir(parents=True)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        recorder = bin_dir / "pi"
        recorder.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$PI_INSTALL_RECORD"\n')
        recorder.chmod(0o755)

        for filename in ("README.md", "README.zh-CN.md"):
            readme = (PACKAGE / filename).read_text(encoding="utf-8")
            recipes = [
                block
                for block in re.findall(r"```bash\n(.*?)```", readme, re.DOTALL)
                if any(line.strip().startswith("pi install ") and "npm:" not in line for line in block.splitlines())
            ]
            assert recipes, f"{filename} must document a local install command"
            for index, recipe in enumerate(recipes):
                record = root / f"{filename}-{index}.args"
                result = subprocess.run(
                    ["/bin/sh", "-eu", "-c", recipe],
                    cwd=checkout,
                    env={"HOME": str(home), "PATH": str(bin_dir), "PI_INSTALL_RECORD": str(record)},
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=5,
                )
                assert result.returncode == 0, f"{filename}: {result.stdout}{result.stderr}"
                assert record.read_text().splitlines() == ["install", str(package.resolve())], filename

            for variable in ("ODK_DESK_LINK_ADDRESS", "ODK_DESK_LINK_TOKEN", "ODK_DESK_LINK_CONTROL_TOKEN"):
                assert variable in readme, f"{filename} must document {variable}"


# ── Configuration boundary ──────────────────────────────────────────

def test_configuration_is_all_or_nothing() -> None:
    result = report(
        r'''
        import { readDeskLinkConfig, defaultMachineName, tokenDigest } from "./packages/open-deskos/src/config.ts";
        const configured = readDeskLinkConfig({ ODK_DESK_LINK_ADDRESS: "10.0.0.5:8765", ODK_DESK_LINK_TOKEN: "t" });
        const controlled = readDeskLinkConfig({ ODK_DESK_LINK_ADDRESS: "10.0.0.5:8765", ODK_DESK_LINK_TOKEN: "t", ODK_DESK_LINK_CONTROL_TOKEN: "control" });
        const noToken = readDeskLinkConfig({ ODK_DESK_LINK_ADDRESS: "10.0.0.5:8765" });
        const noAddress = readDeskLinkConfig({ ODK_DESK_LINK_TOKEN: "t" });
        const badPort = readDeskLinkConfig({ ODK_DESK_LINK_ADDRESS: "10.0.0.5:", ODK_DESK_LINK_TOKEN: "t" });
        const noPort = readDeskLinkConfig({ ODK_DESK_LINK_ADDRESS: "10.0.0.5", ODK_DESK_LINK_TOKEN: "t" });
        console.log(JSON.stringify({
          configured,
          controlled,
          unconfigured: [noToken, noAddress, badPort, noPort].map((value) => value === null),
          machine: defaultMachineName("desk-mac.local"),
          digestStable: tokenDigest("secret") === tokenDigest("secret") && tokenDigest("secret") !== tokenDigest("other"),
          digestHidesToken: !tokenDigest("secret").includes("secret"),
        }));
        '''
    )
    assert result["configured"] == {"machine": result["configured"]["machine"], "host": "10.0.0.5", "port": 8765, "token": "t"}
    assert result["controlled"]["controlToken"] == "control"
    assert result["unconfigured"] == [True, True, True, True], "a partially configured link must be silent"
    assert result["machine"] == "desk-mac"
    assert result["digestStable"] is True
    assert result["digestHidesToken"] is True


def test_machine_identity_falls_back_when_the_hostname_is_empty() -> None:
    result = report(
        r'''
        import { defaultMachineName } from "./packages/open-deskos/src/config.ts";
        console.log(JSON.stringify({ empty: defaultMachineName(""), local: defaultMachineName("Desk-Mac.local") }));
        '''
    )
    assert result["empty"] == "pi-machine"
    assert result["local"] == "Desk-Mac"


# ── Session Event extraction ────────────────────────────────────────

def test_events_come_from_messages_with_complete_tool_result_bodies() -> None:
    result = report(
        r'''
        import { eventsFromMessage, promptFromMessage, summarizeToolCall, boundEventText } from "./packages/open-deskos/src/events.ts";
        const long = "x".repeat(500);
        console.log(JSON.stringify({
          user: eventsFromMessage({ role: "user", content: [{ type: "text", text: "why is the renderer empty" }] }),
          userText: eventsFromMessage({ role: "user", content: "plain text prompt" }),
          thinking: eventsFromMessage({ role: "assistant", content: [{ type: "thinking", thinking: "checking the composer\nand more" }] }),
          tool: eventsFromMessage({ role: "assistant", content: [{ type: "toolCall", name: "bash", arguments: { command: "pnpm test" } }] }),
          assistant: eventsFromMessage({ role: "assistant", content: [{ type: "text", text: "the composer never ran" }] }),
          result: eventsFromMessage({ role: "toolResult", toolName: "bash", content: [{ type: "text", text: "first line\nsecond line" }] }),
          empty: eventsFromMessage(null),
          unmapped: eventsFromMessage({ type: "session", id: "s1" }),
          goal: promptFromMessage({ role: "user", content: [{ type: "text", text: "  read   the    layout  " }] }),
          notGoal: promptFromMessage({ role: "assistant", content: [{ type: "text", text: "nope" }] }),
          readPath: summarizeToolCall("read", { path: "/a/b/index.ts" }),
          query: summarizeToolCall("ffgrep", { query: "index" }),
          bare: summarizeToolCall("work", {}),
          bounded: boundEventText(long).length,
          assistantBody: eventsFromMessage({ role: "assistant", content: [{ type: "text", text: "a\nb" }] })[0].text,
          assistantParts: eventsFromMessage({ role: "assistant", content: [{ type: "text", text: "one" }, { type: "text", text: "two" }] })[0].text,
        }));
        '''
    )
    assert result["user"] == [{"kind": "user", "text": "why is the renderer empty"}]
    assert result["userText"] == [{"kind": "user", "text": "plain text prompt"}]
    assert result["thinking"] == [{"kind": "thinking", "text": "checking the composer\nand more"}]
    assert result["tool"] == [{"kind": "tool", "text": "bash: pnpm test"}]
    assert result["assistant"] == [{"kind": "assistant", "text": "the composer never ran"}]
    assert result["result"] == [{"kind": "result", "text": "first line\nsecond line", "toolName": "bash"}]
    assert result["empty"] == []
    assert result["unmapped"] == []
    assert result["goal"] == "read the layout"
    assert result["notGoal"] == ""
    assert result["readPath"] == "read: /a/b/index.ts"
    assert result["query"] == "search: index"
    assert result["bare"] == "work"
    assert result["bounded"] == 200
    # An assistant reply keeps its line structure and its text parts are one body.
    assert result["assistantBody"] == "a\nb"
    assert result["assistantParts"] == "one\n\ntwo"


def test_events_carry_the_call_identity_and_error_pi_recorded() -> None:
    result = report(
        r'''
        import { eventsFromMessage, boundSessionEvent } from "./packages/open-deskos/src/events.ts";
        console.log(JSON.stringify({
          call: eventsFromMessage({ role: "assistant", content: [{ type: "toolCall", id: "call_1", name: "bash", arguments: { command: "pnpm test" } }] }),
          callWithoutId: eventsFromMessage({ role: "assistant", content: [{ type: "toolCall", name: "bash", arguments: { command: "pnpm test" } }] }),
          failed: eventsFromMessage({ role: "toolResult", toolName: "bash", toolCallId: "call_1", isError: true, content: [{ type: "text", text: "exit code 1" }] }),
          passed: eventsFromMessage({ role: "toolResult", toolName: "bash", toolCallId: "call_1", content: [{ type: "text", text: "ok" }] }),
          identityOnly: eventsFromMessage({ role: "toolResult", toolCallId: "call_2", content: [{ type: "text", text: "ok" }] }),
          kept: boundSessionEvent({ kind: "result", text: "body", toolName: "bash", toolCallId: "call_3", isError: true }),
          notOnOtherKinds: boundSessionEvent({ kind: "assistant", text: "body", toolCallId: "call_4", isError: true }),
          noErrorFlag: boundSessionEvent({ kind: "result", text: "body", isError: false }),
        }));
        '''
    )
    # A desk reads one tool box and the outcome Pi recorded from these two fields,
    # so both travel with the event instead of being inferred from its position.
    assert result["call"] == [{"kind": "tool", "text": "bash: pnpm test", "toolCallId": "call_1"}]
    assert result["callWithoutId"] == [{"kind": "tool", "text": "bash: pnpm test"}]
    assert result["failed"] == [{"kind": "result", "text": "exit code 1", "toolName": "bash", "toolCallId": "call_1", "isError": True}]
    assert result["passed"] == [{"kind": "result", "text": "ok", "toolName": "bash", "toolCallId": "call_1"}]
    assert result["identityOnly"] == [{"kind": "result", "text": "ok", "toolCallId": "call_2"}]
    # The reporter bounds every event, so both fields survive that bound, and
    # neither is invented for a kind that cannot carry it.
    assert result["kept"] == {"kind": "result", "text": "body", "toolName": "bash", "toolCallId": "call_3", "isError": True}
    assert result["notOnOtherKinds"] == {"kind": "assistant", "text": "body"}
    assert result["noErrorFlag"] == {"kind": "result", "text": "body"}


# ─ Reporter contract ───────────────────────────────────────────────

HARNESS = r'''
import { DeskReporter } from "./packages/open-deskos/src/reporter.ts";

const config = { machine: "desk-mac", host: "127.0.0.1", port: 1, token: "t" };

function harness() {
  const transports = [];
  const waits = [];
  const timers = [];
  return {
    transports, waits, timers,
    create(config) {
      let open, close, record;
      const sent = [];
      const transport = {
        sent,
        open() { open?.(); },
        dropFromService(reason) { close?.(reason); },
        deliver(value) { record?.(value); },
        impl: {
          send(value) { sent.push(value); },
          close() { close?.("closed by reporter"); },
          onOpen(handler) { open = handler; },
          onClose(handler) { close = handler; },
          onRecord(handler) { record = handler; },
        },
      };
      transports.push(transport);
      return transport.impl;
    },
    schedule(run, delayMs) { waits.push(delayMs); timers.push(run); },
  };
}

function events(count, text = "step") {
  return Array.from({ length: count }, (_, index) => ({ kind: "tool", text: `${text} ${index}` }));
}

export function scenario(name) {
  const h = harness();
  const reporter = new DeskReporter({ config, createTransport: h.create, now: () => 1700000000000, schedule: h.schedule });
  const reports = { name, h, reporter };
  return reports;
}
console.log(JSON.stringify({ ready: true }));
'''

def test_a_configured_reporter_opens_one_link_and_reports_its_session() -> None:
    result = report(
        HARNESS
        + r'''
        const h = harness();
        const reporter = new DeskReporter({ config, createTransport: h.create, now: () => 1700000000000, schedule: h.schedule });
        reporter.recordSession({ sessionId: "s1", cwd: "/w/desk", workspaceName: "desk", status: "running", startedAt: 1699999000000 });
        const beforeStart = h.transports.length;
        reporter.start();
        const connecting = reporter.snapshot().link;
        h.transports[0].open();
        reporter.recordEvents("s1", [{ kind: "tool", text: "bash: pnpm test" }]);
        console.log(JSON.stringify({
          beforeStart,
          connecting,
          link: reporter.snapshot().link,
          transports: h.transports.length,
          records: h.transports[0].sent.map((record) => record.type),
          hello: h.transports[0].sent[0],
          sessions: h.transports[0].sent.find((record) => record.type === "sessions").sessions,
        }));
        '''
    )
    assert result["beforeStart"] == 0, "an unstarted reporter must not connect"
    assert result["connecting"] == "connecting"
    assert result["link"] == "connected"
    assert result["transports"] == 1, "one link at a time"
    assert result["records"] == ["hello", "sessions", "events"], "identity travels once, then events are append-only"
    assert result["hello"] == {"v": 1, "type": "hello", "machine": "desk-mac", "token": "t"}
    reported = result["sessions"][0]
    assert reported["sessionId"] == "s1"
    assert reported["cwd"] == "/w/desk"
    assert reported["status"] == "running"


def test_reported_events_obey_the_local_bounds() -> None:
    result = report(
        HARNESS
        + r'''
        const h = harness();
        const reporter = new DeskReporter({ config, createTransport: h.create, now: () => 1700000000000, schedule: h.schedule });
        reporter.recordSession({ sessionId: "s1", cwd: "/w", workspaceName: "w", status: "running", startedAt: 1 });
        reporter.start();
        h.transports[0].open();
        reporter.recordEvents("s1", events(70));
        reporter.recordEvents("s1", [{ kind: "result", text: "line one\nline two\n" + "z".repeat(500) }]);
        const wire = h.transports[0].sent.filter((record) => record.type === "events");
        const last = wire[wire.length - 1];
        console.log(JSON.stringify({
          retained: reporter.eventsFor("s1").length,
          lastBatch: last.events.length,
          wireMax: Math.max(...wire.flatMap((record) => record.events.filter((event) => event.kind !== "result").map((event) => event.text.length))),
          multiline: wire.flatMap((record) => record.events).some((event) => event.text.includes("\n")),
          oldest: reporter.eventsFor("s1")[0].text,
          lastStep: reporter.eventsFor("s1")[58].text,
          newest: reporter.eventsFor("s1")[59].text,
          resultText: last.events[last.events.length - 1].text,
        }));
        '''
    )
    assert result["retained"] == 71, "all events within the raised count and byte bounds are retained"
    assert result["wireMax"] <= 4096, "tool events obey their per-kind byte bound"
    assert result["multiline"] is True, "event Markdown preserves newlines"
    assert result["oldest"] == "step 0"
    assert result["lastStep"] == "step 58"
    assert result["newest"] == "step 59"
    assert result["resultText"] == "line one\nline two\n" + "z" * 500, "the complete bounded result body crosses the wire"


def test_an_outage_bounds_what_the_reporter_retains_and_replays() -> None:
    result = report(
        HARNESS
        + r'''
        const h = harness();
        const reporter = new DeskReporter({ config, createTransport: h.create, now: () => 1700000000000, schedule: h.schedule });
        reporter.recordSession({ sessionId: "s1", cwd: "/w", workspaceName: "w", status: "running", startedAt: 1 });
        reporter.start();
        h.transports[0].open();
        h.transports[0].dropFromService("peer went away");
        for (let round = 0; round < 5; round += 1) reporter.recordEvents("s1", events(70, `offline-${round}`));
        const offline = { state: reporter.snapshot(), sent: h.transports[0].sent.length };
        h.timers[0]();
        h.transports[1].open();
        const wire = h.transports[1].sent.filter((record) => record.type === "events");
        console.log(JSON.stringify({
          link: offline.state.link,
          lastError: offline.state.lastError,
          retained: offline.state.events,
          sentWhileOffline: offline.sent,
          replayedBatches: wire.length,
          replayedEvents: wire.flatMap((record) => record.events).length,
          snapshotCount: h.transports[1].sent.filter((record) => record.type === "sessions").length,
        }));
        '''
    )
    assert result["link"] == "offline"
    assert result["lastError"] == "peer went away"
    assert result["retained"] == 300, "an outage never grows retained events past the raised bound"
    assert result["sentWhileOffline"] == 2, "nothing is written to a dropped link"
    assert result["replayedBatches"] == 1, "a reconnect replays one bounded batch, not five"
    assert result["replayedEvents"] == 300
    assert result["snapshotCount"] == 1, "exactly one snapshot is held and sent on reconnect"


def test_a_dropped_link_reconnects_with_a_growing_capped_wait() -> None:
    result = report(
        HARNESS
        + r'''
        const h = harness();
        const reporter = new DeskReporter({ config, createTransport: h.create, now: () => 1700000000000, schedule: h.schedule });
        reporter.start();
        for (let attempt = 0; attempt < 9; attempt += 1) {
          h.transports[attempt].dropFromService("gone");
          h.timers[attempt]();
        }
        const afterDrops = reporter.snapshot();
        const opensPerDrop = h.transports.length - 1;
        console.log(JSON.stringify({
          waits: h.waits,
          attempts: afterDrops.attempts,
          opensPerDrop,
          oneAtATime: opensPerDrop === 9,
          cappedAt: Math.max(...h.waits),
        }));
        '''
    )
    waits = result["waits"]
    assert waits[:5] == [1000, 2000, 4000, 8000, 16000], f"the wait must grow: {waits}"
    assert waits == sorted(waits), "the wait never shrinks"
    assert result["cappedAt"] == 30000, "the wait never exceeds the maximum"
    assert result["attempts"] == 9
    assert result["oneAtATime"] is True, "a scheduled reconnect opens exactly one link"


def test_a_reconnected_link_sends_current_state_and_the_reporter_stops_cleanly() -> None:
    result = report(
        HARNESS
        + r'''
        const h = harness();
        const reporter = new DeskReporter({ config, createTransport: h.create, now: () => 1700000000000, schedule: h.schedule });
        reporter.recordSession({ sessionId: "s1", cwd: "/w", workspaceName: "w", status: "running", startedAt: 1 });
        reporter.start();
        h.transports[0].open();
        h.transports[0].dropFromService("gone");
        reporter.renameSession("s1", "desk work");
        reporter.recordSession({ sessionId: "s1", latestGoal: "read the layout" });
        h.timers[0]();
        h.transports[1].open();
        const sessions = h.transports[1].sent.find((record) => record.type === "sessions").sessions[0];
        reporter.markStatus("s1", "exited");
        reporter.stop();
        const types = h.transports[1].sent.map((record) => record.type);
        console.log(JSON.stringify({
          name: sessions.name,
          goal: sessions.latestGoal,
          workspace: sessions.workspaceName,
          startedAt: sessions.startedAt,
          types,
          afterStop: reporter.snapshot().link,
          sendsAfterStop: (() => { const before = h.transports[1].sent.length; reporter.recordEvents("s1", events(1)); return h.transports[1].sent.length === before; })(),
        }));
        '''
    )
    assert result["name"] == "desk work", "a rename survives the outage"
    assert result["goal"] == "read the layout"
    assert result["workspace"] == "w", "a later update never erases the workspace"
    assert result["startedAt"] == 1, "a later update never erases the start time"
    assert result["types"][-1] == "bye", "stopping closes the link politely"
    assert result["afterStop"] == "offline"
    assert result["sendsAfterStop"] is True, "a stopped reporter writes nothing"


# ── Extension wiring ────────────────────────────────────────────────

def test_an_unconfigured_machine_reports_nothing_but_says_why() -> None:
    result = report(
        r'''
        delete process.env.ODK_DESK_LINK_ADDRESS;
        delete process.env.ODK_DESK_LINK_TOKEN;
        const mod = await import("./packages/open-deskos/index.ts?unconfigured=2");
        const hooks = [];
        const handlers = new Map();
        const commands = new Map();
        const notices = [];
        const statuses = [];
        const pi = {
          on(name, handler) { hooks.push(name); handlers.set(name, handler); },
          registerCommand(name, options) { commands.set(name, options); },
          sendMessage() { throw new Error("an unconfigured reporter must not send a message"); },
        };
        mod.default(pi);
        const ctx = { cwd: "/w", ui: { notify(message, level) { notices.push([message, level]); }, setStatus(key, value) { statuses.push([key, value]); } } };
        handlers.get("session_start")?.({}, ctx);
        handlers.get("session_shutdown")?.({}, ctx);
        await commands.get("open-deskos")?.handler("", ctx);
        console.log(JSON.stringify({
          statuses,
          hooks,
          commands: [...commands.keys()],
          unseenHooks: hooks.filter((name) => name !== "session_start" && name !== "session_shutdown"),
          notices,
          describesTheGap: notices.some(([message]) => message.includes("ODK_DESK_LINK_ADDRESS") && message.includes("ODK_DESK_LINK_TOKEN")),
        }));
        '''
    )
    assert result["commands"] == ["open-deskos"], "an unconfigured machine must still be diagnosable"
    assert result["unseenHooks"] == [], "reporting hooks stay off while unconfigured"
    assert result["statuses"] == [], "unconfigured sessions must never set or clear footer status"
    assert result["hooks"] == [], "unconfigured sessions need no automatic UI hooks"
    assert result["describesTheGap"] is True, "the command must name the variables that are missing"


def test_a_configured_machine_registers_the_reporting_hooks() -> None:
    result = report(
        r'''
        process.env.ODK_DESK_LINK_ADDRESS = "127.0.0.1:1";
        process.env.ODK_DESK_LINK_TOKEN = "t";
        const mod = await import("./packages/open-deskos/index.ts?configured=2");
        const hooks = [];
        const commands = [];
        const pi = {
          on(name, handler) { hooks.push(name); },
          registerCommand(name) { commands.push(name); },
          sendMessage() { throw new Error("the reporter must never send a message"); },
          setActiveTools() { throw new Error("the reporter must never change the active tools"); },
        };
        mod.default(pi);
        console.log(JSON.stringify({ hooks, commands }));
        '''
    )
    assert result["hooks"] == ["session_start", "session_info_changed", "agent_start", "agent_settled", "message_end", "session_shutdown"]
    assert result["commands"] == ["open-deskos"]


def test_the_reporter_never_acts_inside_the_session() -> None:
    result = report(
        r'''
        import fs from "node:fs";
        const source = fs.readFileSync("./packages/open-deskos/src/index.ts", "utf8");
        const reporter = fs.readFileSync("./packages/open-deskos/src/reporter.ts", "utf8");
        const transport = fs.readFileSync("./packages/open-deskos/src/transport.ts", "utf8");
        const forbidden = ["sendMessage", "setActiveTools", "abort(", "shutdown(", "deliverAs"];
        console.log(JSON.stringify({
          used: forbidden.filter((name) => source.includes(name)),
          writesOnly: ["hello", "sessions", "events", "bye"].every((type) => reporter.includes(`"${type}"`)),
          noPromptRecord: !transport.includes("prompt"),
        }));
        '''
    )
    assert result["used"] == [], "the extension must not steer, abort, or shut down the session"
    assert result["writesOnly"] is True
    assert result["noPromptRecord"] is True, "v1 is report-only"

def test_only_a_service_ack_resets_the_reconnect_wait() -> None:
    result = report(
        HARNESS
        + r'''
        const refused = harness();
        const refusedReporter = new DeskReporter({ config, createTransport: refused.create, now: () => 1700000000000, schedule: refused.schedule });
        refusedReporter.start();
        for (let attempt = 0; attempt < 3; attempt += 1) {
          refused.transports[attempt].open();
          refused.transports[attempt].dropFromService("token refused");
          refused.timers[attempt]();
        }
        const accepted = harness();
        const acceptedReporter = new DeskReporter({ config, createTransport: accepted.create, now: () => 1700000000000, schedule: accepted.schedule });
        acceptedReporter.start();
        accepted.transports[0].open();
        accepted.transports[0].deliver({ v: 1, type: "ack", at: 1700000000000 });
        accepted.transports[0].dropFromService("gone");
        accepted.timers[0]();
        accepted.transports[1].open();
        accepted.transports[1].deliver({ v: 1, type: "ack", at: 1700000000000 });
        accepted.transports[1].dropFromService("gone");
        console.log(JSON.stringify({ refusedWaits: refused.waits.slice(0, 3), acceptedWaits: accepted.waits.slice(0, 2) }));
        '''
    )
    assert result["refusedWaits"] == [1000, 2000, 4000], "a refused token must back off, not retry at a fixed rate"
    assert result["acceptedWaits"] == [1000, 1000], "an accepted link resets the wait"


def test_the_reported_session_set_stays_bounded() -> None:
    result = report(
        HARNESS
        + r'''
        const h = harness();
        const reporter = new DeskReporter({ config, createTransport: h.create, now: () => 1700000000000, schedule: h.schedule });
        reporter.start();
        h.transports[0].open();
        for (let index = 0; index < 90; index += 1) {
          reporter.recordSession({ sessionId: `s${index}`, cwd: "/w", workspaceName: "w", status: index === 89 ? "running" : "settled", startedAt: index });
        }
        const snapshot = reporter.snapshot();
        const latest = h.transports[0].sent.filter((record) => record.type === "sessions").slice(-1)[0];
        console.log(JSON.stringify({ sessions: snapshot.sessions, wire: latest.sessions.length, keepsNewest: latest.sessions.some((session) => session.sessionId === "s89") }));
        '''
    )
    assert result["sessions"] == 64, "a process cannot report unbounded sessions"
    assert result["wire"] == 64
    assert result["keepsNewest"] is True


def test_a_session_switch_keeps_reporting() -> None:
    result = report(
        r'''
        import net from "node:net";
        const received = [];
        const peers = [];
        const server = net.createServer((socket) => {
          peers.push(socket);
          socket.on("data", (chunk) => {
            for (const line of chunk.toString("utf8").split("\n")) if (line.trim()) received.push(JSON.parse(line));
          });
        });
        await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
        process.env.ODK_DESK_LINK_ADDRESS = `127.0.0.1:${server.address().port}`;
        process.env.ODK_DESK_LINK_TOKEN = "t";
        process.env.ODK_DESK_LINK_MACHINE = "probe";
        const mod = await import("./packages/open-deskos/index.ts?switch=1");
        const handlers = new Map();
        mod.default({ on(name, handler) { handlers.set(name, handler); }, registerCommand() {} });
        const statuses = [];
        const contextFor = (id) => ({ cwd: "/w/probe", isIdle: () => false, ui: { setStatus(...args) { statuses.push(args); }, notify() {} }, sessionManager: { getSessionId: () => id, getSessionName: () => undefined, getHeader: () => undefined } });
        handlers.get("session_start")({ type: "session_start" }, contextFor("first"));
        await new Promise((resolve) => setTimeout(resolve, 200));
        handlers.get("session_shutdown")({ type: "session_shutdown" }, contextFor("first"));
        await new Promise((resolve) => setTimeout(resolve, 200));
        handlers.get("session_start")({ type: "session_start" }, contextFor("second"));
        await new Promise((resolve) => setTimeout(resolve, 300));
        const sessionsRecords = received.filter((record) => record.type === "sessions");
        const last = sessionsRecords.at(-1)?.sessions ?? [];
        // Release every handle so the harness process exits on its own.
        for (const peer of peers) peer.destroy();
        server.close();
        console.log(JSON.stringify({
          statuses,
          allReported: [...new Set(sessionsRecords.flatMap((record) => record.sessions.map((session) => session.sessionId)))],
          lastRunning: last.filter((session) => session.status === "running").map((session) => session.sessionId),
          lastExited: last.filter((session) => session.status === "exited").map((session) => session.sessionId),
          hellos: received.filter((record) => record.type === "hello").length,
          byes: received.filter((record) => record.type === "bye").length,
        }));
        '''
    )
    assert result["statuses"] == [], "session switches must not write footer status"
    assert result["allReported"] == ["first", "second"], "Pi switches sessions inside one process, so reporting must continue"
    assert result["lastRunning"] == ["second"], "the session after the switch is the running one"
    assert result["lastExited"] == ["first"], "the switched-away session is reported exited, not forgotten"
    assert result["hellos"] == 2, "the second session opens its own link"
    assert result["byes"] == 1, "the switch closes the link politely"

def test_link_transitions_notify_so_a_surface_cannot_show_a_stale_state() -> None:
    result = report(
        HARNESS
        + r'''
        const h = harness();
        const seen = [];
        const reporter = new DeskReporter({ config, createTransport: h.create, now: () => 1700000000000, schedule: h.schedule, onChange: (state) => seen.push(state.link) });
        reporter.start();
        h.transports[0].open();
        h.transports[0].dropFromService("gone");
        reporter.stop();
        console.log(JSON.stringify({ seen }));
        '''
    )
    assert result["seen"] == ["connecting", "connected", "offline", "offline"], (
        "every transition must be announced, including the drop while idle"
    )
