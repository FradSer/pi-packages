import assert from "node:assert/strict";
import { createAssistantMessageEventStream, type AssistantMessage, type StopReason } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionContext, ExtensionEvent, ToolDefinition } from "@earendil-works/pi-coding-agent";
import { readJsonlBatch, writeRoster } from "../src/statefile.ts";
import type { WorkerAssignment } from "../src/types.ts";
import { registerWorkerCapabilities, workerBinding } from "../src/worker.ts";

export function assistant(text: string, stopReason: StopReason = "stop", timestamp = 20, errorMessage?: string): AssistantMessage {
  return {
    role: "assistant", content: [{ type: "text", text }], stopReason, errorMessage, timestamp,
    api: "automatic-results-fixture", provider: "automatic-results-fixture", model: "deterministic",
    usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
  };
}

export function createWorkerFixture(root: string, kind: "direct" | "board" | "none" = "direct", workerName = process.env.PI_TEAMMATE_WORKER_NAME || "worker") {
  Object.assign(process.env, {
    PI_TEAMMATE_WORKER_NAME: workerName, PI_TEAMMATE_SPAWN_ID: "spawn-1",
    PI_TEAMMATE_OUTBOX_FILE: `${root}/events.jsonl`, PI_TEAMMATE_INBOX_FILE: `${root}/mail/inbox-${encodeURIComponent(workerName)}.jsonl`,
    PI_TEAMMATE_ROSTER_FILE: `${root}/roster.json`, PI_TEAMMATE_BOARD_FILE: `${root}/board.json`,
    PI_TEAMMATE_CLAIMS_DIR: `${root}/claims`, PI_TEAMMATE_SUBMISSIONS_DIR: `${root}/submissions`,
  });
  const binding = workerBinding()!;
  const roster = (assignment?: WorkerAssignment, spawnId = binding.spawnId, status = "working", currentTaskId = "work-1") => {
    writeRoster(binding.rosterFile, [{ name: binding.worker, agent: "reviewer", spawnId, status, assignment, currentTaskId: assignment ? currentTaskId : undefined }]);
  };
  roster(kind === "none" ? undefined : { id: "attempt-1", kind, resources: [] });
  type Handler = (event: ExtensionEvent, ctx: ExtensionContext) => unknown;
  const hooks = new Map<string, Handler[]>();
  const tools = new Map<string, ToolDefinition>();
  const pi: Pick<ExtensionAPI, "on" | "registerTool" | "getActiveTools" | "setActiveTools"> = {
    on(event, handler) { hooks.set(event, [...(hooks.get(event) ?? []), handler as Handler]); },
    registerTool(tool) { tools.set(tool.name, tool as unknown as ToolDefinition); },
    getActiveTools: () => [], setActiveTools() {},
  };
  let idle = true;
  const ctx = { isIdle: () => idle } as ExtensionContext;
  const disclosure = registerWorkerCapabilities(pi as ExtensionAPI);
  const emit = async (event: ExtensionEvent) => {
    for (const handler of hooks.get(event.type) ?? []) await handler(event, ctx);
  };
  return {
    binding, disclosure, emit, roster, tools,
    setIdle(value: boolean) { idle = value; },
    records: () => readJsonlBatch(binding.outbox, 0).records,
    start: (id = "attempt-1", timestamp = 10) => emit({ type: "message_start", message: {
      role: "user", content: `[agent-teams-assignment:${id}]\nDo the assignment`, timestamp,
    } }),
    answer: async (message: AssistantMessage) => {
      await emit({ type: "message_start", message: { ...message, stopReason: "pending" } });
      await emit({ type: "message_end", message });
    },
    call: (name: string, params: object) => tools.get(name)!.execute("call", params, undefined, undefined, ctx),
  };
}

export default function (pi: ExtensionAPI): void {
  registerWorkerCapabilities(pi);
  let calls = 0;
  let lowLevelEnds = 0;
  let settlements = 0;
  const binding = workerBinding()!;
  pi.registerProvider("automatic-results-fixture", {
    api: "automatic-results-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_AUTOMATIC_RESULTS_AUTH,
    models: [{ id: "deterministic", name: "Automatic results fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple() {
      calls++;
      const message = calls === 1
        ? assistant("Stale intermediate success", "error", Date.now(), "429 rate limit: retry this request")
        : assistant("PI_AUTOMATIC_RESULTS_OK", "stop", Date.now());
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      if (message.stopReason === "error") stream.push({ type: "error", reason: "error", error: message });
      else stream.push({ type: "done", reason: "stop", message });
      stream.end();
      return stream;
    },
  });
  pi.on("agent_end", () => {
    lowLevelEnds++;
    assert.deepEqual(readJsonlBatch(binding.outbox, 0).records, [], "Low-level run endings must not report a result");
  });
  pi.on("agent_settled", (_event, ctx) => {
    settlements++;
    assert.equal(ctx.isIdle(), true);
    assert.equal(calls, 2);
    assert.equal(lowLevelEnds, 2);
    const records = readJsonlBatch(binding.outbox, 0).records;
    assert.equal(records.length, 1);
    assert.deepEqual(records.map((record) => {
      const event = record as { status: string; body: string; assignmentId: string; spawnId: string };
      return [event.status, event.body, event.assignmentId, event.spawnId];
    }), [["completed", "PI_AUTOMATIC_RESULTS_OK", "attempt-1", "spawn-1"]]);
  });
  pi.on("session_shutdown", () => { assert.equal(settlements, 1); });
}
