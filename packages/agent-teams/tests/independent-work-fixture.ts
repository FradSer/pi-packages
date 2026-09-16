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
const { clearSessionAgents, registerSessionAgent } = await import("../src/agents.ts");
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
  registerLeaderTools({ registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools() { return []; }, setActiveTools() {} });
  const agent = tools.get("agent");
  const call = (params) => agent.execute("call", params, undefined, undefined, context);

  const first = await call({ action: "delegate", name: "reviewer", prompt: "Audit authentication" });
  await assert.rejects(call({ action: "delegate", name: "reviewer", prompt: "Audit authorization" }), /A living teammate named "reviewer" already exists/);
  const second = await call({ action: "delegate", name: "authorization-reviewer", prompt: "Audit authorization", definition: { description: "Review authorization", prompt: "Review thoroughly" } });
  assert.equal(children.length, 2);
  assert.notEqual(first.details.work.id, second.details.work.id);
  assert.notEqual(first.details.session.id, second.details.session.id);
  assert.match(children[0].commands[0].message ?? "", /Audit authentication/);
  assert.match(children[1].commands[0].message ?? "", /Audit authorization/);

  const inspected = await call({ action: "inspect", name: "reviewer", session: first.details.session.id });
  assert.deepEqual(inspected.details.sessions.map((entry) => entry.id), [first.details.session.id]);
  await assert.rejects(call({ action: "inspect", name: "reviewer", session: "session:missing:old" }));
  console.log("INDEPENDENT_WORK_OK");
} finally {
  shutdownTeamMachine();
  resetState();
  clearSessionAgents();
  mock.restoreAll();
  syncBuiltinESMExports();
}
