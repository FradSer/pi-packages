// Offline Pi v1.0 fixture for the interactive decision contract.
// The provider is deterministic; no model request or user authentication is used.
import { appendFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage, type ToolCall } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import mattPocock from "../src/index.ts";

function requireSnapshotPath(): string {
  const value = process.env.PI_DECISION_LIVE_SNAPSHOTS;
  if (!value) throw new Error("the decision fixture requires a snapshot path");
  return value;
}

const resultFile = requireSnapshotPath();

export default function decisionFixture(pi: ExtensionAPI): void {
  mattPocock({
    ...pi,
    registerTool(tool) {
      const renderResult = tool.renderResult;
      if (!renderResult) throw new Error(`Missing renderer for ${tool.name}`);
      pi.registerTool({ ...tool, renderResult });
    },
  });

  const calls: Pick<ToolCall, "name" | "arguments">[] = [
    { name: "matt_pocock_workflow", arguments: { mode: "workflow", route: "hard-bug" } },
    { name: "matt_pocock_ask", arguments: { question: "LIVE selection", options: ["A", "B"] } },
    { name: "matt_pocock_ask", arguments: { question: "LIVE custom", options: ["A", "B"] } },
    { name: "matt_pocock_ask", arguments: { question: "LIVE blank custom", options: ["A", "B"] } },
    { name: "matt_pocock_ask", arguments: { question: "LIVE escape", options: ["A", "B"] } },
    { name: "matt_pocock_ask", arguments: { question: "LIVE timeout without recommendation", options: ["A", "B"], timeout_seconds: 0.05 } },
    { name: "matt_pocock_ask", arguments: { question: "LIVE abort", options: ["A", "B"], recommended: "A", timeout_seconds: 30 } },
    { name: "matt_pocock_ask", arguments: {
      question: "LIVE recommendation timeout",
      options: ["(Recommended) Use adjacent verification", "Block for review"],
      recommended: "(Recommended) Use adjacent verification",
      timeout_seconds: 0.05,
    } },
    { name: "matt_pocock_active", arguments: { action: "complete" } },
  ];
  let index = 0;
  pi.registerProvider("decision-live-fixture", {
    api: "decision-live-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_DECISION_LIVE_AUTH,
    models: [{ id: "deterministic", name: "Decision live fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const call = calls[index++];
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: call ? [{ type: "toolCall", id: `decision-${index}`, ...call }]
          : [{ type: "text", text: "MP_DECISION_LIVE_READY" }],
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
    appendFileSync(resultFile, JSON.stringify({ kind: "result", tool: event.toolName, ...event.result, isError: event.isError }) + "\n");
  });
}
