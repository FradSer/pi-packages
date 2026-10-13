import fs from "node:fs";
import {createAssistantMessageEventStream, type AssistantMessage} from "@earendil-works/pi-ai";
import type {ExtensionAPI} from "@earendil-works/pi-coding-agent";

export default function(pi: ExtensionAPI): void {
  let calls = 0;
  pi.on("message_end", (event, ctx) => {
    if(event.message.role === "assistant")fs.appendFileSync(process.env.PI_COLLECTION_EVENTS!, JSON.stringify({stopReason:event.message.stopReason,errorMessage:event.message.errorMessage,signalAborted:ctx.signal?.aborted})+"\n");
  });
  if (process.env.PI_COLLECTION_OPENAI_URL) {
    pi.registerProvider("maintenance-collector-fixture", {
      api: "openai-completions", baseUrl: process.env.PI_COLLECTION_OPENAI_URL, apiKey: "offline-fixture",
      models: [{id: "deterministic", name: "Maintenance collector OpenAI fixture", reasoning: false, input: ["text"], contextWindow: 200000, maxTokens: 4096,
        cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0}}],
    });
    return;
  }
  pi.registerProvider("maintenance-collector-fixture", {
    api: "maintenance-collector-fixture", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{id: "deterministic", name: "Maintenance collector fixture", reasoning: false, input: ["text"], contextWindow: 200000, maxTokens: 256,
      cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0}}],
    streamSimple(model) {
      calls++;
      fs.appendFileSync(process.env.PI_COLLECTION_EVENTS!, JSON.stringify({providerCall: calls}) + "\n");
      const message: AssistantMessage = {role: "assistant", api: model.api, provider: model.provider, model: model.id,
        content: Array.from({length: process.env.PI_COLLECTION_OVERFLOW === "1" ? 19 : 18}, (_, index) => ({type: "toolCall" as const, id: `source-${calls}-${index}`, name: "learning_read", arguments: {path: process.env.PI_COLLECTION_MISSING_ONCE === "1" && index === 0 ? process.env.PI_COLLECTION_SOURCE! + ".missing" : process.env.PI_COLLECTION_SOURCE!}})),
        stopReason: "toolUse", usage: {input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2,
          cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0}}, timestamp: Date.now()};
      const stream = createAssistantMessageEventStream();
      stream.push({type: "start", partial: message});
      stream.push({type: "done", reason: "toolUse", message});
      stream.end();
      return stream;
    },
  });
}
