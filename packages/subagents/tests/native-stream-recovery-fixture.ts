/** Native SDK retry boundary; provider callbacks are isolated and deterministic. */
import assert from "node:assert/strict";
import fs from "node:fs";
import { createAssistantMessageEventStream, isRetryableAssistantError, type AssistantMessage } from "@earendil-works/pi-ai";
import { createAgentSession, DefaultResourceLoader, ModelRuntime, SessionManager, SettingsManager } from "@earendil-works/pi-coding-agent";

const error = "stream error: stream disconnected before completion: stream closed before response.completed";
const options = JSON.parse(process.env.PI_STREAM_CASE ?? "{}");
const root = process.env.PI_CODING_AGENT_DIR!;
fs.mkdirSync(root, { recursive: true });
const runtime = await ModelRuntime.create({ authPath: root + "/auth.json", modelsPath: root + "/models.json" });
let attempts = 0;
let settled = 0;
let nativeRetries = 0;
runtime.registerProvider("stream-probe", {
  api: "stream-probe", baseUrl: "http://127.0.0.1", apiKey: "isolated-fixture-only",
  models: [{ id: "fixture", name: "Stream recovery fixture", reasoning: false, input: ["text"], contextWindow: 32000,
    maxTokens: 512, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
  streamSimple(model) {
    attempts++;
    const failed = options.alwaysFail || attempts === 1;
    const message: AssistantMessage = { role: "assistant", api: model.api, provider: model.provider, model: model.id,
      timestamp: Date.now(), content: [{ type: "text", text: failed ? "" : "RECOVERED_FINAL" }],
      stopReason: failed ? "error" : "stop", ...(failed ? { errorMessage: error } : {}),
      usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
    const stream = createAssistantMessageEventStream();
    stream.push({ type: "start", partial: message });
    stream.push(failed ? { type: "error", reason: "error", error: message } : { type: "done", reason: "stop", message });
    return stream;
  },
});
const loader = new DefaultResourceLoader({ cwd: root, agentDir: root, noExtensions: true, noSkills: true,
  noPromptTemplates: true, additionalExtensionPaths: [new URL("../src/stream-recovery.ts", import.meta.url).pathname] });
await loader.reload();
const model = runtime.getModel("stream-probe", "fixture");
assert.ok(model);
const { session } = await createAgentSession({ cwd: root, agentDir: root, modelRuntime: runtime, model,
  resourceLoader: loader, sessionManager: SessionManager.inMemory(), tools: [],
  settingsManager: SettingsManager.inMemory({ retry: { enabled: options.enabled !== false, maxRetries: 1, baseDelayMs: 0 },
    compaction: { enabled: false } }) });
try {
  await session.bindExtensions({});
  session.subscribe(event => { if (event.type === "agent_settled") settled++; if (event.type === "auto_retry_start") nativeRetries++; });
  await session.prompt("Return the fixture result; no tools or additional input.");
  const last = session.messages.filter(message => message.role === "assistant").at(-1) as AssistantMessage;
  console.log(JSON.stringify({ attempts, settled, nativeRetries, finalText: session.getLastAssistantText(), stopReason: last.stopReason,
    diagnostic: last.errorMessage, baselineRetryable: isRetryableAssistantError({ ...last, stopReason: "error", errorMessage: error }),
    userInputs: session.messages.filter(message => message.role === "user").length }));
} finally { session.dispose(); }
