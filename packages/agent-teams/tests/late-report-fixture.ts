import assert from "node:assert/strict";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import agentTeams from "../src/index.ts";
import { drainTeammateOutboxes, getConfirmedStopTime, shutdownTeammate } from "../src/team-machine.ts";
import { getTeammate, registerTeammate } from "../src/state.ts";
import { appendWorkerEvent, stateFilePath, workerOutboxPath } from "../src/statefile.ts";

const reportBody = "Completed work before the process was stopped.";

export default function (pi: ExtensionAPI): void {
  agentTeams(pi);
  let calls = 0;
  let checked = false;
  const stopDuringDelivery = process.env.PI_REPORT_STOP_BOUNDARY === "during-delivery";
  pi.on("message_start", async (event) => {
    if (stopDuringDelivery && event.message.role === "custom" && event.message.customType === "agent-teams-report") {
      assert.equal((await shutdownTeammate("fixture-worker")).ok, true);
    }
  });
  pi.registerProvider("late-report-fixture", {
    api: "late-report-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_REPORT_FIXTURE_AUTH,
    models: [{
      id: "deterministic", name: "Late report fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    }],
    streamSimple(model) {
      calls++;
      const output: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: calls <= 2
          ? [{ type: "toolCall", id: `fixture-${calls}`, name: calls === 1 ? "queue_and_stop" : "check_late_report", arguments: {} }]
          : [{ type: "text", text: checked ? "PI_LATE_REPORT_OK" : "PI_LATE_REPORT_FAILED" }],
        stopReason: calls <= 2 ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: output });
      stream.push({ type: "done", reason: calls <= 2 ? "toolUse" : "stop", message: output });
      stream.end();
      return stream;
    },
  });
  pi.registerTool({
    name: "queue_and_stop", label: "Queue and stop", description: "Queue a report and stop before its delivery.",
    parameters: Type.Object({}),
    async execute(_id, _params, _signal, _update, ctx) {
      registerTeammate({ name: "fixture-worker", agent: "fixture", spawnId: "fixture-spawn", pid: 0,
        status: "working", isolation: "none", createdAt: 1, updatedAt: 1 });
      const outbox = workerOutboxPath(stateFilePath(ctx.sessionManager.getSessionFile(), ctx.cwd), "fixture-worker", "fixture-spawn");
      appendWorkerEvent(outbox, { id: "late-report", type: "message", worker: "fixture-worker", spawnId: "fixture-spawn",
        body: reportBody, status: "completed", timestamp: 100 });
      drainTeammateOutboxes();
      assert.equal(ctx.sessionManager.getEntries().some((entry) => entry.type === "custom_message" && entry.customType === "agent-teams-report"), false);
      if (!stopDuringDelivery) assert.equal((await shutdownTeammate("fixture-worker")).ok, true);
      return { content: [{ type: "text", text: stopDuringDelivery ? "Report queued; shutdown will run when delivery starts." : "Report queued and shutdown confirmed." }], details: {} };
    },
  });
  pi.registerTool({
    name: "check_late_report", label: "Check late report", description: "Verify real Pi delivery metadata.",
    parameters: Type.Object({}),
    async execute(_id, _params, _signal, _update, ctx) {
      const report = ctx.sessionManager.getEntries().find((entry) => entry.type === "custom_message" && entry.customType === "agent-teams-report");
      assert.ok(report && report.type === "custom_message");
      const details = report.details as { body: string; timestamp: number; deliveredAt: number; processStoppedAt?: number; deliveredAfterStop?: boolean };
      assert.equal(details.body, reportBody);
      assert.equal(details.timestamp, 100);
      if (stopDuringDelivery) {
        assert.equal(details.deliveredAfterStop, undefined, "A report delivered before shutdown was retroactively marked late");
        const stoppedAt = getConfirmedStopTime("fixture-spawn");
        assert.ok(stoppedAt !== undefined && details.deliveredAt <= stoppedAt);
        assert.doesNotMatch(String(report.content), /delivery="after-stop"/);
      } else {
        assert.equal(details.deliveredAfterStop, true, "Queued report lacks its after-stop delivery marker");
        assert.ok(details.processStoppedAt !== undefined);
        assert.ok(details.deliveredAt >= details.processStoppedAt && details.processStoppedAt > details.timestamp);
        assert.match(String(report.content), /delivery="after-stop"/);
      }
      assert.equal(getTeammate("fixture-worker")?.status, "stopped");
      checked = true;
      return { content: [{ type: "text", text: "Late report preserved and classified." }], details: {} };
    },
  });
}
