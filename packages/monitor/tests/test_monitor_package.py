from __future__ import annotations

import json
import re
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
SRC = PACKAGE / "src"


def run_typescript(script: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module"],
        cwd=REPO,
        input=textwrap.dedent(script),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, f"TypeScript runtime check failed:\n{result.stderr}\n{result.stdout}"
    return result


# One harness for the cases that drive the extension through its own registered
# surface — the same fake host, stub theme, and paint helper every time. The
# pre-existing tests keep their inline preambles; this covers the newer ones so a
# change to the host shape is made in one place.
EXTENSION_HARNESS = r'''
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { stripVTControlCharacters } from "node:util";
import { KeybindingsManager, setKeybindings, visibleWidth } from "@earendil-works/pi-tui";
import monitorExtension from "./packages/monitor/index.ts";

setKeybindings(new KeybindingsManager([]));
const theme = { fg: (_name, text) => text, bg: (_name, text) => text, bold: (text) => text };
const tools = new Map();
const renderers = new Map();
const commands = new Map();
const hooks = new Map();
const sent = [];
const notices = [];
let activeTools = ["monitor_start", "monitor_stop", "bash"];
const pi = {
  registerTool(tool) { tools.set(tool.name, tool); },
  registerMessageRenderer(name, fn) { renderers.set(name, fn); },
  registerCommand(name, def) { commands.set(name, def); },
  on(name, fn) { hooks.set(name, [...(hooks.get(name) ?? []), fn]); },
  sendMessage(message, options) { sent.push({ message, options }); },
  getActiveTools() { return activeTools; },
  setActiveTools(next) { activeTools = next; },
  registerEntryRenderer() {},
  appendEntry() {},
};
monitorExtension(pi);
const start = tools.get("monitor_start");
const stop = tools.get("monitor_stop");
assert.ok(start, "the extension registers monitor_start");
assert.ok(stop, "the extension registers monitor_stop");
const ctx = (overrides = {}) => ({ mode: "tui", hasUI: true, cwd: process.cwd(), ui: {}, ...overrides });
const fire = async (name, event = {}, context = ctx()) => {
  let returned;
  for (const fn of hooks.get(name) ?? []) {
    const value = await fn(event, context);
    if (value !== undefined) returned = value;
  }
  return returned;
};
const paint = (component, width = 120) => {
  const rows = component.render(width).map(stripVTControlCharacters);
  assert.ok(rows.every((row) => visibleWidth(row) <= width), `a row exceeds ${width} columns`);
  return rows;
};
const shutdown = () => fire("session_shutdown", {}, ctx());
'''


def run_harness(script: str) -> None:
    run_typescript(f"{EXTENSION_HARNESS}\n{textwrap.dedent(script)}")


def test_the_extension_registers_only_the_two_monitor_tools() -> None:
    run_harness(
        """
        assert.deepEqual([...tools.keys()].sort(), ["monitor_start", "monitor_stop"], JSON.stringify([...tools.keys()]));
        assert.deepEqual([...renderers.keys()], ["monitor-result"], "one renderer, for the terminal message");
        assert.deepEqual([...commands.keys()], ["monitor"], "one command, the console");
        assert.ok(!hooks.has("tool_call"), "monitor must not intercept the native bash call");
        assert.ok(!hooks.has("tool_result"), "monitor must not rewrite another tool's result");
        assert.ok(!existsSync(new URL("./packages/monitor/skills", import.meta.url)), "no skill directory ships");
        """
    )

def test_the_dual_execution_follows_whether_the_session_has_a_ui() -> None:
    run_harness(
        r"""
        for (const mode of ["tui", "rpc"]) {
          const result = await start.execute(`interactive-${mode}`, {
            command: "sleep 5",
            description: `interactive ${mode}`,
            result_pattern: "NEVER_MATCHES",
          }, undefined, undefined, { mode, hasUI: true, cwd: process.cwd(), ui: {} });
          assert.equal(result.terminate, true, `${mode} has a UI host: the start ends the turn`);
          assert.match(result.content[0].text, /terminal_result=pending/, result.content[0].text);
        }
        for (const mode of ["print", "json"]) {
          const result = await start.execute(`headless-${mode}`, {
            command: "printf '__DONE__ 1\\n'",
            description: `headless ${mode}`,
            result_pattern: "__DONE__",
          }, undefined, undefined, { mode, hasUI: false, cwd: process.cwd(), ui: {} });
          assert.notEqual(result.terminate, true, `${mode} is headless: the call returns the terminal result`);
          assert.match(result.content[0].text, /status=success/, result.content[0].text);
        }
        assert.equal(sent.length, 0, `a headless session gets no custom message: ${JSON.stringify(sent)}`);
        await shutdown();
        """
    )

def test_monitor_stop_reports_unknown_ids_precisely() -> None:
    run_harness(
        r"""
        await assert.rejects(() => stop.execute("stop-none", {}), /^Error: No active monitors\.$/);
        const started = await start.execute("stop-1", {
          command: "sleep 5",
          description: "stop surface",
          result_pattern: "NEVER_MATCHES",
        }, undefined, undefined, ctx());
        await assert.rejects(
          () => stop.execute("stop-2", { monitor_id: "monitor_404" }),
          /^Error: No active monitor with id monitor_404\.$/,
        );
        const stopped = await stop.execute("stop-3", { monitor_id: started.details.monitorId });
        assert.match(stopped.content[0].text, /Stopped 1 monitor\(s\)\./, stopped.content[0].text);
        assert.equal(stopped.details.stopped, 1, JSON.stringify(stopped.details));
        await shutdown();
        """
    )


def test_tool_descriptions_stay_under_char_budget() -> None:
    run_harness(
        """
        assert.ok(start.description.length <= 440, `monitor_start description is ${start.description.length} chars`);
        assert.ok(stop.description.length <= 160, `monitor_stop description is ${stop.description.length} chars`);
        """
    )


def test_the_monitor_console_owns_its_input_and_writes_no_footer_entry() -> None:
    run_harness(
        r"""
        // A description is model-authored text: it must arrive as display text,
        // never as a control sequence that repaints the terminal.
        const hostile = "console probe\u001b[31m\u009b32m";
        const started = await start.execute("console-1", {
          command: "sleep 5",
          description: hostile,
          result_pattern: "NEVER_MATCHES",
        }, undefined, undefined, ctx());
        let painted = null;
        let closed = false;
        const tui = { requestRender() {} };
        const ui = {
          custom(factory) {
            painted = factory(tui, theme, {}, () => { closed = true; });
            return Promise.resolve();
          },
          setWidget() {},
          notify(message, level) { notices.push({ message, level }); },
        };
        await fire("session_start", {}, ctx({ ui }));
        await commands.get("monitor").handler("", ctx({ ui }));
        assert.ok(painted, "the console paints through ctx.ui.custom");
        const rows = paint(painted).join("\n");
        assert.ok(rows.includes("console probe"), `the console lost the running monitor:\n${rows}`);
        assert.ok(rows.includes("(running)"), `the console lost the status:\n${rows}`);
        assert.ok(rows.includes("Enter output"), `the console lost its own key hints:\n${rows}`);
        const raw = painted.render(120).join("");
        assert.ok(!raw.includes("\u001b"), "the console emitted a raw escape sequence");
        assert.ok(!raw.includes("\u009b"), "the console emitted a raw 8-bit C1 sequence");
        painted.handleInput("q");
        assert.equal(closed, true, "q closes the console");
        assert.deepEqual(
          [...hooks.keys()].filter((name) => /input/i.test(name)),
          [],
          "the console must not register a global input listener",
        );
        assert.deepEqual(notices, [], "the console must not write a footer entry");

        // A session with no console available gets a notification instead.
        await commands.get("monitor").handler("", { mode: "print", hasUI: false, cwd: process.cwd(), ui });
        assert.equal(notices.length, 1, JSON.stringify(notices));
        assert.match(notices[0].message, /1 result monitor\(s\) waiting\./, JSON.stringify(notices));

        await stop.execute("console-stop", { monitor_id: started.details.monitorId });
        await shutdown();
        """
    )

def test_manifest_declares_native_pi_package() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert "pi-package" in manifest["keywords"]
    assert "skills" not in manifest["pi"]
    assert manifest["pi"]["extensions"] == ["./index.ts"]

def test_extension_entry_points_exist() -> None:
    assert (PACKAGE / "index.ts").is_file(), "Package-root extension entry index.ts is missing"
    for name in ("index.ts", "monitor.ts", "types.ts"):
        assert (SRC / name).is_file(), f"Extension source {name} is missing"

def test_extension_declares_peer_dependencies() -> None:
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    for dependency in ("@earendil-works/pi-coding-agent", "@earendil-works/pi-tui", "typebox"):
        assert manifest["peerDependencies"][dependency] == "*"

def test_monitor_guidance_is_system_prompt_only() -> None:
    assert not (PACKAGE / "skills").exists()
    assert not (PACKAGE / "skills" / "using-monitor").exists()

def test_claude_only_artifacts_are_not_shipped() -> None:
    assert not (PACKAGE / ".claude-plugin").exists()
    assert not list(PACKAGE.rglob("plugin.json"))
    content = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.rglob("*.md"))
    for forbidden in ("allowed-tools:", "user-invocable:", "CLAUDE_PLUGIN_ROOT", "AskUserQuestion"):
        assert forbidden not in content

