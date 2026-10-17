// Offline Pi v1.0 fixture: inject a real tool-level AbortSignal while Pi's
// selector is open, without sending a keyboard cancellation.
import { appendFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage, type ToolCall } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import mattPocock from "../../src/index.ts";

function evidencePath(): string {
  const value = process.env.PI_ABORT_LIVE_EVIDENCE;
  if (!value) throw new Error("the abort fixture requires an evidence path");
  return value;
}

const evidence = evidencePath();

function mergedAbort(signal: AbortSignal | undefined, delayMs: number): AbortSignal {
  const controller = new AbortController();
  const forward = () => controller.abort();
  signal?.addEventListener("abort", forward, { once: true });
  if (signal?.aborted) controller.abort();
  const timer = setTimeout(() => controller.abort(), delayMs);
  controller.signal.addEventListener("abort", () => {
    clearTimeout(timer);
    signal?.removeEventListener("abort", forward);
  }, { once: true });
  return controller.signal;
}

export default function abortFixture(pi: ExtensionAPI): void {
  mattPocock({
    ...pi,
    registerTool(tool) {
      if (tool.name !== "matt_pocock_ask") {
        pi.registerTool(tool);
        return;
      }
      const execute = tool.execute;
      pi.registerTool({
        ...tool,
        async execute(toolCallId, params, signal, onUpdate, ctx) {
          return execute(toolCallId, params, mergedAbort(signal, 50), onUpdate, ctx);
        },
      });
    },
  });

  const calls: Pick<ToolCall, "name" | "arguments">[] = [
    { name: "matt_pocock_workflow", arguments: { mode: "workflow", route: "hard-bug" } },
    { name: "matt_pocock_ask", arguments: { question: "LIVE programmatic abort", options: ["A", "B"], recommended: "A", timeout_seconds: 30 } },
  ];
  let index = 0;
  pi.registerProvider("abort-live-fixture", {
    api: "abort-live-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_ABORT_LIVE_AUTH,
    models: [{ id: "deterministic", name: "Abort live fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const call = calls[index++];
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: call ? [{ type: "toolCall", id: `abort-live-${index}`, ...call }]
          : [{ type: "text", text: "ABORT_LIVE_READY" }],
        stopReason: call ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: call ? "toolUse" : "stop", message });
      stream.end();
      return stream;
    },
  });
  pi.on("tool_execution_end", (event) => {
    appendFileSync(evidence, JSON.stringify({ tool: event.toolName, ...event.result, isError: event.isError }) + "\n");
  });
}
