/** One native invocation per monitor functional path; real model owns parent selection. */
import fs from "node:fs";
import { stripVTControlCharacters } from "node:util";
import { KeybindingsManager, setKeybindings, visibleWidth } from "@earendil-works/pi-tui";
import monitorExtension from "../../index.ts";

setKeybindings(new KeybindingsManager({} as never));

type Tool = {
  name: string;
  execute: (id: string, params: Record<string, unknown>, signal?: AbortSignal,
    update?: unknown, ctx?: unknown) => Promise<{
      content: Array<{ text: string }>;
      structuredContent: Record<string, unknown>;
      details: Record<string, unknown>;
      terminate?: boolean;
    }>;
};
type Sent = { message: { customType: string; details: Record<string, unknown> }; options: Record<string, unknown> };
type Ctx = {
  mode: string; hasUI: boolean; cwd: string; ui: Record<string, unknown>;
  sessionManager: { getBranch: () => unknown[] };
};

const theme = { fg: (_name: string, text: string) => text, bg: (_name: string, text: string) => text, bold: (text: string) => text };
const tools = new Map<string, Tool>();
const renderers = new Map<string, unknown>();
const commands = new Map<string, (args: string, ctx: Ctx) => unknown>();
const hooks = new Map<string, Array<(...args: never[]) => unknown>>();
const sent: Sent[] = [];
const notices: unknown[] = [];
const widgets: Array<{ key: string; content: unknown }> = [];
let activeTools = ["monitor_start", "bash"];
const setActiveCalls: string[][] = [];
const results: Record<string, unknown> = {};
const bytes = (value: string) => Buffer.byteLength(value, "utf8");

const ui = {
  notify: (message: unknown) => notices.push(message),
  setWidget: (key: string, content: unknown) => widgets.push({ key, content }),
  setStatus() {}, custom: async () => undefined, requestRender() {},
};
const pi = {
  ui,
  registerTool(tool: Tool) { tools.set(tool.name, tool); },
  registerMessageRenderer(name: string, fn: unknown) { renderers.set(name, fn); },
  registerCommand(name: string, value: { handler: (args: string, ctx: Ctx) => unknown }) { commands.set(name, value.handler); },
  on(name: string, fn: (...args: never[]) => unknown) { hooks.set(name, [...(hooks.get(name) ?? []), fn]); },
  sendMessage(message: Sent["message"], options: Sent["options"]) { sent.push({ message, options }); },
  getActiveTools: () => [...activeTools],
  setActiveTools(next: string[]) { activeTools = [...next]; setActiveCalls.push([...next]); },
  registerEntryRenderer() {}, appendEntry() {},
};
// The renderer/theme shim is only for the offline native harness; monitor rows
// still use Pi's real lifecycle renderer and pi-tui geometry helpers.
void theme; void stripVTControlCharacters; void visibleWidth;
monitorExtension(pi as never);

const ctx = (overrides: Partial<Ctx> = {}): Ctx => ({
  mode: "tui", hasUI: true, cwd: "/work", ui, sessionManager: { getBranch: () => [] }, ...overrides,
});
const fire = async (name: string, event: unknown = {}, context: Ctx = ctx()) => {
  let value: unknown;
  for (const fn of hooks.get(name) ?? []) value = await fn(event as never, context as never);
  return value;
};
const start = tools.get("monitor_start")!;
const stop = tools.get("monitor_stop")!;

results.registered = [...tools.keys()].sort();
results.commands = [...commands.keys()].sort();
results.renderers = [...renderers.keys()].sort();

// 1. Session baseline: monitor_stop is not active before a running monitor.
await fire("session_start", {}, ctx());
results.startBaseline = { activeTools: [...activeTools], setActiveCalls: setActiveCalls.length };

const headless = (overrides: Partial<Ctx> = {}) => ctx({ mode: "print", hasUI: false, ...overrides });

// 2. Headless match-mode success, exact bounded model-facing text.
const ok = await start.execute("call-ok", {
  command: "printf 'noise\\n'; printf 'DONE_OK\\n'", description: "headless success",
  result_pattern: "DONE_OK",
}, undefined, undefined, headless());
results.headlessSuccess = {
  status: ok.structuredContent.status, resultStatus: (ok.structuredContent.result as Record<string, unknown>).status,
  monitorId: ok.structuredContent.monitorId, hasResult: ok.details.result !== undefined,
  textBytes: bytes(ok.content[0].text),
  stoppedBy: (ok.structuredContent.result as Record<string, unknown>).stoppedBy,
};