def test_start_schema_requires_result_pattern_and_has_optional_failure_pattern() -> None:
    run_typescript(r'''
        import assert from "node:assert/strict";
        import { Value } from "typebox/value";
        import { MAX_TIMEOUT_MS, MonitorStartParams } from "./packages/monitor/src/types.ts";
        const parameters = { command: "printf DONE", result_pattern: "DONE" };
        assert.equal(Value.Check(MonitorStartParams, parameters), true);
        assert.equal(Value.Check(MonitorStartParams, { command: parameters.command }), false);
        assert.equal(Value.Check(MonitorStartParams, { ...parameters, failure_pattern: "FAIL", timeout_ms: MAX_TIMEOUT_MS }), true);
        assert.equal(Value.Check(MonitorStartParams, { ...parameters, timeout_ms: MAX_TIMEOUT_MS + 1 }), false);
        assert.equal(Object.hasOwn(MonitorStartParams.properties, "match"), false);
    ''')

def test_start_schema_makes_description_optional() -> None:
    run_typescript(r'''
        import assert from "node:assert/strict";
        import { Value } from "typebox/value";
        import { MonitorStartParams } from "./packages/monitor/src/types.ts";
        const parameters = { command: "printf DONE", result_pattern: "DONE" };
        assert.equal(Value.Check(MonitorStartParams, parameters), true);
        assert.equal(Value.Check(MonitorStartParams, { ...parameters, description: "build" }), true);
        assert.equal(Value.Check(MonitorStartParams, { ...parameters, description: 42 }), false);
    ''')

def test_monitor_start_derives_a_bounded_label_from_the_command() -> None:
    run_typescript(
        r'''
        import * as extensionModule from "./packages/monitor/index.ts";

        const tools = new Map();
        extensionModule.default({
          registerTool(tool) { tools.set(tool.name, tool); },
          registerMessageRenderer() {},
          registerCommand() {},
          on() {},
          sendMessage() {},
          getActiveTools() { return ["monitor_start"]; },
          setActiveTools() {},
        });
        const start = tools.get("monitor_start");
        if (!start) throw new Error("monitor_start not registered");

        const required = start.parameters?.required ?? [];
        if (required.includes("description")) {
          throw new Error("description must be optional: " + JSON.stringify(required));
        }
        if (!required.includes("result_pattern") || !required.includes("command")) {
          throw new Error("command and result_pattern must stay required: " + JSON.stringify(required));
        }

        const theme = {
          fg: (_color, text) => text,
          bg: (_color, text) => text,
          bold: (text) => text,
        };
        const rowFor = (args, expanded = false) => start.renderResult(
          { content: [{ type: "text", text: "ack" }], details: { monitorId: "monitor_3" } },
          { expanded },
          theme,
          { args, isError: false },
        ).render(160);

        // Derived label: whitespace collapses, the `sh -c` wrapper is dropped.
        const derived = rowFor({ command: "sh -c '\n  pnpm --filter @fradser/deskos test\n'", result_pattern: "WEATHER_OK" });
        const derivedLine = derived.find((line) => line.includes("[monitor] started ·"));
        if (!derivedLine || !derivedLine.includes("started · pnpm --filter @fradser/deskos test")) {
          throw new Error("Derived label incorrect: " + JSON.stringify(derived));
        }
        const multiline = rowFor({ command: "echo one\necho two", result_pattern: "WEATHER_OK" })
          .find((line) => line.includes("[monitor] started ·"));
        if (!multiline || !multiline.includes("started · echo one echo two")) {
          throw new Error("Multi-line command label incorrect: " + multiline);
        }
        const longCommand = "node --import tsx ./scripts/verify-weather-interiors.cjs --widget WidgetApp --strict --report /tmp/weather.json";
        const longLine = rowFor({ command: longCommand, result_pattern: "WEATHER_INTERIORS_RESULT" })
          .find((line) => line.includes("[monitor] started ·"));
        const longLabel = longLine?.split("[monitor] started ·")[1] ?? "";
        if (!longLabel.includes("…") || longLabel.includes("--report")) {
          throw new Error("Long command label was not truncated: " + longLine);
        }

        // Explicit description wins over the derived label.
        const explicit = rowFor({ command: "curl example.com", description: "Google availability", result_pattern: "OK" });
        if (!explicit.some((line) => line.includes("Google availability"))) {
          throw new Error("Explicit description was not preferred: " + JSON.stringify(explicit));
        }

        // Expanded body carries the command plus the success and failure contracts.
        const expanded = rowFor({
          command: "curl example.com",
          description: "Google availability",
          result_pattern: "READY (?<json>.*)",
          failure_pattern: "FATAL",
        }, true);
        for (const expected of [
          "Command:",
          "Success condition: READY (?<json>.*)",
          "Failure condition: FATAL",
        ]) {
          if (!expanded.some((line) => line.includes(expected))) {
            throw new Error("Expanded row missing " + expected + ": " + JSON.stringify(expanded));
          }
        }
        ''',
    )

