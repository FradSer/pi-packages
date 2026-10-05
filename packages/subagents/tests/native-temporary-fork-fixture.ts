/** Native Pi RPC + loopback HTTP, or the real spawner with only its process boundary mocked. */
import assert from "node:assert/strict";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { EventEmitter } from "node:events";
import { readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { PassThrough } from "node:stream";
import { StringDecoder } from "node:string_decoder";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI, SessionContext } from "@earendil-works/pi-coding-agent";

type Message = SessionContext["messages"][number];
const fixturePath = fileURLToPath(import.meta.url);
const repo = resolve(fixturePath, "../../../..");
const root = process.env.PI_FORK_FIXTURE_ROOT!;
const marker = process.env.PI_FORK_MARKER!;
const usage = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } };

function history(): Message[] {
  return [
    { role: "system", content: "parent-private-metadata", timestamp: 1,
      toolsAdded: [{ name: "parent_admin", description: "Parent authority", parameters: {} }] },
    { role: "compactionSummary", summary: "Native compacted evidence", tokensBefore: 40, timestamp: 2 },
    { role: "branchSummary", summary: "Native branch evidence", fromId: "old-branch", timestamp: 3 },
    { role: "user", content: `Historical marker ${marker} 中文\u2028line`, timestamp: 4 },
    { role: "assistant", content: [{ type: "text", text: "Historical assistant" },
      { type: "toolCall", id: "historical-read", name: "read", arguments: { path: "historical.ts" } },
      { type: "toolCall", id: "unfinished-read", name: "read", arguments: { path: "unfinished.ts" } }],
      api: "openai-completions", provider: "fork-loopback", model: "history", usage,
      stopReason: "toolUse", timestamp: 5 },
    { role: "toolResult", toolCallId: "historical-read", toolName: "read",
      content: [{ type: "text", text: "Historical completed result" }], isError: false, timestamp: 6,
      details: { credential: "parent-private-metadata" } },
    { role: "custom", customType: "evidence", content: "Custom historical evidence", display: false,
      timestamp: 7, details: { runtimeAuthority: "parent-private-metadata" } },
  ];
}

function assertNoHistoryFiles(directory = root): void {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const file = join(directory, entry.name);
    if (entry.isDirectory()) assertNoHistoryFiles(file);
    else if (entry.isFile()) {
      assert.ok(!file.endsWith(".jsonl"), `Temporary fork wrote a history file: ${file}`);
      assert.ok(!readFileSync(file).includes(Buffer.from(marker)), `Temporary fork wrote the seed: ${file}`);
    }
  }
}

/** Loaded after the fork extension: inspect real native context and raw session entries. */
export default function observeNativeContext(pi: ExtensionAPI): void {
  pi.on("context", (event, ctx) => {
    assert.equal(ctx.sessionManager.getSessionFile(), undefined);
    if (process.env.PI_FORK_PRINT === "1") {
      assert.ok(!JSON.stringify(event.messages).includes(marker), "No fork extension means no invented history");
      assertNoHistoryFiles();
      return;
    }
    assert.ok(event.messages.some(message => message.role === "compactionSummary"));
    assert.ok(event.messages.some(message => message.role === "branchSummary"));
    assert.equal(event.messages.filter(message => message.role === "toolResult").length, 1);
    const serialized = JSON.stringify(event.messages);
    assert.equal(serialized.split(marker).length - 1, 1);
    assert.ok(!serialized.includes("parent-private-metadata"));
    assert.ok(!serialized.includes("unfinished-read"));
    assert.deepEqual(pi.getActiveTools(), []);
    const native = JSON.stringify(ctx.sessionManager.getEntries());
    assert.ok(!native.includes(marker), "Seed stays outside native persisted/entry state");
    assert.ok(!native.includes("subagents-context"));
    assertNoHistoryFiles();
  });
}

