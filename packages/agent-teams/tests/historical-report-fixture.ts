import assert from "node:assert/strict";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import agentTeams from "../src/index.ts";
import { applyProgress, createBoardTask, drainTeammateOutboxes, shutdownTeammate } from "../src/team-machine.ts";
import { createTask, getTeammate, reclaimDirectWork, registerTeammate, releaseTask, setTaskClaimed } from "../src/state.ts";
import { appendWorkerEvent, stateFilePath, workerOutboxPath } from "../src/statefile.ts";
import type { LeaderReport } from "../src/leader-reports.ts";

const bodies = ["Scope changed; preserve this evidence.", "A decision is needed about the local fixture."];
const acceptedBody = "Accepted terminal evidence must survive delayed arrival.";
const harnessBody = "The harness diagnostic still requires attention.";
const userPrompt = "Run the historical report fixture";

function reportsIn(details: unknown): LeaderReport[] {
  const report = details as LeaderReport | { reports: LeaderReport[] };
  return "reports" in report ? report.reports : [report];
}

export default function (pi: ExtensionAPI): void {
  agentTeams(pi);
  const transition = process.env.PI_REPORT_HISTORY_TRANSITION;
  let calls = 0;
  let produced = false;
  let checked = false;
  let checkAttempted = false;
  let harnessDelivered = false;
  const observations: string[] = [];
  const received: LeaderReport[] = [];

  pi.on("message_end", (event) => {
    if (event.message.role !== "custom") return;
    if (event.message.customType === "agent-teams-report") received.push(...reportsIn(event.message.details));
    if (event.message.customType === "agent-teams-harness") harnessDelivered = true;
  });
  pi.registerProvider("historical-report-fixture", {
    api: "historical-report-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_REPORT_FIXTURE_AUTH,
    models: [{
      id: "deterministic", name: "Historical report fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    }],
    streamSimple(model, context) {
      calls++;
      if (produced) observations.push(JSON.stringify(context.messages));
      const waitingForQueue = !harnessDelivered || received.length < bodies.length + (transition === "completed" ? 1 : 0);
      const tool = calls === 1 ? "produce_historical_reports" : waitingForQueue ? undefined : "check_historical_reports";
      const useTool = !checkAttempted && tool !== undefined;
      const errors = context.messages.flatMap((message) => message.role === "toolResult" && message.isError
        ? message.content.flatMap((block) => block.type === "text" ? [block.text] : []) : []).join("\n");
      const output: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: useTool ? [{ type: "toolCall", id: `history-${calls}`, name: tool!, arguments: {} }]
          : [{ type: "text", text: checked ? "PI_HISTORICAL_REPORT_OK" : checkAttempted ? `PI_HISTORICAL_REPORT_FAILED\n${errors}` : "Queue boundary reached." }],
        stopReason: useTool ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: output });
      stream.push({ type: "done", reason: useTool ? "toolUse" : "stop", message: output });
      stream.end();
      return stream;
    },
  });
  pi.registerTool({
    name: "produce_historical_reports", label: "Produce reports", description: "Queue native reports, then change the attempt lifecycle.",
    parameters: Type.Object({}),
    async execute(_id, _params, _signal, _update, ctx) {
      const worker = { name: "history-worker", agent: "fixture", spawnId: "history-spawn", pid: 0,
        status: "working" as const, isolation: "none" as const, createdAt: 1, updatedAt: 1 };
      assert.ok(registerTeammate(worker).ok);
      const created = createTask({ subject: "Historical fixture work" });
      assert.ok(created.ok);
      assert.ok(setTaskClaimed(created.task.id, worker.name));
      const assignmentId = getTeammate(worker.name)!.assignment!.id;
      applyProgress(worker.name, worker.spawnId, { text: "", turns: 1, finalResponse: false });
      const outbox = workerOutboxPath(stateFilePath(ctx.sessionManager.getSessionFile(), ctx.cwd), worker.name, worker.spawnId);
      for (const [index, body] of bodies.entries()) {
        appendWorkerEvent(outbox, { id: `history-${index}`, type: "message", worker: worker.name, spawnId: worker.spawnId,
          assignmentId, body, status: index === 0 ? "inform" : "request", timestamp: 100 + index });
        drainTeammateOutboxes();
      }
      if (transition === "stopped" || transition === "replacement") {
        assert.equal((await shutdownTeammate(worker.name)).ok, true);
        if (transition === "replacement") {
          assert.equal(registerTeammate({ ...worker, spawnId: "replacement-spawn", status: "idle" }).ok, true);
          assert.ok(reclaimDirectWork(created.task.id, worker.name,
            { id: "replacement-attempt", kind: "direct", resources: [] }, "pending").ok);
        }
      } else if (transition === "released") {
        assert.ok(releaseTask(created.task.id, "Fixture release", false));
      } else if (transition === "superseded") {
        assert.equal(createBoardTask({ subject: "Replacement fixture work", supersedes: [created.task.id] }).ok, true);
      } else if (transition === "completed") {
        appendWorkerEvent(outbox, { id: "terminal", type: "message", worker: worker.name, spawnId: worker.spawnId,
          assignmentId, body: acceptedBody, status: "completed", timestamp: 200 });
        drainTeammateOutboxes();
        applyProgress(worker.name, worker.spawnId, { text: acceptedBody, turns: 1, finalResponse: true });
        assert.equal((await shutdownTeammate(worker.name)).ok, true);
      } else {
        assert.equal(transition, "active");
      }
      pi.sendMessage({ customType: "agent-teams-harness", display: true, content: harnessBody,
        details: { teammate: worker.name, spawnId: worker.spawnId, origin: "harness",
          harnessEvent: { type: "fixture-diagnostic", subject: "Fixture diagnostic" }, body: harnessBody } },
      { triggerTurn: true, deliverAs: "steer" });
      assert.equal(received.length, 0, "Native reports must not split a tool call from its result");
      produced = true;
      return { content: [{ type: "text", text: "Fixture lifecycle transition applied." }], details: {} };
    },
  });
  pi.registerTool({
    name: "check_historical_reports", label: "Check reports", description: "Check raw history and the real provider transcript.",
    parameters: Type.Object({}),
    async execute(_id, _params, _signal, _update, ctx) {
      checkAttempted = true;
      const reports = ctx.sessionManager.getEntries().flatMap((entry) => entry.type === "custom_message"
        && entry.customType === "agent-teams-report" ? reportsIn(entry.details) : []);
      assert.deepEqual(reports.slice(0, 2).map((report) => [report.eventId, report.body, report.timestamp]),
        bodies.map((body, index) => [`history-${index}`, body, 100 + index]));
      for (const body of bodies) {
        assert.equal(observations.some((context) => context.includes(body)), transition === "active",
          `Historical nonterminal body leaked into provider context after ${transition}: ${body}`);
      }
      assert.ok(observations.every((context) => context.includes(userPrompt)), "Unrelated user context was removed");
      if (transition === "completed") {
        assert.ok(reports.some((report) => report.body === acceptedBody && report.status === "completed" && report.finished));
        assert.ok(observations.some((context) => context.includes(acceptedBody)), "Accepted terminal result was suppressed");
      }
      assert.ok(observations.some((context) => context.includes(harnessBody)), "Harness diagnostic was suppressed");
      const retained = ctx.sessionManager.getEntries().flatMap((entry) => entry.type === "custom_message"
        && entry.customType === "agent-teams-report" ? reportsIn(entry.details) : []);
      for (const body of bodies) {
        assert.ok(retained.some((report) => report.body === body),
          `Retired nonterminal evidence must stay in session history after ${transition}: ${body}`);
      }
      checked = true;
      return { content: [{ type: "text", text: "History and provider projection checked." }], details: {} };
    },
  });
}