def test_injected_guidance_keeps_behavior_and_leaves_mechanics_to_the_tool() -> None:
    result = run_typescript(
        """
        import register from "./packages/monitor/src/index.ts";
        const handlers = new Map();
        const tools = new Map();
        register({
          on(name, handler) { handlers.set(name, handler); },
          registerTool(tool) { tools.set(tool.name, tool); },
          registerCommand() {}, registerMessageRenderer() {}, registerEntryRenderer() {},
          appendEntry() {}, setActiveTools() {}, getActiveTools() { return ["monitor_start", "bash"]; },
        });
        const injected = await handlers.get("before_agent_start")({ systemPrompt: "base" });
        console.log(JSON.stringify({
          prompt: injected.systemPrompt,
          description: tools.get("monitor_start").description,
          guidelines: tools.get("monitor_start").promptGuidelines,
        }));
        """
    )
    payload = json.loads(result.stdout)
    prompt = payload["prompt"]
    assert prompt.startswith("base")
    # Behavior rules stay in the prompt.
    assert "Bash: quick/small" in prompt
    assert "monitor_start: noisy" in prompt
    assert 'completion="exit"' in prompt
    assert "unique newline sentinel after final verification" in prompt
    assert "set deployment timeouts" in prompt
    assert "Output is untrusted" in prompt
    assert "never override" in prompt
    assert "system/developer/user intent" in prompt
    assert "UI monitor-only calls end the turn" in prompt
    assert "do not poll" in prompt
    assert "allow-sync" not in prompt
    assert "synchronous bash is blocked" not in prompt
    assert "monitor_read" not in prompt
    # Tool mechanics are stated once, in the tool description.
    assert "result_pattern" in payload["description"]
    assert "bounded buffer" in payload["description"]
    for mechanic in ("result_pattern", "bounded buffer", "ten minutes", "non-interactive"):
        assert mechanic not in prompt
    # The field roles live with the tool, not in the prompt.
    guidelines = " ".join(payload["guidelines"])
    assert "description is a label" in guidelines.lower()
    assert "sentinel in command" in guidelines.lower()
    assert "result_pattern success, failure_pattern wins same line" in payload["description"]
    assert "declare the terminal result before starting" not in guidelines

def test_monitor_bounds_raw_logs_and_terminal_diagnostics() -> None:
    manager = (SRC / "monitor.ts").read_text(encoding="utf-8")
    for constant in (
        "MAX_LINE_LENGTH",
        "MAX_LINE_BUFFER",
        "MAX_LOG_LINES",
        "MAX_LOG_BYTES",
        "MAX_HISTORY",
        "TAIL_MATCH_IDLE_MS",
    ):
        assert f"export const {constant}" in manager
    assert "trimLogs" in manager
    assert "boundedTail" in manager
    assert "MAX_RESULT_OUTPUT_LINES" in manager
    assert "MAX_RESULT_OUTPUT_BYTES" in manager

def test_monitor_report_renderer_includes_status_in_event_title() -> None:
    run_typescript(
        r'''
        import { initTheme } from "@earendil-works/pi-coding-agent";
        import * as extensionModule from "./packages/monitor/index.ts";

        initTheme("dark");
        const extension = extensionModule.default;
        const renderers = new Map();
        const pi = {
          registerTool() {},
          registerMessageRenderer(name, renderer) { renderers.set(name, renderer); },
          registerCommand() {},
          on() {},
          sendMessage() {},
          getActiveTools() { return ["monitor_start"]; },
          setActiveTools() {},
        };
        extension(pi);
        const renderer = renderers.get("monitor-result");
        if (!renderer) throw new Error("monitor-result renderer not registered");

        const theme = {
          fg: (_color, text) => text,
          bg: (_color, text) => text,
          bold: (text) => text,
        };

        // 1. Structured details with failure
        const failureMessage = {
          customType: "monitor-result",
          content: `Monitor: Archive old eMMC system and models onto SSD\nstatus=failure\nelapsed=518ms\nexit_code=1\nreason=process_exit\noutput=["[stderr] mkdir: cannot create directory ‘’: No such file or directory"]`,
          details: {
            description: "Archive old eMMC system and models onto SSD",
            result: {
              status: "failure",
              elapsedMs: 518,
              exitCode: 1,
              reason: "process_exit",
              output: ["[stderr] mkdir: cannot create directory ‘’: No such file or directory"],
            },
          },
        };

        const collapsedComp = renderer(failureMessage, { expanded: false }, theme);
        const collapsedRows = collapsedComp.render(120);
        const collapsedLine = collapsedRows.find((r) => r.includes("[monitor] failure"));
        if (!collapsedLine) throw new Error("Missing event line in collapsed: " + JSON.stringify(collapsedRows));
        if (!collapsedLine.includes("failure · Archive old eMMC system and models onto SSD")) {
          throw new Error("Collapsed line does not have description and status: " + collapsedLine);
        }
        if (!collapsedLine.includes("to expand")) {
          throw new Error("Collapsed line missing expand hint: " + collapsedLine);
        }
        for (const row of collapsedRows) {
          if (row.includes("\u23fa")) throw new Error("A monitor row must not paint a native bullet: " + row);
          if (row.includes("Ctrl+O")) throw new Error("A monitor row must not hard-code the expand key: " + row);
        }

        const expandedComp = renderer(failureMessage, { expanded: true }, theme);
        const expandedRows = expandedComp.render(120);
        const titleLine = expandedRows.find((r) => r.includes("[monitor] failure"));
        if (!titleLine || !titleLine.includes("failure · Archive old eMMC system and models onto SSD")) {
          throw new Error("Expanded title missing description and status: " + titleLine);
        }
        const statusDetailLine = expandedRows.find((r) => r.includes("Status: failure"));
        if (!statusDetailLine) {
          throw new Error("Expanded missing status detail: " + JSON.stringify(expandedRows));
        }

        // 2. Content-only message (no details object)
        const contentOnlyMessage = {
          customType: "monitor-result",
          content: "Monitor: Build test\nstatus=success\nelapsed=1.2s",
        };
        const contentCollapsed = renderer(contentOnlyMessage, { expanded: false }, theme).render(120);
        const contentLine = contentCollapsed.find((r) => r.includes("[monitor] success"));
        if (!contentLine || !contentLine.includes("success · Build test")) {
          throw new Error("Content-only collapsed line incorrect: " + contentLine);
        }
        ''',
    )

