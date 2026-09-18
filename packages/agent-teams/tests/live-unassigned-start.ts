import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI, ExtensionContext, ToolDefinition } from "@earendil-works/pi-coding-agent";
import { registerLeaderTools } from "../src/tools.ts";
import { initTeamMachine, shutdownTeamMachine, teardownTeammates } from "../src/team-machine.ts";
import { getState, resetState } from "../src/state.ts";
import type { LeaderReport } from "../src/leader-reports.ts";

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
  registerLeaderTools({ registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools: () => [], setActiveTools() {} } as unknown as ExtensionAPI);
  const created = await tools.get("work")!.execute("create", { action: "create", subject: "Return exactly NATIVE_UNASSIGNED_ASSIGNED_OK without calling tools." }, undefined, undefined, ctx);
  const work = (created.details as { work: { id: string } }).work;
  const start = await tools.get("agent")!.execute("start", { action: "start", name: "native-start", model,
    definition: { description: "Startup probe", prompt: "Follow the assigned task exactly.", tools: [] } }, undefined, undefined, ctx);
  const receipt = JSON.parse((start.content[0] as { text: string }).text);
  assert.equal(receipt.session.workId, undefined);
  assert.equal(receipt.session.status, "idle");
  assert.equal(getState().teammates["native-start"].turns, 0);
  assert.equal(getState().teammates["native-start"].assignment, undefined);
  await tools.get("work")!.execute("assign", { action: "assign", id: work.id, target: { session: receipt.session.id } }, undefined, undefined, ctx);
  const report = await done.promise;
  assert.equal(report.status, "completed");
  assert.equal(getState().tasks[work.id].status, "completed");
  assert.match(report.body, /NATIVE_UNASSIGNED_ASSIGNED_OK/);
  console.log(JSON.stringify({ result: "LIVE_UNASSIGNED_START_OK", startupTurns: 0, immediateAssign: true, startStatus: receipt.session.status, assignedSameWork: true, cwd }));
} finally {
  clearTimeout(timer);
  await teardownTeammates();
  shutdownTeamMachine();
  resetState();
}
