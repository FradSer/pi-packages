/** Native Pi parent fixture for parent-session-partitioned durable children. */
import assert from "node:assert/strict";
import childProcess, { type ChildProcess } from "node:child_process";
import { writeFileSync } from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import path from "node:path";
import { StringDecoder } from "node:string_decoder";
import { createAssistantMessageEventStream, type AssistantMessage, type ToolCall } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import subagents from "../src/extension.ts";

type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue =>
  typeof value === "object" && value !== null && !Array.isArray(value) ? value as RecordValue : {};

export default function nativeParentSessionHistoryFixture(pi: ExtensionAPI): void {
  const root = process.env.PI_PARENT_HISTORY_ROOT;
  const evidencePath = process.env.PI_PARENT_HISTORY_EVIDENCE;
  const phase = process.env.PI_PARENT_HISTORY_PHASE;
  const marker = process.env.PI_PARENT_HISTORY_MARKER;
  const identity = process.env.PI_PARENT_HISTORY_IDENTITY;
  const project = process.env.PI_PARENT_HISTORY_PROJECT;
  const childModel = process.env.PI_PARENT_HISTORY_CHILD_MODEL;
  const auth = process.env.PI_PARENT_HISTORY_AUTH;
  assert.ok(root && evidencePath && phase && marker && identity && project && childModel && auth);
  assert.equal(process.env.HOME, root);
  assert.equal(process.env.PI_CODING_AGENT_DIR, path.join(root, "agent"));
  assert.equal(process.cwd(), project);
  assert.equal(process.env.PI_OFFLINE, "1");
  assert.ok(evidencePath.startsWith(root + path.sep) && project.startsWith(root + path.sep));
  assert.ok(["initial", "resume"].includes(phase));

  const launches: RecordValue[] = [];
  const closes: RecordValue[] = [];
  const frames: RecordValue[] = [];
  const notices: RecordValue[] = [];
  const receipts: RecordValue[] = [];
  const failures: string[] = [];
  let order = 0;
  let finalNotice: RecordValue | undefined;
  let durableSession = "";
  let temporarySession = "";
  let resolveFinal!: () => void;
  let finalReceived = new Promise<void>(resolve => { resolveFinal = resolve; });
  let childClosed: Promise<void> | undefined;
  const resetFinal = (): void => {
    finalNotice = undefined;
    finalReceived = new Promise<void>(resolve => { resolveFinal = resolve; });
  };

  const writeEvidence = (): void => writeFileSync(evidencePath, JSON.stringify({
    phase, marker, identity, project, parentId, launches, closes, frames, notices, receipts, failures,
  }));
  const waitFor = async (label: string, pending: Promise<void>): Promise<void> => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      await Promise.race([pending, new Promise<void>((_resolve, reject) => {
        timer = setTimeout(() => reject(new Error(`${label} timed out`)), 45_000);
      })]);
    } finally { if (timer) clearTimeout(timer); }
  };

  let parentId = "";
  pi.on("session_start", (_event, ctx) => {
    parentId = ctx.sessionManager.getSessionId();
    writeEvidence();
  });

  const originalSpawn = childProcess.spawn;
  childProcess.spawn = ((...args: Parameters<typeof childProcess.spawn>): ChildProcess => {
    const spawned: ChildProcess = Reflect.apply(originalSpawn, childProcess, args);
    const argv = args[1];
    if (!Array.isArray(argv) || !argv.includes("rpc")) return spawned;
    let resolveClosed!: () => void;
    childClosed = new Promise<void>(resolve => { resolveClosed = resolve; });
    const options = args[2];
    assert.equal(options?.env?.HOME, root);
    assert.equal(options?.env?.PI_CODING_AGENT_DIR, path.join(root, "agent"));
    assert.equal(options?.cwd, project);
    const sessionDirIndex = argv.indexOf("--session-dir");
    launches.push({
      pid: spawned.pid,
      cwd: options?.cwd,
      args: argv,
      sessionDir: sessionDirIndex >= 0 ? argv[sessionDirIndex + 1] : undefined,
      noSession: argv.includes("--no-session"),
      spawnedAt: Date.now(),
      order: ++order,
    });
    const decoder = new StringDecoder("utf8");
    let pending = "";
    const consume = (text: string, flush = false): void => {
      pending += text;
      const lines = pending.split("\n");
      pending = lines.pop() ?? "";
      if (flush && pending.trim()) { lines.push(pending); pending = ""; }
      for (const line of lines) {
        if (!line.trim()) continue;
        try { frames.push({ ...record(JSON.parse(line)), pid: spawned.pid, order: ++order }); }
        catch { failures.push("native child emitted invalid JSONL"); }
      }
    };
    spawned.stdout?.on("data", (bytes: Buffer) => consume(decoder.write(bytes)));
    spawned.once("close", (code, signal) => {
      consume(decoder.end(), true);
      closes.push({ pid: spawned.pid, code, signal, closedAt: Date.now(), order: ++order });
      resolveClosed();
    });
    return spawned;
  }) as typeof childProcess.spawn;
  syncBuiltinESMExports();

  const observedPi: ExtensionAPI = {
    ...pi,
    sendMessage(message, options) {
      const details = record(message.details);
      notices.push({ customType: message.customType, ...details, order: ++order });
      if (message.customType === "subagents-session-result") {
        finalNotice = details;
        resolveFinal();
      }
      pi.sendMessage(message, options);
    },
  };
  subagents(observedPi);
  pi.on("tool_result", event => {
    if (event.toolName !== "agent_start" && event.toolName !== "agent_stop") return;
    const details = record(event.details);
    receipts.push({ tool: event.toolName, isError: event.isError === true, ...details, order: ++order });
    if (event.toolName === "agent_start" && typeof details.name === "string") {
      if (details.name === identity) durableSession = typeof details.session === "string" ? details.session : "";
      if (details.label === "native-temp") temporarySession = typeof details.session === "string" ? details.session : "";
    }
    writeEvidence();
  });
  pi.on("session_shutdown", () => {
    writeEvidence();
    childProcess.spawn = originalSpawn;
    syncBuiltinESMExports();
  });

  let request = 0;
  pi.registerProvider("native-parent-history", {
    api: "native-parent-history", baseUrl: "http://127.0.0.1", apiKey: auth,
    models: [{ id: "scripted", name: "Native parent history", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const stream = createAssistantMessageEventStream();
      const index = request++;
      void (async () => {
        let call: ToolCall | undefined;
        if (index === 0) {
          call = { type: "toolCall", id: `start-${phase}`, name: "agent_start", arguments: {
            identity, prompt: phase === "initial"
              ? `FIRST_PARENT_HISTORY_MARKER:${marker}`
              : `REOPEN_PARENT_${marker.endsWith("_A") ? "A" : "B"}`,
            tools: ["read", "write", "agent_memory"], model: childModel,
          } };
        } else if (index === 1) {
          await waitFor("durable child result", finalReceived);
          if (!finalNotice || finalNotice.kind !== "result") throw new Error("durable child did not produce a result");
          call = { type: "toolCall", id: `stop-${phase}`, name: "agent_stop", arguments: { session: durableSession } };
        } else if (index === 2 && phase === "initial") {
          assert.ok(childClosed);
          await waitFor("durable child closure", childClosed);
          resetFinal();
          call = { type: "toolCall", id: "start-temporary", name: "agent_start", arguments: {
            label: "native-temp", prompt: "TEMPORARY_CHILD_MARKER", tools: [], model: childModel,
          } };
        } else if (index === 3 && phase === "initial") {
          await waitFor("temporary child result", finalReceived);
          assert.ok(finalNotice && finalNotice.session === temporarySession);
          call = { type: "toolCall", id: "stop-temporary", name: "agent_stop", arguments: { session: temporarySession } };
        } else {
          assert.ok(childClosed);
          await waitFor("native child closure", childClosed);
          assert.equal(closes.length, launches.length);
          assert.ok(receipts.every(value => value.isError !== true));
        }
        const message: AssistantMessage = {
          role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
          content: call ? [call] : [{ type: "text", text: "NATIVE_PARENT_HISTORY_OK" }],
          stopReason: call ? "toolUse" : "stop",
          usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
        };
        stream.push({ type: "start", partial: message });
        stream.push({ type: "done", reason: message.stopReason, message });
      })().catch(error => {
        failures.push(error instanceof Error ? error.message : String(error));
        process.exitCode = 1;
        stream.end();
      });
      return stream;
    },
  });
}