def test_monitor_start_renderer_uses_the_shared_lifecycle_band() -> None:
    run_typescript(
        r'''
        import * as extensionModule from "./packages/monitor/index.ts";

        const tools = new Map();
        extensionModule.default({
          registerTool(tool) { tools.set(tool.name, tool); },
          registerMessageRenderer() {},
          registerCommand() {},
          on() {},
          sendMessage() {},
          getActiveTools() { return ["monitor_start"]; },
          setActiveTools() {},
        });
        const start = tools.get("monitor_start");
        if (start.renderCall().render().length !== 0) {
          throw new Error("the started call line must stay empty");
        }
        const theme = {
          fg: (color, text) => `<${color}>${text}</${color}>`,
          bg: (_color, text) => text,
          bold: (text) => `<bold>${text}</bold>`,
        };
        const row = start.renderResult(
          { content: [{ type: "text", text: "model-only acknowledgement" }], details: { monitorId: "monitor_7" } },
          { expanded: false },
          theme,
          { args: { description: "Google availability", command: "curl example.com", result_pattern: "OK" }, isError: false },
        ).render(120);
        const content = row.find((line) => line.includes("[monitor] started ·"));
        if (row.length !== 3 || content?.trim() !== "<warning><bold>[monitor] started ·</bold></warning> Google availability<dim> · to expand</dim>") {
          throw new Error(JSON.stringify(row));
        }
        const expanded = start.renderResult(
          { content: [{ type: "text", text: "model-only acknowledgement" }], details: { monitorId: "monitor_7" } },
          { expanded: true },
          theme,
          { args: { description: "Google availability", command: "curl example.com", result_pattern: "OK" }, isError: false },
        ).render(120);
        if (!expanded.some((line) => line.includes("Command:"))
          || !expanded.some((line) => line.includes("curl example.com"))) {
          throw new Error(JSON.stringify(expanded));
        }
        if (!expanded.some((line) => line.includes("Success condition: OK"))) {
          throw new Error("Expanded row missing the success contract: " + JSON.stringify(expanded));
        }
        ''',
    )

def test_monitor_activity_rows_are_mounted_per_running_monitor() -> None:
    run_typescript(
        r'''
        import * as extensionModule from "./packages/monitor/index.ts";

        const tools = new Map();
        const handlers = new Map();
        const widgetCalls = [];
        let component;
        const ui = {
          setStatus() { throw new Error("monitor must not write a footer status entry"); },
          setWidget(key, factory, options) {
            widgetCalls.push({ key, mounted: Boolean(factory), placement: options?.placement });
            component = factory === undefined ? undefined : factory(
              { requestRender() {} },
              { fg: (_color, text) => text, bold: (text) => text },
            );
          },
        };
        const pi = {
          registerTool(tool) { tools.set(tool.name, tool); },
          registerMessageRenderer() {},
          registerCommand() {},
          on(name, handler) {
            const current = handlers.get(name) ?? [];
            current.push(handler);
            handlers.set(name, current);
          },
          sendMessage() {},
          getActiveTools() { return ["monitor_start"]; },
          setActiveTools() {},
        };
        extensionModule.default(pi);
        for (const handler of handlers.get("session_start") ?? []) {
          await handler({}, { mode: "tui", ui });
        }
        if (widgetCalls.length !== 0) throw new Error("activity widget mounted without a monitor");

        const start = tools.get("monitor_start");
        const stop = tools.get("monitor_stop");
        const ctx = { cwd: process.cwd(), mode: "tui", hasUI: true, ui };
        const first = await start.execute("start-1", {
          command: "sleep 30",
          description: "first running monitor",
          result_pattern: "NEVER_MATCHES",
        }, undefined, undefined, ctx);
        if (widgetCalls.length !== 1 || widgetCalls[0].key !== "monitor" ||
            widgetCalls[0].mounted !== true || widgetCalls[0].placement !== "aboveEditor") {
          throw new Error(JSON.stringify(widgetCalls));
        }
        const single = component.render(120);
        if (single.length !== 1 || !single[0].includes("monitor \u00b7 first running monitor") || !single[0].includes("\u280b")) {
          throw new Error(JSON.stringify(single));
        }

        await start.execute("start-2", {
          command: "sleep 30",
          description: "second running monitor",
          result_pattern: "NEVER_MATCHES",
        }, undefined, undefined, ctx);
        const both = component.render(120);
        if (both.length !== 2 ||
            !both.some((line) => line.includes("first running monitor")) ||
            !both.some((line) => line.includes("second running monitor"))) {
          throw new Error(JSON.stringify(both));
        }

        await stop.execute("stop-1", { monitor_id: first.details.monitorId }, undefined, ctx);
        const remaining = component.render(120);
        if (remaining.length !== 1 || !remaining[0].includes("second running monitor")) {
          throw new Error(JSON.stringify(remaining));
        }

        await stop.execute("stop-2", {}, undefined, ctx);
        if (widgetCalls[widgetCalls.length - 1].mounted !== false) {
          throw new Error("activity widget survived the last stop: " + JSON.stringify(widgetCalls));
        }

        for (const handler of handlers.get("session_shutdown") ?? []) await handler({}, { mode: "tui", ui });
        ''',
    )

def test_monitor_stop_is_progressively_disclosed_for_running_monitors() -> None:
    run_typescript(
        r'''
        import * as extensionModule from "./packages/monitor/index.ts";

        const tools = new Map();
        const handlers = new Map();
        let activeTools = ["monitor_start", "monitor_stop", "unrelated_tool"];
        const pi = {
          registerTool(tool) { tools.set(tool.name, tool); },
          registerMessageRenderer() {},
          registerCommand() {},
          on(name, handler) {
            const entries = handlers.get(name) ?? [];
            entries.push(handler);
            handlers.set(name, entries);
          },
          sendMessage() {},
          getActiveTools() { return activeTools; },
          setActiveTools(nextTools) { activeTools = nextTools; },
        };
        extensionModule.default(pi);
        const start = tools.get("monitor_start");
        const stop = tools.get("monitor_stop");
        if (!start || !stop) throw new Error("monitor tools were not registered");
        for (const handler of handlers.get("session_start") ?? []) {
          await handler({}, { mode: "print", ui: {} });
        }
        if (!activeTools.includes("monitor_start") || activeTools.includes("monitor_stop") || !activeTools.includes("unrelated_tool")) {
          throw new Error("initial active tools incorrect: " + JSON.stringify(activeTools));
        }

        const first = await start.execute("start-1", {
          command: "sleep 5",
          description: "manual stop disclosure",
          result_pattern: "NEVER_MATCHES",
        }, undefined, undefined, { mode: "tui", hasUI: true, cwd: process.cwd(), ui: {} });
        if (!activeTools.includes("monitor_start") || !activeTools.includes("monitor_stop")) {
          throw new Error("monitor_stop was not activated: " + JSON.stringify(activeTools));
        }
        await stop.execute("stop-1", { monitor_id: first.details.monitorId });
        if (!activeTools.includes("monitor_start") || activeTools.includes("monitor_stop")) {
          throw new Error("monitor_stop was not removed after manual stop: " + JSON.stringify(activeTools));
        }

        await start.execute("start-2", {
          command: "printf 'DONE\\n'",
          description: "terminal disclosure",
          result_pattern: "DONE",
        }, undefined, undefined, { mode: "tui", hasUI: true, cwd: process.cwd(), ui: {} });
        if (!activeTools.includes("monitor_stop")) throw new Error("monitor_stop was not activated for terminal monitor");
        { const deadline = Date.now() + 15000; while (activeTools.includes("monitor_stop") && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (!activeTools.includes("monitor_start") || activeTools.includes("monitor_stop")) {
          throw new Error("monitor_stop was not removed after terminal result: " + JSON.stringify(activeTools));
        }

        for (const handler of handlers.get("session_shutdown") ?? []) await handler();
        if (activeTools.includes("monitor_stop")) throw new Error("monitor_stop remained active after session shutdown");
        ''',
    )

