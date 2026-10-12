/** Offline provider checks the actual Memory reference delivered by native Pi. */
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import registerMemory from "../extensions/inject-memory.ts";

export default function (pi: ExtensionAPI): void {
  registerMemory(pi);
  pi.registerProvider("memory-retrieval-fixture", {
    api: "memory-retrieval-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_RETRIEVAL_FIXTURE_AUTH,
    models: [{ id: "deterministic", name: "Memory retrieval fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 256, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model, context) {
      const fixture = JSON.parse(readFileSync(new URL("./fixtures/real-memory-retrieval-ranking.json", import.meta.url), "utf8"));
      const text = context.messages.map(message => typeof message.content === "string" ? message.content
        : message.content.filter(part => part.type === "text").map(part => part.text).join("\n")).join("\n");
      const blocks = text.split("\n").filter(line => line.startsWith("{"))
        .map(line => JSON.parse(line)).filter(value => typeof value.body === "string");
      const contract = fixture.entries.find((entry: { filename: string }) => entry.filename === "limit_function_type_contract.md");
      const delivered = blocks.find(value => value.filename === contract.filename);
      assert.ok(delivered, "Actual native Pi request omitted the relevant contract body");
      assert.equal(delivered.body, contract.content);
      assert.equal(delivered.revision, createHash("sha256").update(contract.content).digest("hex"));
      assert.ok(blocks.length <= 3);
      assert.ok(text.includes("untrusted reference data"));
      assert.ok(process.env.PI_RETRIEVAL_FIXTURE_RESULT);
      writeFileSync(process.env.PI_RETRIEVAL_FIXTURE_RESULT, JSON.stringify({
        status: "passed", delivered: blocks.map(value => ({ filename: value.filename, revision: value.revision })),
        completeContractBody: true, remoteRequests: 0, efficacyEstablished: false,
      }));
      const message: AssistantMessage = { role: "assistant", api: model.api, provider: model.provider, model: model.id,
        timestamp: Date.now(), content: [{ type: "text", text: "Memory retrieval fixture passed" }], stopReason: "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: "stop", message });
      stream.end();
      return stream;
    },
  });
}
