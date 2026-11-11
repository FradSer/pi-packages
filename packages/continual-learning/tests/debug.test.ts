import { afterEach, beforeEach, expect, test } from "bun:test";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, symlinkSync, unlinkSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import vm from "node:vm";
import { createLearningDebug, debugDirectory, sanitizeDebugValue } from "../extensions/debug.ts";
import { readDebugConfigState, writeUnifiedConfig } from "../extensions/config.ts";
import { buildLearningReceipt, writeLearningReceipt } from "../extensions/learning-efficiency.ts";

type Callback = (...args: unknown[]) => unknown;
class Host {
  events = new Map<string, Callback>();
  commands = new Map<string, { handler: Callback }>();
  tools = new Map<string, { name: string; execute: Callback }>();
  messages: unknown[] = [];
  active: string[] = [];
  on(name: string, callback: Callback) { this.events.set(name, callback); return () => this.events.delete(name); }
  registerCommand(name: string, options: { handler: Callback }) { this.commands.set(name, options); }
  registerTool(tool: { name: string; execute: Callback }) { this.tools.set(tool.name, tool); }
  sendMessage(value: unknown) { this.messages.push(value); }
  appendEntry(name: string, data: unknown) { this.messages.push({ name, data }); }
  setActiveTools(tools: string[]) { this.active = tools; }
}

let root: string, cwd: string, agent: string;
const priorAgent = process.env.PI_CODING_AGENT_DIR;
beforeEach(() => {
  root = realpathSync(mkdtempSync(path.join(os.tmpdir(), "cl-debug-")));
  cwd = path.join(root, "project"); agent = path.join(root, "agent");
  mkdirSync(cwd); mkdirSync(agent, { mode: 0o700 });
  process.env.PI_CODING_AGENT_DIR = agent;
});
afterEach(() => {
  if (priorAgent === undefined) delete process.env.PI_CODING_AGENT_DIR;
  else process.env.PI_CODING_AGENT_DIR = priorAgent;
  rmSync(root, { recursive: true, force: true });
});
function context(id = "one", project = cwd) {
  const notices: unknown[] = [];
  return { cwd: project, mode: "json", hasUI: false,
    model: { provider: "fixture", id: "offline" },
    sessionManager: { getSessionId: () => id, getSessionFile: () => path.join(root, id + ".jsonl"),
      getLeafId: () => "leaf", getBranch: () => [{ type: "message", id: "user", message: { role: "user", content: "Inspect the queue contract." } }] },
    ui: { notify: (...args: unknown[]) => { notices.push(args); } }, notices };
}
function records(project = cwd) {
  const directory = debugDirectory(project, agent);
  if (!existsSync(directory)) return [];
  const rows = readdirSync(directory).filter(name => name.endsWith(".jsonl")).sort()
    .flatMap(name => readFileSync(path.join(directory, name), "utf8").trim().split("\n").filter(Boolean).map(line => JSON.parse(line)))
    .filter(row => row.event !== "context:snapshot");
  const snapshots = new Map(readdirSync(directory).filter(name => name.endsWith(".jsonl")).sort()
    .flatMap(name => readFileSync(path.join(directory, name), "utf8").trim().split("\n").filter(Boolean).map(line => JSON.parse(line)))
    .filter(row => row.event === "context:snapshot")
    .map(row => [row.contextDigest, row.data?.context]));
  return rows.map(row => {
    if (row.event === "context:snapshot" || !row.contextRef || !snapshots.has(row.contextRef)) return row;
    return { ...row, context: { ...row.context, ...snapshots.get(row.contextRef) } };
  });
}

