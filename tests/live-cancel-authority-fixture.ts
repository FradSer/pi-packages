/** Native Pi/real RPC children; gated host confirmations are invented fault probes. */
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { appendFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { AgentToolResult, ExtensionAPI, ToolDefinition } from "@earendil-works/pi-coding-agent";
import piSubagents from "../packages/subagents/src/extension.ts";
import { executeChildIntent, setAgentHost, type AgentHost } from "../packages/subagents/src/child-execution.ts";
import { getAgent, livingAgents, observeAgentRoster, registerAgent, updateAgent } from "../packages/subagents/src/roster.ts";
import { exactSessionRoute, parseExactSessionRoute } from "../packages/subagents/src/session-route.ts";
import { deliverResidentPrompt, deliverResidentSteer, spawnResident, terminateAgent } from "../packages/subagents/src/spawner.ts";

export default function (pi: ExtensionAPI): void {
  // This fixture verifies the supported legacy model interface.
  const nativeGetFlag = pi.getFlag.bind(pi);
  const snapshots = process.env.PI_AGENT_USAGE_SNAPSHOTS;
  const scenario = process.env.PI_CANCEL_AUTHORITY_CASE;
  assert.ok(snapshots && ["stop-pending", "forged-successor", "late-control-failure", "reentrant-successor"].includes(scenario ?? ""));
  const record = (value: unknown): void => appendFileSync(snapshots, JSON.stringify(value) + "\n");
  let releaseOriginal!: (handle: string) => void;
  const originalConfirmation = new Promise<string>(resolve => { releaseOriginal = resolve; });
  let releaseFailure!: () => void;
  const failureGate = new Promise<void>(resolve => { releaseFailure = resolve; });
  let failureObserved!: () => void;
  const lateFailure = new Promise<void>(resolve => { failureObserved = resolve; });
  const hostStops: Array<{ owner: string; session: string }> = [];
  const children: Array<{ pid: number; session: string }> = [];
  type AckEntry = { accepted: boolean; settled: Promise<void>; resolve: () => void };
  const acks = new Map<string, AckEntry>();
  /** One entry per exact handle; `settled` lands after the native acknowledgement. */
  const ackFor = (session: string): AckEntry => {
    const known = acks.get(session);
    if (known) return known;
    let resolve!: () => void;
    const settled = new Promise<void>(done => { resolve = done; });
    const entry: AckEntry = { accepted: false, settled, resolve };
    acks.set(session, entry);
    return entry;
  };
  let originalHandle: string | undefined;
  let successorHandle: string | undefined;
  /** The roster name behind one exact handle; the model names no child itself. */
  const rosterName = (session: string): string => {
    const route = parseExactSessionRoute(session);
    assert.ok(route, `An exact handle must name one incarnation: ${session}`);
    return route.name;
  };

  const makeHost = (owner: "original" | "successor"): AgentHost => ({
    async start(request) {
      const spawnId = randomUUID();
      const session = exactSessionRoute(request.name, spawnId);
      const isCurrent = (): boolean => getAgent(request.name)?.spawnId === spawnId;
      assert.equal(registerAgent({ name: request.name, role: request.name, spawnId, pid: 0, status: "starting",
        scope: "session", standalone: false, tools: [], createdAt: Date.now(), updatedAt: Date.now() }).ok, true);
      const spawned = spawnResident({ agentName: request.name, cwd: process.cwd(), tools: [], session: "none",
        model: "subagents-local-fixture/arithmetic", onUpdate(update) {
          if (isCurrent() && update.finalResponse && !getAgent(request.name)?.leaderRequestedEnd) updateAgent(request.name, { status: "idle" });
        }, onExit() { if (isCurrent()) updateAgent(request.name, { status: "stopped" }); },
        onError(error) { if (isCurrent()) updateAgent(request.name, { error: error.message }); } });
      assert.ok(!("error" in spawned), "Native spawn is required");
      children.push({ pid: spawned.pid, session });
      assert.ok(spawned.pid > 1);
      updateAgent(request.name, { pid: spawned.pid });
      const ready = await spawned.readiness;
      record({ kind: "native-readiness", owner, session, accepted: ready });
      // No kickoff prompt reaches this child, so no turn is in flight and the
      // hosted input sequence is genuinely settled. Without that, a next input
      // would wait in the reservation queue instead of reaching native RPC.
      if (ready && isCurrent() && !getAgent(request.name)?.leaderRequestedEnd) updateAgent(request.name, { status: "idle", sequenceEnded: true });
      if (owner === "original" && scenario !== "late-control-failure") {
        // Delayed/wrong host return is synthetic; the child and closure are real.
        return { ok: true, session: await originalConfirmation };
      }
      return ready ? { ok: true, session } : { ok: false, error: "Native readiness not accepted" };
    },
    async send(name, spawnId, input) {
      assert.equal(getAgent(name)?.spawnId, spawnId);
      updateAgent(name, { status: "starting" });
      const accepted = await deliverResidentPrompt(name, input);
      const ack = ackFor(exactSessionRoute(name, spawnId));
      ack.accepted = accepted;
      record({ kind: "native-input-ack", accepted, session: exactSessionRoute(name, spawnId) });
      ack.resolve();
      if (scenario === "late-control-failure") {
        // Probe a host returning a late error AFTER real native input dispatch.
        // This is not a claim the native positive ACK itself was negative.
        await failureGate;
        return { ok: false, error: "LATE_NATIVE_CONTROL_FAILURE: host confirmation fault probe" };
      }
      return accepted ? { ok: true } : { ok: false, error: "Native prompt rejected" };
    },
    // The intent input path reserves before dispatch, so a published host has
    // to state its reservation policy exactly as a team runtime does.
    authorizeInput(): { ok: true } {
      return { ok: true };
    },
    async interrupt(name, spawnId, input) {
      assert.equal(getAgent(name)?.spawnId, spawnId);
      return await deliverResidentSteer(name, input) ? { ok: true } : { ok: false, error: "Native steer rejected" };
    },
    async stop(name, spawnId) {
      assert.equal(getAgent(name)?.spawnId, spawnId);
      hostStops.push({ owner, session: exactSessionRoute(name, spawnId) });
      const outcome = await terminateAgent(name);
      record({ kind: "native-close", owner, session: exactSessionRoute(name, spawnId), outcome: outcome.outcome });
      return outcome.outcome === "unconfirmed" ? { ok: false, error: "Native closure unconfirmed" } : { ok: true };
    },
  });
  const original = makeHost("original"), successor = makeHost("successor");
  let nestedSuccessor: ReturnType<typeof executeChildIntent> | undefined;
  const reentrant: AgentHost = { ...original, start(request) {
    // Synchronous original reservation/replacement is invented to exercise the
    // pre-bind seam. Only the successor is a real native RPC child here.
    const spawnId = randomUUID();
    registerAgent({ name: request.name, role: request.name, spawnId, pid: 0, status: "starting",
      scope: "session", standalone: false, tools: [], createdAt: Date.now(), updatedAt: Date.now() });
    updateAgent(request.name, { status: "stopped" });
    setAgentHost(successor);
    nestedSuccessor = executeChildIntent({ operation: "start", name: request.name, tools: [] }, { cwd: process.cwd() });
    record({ kind: "synthetic-reentrant-start", retiredSession: exactSessionRoute(request.name, spawnId) });
    return originalConfirmation.then(session => ({ ok: true as const, session }));
  } };
  /** The intent family mapped to the executor operation it performs. */
  const INTENT_OPERATIONS: Record<string, string> = {
    agent_start: "start", agent_input: "input", agent_stop: "stop", agent_list: "list",
  };
  /** A roster read is a page of the whole roster, so it takes no session. */
  const ROSTER_READ: { callTool: string; args: Record<string, never> } = { callTool: "agent_list", args: {} };

const observedPi: ExtensionAPI = {
    ...pi,
    registerTool<TParams extends ToolDefinition["parameters"], TDetails, TState>(tool: ToolDefinition<TParams, TDetails, TState>) {
      if (!INTENT_OPERATIONS[tool.name]) { pi.registerTool(tool); return; }
      pi.registerTool<TParams, TDetails, TState>({ ...tool,
        async execute(id, args, signal, update, ctx): Promise<AgentToolResult<TDetails>> {
          const operation = INTENT_OPERATIONS[tool.name] === "input"
            ? ((args as { delivery?: string }).delivery === "steer" ? "steer" : "input")
            : INTENT_OPERATIONS[tool.name];
          const cancel = scenario === "late-control-failure" ? operation === "input"
            : operation === "start" && successorHandle === undefined && originalHandle === undefined;
          if (!cancel) return tool.execute(id, args, signal, update, ctx);
          const controller = new AbortController();
          const pending = tool.execute(id, args, controller.signal, update, ctx);
          controller.abort();
          const result = await pending;
          // The intent receipt names the cancelled wait in its own vocabulary:
          // the code, the disposition, and the exact handle the runtime still owns.
          const data = result.details as { code?: string; disposition?: string; session?: string; dispatched?: boolean };
          assert.equal(data.code, "cancelled", JSON.stringify(data));
          assert.equal(data.disposition, "uncertain", JSON.stringify(data));
          if (operation === "input") {
            // A cancelled input leaves its reservation with the runtime, so its
            // receipt carries no dispatch flag. The real native dispatch is the
            // correlated acknowledgement this host recorded for that handle.
            assert.ok(data.session, JSON.stringify(data));
            const ack = ackFor(data.session);
            await ack.settled;
            assert.equal(ack.accepted, true, "The cancelled input never reached the native control stream");
          } else {
            assert.equal(data.dispatched, true, JSON.stringify(data));
            if (scenario === "reentrant-successor") {
              assert.equal(data.session, undefined, "The cancelled original start cannot claim the successor handle");
            } else assert.ok(data.session);
          }
          record({ kind: "cancelled-native-control", operation: tool.name, data });
          return result;
        },
      });
    },
  };
  piSubagents(observedPi);
  pi.on("session_start", () => setAgentHost(scenario === "reentrant-successor" ? reentrant : original));
  const flush = (): Promise<void> => new Promise(resolve => setImmediate(resolve));
  const stopObserving = observeAgentRoster(() => {
    if (originalHandle && getAgent(rosterName(originalHandle))?.error?.includes("LATE_NATIVE_CONTROL_FAILURE")) failureObserved();
  });
  pi.on("tool_result", async event => {
    if (!INTENT_OPERATIONS[event.toolName]) return;
    const data = event.details as { operation: string; disposition?: string; ok?: boolean; session?: string; sessions?: Array<{ session?: string; error?: string; status?: string }> };
    const operation = data.operation;
    record({ kind: "receipt", details: data, isError: event.isError, structuredContent: event.structuredContent });
    // ADR-0008 left no inspection operation: the roster is the surviving read,
    // so every ownership claim below is read back from its page.
    const rosterEntry = (session: string) => data.sessions?.find((entry) => entry.session === session);
    if (operation === "agent_start" && !originalHandle) originalHandle = data.session;
    else if (operation === "agent_start" && scenario === "forged-successor") {
      successorHandle = data.session;assert.ok(successorHandle);
      const before = JSON.stringify(getAgent(rosterName(successorHandle)));
      releaseOriginal(successorHandle);
      await flush();
      assert.equal(JSON.stringify(getAgent(rosterName(successorHandle))), before, "Late original host cannot change the successor");
      record({ kind: "successor-preserved", session: successorHandle });
    }
    if (operation === "agent_stop" && scenario === "stop-pending") {
      assert.ok(originalHandle);releaseOriginal(originalHandle);await flush();
      assert.equal(getAgent(rosterName(originalHandle))?.status, "stopped");
      record({ kind: "late-confirmation-refused", status: "stopped" });
    }
    if (operation === "agent_stop" && scenario === "forged-successor" && !successorHandle) setAgentHost(successor);
    if (operation === "agent_input" && scenario === "late-control-failure") releaseFailure();
    if (operation === "agent_list") {
      if (scenario === "late-control-failure") {
        assert.ok(originalHandle);
        const retained = rosterEntry(originalHandle);
        assert.ok(retained?.error?.includes("LATE_NATIVE_CONTROL_FAILURE"), JSON.stringify(data.sessions));
        record({ kind: "late-failure-readback", status: getAgent(rosterName(originalHandle))?.status });
      } else if (scenario === "stop-pending") {
        assert.ok(originalHandle);
        const retained = rosterEntry(originalHandle);
        assert.ok(retained, JSON.stringify(data.sessions));
        assert.equal(retained.status, "stopped", "the roster shows the closed incarnation as stopped");
        record({ kind: "roster-readback", session: originalHandle, status: retained.status });
      } else if (successorHandle) {
        const retained = rosterEntry(successorHandle);
        assert.ok(retained, JSON.stringify(data.sessions));
        assert.equal(retained.session, successorHandle, "the roster still addresses the successor's exact handle");
        record({ kind: "roster-readback", session: successorHandle, status: retained.status });
      }
    }
  });
  pi.on("session_shutdown", () => {
    stopObserving();setAgentHost(undefined);
    record({ kind: "shutdown", living: livingAgents().length, hostStops, children });
  });

  let request = 0;
  pi.registerProvider("subagents-parent-fixture", {
    api: "subagents-parent-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_AGENT_USAGE_AUTH,
    models: [{ id: "scripted", name: "Native cancellation authority", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const index = request++;
      if (scenario === "reentrant-successor") {
        const stream = createAssistantMessageEventStream();
        const emit = async (): Promise<void> => {
          let args: { label?: string; session?: string; prompt?: string; delivery?: string } | undefined;
          let callTool = "agent_start";
          // The label is display only; the roster name is minted per start.
          const authorityStart = { label: "authority", prompt: "Hold the authority case open until the leader stops it" };
          if (index === 0) args = authorityStart;
          if (index === 1) {
            assert.ok(nestedSuccessor);
            const started = await nestedSuccessor;
            assert.equal(started.structuredContent.ok, true, started.content[0].text);
            assert.equal(started.structuredContent.operation, "start");
            assert.ok(started.structuredContent.session);
            successorHandle = started.structuredContent.session;
            const before = JSON.stringify(getAgent(rosterName(successorHandle)));
            releaseOriginal(successorHandle);await flush();
            assert.equal(JSON.stringify(getAgent(rosterName(successorHandle))), before);
            record({ kind: "reentrant-owner-preserved", session: successorHandle });
            args = ROSTER_READ.args; callTool = ROSTER_READ.callTool;
          }
          if (index === 2) { args = { session: successorHandle }; callTool = "agent_stop"; }
          const message: AssistantMessage = { role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
            content: args ? [{ type: "toolCall", id: `reentrant-${index}`, name: callTool, arguments: args }]
              : [{ type: "text", text: "NATIVE_AUTHORITY_DONE" }], stopReason: args ? "toolUse" : "stop",
            usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
              cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
          stream.push({ type: "start", partial: message });
          stream.push({ type: "done", reason: args ? "toolUse" : "stop", message });stream.end();
        };
        void emit().catch(error => {
          const failure: AssistantMessage = { role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
            content: [], stopReason: "error", errorMessage: error instanceof Error ? error.message : String(error),
            usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
              cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
          stream.push({ type: "error", reason: "error", error: failure });stream.end();
        });
        return stream;
      }
      let args: { label?: string; session?: string; prompt?: string; delivery?: string } | undefined;
      let callTool = "agent_start";
      const authorityStart = { label: "authority", prompt: "Hold the authority case open until the leader stops it" };
      if (index === 0) args = authorityStart;
      else if (scenario === "stop-pending") {
        if (index === 1) { args = { session: originalHandle }; callTool = "agent_stop"; }
        if (index === 2) { args = ROSTER_READ.args; callTool = ROSTER_READ.callTool; }
      } else if (scenario === "forged-successor") {
        // The original exact handle closes first, so the second start is a real
        // successor and the late original confirmation can only forge its route.
        if (index === 1) { args = { session: originalHandle }; callTool = "agent_stop"; }
        if (index === 2) args = authorityStart;
        if (index === 3) { args = { session: successorHandle }; callTool = "agent_stop"; }
        if (index === 4) { args = ROSTER_READ.args; callTool = ROSTER_READ.callTool; }
      } else {
        if (index === 1) { args = { session: originalHandle, prompt: "Hold the native model until explicitly stopped", delivery: "next" }; callTool = "agent_input"; }
        if (index === 2) { args = ROSTER_READ.args; callTool = ROSTER_READ.callTool; }
        if (index === 3) { args = { session: originalHandle }; callTool = "agent_stop"; }
      }
      const message: AssistantMessage = { role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: args ? [{ type: "toolCall", id: `authority-${index}`, name: callTool, arguments: args }]
          : [{ type: "text", text: "NATIVE_AUTHORITY_DONE" }], stopReason: args ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
      const stream = createAssistantMessageEventStream();
      const emit = (): void => {
        stream.push({ type: "start", partial: message });
        stream.push({ type: "done", reason: args ? "toolUse" : "stop", message });stream.end();
      };
      if (scenario === "late-control-failure" && index === 2) void lateFailure.then(emit);
      else emit();
      return stream;
    },
  });
}
