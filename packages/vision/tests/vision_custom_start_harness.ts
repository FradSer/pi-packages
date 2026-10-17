import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

const agentDir = process.env.PI_CODING_AGENT_DIR!;
mkdirSync(agentDir, { recursive: true });
writeFileSync(join(agentDir, "vision.json"), JSON.stringify({
  provider: "vision-test", model: "vision", enabled: true,
}));
const { default: visionExtension } = await import("../src/index.ts");
type Handler = (event: unknown, ctx: ExtensionContext) => unknown;
const handlers = new Map<string, Handler>();
let injectedMessages = 0;
visionExtension({
  on: (name: string, handler: Handler) => handlers.set(name, handler),
  registerCommand: () => {},
  sendMessage: () => { injectedMessages++; },
} as unknown as ExtensionAPI);

let visionCalls = 0;
const ctx = {
  hasUI: false,
  model: { input: ["text"] },
  modelRegistry: {
    find: () => ({ provider: "vision-test", id: "vision", input: ["text", "image"] }),
    getApiKeyAndHeaders: async () => ({ ok: true }),
    complete: async () => {
      visionCalls++;
      return { content: [{ type: "text", text: "VISION_RESULT" }] };
    },
  },
} as unknown as ExtensionContext;
const invoke = async (name: string, event: unknown) => {
  const handler = handlers.get(name);
  assert.ok(handler, `Missing registered ${name} handler`);
  return handler(event, ctx);
};
const image = { type: "image", mimeType: "image/png", data: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg==" };
const prompt = "Explain the image";
const userMessage = { role: "user", content: [{ type: "text", text: prompt }, image], timestamp: 1 };
const original = structuredClone(userMessage);
await invoke("before_agent_start", { type: "before_agent_start", messageType: "user", prompt, images: [image] });
const transformed = await invoke("context", { type: "context", messages: [userMessage] });
assert.ok(JSON.stringify(transformed).includes("VISION_RESULT"));
assert.equal(visionCalls, 1);
assert.deepEqual(userMessage, original);

const result = await invoke("before_agent_start", {
  type: "before_agent_start", messageType: "custom",
  message: { customType: "test", content: "Continue", display: false },
});
assert.equal(result, undefined);
assert.equal(await invoke("context", { type: "context", messages: [userMessage] }), undefined);
assert.equal(visionCalls, 1);
assert.deepEqual(userMessage, original);
assert.equal(injectedMessages, 0);
console.log(JSON.stringify({ customStart: "passed", visionCalls, originalImageUnchanged: true }));
