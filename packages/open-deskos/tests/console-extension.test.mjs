import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import extension from "../index.ts";
import { formatHistory } from "../src/console-extension.ts";
import { DeskConsoleClient } from "../src/console-client.ts";

function harness(env) {
  const previous = { ...process.env };
  // The extension reads the machine's desk list when one exists, and that default
  // path is computed once when this package is imported, before a fixture can set
  // HOME. A fixture therefore states its own list: otherwise the host's real desks
  // are what the extension reports to, and the fixture proves nothing about itself.
  const desksFile = join(mkdtempSync(join(tmpdir(), "odk-console-fixture-")), "desks.json");
  writeFileSync(desksFile, JSON.stringify({
    desks: env.ODK_LINK_ADDRESS === undefined ? [] : [{
      address: env.ODK_LINK_ADDRESS,
      token: env.ODK_LINK_TOKEN ?? "",
      ...(env.ODK_LINK_CONTROL_TOKEN ? { controlToken: env.ODK_LINK_CONTROL_TOKEN } : {}),
    }],
  }));
  Object.assign(process.env, { ODK_LINK_DESKS_FILE: desksFile, ...env });
  const hooks = new Map();
  const commands = new Map();
  const tools = new Map();
  const renderers = [];
  const appended = [];
  const messages = [];
  const pi = {
    on(name, handler) { hooks.set(name, handler); },
    registerCommand(name, command) { commands.set(name, command); },
    registerTool(tool) { tools.set(tool.name, tool); },
    registerMessageRenderer(name) { renderers.push(name); },
    appendEntry(customType, data) { appended.push({ customType, data: structuredClone(data) }); },
    sendMessage(message, options) { messages.push({ message: structuredClone(message), options: structuredClone(options) }); },
  };
  extension(pi);
  return {
    hooks, commands, tools, renderers, appended, messages,
    restore() {
      for (const key of Object.keys(process.env)) if (!(key in previous)) delete process.env[key];
      Object.assign(process.env, previous);
    },
  };
}

test("desk tools use the required snake_case surface without status or detach", () => {
  const h = harness({ ODK_LINK_ADDRESS: "127.0.0.1:8765", ODK_LINK_TOKEN: "report", ODK_LINK_CONTROL_TOKEN: "control" });
  try {
    assert.deepEqual([...h.tools.keys()], ["odk_list", "odk_start", "odk_attach", "odk_prompt", "odk_cancel", "odk_end", "odk_history"]);
    assert.equal(h.tools.has("odk_status"), false);
    assert.equal(h.tools.has("odk_detach"), false);
    assert.deepEqual(h.renderers, ["odk-hosted-pi"]);
  } finally { h.restore(); }
});

test("without a Control Credential the machine stays report-only and registers no desk tools", () => {
  const h = harness({ ODK_LINK_ADDRESS: "127.0.0.1:8765", ODK_LINK_TOKEN: "report", ODK_LINK_CONTROL_TOKEN: "" });
  try {
    assert.deepEqual([...h.tools.keys()], []);
    assert.deepEqual(h.renderers, []);
    assert.equal(h.commands.has("odk"), true);
  } finally { h.restore(); }
});

test("session restore accepts the persisted attached identity and last applied position", () => {
  const h = harness({ ODK_LINK_ADDRESS: "127.0.0.1:8765", ODK_LINK_TOKEN: "report", ODK_LINK_CONTROL_TOKEN: "control" });
  try {
    h.hooks.get("session_start")({}, {
      sessionManager: {
        getSessionId() { return "console-a"; },
        getBranch() { return [{ type: "custom", customType: "odk-console-state", data: { sessionId: "hosted-1", attachmentId: "attachment-old", lastApplied: 17 } }]; },
      },
    });
    h.hooks.get("agent_settled")({}, {});
    assert.deepEqual(h.appended, []);
    assert.deepEqual(h.messages, []);
    h.hooks.get("session_shutdown")({}, {});
  } finally { h.restore(); }
});

test("history output truncates only before a complete physical position batch", () => {
  const large = "x".repeat(30 * 1024);
  const text = formatHistory({
    entries: [
      { position: 7, events: [{ kind: "assistant", text: large }] },
      { position: 8, events: [{ kind: "assistant", text: large }] },
    ],
    nextPosition: null,
  });
  assert.match(text, /^7 assistant/);
  assert.doesNotMatch(text, /8 assistant/);
  assert.match(text, /continue from position 7/);
});

test("attached Console exposes an explicit history paging action", async () => {
  const source = await readFile(new URL("../src/console-extension.ts", import.meta.url), "utf8");
  assert.match(source, /ctrl\+h history/);
  assert.match(source, /Key\.ctrl\("h"\)/);
  assert.match(source, /attachment\.history/);
});

test("Hosted Pi context injection never starts an autonomous model loop", async () => {
  const source = await readFile(new URL("../src/console-extension.ts", import.meta.url), "utf8");
  assert.match(source, /deliverAs: "followUp", triggerTurn: false/);
  assert.doesNotMatch(source, /deliverAs: "followUp", triggerTurn: true/);
});

