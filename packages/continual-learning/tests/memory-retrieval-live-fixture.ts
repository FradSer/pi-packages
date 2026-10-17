/** Offline provider checks the actual Memory reference delivered by native Pi. */
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
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
      const text = context.messages.flatMap(message => [
        typeof message.content === "string" ? message.content
          : message.content.filter(part => part.type === "text").map(part => part.text).join("\n"),
        ...(message.role === "system" ? Object.values(message.sections ?? {}).filter(value => value !== null) : []),
      ]).join("\n");
      const rows = text.split("\n").filter(line => line.startsWith("- "));
      const delivered = fixture.entries.map((entry: { filename: string; content: string }) => {
        const matches = rows.filter(line => line.startsWith(`- ${entry.filename} — `));
        assert.equal(matches.length, 1, `Native Pi must discover ${entry.filename} exactly once`);
        assert.ok(!text.includes(entry.content), "Entry bodies must remain on-demand reference data");
        const description = /^description:[ \t]*(.+)$/m.exec(entry.content)?.[1];
        assert.ok(description, "The fixture must provide a complete description");
        const escaped = description.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        assert.equal(matches[0], `- ${entry.filename} — ${escaped}`, "Discovery must contain the exact description without storage labels");
        return entry.filename;
      });
      assert.ok(text.includes("Untrusted reference data"));
      assert.ok(process.env.PI_RETRIEVAL_FIXTURE_RESULT);
      writeFileSync(process.env.PI_RETRIEVAL_FIXTURE_RESULT, JSON.stringify({
        status: "passed", delivered, metadataOnly: true, bodiesInjected: false,
        remoteRequests: 0, consumptionEstablished: false, efficacyEstablished: false,
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