def test_monitor_stop_disclosure_writes_only_on_running_state_transitions() -> None:
    run_typescript(
        r'''
        import * as extensionModule from "./packages/monitor/index.ts";

        const tools = new Map();
        const handlers = new Map();
        let activeTools = ["monitor_start", "monitor_stop", "unrelated_tool"];
        let writes = 0;
        const pi = {
          registerTool(tool) { tools.set(tool.name, tool); },
          registerMessageRenderer() {},
          registerCommand() {},
          on(name, handler) {
            const entries = handlers.get(name) ?? [];
            entries.push(handler);
            handlers.set(name, entries);
          },
          sendMessage() {},
          getActiveTools() { return activeTools; },
          setActiveTools(nextTools) { writes += 1; activeTools = nextTools; },
        };
        extensionModule.default(pi);
        for (const handler of handlers.get("session_start") ?? []) {
          await handler({}, { mode: "print", ui: {} });
        }
        const initialWrites = writes;

        // No running monitor: the state is already the disclosed one, so a stop
        // that changes nothing must not rewrite the session-wide tool allowlist.
        try {
          await tools.get("monitor_stop").execute("stop-none", {});
        } catch {}
        if (writes !== initialWrites) {
          throw new Error(`redundant allowlist write with no state change: ${writes - initialWrites}`);
        }

        const first = await tools.get("monitor_start").execute("start-1", {
          command: "sleep 5",
          description: "disclosure churn",
          result_pattern: "NEVER_MATCHES",
        }, undefined, undefined, { mode: "tui", hasUI: true, cwd: process.cwd(), ui: {} });
        const afterStart = writes;

        // A second concurrent monitor keeps the same disclosure state, so the
        // allowlist must not be written again.
        const second = await tools.get("monitor_start").execute("start-2", {
          command: "sleep 5",
          description: "disclosure churn second",
          result_pattern: "NEVER_MATCHES",
        }, undefined, undefined, { mode: "tui", hasUI: true, cwd: process.cwd(), ui: {} });
        if (writes !== afterStart) {
          throw new Error(`allowlist rewritten without a state transition: ${writes - afterStart}`);
        }

        await tools.get("monitor_stop").execute("stop-1", { monitor_id: first.details.monitorId });
        if (writes !== afterStart) {
          throw new Error(`stopping one of two monitors should not write, wrote ${writes - afterStart}`);
        }
        await tools.get("monitor_stop").execute("stop-2", { monitor_id: second.details.monitorId });
        if (writes !== afterStart + 1) {
          throw new Error(`stopping the last monitor should write once, wrote ${writes - afterStart}`);
        }
        if (activeTools.includes("monitor_stop")) throw new Error("monitor_stop remained active: " + activeTools);
        ''',
    )

def test_registered_monitor_tool_terminates_and_wakes_once() -> None:
    run_typescript(
        r'''
        import * as extensionModule from "./packages/monitor/index.ts";

        const extension = extensionModule.default;
        const tools = new Map();
        const handlers = new Map();
        const messages = [];
        const pi = {
          registerTool(tool) { tools.set(tool.name, tool); },
          registerMessageRenderer() {},
          registerCommand() {},
          on(name, handler) {
            const current = handlers.get(name) ?? [];
            current.push(handler);
            handlers.set(name, current);
          },
          sendMessage(message, options) { messages.push({ message, options }); },
          getActiveTools() { return ["monitor_start"]; },
          setActiveTools() {},
        };
        extension(pi);
        const start = tools.get("monitor_start");
        if (!start) throw new Error("monitor_start was not registered");
        const startResult = await start.execute(
          "call-1",
          {
            command: `sleep 0.15; printf '__PI_MONITOR_RESULT__ {"ok":true}\\n'`,
            description: "extension integration",
            result_pattern: String.raw`__PI_MONITOR_RESULT__ (?<json>\{.*\})`,
          },
          undefined,
          undefined,
          { mode: "tui", hasUI: true, cwd: process.cwd(), ui: {} },
        );
        if (startResult.terminate !== true) throw new Error(JSON.stringify(startResult));
        const acknowledgement = startResult.content?.[0]?.text ?? "";
        if (!acknowledgement.includes("Monitor started: extension integration") ||
            !acknowledgement.includes(`monitor_id=${startResult.details.monitorId}`) ||
            !acknowledgement.includes("terminal_result=pending")) {
          throw new Error(JSON.stringify(startResult));
        }
        if (messages.length !== 0) throw new Error("monitor emitted before completion");

        { const deadline = Date.now() + 15000; while (messages.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (messages.length !== 1) throw new Error(JSON.stringify(messages));
        if (messages[0].message.customType !== "monitor-result") throw new Error(JSON.stringify(messages));
        if (messages[0].options.deliverAs !== "steer") throw new Error(JSON.stringify(messages));
        if (messages[0].options.triggerTurn !== true) throw new Error(JSON.stringify(messages));
        // The model-facing report is compact key=value text, never a pretty dump.
        for (const line of messages[0].message.content.split("\n")) {
          if (line === "" || line.startsWith("Monitor: ")) continue;
          if (!/^[a-z_]+(\.[a-z_]+)?=/.test(line)) throw new Error("non-compact terminal line: " + line);
        }
        if (messages[0].message.content.includes('<agent-message from="monitor">')) {
          throw new Error(JSON.stringify(messages));
        }
        if (!messages[0].message.content.includes("status=success")) {
          throw new Error(JSON.stringify(messages));
        }
        if (messages[0].message.content.includes("</agent-message>")) {
          throw new Error(JSON.stringify(messages));
        }
        if (messages[0].message.content.includes("output=")) {
          throw new Error(JSON.stringify(messages));
        }
        if (messages[0].message.details?.result?.result?.ok !== true ||
            messages[0].message.details?.description !== "extension integration") {
          throw new Error(JSON.stringify(messages));
        }
        ''',    )

def test_noninteractive_monitor_returns_terminal_result_without_custom_message() -> None:
    run_typescript(
        r'''
        import * as extensionModule from "./packages/monitor/index.ts";

        const tools = new Map();
        const messages = [];
        extensionModule.default({
          registerTool(tool) { tools.set(tool.name, tool); },
          registerMessageRenderer() {},
          registerCommand() {},
          on() {},
          sendMessage(message, options) { messages.push({ message, options }); },
          getActiveTools() { return ["monitor_start"]; },
          setActiveTools() {},
        });
        const start = tools.get("monitor_start");
        const result = await start.execute(
          "call-print",
          {
            command: `printf '__PI_MONITOR_RESULT__ {"ok":true}\\n'`,
            description: "print integration",
            result_pattern: String.raw`__PI_MONITOR_RESULT__ (?<json>\{.*\})`,
          },
          undefined,
          undefined,
          { cwd: process.cwd(), mode: "print", hasUI: false },
        );
        if (result.terminate) throw new Error(JSON.stringify(result));
        const content = result.content?.[0]?.text ?? "";
        if (!content.includes("status=success") || !content.includes('result={"ok":true}')) {
          throw new Error(JSON.stringify(result));
        }
        if (!/^monitor_[0-9a-f-]{36}$/.test(result.details?.monitorId ?? "") || result.details?.result?.result?.ok !== true) {
          throw new Error(JSON.stringify(result));
        }
        if (messages.length !== 0) throw new Error(JSON.stringify(messages));
        ''',
    )