async function spawnProbe(probe: string): Promise<void> {
  const { mock } = await import("node:test");
  const kit = await import("@fradser/pi-kit");
  const context = await import("../src/work-context.ts");
  const launches: string[][] = [];
  const commands: Array<{ id: string; type: string; message?: string }> = [];
  const child = Object.assign(new EventEmitter(), {
    pid: 7, stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(),
  });
  child.stdin.on("data", chunk => {
    const command = JSON.parse(String(chunk));
    commands.push(command);
    child.stdout.write(JSON.stringify({ type: "response", id: command.id, command: command.type, success: true,
      data: command.type === "get_state" ? { isStreaming: false, pendingMessageCount: 0 }
        : { disposition: command.message?.startsWith("/subagents-context ") ? "handled" : "started" },
    }) + "\n");
  });
  mock.module("@fradser/pi-kit", { namedExports: { ...kit,
    resolvePiCli: () => ({ command: "fixture-pi", args: [] }),
    spawnPiChild: (_command: string, args: string[]) => { launches.push([...args]); return child; },
    terminateChildProcess: async () => { child.emit("close", 0, null); return true; },
  } });
  const spawner = await import("../src/spawner.ts");
  if (probe === "setup-timeout") mock.timers.enable({ apis: ["setTimeout"] });
  try {
    const prompted = probe !== "spawn-idle";
    const started = spawner.spawnResident({ agentName: "memory-fork", context: history(), session: "none",
      cwd: root, tools: [], ...(prompted ? { description: "FORK_INPUT_ONE" } : {}), onExit: () => {} });
    assert.ok(!("error" in started));
    const args = launches[0];
    assert.ok(args.includes("--no-session"), "Temporary context must not override --no-session with --session");
    assert.ok(!args.includes("--session") && !args.includes("--session-dir"));
    assert.ok(args.includes(join(repo, "packages/subagents/src/fork-extension.ts")), "Explicit child fork extension required");
    assertNoHistoryFiles();
    await new Promise<void>(resolve => setImmediate(resolve));
    const setup = commands.find(command => command.message?.startsWith("/subagents-context "));
    assert.ok(setup, "Setup must cross the control pipe, not argv/env/history files");
    assert.ok(!commands.some(command => command.message === "FORK_INPUT_ONE"), "Kickoff waits for setup acknowledgement");
    let completed = false;
    const outcome = (prompted ? started.accepted! : started.readiness!).then(value => {
      completed = true;
      return value;
    });
    await new Promise<void>(resolve => setImmediate(resolve));
    assert.equal(completed, false, "RPC handled alone does not acknowledge setup");
    if (probe === "setup-timeout") {
      mock.timers.tick(29_999);
      await new Promise<void>(resolve => setImmediate(resolve));
      assert.equal(completed, false, "Fork setup remains pending within its startup window");
      mock.timers.tick(2);
    } else if (probe === "setup-close") child.emit("close", 0, null);
    else if (probe !== "setup-timeout") {
      child.stdout.write(JSON.stringify({ type: "extension_ui_request", method: "setStatus",
        statusKey: context.FORK_CONTEXT_ACK_STATUS,
        statusText: JSON.stringify(probe === "setup-rejected"
          ? { version: 1, requestId: setup.id, success: false, error: "Fixture setup refused" }
          : { version: 1, requestId: setup.id, success: true, messageCount: 6 }),
      }) + "\n");
    }
    const expected = !probe.startsWith("setup-");
    assert.equal(await outcome, expected);
    assert.equal(commands.filter(command => command.message === "FORK_INPUT_ONE").length, expected && prompted ? 1 : 0);
    child.emit("close", 0, null);
    assertNoHistoryFiles();
    console.log(JSON.stringify({ ok: true, probe }));
  } finally {
    child.emit("close", 0, null);
    if (probe === "setup-timeout") mock.timers.reset();
    mock.restoreAll();
  }
}

