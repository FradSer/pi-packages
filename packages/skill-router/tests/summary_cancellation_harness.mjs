import assert from "node:assert/strict";
import { generateCollectionDescription, generateWorkflowSummaries } from "../src/sync.ts";

const mode = process.argv[2];
const controller = new AbortController();
const skills = [{ name: "review", description: "Review project changes carefully before shipping.", path: "/unused" }];
const model = { provider: "test", id: "test" };
let authCalls = 0;
let modelCalls = 0;
const registry = {
  async getApiKeyAndHeaders() {
    authCalls += 1;
    if (mode.endsWith("auth-cancel")) controller.abort();
    return { ok: mode !== "auth-cancel", apiKey: "fixture", headers: {} };
  },
  async complete() {
    modelCalls += 1;
    if (mode !== "provider-abort") controller.abort();
    if (mode === "model-reject" || mode === "provider-abort") throw new DOMException("Cancelled", "AbortError");
    return {
      stopReason: "stop",
      content: [{ type: "text", text: JSON.stringify([
        { skill: "review", summary: "Review project changes carefully and identify concrete issues before shipping." },
      ]) }],
    };
  },
};

if (mode === "pre-aborted") controller.abort();
const generate = mode === "collection-auth-cancel" ? generateCollectionDescription : generateWorkflowSummaries;
await assert.rejects(
  () => generate(registry, mode === "pre-aborted" ? undefined : model, skills, controller.signal),
  { name: "AbortError" },
);
assert.equal(authCalls, mode === "pre-aborted" ? 0 : 1);
assert.equal(modelCalls, mode === "pre-aborted" || mode.endsWith("auth-cancel") ? 0 : 1);
console.log("ok");