def test_bare_pcre_case_insensitive_flag_has_actionable_javascript_diagnostic() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const manager = new MonitorManager({ onTerminal: () => {} });
        for (const [name, args] of [
          ["result", { resultPattern: "(?i)(error|failed)" }],
          ["failure", { resultPattern: "SUCCESS", failurePattern: "(?i)(error|failed)" }],
        ]) {
          let message = "";
          try {
            manager.start({
              command: "printf ignored",
              description: `${name} inline case flag`,
              ...args,
            });
          } catch (error) {
            message = String(error);
          }
          if (!message.includes("JavaScript RegExp does not support bare (?i)")) {
            throw new Error(`missing JavaScript compatibility guidance: ${message}`);
          }
          if (!message.includes("[eE][rR][rR][oO][rR]")) {
            throw new Error(`missing explicit case-alternative example: ${message}`);
          }
          if (!message.includes("(?i:error|failed)")) {
            throw new Error(`missing scoped case-insensitive equivalent: ${message}`);
          }
        }
        ''',
    )

def test_literal_inline_flag_text_preserves_native_javascript_regexp_behavior() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        for (const [pattern, output] of [
          ["[(?i)]", "?"],
          ["[a(?i)z]", "a"],
          [String.raw`\(\?i\)`, "(?i)"],
        ]) {
          const terminals = [];
          const manager = new MonitorManager({
            onTerminal: (_monitor, result) => terminals.push(result),
          });
          manager.start({
            command: `printf '%s\\n' ${JSON.stringify(output)}`,
            description: "literal inline-flag text",
            resultPattern: pattern,
          });
          { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
          if (terminals.length !== 1 || terminals[0].status !== "success") {
            throw new Error(`native RegExp behavior changed for ${pattern}: ${JSON.stringify(terminals)}`);
          }
        }
        ''',
    )

def test_success_sentinel_omits_progress_output_from_terminal_result() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        manager.start({
          command: `printf 'progress\\nFINAL_RESULT ok\\n'`,
          description: "quiet success",
          resultPattern: String.raw`FINAL_RESULT (?<value>\w+)`,
        });
        { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (terminals.length !== 1) throw new Error(JSON.stringify(terminals));
        const result = terminals[0].result;
        if (result.status !== "success") throw new Error(JSON.stringify(result));
        if (result.output !== undefined) throw new Error(JSON.stringify(result));
        if (result.outputTruncated !== undefined) throw new Error(JSON.stringify(result));
        ''',
    )

def test_nonparticipating_optional_named_capture_is_omitted_without_crashing() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        manager.start({
          command: `printf 'READY\n'`,
          description: "optional capture",
          resultPattern: String.raw`READY(?<optional> x)?`,
        });
        { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (terminals.length !== 1) throw new Error(JSON.stringify(terminals));
        const result = terminals[0].result;
        if (result.status !== "success" || result.captures?.optional !== undefined) {
          throw new Error(JSON.stringify(result));
        }
        ''',
    )

def test_success_sentinel_returns_one_structured_terminal_result() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        const started = manager.start({
          command: `printf 'progress\\n__PI_MONITOR_RESULT__ {"ok":true,"count":3}\\n'`,
          description: "sentinel",
          resultPattern: String.raw`__PI_MONITOR_RESULT__ (?<json>\{.*\})`,
        });
        { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (terminals.length !== 1) throw new Error(`terminal count ${terminals.length}`);
        const terminal = terminals[0];
        if (terminal.result.status !== "success") throw new Error(JSON.stringify(terminal));
        if (terminal.result.result.ok !== true || terminal.result.result.count !== 3) {
          throw new Error(JSON.stringify(terminal));
        }
        if (terminal.result.output !== undefined) {
          throw new Error(JSON.stringify(terminal));
        }
        if (manager.list().length !== 0) throw new Error("monitor remained active");
        const archived = manager.listAll().find((monitor) => monitor.id === terminal.monitor.id);
        if (!archived || archived.status !== "success") throw new Error(JSON.stringify(manager.listAll()));
        if (!manager.tail(archived.id)?.lines.some((line) => line.includes("progress"))) {
          throw new Error(JSON.stringify(manager.tail(archived.id)));
        }
        ''',    )

def test_failure_pattern_matches_stderr_and_returns_capture() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        const started = manager.start({
          command: `printf 'deploy failed: broken config\\n' >&2; sleep 5`,
          description: "failure",
          resultPattern: "DEPLOY_COMPLETE",
          failurePattern: String.raw`deploy failed: (?<reason>.+)`,
        });
        { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (terminals.length !== 1) throw new Error(`terminal count ${terminals.length}`);
        if (terminals[0].result.status !== "failure") throw new Error(JSON.stringify(terminals));
        if (terminals[0].result.captures.reason !== "broken config") {
          throw new Error(JSON.stringify(terminals));
        }
        if (!terminals[0].result.output?.some((line) => line.startsWith("[stderr]"))) {
          throw new Error(JSON.stringify(terminals));
        }
        ''',
    )

def test_drain_captures_lines_after_pattern_match_before_finalizing() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        manager.start({
          command: [
            "printf 'CMake Error at project.cmake:789 (message):\\n'",
            "printf '  Missing required dependency esp_hosted\\n'",
            "printf '  Please update your sdkconfig\\n'",
            "sleep 5",
          ].join("; "),
          description: "drain after failure",
          resultPattern: "BUILD_SUCCESS",
          failurePattern: "CMake Error",
        });
        { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (terminals.length !== 1) throw new Error(`terminal count ${terminals.length}`);
        const result = terminals[0].result;
        if (result.status !== "failure") throw new Error(JSON.stringify(result));
        const outputLines = result.output ?? [];
        const hasErrorLine = outputLines.some((line) => line.includes("CMake Error at project.cmake:789"));
        const hasDetailLine = outputLines.some((line) => line.includes("Missing required dependency esp_hosted"));
        const hasSecondDetailLine = outputLines.some((line) => line.includes("Please update your sdkconfig"));
        if (!hasErrorLine) throw new Error(`missing error line in: ${JSON.stringify(outputLines)}`);
        if (!hasDetailLine) throw new Error(`missing detail line in: ${JSON.stringify(outputLines)}`);
        if (!hasSecondDetailLine) throw new Error(`missing second detail line in: ${JSON.stringify(outputLines)}`);
        ''',
    )

def test_progress_output_does_not_emit_notifications() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        const started = manager.start({
          command: `printf 'step 1\\nstep 2\\n'; sleep 5`,
          description: "quiet progress",
          resultPattern: "NEVER_MATCHES",
        });
        await new Promise((resolve) => setTimeout(resolve, 200));
        if (terminals.length !== 0) throw new Error(JSON.stringify(terminals));
        manager.stop(started.id);
        if (terminals.length !== 0) throw new Error("manual stop emitted a terminal result");
        ''',
    )

