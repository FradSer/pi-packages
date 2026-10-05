/** Q1/Q3: native parent Pi, production agent/spawner, and real child RPC I/O.
 * No fake process, control reply, readiness promise, or input acknowledgement.
 * The spawn/write taps forward original arguments and bytes without substitution.
 */
import assert from "node:assert/strict";
import childProcess, { type ChildProcess } from "node:child_process";
import { appendFileSync, existsSync, readFileSync, realpathSync } from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import path from "node:path";
import { StringDecoder } from "node:string_decoder";
import { stripVTControlCharacters } from "node:util";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { visibleWidth } from "@earendil-works/pi-tui";
import piSubagents from "../packages/subagents/src/extension.ts";
import { getAgent, livingAgents } from "../packages/subagents/src/roster.ts";
import { setAgentHost } from "../packages/subagents/src/child-execution.ts";

type ToolArguments = Extract<AssistantMessage["content"][number], { type: "toolCall" }>["arguments"];

function nativePiVersion(entry: string): string {
  let directory = path.dirname(realpathSync(entry));
  for (;;) {
    const manifest = path.join(directory, "package.json");
    if (existsSync(manifest)) {
      const metadata = JSON.parse(readFileSync(manifest, "utf8")) as { name: string; version: string };
      if (metadata.name === "@earendil-works/pi-coding-agent") return metadata.version;
    }
    const parent = path.dirname(directory);
    assert.notEqual(parent, directory, "Native executable must belong to the actual Pi coding-agent package");
    directory = parent;
  }
}

type WireRecord = {
  type: string;
  id?: string;
  command?: string;
  success?: boolean;
  data?: Record<string, unknown>;
  message?: string;
  streamingBehavior?: string;
};

