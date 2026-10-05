import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import type { ChildProcess } from "node:child_process";
import { PassThrough } from "node:stream";
import { mock } from "node:test";
import * as kit from "@fradser/pi-kit";
import { FORK_CONTEXT_ACK_STATUS } from "../src/work-context.ts";

const children: Array<ReturnType<typeof makeChild>> = [];
const launches: Array<{ args: string[] }> = [];
let respond = true;
let rejected = false;
let delayTermination = false;
const commands: Array<{ type: string; id?: string; message?: string }> = [];
function makeChild() {
  const child = Object.assign(new EventEmitter(), {
    pid: 7,
    stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(),
    commands: [] as typeof commands,
  });
  child.stdin.on("data", chunk => {
    const command = JSON.parse(String(chunk));
    commands.push(command);
    child.commands.push(command);
    if (!respond) return;
    child.stdout.write(JSON.stringify({ type: "response", id: command.id, command: command.type,
      success: !rejected, data: command.type === "get_state" ? { isStreaming: false } : { disposition: "started" },
    }) + "\n");
  });
  return child;
}
mock.module("@fradser/pi-kit", {
  namedExports: { ...kit,
    resolvePiCli: () => ({ command: "fake-cli", args: [] }),
    spawnPiChild: (_command: string, args: string[]) => { launches.push({ args }); const child = makeChild(); children.push(child); return child; },
    terminateChildProcess: async (child: ChildProcess) => {
      if (delayTermination) await new Promise<void>(resolve => child.once("close", () => resolve()));
      else child.emit("close", null, "SIGTERM");
      return true;
    },
  },
});
const spawner = await import("../src/spawner.ts");
const frames: Array<{ text: string; finalResponse?: boolean; ready?: boolean; answerComplete?: boolean;
  stopReason?: string; errorMessage?: string; hasToolCalls?: boolean; missingFinal?: boolean }> = [];