test("debug defaults on independently of learning settings and explicit false writes nothing", () => {
  expect(readDebugConfigState()).toEqual({ enabled: true });
  const host = new Host(), debug = createLearningDebug(), pi = debug.wrap(host, "extensions/example.ts");
  const ctx = context();
  pi.on("input", () => ({ action: "continue" }));
  expect(host.events.get("input")?.({ text: "inspect queue" }, ctx)).toEqual({ action: "continue" });
  const rows = records();
  expect(rows.map(row => row.phase)).toEqual(["started", "completed"]);
  expect(rows[0].source).toBe("extensions/example.ts");
  expect(rows[0].context.cwd).toBe(cwd);
  expect(rows[0].context.sessionId).toBe("one");
  expect(rows[0].context.entries[0].message.content).toBe("Inspect the queue contract.");
  expect(rows[1].invocationId).toBe(rows[0].invocationId);
  writeUnifiedConfig({ autoSettledLearning: false, autoContinualLearning: false, debug: false });
  host.events.get("input")?.({ text: "inspect again" }, ctx);
  expect(records()).toHaveLength(2);
  expect(readDebugConfigState()).toEqual({ enabled: false });
  const other = path.join(root, "other"); mkdirSync(other);
  host.events.get("input")?.({}, context("disabled", other));
  expect(existsSync(debugDirectory(other, agent))).toBe(false);
});

test("callbacks keep sync results, rejection identity, blocked results and cancellation", async () => {
  const host = new Host(), pi = createLearningDebug().wrap(host, "extensions/example.ts"), ctx = context();
  const failure = new Error("fixture worker failed");
  const invocations: Callback[] = [];
  const originalOn = host.on.bind(host);
  host.on = (name: string, handler: Callback) => { invocations.push(handler); return originalOn(name, handler); };
  pi.on("sync", () => { throw failure; });
  expect(() => invocations[0]({}, ctx)).toThrow(failure);
  pi.on("async", async () => { throw failure; });
  let observed: unknown;
  try { await invocations[1]({}, ctx); } catch (error) { observed = error; }
  expect(observed).toBe(failure);
  pi.on("tool_call", () => ({ block: true, reason: "fixture policy" }));
  expect(invocations[2]({ toolName: "bash", input: { command: "fixture" } }, ctx)).toEqual({ block: true, reason: "fixture policy" });
  pi.registerTool({ name: "learn", execute: async () => ({ details: { status: "cancelled" }, content: [] }) });
  await host.tools.get("learn")?.execute("call", {}, undefined, undefined, ctx);
  const ends = records().filter(row => row.phase !== "started");
  expect(ends.map(row => row.outcome)).toEqual(["failed", "failed", "blocked", "cancelled"]);
  expect(ends[0].data.error.message).toBe("fixture worker failed");
  expect(ends[0].data.error.stack).toContain("debug.test.ts");
});

test("overlapping sessions retain nested message, notification and receipt ownership", async () => {
  const host = new Host(), debug = createLearningDebug(), pi = debug.wrap(host, "extensions/inject-memory.ts");
  let release: (() => void) | undefined;
  const gate = new Promise<void>(resolve => { release = resolve; });
  pi.registerCommand("learning", { handler: async (...args) => {
    const ctx = args[1];
    if (!ctx || typeof ctx !== "object" || !("ui" in ctx)) throw Error("Missing context");
    const ui = ctx.ui;
    if (!ui || typeof ui !== "object" || !("notify" in ui) || typeof ui.notify !== "function") throw Error("Missing UI");
    if (args[0] === "first") await gate;
    ui.notify("review held", "error");
    pi.setActiveTools(["learn"]);
    pi.sendMessage({ customType: "continual-learning-result", details: { batchId: args[0], operations: 0,
      attempts: [{ phase: "memory", outcome: "proposed", diagnostic: "fixture hold", usageLedgerId: "ledger" }] } });
    return args[0];
  } });
  const a = host.commands.get("learning")?.handler("first", context("a"));
  const b = host.commands.get("learning")?.handler("second", context("b"));
  await b; release?.(); await a;
  const rows = records(), starts = rows.filter(row => row.phase === "started" && row.event === "command:learning");
  expect(starts).toHaveLength(2);
  for (const start of starts) {
    const nested = rows.filter(row => row.parentInvocationId === start.invocationId);
    expect(nested.some(row => row.event === "ui:notify" && row.outcome === "failed")).toBe(true);
    const receipt = nested.find(row => row.event === "sendMessage");
    expect(receipt?.context.sessionId).toBe(start.context.sessionId);
    expect(receipt?.data[0].details.batchId).toBe(start.data[0]);
    expect(receipt?.data[0].details.attempts[0].outcome).toBe("proposed");
  }
  expect(host.active).toEqual(["learn"]);
  expect(host.messages).toHaveLength(2);
});

