import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import extension from "../index.ts";
import { formatHistory } from "../src/console-extension.ts";

function harness(env) {
  const previous = { ...process.env };
  Object.assign(process.env, env);
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
  const h = harness({ ODK_DESK_LINK_ADDRESS: "127.0.0.1:8765", ODK_DESK_LINK_TOKEN: "report", ODK_DESK_LINK_CONTROL_TOKEN: "control" });
  try {
    assert.deepEqual([...h.tools.keys()], ["desk_list", "desk_start", "desk_attach", "desk_prompt", "desk_cancel", "desk_end", "desk_history"]);
    assert.equal(h.tools.has("desk_status"), false);
    assert.equal(h.tools.has("desk_detach"), false);
    assert.deepEqual(h.renderers, ["open-deskos-hosted-pi"]);
  } finally { h.restore(); }
});

test("without a Control Credential the machine stays report-only and registers no desk tools", () => {
  const h = harness({ ODK_DESK_LINK_ADDRESS: "127.0.0.1:8765", ODK_DESK_LINK_TOKEN: "report", ODK_DESK_LINK_CONTROL_TOKEN: "" });
  try {
    assert.deepEqual([...h.tools.keys()], []);
    assert.deepEqual(h.renderers, []);
    assert.equal(h.commands.has("open-deskos"), true);
  } finally { h.restore(); }
});

test("session restore accepts the persisted attached identity and last applied position", () => {
  const h = harness({ ODK_DESK_LINK_ADDRESS: "127.0.0.1:8765", ODK_DESK_LINK_TOKEN: "report", ODK_DESK_LINK_CONTROL_TOKEN: "control" });
  try {
    h.hooks.get("session_start")({}, {
      sessionManager: {
        getSessionId() { return "console-a"; },
        getBranch() { return [{ type: "custom", customType: "open-deskos-console-state", data: { sessionId: "hosted-1", attachmentId: "attachment-old", lastApplied: 17 } }]; },
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

test("open-deskos no-argument fallback stays usable without TUI and names stable rows", async () => {
  const h = harness({ ODK_DESK_LINK_ADDRESS: "", ODK_DESK_LINK_TOKEN: "", ODK_DESK_LINK_CONTROL_TOKEN: "" });
  const notices = [];
  try {
    await h.commands.get("open-deskos").handler("", {
      mode: "print",
      hasUI: false,
      cwd: "/workspace",
      ui: { notify(message) { notices.push(message); } },
    });
    assert.match(notices[0], /ODK_DESK_LINK_ADDRESS/);
    assert.match(notices[0], /ODK_DESK_LINK_TOKEN/);
    assert.match(notices[0], /Control Credential|ODK_DESK_LINK_CONTROL_TOKEN/);
  } finally { h.restore(); }
});
