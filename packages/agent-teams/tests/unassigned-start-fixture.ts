import assert from "node:assert/strict";
import childProcess from "node:child_process";
import { EventEmitter } from "node:events";
import { syncBuiltinESMExports } from "node:module";
import { PassThrough, Writable } from "node:stream";
import { mock } from "node:test";

const commands: Array<{ type: string; id?: string; message?: string }> = [];
const child = Object.assign(new EventEmitter(), {
  pid: 1, stdout: new PassThrough(), stderr: new PassThrough(),
  stdin: new Writable({ write(chunk, _encoding, done) {
    const command = JSON.parse(String(chunk));
    commands.push(command);
    if (command.type === "get_state") setImmediate(() => {
      const mode = process.env.PI_TEST_MODE;
      if (mode === "timeout") return;
      if (mode === "exit") { child.emit("close", 1, null); return; }
      child.stdout.write(JSON.stringify({ type: "response", command: "get_state", id: command.id,
        success: mode !== "rejected", error: "readiness rejected", data: { isStreaming: mode === "not-ready" } }) + "\n");
    });
    done();
  } }),
});
mock.method(childProcess, "spawn", () => child);
syncBuiltinESMExports();
const { registerLeaderTools } = await import("../src/tools.ts");
const { registerTaskTool } = await import("@fradser/pi-tasks");
const { registerAgentTool } = await import("@fradser/pi-subagents");
const { exactSessionRoute, setAgentHost } = await import("@fradser/pi-subagents");
const { initTeamMachine, shutdownTeamMachine, wakeIdleTeammates, deliverFeedback, routePeerInboxes, spawnTeammate, shutdownTeammateExact } = await import("../src/team-machine.ts");
const { getState, resetState, takeTask } = await import("../src/state.ts");
const root = process.env.PI_TEST_DIR;
assert.ok(root);
resetState();
initTeamMachine({ sessionManager: undefined, cwd: root }, { sendUpdate() {}, notifyChange() {} });
const tools = new Map();
const host = { registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools: () => [], setActiveTools() {} };
registerLeaderTools(host);
registerAgentTool(host);
registerTaskTool(host);
// The `agent` tool belongs to @fradser/pi-subagents, so the team spawn path
// reaches it the only way it can: by publishing itself as the coordinator. These
// assertions are about the team behaviour, so they have to drive the real host
// rather than the raw spawner underneath it.
setAgentHost({
  async start(request) {
    const definition = request.definition ?? { description: request.name, prompt: "" };
    const spawned = spawnTeammate({
      name: request.name,
      agent: request.name,
      ...(request.model ? { model: request.model } : {}),
      ...(request.prompt ? { prompt: request.prompt } : {}),
      ...(request.definition ? { definition: { ...definition, ...(request.tools ? { tools: request.tools } : {}) } } : {}),
    });
    if (!spawned.ok) return spawned;
    // Readiness is the host's job: a handle is only evidence of anything once
    // the child has answered, so the host awaits its own probe before returning.
    if (spawned.readiness) {
      const failure = await spawned.readiness;
      if (failure) return { ok: false, error: failure };
    }
    return { ok: true, session: exactSessionRoute(spawned.teammate.name, spawned.teammate.spawnId) };
  },
  stop: shutdownTeammateExact,
});
const ctx = { cwd: root };
try {
  const created = await tools.get("task").execute("create", { action: "create", subject: "Recover existing work" }, undefined, undefined, ctx);
  const starting = tools.get("agent").execute("start", { action: "start", name: "recovery", description: "Recovery", role_prompt: "Read assigned evidence", tools: ["read"] }, undefined, undefined, ctx);
  const mode = process.env.PI_TEST_MODE;
  if (["timeout", "exit", "not-ready", "rejected"].includes(mode ?? "")) {
    // A refused action is reported, not thrown. The tool returns an error result
    // for every refusal, so a caller reads one shape whether the refusal came
    // from validation, a conflict, or a child that never came up.
    const refused = await starting;
    assert.equal(refused.details.ok, false, "a child that never became ready must not report a handle");
    assert.equal(refused.details.session, undefined);
    assert.match(refused.content[0].text, /readiness|exited|closed/i, refused.content[0].text);
    console.log("UNASSIGNED_START_OK");
  } else {
  const started = await starting;
  // `start` returns a handle, not a projection. The readiness property is
  // therefore read back through `inspect`, which is the surviving way to ask.
  const session = started.details.session;
  assert.match(session, /^session:recovery:/, "start must return an exact handle");
  const inspected = await tools.get("agent").execute("inspect", { action: "inspect", session }, undefined, undefined, ctx);
  assert.equal(inspected.details.sessions[0].status, "idle", "awaited public start must resolve native readiness");
  // An unassigned resident must not acquire a task by being started: the board
  // states what must be done, and a participant takes it.
  assert.equal(inspected.details.sessions[0].currentTaskId, undefined, "unassigned start must not fabricate Work identity");
  assert.equal(inspected.details.sessions[0].assignment, undefined, "unassigned start must not fabricate an assignment");
  assert.equal(commands.some((command) => command.type === "prompt"), false, "unassigned start must not execute a model kickoff");
  assert.equal(getState().teammates.recovery.status, "idle");
  const ready = commands.find((command) => command.type === "get_state");
  assert.ok(ready, "native readiness requires an acknowledged control request");
  assert.equal(getState().teammates.recovery.status, "idle");
  if (mode === "notice" || mode === "inbox") {
    if (mode === "inbox") {
      // Prevent a board notice from masking the ordinary first-wake path.
      getState().teammates.recovery.noticedTaskIds = [created.details.id];
      deliverFeedback("recovery", "Context", "Read-only context, no new assignment");
      routePeerInboxes();
    }
    wakeIdleTeammates();
    const wake = commands.find((command) => command.type === "prompt");
    assert.match(wake?.message ?? "", /Read assigned evidence/);
    if (mode === "notice") assert.match(wake?.message ?? "", /=== BOARD NOTICE ===/);
    else {
      assert.match(wake?.message ?? "", /Read-only context/);
      assert.doesNotMatch(wake?.message ?? "", /=== BOARD NOTICE ===/);
    }
    assert.equal(getState().tasks[created.details.id].status, "pending");
    console.log("UNASSIGNED_START_OK");
  } else if (mode === "in_progress") {
    takeTask(created.details.id, "recovery");
    assert.equal(getState().teammates.recovery.currentTaskId, created.details.id);
    // Nothing may direct the assignment at a named participant any more. The
    // board states what must be done; the participant raises a hand.
    const directed = await tools.get("task").execute("assign", { action: "assign", id: created.details.id, target: { session: "session:recovery" } }, undefined, undefined, ctx);
    assert.equal(directed.details.ok, false, "assign must be refused");
    assert.match(directed.content[0].text, /update/);
    assert.equal(getState().tasks[created.details.id].status, "in_progress", "a refused assign changes nothing");
    console.log("UNASSIGNED_START_OK");
  } else {
    // The same rule in the plain case: the resident takes the task itself, and
    // there is no leader-side verb that can hand it over.
    const directed = await tools.get("task").execute("assign", { action: "assign", id: created.details.id, target: { session: "session:recovery" } }, undefined, undefined, ctx);
    assert.equal(directed.details.ok, false);
    assert.equal(getState().tasks[created.details.id].status, "pending");
    assert.equal(getState().teammates.recovery.currentTaskId, undefined, "an unstarted resident holds nothing");
    assert.equal(commands.some((command) => command.type === "new_session"), false, "no fresh session is created by a refused assignment");
    console.log("UNASSIGNED_START_OK");
  }
  }
} finally {
  shutdownTeamMachine();
  child.emit("close", 0, null);
  mock.restoreAll();
}
