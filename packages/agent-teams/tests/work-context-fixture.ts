import assert from "node:assert/strict";
import childProcess, { type SpawnOptions } from "node:child_process";
import { syncBuiltinESMExports } from "node:module";
import { EventEmitter } from "node:events";
import fs from "node:fs";
import path from "node:path";
import { PassThrough } from "node:stream";
import { mock } from "node:test";
import { SessionManager, type SessionContext } from "@earendil-works/pi-coding-agent";

type Message = SessionContext["messages"][number];
type Assistant = Extract<Message, { role: "assistant" }>;
type ToolResult = Extract<Message, { role: "toolResult" }>;
const root = process.env.WORK_CONTEXT_FIXTURE_DIR!;
const mode = process.argv[2];
fs.mkdirSync(root, { recursive: true });
const temporary = path.join(root, "temporary");
fs.mkdirSync(temporary);
process.env.TMPDIR = temporary;
const image = { type: "image" as const, data: "aW1hZ2U=", mimeType: "image/png" };
const usage = { input: 1, output: 2, cacheRead: 0, cacheWrite: 0, totalTokens: 3, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } };

function user(text: string): Extract<Message, { role: "user" }> {
  return { role: "user", content: [{ type: "text", text }, { ...image }], timestamp: 1000 };
}

function assistant(text: string, calls: string[] = []): Assistant {
  return {
    role: "assistant", content: [
      ...(text ? [{ type: "text" as const, text }] : []),
      ...calls.map((id) => ({ type: "toolCall" as const, id, name: "read", arguments: { path: `${id}.ts`, nested: { value: 1 } } })),
    ], api: "openai-responses", provider: "openai", model: "parent-model", usage: structuredClone(usage),
    stopReason: calls.length ? "toolUse" : "stop", timestamp: 2000,
  };
}

function result(id: string): ToolResult {
  return {
    role: "toolResult", toolCallId: id, toolName: "read", content: [{ type: "text", text: `result ${id}` }, { ...image }],
    isError: false, timestamp: 3000, usage: structuredClone(usage),
  };
}

function parentSession(): SessionManager {
  const parent = SessionManager.create(root, path.join(root, "parent"));
  const origin = parent.appendMessage(user("summarized original"));
  parent.appendMessage(assistant("discarded sibling"));
  parent.branchWithSummary(origin, "Existing branch summary", { runtimeIdentity: "parent-branch" });
  const kept = parent.getLeafId()!;
  parent.appendMessage(user("active request"));
  parent.appendMessage(assistant("completed exchange", ["completed"]));
  parent.appendMessage(result("completed"));
  parent.appendCustomEntry("agent-teams-runtime", { worker: "leader", tools: ["teammate_spawn"] });
  parent.appendCustomMessageEntry("review-evidence", "Existing extension conversation", true, { runtimeIdentity: "parent-custom" });
  parent.appendCompaction("Existing compaction summary", kept, 5000, { runtimeIdentity: "parent-compaction" });
  parent.appendMessage(assistant("active answer"));
  parent.appendModelChange("parent-provider", "parent-model-selection");
  parent.appendThinkingLevelChange("high");
  return parent;
}

function parentState(parent: SessionManager): unknown {
  const file = parent.getSessionFile();
  return {
    id: parent.getSessionId(), leaf: parent.getLeafId(), entries: structuredClone(parent.getEntries()),
    file: file && fs.existsSync(file) ? fs.readFileSync(file, "utf8") : undefined,
  };
}

function expectedContext(parent: SessionManager): Message[] {
  return structuredClone(parent.buildSessionContext().messages).map((message) => {
    if (message.role === "custom" || message.role === "toolResult") delete message.details;
    if (message.role === "toolResult") delete message.addedToolNames;
    return message;
  });
}

type Snapshot = typeof import("../src/work-context.ts").snapshotWorkContext;

function assertEmptySnapshot(snapshotWorkContext: Snapshot): void {
  const parent = SessionManager.inMemory(root);
  assert.deepEqual(snapshotWorkContext(parent), []);
  parent.appendMessage(user("inactive root"));
  parent.resetLeaf();
  assert.deepEqual(snapshotWorkContext(parent), []);
  assert.throws(() => snapshotWorkContext(undefined), /fork.*context.*unavailable/i);
}

function assertInterleavedSnapshot(snapshotWorkContext: Snapshot): void {
  const parent = SessionManager.inMemory(root);
  parent.appendMessage(user("request"));
  parent.appendMessage(assistant("complete call", ["shared-id"]));
  parent.appendCustomMessageEntry("historical-guidance", "Historical leader control, not child authority", true);
  parent.appendMessage(result("shared-id"));
  parent.appendMessage(assistant(""));
  const expected = expectedContext(parent);
  parent.appendMessage(assistant("", ["shared-id"]));
  assert.deepEqual(snapshotWorkContext(parent), expected);
}