def test_timeout_reports_terminal_result_and_stops_the_process() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        manager.start({
          command: `sleep 5`,
          description: "deployment timeout",
          resultPattern: "NEVER_MATCHES",
          timeoutMs: 100,
        });
        { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (terminals.length !== 1) throw new Error(JSON.stringify(terminals));
        const result = terminals[0].result;
        if (result.status !== "timeout") throw new Error(JSON.stringify(result));
        if (result.timeoutMs !== 100 || result.reason !== "timeout") {
          throw new Error(JSON.stringify(result));
        }
        if (manager.list().length !== 0) throw new Error("timed out monitor remained active");
        ''',
    )

def test_result_match_wins_over_timeout_during_drain() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        manager.start({
          command: `printf 'FINAL_RESULT\\n'; sleep 5`,
          description: "result before timeout",
          resultPattern: "FINAL_RESULT",
          timeoutMs: 100,
        });
        { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (terminals.length !== 1) throw new Error(JSON.stringify(terminals));
        if (terminals[0].result.status !== "success") throw new Error(JSON.stringify(terminals));
        ''',
    )

def test_timeout_above_node_timer_maximum_is_rejected() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const manager = new MonitorManager({ onTerminal: () => {} });
        let message = "";
        try {
          manager.start({
            command: "sleep 1",
            description: "invalid timeout",
            resultPattern: "NEVER_MATCHES",
            timeoutMs: 2_147_483_648,
          });
        } catch (error) {
          message = String(error);
        }
        if (!message.includes("timeout_ms")) throw new Error(message);
        ''',
    )

def test_unterminated_final_sentinel_matches_during_close_once() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        manager.start({
          command: `printf 'FINAL_RESULT id=42'`,
          description: "unterminated sentinel",
          resultPattern: String.raw`FINAL_RESULT id=(?<id>\d+)`,
        });
        { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (terminals.length !== 1 || terminals[0].result.status !== "success") {
          throw new Error(JSON.stringify(terminals));
        }
        if (terminals[0].result.captures.id !== "42") throw new Error(JSON.stringify(terminals));
        ''',
    )

def test_clean_exit_without_result_reports_result_missing() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        manager.start({
          command: `printf 'done without contract\\n'`,
          description: "missing",
          resultPattern: "EXPECTED_SENTINEL",
        });
        { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (terminals.length !== 1 || terminals[0].result.status !== "result_missing") {
          throw new Error(JSON.stringify(terminals));
        }
        if (terminals[0].result.expected !== "EXPECTED_SENTINEL") {
          throw new Error(JSON.stringify(terminals));
        }
        ''',
    )

def test_unterminated_sentinel_resolves_while_the_command_keeps_running() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const startedAt = Date.now();
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({
            monitor,
            result,
            resolvedAfterMs: Date.now() - startedAt,
          }),
        });
        // The sentinel is complete but carries no newline, and the command keeps
        // running. A server that prints READY and then serves must resolve on the
        // sentinel, not on exit and not on the timeout.
        manager.start({
          command: `printf 'READY url=http://localhost:3000'; sleep 20`,
          description: "ready without newline",
          resultPattern: String.raw`READY url=(?<url>\S+)`,
          timeoutMs: 30000,
        });
        { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (terminals.length !== 1) {
          throw new Error(`expected one terminal result, got ${JSON.stringify(terminals)}`);
        }
        if (terminals[0].result.status !== "success") {
          throw new Error(JSON.stringify(terminals));
        }
        if (terminals[0].result.captures.url !== "http://localhost:3000") {
          throw new Error(JSON.stringify(terminals));
        }
        if (terminals[0].resolvedAfterMs > 2000) {
          // The idle window plus the drain grace is ~1.2s; anything near the
          // command's 20s lifetime means the sentinel was only seen at exit.
          throw new Error(`sentinel resolved too late to be useful: ${terminals[0].resolvedAfterMs}ms`);
        }
        await manager.stopAllOnShutdown();
        ''',
    )

def test_sentinel_split_by_a_write_pause_still_matches_the_joined_line() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        // Two bursts separated by a pause longer than the unterminated-line idle
        // window. The partial buffer is never committed, so the sentinel still
        // matches once the line is complete.
        manager.start({
          command: `printf 'READY'; sleep 1; printf ' url=http://localhost:3000\\n'`,
          description: "sentinel split by a pause",
          resultPattern: String.raw`READY url=(?<url>\S+)`,
          timeoutMs: 30000,
        });
        { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (terminals.length !== 1 || terminals[0].result.status !== "success") {
          throw new Error(JSON.stringify(terminals));
        }
        if (terminals[0].result.captures.url !== "http://localhost:3000") {
          throw new Error(JSON.stringify(terminals));
        }
        await manager.stopAllOnShutdown();
        ''',
    )

def test_nonzero_exit_reports_failure() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ id: monitor.id, result }),
        });
        manager.start({
          command: `printf 'ordinary error\\n' >&2; exit 7`,
          description: "exit failure",
          resultPattern: "SUCCESS",
        });
        { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (terminals.length !== 1) throw new Error(JSON.stringify(terminals));
        const failure = terminals.find((entry) => entry.result.status === "failure");
        if (!failure || failure.result.exitCode !== 7) {
          throw new Error(JSON.stringify(terminals));
        }
        ''',
    )

def test_adjacent_terminal_diagnostics_are_collapsed_with_counts() -> None:
    run_typescript(
        r'''
        import { MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        manager.start({
          command: [
            "for i in 1 2 3; do printf '%s\\n' '/bin/sh: line 6: [: 0' >&2; done; for i in 1 2 3; do printf '%s\\n' '0: integer expression expected' >&2; done",
            "sleep 5",
          ].join("; "),
          description: "deduplicated diagnostics",
          resultPattern: "EXPECTED_SENTINEL",
          timeoutMs: 100,
        });
        { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (terminals.length !== 1) throw new Error(JSON.stringify(terminals));
        const result = terminals[0].result;
        if (result.status !== "timeout") throw new Error(JSON.stringify(result));
        if (result.outputTruncated) throw new Error(JSON.stringify(result));
        const output = result.output ?? [];
        if (output.length !== 2) throw new Error(JSON.stringify(output));
        if (!output[0].startsWith("[stderr]") || !output[0].includes("line 6") || !output[0].includes("repeated 3 times")) {
          throw new Error(JSON.stringify(output));
        }
        if (!output[1].startsWith("[stderr]") || !output[1].includes("integer expression expected") || !output[1].includes("repeated 3 times")) {
          throw new Error(JSON.stringify(output));
        }
        ''',
    )