export default function (pi: ExtensionAPI): void {
  // This fixture verifies the supported legacy model interface.
  const nativeGetFlag = pi.getFlag.bind(pi);
  const root = process.env.PI_LIVE_RESIDENT_ROOT;
  const evidence = process.env.PI_LIVE_RESIDENT_EVIDENCE;
  const baseUrl = process.env.PI_LIVE_RESIDENT_URL;
  const credential = process.env.PI_LIVE_RESIDENT_AUTH;
  const scenario = process.env.PI_LIVE_RESIDENT_CASE;
  assert.ok(root && evidence && baseUrl && credential && scenario, "Only an explicitly isolated fixture may load this extension");
  assert.ok(["save", "resume", "temporary", "project", "steer", "tui"].includes(scenario));
  assert.equal(process.env.HOME, root);
  assert.equal(process.env.PI_CODING_AGENT_DIR, path.join(root, "agent"));
  assert.equal(process.cwd(), path.join(root, "project"));
  assert.ok(evidence.startsWith(root + path.sep));
  assert.equal(new URL(baseUrl).hostname, "127.0.0.1");
  assert.equal(process.env.PI_OFFLINE, "1");
  let order = 0;
  const record = (value: Record<string, unknown>): void => {
    appendFileSync(evidence, JSON.stringify({ ...value, order: ++order }) + "\n");
  };
  const name = scenario === "project" ? "project-reader" : scenario === "steer" ? "resident-steer"
    : scenario === "temporary" ? "temporary-reader" : "saved-reader";
  let mode: ExtensionContext["mode"];
  let handle: string | undefined;
  let child: ChildProcess | undefined;
  let results = 0;
  let resolveResult!: () => void;
  const received = new Promise<void>(resolve => { resolveResult = resolve; });
  let resolveClosed!: () => void;
  const closed = new Promise<void>(resolve => { resolveClosed = resolve; });
  void closed;
  const frames: WireRecord[] = [];
  const writes: WireRecord[] = [];
  const observers = new Set<() => void>();

  async function waitForFrame(predicate: (frame: WireRecord) => boolean): Promise<WireRecord> {
    const existing = frames.find(predicate);
    if (existing) return existing;
    return new Promise((resolve, reject) => {
      const listener = (): void => {
        const frame = frames.find(predicate);
        if (!frame) return;
        clearTimeout(timeout);
        observers.delete(listener);
        resolve(frame);
      };
      const timeout = setTimeout(() => {
        observers.delete(listener);
        reject(new Error("Native RPC evidence deadline exceeded"));
      }, 15_000);
      observers.add(listener);
    });
  }

  let probeId = 0;
  async function probe(tag: string): Promise<void> {
    assert.ok(child?.stdin?.writable, "The real resident must have a living control stream");
    const id = `probe-${++probeId}`;
    const response = waitForFrame(frame => frame.type === "response" && frame.id === id && frame.command === "get_state");
    child.stdin.write(JSON.stringify({ type: "get_state", id }) + "\n");
    const reply = await response;
    assert.equal(reply.success, true, JSON.stringify(reply));
    record({ kind: "probe-state", tag, data: reply.data });
  }

  async function releaseModel(): Promise<void> {
    const response = await fetch(baseUrl + "/release", { method: "POST", signal: AbortSignal.timeout(5_000) });
    assert.equal(response.status, 204);
  }

  // Observe the real OS spawn before the spawner installs its own listeners. ESM
  // synchronization changes only this process's instrumentation binding. The
  // original spawn remains responsible for the actual executable and arguments.
  const originalSpawn = childProcess.spawn;
  const observedSpawn = (...args: Parameters<typeof childProcess.spawn>): ChildProcess => {
    const spawned: ChildProcess = Reflect.apply(originalSpawn, childProcess, args);
    const argv = args[1];
    if (!Array.isArray(argv) || !argv.includes("rpc")) return spawned;
    assert.equal(child, undefined, "This reproduction owns exactly one child");
    child = spawned;
    const options = args[2];
    assert.equal(options?.env?.HOME, root);
    assert.equal(options?.env?.PI_CODING_AGENT_DIR, path.join(root, "agent"));
    assert.equal(options?.cwd, path.join(root, "project"));
    record({ kind: "launch", command: args[0], args: argv, pid: spawned.pid, cwd: options?.cwd,
      piVersion: nativePiVersion(argv[0]) });
    const decoder = new StringDecoder("utf8");
    let pending = "";
    spawned.stdout?.on("data", (bytes: Buffer) => {
      pending += decoder.write(bytes);
      const lines = pending.split("\n");
      pending = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const frame = JSON.parse(line) as WireRecord;
        frames.push(frame);
        record({ kind: "rpc-frame", record: frame });
        for (const observer of [...observers]) observer();
      }
    });
    spawned.stderr?.on("data", (bytes: Buffer) => record({ kind: "child-stderr", text: bytes.toString("utf8") }));
    spawned.once("close", (code, signal) => {
      record({ kind: "child-close", pid: spawned.pid, code, signal });
      resolveClosed();
    });
    assert.ok(spawned.stdin);
    const originalWrite = spawned.stdin.write.bind(spawned.stdin);
    let input = "";
    spawned.stdin.write = ((chunk: unknown, ...rest: unknown[]): boolean => {
      input += Buffer.isBuffer(chunk) ? chunk.toString("utf8") : String(chunk);
      const lines = input.split("\n");
      input = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const command = JSON.parse(line) as WireRecord;
        writes.push(command);
        record({ kind: "rpc-write", record: command });
      }
      return Reflect.apply(originalWrite, spawned.stdin, [chunk, ...rest]);
    }) as typeof spawned.stdin.write;
    return spawned;
  };
  // Node's spawn/write declarations have overloaded return/callback signatures.
  // This fixture adapts those signatures only; every operation still goes to the
  // original native implementation, including backpressure and close semantics.
  childProcess.spawn = observedSpawn as typeof childProcess.spawn;
  syncBuiltinESMExports();

  pi.on("session_start", (_event, ctx) => {
    mode = ctx.mode;
    record({ kind: "parent-start", mode, cwd: ctx.cwd, sessionFile: ctx.sessionManager.getSessionFile(),
      sessionId: ctx.sessionManager.getSessionId(),
      piVersion: nativePiVersion(process.argv[1]) });
  });

  const observedPi: ExtensionAPI = {
    ...pi,
    registerTool(tool) {
      if (tool.name === "agent_start") record({ kind: "schema", parameters: tool.parameters });
      const renderResult = tool.renderResult;
      if (!tool.name.startsWith("agent_") || !renderResult) { pi.registerTool(tool); return; }
      pi.registerTool({
        ...tool,
        renderResult(result, state, theme, context) {
          const component = renderResult(result, state, theme, context);
          return {
            invalidate: () => component.invalidate(),
            render(width) {
              const lines = component.render(width);
              record({ kind: "agent-row", width, expanded: state.expanded, partial: state.isPartial,
                lines: lines.map(stripVTControlCharacters),
                bounded: lines.every(line => !line.includes("\n") && visibleWidth(line) <= width) });
              return lines;
            },
          };
        },
      });
    },
    sendMessage(message, options) {
      if (message.customType === "subagents-session-result") {
        results++;
        record({ kind: "result", content: message.content, details: message.details, options });
        resolveResult();
      } else if (message.customType === "subagents-session-ended") {
        record({ kind: "ended", content: message.content, details: message.details, options });
      }
      pi.sendMessage(message, options);
    },
  };
  piSubagents(observedPi);
  if (scenario === "resume") {
    // A published consumer must not steal saved-definition derivation. Returning
    // a refusal makes an accidental route observable without fabricating a child.
    setAgentHost({
      start(request) {
        record({ kind: "unexpected-host-start", request });
        return { ok: false, error: "Saved-role reuse must keep its private standalone execution" };
      },
      async stop() {
        record({ kind: "unexpected-host-stop" });
        return { ok: false, error: "A private resident must close through its real control binding" };
      },
    });
    record({ kind: "published-host", scenario });
  }
  pi.on("tool_result", event => {
    if (!event.toolName.startsWith("agent_")) return;
    const details = event.details as Record<string, unknown>;
    const action = event.toolName;
    if (action === "agent_start" && typeof details.session === "string") handle = details.session;
    // A saved identity keeps its own name; a temporary role is named by the exact
    // route the start receipt returned, because its label is display only.
    const resident = getAgent(handle?.startsWith("session:") ? handle.slice(8).split(":")[0]! : name);
    record({ kind: "receipt", id: event.toolCallId, action, input: event.input, content: event.content, details,
      resident: resident ? { status: resident.status, pid: resident.pid, spawnId: resident.spawnId } : undefined });
  });
  pi.on("session_shutdown", () => {
    setAgentHost(undefined);
    childProcess.spawn = originalSpawn;
    syncBuiltinESMExports();
    record({ kind: "shutdown", living: livingAgents().length, results });
  });

  const prompt = scenario === "save" ? `SAVE_KICKOFF ${process.env.PI_LIVE_RESIDENT_SAVED_MARKER}`
    : scenario === "resume" ? "RESUME_KICKOFF: restore your own history and read your capability entry."
      : scenario === "temporary" ? "TEMPORARY_KICKOFF"
        : scenario === "project" ? "PROJECT_KICKOFF"
          : scenario === "tui" ? "TUI_KICKOFF" : undefined;
  // `agent_start` always takes a prompt, so the idle no-prompt start this contract
  // used to cover has no model-facing path; every scenario supplies one.
  const start: ToolArguments = {
    ...(["save", "resume", "project", "steer", "tui"].includes(scenario) ? { identity: name } : { label: name }),
    prompt: prompt ?? "Confirm that you received the initial work.",
    ...(scenario === "temporary" ? {
      tools: [], model: "resident-loopback/contract", instructions: "PINNED_RESIDENT_ROLE: use only the granted tools and return the complete answer.",
    } : {}),
  };
  const call = (id: string, tool: string, args: ToolArguments): AssistantMessage["content"] => [
    { type: "toolCall", id, name: tool, arguments: args },
  ];
  const address = (action: string, prompt?: string): [string, ToolArguments] => {
    assert.ok(handle, "The native start receipt must supply the full exact handle");
    if (action === "stop") return ["agent_stop", { session: handle }];
    assert.ok(prompt, "Input must carry the text the child is to receive");
    const delivery = action === "send" ? "next" : "steer";
    return ["agent_input", { session: handle, prompt, delivery }];
  };
  const addressCall = (id: string, action: string, prompt?: string): AssistantMessage["content"] => {
    const [tool, args] = address(action, prompt);
    return call(id, tool, args);
  };

  async function finishTurn(steered = false): Promise<void> {
    if (steered) {
      const command = writes.find(command => command.streamingBehavior === "steer");
      assert.ok(command?.id, "Interrupt must actually write a steer to native RPC");
      const ack = await waitForFrame(frame => frame.type === "response" && frame.id === command.id);
      assert.equal(ack.success, true);
      assert.equal(ack.data?.disposition, "queued");
      await probe("steered");
    } else await probe("accepted");
    await releaseModel();
    await received;
    await probe("settled");
  }

  let request = 0;
  pi.registerProvider("resident-parent-script", {
    api: "resident-parent-script", baseUrl, apiKey: credential,
    models: [{ id: "scripted", name: "Offline resident caller", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model, _context, options) {
      const index = request++;
      const stream = createAssistantMessageEventStream();
      record({ kind: "parent-request", index });
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: [], stopReason: "pending",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const prepare = async (): Promise<AssistantMessage["content"]> => {
        if (index === 0) return call("resident-start", "agent_start", start);
        if (scenario === "steer") {
          // Every start takes a prompt, so the kickoff turn is already in
          // flight. The mid-turn steer is the real interrupt; the idle and
          // closed refusals are probed once that turn has settled.
          if (index === 1) { await probe("ready"); return addressCall("working-interrupt", "interrupt", "STEER_INPUT"); }
          if (index === 2) { await finishTurn(true); return addressCall("idle-interrupt", "interrupt", "IDLE_REFUSED_INPUT"); }
          if (index === 3) return addressCall("resident-stop", "stop");
          if (index === 4) return addressCall("closed-input", "send", "CLOSED_REFUSED_INPUT");
        } else {
          if (mode === "tui" && index === 1) {
            await probe("accepted");
            return [{ type: "text", text: "LIVE_RESIDENT_ACCEPTED" }];
          }
          const finishIndex = mode === "tui" ? 2 : 1;
          if (index === finishIndex) {
            await finishTurn();
            return addressCall("resident-stop", "stop");
          }
        }
        return [{ type: "text", text: `LIVE_RESIDENT_RESULT_${scenario}` }];
      };
      const run = async (): Promise<void> => {
        let timeout: ReturnType<typeof setTimeout> | undefined;
        let onAbort: (() => void) | undefined;
        try {
          const cancelled = new Promise<never>((_resolve, reject) => {
            timeout = setTimeout(() => reject(new Error("Offline parent script deadline exceeded")), 25_000);
            onAbort = () => reject(new Error("Offline parent script aborted"));
            options?.signal?.addEventListener("abort", onAbort, { once: true });
            if (options?.signal?.aborted) onAbort();
          });
          message.content = await Promise.race([prepare(), cancelled]);
          const reason = message.content.some(part => part.type === "toolCall") ? "toolUse" : "stop";
          message.stopReason = reason;
          stream.push({ type: "start", partial: message });
          stream.push({ type: "done", reason, message });
        } catch (error) {
          message.stopReason = options?.signal?.aborted ? "aborted" : "error";
          message.errorMessage = error instanceof Error ? error.message : String(error);
          record({ kind: "fixture-error", index, error: message.errorMessage });
          stream.push({ type: "error", reason: message.stopReason, error: message });
        } finally {
          clearTimeout(timeout);
          if (onAbort) options?.signal?.removeEventListener("abort", onAbort);
          stream.end();
        }
      };
      void run(); // run consumes every rejection and emits one terminal event.
      return stream;
    },
  });
}
