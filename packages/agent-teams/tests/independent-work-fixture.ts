import assert from "node:assert/strict";
import childProcess from "node:child_process";
import { EventEmitter } from "node:events";
import { syncBuiltinESMExports } from "node:module";
import { PassThrough, Writable } from "node:stream";
import { mock } from "node:test";
import type { ExtensionAPI, ToolDefinition } from "@earendil-works/pi-coding-agent";

const probe = process.argv[2] ?? "independent";
type Command = { type: string; id: string; message?: string };
type FixtureChild = EventEmitter & {
  stdin: Writable; stdout: PassThrough; stderr: PassThrough; pid: number;
  exitCode: number | null; signalCode: NodeJS.Signals | null;
  commands: Command[]; responses: Command[]; closed: boolean;
  kill: (signal?: NodeJS.Signals) => boolean;
};
const children: FixtureChild[] = [];
// Real processes keep readiness's unref'ed deadline alive. This OS double must
// do the same, without changing the shipping acknowledgement timeout.
const watchdog = setTimeout(() => { throw new Error(`RPC fixture stalled: ${probe}`); }, 40_000);
mock.method(childProcess, "spawn", () => {
  const child: FixtureChild = Object.assign(new EventEmitter(), {
    // No OS PID: termination must call our kill seam, never signal a real group.
    pid: 0, exitCode: null, signalCode: null, closed: false,
    stdin: new Writable(), stdout: new PassThrough(), stderr: new PassThrough(),
    commands: [] as Command[], responses: [] as Command[],
    kill(signal: NodeJS.Signals = "SIGTERM") {
      if (child.closed) return false;
      child.closed = true;
      child.signalCode = signal;
      child.stdin.destroy();
      child.stdout.end();
      child.stderr.end();
      child.emit("close", null, signal);
      return true;
    },
  });
  child.stdin = new Writable({ write(chunk, _encoding, done) {
    const command = JSON.parse(String(chunk)) as Command;
    assert.ok(command.id, "every response is correlated to a parsed request");
    assert.ok(["get_state", "prompt"].includes(command.type), command.type);
    child.commands.push(command);
    done();
    // Go through stdout JSONL and the real spawner parser, not a resolved spawn
    // promise. A wrong id is deliberately ignored until the real timeout.
    setImmediate(() => {
      if (child.closed || probe.endsWith("-timeout")) return;
      const rejected = probe.endsWith("-rejected");
      const response = {
        type: "response", id: probe === "prompt-wrong-id" ? `${command.id}-wrong` : command.id,
        command: command.type, success: !rejected,
        ...(rejected ? { error: "Fixture rejected input" } : { data: command.type === "get_state"
          ? { isStreaming: probe === "readiness-not-idle", isCompacting: false, pendingMessageCount: 0 }
          : { disposition: probe === "prompt-handled" ? "handled" : "started" } }),
      };
      child.responses.push(command);
      child.stdout.write(`${JSON.stringify(response)}\n`);
    });
  } });
  children.push(child);
  return child;
});
syncBuiltinESMExports();

const { registerLeaderTools } = await import("../src/tools.ts");
const { registerTaskTools } = await import("@fradser/pi-tasks");
const { clearSessionAgents, registerIntentTools, registerSessionAgent } = await import("@fradser/pi-subagents");
const { resetState } = await import("../src/state.ts");
const { initTeamMachine, shutdownTeamMachine } = await import("../src/team-machine.ts");
const { SessionManager } = await import("@earendil-works/pi-coding-agent");

