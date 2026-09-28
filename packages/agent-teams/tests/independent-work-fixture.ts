import assert from "node:assert/strict";
import childProcess from "node:child_process";
import { EventEmitter } from "node:events";
import { syncBuiltinESMExports } from "node:module";
import { PassThrough, Writable } from "node:stream";
import { mock } from "node:test";

const children: Array<EventEmitter & { stdin: Writable; stdout: PassThrough; stderr: PassThrough; pid: number; commands: Array<{ message?: string }> }> = [];
mock.method(childProcess, "spawn", () => {
  const child = Object.assign(new EventEmitter(), { pid: children.length + 1, stdin: new Writable(), stdout: new PassThrough(), stderr: new PassThrough(), commands: [] as Array<{ message?: string }> });
  child.stdin = new Writable({ write(chunk, _encoding, done) { child.commands.push(JSON.parse(String(chunk))); done(); } });
  children.push(child);
  return child;
});
syncBuiltinESMExports();

const { registerLeaderTools } = await import("../src/tools.ts");
const { registerTaskTool } = await import("@fradser/pi-tasks");
const { clearSessionAgents, registerAgentTool, registerSessionAgent } = await import("@fradser/pi-subagents");
const { getState, resetState } = await import("../src/state.ts");
const { initTeamMachine, shutdownTeamMachine } = await import("../src/team-machine.ts");
const { SessionManager } = await import("@earendil-works/pi-coding-agent");

const context = { cwd: process.cwd(), sessionManager: SessionManager.inMemory(process.cwd()) };
try {
  resetState();
  clearSessionAgents();
  initTeamMachine(context, { sendUpdate() {}, notifyChange() {} });
  registerSessionAgent({ name: "reviewer", description: "Review", prompt: "Review thoroughly", tools: ["read"] });
  const tools = new Map();
  const host = { registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools() { return []; }, setActiveTools() {} };
  registerLeaderTools(host);
  registerAgentTool(host);
  registerTaskTool(host);
  const agent = tools.get("agent");
  const call = (params) => agent.execute("call", params, undefined, undefined, context);

  const first = await call({ action: "start", name: "reviewer", prompt: "Audit authentication" });
  assert.equal(first.details.outcome, "started", first.content[0].text);
  // The second start under a living name is refused, and the refusal names the two
  // ways out. Reported rather than thrown: one shape for every refusal.
  const duplicate = await call({ action: "start", name: "reviewer", prompt: "Audit authorization" });
  assert.equal(duplicate.details.ok, false);
  assert.match(duplicate.content[0].text, /A living teammate named "reviewer" already exists/);
  assert.match(duplicate.content[0].text, /inspect/);
  assert.match(duplicate.content[0].text, /stop/);
  const second = await call({ action: "start", name: "authorization-reviewer", prompt: "Audit authorization", description: "Review authorization", role_prompt: "Review thoroughly" });
  assert.equal(second.details.outcome, "started", second.content[0].text);
  // Independence is per session and per handle, and neither carries a work id:
  // a spawn records no task, so there is no shared identity to diverge.
  assert.equal(children.length, 2);
  assert.equal(first.details.work, undefined);
  assert.equal(second.details.work, undefined);
  assert.notEqual(first.details.session, second.details.session);
  assert.match(children[0].commands[0].message ?? "", /Audit authentication/);
  assert.match(children[1].commands[0].message ?? "", /Audit authorization/);

  // `inspect` addresses one incarnation by its exact handle, and reports the
  // handle rather than an id, so the two can be compared directly.
  const inspected = await call({ action: "inspect", session: first.details.session });
  assert.equal(inspected.details.outcome, "inspected", inspected.content[0].text);
  assert.deepEqual(inspected.details.sessions.map((entry) => entry.session), [first.details.session]);
  const missing = await call({ action: "inspect", session: "session:missing:old" });
  assert.equal(missing.details.ok, false);
  assert.match(missing.content[0].text, /No living session/);
  console.log("INDEPENDENT_WORK_OK");
} finally {
  shutdownTeamMachine();
  resetState();
  clearSessionAgents();
  mock.restoreAll();
  syncBuiltinESMExports();
}