test("all module wrappers share the API identity required by the Harness bridge", () => {
  const host = new Host(), debug = createLearningDebug();
  const first = debug.wrap(host, "extensions/inject-memory.ts");
  const second = debug.wrap(first, "extensions/guardrails.ts");
  expect(second).toBe(first);
  expect(debug.wrap(host, "extensions/output-checks.ts")).toBe(first);
  expect(Object.hasOwn(first, "missingMethod")).toBe(false);
});

test("silent receipts and storage failures retain batch, worker telemetry and artifact locations", async () => {
  const host = new Host(), pi = createLearningDebug().wrap(host, "extensions/inject-memory.ts"), ctx = context();
  const batchId = "batch_" + "1".repeat(32), directory = path.join(agent, "memory", "runs", "fixture");
  const receipt = buildLearningReceipt("automatic", { memory: true, harness: false, agents: false, reasons: [] }, [
    { phase: "memory", attempt: 0, durationMs: 1, operations: 0, outcome: "failed", diagnostic: "fixture worker failed", usageComplete: false,
      usageLedgerId: "fixture-ledger", jev: { stage: "memory", status: "propose", reason: "unavailable", durationMs: 1 } },
  ], undefined, batchId);
  pi.on("agent_settled", async () => { await writeLearningReceipt(directory, receipt); });
  await host.events.get("agent_settled")?.({}, ctx);
  expect(host.messages).toEqual([]);
  const saved = records().find(row => row.event === "receipt:written");
  expect(saved?.data.receipt.batchId).toBe(batchId);
  expect(saved?.data.receipt.attempts[0].usageComplete).toBe(false);
  expect(saved?.data.receipt.attempts[0].jev.reason).toBe("unavailable");
  expect(saved?.data.file).toBe(path.join(directory, "learning-pipeline-receipt.json"));
  const outside = path.join(root, "outside-receipt"); mkdirSync(outside);
  rmSync(directory, { recursive: true }); symlinkSync(outside, directory);
  try { await host.events.get("agent_settled")?.({}, ctx); } catch { /* 验证原回执写入仍拒绝不安全路径。 */ }
  expect(records().some(row => row.event === "receipt:failed")).toBe(true);
  expect(readdirSync(outside)).toEqual([]);
});

test("debug serializes safe context and redacts complete secrets before clipping", () => {
  const secret = "sk-" + "sanitizedfixturecredential123456789";
  const large = "safe prefix ".repeat(2000) + "\napi_key: " + secret;
  const input: Record<string, unknown> = { note: "The queue is idle.", apiKey: "short", headers: { Authorization: secret },
    environment: { CUSTOM_KEY: secret }, content: large,
    image: { type: "image", data: "PRIVATE_IMAGE_BYTES", mimeType: "image/png" },
    error: new Error("api_key: " + secret), nested: JSON.stringify({ password: "other-private-value" }) };
  input.cycle = input;
  const safe = sanitizeDebugValue(input), text = JSON.stringify(safe);
  expect(text).toContain("The queue is idle.");
  for (const value of [secret, "short", "PRIVATE_IMAGE_BYTES", "other-private-value"]) expect(text).not.toContain(value);
  expect(text).toContain(createHash("sha256").update(large).digest("hex"));
  expect(text).toContain("redacted");
  expect(text).toContain("cycle");
  expect(text.length).toBeLessThan(65536);
});

test("异步结束记录保留调用开始时的上下文", async () => {
  const host = new Host(), pi = createLearningDebug().wrap(host, "extensions/example.ts"), ctx = context();
  const branch = ctx.sessionManager.getBranch(); ctx.sessionManager.getBranch = () => branch;
  let release: (() => void) | undefined;
  const gate = new Promise<void>(resolve => { release = resolve; });
  pi.on("pending", async () => { await gate; return "completed"; });
  const pending = host.events.get("pending")?.({}, ctx);
  branch[0].message.content = "Changed after invocation";
  release?.(); await pending;
  expect(records().map(row => row.context.entries[0].message.content)).toEqual(["Inspect the queue contract.", "Inspect the queue contract."]);
});

