/** Native Pi delegates twice; the first unusable result must be explicit, not blank. */
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage, type ToolCall } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import extension from "../packages/subagents/src/extension.ts";
import { getAgent, livingAgents } from "../packages/subagents/src/roster.ts";
import type { SessionNotice } from "../packages/subagents/src/session-result.ts";

export default function(pi: ExtensionAPI): void {
  // This fixture verifies the supported legacy model interface.
  const nativeGetFlag = pi.getFlag.bind(pi);
  const evidence = process.env.PI_UNANSWERED_EVIDENCE;
  assert.ok(evidence, "An isolated evidence path is required");
  let request = 0;
  let handle: string | undefined;
  let closed = false;
  const notices: SessionNotice[] = [];
  const resolvers: Array<() => void> = [];
  const outcomes = [0, 1].map(() => new Promise<void>(resolve => resolvers.push(resolve)));
  extension({ ...pi, sendMessage(message, options) {
    if (message.customType === "subagents-session-unanswered" || message.customType === "subagents-session-result") {
      const notice = message.details as SessionNotice;
      assert.ok(notices.length < 2, "No duplicate terminal notices or automatic model retry");
      notices.push(notice);
      resolvers[notices.length - 1]();
    }
    pi.sendMessage(message, options);
  } });
  pi.on("tool_result", event => {
    if (!event.toolName.startsWith("agent_")) return;
    const details = event.details as { ok?: boolean; operation?: string; session?: string };
    assert.equal(details.ok, true, JSON.stringify(event.content));
    if (details.operation === "agent_start") handle = details.session;
    if (details.operation === "agent_stop") closed = true;
  });
  pi.on("session_shutdown", () => writeFileSync(evidence, JSON.stringify({ notices, closed,
    living: livingAgents().length, sameHandle: notices.every(notice => notice.session === handle) })));
  pi.registerProvider("unanswered-parent", {
    api: "unanswered-parent", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_UNANSWERED_AUTH,
    models: [{ id: "scripted", name: "Unanswered native reproduction", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const index = request++;
      const session = () => { assert.ok(handle); return handle; };
      let call: ToolCall | undefined;
      // A temporary label is display only, so the roster name is read from the exact
      // route the start receipt returned rather than from what the model asked for.
      const child = () => { assert.ok(handle?.startsWith("session:")); return getAgent(handle.slice(8).split(":")[0]!); };
      if (index === 0) call = { type: "toolCall", id: "first", name: "agent_start", arguments: {
        label: "reviewer", prompt: "Read-only short fork review", tools: [], model: "unanswered-loopback/reviewer" } };
      if (index === 2) {
        assert.equal(child()?.status, "idle");
        call = { type: "toolCall", id: "send", name: "agent_input", arguments: {
          session: session(), prompt: "Return a short explicit final answer", delivery: "next" } };
      }
      if (index === 4) call = { type: "toolCall", id: "stop", name: "agent_stop", arguments: { session: session() } };
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: call ? [call] : [{ type: "text", text: index === 5 ? "UNANSWERED_REPRO_DONE" : "Input accepted" }],
        stopReason: call ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      const emit = () => {
        stream.push({ type: "start", partial: message });
        stream.push({ type: "done", reason: call ? "toolUse" : "stop", message });
        stream.end();
      };
      if (index === 1 || index === 3) void outcomes[index === 1 ? 0 : 1].then(emit);
      else emit();
      return stream;
    },
  });
}
