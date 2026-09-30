/**
 * A settle arriving in the same stdout read as the next turn.
 *
 * A real child can finish a turn and start the next one inside one read of its
 * control stream. If the spawner reports one frame per read, that read carries
 * only the new turn, the settle is never observable, and the answer is never
 * reported to anyone. Hand-written frames cannot catch this, because the parser
 * is what has to survive it.
 *
 * Driven from `test_session_result.py`. Lives in a file rather than an inline
 * eval because node only exposes module mocking reliably for a real entry.
 */

import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { mock } from "node:test";
import * as kit from "@fradser/pi-kit";

const child = Object.assign(new EventEmitter(), {
  pid: 7,
  stdin: new PassThrough(),
  stdout: new PassThrough(),
  stderr: new PassThrough(),
});

mock.module("@fradser/pi-kit", {
  namedExports: {
    ...kit,
    resolvePiCli: () => ({ command: "unused-mock", args: [] }),
    spawnPiChild: () => child,
    terminateChildProcess: async () => true,
  },
});

const { registerTeammate, resetRoster } = await import("../src/roster.ts");
const { spawnResident } = await import("../src/spawner.ts");

resetRoster();
registerTeammate({
  name: "coalesced", agent: "coalesced", spawnId: "s1", pid: 0,
  status: "starting", isolation: "none", createdAt: 1, updatedAt: 1,
});

const frames: Array<{ finalResponse?: boolean; text: string }> = [];
const started = spawnResident({
  workerName: "coalesced",
  description: "Answer one question.",
  tools: [],
  cwd: process.cwd(),
  onUpdate: (update) => frames.push({ finalResponse: update.finalResponse, text: update.text }),
  onExit: () => {},
  onError: () => {},
});
assert.ok(!("error" in started), "the child starts");

// One read carrying a whole turn: answer, settle, and the next turn's start.
child.stdout.write([
  JSON.stringify({ type: "agent_start" }),
  JSON.stringify({ type: "message_update", assistantMessageEvent: { type: "text_delta", delta: "the answer" } }),
  JSON.stringify({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "the answer" }] } }),
  JSON.stringify({ type: "agent_settled" }),
  JSON.stringify({ type: "agent_start" }),
].join("\n") + "\n");

const settled = frames.filter((frame) => frame.finalResponse === true && frame.text.trim());
assert.equal(settled.length, 1, `the settle must survive a coalesced read: ${JSON.stringify(frames)}`);
assert.equal(settled[0]?.text, "the answer");

child.emit("close", 0, null);
console.log(JSON.stringify({ ok: true, frames: frames.length }));