const exits: Array<{ stdout: string }> = [];
const emit = (child: ReturnType<typeof makeChild>, records: unknown[]) => {
  child.stdout.write(records.map(record => JSON.stringify(record)).join("\n") + "\n");
};
const flush = () => new Promise<void>(resolve => setImmediate(resolve));
const answer = (text: string) => [
  { type: "agent_start" },
  { type: "message_end", message: { role: "assistant", content: [{ type: "text", text }] } },
  { type: "agent_settled" },
];
const start = (name: string, prompt = "Run") => spawner.spawnResident({ agentName: name, description: prompt, tools: [], onUpdate: frame => frames.push(frame), onExit: result => exits.push(result) });
const probe = process.argv[2];
if (probe === "fork-kickoff-timeout") {
  respond = false;
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const started = spawner.spawnResident({ agentName: "fork-deadline", description: "Run", context: [], tools: [], onExit: () => {} });
    assert.ok(!("error" in started));
    let outcome = "pending";
    const confirmation = started.accepted!.then(
      () => { outcome = "accepted"; },
      error => { assert.match(error.message, /execution may already have started/); outcome = "timed-out"; },
    );
    mock.timers.tick(5_001);
    await flush();
    assert.equal(outcome, "pending");
    assert.equal(commands.length, 1);
    const setup = commands[0];
    emit(children[0], [{ type: "extension_ui_request", method: "setStatus", statusKey: FORK_CONTEXT_ACK_STATUS,
      statusText: JSON.stringify({ version: 1, requestId: setup.id, success: true, messageCount: 0 }) }]);
    await flush();
    assert.equal(commands.length, 2, "Context setup dispatches one kickoff");
    const kickoff = commands[1];
    assert.equal(kickoff.type, "prompt");
    mock.timers.tick(4_999);
    await flush();
    assert.equal(outcome, "pending");
    mock.timers.tick(2);
    await confirmation;
    assert.equal(outcome, "timed-out", "An acknowledged fork no longer needs a cold-start budget");
    emit(children[0], [{ type: "response", id: kickoff.id, command: "prompt", success: true }]);
    await flush();
    assert.equal(outcome, "timed-out");
    assert.equal(commands.length, 2, "Expired kickoff is never repeated");
    children[0].emit("close", 0, null);
  } finally {
    mock.timers.reset();
  }
} else if (probe === "cancel-replace-late-ack") {
  const { executeChildIntent } = await import("../src/child-execution.ts");
  const roster = await import("../src/roster.ts");
  roster.resetRoster();
  respond = false;
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const call = (params: unknown, signal?: AbortSignal) => executeChildIntent(params, {
      cwd: process.env.TMPDIR!, parentSessionId: "race-parent", signal,
    });
    const controller = new AbortController();
    const original = call({ name: "replaced", prompt: "Original", tools: [] }, controller.signal);
    assert.equal(children.length, 1);
    const oldChild = children[0];
    const oldCommand = oldChild.commands[0];
    assert.equal(oldCommand.type, "prompt");
    controller.abort();
    const cancelled = await original;
    assert.equal(cancelled.details.outcome, "cancelled");
    assert.equal(cancelled.details.controlOutcome, "uncertain");
    assert.equal(cancelled.details.dispatched, true);
    const oldSession = cancelled.details.session;
    assert.equal(typeof oldSession, "string");
    assert.equal(oldSession, `session:replaced:${roster.getAgent("replaced")?.spawnId}`);
    assert.equal(roster.getAgent("replaced")?.status, "starting");
    assert.equal(oldChild.commands.length, 1, "Cancellation does not repeat startup input");

    delayTermination = true;
    const stopping = call({ operation: "stop", session: oldSession });
    await flush();
    assert.equal(roster.getAgent("replaced")?.leaderRequestedEnd, true);
    const beforeClose = await call({ name: "replaced", prompt: "Too early", tools: [] });
    assert.equal(beforeClose.details.ok, false, "Name remains reserved until close confirmation");
    assert.equal(children.length, 1);
    oldChild.emit("close", null, "SIGTERM");
    const stopped = await stopping;
    assert.equal(stopped.details.ok, true);
    assert.equal(stopped.details.session, oldSession);
    assert.equal(roster.getAgent("replaced")?.status, "stopped");
    delayTermination = false;

    let successorConfirmed = false;
    const successor = call({ name: "replaced", prompt: "Successor", tools: [] }).then(result => {
      successorConfirmed = true;
      return result;
    });
    const newChild = children[1];
    const newCommand = newChild.commands[0];
    const beforeLate = structuredClone(roster.getAgent("replaced"));
    assert.ok(beforeLate && beforeLate.status === "starting");
    assert.notEqual(`session:replaced:${beforeLate.spawnId}`, oldSession);
    emit(oldChild, [
      { type: "response", id: oldCommand.id, command: "prompt", success: true },
      { type: "response", id: newCommand.id, command: "prompt", success: true },
    ]);
    oldChild.emit("close", 0, null);
    mock.timers.tick(5_001);
    await flush();
    assert.equal(successorConfirmed, false, "Old child cannot confirm successor controls");
    assert.deepEqual(roster.getAgent("replaced"), beforeLate, "Old ACK and close cannot change successor facts");
    assert.equal(oldChild.commands.length, 1);
    assert.equal(newChild.commands.length, 1);
    emit(newChild, [{ type: "response", id: newCommand.id, command: "prompt", success: true }]);
    const accepted = await successor;
    assert.equal(accepted.details.ok, true);
    const newSession = accepted.details.session;
    assert.notEqual(newSession, oldSession);

    const stale = await call({ operation: "input", delivery: "next", session: oldSession, prompt: "Stale" });
    assert.equal(stale.details.ok, false, "Retired handle cannot control the replacement");
    emit(newChild, answer("Successor result"));
    await flush();
    assert.equal(roster.getAgent("replaced")?.status, "idle");
    const later = call({ operation: "input", delivery: "next", session: newSession, prompt: "Later" });
    assert.equal(newChild.commands.length, 2);
    const laterCommand = newChild.commands[1];
    emit(newChild, [{ type: "response", id: laterCommand.id, command: "prompt", success: true }]);
    assert.equal((await later).details.ok, true);
    assert.equal(newChild.commands.filter(command => command.message === "Later").length, 1);
    assert.equal(oldChild.commands.length, 1, "Subsequent input belongs only to the successor binding");
    assert.equal((await call({ operation: "stop", session: newSession })).details.ok, true);
  } finally {
    mock.timers.reset();
  }
} else if (probe?.startsWith("startup-delayed-")) {
  respond = false;
  mock.timers.enable({ apis: ["setTimeout"] });
  const fork = probe === "startup-delayed-fork";
  const idle = probe === "startup-delayed-idle";
  const started = fork
    ? spawner.spawnResident({ agentName: "cold", description: "Run", context: [], tools: [], onExit: () => {} })
    : start("cold", idle ? "" : "Run");
  assert.ok(!("error" in started));
  let outcome = "pending";
  const confirmation = (idle ? started.readiness! : started.accepted!).then(
    accepted => { outcome = accepted ? "accepted" : "refused"; },
    () => { outcome = "timed-out"; },
  );
  mock.timers.tick(5_001);
  await flush();
  assert.equal(outcome, "pending", "Pi loading time must not consume the running-resident deadline");
  assert.equal(commands.length, 1, "Cold startup writes one command");
  const command = commands[0];
  if (fork) {
    respond = true;
    emit(children[0], [{ type: "extension_ui_request", method: "setStatus", statusKey: FORK_CONTEXT_ACK_STATUS,
      statusText: JSON.stringify({ version: 1, requestId: command.id, success: true, messageCount: 0 }) }]);
  } else {
    emit(children[0], [{ type: "response", id: command.id, command: command.type, success: true,
      data: idle ? { isStreaming: false } : { disposition: "started" } }]);
  }
  await confirmation;
  assert.equal(outcome, "accepted");
  assert.equal(commands.length, fork ? 2 : 1, "Fork setup sends exactly one subsequent kickoff");
  children[0].emit("close", 0, null);
  mock.timers.reset();
} else if (probe === "startup-timeout" || probe === "resident-timeout") {
  mock.timers.enable({ apis: ["setTimeout"] });
  respond = probe === "resident-timeout";
  const started = start("deadline", probe === "resident-timeout" ? "" : "Run");
  assert.ok(!("error" in started));
  if (probe === "resident-timeout") await started.readiness;
  respond = false;
  const pending = probe === "startup-timeout" ? started.accepted! : spawner.deliverResidentPrompt("deadline", "Later");
  let outcome = "pending";
  const confirmation = pending.then(
    () => { outcome = "accepted"; },
    error => { assert.match(error.message, /execution may already have started/); outcome = "timed-out"; },
  );
  const command = commands.at(-1)!;
  mock.timers.tick(probe === "startup-timeout" ? 29_999 : 4_999);
  await flush();
  assert.equal(outcome, "pending");
  mock.timers.tick(2);
  await confirmation;
  assert.equal(outcome, "timed-out");
  emit(children[0], [{ type: "response", id: command.id, command: "prompt", success: true }]);
  await flush();
  assert.equal(outcome, "timed-out", "Late acknowledgements cannot revive expired controls");
  assert.equal(commands.length, probe === "startup-timeout" ? 1 : 2, "Timeout does not repeat input");
  children[0].emit("close", 0, null);
  mock.timers.reset();
} else if (probe === "later-message") {
  start("messages");
  const boundaries = [
    [{type:"message_start",message:{role:"assistant"}}, {type:"message_update",assistantMessageEvent:{type:"text_delta",delta:"latest draft"}}],
    [{type:"message_update",assistantMessageEvent:{type:"text_start"}}, {type:"message_update",assistantMessageEvent:{type:"text_delta",delta:"latest draft"}}],
    [{type:"message_update",assistantMessageEvent:{type:"text_delta",delta:"latest draft"}}],
    [{type:"message_update",assistantMessageEvent:{type:"thinking_start"}}],
    [{type:"message_update",assistantMessageEvent:{type:"toolcall_start"}}],
  ];
  for (const [index,boundary] of boundaries.entries()) {
    frames.length=0;
    emit(children[0],[{type:"agent_start"},
      {type:"message_end",message:{role:"assistant",stopReason:"stop",errorMessage:"previous diagnostics",content:[{type:"text",text:"previous complete"}]}},
      ...boundary,{type:"agent_settled"}]);
    await flush();
    const final=frames.find(frame=>frame.finalResponse);assert.ok(final);
    assert.equal(final.answerComplete,false,`Boundary ${index} cannot reuse prior message_end`);
    assert.equal(final.stopReason,undefined);assert.equal(final.errorMessage,undefined);
    assert.equal(final.missingFinal,true);assert.equal(final.text,index<3?"latest draft":"");
  }
  emit(children[0],[{type:"agent_start"},{type:"message_start",message:{role:"assistant"}},
    {type:"message_update",assistantMessageEvent:{type:"text_start"}},
    {type:"message_update",assistantMessageEvent:{type:"text_delta",delta:"first block"}},
    {type:"message_update",assistantMessageEvent:{type:"text_start"}},
    {type:"message_update",assistantMessageEvent:{type:"text_delta",delta:" second block"}},
    {type:"message_end",message:{role:"assistant",stopReason:"stop",content:[{type:"text",text:"authoritative final"}]}},
    {type:"agent_settled"}]);await flush();
  const settled=frames.at(-1)!;assert.equal(settled.text,"authoritative final");assert.equal(settled.answerComplete,true);
  children[0].emit("close",0,null);
} else if (probe === "stop-reason-budget") {
  start("reason");
  emit(children[0],[{type:"agent_start"},{type:"message_end",message:{role:"assistant",
    stopReason:"\u001b[31m"+"z".repeat(5000),content:[{type:"text",text:"original partial"}]}},{type:"agent_settled"}]);
  await flush();
  const final=frames.find(frame=>frame.finalResponse)!;assert.equal(final.stopReason,"unknown");
  assert.equal(final.text,"original partial");children[0].emit("close",0,null);
} else if (probe === "final-evidence") {
  start("evidence");
  emit(children[0],[{type:"agent_start"},
    {type:"message_end",message:{role:"assistant",content:[{type:"thinking",thinking:"No verdict"}],
      stopReason:"length",errorMessage:"x".repeat(5000)}},
    {type:"agent_settled"},{type:"agent_start"}]);
  await flush();
  const settled=frames.find(frame=>frame.finalResponse&&!frame.ready);assert.ok(settled);
  assert.equal(settled.text,"");assert.equal(settled.answerComplete,true);
  assert.equal(settled.stopReason,"length");assert.equal(settled.hasToolCalls,false);
  assert.ok(settled.errorMessage?.includes("truncated")&&settled.errorMessage.length<1200);
  const next=frames.at(-1)!;assert.equal(next.stopReason,undefined);assert.equal(next.errorMessage,undefined);
  assert.equal(next.answerComplete,false);
  emit(children[0],[{type:"agent_settled"}]);await flush();
  assert.equal(frames.at(-1)?.missingFinal,true);
  children[0].emit("close",0,null);
} else if (probe === "resume-symlink") {
  const fs = await import("node:fs");
  const path = await import("node:path");
  const sessionDir = path.join(process.env.TMPDIR!, "private-agent-session");fs.mkdirSync(sessionDir);
  const outside = path.join(process.env.TMPDIR!, "outside.jsonl");fs.writeFileSync(outside, "EXTERNAL HISTORY\n");
  fs.symlinkSync(outside, path.join(sessionDir, "history.jsonl"));
  const started=spawner.spawnResident({agentName:"unsafe",tools:[],session:"resume",sessionDir,onExit:()=>{}});
  assert.ok("error" in started, "Resume must fail before child creation");
  assert.equal(children.length,0);
  assert.equal(fs.readFileSync(outside,"utf8"),"EXTERNAL HISTORY\n");
} else if (probe === "session-dir" || probe === "fork-dir") {
  const fs = await import("node:fs");
  const path = await import("node:path");
  const sessionDir = path.join(process.env.TMPDIR!, "private-agent-session");
  const started = spawner.spawnResident({ agentName: "saved", tools: [], session: "persist", sessionDir, description: "Run",
    ...(probe === "fork-dir" ? { context: [] } : {}), onExit: result => exits.push(result) });
  assert.ok(!("error" in started));
  const args = launches[0].args;
  assert.equal(args[args.indexOf("--session-dir") + 1], sessionDir);
  assert.ok(!args.includes("--no-session"));
  if (probe === "fork-dir") {
    const file = args[args.indexOf("--session") + 1];
    assert.ok(file.startsWith(sessionDir));
    children[0].emit("close", 0, null);
    assert.ok(fs.existsSync(file), "persisted fork must survive process close");
  } else children[0].emit("close", 0, null);
} else if (probe === "kickoff-rejected") {
  rejected = true;
  const started = start("rejected");
  assert.ok(!("error" in started));
  assert.equal(await started.accepted, false, "kickoff acceptance uses the correlated prompt response");
  children[0].emit("close", 0, null);
} else if (probe === "long") {
  start("long");
  const text = "  " + "x".repeat(20_000) + "最终结论\n";
  emit(children[0], answer(text));
  await flush();
  assert.equal(frames.find(frame => frame.finalResponse)?.text, text, "settled output is complete and verbatim");
  children[0].emit("close", 0, null);
  assert.equal(exits[0].stdout, text, "exit output is not a diagnostic preview");
} else if (probe === "utf8") {
  start("utf8");
  const text = "中文\u2028中文\n";
  const bytes = Buffer.from(answer(text).map(record => JSON.stringify(record)).join("\n") + "\n");
  for (let offset = 0; offset < bytes.length; offset++) children[0].stdout.write(bytes.subarray(offset, offset + 1));
  await flush();
  assert.equal(frames.find(frame => frame.finalResponse)?.text, text);
  children[0].emit("close", 0, null);
} else if (probe === "unterminated") {
  start("unterminated");
  const text = "最终答案\n";
  children[0].stdout.write(Buffer.from(answer(text).map(record => JSON.stringify(record)).join("\n")));
  await flush();
  children[0].emit("close", 0, null);
  assert.equal(frames.find(frame => frame.finalResponse)?.text, text, "close must flush an unterminated final record");
  assert.equal(exits[0]?.stdout, text, "onExit must retain the parsed final answer");
} else if (probe === "successor-on-close") {
  const oldFrames: Array<{ turns: number; finalResponse?: boolean }> = [];
  const newFrames: Array<{ turns: number; finalResponse?: boolean }> = [];
  let successor: ReturnType<typeof spawner.spawnResident> | undefined;
  const old = spawner.spawnResident({ agentName: "reentrant", description: "old", tools: [],
    onUpdate: update => {
      oldFrames.push(update);
      if (update.finalResponse && update.turns === 4 && successor === undefined) {
        successor = spawner.spawnResident({ agentName: "reentrant", description: "new", tools: [],
          onUpdate: next => newFrames.push(next), onExit: () => {} });
      }
    }, onExit: () => {} });
  assert.ok(!("error" in old));
  for (let turn = 0; turn < 3; turn++) { emit(children[0], answer(`old-${turn}`)); await flush(); }
  children[0].stdout.write(Buffer.from(answer("old-close").map(record => JSON.stringify(record)).join("\n")));
  await flush();
  children[0].emit("close", 0, null);
  assert.ok(successor && !("error" in successor), "close-time result must be able to start a successor");
  emit(children[1], answer("new-result"));
  await flush();
  const final = newFrames.find(update => update.finalResponse);
  assert.equal(final?.turns, 1, `successor must have a fresh turn baseline: ${JSON.stringify(newFrames)}`);
  children[1].emit("close", 0, null);
} else if (probe === "readiness") {
  const result = start("idle", "");
  assert.ok(!("error" in result));
  assert.ok("readiness" in result, "prompt-less startup exposes native readiness");
  assert.equal(await result.readiness, true);
  assert.equal(await spawner.waitForResidentReady("idle"), true);
  assert.equal(commands.filter(command => command.type === "get_state").length, 1);
  children[0].emit("close", 0, null);
  assert.equal(await spawner.waitForResidentReady("idle"), false);
} else if (probe === "prompt") {
  const result = start("idle", "");
  assert.ok(!("error" in result));
  assert.ok(typeof spawner.deliverResidentPrompt === "function", "resident input acknowledges RPC acceptance");
  assert.equal(await result.readiness, true);
  assert.equal(await spawner.deliverResidentPrompt("idle", "one"), true, "synchronous ack is not lost");
  emit(children[0], answer("one"));
  rejected = true;
  assert.equal(await spawner.deliverResidentPrompt("idle", "reject"), false);
  rejected = false;
  respond = false;
  const pending = spawner.deliverResidentPrompt("idle", "close");
  children[0].emit("close", 0, null);
  assert.equal(await pending, false);
} else if (probe === "steer" || probe === "steer-timeout") {
  const started = start("steered");
  assert.ok(!("error" in started));
  assert.equal(await started.accepted, true);
  emit(children[0], [
    { type: "agent_start" },
    { type: "message_update", assistantMessageEvent: { type: "text_delta", contentIndex: 0, delta: "draft" } },
  ]);
  await flush();
  assert.equal(typeof spawner.deliverResidentSteer, "function");
  respond = false;
  let settled = false;
  const pending = spawner.deliverResidentSteer("steered", "change direction");
  if (probe === "steer-timeout") {
    await assert.rejects(pending, /acknowledgement timed out/);
    children[0].emit("close", 0, null);
  } else {
    pending.then(() => { settled = true; });
    const command = commands.at(-1)!;
    assert.equal(command.type, "prompt");
    assert.equal((command as { streamingBehavior?: string }).streamingBehavior, "steer");
    emit(children[0], [{ type: "response", id: command.id, command: "get_state", success: true }]);
    await flush();
    assert.equal(settled, false, "wrong command cannot acknowledge the steer");
    emit(children[0], [{ type: "response", id: command.id, command: "prompt", success: true, data: { disposition: "queued" } }]);
    assert.equal(await pending, true);
    emit(children[0], [
      { type: "message_update", assistantMessageEvent: { type: "text_delta", contentIndex: 0, delta: " tail" } },
      { type: "agent_settled" },
    ]);
    await flush();
    assert.equal(frames.find(frame => frame.finalResponse)?.text, "draft tail", "steer preserves the active text baseline");
    respond = true; rejected = true;
    assert.equal(await spawner.deliverResidentSteer("steered", "rejected"), false);
    rejected = false; respond = false;
    const closing = spawner.deliverResidentSteer("steered", "close");
    children[0].emit("close", 0, null);
    assert.equal(await closing, false);
  }
} else if (probe === "copies") {
  start("copies");
  const otherSpecifier = "../src/spawner.ts?second-copy=1";
  const other: typeof spawner = await import(otherSpecifier);
  assert.notEqual(other, spawner);
  assert.equal(await other.terminateAgent("copies").then(result => result.outcome), "closed");
} else if (probe === "tail") {
  start("tail");
  const text = "last answer";
  emit(children[0], answer(text));
  for (let index = 0; index < 100; index++) emit(children[0], [{ type: "other", content: "x".repeat(1_000) }]);
  emit(children[0], [{ type: "agent_start" }]);
  await flush();
  children[0].emit("close", 0, null);
  assert.equal(exits[0].stdout, text, "diagnostic eviction cannot erase settled output");
}
console.log(JSON.stringify({ ok: true, probe }));
