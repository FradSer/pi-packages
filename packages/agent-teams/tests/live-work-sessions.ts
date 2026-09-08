import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SessionManager, type ExtensionAPI, type ExtensionContext, type ToolDefinition } from "@earendil-works/pi-coding-agent";
import { registerSessionAgent, clearSessionAgents } from "../src/agents.ts";
import { registerLeaderTools } from "../src/tools.ts";
import { getState, resetState } from "../src/state.ts";
import { initTeamMachine, removeRuntimeDir, shutdownTeamMachine, teardownTeammates } from "../src/team-machine.ts";
import type { LeaderReport } from "../src/leader-reports.ts";

const model = process.env.LIVE_AGENT_WORK_MODEL;
assert.ok(model, "LIVE_AGENT_WORK_MODEL must select an authenticated model for this opt-in test.");
const cwd = mkdtempSync(join(tmpdir(), "pi-live-work-sessions-"));
const sessionManager = SessionManager.inMemory(cwd);
const secret = `CONTEXT_${randomUUID().replaceAll("-", "")}`;
sessionManager.appendMessage({ role: "user", content: `The verification codeword is ${secret}. Only repeat it when asked for the codeword.`, timestamp: Date.now() });
const original = JSON.stringify(sessionManager.getEntries());
const ctx = { cwd, sessionManager, mode: "print", hasUI: false } as ExtensionContext;
const tools = new Map<string, ToolDefinition>();
const pending = new Map<string, ReturnType<typeof Promise.withResolvers<LeaderReport>>>();
const reports: LeaderReport[] = [];
const waitFor = (workId: string) => {
  const deferred = Promise.withResolvers<LeaderReport>();
  pending.set(workId, deferred);
  const already = reports.find((report) => report.workId === workId);
  if (already) deferred.resolve(already);
  return deferred.promise;
};
const budget = AbortSignal.timeout(150_000);
const withBudget = <T>(promise: Promise<T>) => Promise.race([
  promise,
  new Promise<never>((_resolve, reject) => budget.addEventListener("abort", () => reject(new Error("Live Work Session verification timed out.")), { once: true })),
]);
try {
  resetState();
  initTeamMachine(ctx, { notifyChange() {}, sendUpdate(report) {
    if (!report.finished) return;
    reports.push(report);
    if (report.workId) pending.get(report.workId)?.resolve(report);
  } });
  registerSessionAgent({ name: "live-worker", description: "Read-only context verification", tools: [],
    prompt: "Follow the assigned response format exactly. Return one ordinary final answer with no tool calls. The runtime reports final answers automatically. Never use a message tool for completion." });
  registerLeaderTools({ registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools() { return []; }, setActiveTools() {} } as ExtensionAPI);
  const call = (params: object) => tools.get("agent")!.execute("live-delegation", params, undefined, undefined, ctx);
  const prompt = "Return the verification codeword from earlier conversation, if present. If no earlier codeword was provided, return exactly NO_PRIOR_CONTEXT. Return only the codeword or NO_PRIOR_CONTEXT; no tools.";
  const fresh = await call({ name: "live-worker", prompt, model });
  const fork = await call({ name: "live-worker", prompt, model, fork: true });
  const first = fresh.details as { workId: string; route: string };
  const second = fork.details as { workId: string; route: string };
  assert.notEqual(first.workId, second.workId);
  assert.notEqual(first.route, second.route);
  const [freshResult, forkResult] = await withBudget(Promise.all([waitFor(first.workId), waitFor(second.workId)]));
  assert.equal(freshResult.status, "completed");
  assert.equal(freshResult.body.trim(), "NO_PRIOR_CONTEXT");
  assert.equal(forkResult.status, "completed");
  assert.equal(forkResult.body.trim(), secret);
  assert.equal(JSON.stringify(sessionManager.getEntries()), original);
  const next = Promise.withResolvers<LeaderReport>();
  pending.set(first.workId, next);
  const reopened = await call({ name: "live-worker", work: first.workId, prompt: "Return exactly FOLLOWUP_COMPLETE as your ordinary final answer. Use no tools." });
  assert.equal((reopened.details as { workId: string }).workId, first.workId);
  const last = await withBudget(next.promise);
  assert.equal(last.status, "completed");
  assert.equal(last.body.trim(), "FOLLOWUP_COMPLETE");
  assert.notEqual(last.assignmentId, freshResult.assignmentId);
  assert.equal(reports.length, 3);
  assert.equal(Object.values(getState().teammates).find((worker) => worker.workId === first.workId)?.assignment?.closed, true);
} finally {
  await teardownTeammates();
  shutdownTeamMachine();
  removeRuntimeDir(ctx);
  clearSessionAgents();
  resetState();
  rmSync(cwd, { recursive: true, force: true });
}
console.log(`LIVE_WORK_SESSIONS_OK=${JSON.stringify({ fresh: true, fork: true, concurrent: true, automaticResults: reports.length, explicitReopen: true, parentUnchanged: true })}`);
