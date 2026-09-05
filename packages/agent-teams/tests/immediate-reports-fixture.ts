import assert from "node:assert/strict";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import agentTeams from "../src/index.ts";
import { drainTeammateOutboxes } from "../src/team-machine.ts";
import { registerTeammate } from "../src/state.ts";
import { appendWorkerEvent, stateFilePath, workerOutboxPath } from "../src/statefile.ts";

export default function (pi: ExtensionAPI): void {
  agentTeams(pi);
  let calls = 0;
  let settled = false;
  let checked = false;
  const received: string[] = [];

  pi.registerProvider("report-fixture", {
    api: "report-fixture",
    baseUrl: "http://127.0.0.1",
    apiKey: process.env.PI_REPORT_FIXTURE_AUTH,
    models: [{
      id: "deterministic", name: "Deterministic report fixture", reasoning: false,
      input: ["text"], contextWindow: 200000, maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    }],
    streamSimple(model) {
      calls++;
      const content: AssistantMessage["content"] = calls === 1
        ? [{ type: "toolCall", id: "produce", name: "produce_reports", arguments: {} }]
        : calls <= 3
          ? [{ type: "toolCall", id: `check-${calls}`, name: "check_reports", arguments: {} }]
          : [{ type: "text", text: checked ? "PI_IMMEDIATE_REPORTS_OK" : "PI_IMMEDIATE_REPORTS_FAILED" }];
      const output: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id,
        timestamp: Date.now(), content, stopReason: calls <= 3 ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: output });
      stream.push({ type: "done", reason: calls <= 3 ? "toolUse" : "stop", message: output });
      stream.end();
      return stream;
    },
  });

  pi.on("agent_settled", () => { settled = true; });
  pi.on("message_end", (event) => {
    const message = event.message;
    if (message.role !== "custom" || message.customType !== "agent-teams-report") return;
    const details = message.details as { eventId: string };
    received.push(details.eventId);
  });

  pi.registerTool({
    name: "produce_reports", label: "Produce reports", description: "Exercise the real report outbox during a tool call.",
    parameters: Type.Object({}),
    async execute(_id, _params, _signal, _update, ctx) {
      registerTeammate({ name: "fixture-worker", agent: "fixture", spawnId: "fixture-spawn",
        pid: 0, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 });
      const outbox = workerOutboxPath(stateFilePath(ctx.sessionManager.getSessionFile(), ctx.cwd), "fixture-worker", "fixture-spawn");
      for (const [id, status] of [["progress", "in_progress"], ["terminal", "completed"]] as const) {
        appendWorkerEvent(outbox, { id, type: "message", worker: "fixture-worker", spawnId: "fixture-spawn",
          body: id === "progress" ? "New evidence" : "Completed with verification", status, timestamp: 100 });
        drainTeammateOutboxes();
      }
      assert.deepEqual(received, [], "Reports must not split an in-flight tool call and its result");
      return { content: [{ type: "text", text: "Reports produced" }], details: {} };
    },
  });

  pi.registerTool({
    name: "check_reports", label: "Check reports", description: "Verify all reports reached context before the leader settles.",
    parameters: Type.Object({}),
    async execute(_id, _params, _signal, _update, ctx) {
      const entries = ctx.sessionManager.getEntries();
      const ids = entries.flatMap((entry) => entry.type === "custom_message" && entry.customType === "agent-teams-report"
        ? [(entry.details as { eventId: string }).eventId] : []);
      const expected = calls === 2 ? ["progress"] : ["progress", "terminal"];
      assert.deepEqual(ids, expected);
      assert.deepEqual(received, expected);
      assert.equal(settled, false, "Reports must arrive before agent_settled");
      checked = calls === 3;
      return { content: [{ type: "text", text: "All reports reached the active leader" }], details: {} };
    },
  });
}
