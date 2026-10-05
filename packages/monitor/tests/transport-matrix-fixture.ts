/** Native offline provider; scripted outcomes exercise Pi, never model reasoning. */
import assert from "node:assert/strict";
import { appendFileSync, readFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import monitor from "../src/index.ts";

export default function (pi: ExtensionAPI): void {
  const spec = JSON.parse(readFileSync(process.env.MONITOR_TRANSPORT_SPEC!, "utf8"));
  const trace = (event: object) => appendFileSync(process.env.MONITOR_TRANSPORT_TRACE!, JSON.stringify(event) + "\n");
  const send = pi.sendMessage.bind(pi);
  pi.sendMessage = (message, options) => { trace({ kind: "send", message }); send(message, options); };
  monitor(pi);
  pi.registerTool({ name: "transport_foreign", label: "Fixture", description: "Local offline fixture",
    parameters: Type.Object({}), execute: async () => ({ content: [{ type: "text", text: "FOREIGN_OK" }], details: {} }) });
  pi.registerTool({ name: "transport_nested", label: "Nested fixture", description: "Local nested fixture",
    parameters: Type.Object({ job: Type.Integer() }),
    async execute(_id, args, signal, _update, ctx) {
      const receipt = await ctx.executeTool("monitor_start", spec.jobs[args.job], { signal });
      const value = receipt.result.structuredContent;
      assert.ok(value && typeof value === "object" && "status" in value);
      assert.equal(value.status, spec.expected[args.job]);
      trace({ kind: "nested", result: value });
      return { content: [{ type: "text", text: JSON.stringify({ status: value.status }) }], details: {} };
    },
  });
  pi.on("tool_result", event => { trace({ kind: "tool_result", event }); });
  let step = 0;
  pi.registerProvider("monitor-transport-offline", {
    api: "monitor-transport-offline", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{ id: "scripted", name: "Transport matrix", reasoning: false, input: ["text"], contextWindow: 200000,
      maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model, context) {
      const current = step++;
      trace({ kind: "request", step: current, messages: context.messages });
      let content: AssistantMessage["content"] = [{ type: "text", text: "TRANSPORT_MATRIX_READY" }];
      if (current === 0) {
        if (spec.route === "nested") content = [{ type: "toolCall", id: "nested-parent", name: "transport_nested", arguments: { job: 0 } }];
        else if (spec.route === "codemode") content = [{ type: "toolCall", id: "script-parent", name: "codemode", arguments: { code: `
          const outcomes = await Promise.all(${JSON.stringify(spec.jobs)}.map(args => tools.monitor_start(args)));
          const expected = ${JSON.stringify(spec.expected)};
          for (let i = 0; i < outcomes.length; i++) {
            if (outcomes[i].status !== expected[i]) throw new Error('wrong terminal status');
            if (outcomes[i].result.resultParseError) throw new Error('invalid sentinel JSON');
          }
          text(outcomes.map(value => ({status:value.status, result:value.result.result ?? null})));
        ` } }];
        else content = [
          ...spec.jobs.map((args: object, index: number) => ({ type: "toolCall" as const, id: `direct-${index}`, name: "monitor_start", arguments: args })),
          ...(spec.route === "mixed" ? [{ type: "toolCall" as const, id: "foreign", name: "transport_foreign", arguments: {} }] : []),
        ];
      } else if (spec.route === "stop" && current === 1) content = [{ type: "toolCall", id: "stop-call", name: "monitor_stop", arguments: {} }];
      const isCall = content.some(block => block.type === "toolCall");
      const message: AssistantMessage = { role: "assistant", content, api: model.api, provider: model.provider, model: model.id,
        timestamp: Date.now(), stopReason: isCall ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: message.stopReason as "stop" | "toolUse", message });
      stream.end();
      return stream;
    },
  });
}
