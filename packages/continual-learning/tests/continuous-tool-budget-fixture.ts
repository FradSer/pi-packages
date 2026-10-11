import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { createAssistantMessageEventStream, getCurrentTools, type AssistantMessage } from "@earendil-works/pi-ai";
import { installStudyToolBudget } from "./continuous-tool-budget.ts";

export default function fixture(pi: ExtensionAPI): void {
  installStudyToolBudget(pi, 2);
  let calls = 0;
  pi.registerProvider("study-budget-fixture", {
    api: "study-budget-fixture", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{ id: "deterministic", name: "Study budget fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model, context) {
      calls++;
      pi.appendEntry("study-budget-provider", { call: calls, tools: getCurrentTools(context.messages).map(tool => tool.name) });
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: calls === 1 || process.env.STUDY_BUDGET_REPEAT_TOOLS === "1" ? (calls === 1 ? ["one", "two", "forbidden"] : ["forbidden"]).map(name => ({
          type: "toolCall" as const, id: name, name: "bash", arguments: { command: `printf observed > ${name}` },
        })) : [{ type: "text", text: "Summarized existing observations." }],
        stopReason: calls === 1 || process.env.STUDY_BUDGET_REPEAT_TOOLS === "1" ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: message.stopReason, message });
      stream.end();
      return stream;
    },
  });
}