// 3. Exit mode with a named JSON capture and natural zero exit.
const exit = await start.execute("call-exit", {
  command: "node -e 'console.log(\"DONE \" + JSON.stringify({ok:true,value:7}))'",
  description: "exit json", result_pattern: "DONE (?<json>.*)", completion: "exit",
}, undefined, undefined, headless());
const exitResult = exit.structuredContent.result as Record<string, unknown>;
results.exitJson = {
  status: exitResult.status, result: exitResult.result, captures: exitResult.captures,
  completion: exitResult.completion, exitCode: exitResult.exitCode,
};

// 4. Failure pattern wins over a later success line.
const fail = await start.execute("call-fail", {
  command: "printf 'FAIL_NOW\\n'; printf 'DONE_OK\\n'", description: "failure wins",
  result_pattern: "DONE_OK", failure_pattern: "FAIL_NOW",
}, undefined, undefined, headless());
const failResult = fail.structuredContent.result as Record<string, unknown>;
results.failure = { status: failResult.status, stoppedBy: failResult.stoppedBy, matched: failResult.matched };

// 5. Zero exit without the required contract is an honest result_missing.
const missing = await start.execute("call-missing", {
  command: "printf 'nothing\\n'", description: "missing", result_pattern: "NEVER", completion: "exit",
}, undefined, undefined, headless());
const missingResult = missing.structuredContent.result as Record<string, unknown>;
results.resultMissing = { status: missingResult.status, exit: missingResult.exitCode };

// 6. Explicit deadline stays bounded.
const timed = await start.execute("call-timeout", {
  command: "sleep 3", description: "timeout", result_pattern: "NEVER", timeout_ms: 300,
}, undefined, undefined, headless());
const timedResult = timed.structuredContent.result as Record<string, unknown>;
results.timeout = { status: timedResult.status, timeoutMs: timedResult.timeoutMs };

// 7. UI-host-only batch: pending acknowledgement, then one steer-triggered custom result.
const uiBranch = (id: string): Ctx => ctx({
  sessionManager: { getBranch: () => [{ type: "message", message: { role: "assistant",
    content: [{ type: "toolCall", id, name: "monitor_start", arguments: {} }] } }] },
});
const asyncStart = await start.execute("ui-1", {
  command: "printf 'PRIVATE\\n'; sleep 0.6; printf 'DONE_ASYNC\\n'", description: "async ui",
  result_pattern: "DONE_ASYNC", timeout_ms: 4000,
}, undefined, undefined, uiBranch("ui-1"));
results.asyncUi = {
  status: asyncStart.structuredContent.status, terminate: asyncStart.terminate,
  monitorId: asyncStart.structuredContent.monitorId, activeTools: [...activeTools],
};
await new Promise(resolve => setTimeout(resolve, 1500));
results.asyncDelivery = {
  sent: sent.length, lastCustom: sent.at(-1)?.message.customType,
  deliverAs: sent.at(-1)?.options.deliverAs, trigger: sent.at(-1)?.options.triggerTurn,
  lastStatus: (sent.at(-1)?.message.details.result as Record<string, unknown> | undefined)?.status,
  activeTools: [...activeTools], widgets: widgets.length,
};

// 8. Stop tool: unknown id fails; a running UI monitor stops by exact id.
const invalidStop = await stop.execute("stop-invalid", { monitor_id: "does-not-exist" },
  undefined, undefined, ctx()).then(() => false, () => true);
const pending = await start.execute("ui-2", {
  command: "sleep 8", description: "stop me", result_pattern: "NEVER", timeout_ms: 9000,
}, undefined, undefined, uiBranch("ui-2"));
const stopped = await stop.execute("stop-run", { monitor_id: pending.structuredContent.monitorId as string },
  undefined, undefined, ctx());
results.stop = {
  invalidRefused: invalidStop, stopped: stopped.structuredContent.stopped,
  content: stopped.content[0].text,
};

// 9. Capability-dependent prompt guidance injection.
const promptEvent = { systemPromptOptions: { sections: {} as Record<string, unknown> } };
await fire("before_agent_start", promptEvent, ctx());
results.guidance = {
  section: Object.keys(promptEvent.systemPromptOptions.sections),
  bytes: bytes(JSON.stringify(promptEvent.systemPromptOptions.sections)),
  hasBash: JSON.stringify(promptEvent.systemPromptOptions.sections).includes("Bash:"),
  hasMonitor: JSON.stringify(promptEvent.systemPromptOptions.sections).includes("monitor_start"),
};

// 10. Shutdown clears the widget and leaves no active monitor_stop disclosure.
await fire("session_shutdown", {}, ctx());
results.shutdown = { activeTools: [...activeTools], widgetsCleared: widgets.some(row => row.content === undefined) };

fs.mkdirSync("/results", { recursive: true });
fs.writeFileSync("/results/native.json", JSON.stringify(results, null, 2) + "\n");
console.log(JSON.stringify({ paths: Object.keys(results) }));
