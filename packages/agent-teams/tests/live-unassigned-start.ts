import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI, ExtensionContext, ToolDefinition } from "@earendil-works/pi-coding-agent";
import { registerLeaderTools } from "../src/tools.ts";
import { TASK_CAPABILITY_TOOLS, registerTaskTools } from "@fradser/pi-tasks";
import { initTeamMachine, shutdownTeamMachine, teardownAgents } from "../src/team-machine.ts";
import { getState, resetState } from "../src/state.ts";
import { registerIntentTools, type LeaderReport } from "@fradser/pi-subagents";

/** No task tool may name a participant to hand a task to.
 *
 *  The single `task` tool used to be callable with `action: "assign"` and refuse.
 *  With four tools and no verb for it, the property is stronger and is asserted
 *  over the task surface: no parameter on any of the four names a participant.
 *  Scoped to those four on purpose — the `agent` tool has a `session` handle of
 *  its own, which is a different tool's business. */
const TASK_TOOL_NAMES = [...TASK_CAPABILITY_TOOLS];

function assertNoParticipantDirective(): void {
  const banned = ["assign", "assignee", "owner", "target", "participant", "agent", "spawnId", "session"];
  const names = TASK_TOOL_NAMES.filter((name) => tools.has(name));
  assert.deepEqual(names, TASK_TOOL_NAMES, "the four task tools are registered");
  for (const name of names) {
    const properties = (tools.get(name)!.parameters as { properties?: Record<string, unknown> }).properties ?? {};
    for (const key of Object.keys(properties)) {
      for (const word of banned) {
        assert.equal(key.toLowerCase().includes(word), false, `${name} must not offer ${key}`);
      }
    }
  }
}


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
  const host = { registerTool(tool: { name: string }) { tools.set(tool.name, tool); }, getActiveTools: () => [], setActiveTools() {} };
  registerLeaderTools(host as unknown as ExtensionAPI);
  registerIntentTools(host as unknown as ExtensionAPI));
  registerTaskTools(host as unknown as ExtensionAPI);
  const created = await tools.get("create_task")!.execute("create", { subject: "Return exactly NATIVE_UNASSIGNED_ASSIGNED_OK without calling tools." }, undefined, undefined, ctx);
  const work = (created.details as { work: { id: string } }).work;
  const start = await tools.get("agent")!.execute("start", { operation: "start", name: "native-start", model,
    definition: { description: "Startup probe", prompt: "Follow the assigned task exactly.", tools: [] } }, undefined, undefined, ctx);
  const receipt = JSON.parse((start.content[0] as { text: string }).text);
  assert.equal(receipt.session.workId, undefined);
  assert.equal(receipt.session.status, "idle");
  assert.equal(getState().agents["native-start"].turns, 0);
  assert.equal(getState().agents["native-start"].assignment, undefined);
  assertNoParticipantDirective();
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