test("context omissions are explicit and debug never reads the model registry or effective system prompt", () => {
  const host = new Host(), pi = createLearningDebug().wrap(host, "extensions/example.ts");
  const ctx = { ...context(), getSystemPrompt: () => { throw Error("Must not read prompt"); },
    modelRegistry: { getApiKey: () => { throw Error("Must not read auth"); } } };
  ctx.sessionManager.getBranch = () => Array.from({ length: 40 }, (_, i) => ({ type: "message", id: String(i), message: { role: "user", content: "fixture " + i } }));
  pi.on("context", event => event);
  host.events.get("context")?.({ messages: [{ content: "safe context" }] }, ctx);
  expect(records()[0].context.omittedEntries).toBeGreaterThan(0);
  expect(records()[0].context.entryCount).toBe(40);
  expect(records()[0].context.entries.at(-1).message.content).toBe("fixture 39");
  expect(existsSync(path.join(cwd, ".memory"))).toBe(false);
});

test("learning debug uses the existing command, preserves settings and reports exact storage", async () => {
  writeUnifiedConfig({ model: "fixture/offline", debug: false, autoSettledLearning: false, jev: false });
  const host = new Host(), debug = createLearningDebug(), pi = debug.wrap(host, "extensions/inject-memory.ts"), ctx = context();
  let ordinary = 0;
  pi.registerCommand("learning", { handler: () => { ordinary++; } });
  await host.commands.get("learning")?.handler("debug on", ctx);
  expect(readDebugConfigState()).toEqual({ enabled: true });
  await host.commands.get("learning")?.handler("debug", ctx);
  expect(JSON.stringify(ctx.notices)).toContain(debugDirectory(cwd, agent));
  await host.commands.get("learning")?.handler("remember the queue", ctx);
  await host.commands.get("learning")?.handler("debug off", ctx);
  expect(JSON.parse(readFileSync(path.join(agent, "continual-learning.json"), "utf8"))).toEqual({ model: "fixture/offline", debug: false, autoSettledLearning: false, jev: false });
  expect(ordinary).toBe(1);
  expect([...host.commands.keys()]).toEqual(["learning"]);
  expect(records().some(row => row.event === "debug:configuration")).toBe(true);
});

test("malformed debug configuration is diagnosed without disabling observation or clobbering config", async () => {
  writeUnifiedConfig({ debug: "wrong" });
  expect(readDebugConfigState().enabled).toBe(true);
  expect(readDebugConfigState().invalid).toBeDefined();
  writeFileSync(path.join(agent, "continual-learning.json"), "{");
  const host = new Host(), pi = createLearningDebug().wrap(host, "extensions/example.ts"), ctx = context();
  pi.registerCommand("learning", { handler: () => undefined });
  await host.commands.get("learning")?.handler("debug off", ctx);
  expect(readFileSync(path.join(agent, "continual-learning.json"), "utf8")).toBe("{");
  expect(JSON.stringify(ctx.notices)).toContain("error");
});

test("private log writes refuse symlink roots, replaced files and FIFOs without changing callback results", () => {
  const host = new Host(), debug = createLearningDebug(), pi = debug.wrap(host, "extensions/example.ts"), ctx = context();
  void debug;
  const outside = path.join(root, "outside"); mkdirSync(outside);
  const privateRoot = path.join(agent, "continual-learning"); symlinkSync(outside, privateRoot);
  pi.on("input", () => "unchanged");
  expect(host.events.get("input")?.({}, ctx)).toBe("unchanged");
  expect(readdirSync(outside)).toEqual([]);
  expect(ctx.notices).toHaveLength(1);
  unlinkSync(privateRoot);
  host.events.get("input")?.({}, ctx);
  const directory = debugDirectory(cwd, agent), file = path.join(directory, readdirSync(directory)[0]);
  expect(lstatSync(directory).mode & 0o777).toBe(0o700);
  expect(lstatSync(file).mode & 0o777).toBe(0o600);
  const sentinel = path.join(outside, "sentinel"); writeFileSync(sentinel, "preserve");
  unlinkSync(file); symlinkSync(sentinel, file);
  expect(host.events.get("input")?.({}, ctx)).toBe("unchanged");
  expect(readFileSync(sentinel, "utf8")).toBe("preserve");
  unlinkSync(file); execFileSync("mkfifo", [file]);
  const before = Date.now();
  expect(host.events.get("input")?.({}, ctx)).toBe("unchanged");
  expect(Date.now() - before).toBeLessThan(1000);
});

