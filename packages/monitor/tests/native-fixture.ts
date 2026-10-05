/** Explicit native acceptance fixture: scripted in-process provider, zero network. */
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import assert from "node:assert/strict";
import { convertResponsesMessages } from "@earendil-works/pi-ai/api/openai-responses-shared";
import { appendFileSync } from "node:fs";
import { stripVTControlCharacters } from "node:util";
import monitor from "../src/index.ts";

export default function (pi: ExtensionAPI): void {
  let step = 0;
  const trace = (event: object) => {
    if (process.env.PI_MONITOR_NATIVE_TRACE) appendFileSync(process.env.PI_MONITOR_NATIVE_TRACE, JSON.stringify({ at: Date.now(), ...event }) + "\n");
  };
  const send = pi.sendMessage.bind(pi);
  pi.sendMessage = (message, options) => { trace({ kind: "send", message, options }); send(message, options); };
  pi.on("session_start", (_event, ctx) => {
    trace({ kind: "session", mode: ctx.mode });
    if (ctx.mode !== "tui") return;
    const custom = ctx.ui.custom.bind(ctx.ui);
    ctx.ui.custom = (factory, options) => custom((tui, theme, keys, done) => {
      const component = factory(tui, theme, keys, done);
      return Promise.resolve(component).then((value) => {
        const render = value.render.bind(value);
        value.render = (width) => {
          const lines = render(width);
          trace({ kind: "frame", width, rows: tui.terminal.rows, lines: lines.map(stripVTControlCharacters) });
          return lines;
        };
        const handle = value.handleInput?.bind(value);
        value.handleInput = (key) => { trace({ kind: "key", key }); handle?.(key); };
        return value;
      });
    }, options);
  });
  monitor(pi);
  pi.registerTool({ name: "fixture_foreign", label: "Fixture read", description: "Offline foreign tool", parameters: Type.Object({}),
    execute: async () => ({ content: [{ type: "text", text: "FOREIGN_TOOL_OK" }], details: {} }) });
  pi.on("tool_result", (event) => { trace({ kind: "tool_result", event, activeTools: pi.getActiveTools() }); });
  pi.registerProvider("monitor-offline", {
    api: "monitor-offline", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{ id: "scripted", name: "Offline monitor fixture", reasoning: false, input: ["text"], contextWindow: 200000,
      maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model, context) {
      const current = step++;
      const input = convertResponsesMessages(model, context, new Set([model.provider]));
      const marked = structuredClone(context);
      for (const message of marked.messages) if (message.role === "toolResult") {
        Object.assign(message, { details: { startConfiguration: { command: "START_UI_ONLY_MARKER", cwd: "START_UI_ONLY_MARKER" } } });
      }
      assert.deepEqual(convertResponsesMessages(model, marked, new Set([model.provider])), input);
      assert.ok(!JSON.stringify(input).includes("startConfiguration"));
      trace({ kind: "request", step: current, messages: context.messages, activeTools: pi.getActiveTools() });
      const values = process.env.PI_MONITOR_NATIVE_CASE === "tui-values";
      const tui = process.env.PI_MONITOR_NATIVE_CASE === "tui" || values;
      const command = values
        ? `node -e 'console.log("DONE " + JSON.stringify({body:"a".repeat(24000)+String.fromCharCode(80,65,89,76,79,65,68,95,69,78,68),ok:true}))'`
        : tui
        ? "i=0; while [ $i -lt 80 ]; do printf 'diagnostic-%s\\n' \"$i\"; i=$((i+1)); done; sleep 0.5; exit 1"
        : "printf 'PRIVATE_PROGRESS\\n'; sleep 0.7; printf 'DONE_NATIVE\\n'";
      const content: AssistantMessage["content"] = current === 0 ? [
        { type: "toolCall", id: "native-monitor", name: "monitor_start", arguments: {
          command, description: "native acceptance", result_pattern: values ? "DONE (?<json>.*)" : tui ? "NEVER_MATCHES" : "DONE_NATIVE", timeout_ms: 4000,
          ...(values ? { completion: "exit" } : {}),
        } },
        ...(process.env.PI_MONITOR_NATIVE_CASE === "mixed" ? [{ type: "toolCall" as const, id: "native-foreign", name: "fixture_foreign", arguments: {} }] : []),
      ] : [{ type: "text", text: "MONITOR_NATIVE_READY" }];
      const message: AssistantMessage = { role: "assistant", api: model.api, provider: model.provider, model: model.id,
        timestamp: Date.now(), content, stopReason: current === 0 ? "toolUse" : "stop",
        usage: { input: 10, output: 5, cacheRead: 0, cacheWrite: 0, totalTokens: 15,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: message.stopReason as "stop" | "toolUse", message });
      stream.end();
      return stream;
    },
  });
}