const context = { cwd: process.cwd(), sessionManager: SessionManager.inMemory(process.cwd()), model: undefined };
interface FixtureResult {
  text: string;
  details: { ok?: boolean; outcome?: string; disposition?: string; session?: string; work?: unknown;
    sessions?: Array<{ session: string; status: string }> };
}
try {
  resetState();
  clearSessionAgents();
  initTeamMachine(context, { sendUpdate() {}, notifyChange() {} });
  registerSessionAgent({ name: "reviewer", description: "Review", prompt: "Review thoroughly", tools: ["read"] });
  const tools = new Map<string, ToolDefinition>();
  const host = {
    registerTool(tool: ToolDefinition) { tools.set(tool.name, tool); },
    getActiveTools() { return []; }, setActiveTools() {},
  } as unknown as ExtensionAPI;
  registerLeaderTools(host);
  registerIntentTools(host);
  registerTaskTools(host);
  /** The intent tool each child operation belongs to; the retired single tool is gone. */
  const childTool = (operation: string): ToolDefinition => {
    const name = operation === "input" || operation === "steer" ? "agent_input"
      : operation === "stop" ? "agent_stop"
      : operation === "list" ? "agent_list" : "agent_start";
    const tool = tools.get(name);
    assert.ok(tool, `the fixture registers ${name}`);
    return tool;
  };
  const call = async (params: Record<string, unknown>): Promise<FixtureResult> => {
    const { operation, name, session, prompt, tools: grant, ...rest } = params;
    const toolName = operation === "input" || operation === "steer" ? "agent_input"
      : operation === "stop" ? "agent_stop"
      : operation === "list" ? "agent_list" : "agent_start";
    const args = toolName === "agent_start"
      ? { prompt, ...(name === undefined ? {} : { label: name }), ...(grant === undefined ? {} : { tools: grant }), ...rest }
      : toolName === "agent_input" ? { session, prompt, delivery: operation === "steer" ? "steer" : "next" }
      : session === undefined ? { ...rest } : { session, ...rest };
    const result = await childTool(String(operation ?? "start")).execute("call", args, undefined, undefined, context as never);
    assert.ok(result.details && typeof result.details === "object");
    return {
      text: result.content.map(block => block.type === "text" ? block.text : "").join("\n"),
      details: result.details as FixtureResult["details"],
    };
  };
  const start = async (params: Record<string, unknown>) => {
    let completed = false;
    const pending = Promise.resolve(call(params)).then(result => { completed = true; return result; });
    assert.equal(completed, false, "start must not return after a writable pipe alone");
    assert.equal(children.at(-1)!.responses.length, 0, "fixture has not acknowledged this child yet");
    const result = await pending;
    const child = children.at(-1)!;
    if (result.details.ok) {
      assert.equal(child.responses.length, 1, "success requires a parsed RPC response");
      assert.equal(child.closed, false);
    }
    return result;
  };

  if (probe !== "independent") {
    // The intent family has no promptless startup, so a prompted start is the only
    // shape left and the child acknowledges the prompt over RPC. An unparsed or
    // refused acknowledgement still cannot become `started`.
    const result = await start({ operation: "start", name: "reviewer", prompt: "Audit authentication" });
    assert.equal(children.length, 1);
    assert.equal(children[0].commands[0].type, "prompt");
    if (probe === "readiness") {
      assert.equal(result.details.disposition, "started", result.text);
      const listed = await call({ operation: "list" });
      assert.equal(listed.details.disposition, "listed", listed.text);
      assert.ok(listed.details.sessions!.some((entry) => entry.session === result.details.session), listed.text);
      const stopped = await call({ operation: "stop", session: result.details.session });
      assert.equal(stopped.details.disposition, "stopped", stopped.text);
    } else {
      assert.equal(result.details.ok, false, "an unacknowledged start cannot become started");
      // A failed start retains known stopped facts on the roster, not a claim
      // that the acknowledgement succeeded or the process remains alive.
      assert.match(result.details.session, /^session:/);
      assert.equal(result.details.state, "stopped");
      assert.match(result.text, /did not accept its initial prompt/);
    }
    assert.equal(children[0].closed, true, "failure and stop both confirm process closure");
    console.log(`RPC_CONFIRMATION_OK ${probe}`);
  } else {
    const first = await start({ operation: "start", name: "reviewer", prompt: "Audit authentication" });
    assert.equal(first.details.disposition, "started", first.text);
    // A label is display text, so a second start under the same label is a second
    // child, not a duplicate: each start mints its own roster name and its own
    // handle, which is what makes the two sessions independent.
    const duplicate = await call({ operation: "start", name: "reviewer", prompt: "Audit authorization" });
    assert.equal(duplicate.details.ok, true, duplicate.text);
    assert.equal(duplicate.details.disposition, "started", duplicate.text);
    assert.notEqual(duplicate.details.session, first.details.session);
    assert.equal(children.length, 2);
    const stopped = await call({ operation: "stop", session: duplicate.details.session });
    assert.equal(stopped.details.disposition, "stopped", stopped.text);
    const second = await start({ operation: "start", name: "authorization-reviewer", prompt: "Audit authorization", instructions: "Review thoroughly" });
    assert.equal(second.details.disposition, "started", second.text);
    // Independence is per session and per handle, and neither carries a work id:
    // a spawn records no task, so there is no shared identity to diverge.
    assert.equal(children.length, 3);
    assert.equal(first.details.work, undefined);
    assert.equal(second.details.work, undefined);
    assert.notEqual(first.details.session, second.details.session);
    assert.match(children[0].commands[0].message ?? "", /Audit authentication/);
    assert.match(children[1].commands[0].message ?? "", /Audit authorization/);
    assert.match(children[2].commands[0].message ?? "", /Audit authorization/);

    // `list` reports every incarnation by its exact handle, so the three handles
    // can be compared directly and no two of them share one identity.
    const listed = await call({ operation: "list" });
    assert.equal(listed.details.disposition, "listed", listed.text);
    const handles = listed.details.sessions!.map((entry) => entry.session);
    for (const expected of [first.details.session, second.details.session]) {
      assert.ok(handles.includes(expected as string), `${expected} is absent from ${JSON.stringify(handles)}`);
    }
    assert.equal(new Set(handles).size, handles.length, "each roster row carries its own exact handle");
    // The roster holds no entry for a handle it never recorded: an unknown
    // incarnation is absence of recorded facts, not a liveness claim.
    assert.ok(!handles.includes("session:missing:old"), JSON.stringify(handles));
    assert.ok(listed.details.sessions!.every((entry) => entry.status !== undefined));
    for (const session of [first.details.session, second.details.session]) {
      const stopped = await call({ operation: "stop", session });
      assert.equal(stopped.details.disposition, "stopped", stopped.text);
    }
    assert.ok(children.every(child => child.closed), "each session's child confirms close");
    console.log("INDEPENDENT_WORK_OK");
  }
} finally {
  for (const child of children) if (!child.closed) child.kill();
  clearTimeout(watchdog);
  shutdownTeamMachine();
  resetState();
  clearSessionAgents();
  mock.restoreAll();
  syncBuiltinESMExports();
}