test("大型上下文不会挤掉回执的 batch 身份和结果", () => {
  const host = new Host(), pi = createLearningDebug().wrap(host, "extensions/example.ts"), ctx = context();
  const branch = Array.from({ length: 12 }, (_, i) => ({ type: "message", id: String(i), message: { role: "user", content: Array.from({ length: 48 }, () => ({ type: "text", text: "Large fixture context." })) } }));
  const large = { ...ctx, sessionManager: { ...ctx.sessionManager, getBranch: () => branch } };
  pi.on("result", () => { pi.sendMessage({ customType: "continual-learning-result", details: { batchId: "fixture-batch", operations: 1 } }); return true; });
  host.events.get("result")?.({}, large);
  const message = records().find(row => row.event === "sendMessage");
  expect(message?.data[0].details.batchId).toBe("fixture-batch");
  expect(message?.data[0].details.operations).toBe(1);
  expect(message?.context.sessionId).toBe("one");
});

test("凭证集合不能借复数 tokens 字段绕过脱敏", () => {
  const input = { access_tokens: ["access-private-value"], refresh_tokens: "refresh-private-value", auth: "short-private-value",
    inputTokens: 2, totalTokens: 5, tokenCount: 5, outputTokens: "credential-in-count-field" };
  const safe = sanitizeDebugValue(input), text = JSON.stringify(safe);
  for (const value of ["access-private-value", "refresh-private-value", "short-private-value", "credential-in-count-field"]) expect(text).not.toContain(value);
  expect(safe).toMatchObject({ inputTokens: 2, totalTokens: 5, tokenCount: 5 });
});

test("debug off 边界显式绑定在途调用且关闭后不再补写批量与结束记录", async () => {
  const host = new Host(), pi = createLearningDebug().wrap(host, "extensions/example.ts"), ctx = context();
  let release: (() => void) | undefined;
  const gate = new Promise<void>(resolve => { release = resolve; });
  pi.on("waiting", async () => { await gate; pi.appendEntry("later", { text: "late private context" }); return "late result"; });
  pi.on("session_start", () => undefined);
  pi.registerCommand("learning", { handler: () => undefined });
  const waiting = host.events.get("waiting")?.({}, ctx);
  host.events.get("session_start")?.({ type: "session_start", reason: "startup" }, ctx);
  await host.commands.get("learning")?.handler("debug off", ctx);
  await Bun.sleep(1);
  const boundary = records();
  const config = boundary.find(row => row.event === "debug:configuration");
  const started = boundary.find(row => row.event === "event:waiting" && row.phase === "started");
  expect(config?.data.enabled).toBe(false);
  expect(started).toBeDefined();
  expect(config?.data.truncatedInvocations).toContain(started?.invocationId);
  expect(boundary.some(row => row.event === "lifecycle:batch")).toBe(false);
  release?.(); expect(await waiting).toBe("late result");
  expect(records()).toEqual(boundary);
});

test("启用或关闭 debug 均不读取返回值的 accessor", () => {
  for (const enabled of [true, false]) {
    writeUnifiedConfig({ debug: enabled });
    const host = new Host(), pi = createLearningDebug().wrap(host, "extensions/example.ts"), ctx = context();
    let reads = 0;
    const result = Object.defineProperty({}, "block", { enumerable: true, get() { reads++; throw Error("getter must remain untouched"); } });
    pi.on("accessor", () => result);
    expect(host.events.get("accessor")?.({}, ctx)).toBe(result);
    expect(reads).toBe(0);
  }
});

test("跨运行域 Promise 和 thenable 拒绝保留真实异步失败", async () => {
  const host = new Host(), pi = createLearningDebug().wrap(host, "extensions/example.ts"), ctx = context();
  const foreign = vm.runInNewContext('Promise.reject(new Error("foreign fixture failure"))');
  const failure = Error("thenable fixture failure");
  const thenable = { then(_resolve: unknown, reject: (error: unknown) => void) { reject(failure); } };
  for (const [name, value] of [["foreign", foreign], ["thenable", thenable]] as const) {
    pi.on(name, () => value);
    let error: unknown;
    try { await host.events.get(name)?.({}, ctx); } catch (caught) { error = caught; }
    expect(error).toBeDefined();
    if (name === "thenable") expect(error).toBe(failure);
  }
  expect(records().filter(row => row.phase !== "started").map(row => row.outcome)).toEqual(["failed", "failed"]);
});

