import assert from "node:assert/strict";
import { registerLeaderTools } from "../src/tools.ts";
import { registerSessionAgent } from "../src/agents.ts";
import { getTeammate, registerTeammate, resetState, updateTeammate } from "../src/state.ts";

resetState();
registerSessionAgent({ name: "defined", description: "Review", prompt: "Keep this role", tools: ["read"], model: "original/model" });
const tools = new Map();
const sends = [];
const spawns = [];
let outcome = "queued";
registerLeaderTools({ registerTool: (tool) => tools.set(tool.name, tool), getActiveTools: () => [], setActiveTools() {} }, {
  spawnTeammate(input) {
    spawns.push(input);
    registerTeammate({ name: input.name, agent: input.agent, workId: input.workId, spawnId: "spawn", pid: 0, status: "starting", isolation: "none", createdAt: 1, updatedAt: 1,
      assignment: { id: "new-work", kind: "direct", prompt: input.prompt, resources: [], closed: false } });
    return { ok: true, teammate: getTeammate(input.name) };
  },
  sendLeaderMessage(to, message, options) { sends.push({ to, message, options }); return { ok: true, outcome, terminalReport: "Recorded evidence" }; },
});
const call = (name, params) => tools.get(name).execute("call", params, undefined, undefined, { mode: "print", hasUI: false });
const missing = await call("agent", { name: "missing" });
assert.equal(missing.details.status, "unknown");
assert.equal("activeSessions" in missing.details, false);
assert.equal((await call("agent", { name: "defined" })).details.status, "idle");
assert.equal(spawns.length, 0);
await assert.rejects(call("agent", { name: "missing", prompt: "Implement" }), /teammate_spawn/);
assert.equal(spawns.length, 0);
for (const status of ["starting", "working", "idle", "stopped"]) {
  if (!getTeammate("resident")) registerTeammate({ name: "resident", agent: "defined", spawnId: "resident-spawn", pid: 0, status, isolation: "none", createdAt: 1, updatedAt: 1 });
  updateTeammate("resident", { status, assignment: { id: "work-1", kind: "direct", prompt: "Review", resources: [], closed: false } });
  const result = await call("agent", { name: "defined", work: "work-1" });
  assert.equal(result.details.status, status);
  assert.equal(result.details.assignmentOpen, true);
  assert.equal(result.details.workId, "work-1");
  assert.equal(result.details.sessions[0].route, "session:resident");
}
updateTeammate("resident", { status: "working" });
await assert.rejects(call("agent", { name: "defined", work: "wrong" }), /work/i);
await assert.rejects(call("agent", { name: "defined", work: "wrong", prompt: "Steer" }), /work/i);
assert.equal(sends.length, 0);
assert.equal(spawns.length, 0);
await call("agent", { name: "defined", work: "work-1", prompt: "Steer" });
assert.equal(sends.at(-1).options.reopen, "if-closed");
outcome = "not-sent";
const notSent = await call("agent", { name: "defined", work: "work-1", prompt: "Repeat" });
assert.match(notSent.content[0].text, /Recorded evidence/);
outcome = "queued";
getTeammate("resident").assignment.closed = true;
await call("agent", { name: "defined", work: "work-1", prompt: "New work" });
assert.equal(sends.at(-1).options.reopen, "if-closed");
assert.equal(spawns.length, 0);
await call("agent", { name: "defined", prompt: "Audit", model: "override/model" });
assert.equal(spawns[0].model, "override/model");
assert.equal(spawns[0].definition, undefined);
for (outcome of ["queued", "not-sent", "steered"]) {
  const result = await call("agent_event", { to: "resident", message: "Hello" });
  assert.equal(result.details.outcome, outcome);
  assert.ok(!result.content[0].text.includes("EVENT DELIVERED"));
  assert.ok(result.content[0].text.includes(outcome));
}
const sentBeforeInvalid = sends.length;
for (const params of [{ message: "Hi" }, { to: "leader", message: "Hi" }, { to: "resident", message: "Hi", status: "completed" }, { to: "resident", message: "Hi", status: "failed" }, { to: "resident", message: "Hi", status: "in_progress" }]) {
  await assert.rejects(call("agent_event", params));
}
assert.equal(sends.length, sentBeforeInvalid);
console.log("AGENT_CONTROL_OK");