type RecordValue = Record<string, unknown>;
class NativeRpc {
  readonly child: ChildProcessWithoutNullStreams;
  readonly records: RecordValue[] = [];
  readonly waiters = new Set<() => void>();
  stderr = "";
  private buffer = "";
  constructor() {
    this.child = spawn(process.execPath, [join(repo, "node_modules/@earendil-works/pi-coding-agent/dist/cli.js"),
      "--mode", "rpc", "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes",
      "--no-context-files", "--no-approve", "--no-tools", "--provider", "fork-loopback", "--model", "history", "--thinking", "off",
      "--extension", join(repo, "packages/subagents/src/fork-extension.ts"), "--extension", fixturePath,
    ], { cwd: root, env: process.env, stdio: ["pipe", "pipe", "pipe"] });
    const decoder = new StringDecoder("utf8");
    this.child.stdout.on("data", (chunk: Buffer) => {
      this.buffer += decoder.write(chunk);
      const lines = this.buffer.split("\n");
      this.buffer = lines.pop() ?? "";
      for (const line of lines) if (line.trim()) this.records.push(JSON.parse(line));
      for (const wake of [...this.waiters]) wake();
    });
    this.child.stderr.on("data", chunk => { this.stderr += String(chunk); });
    this.child.on("close", () => { for (const wake of [...this.waiters]) wake(); });
  }
  async wait(predicate: (record: RecordValue) => boolean, offset = 0): Promise<RecordValue> {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => finish(new Error(`Native RPC deadline: ${this.stderr}`)), 10_000);
      const finish = (error?: Error, record?: RecordValue) => {
        clearTimeout(timeout); this.waiters.delete(wake);
        if (error) reject(error); else resolve(record!);
      };
      const wake = () => {
        const error = this.records.find(record => record.type === "extension_error");
        if (error) return finish(new Error(JSON.stringify(error)));
        const record = this.records.slice(offset).find(predicate);
        if (record) finish(undefined, record);
        else if (this.child.exitCode !== null || this.child.signalCode !== null) finish(new Error(`Native RPC exited: ${this.stderr}`));
      };
      this.waiters.add(wake); wake();
    });
  }
  async command(command: { type: string; id: string; message?: string }): Promise<RecordValue> {
    this.child.stdin.write(JSON.stringify(command) + "\n");
    const response = await this.wait(record => record.type === "response" && record.id === command.id);
    assert.equal(response.success, true, JSON.stringify(response));
    return response;
  }
  async close(): Promise<void> {
    if (this.child.exitCode !== null || this.child.signalCode !== null) return;
    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => { this.child.kill("SIGKILL"); reject(new Error("Native RPC close deadline")); }, 5_000);
      this.child.once("close", code => {
        clearTimeout(timeout);
        if (code === 0) resolve(); else reject(new Error(`Native RPC close failed: ${this.stderr}`));
      });
      this.child.stdin.end();
    });
  }
}

async function nativeProbe(): Promise<void> {
  const { createForkContextCommand, parseForkContextAck } = await import("../src/work-context.ts");
  const rpc = new NativeRpc();
  try {
    const initial = await rpc.command({ type: "get_state", id: "initial" });
    assert.equal((initial.data as RecordValue).sessionFile, undefined);
    const command = createForkContextCommand("fork-setup", history());
    const setupResponse = await rpc.command(command);
    assert.equal((setupResponse.data as RecordValue).disposition, "handled");
    const ackRecord = await rpc.wait(record => parseForkContextAck(record, command.id) !== undefined);
    assert.equal(parseForkContextAck(ackRecord, command.id)?.success, true);
    assertNoHistoryFiles();
    // Pi emits handled even when a command refuses setup. Verify the negative
    // correlated ack and no extra model request for both repeated/malformed seed.
    for (const [id, message] of [["repeated", createForkContextCommand("repeated", []).message], ["malformed", "/subagents-context malformed %%%"]]) {
      const response = await rpc.command({ type: "prompt", id, message });
      assert.equal((response.data as RecordValue).disposition, "handled");
      const refusal = await rpc.wait(record => parseForkContextAck(record, id) !== undefined);
      assert.equal(parseForkContextAck(refusal, id)?.success, false);
    }
    for (const [id, message, answer] of [["first", "FORK_INPUT_ONE", "FORK_ANSWER_1"], ["second", "FORK_INPUT_TWO", "FORK_ANSWER_2"]]) {
      const offset = rpc.records.length;
      const response = await rpc.command({ type: "prompt", id, message });
      assert.equal((response.data as RecordValue).disposition, "started");
      assert.ok(rpc.records.indexOf(ackRecord) < rpc.records.indexOf(response), "Setup acknowledged before first model input");
      await rpc.wait(record => record.type === "agent_settled", offset);
      const last = await rpc.command({ type: "get_last_assistant_text", id: `${id}-answer` });
      assert.equal((last.data as RecordValue).text, answer);
      assertNoHistoryFiles();
    }
    const state = await rpc.command({ type: "get_state", id: "final-state" });
    assert.equal((state.data as RecordValue).sessionFile, undefined);
    const entries = await rpc.command({ type: "get_entries", id: "entries" });
    assert.ok(!JSON.stringify(entries).includes(marker));
    assert.ok(!JSON.stringify(entries).includes("subagents-context"));
    assert.equal((entries.data as { entries: Array<{ type: string; message?: Message }> }).entries
      .filter(entry => entry.type === "message" && entry.message?.role === "user").length, 2);
    const reset = await rpc.command({ type: "new_session", id: "reset" });
    assert.equal((reset.data as RecordValue).cancelled, false);
    const fresh = await rpc.command({ type: "get_messages", id: "fresh" });
    assert.ok(!JSON.stringify(fresh).includes(marker));
    await rpc.close(); assertNoHistoryFiles();
    console.log(JSON.stringify({ ok: true, probe: "native", requests: 2 }));
  } finally {
    await rpc.close();
  }
}