async function snapshotScenario(): Promise<void> {
  const { snapshotWorkContext } = await import("../src/work-context.ts");
  if (mode === "snapshot-empty") return assertEmptySnapshot(snapshotWorkContext);
  if (mode === "snapshot-interleaved") return assertInterleavedSnapshot(snapshotWorkContext);
  if (mode === "snapshot-selected-leaf") {
    const parent = parentSession();
    const selected = parent.getBranch().find((entry) => entry.type === "message" && entry.message.role === "user")!;
    parent.branch(selected.id);
    const before = parentState(parent);
    assert.deepEqual(snapshotWorkContext(parent), expectedContext(parent));
    assert.deepEqual(parentState(parent), before);
    return;
  }
  const parent = mode === "snapshot-active" ? parentSession() : SessionManager.inMemory(root);
  if (mode === "snapshot-in-memory") parent.appendMessage(user("in-memory request"));
  const beforeExchange = expectedContext(parent);
  const partial = assistant("Keep completed sibling evidence", ["done", "pending-spawn"]);
  partial.content.unshift({ type: "thinking", thinking: "Existing reasoning", thinkingSignature: "existing-signature" });
  parent.appendMessage(partial);
  const completed = result("done");
  completed.details = { runtimeIdentity: "parent-tool-state" };
  completed.addedToolNames = ["teammate_spawn"];
  parent.appendMessage(completed);
  parent.appendMessage(user("new request"));
  parent.appendMessage(result("orphan"));
  parent.appendMessage(assistant("", ["unfinished-only"]));
  const before = parentState(parent);
  const snapshot = snapshotWorkContext(parent);
  assert.deepEqual(parentState(parent), before);
  const sanitized = { ...partial, content: partial.content.filter((block) => block.type !== "toolCall" || block.id === "done") };
  assert.deepEqual(snapshot, [...beforeExchange, sanitized, result("done"), user("new request")]);
  assert.equal(JSON.stringify(snapshot).includes("runtimeIdentity"), false);
  assert.equal(JSON.stringify(snapshot).includes("pending-spawn"), false);
  assert.equal(JSON.stringify(snapshot).includes("discarded sibling"), false);
  assertDetachedSnapshot(parent, snapshot);
}

function assertDetachedSnapshot(parent: SessionManager, snapshot: Message[]): void {
  const frozenSnapshot = structuredClone(snapshot);
  parent.appendMessage(user("parent continues"));
  assert.deepEqual(snapshot, frozenSnapshot);
  const parentAfterAppend = parentState(parent);
  const snapshotUser = snapshot.find((message) => message.role === "user")!;
  assert.ok(Array.isArray(snapshotUser.content));
  const snapshotImage = snapshotUser.content.find((block) => block.type === "image")!;
  snapshotImage.data = "child-only-image";
  const snapshotAssistant = snapshot.find((message): message is Assistant => message.role === "assistant" && message.content.some((block) => block.type === "toolCall"))!;
  const call = snapshotAssistant.content.find((block) => block.type === "toolCall")!;
  call.arguments.path = "child-only-path";
  assert.deepEqual(parentState(parent), parentAfterAppend);
}

function mockChild(pid: number | undefined) {
  return Object.assign(new EventEmitter(), { pid, stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough() });
}

type CapturedSpawn = { args: string[]; options: SpawnOptions; file?: string; messages?: Message[]; header?: unknown; child: ReturnType<typeof mockChild> };
const captures: CapturedSpawn[] = [];
mock.method(childProcess, "spawn", (_command: string, args: string[], options: SpawnOptions) => {
  const sessionIndex = args.indexOf("--session");
  const file = sessionIndex < 0 ? undefined : args[sessionIndex + 1];
  const child = mockChild(mode === "spawn-error" ? undefined : 100 + captures.length);
  const manager = file ? SessionManager.open(file) : undefined;
  captures.push({ args: [...args], options, file, messages: manager?.buildSessionContext().messages, header: manager?.getHeader(), child });
  if (mode === "spawn-throw") throw new Error("fixture spawn failure");
  return child;
});
syncBuiltinESMExports();

type SpawnFixture = Awaited<ReturnType<typeof spawnFixture>>;

async function spawnFixture() {
  const { spawnResident, isWorkerCloseObserved } = await import("../src/spawner.ts");
  const parent = parentSession();
  const before = parentState(parent);
  const context = mode === "spawn-empty" ? [] : mode === "spawn-user-only" ? [user("only user")] : expectedContext(parent);
  const errors: string[] = [];
  let exits = 0;
  if (mode === "spawn-seed-failure") mock.method(SessionManager, "create", () => { throw new Error("fixture context setup failure"); });
  const spawned = spawnResident({
    workerName: captures.length ? "sibling" : "child", cwd: root, description: "Only child assignment", tools: ["read"],
    model: "child-provider/child-model", thinking: "low", context: mode === "spawn-fresh" ? undefined : context,
    env: { PI_TEAMMATE_WORKER_NAME: "child", PI_TEAMMATE_SPAWN_ID: "child-spawn" },
    onError: (error) => errors.push(error.message), onExit: () => { exits++; },
  });
  return { parent, before, context, spawned, errors, get exits() { return exits; }, isWorkerCloseObserved };
}

