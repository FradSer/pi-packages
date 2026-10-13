import fs from "node:fs";
import path from "node:path";
import assert from "node:assert/strict";
import {createAssistantMessageEventStream, getCurrentTools, type AssistantMessage} from "@earendil-works/pi-ai";
import type {ExtensionAPI} from "@earendil-works/pi-coding-agent";
import {registerPlannerRead} from "../extensions/planner-read-scope.ts";

export default function(pi: ExtensionAPI): void {
  registerPlannerRead(pi, {cwd: process.cwd(), roots: [process.cwd()], files: [], excludedComponents: [".memory", ".pi", "node_modules"]}, async read => {
    pi.appendEntry("maintenance-reader-observed", {sourceSha256: read.sha256, error: read.error, result: read.result});
  }, 2);
  let calls = 0;
  pi.registerProvider("maintenance-reader-fixture", {
    api: "maintenance-reader-fixture", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{id: "deterministic", name: "Maintenance reader fixture", reasoning: false, input: ["text"], contextWindow: 200000, maxTokens: 256,
      cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0}}],
    streamSimple(model, context) {
      calls += 1;
      const tools = getCurrentTools(context.messages).map(tool => tool.name);
      pi.appendEntry("maintenance-reader-provider", {call: calls, tools});
      assert.deepEqual(tools, calls === 1 ? ["learning_read"] : []);
      assert.ok(calls <= 2);
      const message: AssistantMessage = {role: "assistant", api: model.api, provider: model.provider, model: model.id,
        content: calls === 1 ? Array.from({length: process.env.MAINTENANCE_READER_OVERFLOW === "1" ? 3 : 2}, (_, index) => ({type: "toolCall" as const, id: `source-${index}`, name: "learning_read", arguments: {path: path.join(process.cwd(), "runtime.ts")}}))
          : [{type: "text", text: "Scoped source reads finished."}],
        stopReason: calls === 1 ? "toolUse" : "stop", usage: {input: 1, output: 1, cacheRead: 0, cacheWrite: 0, totalTokens: 2,
          cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0}}, timestamp: Date.now()};
      const stream = createAssistantMessageEventStream();
      stream.push({type: "start", partial: message});
      stream.push({type: "done", reason: message.stopReason, message});
      stream.end();
      return stream;
    },
  });
}
