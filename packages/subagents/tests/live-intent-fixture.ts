/** Real native parent and RPC child exercise busy continuation through intent tools. */
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage, type ToolCall } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { IntentToolData } from "../src/intent-tools.ts";
import extension from "../src/extension.ts";
import { listAgents, observeAgentRoster } from "../src/roster.ts";

export default function (pi: ExtensionAPI): void {
  let request = 0;
  let handle = "";
  const receipts: Array<IntentToolData & { isError: boolean }> = [];
  const notices: Array<{ inputId?: string; text?: string; kind?: string }> = [];
  const controls: Array<{ tool: string; isError: boolean; details: IntentToolData }> = [];
  const stopPending = process.env.PI_INTENT_CASE === "stop-pending";
  const savedIdentity = process.env.PI_INTENT_CASE === "saved-identity";
  const steering = process.env.PI_INTENT_CASE === "steer";
  const rejectStop = process.env.PI_INTENT_CASE === "rejected-stop";
  let finish!: () => void;
  const results = new Promise<void>(resolve => { finish = resolve; });
  const settledInputs = new Set<string>();
  const unobserve = observeAgentRoster(() => {
    for (const child of listAgents()) {
      if (child.inputId && child.resultKind === "result" && child.sequenceEnded) settledInputs.add(child.inputId);
    }
    if (settledInputs.size >= (steering ? 1 : 2)) finish();
  });
  // Configured mode loads the package from settings and its real manifest.
  if (process.env.PI_INTENT_CONFIGURED !== "1") extension(pi);
  pi.on("message_end", event => {
    const message = event.message;
    if (message.role === "custom" && (message.customType === "subagents-session-result" || message.customType === "subagents-input-cancelled")) {
      notices.push(message.details as { inputId?: string; text?: string; kind?: string });
    }
  });
  pi.on("tool_result", event => {
    if (event.toolName === "agent_start" || event.toolName === "agent_input") {
      const data = event.details as IntentToolData;
      if (typeof data.session === "string") handle = data.session;
      receipts.push({ ...data, isError: event.isError === true });
    } else if (event.toolName === "agent_stop" || event.toolName === "agent_list" || event.toolName === "agent_list") {
      // Pi catches handler assertions. Always retain the real control outcome;
      // the outer test, not this extension callback, owns pass/fail.
      controls.push({ tool: event.toolName, isError: event.isError === true, details: event.details as IntentToolData });
    }
  });
  pi.on("session_shutdown", () => {
    unobserve();
    const evidence = process.env.PI_INTENT_EVIDENCE;
    if (evidence) writeFileSync(evidence, JSON.stringify({ receipts, notices, controls, activeTools: pi.getActiveTools() }));
  });
  pi.registerProvider("intent-parent", {
    api: "intent-parent", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_INTENT_AUTH,
    models: [{ id: "scripted", name: "Intent parent fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const stream = createAssistantMessageEventStream();
      const index = request++;
      const call: ToolCall | undefined = index === 0
        ? { type: "toolCall", id: "start", name: "agent_start", arguments: {
            prompt: "FIRST INPUT", label: process.env.PI_INTENT_LABEL ?? "native-intent", tools: [], model: "intent-loopback/fixture",
            ...(savedIdentity ? {identity:"native-saved"} : {}) } }
        : index === 1 ? { type: "toolCall", id: "next", name: "agent_input", arguments: {
            session: handle, prompt: steering ? "STEER_INPUT" : "SECOND INPUT", delivery: steering ? "steer" : "next" } }
          : index === 2 ? { type: "toolCall", id: "stop", name: "agent_stop", arguments: { session: rejectStop ? `${handle}-not-current` : handle } }
            : stopPending && index === 3 ? { type: "toolCall", id: "inspect", name: "agent_list", arguments: { session: handle } }
              : stopPending && index === 4 ? { type: "toolCall", id: "list", name: "agent_list", arguments: {} } : undefined;
      void (async () => {
        if (index === 2 && !stopPending) await results;
        const message: AssistantMessage = { role: "assistant", api: model.api, provider: model.provider, model: model.id,
          timestamp: Date.now(), content: call ? [call] : [{ type: "text", text: "NATIVE_INTENT_OK" }],
          stopReason: call ? "toolUse" : "stop", usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
        stream.push({ type: "start", partial: message });
        stream.push({ type: "done", reason: message.stopReason, message });
      })().catch(error => { stream.end(); console.error(error); });
      return stream;
    },
  });
}