async function productionSpawnerProbe(probe: string): Promise<void> {
  const { spawnResident, deliverResidentPrompt, terminateAgent } = await import("../src/spawner.ts");
  const firstInput = probe === "spawner-native-prompted";
  const finals: string[] = [];
  const pending = new Set<() => void>();
  let error: string | undefined;
  const waitAnswers = (count: number) => new Promise<void>((resolveAnswer, reject) => {
    const timeout = setTimeout(() => finish(new Error(error ?? "Production spawner answer deadline exceeded")), 10000);
    const finish = (failure?: Error) => { clearTimeout(timeout); pending.delete(update); if (failure) reject(failure); else resolveAnswer(); };
    const update = () => { if (error) finish(new Error(error)); else if (finals.length >= count) finish(); };
    pending.add(update); update();
  });
  try {
    const started = spawnResident({ agentName: "native-fork", session: "none", context: history(), cwd: root, tools: [],
      model: "fork-loopback/history", extensions: [fixturePath],
      ...(firstInput ? { description: "FORK_INPUT_ONE" } : {}),
      onUpdate(progress) {
        if (progress.finalResponse && progress.answerComplete) finals.push(progress.text);
        if (progress.controlError) error = progress.controlError;
        for (const update of [...pending]) update();
        assertNoHistoryFiles();
      },
      onError(failure) { error = failure.message; for (const update of [...pending]) update(); },
      onExit(result) { if (result.exitCode !== 0 && result.signal !== "SIGTERM") error = result.stderr; for (const update of [...pending]) update(); },
    });
    assert.ok(!("error" in started), JSON.stringify(started));
    if (firstInput) assert.equal(await started.accepted, true);
    else { assert.equal(await started.readiness, true); assert.equal(await deliverResidentPrompt("native-fork", "FORK_INPUT_ONE"), true); }
    await waitAnswers(1); assertNoHistoryFiles();
    assert.equal(await deliverResidentPrompt("native-fork", "FORK_INPUT_TWO"), true);
    await waitAnswers(2); assertNoHistoryFiles();
    assert.deepEqual(finals, ["FORK_ANSWER_1", "FORK_ANSWER_2"]);
    assert.equal((await terminateAgent("native-fork")).outcome, "closed");
    assertNoHistoryFiles();
    console.log(JSON.stringify({ ok: true, probe, requests: 2 }));
  } finally { await terminateAgent("native-fork"); }
}

if (process.argv[1] && resolve(process.argv[1]) === fixturePath) {
  const probe = process.argv[2];
  if (probe === "native") await nativeProbe();
  else if (probe.startsWith("spawner-native-")) await productionSpawnerProbe(probe);
  else await spawnProbe(probe);
}