function assertSpawnSelection(capture: CapturedSpawn, fixture: SpawnFixture): void {
  const { parent, before, context } = fixture;
  assert.equal(capture.args.includes("--no-extensions"), true);
  assert.equal(capture.args[capture.args.indexOf("--tools") + 1], "read,agent_event,send_message,task_list,task_claim,task_submit");
  assert.equal(capture.args[capture.args.indexOf("--model") + 1], "child-provider/child-model");
  assert.equal(capture.args[capture.args.indexOf("--thinking") + 1], "low");
  assert.equal(capture.options.env?.PI_TEAMMATE_WORKER_NAME, "child");
  assert.deepEqual(parentState(parent), before);
  if (mode === "spawn-fresh") {
    assert.equal(capture.file, undefined);
    assert.equal(capture.args.includes("--no-session"), true);
    assert.deepEqual(fs.readdirSync(temporary), []);
  } else {
    assert.ok(capture.file, "fork must select a prepared --session before spawn");
    assert.equal(capture.args.includes("--no-session"), false);
    assert.deepEqual(capture.messages, context);
    assert.notEqual(capture.file, parent.getSessionFile());
    assert.notDeepEqual(capture.header, parent.getHeader());
  }
}

function assertIndependentSession(capture: CapturedSpawn, fixture: SpawnFixture): void {
  const { parent, before, context } = fixture;
  const manager = SessionManager.open(capture.file!);
  assert.equal(manager.getCwd(), root);
  assert.notEqual(manager.getSessionId(), parent.getSessionId());
  assert.equal(manager.getHeader()?.parentSession, undefined);
  assert.ok(manager.getEntries().every((entry) => entry.type === "message"));
  assert.equal(fs.statSync(capture.file!).mode & 0o777, 0o600);
  assert.equal(fs.statSync(path.dirname(capture.file!)).mode & 0o777, 0o700);
  manager.appendMessage(user("child continues"));
  assert.deepEqual(parentState(parent), before);
  parent.appendMessage(user("parent continues"));
  assert.deepEqual(manager.buildSessionContext().messages, [...context, user("child continues")]);
  capture.child.emit("exit", 0, null);
  assert.equal(fs.existsSync(capture.file!), true, "exit is not an observed close");
}

async function spawnScenario(): Promise<void> {
  const fixture = await spawnFixture();
  const { spawned, errors, parent, before, isWorkerCloseObserved } = fixture;
  if (mode === "spawn-seed-failure") {
    assert.deepEqual(spawned, { error: "fixture context setup failure" });
    assert.equal(captures.length, 0);
    assert.deepEqual(fs.readdirSync(temporary), []);
    assert.deepEqual(parentState(parent), before);
    return;
  }
  const capture = captures[0];
  assert.ok(capture);
  assertSpawnSelection(capture, fixture);
  if (mode === "spawn-parallel") {
    await spawnFixture();
    const sibling = captures[1];
    assert.notEqual(sibling.file, capture.file);
    assert.notEqual(path.dirname(sibling.file!), path.dirname(capture.file!));
    capture.child.emit("close", 0, null);
    assert.equal(fs.existsSync(capture.file!), false);
    assert.equal(fs.existsSync(sibling.file!), true);
    sibling.child.emit("close", 0, null);
    assert.deepEqual(fs.readdirSync(temporary), []);
    return;
  }
  if (mode === "spawn-throw") {
    assert.deepEqual(spawned, { error: "fixture spawn failure" });
    assert.equal(fs.existsSync(capture.file!), false);
    assert.deepEqual(fs.readdirSync(temporary), []);
    return;
  }
  assert.equal("error" in spawned, false);
  const prompt = JSON.parse(capture.child.stdin.read().toString());
  assert.equal(prompt.message, "Only child assignment");
  assert.equal(prompt.type, "prompt");
  if (mode === "spawn-error" || mode === "spawn-runtime-error") {
    capture.child.emit("error", new Error("fixture asynchronous error"));
    assert.deepEqual(errors, ["fixture asynchronous error"]);
    assert.equal(fs.existsSync(capture.file!), mode === "spawn-runtime-error");
    assert.equal(isWorkerCloseObserved("child"), false);
  } else if (capture.file) {
    assertIndependentSession(capture, fixture);
  }
  capture.child.emit("close", 0, null);
  assert.equal(isWorkerCloseObserved("child"), true);
  assert.equal(fixture.exits, errors.length ? 0 : 1);
  assert.deepEqual(fs.readdirSync(temporary), []);
  assert.equal(fs.existsSync(parent.getSessionFile()!), true);
}

try {
  if (mode.startsWith("snapshot-")) await snapshotScenario();
  else await spawnScenario();
  console.log(JSON.stringify({ ok: true, scenario: mode }));
} finally {
  for (const capture of captures) capture.child.emit("close", 0, null);
  mock.restoreAll();
  syncBuiltinESMExports();
  fs.rmSync(root, { recursive: true, force: true });
}
