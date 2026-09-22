// Offline Pi prompt-delivery check. No Agent is spawned and no user storage is used.
import assert from "node:assert/strict";
import { createAssistantMessageEventStream, getSystemMessageText, type AssistantMessage, type ToolCall } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import agentTeams from "../src/index.ts";
import mattPocock from "../../matt-pocock/src/index.ts";

export default function (pi: ExtensionAPI): void {
  agentTeams(pi);
  mattPocock(pi);
  let step = 0;
  pi.registerProvider("orchestration-guidance-fixture", {
    api: "orchestration-guidance-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_ORCHESTRATION_AUTH,
    models: [{ id: "deterministic", name: "Orchestration guidance fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model, context) {
      // Providers receive a TranscriptContext: the prompt lives in the transcript's
      // system messages, so replay them in order instead of reading a removed
      // `context.systemPrompt` field.
      const prompt = context.messages.filter(message => message.role === "system").map(getSystemMessageText).join("\n\n");
      assert.ok(prompt, "Pi must deliver the composed system prompt");
      assert.ok(prompt.includes("one integration owner"));
      assert.ok(prompt.includes("yield without declaring completion"));
      assert.ok(prompt.includes("independent reviewer prompt, not a shell command"));
      assert.ok(prompt.includes("does not update the description"));
      assert.ok(prompt.includes("bounded follow-up"));
      const latest = context.messages.filter(message => message.role === "toolResult").at(-1);
      if (latest) {
        assert.equal(latest.isError, false);
        const text = latest.content.filter(part => part.type === "text").map(part => part.text).join("\n");
        if (step === 2) {
          assert.ok(text.includes("one integration owner"));
          assert.ok(text.includes("same candidate"));
        } else if (step === 3) {
          assert.ok(text.includes("one fresh reviewer"));
          assert.ok(text.includes("confirmed conversation"));
          assert.ok(text.includes("root cause"));
          assert.ok(text.includes("Review-only scope"));
          assert.ok(text.includes("without waiting for repairs"));
          assert.ok(text.includes("does not update the description"));
          assert.ok(text.includes("candidate fingerprint"));
        }
      }
      const calls: Pick<ToolCall, "name" | "arguments">[] = [
        { name: "matt_pocock_workflow", arguments: { mode: "workflow", route: "hard-bug" } },
        { name: "matt_pocock_active", arguments: { action: "transition", target: "implement" } },
        { name: "matt_pocock_active", arguments: { action: "transition", target: "code-review" } },
        { name: "matt_pocock_active", arguments: { action: "complete" } },
      ];
      const call = calls[step++];
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: call ? [{ type: "toolCall", id: `orchestration-${step}`, ...call }]
          : [{ type: "text", text: "ORCHESTRATION_PROMPT_DELIVERY_OK" }],
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
}
