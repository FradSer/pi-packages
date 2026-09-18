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
const { initTeamMachine, shutdownTeamMachine, wakeIdleTeammates, deliverFeedback, routePeerInboxes } = await import("../src/team-machine.ts");
const { getState, resetState, setTaskClaimed } = await import("../src/state.ts");
const root = process.env.PI_TEST_DIR;
assert.ok(root);
resetState();
initTeamMachine({ sessionManager: undefined, cwd: root }, { sendUpdate() {}, notifyChange() {} });
const tools = new Map();
registerLeaderTools({ registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools: () => [], setActiveTools() {} });
const ctx = { cwd: root };
try {
  const created = await tools.get("work").execute("create", { action: "create", subject: "Recover existing work" }, undefined, undefined, ctx);
  const starting = tools.get("agent").execute("start", { action: "start", name: "recovery", definition: { description: "Recovery", prompt: "Read assigned evidence", tools: ["read"] } }, undefined, undefined, ctx);
  const mode = process.env.PI_TEST_MODE;
  if (["timeout", "exit", "not-ready", "rejected"].includes(mode ?? "")) {
    await assert.rejects(starting, /readiness|exited/i);
    console.log("UNASSIGNED_START_OK");
  } else {
  const started = await starting;
  assert.equal(started.details.session.status, "idle", "awaited public start must resolve native readiness");
  assert.equal(started.details.session.workId, undefined, "unassigned start must not fabricate Work identity");
  assert.equal(started.details.session.assignmentId, undefined);
  assert.equal(commands.some((command) => command.type === "prompt"), false, "unassigned start must not execute a model kickoff");
  assert.equal(getState().teammates.recovery.status, "idle");
  const ready = commands.find((command) => command.type === "get_state");
  assert.ok(ready, "native readiness requires an acknowledged control request");
  assert.equal(getState().teammates.recovery.status, "idle");
  if (mode === "notice" || mode === "inbox") {
    if (mode === "inbox") {
      // Prevent a board notice from masking the ordinary first-wake path.
      getState().teammates.recovery.noticedTaskIds = [created.details.work.id];
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
    assert.equal(getState().tasks[created.details.work.id].status, "pending");
    console.log("UNASSIGNED_START_OK");
  } else if (mode === "claimed") {
    setTaskClaimed(created.details.work.id, "recovery");
    const holding = getState().teammates.recovery.assignment.id;
    const assigned = await tools.get("work").execute("assign", { action: "assign", id: created.details.work.id, target: { session: started.details.session.id } }, undefined, undefined, ctx);
    assert.equal(assigned.details.assignment.id, holding);
    assert.equal(commands.some((command) => command.type === "new_session" || command.type === "prompt"), false);
    await assert.rejects(tools.get("work").execute("stale", { action: "assign", id: created.details.work.id, target: { session: started.details.session.id + "-stale" } }, undefined, undefined, ctx));
    console.log("UNASSIGNED_START_OK");
  } else {
  const assigned = await tools.get("work").execute("assign", { action: "assign", id: created.details.work.id, target: { session: started.details.session.id } }, undefined, undefined, ctx);
  assert.equal(assigned.details.work.id, created.details.work.id);
  assert.equal(assigned.details.work.state, "claimed");
  const repeated = await tools.get("work").execute("assign-again", { action: "assign", id: created.details.work.id, target: { session: started.details.session.id } }, undefined, undefined, ctx);
  assert.deepEqual(repeated.details, assigned.details, "same exact holding is an idempotent receipt");
  const reset = commands.find((command) => command.type === "new_session");
  assert.ok(reset, "ready resident accepts fresh assignment without waiting for a nonexistent turn");
  child.stdout.write(JSON.stringify({ type: "response", command: "new_session", id: reset.id, success: true, data: { cancelled: false } }) + "\n");
  await new Promise((resolve) => setImmediate(resolve));
  assert.ok(commands.some((command) => command.type === "prompt" && command.message?.includes("Recover existing work")));
  console.log("UNASSIGNED_START_OK");
  }
  }
} finally {
  shutdownTeamMachine();
  child.emit("close", 0, null);
  mock.restoreAll();
}