test("console surface uses the Pi TUI Input seam for focused IME text", async () => {
  const source = await readFile(new URL("../src/console-extension.ts", import.meta.url), "utf8");
  assert.match(source, /new Input\(\)/);
  assert.match(source, /type Focusable/);
  assert.doesNotMatch(source, /❯/);
});

test("odk no-argument fallback stays usable without TUI and names stable rows", async () => {
  const h = harness({ ODK_LINK_ADDRESS: "", ODK_LINK_TOKEN: "", ODK_LINK_CONTROL_TOKEN: "" });
  const notices = [];
  try {
    await h.commands.get("odk").handler("", {
      mode: "print",
      hasUI: false,
      cwd: "/workspace",
      ui: { notify(message) { notices.push(message); } },
    });
    assert.match(notices[0], /ODK_LINK_ADDRESS/);
    assert.match(notices[0], /ODK_LINK_TOKEN/);
    assert.match(notices[0], /Control Credential|ODK_LINK_CONTROL_TOKEN/);
  } finally { h.restore(); }
});

test("console session reload closes an old hosted attachment", async () => {
  const { registerConsoleExtension } = await import("../src/console-extension.ts");
  const hooks = new Map();
  const tools = new Map();
  const transports = [];
  registerConsoleExtension({
    pi: { on: (name, handler) => hooks.set(name, handler), registerTool: tool => tools.set(tool.name, tool), registerCommand() {}, registerMessageRenderer() {}, appendEntry() {}, sendMessage() {} },
    config: { host: "127.0.0.1", port: 1, machine: "test", token: "report", controlToken: "control" },
    reporterSnapshot: () => null,
    createControlTransport() {
      let onRecord;
      const transport = {
        closed: false,
        send(record) {
          const reply = record.type === "control-hello" ? { v: 2, type: "challenge", nonce: "fixture" } : record.type === "control-proof" ? { v: 2, type: "control-ack" } : { v: 2, type: "ack", requestId: record.requestId, result: { caughtUp: true } };
          queueMicrotask(() => onRecord(reply));
        },
        close() { this.closed = true; },
        onOpen(fn) { queueMicrotask(fn); }, onClose() {}, onRecord(fn) { onRecord = fn; },
      };
      transports.push(transport);
      return transport;
    },
  });
  const ctx = id => ({ sessionManager: { getSessionId: () => id, getBranch: () => [] } });
  hooks.get("session_start")({}, ctx("first"));
  await tools.get("odk_attach").execute("fixture", { session_id: "hosted" });
  hooks.get("session_start")({}, ctx("second"));
  assert.equal(transports[0].closed, true);
  hooks.get("session_shutdown")({}, ctx("second"));
});

for (const verb of ["prompt", "cancel", "end"]) {
  test(`a completed ${verb} continuation keeps its owner across console reload`, async (t) => {
    const { registerConsoleExtension } = await import("../src/console-extension.ts");
    const hooks = new Map(), tools = new Map(), messages = [];
    let complete;
    const acknowledged = new Promise((resolve) => { complete = resolve; });
    const attachments = [];
    t.mock.method(DeskConsoleClient.prototype, "attach", async ({ sessionId }) => {
      const joined = {
        sessionId, attachmentId: `attachment-${sessionId}`, closed: 0,
        lastApplied: () => 0,
        prompt: () => acknowledged, cancel: () => acknowledged, end: () => acknowledged,
        close() { this.closed += 1; },
      };
      attachments.push(joined);
      return joined;
    });
    registerConsoleExtension({
      pi: {
        on: (name, handler) => hooks.set(name, handler),
        registerTool: (tool) => tools.set(tool.name, tool),
        registerCommand() {}, registerMessageRenderer() {}, appendEntry() {},
        sendMessage: (message) => messages.push(message),
      },
      config: { host: "127.0.0.1", port: 1, machine: "fixture", token: "report", controlToken: "control" },
      reporterSnapshot: () => null,
      createControlTransport() { throw new Error("isolated fixture must not create a transport"); },
    });
    const ctx = (id) => ({ sessionManager: { getSessionId: () => id, getBranch: () => [] } });
    hooks.get("session_start")({}, ctx("console-old"));
    await tools.get("odk_attach").execute("attach-old", { session_id: "hosted-old" });
    const pending = tools.get(`odk_${verb}`).execute("mutation", { prompt: "fixture" });
    hooks.get("session_start")({}, ctx("console-new"));
    await tools.get("odk_attach").execute("attach-new", { session_id: "hosted-new" });
    complete();
    const result = await pending;
    assert.match(result.content[0].text, /hosted-old/, "the acknowledgement belongs to the original target");
    assert.equal(attachments[1].closed, 0, "an old completion must not close the replacement");
    assert.deepEqual(messages, [], "an old completion must not inject context into the new console");
    hooks.get("session_shutdown")({}, ctx("console-new"));
  });
}
