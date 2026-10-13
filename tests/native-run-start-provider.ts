/** Offline provider captures the actual Pi transcript without changing prompt sections. */
import { appendFileSync } from "node:fs";
import { createAssistantMessageEventStream, getCurrentSystemPrompt } from "@earendil-works/pi-ai";
import type { AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI): void {
  const emit = (value: unknown) => appendFileSync(process.env.PI_NATIVE_EVIDENCE!, JSON.stringify(value) + "\n");
  let calls = 0;
  pi.on("before_agent_start", event => {
    calls = 0;
    emit({ kind: "start", messageType: event.messageType, prompt: event.prompt,
      options: event.systemPromptOptions });
  });
  pi.registerCommand("fixture-custom", {
    description: "Start the isolated offline acceptance run",
    handler: async (_args, ctx) => {
      pi.sendMessage({ customType: "offline-acceptance-start", content: "fixture-needle", display: false },
        { triggerTurn: true });
      await ctx.waitForIdle();
    },
  });
  pi.registerProvider("native-run-start", {
    api: "native-run-start", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{ id: "deterministic", name: "Offline run-start acceptance", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 256, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model, context) {
      calls++;
      emit({ kind: "request", call: calls, context, currentSystemPrompt: getCurrentSystemPrompt(context.messages) });
      if (calls > 3) throw new Error("Unexpected acceptance continuation");
      const content: AssistantMessage["content"] = calls < 3
        ? [{ type: "toolCall", id: `fixture-read-${calls}`, name: "read", arguments: { path: "fixture.txt" } }]
        : [{ type: "text", text: "Offline native run-start acceptance complete" }];
      const message: AssistantMessage = { role: "assistant", api: model.api, provider: model.provider, model: model.id,
        timestamp: Date.now(), content, stopReason: calls < 3 ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: message.stopReason, message });
      stream.end();
      return stream;
    },
  });
}