def test_sigkill_escalates_to_term_resistant_descendant_after_shell_closes() -> None:
    run_typescript(
        r'''
        import { existsSync, readFileSync } from "node:fs";
        import { mkdtemp, rm, writeFile } from "node:fs/promises";
        import { tmpdir } from "node:os";
        import { join } from "node:path";
        import { KILL_GRACE_MS, MonitorManager } from "./packages/monitor/src/monitor.ts";

        const fixtureDirectory = await mkdtemp(join(tmpdir(), "pi-monitor-kill-tree-"));
        const fixture = join(fixtureDirectory, "ignore-term.mjs");
        const pidFile = join(fixtureDirectory, "pids.json");
        await writeFile(fixture, [
          'import { writeFileSync } from "node:fs";',
          'process.on("SIGTERM", () => {});',
          'writeFileSync(process.env.PID_FILE, JSON.stringify({ childPid: process.pid, shellPid: process.ppid }));',
          'setInterval(() => {}, 1000);',
        ].join("\n"));

        const terminals = [];
        let childPid;
        let shellPid;
        const isAlive = (pid) => {
          try {
            process.kill(pid, 0);
            return true;
          } catch (error) {
            return error?.code === "EPERM";
          }
        };
        const waitForPidFile = async () => {
          for (let attempt = 0; attempt < 40; attempt += 1) {
            if (existsSync(pidFile)) return JSON.parse(readFileSync(pidFile, "utf8"));
            await new Promise((resolve) => setTimeout(resolve, 25));
          }
          throw new Error("descendant did not publish its pids");
        };
        const manager = new MonitorManager({
          onTerminal: (_monitor, result) => terminals.push(result),
        });
        try {
          const started = manager.start({
            command: `PID_FILE=${JSON.stringify(pidFile)} ${JSON.stringify(process.execPath)} ${JSON.stringify(fixture)} & wait`,
            description: "term-resistant descendant",
            resultPattern: "NEVER_MATCHES",
          });
          ({ childPid, shellPid } = await waitForPidFile());
          manager.stop(started.id);
          await new Promise((resolve) => setTimeout(resolve, 150));
          if (terminals.length !== 0 || isAlive(shellPid) || !isAlive(childPid)) {
            throw new Error(`expected closed shell, live descendant, no result: ${JSON.stringify({ terminals, shellPid, childPid })}`);
          }
          await new Promise((resolve) => setTimeout(resolve, KILL_GRACE_MS + 500));
          if (isAlive(childPid)) throw new Error(`descendant ${childPid} survived SIGKILL escalation`);
        } finally {
          if (childPid && isAlive(childPid)) process.kill(childPid, "SIGKILL");
          if (shellPid && isAlive(shellPid)) process.kill(shellPid, "SIGKILL");
          await rm(fixtureDirectory, { recursive: true, force: true });
        }
        ''',
    )

def test_session_shutdown_waits_for_sigkill_escalation_before_parent_exit() -> None:
    run_typescript(
        r'''
        import { existsSync } from "node:fs";
        import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
        import { spawn } from "node:child_process";
        import { tmpdir } from "node:os";
        import { join } from "node:path";
        import { pathToFileURL } from "node:url";

        const fixtureDirectory = await mkdtemp(join(tmpdir(), "pi-monitor-shutdown-"));
        const descendant = join(fixtureDirectory, "ignore-term.mjs");
        const parent = join(fixtureDirectory, "shutdown-parent.mjs");
        const pidFile = join(fixtureDirectory, "pids.json");
        let childPid;
        let shellPid;
        const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
        const isRunning = (pid) => {
          try {
            process.kill(pid, 0);
            return true;
          } catch (error) {
            return error?.code === "EPERM";
          }
        };
        const waitForExit = (child) => new Promise((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error("shutdown parent did not exit")), 5000);
          child.on("error", reject);
          child.on("close", (code) => {
            clearTimeout(timeout);
            code === 0 ? resolve(undefined) : reject(new Error(`shutdown parent exited ${code}`));
          });
        });

        await writeFile(descendant, [
          'import { writeFileSync } from "node:fs";',
          'process.on("SIGTERM", () => {});',
          'writeFileSync(process.env.PID_FILE, JSON.stringify({ childPid: process.pid, shellPid: process.ppid }));',
          'setInterval(() => {}, 1000);',
        ].join("\n"));
        const monitorModule = pathToFileURL(join(process.cwd(), "packages/monitor/src/monitor.ts")).href;
        const command = `PID_FILE=${JSON.stringify(pidFile)} ${JSON.stringify(process.execPath)} ${JSON.stringify(descendant)} & wait`;
        await writeFile(parent, [
          `import { existsSync, readFileSync } from "node:fs";`,
          `import { MonitorManager } from ${JSON.stringify(monitorModule)};`,
          `const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));`,
          `const manager = new MonitorManager({ onTerminal: () => {} });`,
          `manager.start({ command: ${JSON.stringify(command)}, description: "shutdown", resultPattern: "NEVER_MATCHES" });`,
          `for (let attempt = 0; attempt < 80 && !existsSync(${JSON.stringify(pidFile)}); attempt += 1) await delay(25);`,
          `if (!existsSync(${JSON.stringify(pidFile)})) throw new Error("descendant did not publish its pid");`,
          `await manager.stopAllOnShutdown();`,
          `JSON.parse(readFileSync(${JSON.stringify(pidFile)}, "utf8"));`,
        ].join("\n"));

        try {
          const shutdownParent = spawn(process.execPath, ["--import", "tsx", parent], {
            cwd: process.cwd(),
            stdio: "ignore",
          });
          await waitForExit(shutdownParent);
          ({ childPid, shellPid } = JSON.parse(await readFile(pidFile, "utf8")));
          await delay(100);
          if (isRunning(childPid)) {
            throw new Error(`SIGTERM-resistant descendant ${childPid} survived parent shutdown`);
          }
        } finally {
          if (childPid && isRunning(childPid)) process.kill(childPid, "SIGKILL");
          if (shellPid && isRunning(shellPid)) process.kill(shellPid, "SIGKILL");
          await rm(fixtureDirectory, { recursive: true, force: true });
        }
        ''',
    )

def test_terminal_diagnostics_are_bounded_after_completion() -> None:
    run_typescript(
        r'''
        import { MAX_LOG_LINES, MonitorManager } from "./packages/monitor/src/monitor.ts";

        const terminals = [];
        const manager = new MonitorManager({
          onTerminal: (monitor, result) => terminals.push({ monitor, result }),
        });
        const started = manager.start({
          command: `node -e "for(let i=0;i<3000;i++) console.log('line-' + i)"`,
          description: "bounded logs",
          resultPattern: "NEVER_MATCHES",
        });
        // A loaded machine can outrun a fixed wait; poll for the condition instead.
        { const deadline = Date.now() + 15000; while (terminals.length < 1 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 20)); }
        if (terminals.length !== 1) throw new Error(JSON.stringify(terminals));
        const result = terminals[0].result;
        if (result.output?.length > 100) throw new Error(`too many lines ${result.output.length}`);
        if (!result.outputTruncated) throw new Error(JSON.stringify(result));
        if (result.status !== "result_missing") throw new Error(JSON.stringify(terminals));
        ''',
    )
