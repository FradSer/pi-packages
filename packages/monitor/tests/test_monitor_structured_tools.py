import subprocess
import tempfile
import textwrap
from pathlib import Path

from test_monitor_package import EXTENSION_HARNESS, REPO, run_harness


def run_native_harness(script: str) -> None:
    # File-based ESM keeps stdin-only --input-type out of Pi worker arguments.
    harness = EXTENSION_HARNESS.replace('"./packages/monitor/index.ts"',
        '"' + str(REPO / "packages/monitor/index.ts") + '"')
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mts", prefix="codemode-",
        dir=Path(__file__).parent, delete=False) as fixture:
        fixture.write(harness + "\n" + textwrap.dedent(script))
        path = Path(fixture.name)
    try:
        result = subprocess.run(["node", "--import", "tsx", str(path)], cwd=REPO,
            text=True, capture_output=True, timeout=30, check=False)
        assert result.returncode == 0, f"Native Pi codemode check failed:\n{result.stderr}\n{result.stdout}"
    finally:
        path.unlink()


def test_native_codemode_consumes_structured_terminal_json() -> None:
    run_native_harness(r'''
        const { executeCodemode } = await import(new URL("./extensions/codemode/execute.js",
          import.meta.resolve("@earendil-works/pi-coding-agent")));
        const { runToolCall } = await import(new URL("../../pi-agent-core/dist/agent-loop.js",
          import.meta.resolve("@earendil-works/pi-coding-agent")));
        const assistantMessage = { role: "assistant", content: [{ type: "toolCall", id: "script",
          name: "codemode", arguments: {} }] };
        const branch = [{ type: "message", message: assistantMessage }];
        const context = ctx({ sessionManager: { getBranch: () => branch }, tools: [start] });
        let calls = 0;
        context.executeTool = (name, args, options) => runToolCall({ type: "toolCall", id: `script/${++calls}`,
          name, arguments: args }, { assistantMessage, context: { messages: [assistantMessage], tools: [start] },
          tools: [{ ...start, execute: (id, params, signal, update) => start.execute(id, params, signal, update, context) }],
          signal: options.signal });
        try {
          const parameters = { command: "printf 'DONE {\"count\":7}\\n'", result_pattern: "DONE (?<json>.*)" };
          const primitives = [false, null, 0].map(value => ({ value,
            args: { command: `printf 'DONE ${JSON.stringify(value)}\\n'`, result_pattern: "DONE (?<json>.*)" } }));
          const result = await executeCodemode("script", { code: `
            const terminal = await tools.monitor_start(${JSON.stringify(parameters)});
            if (terminal.status !== 'success' || terminal.result.result.count !== 7)
              throw new Error('missing typed monitor outcome');
            text({ status: terminal.status, count: terminal.result.result.count, monitorId: terminal.monitorId });
            for (const fixture of ${JSON.stringify(primitives)}) {
              const value = await tools.monitor_start(fixture.args);
              if (value.result.result !== fixture.value) throw new Error('JSON primitive lost');
            }
          ` }, undefined, undefined, context);
          assert.equal(result.isError, undefined, JSON.stringify(result));
          const output = result.content.filter(block => block.type === "text").map(block => block.text).join("\n");
          assert.match(output, /"count":7/, output);
          assert.match(output, /"status":"success"/, output);
          assert.equal(calls, 4);
          assert.equal(sent.length, 0);
        } finally { await shutdown(); }
    ''')


def test_structured_pending_terminal_and_stop_follow_declared_schemas() -> None:
    run_harness(r'''
        const { Value } = await import("typebox/value");
        try {
          const pending = await start.execute("pending", { command: "sleep 5", result_pattern: "NEVER" },
            undefined, undefined, ctx());
          assert.equal(pending.structuredContent?.status, "running");
          assert.equal(pending.structuredContent.monitorId, pending.details.monitorId);
          assert.equal(Value.Check(start.outputSchema, pending.structuredContent), true);
          const stopped = await stop.execute("stop", { monitor_id: pending.details.monitorId });
          assert.deepEqual(stopped.structuredContent, { stopped: 1 });
          assert.equal(Value.Check(stop.outputSchema, stopped.structuredContent), true);
          const terminal = await start.execute("bad-json", { command: "printf 'DONE {bad}\\n'", result_pattern: "DONE (?<json>.*)" },
            undefined, undefined, ctx({ mode: "print", hasUI: false }));
          assert.equal(terminal.structuredContent.status, "success");
          assert.equal(terminal.structuredContent.result.captures.json, "{bad}");
          assert.ok(terminal.structuredContent.result.resultParseError);
          assert.equal(Value.Check(start.outputSchema, terminal.structuredContent), true);
          assert.match(terminal.content[0].text, /result_parse_error=/);
        } finally { await shutdown(); }
    ''')


