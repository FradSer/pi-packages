// Offline Pi v1.0 fixture for active /matt-pocock menu actions.
import { appendFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage, type ToolCall } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import mattPocock from "../src/index.ts";

function evidencePath(): string {
  const value = process.env.PI_ACTIVE_MENU_EVIDENCE;
  if (!value) throw new Error("the active menu fixture requires an evidence path");
  return value;
}

const evidence = evidencePath();

export default function activeMenuFixture(pi: ExtensionAPI): void {
  mattPocock({
    ...pi,
    appendEntry(customType, data) {
      appendFileSync(evidence, JSON.stringify({ kind: "entry", customType, data }) + "\n");
      pi.appendEntry(customType, data);
    },
    setActiveTools(names) {
      appendFileSync(evidence, JSON.stringify({ kind: "activeTools", names }) + "\n");
      pi.setActiveTools(names);
    },
  });

  const calls: Pick<ToolCall, "name" | "arguments">[] = [
    { name: "matt_pocock_workflow", arguments: { mode: "workflow", route: "hard-bug" } },
  ];
  let index = 0;
  pi.registerProvider("active-menu-live-fixture", {
    api: "active-menu-live-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_ACTIVE_MENU_AUTH,
    models: [{ id: "deterministic", name: "Active menu fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const call = calls[index++];
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: call ? [{ type: "toolCall", id: `active-menu-${index}`, ...call }]
          : [{ type: "text", text: "ACTIVE_MENU_READY" }],
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
    appendFileSync(evidence, JSON.stringify({ kind: "result", tool: event.toolName, ...event.result, isError: event.isError }) + "\n");
  });
}