test("敏感 cwd 仅脱敏显示，不改变实际日志项目归属", () => {
  const sensitive = path.join(root, "sk-" + "synthetic-project-credential-123456"); mkdirSync(sensitive);
  const host = new Host(), pi = createLearningDebug().wrap(host, "extensions/example.ts");
  pi.on("input", () => "observed");
  host.events.get("input")?.({}, context("sensitive-path", sensitive));
  const rows = records(sensitive);
  expect(rows.filter(row => row.event === "event:input")).toHaveLength(2);
  expect(rows[0].context.cwd.omitted).toBe("redacted");
  expect(rows[0].context.projectId).toBe(createHash("sha256").update(sensitive).digest("hex"));
  expect(JSON.stringify(rows)).not.toContain(sensitive);
});

test("重复工具定义只保留一次上下文快照，并让嵌套记录引用它", () => {
  const host = new Host(), pi = createLearningDebug().wrap(host, "extensions/example.ts");
  const branch = [{ type: "message", id: "tools", message: { role: "assistant", toolsAdded: [
    { name: "fixture", description: "One complete schema.", parameters: { type: "object", properties: { auth: { type: "string", description: "private fixture field" }, path: { type: "string" } } } },
  ] } }];
  const ctx = context(); ctx.sessionManager.getBranch = () => branch;
  pi.on("input", () => { pi.setActiveTools(["learn"]); pi.appendEntry("observation", { text: "safe nested value" }); return true; });
  host.events.get("input")?.({}, ctx);
  const directory = debugDirectory(cwd, agent);
  const raw = readdirSync(directory).filter(name => name.endsWith(".jsonl")).sort()
    .flatMap(name => readFileSync(path.join(directory, name), "utf8").trim().split("\n").filter(Boolean).map(line => JSON.parse(line)));
  const snapshots = raw.filter(row => row.event === "context:snapshot");
  expect(snapshots).toHaveLength(1);
  expect(snapshots[0].data.context.cwd).toBe(cwd);
  expect(JSON.stringify(snapshots[0].data.context)).not.toContain("private fixture field");
  for (const row of raw.filter(row => row.event !== "context:snapshot")) {
    expect(row.contextRef).toBe(snapshots[0].contextDigest);
    expect(row.context.sessionId).toBe("one");
    expect(row.context.projectId).toBe(createHash("sha256").update(cwd).digest("hex"));
    expect(JSON.stringify(row.context)).not.toContain("toolsAdded");
  }
  const all = JSON.stringify(raw);
  expect(all.split("private fixture field")).toHaveLength(1);
  expect(all.length).toBeLessThan(12_000);
});

test("重复的生命周期 handler 保留独立身份但不复制完整上下文", async () => {
  const host = new Host(), pi = createLearningDebug().wrap(host, "extensions/example.ts"), ctx = context();
  const failure = Error("fixture handler failed");
  const invocations: Array<{ name: string; handler: Callback }> = [];
  const originalOn = host.on.bind(host);
  host.on = (name: string, handler: Callback) => { invocations.push({ name, handler }); return originalOn(name, handler); };
  for (const index of [0, 1, 2]) pi.on("session_start", () => index);
  pi.on("session_start", () => { throw failure; });
  for (const { handler } of invocations.slice(0, 3)) expect(handler({}, ctx)).toBeGreaterThanOrEqual(0);
  try { invocations[3].handler({}, ctx); } catch (error) { expect(error).toBe(failure); }
  await Bun.sleep(1);
  const batch = records().filter(row => row.event === "lifecycle:batch");
  expect(batch).toHaveLength(1);
  expect(batch[0].data.handlers).toHaveLength(7);
  expect(new Set(batch[0].data.handlers.map((entry: { invocationId: string }) => entry.invocationId)).size).toBe(4);
  expect(batch[0].data.handlerCount).toBe(4);
  expect(records().filter(row => row.phase === "failed")).toHaveLength(1);
  expect(JSON.stringify(batch[0].context)).not.toContain("Inspect the queue contract.");
});

