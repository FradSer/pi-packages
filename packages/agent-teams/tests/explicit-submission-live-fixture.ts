import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { createAssistantMessageEventStream } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { assistant } from "./automatic-results-fixture.ts";
import { readJsonlBatch } from "../src/statefile.ts";
import { registerWorkerCapabilities, workerBinding } from "../src/worker.ts";

export default function (pi: ExtensionAPI): void {
  registerWorkerCapabilities(pi);
  const binding = workerBinding()!;
  let calls = 0;
  pi.registerProvider("explicit-submission-fixture", {
    api: "explicit-submission-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_SUBMISSION_AUTH,
    models: [{ id: "deterministic", name: "Explicit submission fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple() {
      calls++;
      assert.equal(calls, 1, "Explicit submission must terminate before another model request");
      const message = assistant("", "toolUse", Date.now());
      message.content = [{ type: "toolCall", id: "submit-1", name: "work",
        arguments: { action: "submit", outcome: process.env.PI_SUBMISSION_OUTCOME ?? "success", result: "Native submission evidence" } }];
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: "toolUse", message });
      stream.end();
      return stream;
    },
  });
  pi.on("agent_settled", (_event, ctx) => {
    assert.equal(ctx.isIdle(), true);
    assert.equal(calls, 1);
    assert.deepEqual(readJsonlBatch(binding.outbox, 0).records, []);
    assert.deepEqual(readdirSync(binding.submissionsDir), ["work-1.json"]);
    const submission = JSON.parse(readFileSync(`${binding.submissionsDir}/work-1.json`, "utf8"));
    assert.equal(submission.assignmentId, "attempt-1");
    assert.equal(submission.result, "Native submission evidence");
    console.log("NATIVE_EXPLICIT_SUBMISSION_OK");
  });
}
