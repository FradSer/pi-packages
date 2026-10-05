/** Native resident probe. All paths and the loopback-only model come from the
 * isolated pytest harness; no real HOME/config/auth, Git or dependencies are used.
 */
import assert from "node:assert/strict";
import { existsSync, mkdirSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { SessionManager, type ExtensionContext } from "@earendil-works/pi-coding-agent";
import { ensureAgentWorkspace, resolveAgent, type LeaderReport } from "@fradser/pi-subagents";
import { getAgent, resetState } from "../src/state.ts";
import { initTeamMachine, shutdownTeamMachine, spawnAgent, teardownAgents } from "../src/team-machine.ts";

const root = process.env.PI_TEST_DIR!;
const config = process.env.PI_CODING_AGENT_DIR!;
const model = process.env.PI_TEST_MODEL!;
assert.ok(root && config && model, "Use the isolated native test harness");
assert.ok(path.resolve(config).startsWith(path.resolve(root) + path.sep));
const project = path.join(root, "project");
mkdirSync(project, { recursive: true });
const source = path.join(project, ".pi", "agents", "memory-probe", "agent.md");
mkdirSync(path.dirname(source), { recursive: true });
writeFileSync(source, "---\nname: memory-probe\ndescription: Native durable data probe\ntools: read\n---\nReturn the requested evidence, without tools.\n");
const home = path.join(config, "agents", "memory-probe");
const workspace = ensureAgentWorkspace({ agentName: "memory-probe", cwd: project });
writeFileSync(path.join(home, "memory", "known-method.md"),
  "---\nname: known-method\ndescription: Use when probing capability injection\ntype: capability\n---\n\nA fixture capability.\n");
writeFileSync(path.join(home, "memory", "MEMORY.md"), "# Agent Memory Index\n\n- known-method.md — Use when probing capability injection\n");
const ctx = { cwd: project, sessionManager: SessionManager.inMemory(project), model: undefined } satisfies Pick<ExtensionContext, "cwd" | "sessionManager" | "model">;
const reports: LeaderReport[] = [];
let resolveReport!: (report: LeaderReport) => void;
const finished = new Promise<LeaderReport>(resolve => { resolveReport = resolve; });
const timer = setTimeout(() => { throw new Error("Native team result did not arrive"); }, 25_000);
try {
  resetState();
  initTeamMachine(ctx, { notifyChange() {}, sendUpdate(report) {
    reports.push(report);
    if (report.finished) resolveReport(report);
  } });
  assert.equal(resolveAgent("memory-probe", project)?.scope, "project");
  const spawned = spawnAgent({ name: "memory-probe", role: "memory-probe", model, prompt: "Return LIVE_TEAM_DATA_OK" });
  if (!spawned.ok) throw new Error(spawned.error);
  assert.equal(await spawned.readiness, undefined, "prompted start must confirm native accepted input");
  const report = await finished;
  assert.equal(report.status, "completed");
  assert.equal(report.body, "LIVE_TEAM_DATA_OK");
  assert.equal(reports.filter(entry => entry.finished).length, 1, "one result owner");
  const agent = getAgent("memory-probe")!;
  assert.equal(agent.status, "idle", "settled durable resident remains idle");
  assert.equal(agent.cwd, project, "scratch is data, not a project checkout");
  assert.ok(agent.tools?.includes("agent_memory"), "all disk scopes get Memory");
  assert.ok(readdirSync(workspace.sessionDir).some(file => file.endsWith(".jsonl")), "history is private and project-scoped");
  assert.ok(!existsSync(path.join(config, "agents", "memory-probe", "agent.md")), "project identity is not promoted");
  await teardownAgents();
  assert.equal(agent.status, "stopped");
  assert.ok(existsSync(workspace.workspacePath));
  assert.ok(existsSync(source));
  assert.ok(!existsSync(path.join(workspace.workspacePath, ".git")));
  assert.ok(!existsSync(path.join(config, "workspaces")));
  assert.equal(ensureAgentWorkspace({ agentName: "memory-probe", cwd: project }).reused, true);
  console.log(JSON.stringify({ ok: true, status: report.status, reports: 1, durableDataRetained: true }));
} finally {
  clearTimeout(timer);
  await teardownAgents();
  shutdownTeamMachine();
  resetState();
}