test("零写入与应用流水线记录明确终态而非 unverified 兜底", async () => {
  const host = new Host(), pi = createLearningDebug().wrap(host, "extensions/inject-memory.ts"), ctx = context();
  const screened = buildLearningReceipt("automatic", { memory: false, harness: false, agents: false, reasons: ["no-durable-memory-evidence"] }, [], undefined, "batch_" + "2".repeat(32));
  const applied = buildLearningReceipt("automatic", { memory: true, harness: false, agents: false, reasons: [] }, [
    { phase: "memory", attempt: 0, outcome: "applied", durationMs: 1, operations: 2 },
  ], undefined, "batch_" + "3".repeat(32));
  pi.on("agent_settled", () => undefined);
  for (const receipt of [screened, applied]) {
    host.events.get("agent_settled")?.({}, ctx);
    pi.sendMessage({ customType: "continual-learning-result", details: receipt });
  }
  await Bun.sleep(1);
  const rows = records();
  expect(rows.some(row => row.event === "pipeline:closed")).toBe(false);
  expect(rows.every(row => row.outcome !== "unverified")).toBe(true);
});

test("进程退出标记与检查器显式区分缺少 shutdown 和未闭合回调", () => {
  const host = new Host(), debug = createLearningDebug(), pi = debug.wrap(host, "extensions/example.ts"), ctx = context();
  pi.on("session_start", () => undefined);
  host.events.get("session_start")?.({ type: "session_start", reason: "startup" }, ctx);
  debug.noteProcessExit("quit", 0, undefined, cwd);
  const rows = records();
  expect(rows.filter(row => row.event === "process:exit").map(row => row.data)).toEqual([{ reason: "quit", exitCode: 0 }]);
  expect(rows.some(row => row.phase === "started" && row.event === "event:session_start" && !rows.some(other => other.event === "lifecycle:batch"))).toBe(false);
});

test("后台 detached 任务保留根调用身份和同一 batch", async () => {
  const host = new Host(), debug = createLearningDebug(), pi = debug.wrap(host, "extensions/inject-memory.ts"), ctx = context();
  let release: (() => void) | undefined;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const batchId = "batch_" + "7".repeat(32);
  pi.on("agent_settled", () => {
    void gate.then(() => {
      pi.sendMessage({ customType: "continual-learning-result", details: { batchId, operations: 1 } });
    });
    return undefined;
  });
  host.events.get("agent_settled")?.({}, ctx);
  release?.(); await Promise.resolve(); await Promise.resolve();
  const rows = records(), root = rows.find(row => row.event === "event:agent_settled" && row.phase === "started");
  const message = rows.find(row => row.event === "sendMessage");
  expect(message?.parentInvocationId).toBe(root?.invocationId);
  expect(message?.contextRef).toBe(root?.contextRef);
  expect(message?.data[0].details.batchId).toBe(batchId);
});

test("debug status 报告分段数和总字节但不自动清理历史", () => {
  const debug = createLearningDebug(), ctx = context();
  const status = debug.status(cwd);
  expect(status.segmentCount).toBeGreaterThanOrEqual(0);
  expect(status.totalBytes).toBeGreaterThanOrEqual(0);
  expect(status.retention).toBe("manual");
  expect(ctx.notices).toEqual([]);
});

test("separate writers and rotation preserve earlier complete JSONL evidence", () => {
  const host = new Host(), debug = createLearningDebug(), pi = debug.wrap(host, "extensions/example.ts"), ctx = context();
  pi.on("input", () => "observed");
  const event = { text: "bounded fixture ".repeat(800) };
  for (let i = 0; i < 1200; i++) host.events.get("input")?.(event, ctx);
  const files = readdirSync(debugDirectory(cwd, agent));
  expect(files.length).toBeGreaterThan(1);
  expect(records()).toHaveLength(2400);
  expect(files.length).toBeGreaterThan(1);
  const other = new Host(); createLearningDebug().wrap(other, "extensions/second.ts").on("input", () => true);
  other.events.get("input")?.({}, ctx);
  expect(readdirSync(debugDirectory(cwd, agent)).length).toBeGreaterThan(files.length);
  expect(records()).toHaveLength(2402);
});
