import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import type { ChildProcess } from "node:child_process";
import { mock } from "node:test";
import * as kit from "@fradser/pi-kit";
import { MAX_PARENT_MESSAGE_BODY_BYTES, MAX_PARENT_MESSAGE_TOOL_CALL_ID_BYTES, parseParentMessageResult } from "../src/parent-message.ts";

const children: Array<ReturnType<typeof makeChild>> = [];
function makeChild() {
  const child = Object.assign(new EventEmitter(), {
    pid: children.length + 20,
    stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(),
  });
  child.stdin.on("data", chunk => {
    const command = JSON.parse(String(chunk));
    child.stdout.write(JSON.stringify({ type: "response", id: command.id, command: command.type,
      success: true, data: command.type === "get_state" ? { isStreaming: false } : { disposition: "started" },
    }) + "\n");
  });
  return child;
}
mock.module("@fradser/pi-kit", {
  namedExports: {
    ...kit,
    resolvePiCli: () => ({ command: "fake-cli", args: [] }),
    spawnPiChild: () => { const child = makeChild(); children.push(child); return child; },
    terminateChildProcess: async (child: ChildProcess) => { child.emit("close", null, "SIGTERM"); return true; },
  },
});
const spawner = await import("../src/spawner.ts");
const parentMessageExtension = await import("../src/parent-message-extension.ts");

const emit = (child: ReturnType<typeof makeChild>, records: unknown[]) => {
  child.stdout.write(records.map(record => JSON.stringify(record)).join("\n") + "\n");
};
const flush = () => new Promise<void>(resolve => setImmediate(resolve));
const toolResult = (message: string, overrides: Record<string, unknown> = {}, toolCallId = "call-1") => ({
  type: "tool_execution_end", toolName: "agent_message", toolCallId, isError: false,
  result: {
    details: { kind: "intermediate", outcome: "emitted", message },
    structuredContent: { kind: "intermediate", outcome: "emitted", message },
    ...overrides,
  },
});