def test_preaborted_tool_does_not_start_command() -> None:
    run_harness(r'''
        const { mkdtempSync, rmSync } = await import("node:fs");
        const { tmpdir } = await import("node:os");
        const { join } = await import("node:path");
        const directory = mkdtempSync(join(tmpdir(), "monitor-cancel-"));
        const marker = join(directory, "marker");
        const controller = new AbortController();
        controller.abort();
        try {
          await fire("session_start");
          await assert.rejects(() => start.execute("cancelled", { command: `touch '${marker}'`, result_pattern: "NEVER" },
            controller.signal, undefined, ctx()), { name: "AbortError" });
          await new Promise(resolve => setTimeout(resolve, 150));
          assert.equal(existsSync(marker), false);
          assert.equal(sent.length, 0);
          assert.equal(activeTools.includes("monitor_stop"), false);
        } finally { await shutdown(); rmSync(directory, { recursive: true, force: true }); }
    ''')


def test_nested_abort_stops_command_but_acknowledged_background_survives() -> None:
    run_harness(r'''
        const { mkdtempSync, rmSync } = await import("node:fs");
        const { tmpdir } = await import("node:os");
        const { join } = await import("node:path");
        const directory = mkdtempSync(join(tmpdir(), "monitor-nested-cancel-"));
        const marker = join(directory, "marker");
        const controller = new AbortController();
        const context = ctx({ sessionManager: { getBranch: () => [{ type: "message", message: { role: "assistant",
          content: [{ type: "toolCall", id: "parent", name: "codemode", arguments: {} }] } }] } });
        try {
          const waiting = start.execute("parent/1", { command: `sleep 0.5; touch '${marker}'; printf DONE`, result_pattern: "DONE" },
            controller.signal, undefined, context);
          setTimeout(() => controller.abort(), 50);
          await assert.rejects(waiting, { name: "AbortError" });
          await new Promise(resolve => setTimeout(resolve, 700));
          assert.equal(existsSync(marker), false);
          assert.equal(sent.length, 0);
          const backgroundController = new AbortController();
          const acknowledged = await start.execute("background", { command: "sleep 0.2; printf DONE", result_pattern: "DONE" },
            backgroundController.signal, undefined, ctx());
          assert.equal(acknowledged.terminate, true);
          backgroundController.abort();
          const deadline = Date.now() + 3000;
          while (sent.length === 0 && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 20));
          assert.equal(sent.length, 1);
          assert.equal(sent[0].message.details.result.status, "success");
        } finally { await shutdown(); rmSync(directory, { recursive: true, force: true }); }
    ''')


def test_failed_tool_renderers_preserve_errors() -> None:
    run_harness(r'''
        try {
          for (const tool of [start, stop]) {
            const error = { content: [{ type: "text", text: "EXPLICIT_TOOL_FAILURE" }], details: {} };
            const rendered = paint(tool.renderResult(error, { expanded: true, isPartial: false }, theme,
              { args: {}, toolCallId: "failed", isError: true })).join("\n");
            assert.match(rendered, /EXPLICIT_TOOL_FAILURE/, rendered);
            assert.match(rendered, /failed/, rendered);
            assert.ok(!rendered.includes("started"), rendered);
          }
        } finally { await shutdown(); }
    ''')


def test_matcher_startup_failure_returns_terminal_instead_of_pending() -> None:
    run_harness(r'''
        const threads = (await import("node:worker_threads")).default;
        const { syncBuiltinESMExports } = await import("node:module");
        const originalWorker = threads.Worker;
        threads.Worker = class { constructor() { throw new Error("WORKER_STARTUP_FAILURE"); } };
        syncBuiltinESMExports();
        const context = ctx({ sessionManager: { getBranch: () => [{ type: "message", message: { role: "assistant",
          content: [{ type: "toolCall", id: "standalone", name: "monitor_start", arguments: {} }] } }] } });
        try {
          const result = await start.execute("standalone", { command: "sleep 5", result_pattern: "DONE" },
            undefined, undefined, context);
          assert.equal(result.structuredContent.status, "failure");
          assert.equal(result.details.result.status, "failure");
          assert.match(result.details.result.reason, /WORKER_STARTUP_FAILURE/);
          assert.notEqual(result.terminate, true);
          assert.match(result.content[0].text, /status=failure/);
          assert.ok(!result.content[0].text.includes("terminal_result=pending"));
          assert.equal(sent.length, 0);
          const rendered = paint(start.renderResult(result, { expanded: true, isPartial: false }, theme,
            { args: {}, toolCallId: "standalone", isError: false })).join("\n");
          assert.match(rendered, /failure/);
          assert.match(rendered, /WORKER_STARTUP_FAILURE/);
        } finally {
          threads.Worker = originalWorker;
          syncBuiltinESMExports();
          await shutdown();
        }
    ''')
