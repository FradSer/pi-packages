/** Full standalone entry + production spawner parser; only OS child creation is mocked. */
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { mock } from "node:test";
import * as kit from "@fradser/pi-kit";

const probe = process.argv[2];
const child = Object.assign(new EventEmitter(), {
  pid: 7, stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(),
});
const commands: Array<{ type: string; id?: string; message?: string }> = [];
child.stdin.on("data", chunk => {
  const command = JSON.parse(String(chunk)); commands.push(command);
  child.stdout.write(JSON.stringify({ type: "response", id: command.id, command: command.type,
    success: true, data: command.type === "get_state" ? { isStreaming: false } : { disposition: "started" } }) + "\n");
});
mock.module("@fradser/pi-kit", { namedExports: { ...kit,
  resolvePiCli: () => ({ command: "fixture-cli", args: [] }),
  spawnPiChild: () => child,
  terminateChildProcess: async () => { child.emit("close", 0, null); return true; },
} });
const { default: extension, getAgent, resetRoster } = await import("../index.ts");
import type { SessionNotice } from "../src/session-result.ts";
resetRoster();
const tools: Array<{ name: string; execute: (id: string, args: unknown, signal: unknown, update: unknown, ctx: unknown) => Promise<unknown> }> = [];
const notices: SessionNotice[] = [];
const pi = { registerTool: (tool: typeof tools[number]) => tools.push(tool), registerMessageRenderer() {},
  on() {}, events: { emit() {} }, sendMessage(message: { details: SessionNotice }) { notices.push(message.details); } };
extension(pi as never);
const call = async (request: { operation?: string; name?: string; session?: string; prompt?: string; tools?: string[] }) => {
  const { operation, name, session, prompt, tools: grant } = request;
  const tool = operation === "input" || operation === "steer" ? "agent_input" : operation === "inspect" ? "agent_list"
    : operation === "stop" ? "agent_stop" : operation === "list" ? "agent_list" : "agent_start";
  const params = tool === "agent_start"
    ? { prompt: prompt ?? "Start the assigned work.", ...(name === undefined ? {} : { label: name }), ...(grant === undefined ? {} : { tools: grant }) }
    : tool === "agent_input" ? { session: session!, prompt: prompt!, delivery: operation === "steer" ? "steer" : "next" }
    : { session: session! };
  const intent = tools.find(candidate => candidate.name === tool)!;
  return await intent.execute("parser", params, undefined, undefined, { cwd: process.env.PI_TEST_CWD }) as { details: { ok?: boolean; session?: string }; content: Array<{ text: string }> };
};
const emit = (records: unknown[]) => child.stdout.write(records.map(record => JSON.stringify(record)).join("\n") + "\n");
const first = await call({ name: "parse-review", prompt: "Review" });
assert.equal(first.details.ok, true, JSON.stringify(first));
const headers = [{ type: "agent_start" }, { type: "message_end", message: {
  role: "assistant", stopReason: "stop", errorMessage: "previous diagnostics", content: [{ type: "text", text: "prior complete" }] } }];
const delta = { type: "message_update", assistantMessageEvent: { type: "text_delta", delta: "current draft" } };
const boundary = probe === "message-start" ? [{ type: "message_start", message: { role: "assistant" } }, delta]
  : probe === "text-start" ? [{ type: "message_update", assistantMessageEvent: { type: "text_start" } }, delta]
    : probe === "delta-only" ? [delta]
      : probe === "thinking-start" ? [{ type: "message_update", assistantMessageEvent: { type: "thinking_start" } }]
        : probe === "tool-start" ? [{ type: "message_update", assistantMessageEvent: { type: "toolcall_start" } }]
          : [{ type: "message_start", message: { role: "assistant" } },
            { type: "message_end", message: { role: "assistant", stopReason: "x".repeat(30000), content: [{ type: "text", text: "current draft" }] } }];
emit([...headers, ...boundary, { type: "agent_settled" }]);
assert.equal(notices.length, 1, "One settled native sequence, one follow-up");
const unanswered = notices[0]; assert.equal(unanswered.kind, "unanswered");
assert.ok(unanswered.kind === "unanswered");
assert.equal(unanswered.reason, probe === "unknown-stop" ? "incomplete" : "missing-final");
assert.equal(unanswered.text, probe === "thinking-start" || probe === "tool-start" ? "" : "current draft");
assert.equal(unanswered.stopReason, probe === "unknown-stop" ? "unknown" : undefined);
assert.equal(unanswered.errorMessage, undefined); assert.equal(unanswered.turn, 1);
assert.equal(getAgent(first.details.name as string)?.status, "idle");
emit([{ type: "agent_settled" }]); assert.equal(notices.length, 1);
const sent = await call({ operation: "input", delivery: "next", session: first.details.session, prompt: "Return a complete answer" });
assert.equal(sent.details.ok, true, JSON.stringify(sent));
emit([{ type: "agent_start" }, { type: "message_start", message: { role: "assistant" } },
  { type: "message_end", message: { role: "assistant", stopReason: "stop", content: [{ type: "text", text: "new complete final" }] } },
  { type: "agent_settled" }]);
assert.equal(notices.length, 2); assert.equal(notices[1].kind, "result");
assert.ok(notices[1].kind === "result"); assert.equal(notices[1].text, "new complete final");
assert.equal(notices[1].turn, 2); assert.equal(notices[1].session, first.details.session);
assert.equal((await call({ operation: "stop", session: first.details.session })).details.ok, true);
assert.equal(notices.length, 2); assert.equal(commands.filter(command => command.type === "prompt").length, 2);
console.log(JSON.stringify({ ok: true, probe }));
