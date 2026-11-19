import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI, ExtensionContext, ToolDefinition } from "@earendil-works/pi-coding-agent";
import { registerLeaderTools } from "../src/tools.ts";
import { initTeamMachine, shutdownTeamMachine, teardownAgents } from "../src/team-machine.ts";
import { createTask, getState, resetState } from "../src/state.ts";
import { registerIntentTools, type LeaderReport } from "@fradser/pi-subagents";

// Leader task tools are retired. Work is created in the internal domain and
// handed to a child through `agent_start`; no model-facing task tool exists.
const model = process.env.LIVE_AGENT_WORK_MODEL;
assert.ok(model, "Select an authenticated model explicitly");
const cwd = mkdtempSync(join(tmpdir(), "pi-live-unassigned-"));
const ctx = { cwd, sessionManager: { getSessionFile: () => join(cwd, "leader.jsonl") } } as ExtensionContext;
const tools = new Map<string, ToolDefinition>();
const done = Promise.withResolvers<LeaderReport>();
const timer = setTimeout(() => { done.reject(new Error("Result timeout")); }, 120_000);
// Attach rejection handlers before either phase can time out.
void done.promise.catch(() => {});
try {
  resetState();
  initTeamMachine(ctx, {
    notifyChange() {},
    sendUpdate(report) { if (report.finished) done.resolve(report); },
  });
  const host = { registerTool(tool: { name: string }) { tools.set(tool.name, tool); }, getActiveTools: () => [], setActiveTools() {} } as unknown as ExtensionAPI;
  registerLeaderTools(host);
  registerIntentTools(host);
  assert.equal(tools.has("create_task"), false, "the leader must not register a task tool");
  const created = createTask({ subject: "Return exactly NATIVE_UNASSIGNED_ASSIGNED_OK without calling tools." });
  assert.equal(created.ok, true);
  const work = created.task;
  const start = await tools.get("agent")!.execute("start", { operation: "start", name: "native-start", model,
    definition: { description: "Startup probe", prompt: "Follow the assigned task exactly.", tools: [] } }, undefined, undefined, ctx);
  const receipt = JSON.parse((start.content[0] as { text: string }).text);
  assert.equal(receipt.session.workId, undefined);
  assert.equal(receipt.session.status, "idle");
  assert.equal(getState().agents["native-start"].turns, 0);
  assert.equal(getState().agents["native-start"].assignment, undefined);
  const report = await done.promise;
  assert.equal(report.status, "completed");
  assert.equal(getState().tasks[work.id].status, "completed");
  assert.match(report.body, /NATIVE_UNASSIGNED_ASSIGNED_OK/);
  console.log(JSON.stringify({ result: "LIVE_UNASSIGNED_START_OK", startupTurns: 0, immediateAssign: true, startStatus: receipt.session.status, assignedSameWork: true, cwd }));
} finally {
  clearTimeout(timer);
  await teardownAgents();
  shutdownTeamMachine();
  resetState();
}
