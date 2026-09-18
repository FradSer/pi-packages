import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI, ExtensionContext, ToolDefinition } from "@earendil-works/pi-coding-agent";
import { registerLeaderTools } from "../src/tools.ts";
import { initTeamMachine, shutdownTeamMachine, teardownTeammates } from "../src/team-machine.ts";
import { getTask, resetState } from "../src/state.ts";
import type { LeaderReport } from "../src/leader-reports.ts";

const model = process.env.LIVE_AGENT_WORK_MODEL;
assert.ok(model, "Select an authenticated model explicitly for this opt-in test");
const cwd = mkdtempSync(join(tmpdir(), "pi-live-capability-"));
const ctx = { cwd, sessionManager: { getSessionFile: () => join(cwd, "leader.jsonl") } } as ExtensionContext;
const tools = new Map<string, ToolDefinition>();
const done = Promise.withResolvers<LeaderReport>();
const reports: LeaderReport[] = [];
const timer = setTimeout(() => done.reject(new Error("Live capability verification timed out")), 120_000);
try {
  resetState();
  initTeamMachine(ctx, { notifyChange() {}, sendUpdate(report) {
    if (report.finished) { reports.push(report); done.resolve(report); }
  } });
  registerLeaderTools({ registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools: () => [], setActiveTools() {} } as unknown as ExtensionAPI);
  const result = await tools.get("agent")!.execute("live", {
    action: "delegate", name: "capability-blocker", model,
    prompt: "Read the local file evidence.txt using a file tool and report its content. Do not invent evidence. If required tools are absent, follow your Worker Protocol and explicitly submit failed with the missing capabilities. Do not send an agent_event or ordinary final instead of failed submission.",
    definition: { description: "Verify missing capability handling", prompt: "Execute only the assigned work; never invent evidence.", tools: [] },
  }, undefined, undefined, ctx);
  const content = JSON.parse((result.content[0] as { text: string }).text);
  assert.deepEqual(content.session.tools, ["agent_event", "work"]);
  assert.match(content.session.warning, /coordination-only/);
  const report = await done.promise;
  assert.equal(report.status, "failed");
  assert.notEqual(getTask(content.work.id)?.status, "completed");
  assert.equal(reports.length, 1);
  console.log(JSON.stringify({ result: "LIVE_CAPABILITY_BLOCKER_OK", grant: content.session.tools,
    reportStatus: report.status, workStatus: getTask(content.work.id)?.status, reports: reports.length, cwd }));
} finally {
  clearTimeout(timer);
  await teardownTeammates();
  shutdownTeamMachine();
  resetState();
}
