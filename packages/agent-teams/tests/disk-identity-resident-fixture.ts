import assert from "node:assert/strict";
import childProcess from "node:child_process";
import { EventEmitter } from "node:events";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import path from "node:path";
import { PassThrough, Writable } from "node:stream";
import { mock } from "node:test";

const mode = process.env.PI_TEST_MODE ?? "accepted";
const root = process.env.PI_TEST_DIR!;
assert.ok(root && process.env.HOME && process.env.PI_CODING_AGENT_DIR);
const config = process.env.PI_CODING_AGENT_DIR!;
assert.ok(path.resolve(config).startsWith(path.resolve(root) + path.sep), "Pi config must be isolated");
const project = path.join(root, "project");
mkdirSync(project, { recursive: true });
type Command = { type: string; id: string; message?: string; streamingBehavior?: string };
const commands: Command[] = [];
const launches: Array<{ args: string[]; cwd?: string; env?: NodeJS.ProcessEnv }> = [];
const children: Array<ReturnType<typeof makeChild>> = [];
function makeChild() {
  const child = Object.assign(new EventEmitter(), {
    // A mock must never cause terminateChildProcess to signal a real OS group.
    pid: 0,
    stdout: new PassThrough(), stderr: new PassThrough(),
    kill() { setImmediate(() => child.emit("close", 0, "SIGTERM")); return true; },
    stdin: new Writable({ write(chunk, _encoding, done) {
      commands.push(JSON.parse(String(chunk)) as Command);
      done();
    } }),
  });
  return child;
}
mock.method(childProcess, "spawn", (_command: string, args: string[], options: childProcess.SpawnOptions) => {
  const child = makeChild();
  children.push(child);
  launches.push({ args: [...args], cwd: typeof options?.cwd === "string" ? options.cwd : undefined, env: options?.env });
  return child;
});
syncBuiltinESMExports();
const subagents = await import("@fradser/pi-subagents");
const { publishAgentHost } = await import("../src/agent-host.ts");
const { initTeamMachine, shutdownTeamMachine, spawnAgent, applyProgress, teardownAgents, drainTeammateOutboxes, setVerifyGateRunner } = await import("../src/team-machine.ts");
const { appendWorkerEvent } = await import("../src/statefile.ts");
const { getAgent, getTask, resetState } = await import("../src/state.ts");
const ctx = { cwd: project };
resetState();
const reports: import("@fradser/pi-subagents").LeaderReport[] = [];
initTeamMachine(ctx as never, { sendUpdate(report) { reports.push(report); }, notifyChange() {} });
publishAgentHost();
const host = subagents.resolveAgentHost()!;
function respond(command: Command, success = true, disposition = "started") {
  children.at(-1)!.stdout.write(JSON.stringify({ type: "response", command: command.type, id: command.id,
    success, error: success ? undefined : "test input rejected", data: command.type === "get_state"
      ? { isStreaming: false, isCompacting: false, pendingMessageCount: 0 } : { disposition } }) + "\n");
}
const next = () => new Promise<void>(resolve => setImmediate(resolve));
function diskDefinition(file: string, body: string) {
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, `---\nname: saved\ndescription: Saved role\ntools: read, bash\n---\n${body}\n`);
}
async function settle(body: string) {
  const agent = getAgent("temporary")!;
  const assignmentId = agent.assignment!.id;
  appendWorkerEvent(launches[0].env!.PI_TEAMMATE_OUTBOX_FILE!, { id: `result-${reports.length}`, type: "message",
    worker: agent.name, spawnId: agent.spawnId, assignmentId, body, status: "completed", timestamp: Date.now() });
  children[0].stdout.write([
    { type: "message_end", message: { role: "assistant", content: [{ type: "text", text: body }], stopReason: "stop" } },
    { type: "agent_settled" },
  ].map(event => JSON.stringify(event) + "\n").join(""));
  drainTeammateOutboxes();
  await next();
  assert.equal(agent.status, "idle");
}
try {
  if (mode === "intent-fast-report") {
    const starting = subagents.executeIntentTool("agent_start", { prompt: "First evidence", label: "temporary", tools: ["read"] }, { cwd: project });
    const agent = subagents.livingAgents()[0]!;
    const session = `session:${agent.name}:${agent.spawnId}`;
    const firstInputId = agent.inputId;
    const firstTask = agent.currentTaskId!;
    const queued = await subagents.executeIntentTool("agent_input", { session, prompt: "Second evidence", delivery: "next" }, { cwd: project });
    assert.equal(queued.structuredContent.ok, true);
    children[0].stdout.write([
      { type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "First evidence" }], stopReason: "stop" } },
      { type: "agent_settled" },
    ].map(event => JSON.stringify(event) + "\n").join(""));
    // Simulate the worker's final report reaching the outbox after the settle edge.
    appendWorkerEvent(launches[0].env!.PI_TEAMMATE_OUTBOX_FILE!, { id: "late-first", type: "message", worker: agent.name,
      spawnId: agent.spawnId, assignmentId: agent.assignment!.id, body: "First evidence", status: "completed", timestamp: Date.now() });
    respond(commands[0]);
    const start = await starting;
    assert.equal(start.structuredContent.ok, true);
    await next();
    assert.equal(commands.filter(command => command.type === "prompt").length, 2, "late prior report must complete before queued dispatch");
    assert.equal(getTask(firstTask)?.status, "completed", "prior task is not parked after sequence metadata changes");
    const firstReport = reports.find(report => report.finished && report.body === "First evidence");
    assert.equal(firstReport?.inputId, firstInputId, "prior result retains its original input ID");
    assert.equal(agent.inputId, queued.structuredContent.inputId);
    respond(commands.at(-1)!);
    await next();
    appendWorkerEvent(launches[0].env!.PI_TEAMMATE_OUTBOX_FILE!, { id: "second", type: "message", worker: agent.name,
      spawnId: agent.spawnId, assignmentId: agent.assignment!.id, body: "Second evidence", status: "completed", timestamp: Date.now() });
    children[0].stdout.write([
      { type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "Second evidence" }], stopReason: "stop" } },
      { type: "agent_settled" },
    ].map(event => JSON.stringify(event) + "\n").join(""));
    await next();
    assert.deepEqual(reports.filter(report => report.finished).map(report => report.inputId), [firstInputId, queued.structuredContent.inputId]);
    assert.equal(launches.length, 1);
  } else if (["late-negative", "pending-start", "gate-on-drain"].includes(mode)) {
    const starting = host.start({ name: "temporary", prompt: "First evidence", definition: { description: "Evidence", prompt: "Report evidence", tools: ["read"] } });
    if (mode !== "pending-start") respond(commands.at(-1)!);
    else {
      await settle("First evidence");
      const before = commands.length;
      const sending = host.send!("temporary", getAgent("temporary")!.spawnId, "Sibling input");
      assert.equal(commands.length, before, "pending startup acknowledgement must reserve the incarnation");
      assert.equal((await sending).ok, false);
      respond(commands[0]);
    }
    assert.ok((await starting).ok);
    const agent = getAgent("temporary")!;
    if (mode === "late-negative") {
      await settle("First evidence");
      const sending = host.send!(agent.name, agent.spawnId, "Second evidence");
      const control = commands.at(-1)!;
      await settle("Second evidence");
      assert.equal(agent.reportSequenceEnded, true);
      respond(control, false);
      assert.equal((await sending).ok, false);
      assert.equal(agent.reportSequenceEnded, true, "late negative ack cannot reopen settled report authority");
      assert.equal(reports.filter(report => report.finished).length, 2);
    } else if (mode === "gate-on-drain") {
      const task = getTask(agent.currentTaskId!)!;
      task.verify = "Inspect evidence independently";
      setVerifyGateRunner(() => new Promise(() => {}));
      applyProgress(agent.name, agent.spawnId, { text: "Evidence", turns: 1, finalResponse: true });
      appendWorkerEvent(launches[0].env!.PI_TEAMMATE_OUTBOX_FILE!, { id: "gated-final", type: "message", worker: agent.name,
        spawnId: agent.spawnId, assignmentId: agent.assignment!.id, body: "Evidence", status: "completed", timestamp: Date.now() });
      const before = commands.length;
      const sending = host.send!(agent.name, agent.spawnId, "Bypass the gate");
      assert.equal(commands.length, before, "drained final report must freeze verification before input delivery");
      assert.equal((await sending).ok, false);
      assert.equal(getTask(task.id)?.status, "in_progress");
    }
  } else if (["two-results", "idle-send", "interrupt", "interrupt-rejected", "interrupt-handled", "interrupt-timeout", "interrupt-exit", "send-rejected", "send-handled", "send-timeout", "send-exit", "send-fast-result"].includes(mode)) {
    const starting = subagents.executeChildIntent({ operation: "start", name: "temporary", ...(mode === "idle-send" ? {} : { prompt: "First evidence" }),
      description: "Evidence", role_prompt: "Report evidence", tools: ["read"] }, { cwd: project });
    respond(commands.at(-1)!);
    const started = await starting;
    assert.equal(started.details.ok, true, started.content[0].text);
    const agent = getAgent("temporary")!;
    const originalSession = String(started.details.session);
    const firstAttempt = agent.assignment?.id;
    if (mode.startsWith("interrupt")) {
      const interrupt = (host as typeof host & { interrupt(name: string, spawnId: string, input: string): Promise<{ ok: boolean; error?: string }> }).interrupt;
      assert.equal(typeof interrupt, "function", "host must expose exact acknowledged interrupt");
      let returned = false;
      const steering = subagents.executeChildIntent({ operation: "input", delivery: "steer", session: originalSession, prompt: "Keep it read-only" })
        .then(result => { returned = true; return result; });
      await next();
      assert.equal(returned, false, "steer waits for native acknowledgement, not pipe write");
      assert.equal(commands.at(-1)!.streamingBehavior, "steer");
      assert.equal(agent.assignment?.id, firstAttempt);
      if (mode === "interrupt-exit") children[0].emit("close", 1, null);
      else if (mode !== "interrupt-timeout") respond(commands.at(-1)!, mode !== "interrupt-rejected", mode === "interrupt-handled" ? "handled" : "queued");
      const steered = await steering;
      assert.equal(steered.details.ok, mode === "interrupt", steered.content[0].text);
      if (mode !== "interrupt-exit") {
        assert.equal(agent.status, "working");
        assert.equal(agent.assignment?.id, firstAttempt);
        await settle("Steered evidence");
        assert.equal(reports.filter(report => report.finished).length, 1);
        assert.equal((await interrupt(agent.name, agent.spawnId, "Idle steer")).ok, false);
      }
      assert.equal((await interrupt(agent.name, "retired", "Wrong incarnation")).ok, false);
    } else {
      if (mode !== "idle-send") await settle("First evidence");
      assert.equal(getAgent(agent.name)?.assignment, undefined, "first result retires task authority");
      const send = (host as typeof host & { send(name: string, spawnId: string, input: string): Promise<{ ok: boolean; error?: string }> }).send;
      assert.equal(typeof send, "function", "host must expose exact acknowledged send");
      let returned = false;
      subagents.registerSessionAgent({ name: "temporary", description: "Changed later", prompt: "Wrong late role", tools: ["read"] });
      const sending = subagents.executeChildIntent({ operation: "input", delivery: "next", session: originalSession, prompt: "Second evidence" })
        .then(result => { returned = true; return result; });
      await next();
      assert.equal(returned, false, "hosted send waits for native input acceptance");
      assert.ok(agent.assignment && agent.currentTaskId, "next attempt is visible before input delivery");
      assert.notEqual(agent.assignment.id, firstAttempt);
      const secondAttempt = agent.assignment.id;
      const secondTask = agent.currentTaskId;
      const prompt = commands.at(-1)!;
      assert.doesNotMatch(prompt.message!, /Wrong late role/);
      if (mode === "idle-send") assert.match(prompt.message!, /Report evidence/, "first input retains pinned launch role");
      else assert.doesNotMatch(prompt.message!, /ROLE PROMPT|Report evidence/, "later send does not repeat role");
      assert.equal((await send(agent.name, agent.spawnId, "Duplicate")).ok, false, "no second input while reserved");
      if (mode === "send-exit") children[0].emit("close", 1, null);
      else if (mode !== "send-timeout") {
        if (mode === "send-fast-result") await settle("Second evidence");
        respond(commands.at(-1)!, mode !== "send-rejected", mode === "send-handled" ? "handled" : "started");
      }
      const sent = await sending;
      if (["send-rejected", "send-handled", "send-timeout", "send-exit"].includes(mode)) {
        assert.equal(sent.details.ok, false);
        if (mode === "send-timeout") {
          assert.equal(agent.assignment?.id, secondAttempt, "uncertain acceptance retains authority");
          assert.equal(getTask(secondTask)?.status, "in_progress");
          assert.match(sent.content[0].text, /may already have started|uncertain/i);
          assert.equal(agent.status, "working", "tool routing must not erase uncertain host reservation");
        } else assert.notEqual(getTask(secondTask)?.status, "in_progress");
      } else {
        assert.equal(sent.details.ok, true, sent.content[0].text);
        if (mode !== "send-fast-result") await settle("Second evidence");
        drainTeammateOutboxes();
        const results = reports.filter(report => report.finished);
        assert.deepEqual(results.map(report => report.body), mode === "idle-send" ? ["Second evidence"] : ["First evidence", "Second evidence"]);
        assert.ok(results.every(report => report.spawnId === agent.spawnId));
        assert.equal(new Set(results.map(report => report.assignmentId)).size, results.length);
        assert.equal(originalSession, `session:${agent.name}:${agent.spawnId}`);
        assert.equal(agent.status, "idle");
      }
      assert.equal((await send(agent.name, "retired", "Wrong incarnation")).ok, false);
    }
    assert.equal(launches.length, 1, "send/interrupt never spawn a replacement");
    assert.ok(!commands.some(command => command.type === "new_session"), "send retains this child's history");
  } else if (["accepted", "queued", "rejected", "handled", "exit", "timeout", "fast-result"].includes(mode)) {
    let returned = false;
    const starting = subagents.executeChildIntent({ operation: "start", name: "temporary", prompt: "Read evidence", tools: ["read"],
      description: "Evidence", role_prompt: "Report evidence" }, { cwd: project });
    const pending = starting.then(result => { returned = true; return result; });
    await next();
    assert.equal(returned, false, "host must await correlated kickoff acceptance, not writable stdin or spawn");
    const command = commands.find(entry => entry.type === "prompt")!;
    assert.ok(command);
    if (mode === "exit") children[0].emit("close", 1, null);
    else if (mode !== "timeout") {
      if (mode === "fast-result") {
        children[0].stdout.write([
          { type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "Evidence" }], stopReason: "stop" } },
          { type: "agent_settled" },
        ].map(event => JSON.stringify(event) + "\n").join(""));
      }
      respond(command, mode !== "rejected", mode === "handled" ? "handled" : mode === "queued" ? "queued" : "started");
    }
    const result = await pending;
    if (["rejected", "handled", "exit", "timeout"].includes(mode)) {
      assert.equal(result.details.ok, false, `${mode} cannot report accepted input`);
      assert.match(result.content[0].text, /accept|acknowledg|closed|exited|rejected/i);
    } else {
      assert.equal(result.details.ok, true, result.content[0].text);
      assert.match(String(result.details.session), /^session:temporary:/);
      assert.ok(!launches[0].args.includes("--session-dir"));
      assert.ok(launches[0].args.includes("--no-session"));
      assert.equal(launches[0].cwd, project);
      assert.equal(getAgent("temporary")?.status, mode === "fast-result" ? "idle" : "working");
      const agent = getAgent("temporary")!;
      applyProgress(agent.name, agent.spawnId, { text: "Evidence", turns: 1, finalResponse: true });
      assert.equal(getAgent(agent.name)?.status, "idle");
      assert.equal(getAgent(agent.name)?.spawnId, agent.spawnId);
      assert.ok(!existsSync(path.join(config, "agents", "temporary")), "temporary execution creates no durable data");
      const sending = subagents.executeChildIntent({ operation: "input", delivery: "next", session: `session:${agent.name}:${agent.spawnId}`, prompt: "Next evidence" });
      await next();
      respond(commands.at(-1)!);
      const sent = await sending;
      assert.equal(sent.details.ok, true, `settlement permits send to this exact incarnation: ${sent.content[0].text}`);
    }
  } else if (mode === "disk") {
    const user = path.join(config, "agents", "saved", "agent.md");
    const shared = path.join(project, ".pi", "agents", "saved", "agent.md");
    const local = path.join(project, ".pi", "agents", "saved.local", "agent.md");
    diskDefinition(user, "User instructions");
    diskDefinition(shared, "Project instructions");
    diskDefinition(local, "Local instructions");
    const originals = [user, shared, local].map(file => readFileSync(file, "utf8"));
    const started = spawnAgent({ name: "saved", role: "saved", prompt: "Inspect the original project", tools: ["read"],
      definition: { description: "Ignored inline", prompt: "Ignored inline", tools: ["write"] } } as Parameters<typeof spawnAgent>[0]);
    assert.equal(started.ok, true, started.ok ? "" : started.error);
    assert.equal(subagents.resolveAgent("saved", project)?.scope, "project-local");
    const prompt = commands.find(entry => entry.type === "prompt")!;
    assert.match(prompt.message!, /Local instructions/);
    assert.doesNotMatch(prompt.message!, /Ignored inline|User instructions/);
    respond(prompt);
    if (started.ok) {
      const failure = await started.readiness;
      assert.equal(failure, undefined);
      const agent = getAgent("saved")!;
      const workspace = path.join(config, "agents", "saved", "workspace");
      assert.equal(agent.cwd, project, "scratch data is not a checkout; launch retains the original project");
      assert.ok(existsSync(workspace));
      assert.deepEqual(agent.tools, ["read", "agent_memory", "message", "task"]);
      assert.ok(!("isolation" in agent));
      const args = launches[0].args;
      const sessionDir = args[args.indexOf("--session-dir") + 1];
      assert.ok(sessionDir.startsWith(path.join(config, "agents", "saved", "projects") + path.sep));
      assert.equal(path.basename(sessionDir), "session");
      assert.ok(!args.includes("--no-session"));
      assert.equal(launches[0].env?.PI_SUBAGENT_PROJECT_CWD, project);
      assert.ok(existsSync(path.join(config, "agents", "saved", "memory")));
      assert.ok(!existsSync(path.join(workspace, ".git")), "scratch workspace is not a checkout");
      applyProgress(agent.name, agent.spawnId, { text: "Durable evidence", turns: 1, finalResponse: true });
      assert.equal(agent.status, "idle");
      await teardownAgents();
      assert.ok(existsSync(workspace));
      assert.deepEqual([user, shared, local].map(file => readFileSync(file, "utf8")), originals);
      assert.ok(!existsSync(path.join(config, "workspaces")));
      assert.equal(launches.length, 1, "no Git/commit process may run");
    }
  } else if (mode === "registry-owner") {
    subagents.registerSessionAgent({ name: "retained", description: "Retain role", prompt: "Retain instructions", tools: [] });
    const register = (await import("../src/index.ts")).default;
    const events = new Map<string, (...args: unknown[]) => unknown>();
    const ui = { setWidget() {}, setStatus() {} };
    register({ on(name: string, handler: (...args: unknown[]) => unknown) { events.set(name, handler); }, registerTool() {}, registerCommand() {},
      registerMessageRenderer() {}, registerEntryRenderer() {} } as never);
    await events.get("session_start")!({}, { ...ctx, ui, mode: "print" });
    assert.equal(subagents.resolveAgent("retained", project)?.prompt, "Retain instructions",
      "team session setup must not clear the execution owner's temporary role history");
  } else throw new Error(`Unknown fixture mode ${mode}`);
  console.log(JSON.stringify({ ok: true, mode, launches: launches.length, commands: commands.length }));
} finally {
  shutdownTeamMachine();
  subagents.setAgentHost(undefined);
  for (const child of children) child.emit("close", 0, null);
  mock.restoreAll();
}
