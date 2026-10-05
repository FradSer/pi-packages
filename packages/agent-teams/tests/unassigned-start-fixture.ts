import assert from "node:assert/strict";
import childProcess from "node:child_process";
import { EventEmitter } from "node:events";
import { syncBuiltinESMExports } from "node:module";
import { PassThrough, Writable } from "node:stream";
import { mock } from "node:test";

/** No task tool may name a participant to hand a task to.
 *
 *  The single `task` tool used to be callable with `action: "assign"` and refuse.
 *  With four tools and no verb for it, the property is stronger and is asserted
 *  over the task surface: no parameter on any of the four names a participant.
 *  Scoped to those four on purpose — the `agent` tool has a `session` handle of
 *  its own, which is a different tool's business. */
function assertNoParticipantDirective(): void {
  const names = [...TASK_CAPABILITY_TOOLS].filter((name) => tools.has(name));
  const banned = ["assign", "assignee", "owner", "target", "participant", "agent", "spawnId", "session"];
  assert.deepEqual(names, [...TASK_CAPABILITY_TOOLS], "the four task tools are registered");
  for (const name of names) {
    const properties = (tools.get(name)!.parameters as { properties?: Record<string, unknown> }).properties ?? {};
    for (const key of Object.keys(properties)) {
      for (const word of banned) {
        assert.equal(key.toLowerCase().includes(word), false, `${name} must not offer ${key}`);
      }
    }
  }
}


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
const { TASK_CAPABILITY_TOOLS, registerTaskTools } = await import("@fradser/pi-tasks");
const { registerIntentTools } = await import("@fradser/pi-subagents");
const { exactSessionRoute, setAgentHost } = await import("@fradser/pi-subagents");
const { initTeamMachine, shutdownTeamMachine, wakeIdleTeammates, deliverFeedback, routePeerInboxes, spawnAgent, sendResidentSequence, interruptResidentSequence, shutdownAgentExact } = await import("../src/team-machine.ts");
const { getState, resetState, takeTask } = await import("../src/state.ts");
const root = process.env.PI_TEST_DIR;
assert.ok(root);
resetState();
initTeamMachine({ sessionManager: undefined, cwd: root }, { sendUpdate() {}, notifyChange() {} });
const tools = new Map();
const host = { registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools: () => [], setActiveTools() {} };
registerLeaderTools(host);
registerIntentTools(host);
registerTaskTools(host);
// The `agent` tool belongs to @fradser/pi-subagents, so the team spawn path
// reaches it the only way it can: by publishing itself as the coordinator. These
// assertions are about the team behaviour, so they have to drive the real host
// rather than the raw spawner underneath it.
setAgentHost({
  async start(request) {
    const definition = request.definition ?? { description: request.name, prompt: "" };
    const spawned = spawnAgent({
      name: request.name,
      role: request.name,
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
    return { ok: true, session: exactSessionRoute(spawned.agent.name, spawned.agent.spawnId) };
  },
  send: sendResidentSequence,
  interrupt: interruptResidentSequence,
  stop: shutdownAgentExact,
});
const ctx = { cwd: root };
try {
  const created = await tools.get("create_task").execute("create", { subject: "Recover existing work" }, undefined, undefined, ctx);
  const mode = process.env.PI_TEST_MODE;
  if (["timeout", "exit", "not-ready", "rejected"].includes(mode ?? "")) {
    // The intent family addresses children by their own tools; a label is display text.
    const starting = tools.get("agent_start").execute("start", { label: "recovery", prompt: "Read assigned evidence", tools: ["read"] }, undefined, undefined, ctx);
    // A refused action is reported, not thrown. The tool returns an error result
    // for every refusal, so a caller reads one shape whether the refusal came
    // from validation, a conflict, or a child that never came up.
    const refused = await starting;
    assert.equal(refused.details.ok, false, "unconfirmed readiness must not report startup success");
    // The structured failure keeps its known exact diagnostic handle; it does
    // not confer living control authority or claim readiness succeeded.
    assert.match(refused.details.session, /^session:/);
    assert.equal(refused.details.ok, false);
    // This fixture's host can return before its close cleanup; readback must
    // report the actually retained state, not guess stopped from a refusal.
    // The receipt's state is read back from the roster entry its own handle names,
    // because the intent family mints the roster name and a label is display text.
    const refusedName = (refused.details.session ?? "").split(":")[1] ?? "";
    assert.equal(refused.details.state, getState().agents[refusedName]?.status ?? "unknown");
    assert.match(refused.content[0].text, /acknowledgement|timeout|exited|closed|readiness/i, refused.content[0].text);
    console.log("UNASSIGNED_START_OK");
  } else {
  // The intent family starts a child only with work, so the idle-resident shape
  // these scenarios are about comes from the coordinator's own spawn, which is
  // where a team creates a participant that waits for an assignment.
  const idle = spawnAgent({ name: "recovery", role: "recovery",
    definition: { description: "Recovery", prompt: "Read assigned evidence" }, tools: ["read"] });
  assert.ok(idle.ok, "the coordinator spawns an idle resident");
  if (idle.readiness) { const failure = await idle.readiness; assert.equal(failure, undefined, failure); }
  const session = exactSessionRoute(idle.agent.name, idle.agent.spawnId);
  assert.match(session, /^session:/, "the coordinator returns an exact handle");
  const inspected = await tools.get("agent_inspect").execute("inspect", { session }, undefined, undefined, ctx);
  assert.equal(inspected.details.sessions[0].status, "idle", "awaited public start must resolve native readiness");
  // An unassigned resident must not acquire a task by being started: the tasks
  // states what must be done, and a participant takes it.
  assert.equal(inspected.details.sessions[0].currentTaskId, undefined, "unassigned start must not fabricate Work identity");
  assert.equal(inspected.details.sessions[0].assignment, undefined, "unassigned start must not fabricate an assignment");
  assert.equal(commands.some((command) => command.type === "prompt"), false, "unassigned start must not execute a model kickoff");
  assert.equal(getState().agents.recovery.status, "idle");
  const ready = commands.find((command) => command.type === "get_state");
  assert.ok(ready, "native readiness requires an acknowledged control request");
  assert.equal(getState().agents.recovery.status, "idle");
  if (mode === "notice" || mode === "inbox") {
    if (mode === "inbox") {
      // Prevent a task set notice from masking the ordinary first-wake path.
      getState().agents.recovery.noticedTaskIds = [created.details.id];
      deliverFeedback("recovery", "Context", "Read-only context, no new assignment");
      routePeerInboxes();
    }
    wakeIdleTeammates();
    const wake = commands.find((command) => command.type === "prompt");
    assert.match(wake?.message ?? "", /Read assigned evidence/);
    if (mode === "notice") assert.match(wake?.message ?? "", /=== TASK NOTICE ===/);
    else {
      assert.match(wake?.message ?? "", /Read-only context/);
      assert.doesNotMatch(wake?.message ?? "", /=== TASK NOTICE ===/);
    }
    assert.equal(getState().tasks[created.details.id].status, "pending");
    console.log("UNASSIGNED_START_OK");
  } else if (mode === "in_progress") {
    takeTask(created.details.id, "recovery");
    assert.equal(getState().agents.recovery.currentTaskId, created.details.id);
    // Nothing may direct the assignment at a named participant. The task states
    // what must be done; the participant takes it. With four tools there is no
    // verb to call at all, so the property is asserted over the whole surface
    // rather than as one refusal.
    assertNoParticipantDirective();
    assert.equal(getState().tasks[created.details.id].status, "in_progress", "a refused assign changes nothing");
    console.log("UNASSIGNED_START_OK");
  } else {
    // The same rule in the plain case: the resident takes the task itself, and
    // there is no leader-side verb that can hand it over.
    assertNoParticipantDirective();
    assert.equal(getState().tasks[created.details.id].status, "pending");
    assert.equal(getState().agents.recovery.currentTaskId, undefined, "an unstarted resident holds nothing");
    assert.equal(commands.some((command) => command.type === "new_session"), false, "no fresh session is created by a refused assignment");
    console.log("UNASSIGNED_START_OK");
  }
  }
} finally {
  shutdownTeamMachine();
  child.emit("close", 0, null);
  mock.restoreAll();
}
