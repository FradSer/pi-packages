/** Real parent Pi; unsafe resume refuses before any OS RPC child is spawned. */
import assert from "node:assert/strict";
import childProcess, { type ChildProcess } from "node:child_process";
import { writeFileSync } from "node:fs";
import path from "node:path";
import { syncBuiltinESMExports } from "node:module";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import extension from "../packages/subagents/src/extension.ts";
import { INTENT_TOOL_NAMES, type IntentToolName } from "../packages/subagents/src/intent-tools.ts";

// Pi reifies this import at extension load; shared root development cohort.
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
export default function (pi: ExtensionAPI): void {
  // This fixture verifies the supported legacy model interface.
  const nativeGetFlag = pi.getFlag.bind(pi);
  const root = process.env.PI_HISTORY_SAFETY_ROOT; assert.ok(root);
  let spawns = 0, request = 0, refused = false, outsideInContext = false, code: string | undefined;
  const originalSpawn = childProcess.spawn;
  const observedSpawn = (...args: Parameters<typeof childProcess.spawn>): ChildProcess => {
    if (Array.isArray(args[1]) && args[1].includes("rpc")) spawns++;
    return Reflect.apply(originalSpawn, childProcess, args);
  };
  childProcess.spawn = observedSpawn as typeof childProcess.spawn;
  syncBuiltinESMExports(); extension(pi);
  pi.on("tool_result", event => {
    if (!INTENT_TOOL_NAMES.includes(event.toolName as IntentToolName)) return;
    const details = event.details as { ok?: boolean; code?: string; error?: string } | undefined;
    refused = details?.ok === false;
    code = details?.code;
    assert.ok(refused && event.isError, JSON.stringify(event.details));
    // The refusal has to come from the private-history guard itself. A missing
    // identity would refuse the same call without ever reading the linked file.
    const diagnostic = details?.error ?? "";
    assert.ok(diagnostic.includes("Refusing linked or non-regular private history"), diagnostic);
  });
  pi.on("session_shutdown", () => { childProcess.spawn = originalSpawn; syncBuiltinESMExports();
    writeFileSync(path.join(root, "safety-evidence.json"), JSON.stringify({ spawns, refused, outsideInContext, code })); });
  pi.registerProvider("history-safety-fixture", { api: "history-safety-fixture", baseUrl: "http://127.0.0.1",
    apiKey: process.env.PI_HISTORY_SAFETY_AUTH, models: [{ id: "scripted", name: "History safety", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model, context) {
      outsideInContext ||= JSON.stringify(context.messages).includes("OUTSIDE_PRIVATE_SENTINEL");
      const index = request++; const message: AssistantMessage = { role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: 1,
        content: index === 0 ? [{ type: "toolCall", id: "unsafe-start", name: "agent_start",
          arguments: { identity: "unsafe-reader", prompt: "Resume your own private history." } }]
          : [{ type: "text", text: "HISTORY_SAFETY_REFUSED" }],
        stopReason: index === 0 ? "toolUse" : "stop", usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
      const stream = createAssistantMessageEventStream(); stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: index === 0 ? "toolUse" : "stop", message }); stream.end(); return stream;
    }
  });
}