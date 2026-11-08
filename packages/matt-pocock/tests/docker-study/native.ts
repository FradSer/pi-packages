/** One native invocation per functional path; the model only owns parent selection. */
import fs from "node:fs";
import mattPocock from "../../src/index.ts";

type Tool = {
  name: string;
  parameters: { properties?: Record<string, unknown> };
  execute: (id: string, params: Record<string, unknown>, signal?: AbortSignal,
    update?: unknown, ctx?: unknown) => Promise<{ content: Array<{ text: string }>; details?: Record<string, unknown> }>;
};
type Notice = { customType: string; content: string; details: Record<string, unknown>; display: boolean };
type Entry = { type: string; customType: string; data: Record<string, unknown> };

const results: Record<string, unknown> = {};
const notices: Array<{ message: Notice; options: unknown }> = [];
const appended: Array<{ type: string; data: Record<string, unknown> }> = [];
const tools: Record<string, Tool> = {};
const commands: Record<string, (args: string, ctx: unknown) => unknown> = {};
const listeners: Record<string, Array<(...args: never[]) => unknown>> = {};
let activeTools = ["matt_pocock_workflow"];
let sessionEntries: Entry[] = [];
const bytes = (value: string) => Buffer.byteLength(value, "utf8");

const ui = {
  notify() {}, select: async () => undefined, input: async () => undefined,
  setStatus() {}, setWidget() {}, custom() {},
};
const ctx = {
  cwd: "/work", hasUI: false, ui,
  sessionManager: {
    getBranch: () => sessionEntries,
    getEntries: () => sessionEntries,
    getLeafId: () => "leaf",
  },
};
const pi = {
  on(event: string, fn: (...args: never[]) => unknown) { (listeners[event] ??= []).push(fn); },
  registerTool(tool: Tool) { tools[tool.name] = tool; },
  registerCommand(name: string, value: { handler: (args: string, ctx: unknown) => unknown }) {
    commands[name] = value.handler;
  },
  registerMessageRenderer() {},
  sendMessage(message: Notice, options: unknown) { notices.push({ message, options }); },
  appendEntry(type: string, data: Record<string, unknown>) {
    appended.push({ type, data });
    sessionEntries.push({ type: "custom", customType: type, data });
  },
  getActiveTools: () => [...activeTools],
  setActiveTools(next: string[]) { activeTools = [...next]; },
  getAllTools: () => Object.keys(tools),
  ui,
};

mattPocock(pi as never);
results.registered = Object.keys(tools).sort();
results.commands = Object.keys(commands).sort();

async function restore(record: Record<string, unknown>, reason: string): Promise<void> {
  sessionEntries = [{ type: "custom", customType: "matt-pocock-workflow", data: record }];
  for (const handler of listeners.session_start ?? []) await handler({ reason } as never, ctx as never);
}

const command = commands["matt-pocock"]!;
const active = tools.matt_pocock_active!;
const ask = tools.matt_pocock_ask!;
const gateway = tools.matt_pocock_workflow!;

// 1. User command starts a persisted workflow, carrying the task only into delivery.
await command("hard-bug Fix receipt quantity", ctx);
const first = notices.at(-1)!.message;
const state = appended.at(-1)!.data;
results.workflowCommand = {
  customType: first.customType, route: first.details.route, procedure: first.details.procedure,
  status: first.details.status, request: first.details.request, textBytes: bytes(first.content),
  hasStateContract: first.content.includes("## Workflow state contract"),
  activeTools: [...activeTools],
};
results.workflowState = state;

// 2. A new session restores the active branch without a second persisted record.
const beforeRestore = appended.length;
await restore(state, "restored");
results.restore = {
  activeTools: [...activeTools], persistedRecordsAdded: appended.length - beforeRestore,
  state: appended.at(-1)!.data.status,
};

// 3. One legal transition, one no-UI decision, one completion.
const transition = await active.execute("transition-1", { action: "transition", target: "implement" }, undefined, undefined, ctx);
results.transition = {
  parameters: Object.keys(active.parameters.properties ?? {}),
  procedure: (transition.details?.state as Record<string, unknown> | undefined)?.procedure,
  textBytes: bytes(transition.content[0].text),
  hasStateContract: transition.content[0].text.includes("## Workflow state contract"),
};
const decision = await ask.execute("ask-1", {
  question: "Choose one?", options: ["A", "B"], recommended: "A",
  timeout_seconds: 0.1, allow_custom: false,
}, undefined, undefined, ctx);
results.ask = { pending: decision.details?.pending, source: decision.details?.source };
const completed = await active.execute("complete-1", { action: "complete" }, undefined, undefined, ctx);
results.completed = {
  status: (completed.details?.state as Record<string, unknown> | undefined)?.status,
  workItemId: (completed.details?.state as Record<string, unknown> | undefined)?.workItemId,
  activeTools: [...activeTools],
};

// 4. Gateway modes: model capability, user capability, disclosed reference, invalid crossover.
const capability = await gateway.execute("cap-1", { mode: "capability", capability: "research" }, undefined, undefined, ctx);
results.capability = {
  mode: capability.details?.mode, textBytes: bytes(capability.content[0].text),
  hasSource: capability.content[0].text.includes("<procedure-source"),
};
const userCapability = await gateway.execute("user-cap-1", { mode: "user-capability", capability: "handoff" }, undefined, undefined, ctx);
results.userCapability = { mode: userCapability.details?.mode, textBytes: bytes(userCapability.content[0].text) };
const reference = await gateway.execute("reference-1", { mode: "reference", capability: "prototype", reference: "LOGIC" }, undefined, undefined, ctx);
results.reference = {
  mode: reference.details?.mode, textBytes: bytes(reference.content[0].text),
  hasHeading: reference.content[0].text.includes("# Matt Pocock standalone reference"),
};
results.invalidCapabilityRefused = await gateway.execute("invalid-1", { mode: "capability", capability: "handoff" },
  undefined, undefined, ctx).then(() => false, () => true);

// 5. Workflow-only reference load, command cancellation, and unknown-token routing.
await command("hard-bug reproduce", ctx);
const load = await active.execute("load-1", { action: "load", reference: "hitl-loop.template.sh" }, undefined, undefined, ctx);
results.workflowReference = { action: load.details?.action, textBytes: bytes(load.content[0].text) };
await command("cancel done", ctx);
results.cancelled = {
  status: appended.at(-1)!.data.status, reason: appended.at(-1)!.data.reason,
  activeTools: [...activeTools],
};
await command("nonsense route this", ctx);
const routing = notices.at(-1)!.message;
results.unknownRouting = {
  customType: routing.customType,
  textHasRouting: routing.content.includes("Route and execute this request"),
  persistedStateStatus: appended.at(-1)!.data.status,
};

fs.mkdirSync("/results", { recursive: true });
fs.writeFileSync("/results/native.json", JSON.stringify(results, null, 2) + "\n");
console.log(JSON.stringify({ paths: Object.keys(results) }));
