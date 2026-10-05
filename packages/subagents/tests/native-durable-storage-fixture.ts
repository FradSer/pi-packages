/** Real Pi parent and child: durable tools, explicit stop, and native closure. */
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

export default function nativeDurableStorageFixture(pi: ExtensionAPI): void {
  const root = process.env.PI_NATIVE_DURABLE_ROOT;
  const project = process.env.PI_NATIVE_DURABLE_PROJECT;
  const evidence = process.env.PI_NATIVE_DURABLE_EVIDENCE;
  const phase = process.env.PI_NATIVE_DURABLE_PHASE;
  const prompt = process.env.PI_NATIVE_DURABLE_PROMPT;
  const auth = process.env.PI_NATIVE_DURABLE_AUTH;
  assert.ok(root && project && evidence && phase && prompt && auth, "An isolated durable fixture is required");
  assert.equal(process.env.HOME, root);
  assert.equal(process.env.PI_CODING_AGENT_DIR, path.join(root, "agent"));
  assert.equal(process.cwd(), project);
  assert.ok(project.startsWith(root + path.sep) && evidence.startsWith(root + path.sep));
  assert.ok(["write-a", "resume-a", "project-b"].includes(phase));
  assert.equal(process.env.PI_OFFLINE, "1");

  const launches: RecordValue[] = [];
  const frames: RecordValue[] = [];
  const receipts: RecordValue[] = [];
  const notices: RecordValue[] = [];
  const closes: RecordValue[] = [];
  const failures: string[] = [];
  let order = 0;
  let parentSessionId: string | undefined;
  let child: ChildProcess | undefined;
  let finalNotice: RecordValue | undefined;
  let resolveFinal!: () => void;
  let resolveClosed!: () => void;
  const finalReceived = new Promise<void>(resolve => { resolveFinal = resolve; });
  const childClosed = new Promise<void>(resolve => { resolveClosed = resolve; });
  const waitFor = async (label: string, pending: Promise<void>): Promise<void> => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      await Promise.race([pending, new Promise<void>((_resolve, reject) => {
        timer = setTimeout(() => reject(new Error(`${label} timed out`)), 30_000);
      })]);
    } finally {
      if (timer) clearTimeout(timer);
    }
  };

  // Observe native arguments, bytes and closure without substituting a process
  // or protocol outcome. The hook is private to this fixture's parent process.
  const originalSpawn = childProcess.spawn;
  childProcess.spawn = ((...args: Parameters<typeof childProcess.spawn>): ChildProcess => {
    const spawned: ChildProcess = Reflect.apply(originalSpawn, childProcess, args);
    const argv = args[1];
    if (!Array.isArray(argv) || !argv.includes("rpc")) return spawned;
    assert.equal(child, undefined, "One phase owns exactly one native child");
    child = spawned;
    const options = args[2];
    launches.push({ pid: spawned.pid, cwd: options?.cwd, args: argv, order: ++order });
    const decoder = new StringDecoder("utf8");
    let pending = "";
    const consume = (text: string, flush = false): void => {
      pending += text;
      const lines = pending.split("\n");
      pending = lines.pop() ?? "";
      if (flush && pending.trim()) { lines.push(pending); pending = ""; }
      for (const line of lines) {
        if (!line.trim()) continue;
        try { frames.push({ ...record(JSON.parse(line)), order: ++order }); }
        catch { failures.push("The native child emitted invalid JSONL"); }
      }
    };
    spawned.stdout?.on("data", (bytes: Buffer) => consume(decoder.write(bytes)));
    spawned.once("close", (code, signal) => {
      consume(decoder.end(), true);
      closes.push({ pid: spawned.pid, code, signal, order: ++order });
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
  pi.on("session_start", (_event, ctx) => {
    parentSessionId = ctx.sessionManager.getSessionId();
    assert.equal(parentSessionId, process.env.PI_NATIVE_DURABLE_PARENT_ID);
  });
  pi.on("tool_result", event => {
    if (event.toolName === "agent_start" || event.toolName === "agent_stop") {
      receipts.push({ tool: event.toolName, isError: event.isError, ...record(event.details), order: ++order });
    }
  });
  pi.on("session_shutdown", () => {
    writeFileSync(evidence, JSON.stringify({ phase, project, parentSessionId, launches, frames, receipts, notices, closes, failures }));
    childProcess.spawn = originalSpawn;
    syncBuiltinESMExports();
  });

  let request = 0;
  pi.registerProvider("native-durable-parent", {
    api: "native-durable-parent", baseUrl: "http://127.0.0.1", apiKey: auth,
    models: [{ id: "scripted", name: "Isolated durable parent", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const stream = createAssistantMessageEventStream();
      const index = request++;
      void (async () => {
        let call: ToolCall | undefined;
        if (index === 0) {
          call = { type: "toolCall", id: `start-${phase}`, name: "agent_start",
            arguments: { identity: "native-durable", prompt } };
        } else if (index === 1) {
          await waitFor("native final delivery", finalReceived);
          assert.ok(finalNotice);
          assert.equal(finalNotice?.kind, "result");
          assert.equal(typeof finalNotice.session, "string");
          call = { type: "toolCall", id: `stop-${phase}`, name: "agent_stop",
            arguments: { session: finalNotice.session } };
        } else {
          await waitFor("native child closure", childClosed);
          assert.equal(closes.length, 1);
          assert.ok(receipts.some(value => value.tool === "agent_stop" && value.isError !== true));
          assert.equal(failures.length, 0);
        }
        const message: AssistantMessage = {
          role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
          content: call ? [call] : [{ type: "text", text: "NATIVE_DURABLE_OK" }],
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