const probe = process.argv[2];
if (probe === "parse") {
  const legal = " 保留原始空白与中文 ";
  assert.deepEqual(parseParentMessageResult("call-1", toolResult(legal).result), { toolCallId: "call-1", text: legal });
  assert.equal(parseParentMessageResult("call-blank", toolResult(" \n\t").result), undefined);
  assert.equal(parseParentMessageResult("call-unknown", { details: { kind: "other", outcome: "emitted", message: "x" } }), undefined);
  assert.equal(parseParentMessageResult("call-extra", { details: { kind: "intermediate", outcome: "emitted", message: "x", extra: true }, structuredContent: { kind: "intermediate", outcome: "emitted", message: "x", extra: true } }), undefined);
  assert.equal(parseParentMessageResult("call-failed", { isError: true, details: { kind: "intermediate", outcome: "emitted", message: "x" } }), undefined);
  assert.equal(parseParentMessageResult("call-large", toolResult("x".repeat(MAX_PARENT_MESSAGE_BODY_BYTES + 1)).result), undefined);
  const exactAsciiId = "a".repeat(MAX_PARENT_MESSAGE_TOOL_CALL_ID_BYTES);
  const oversizedAsciiId = "a".repeat(MAX_PARENT_MESSAGE_TOOL_CALL_ID_BYTES + 1);
  const exactMultibyteId = "界".repeat(341) + "a"; // 1024 UTF-8 bytes
  const oversizedMultibyteId = "界".repeat(341) + "aa"; // 1025 UTF-8 bytes
  assert.deepEqual(parseParentMessageResult(exactAsciiId, toolResult("ascii").result), { toolCallId: exactAsciiId, text: "ascii" });
  assert.equal(parseParentMessageResult(oversizedAsciiId, toolResult("ascii").result), undefined);
  assert.deepEqual(parseParentMessageResult(exactMultibyteId, toolResult("multibyte").result), { toolCallId: exactMultibyteId, text: "multibyte" });
  assert.equal(parseParentMessageResult(oversizedMultibyteId, toolResult("multibyte").result), undefined);
} else if (probe === "extension") {
  let tool: { parameters: Record<string, unknown>; execute: (id: string, params: unknown, signal?: AbortSignal) => Promise<unknown> } | undefined;
  parentMessageExtension.default({ registerTool: candidate => { tool = candidate as typeof tool; } } as never);
  if (!tool) throw new Error("parent_message extension did not register its tool");
  assert.deepEqual(tool.parameters.required, ["message"]);
  assert.deepEqual(tool.parameters.additionalProperties, false);
  const message = " 原样保留 " + "消息";
  const result = await tool.execute("call-1", { message }) as {
    details: { kind: string; outcome: string; message: string };
    structuredContent: { kind: string; outcome: string; message: string };
  };
  assert.equal(result.details.kind, "intermediate");
  assert.equal(result.details.outcome, "emitted");
  assert.equal(result.details.message, message);
  assert.deepEqual(result.structuredContent, result.details);
  for (const invalid of [undefined, null, [], {}, { message: " " }, { message: "x", extra: true }, { message: "x".repeat(MAX_PARENT_MESSAGE_BODY_BYTES + 1) }]) {
    const refused = await tool.execute("bad", invalid) as { isError?: boolean; details: { outcome: string; code: string } };
    assert.equal(refused.isError, true);
    assert.equal(refused.details.outcome, "refused");
    assert.equal(refused.details.code, "invalid-arguments");
  }
  const controller = new AbortController();
  controller.abort();
  const aborted = await tool.execute("aborted", { message: "ignored" }, controller.signal) as { isError?: boolean; details: { outcome: string; code: string } };
  assert.equal(aborted.isError, true);
  assert.equal(aborted.details.outcome, "refused");
  assert.equal(aborted.details.code, "aborted");
} else if (probe === "route") {
  const payloads: Array<{ toolCallId: string; text: string; sequence: number }> = [];
  const updates: Array<{ finalResponse?: boolean }> = [];
  const started = spawner.spawnResident({ agentName: "messages", description: "Run", tools: [],
    onUpdate: update => updates.push(update),
    onParentMessage: (payload, sequence) => payloads.push({ ...payload, sequence }), onExit: () => {} });
  assert.ok(!("error" in started));
  emit(children[0], [toolResult("合法消息"), toolResult("第二条", {}, "call-2"), toolResult("复用ID")]);
  emit(children[0], [toolResult(" "), toolResult("x", { isError: true }), toolResult("x".repeat(MAX_PARENT_MESSAGE_BODY_BYTES + 1))]);
  await flush();
  assert.deepEqual(payloads, [
    { toolCallId: "call-1", text: "合法消息", sequence: 1 },
    { toolCallId: "call-2", text: "第二条", sequence: 2 },
    { toolCallId: "call-1", text: "复用ID", sequence: 3 },
  ]);
  assert.equal(updates.some(update => update.finalResponse === true), false);
  children[0].emit("close", 0, null);
} else if (probe === "ownership") {
  const oldPayloads: string[] = [];
  const replacementPayloads: string[] = [];
  const old = spawner.spawnResident({ agentName: "same", description: "old", tools: [],
    onParentMessage: payload => oldPayloads.push(payload.text), onExit: () => {} });
  assert.ok(!("error" in old));
  const replacement = spawner.spawnResident({ agentName: "same", description: "new", tools: [],
    onParentMessage: payload => replacementPayloads.push(payload.text), onExit: () => {} });
  assert.ok(!("error" in replacement));
  emit(children[0], [toolResult("late-old")]);
  emit(children[1], [toolResult("new")]);
  await flush();
  assert.deepEqual(oldPayloads, []);
  assert.deepEqual(replacementPayloads, ["new"]);
  children[0].emit("close", 0, null);
  children[1].emit("close", 0, null);
}
console.log(JSON.stringify({ ok: true, probe }));
