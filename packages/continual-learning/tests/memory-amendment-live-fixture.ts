import assert from "node:assert/strict";
import {createAssistantMessageEventStream, getCurrentTools, type AssistantMessage} from "@earendil-works/pi-ai";
import type {ExtensionAPI} from "@earendil-works/pi-coding-agent";

export default function fixture(pi: ExtensionAPI): void {
  pi.registerProvider("amendment-fixture", {
    api: "amendment-fixture", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{id: "fixed", name: "Read-only Memory amendment", reasoning: false, input: ["text"], contextWindow: 200000, maxTokens: 2048, cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0}}],
    streamSimple(model, context) {
      assert.equal(getCurrentTools(context.messages).length, 0);
      const user = context.messages.filter(message => message.role === "user").at(-1);
      const text = typeof user?.content === "string" ? user.content : user?.content.filter(block => block.type === "text").map(block => block.text).join("\n");
      assert.ok(text);
      const data = JSON.parse(text.split("\n").at(-1)!);
      assert.equal(data.repairCandidates.length, 1);
      const candidate = data.repairCandidates[0];
      const prior = data.rejectedPlan[candidate.field][candidate.index];
      const output = {kind: "incremental-memory-amendment", version: 1, ...data.identity,
        replacements: [{candidateId: candidate.candidateId, content: prior.content.replace("Old claim", "Correct claim"), evidence: prior.evidence}]};
      const message: AssistantMessage = {role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: [{type: "text", text: JSON.stringify(output)}], stopReason: "stop",
        usage: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0}}};
      const stream = createAssistantMessageEventStream();
      stream.push({type: "start", partial: message});
      stream.push({type: "done", reason: "stop", message});
      stream.end();
      return stream;
    },
  });
}
