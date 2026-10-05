/** Offline native Pi fixture: real agent tool, RPC child and above-editor widget. */
import assert from "node:assert/strict";
import { appendFileSync } from "node:fs";
import { stripVTControlCharacters } from "node:util";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import { createCodemodeExtension, type AgentToolResult, type ExtensionAPI, type ExtensionContext, type MessageRenderer, type ToolDefinition } from "@earendil-works/pi-coding-agent";
import { visibleWidth } from "@earendil-works/pi-tui";
import piSubagents from "../packages/subagents/src/extension.ts";
import { INTENT_TOOL_NAMES } from "../packages/subagents/src/intent-tools.ts";
import { getAgent, livingAgents, updateAgent } from "../packages/subagents/src/roster.ts";

const INTENT_TOOLS = INTENT_TOOL_NAMES.filter(name => name !== "agent_list");

export default function (pi: ExtensionAPI): void {
  // This fixture verifies the supported legacy model interface.
  const nativeGetFlag = pi.getFlag.bind(pi);
  const snapshots = process.env.PI_AGENT_USAGE_SNAPSHOTS;
  assert.ok(snapshots, "An isolated snapshot path is required");
  const record = (value: unknown) => appendFileSync(snapshots, JSON.stringify(value) + "\n");
  let mode: ExtensionContext["mode"];
  let resolveResult!: () => void;
  const received = new Promise<void>(resolve => { resolveResult = resolve; });
  let results = 0;
  const interruptExpansion = process.env.PI_AGENT_USAGE_CASE === "interrupt-expansion";
  const steeringText = process.env.PI_AGENT_STEER_TEXT;
  const cancelStartupWait = process.env.PI_AGENT_USAGE_CASE === "cancel-startup-wait";
  const codemodeLifecycle = process.env.PI_AGENT_USAGE_CASE === "codemode-lifecycle";
  const inspectStopped = process.env.PI_AGENT_USAGE_CASE === "stopped-inspect" || cancelStartupWait || codemodeLifecycle;
  const injectedDiagnostic = process.env.PI_AGENT_INSPECT_DIAGNOSTIC;
  let stoppedSnapshot: string | undefined;
  let handle: string | undefined;
  // A temporary label is display only, so the roster name comes from the exact
  // route the start receipt returned rather than from what the model asked for.
  const childName = (): string => {
    const route = handle ?? "";
    assert.ok(route.startsWith("session:"), "A start receipt must precede any roster read");
    return route.slice("session:".length).split(":")[0]!;
  };

  pi.on("session_start", (_event, ctx) => {
    mode = ctx.mode;
    if (mode !== "tui") return;
    const setWidget = ctx.ui.setWidget.bind(ctx.ui);
    ctx.ui.setWidget = (key, factory, options) => {
      if (typeof factory !== "function") {
        setWidget(key, factory, options);
        return;
      }
      if (key !== "subagents-activity") {
        setWidget(key, factory, options);
        return;
      }
      record({ kind: "mount", placement: options?.placement });
      setWidget(key, (tui, theme) => {
        const component = factory(tui, theme);
        return {
          ...component,
          render(width) {
            const lines = component.render(width);
            record({ kind: "widget", width, lines: lines.map(stripVTControlCharacters),
              bounded: lines.every(line => !line.includes("\n") && visibleWidth(line) <= width) });
            return lines;
          },
          dispose() {
            record({ kind: "clear" });
            component.dispose?.();
          },
        };
      }, options);
    };
  });

  const observedPi: ExtensionAPI = {
    ...pi,
    registerMessageRenderer<T>(customType: string, renderer: MessageRenderer<T>) {
      pi.registerMessageRenderer<T>(customType, (message, state, theme) => {
        const component = renderer(message, state, theme);
        if (!component || customType !== "subagents-session-result") return component;
        return {
          invalidate: () => component.invalidate(),
          render(width) {
            const lines = component.render(width);
            record({ kind: "result-row", width, expanded: state.expanded,
              lines: lines.map(stripVTControlCharacters),
              bounded: lines.every(line => !line.includes("\n") && visibleWidth(line) <= width) });
            return lines;
          },
        };
      });
    },
    registerTool<TParams extends ToolDefinition["parameters"], TDetails, TState>(tool: ToolDefinition<TParams, TDetails, TState>) {
      const renderResult = tool.renderResult;
      if (!tool.name.startsWith("agent_") || !renderResult) { pi.registerTool(tool); return; }
      pi.registerTool<TParams, TDetails, TState>({
        ...tool,
        async execute(toolCallId, args, signal, onUpdate, ctx): Promise<AgentToolResult<TDetails>> {
          if (!cancelStartupWait || tool.name !== "agent_start") {
            return tool.execute(toolCallId, args, signal, onUpdate, ctx);
          }
          // Dispatch a real native RPC start, then cancel only the caller's wait
          // before its asynchronous ACK. The original resident must still answer.
          const controller = new AbortController();
          const pending = tool.execute(toolCallId, args, controller.signal, onUpdate, ctx);
          controller.abort();
          const result = await pending;
          const details = result.details as { disposition?: string; dispatched?: boolean; controlOutcome?: string; session?: string; pendingIntent?: string };
          // A cancelled wait over a dispatched start is uncertain, not refused:
          // the child exists and only the acknowledgement was lost.
          assert.equal(details.disposition, "uncertain");
          assert.equal(details.dispatched, true);
          // Recorded rather than asserted: the pending-intent field is the runtime's
          // own vocabulary, and a fixture must not fail a run over its absence.
          assert.equal(details.controlOutcome, "uncertain");
          // A cancelled start reports no route: the receipt is uncertain, not a
          // handle the caller may act on.
          record({ kind: "cancelled-native-start", details, living: livingAgents().length });
          return result;
        },
        renderResult(result, state, theme, context) {
          const component = renderResult(result, state, theme, context);
          return {
            invalidate: () => component.invalidate(),
            render(width) {
              const lines = component.render(width);
              const action = (result.details as { operation?: string } | undefined)?.operation;
              record({ kind: "agent-row", action, width, expanded: state.expanded, partial: state.isPartial,
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
        assert.equal(results, 1, "One invocation returns one answer");
        const details = message.details as { text: string; turn: number; session: string };
        assert.equal(details.text, process.env.PI_AGENT_RESULT_TEXT);
        record({ kind: "result", content: message.content, details: message.details, options });
        resolveResult();
      }
      pi.sendMessage(message, options);
    },
  };
  piSubagents(observedPi);
  if (codemodeLifecycle) {
    createCodemodeExtension({ models: false })(pi);
    pi.on("session_start", () => pi.setActiveTools([...pi.getActiveTools(), ...INTENT_TOOLS, "codemode"]));
  }
  pi.on("tool_result", event => {
    if (event.toolName === "codemode") {
      assert.equal(event.isError, false, JSON.stringify(event.content));
      record({ kind: "codemode-receipt", isError: event.isError });
      return;
    }
    if (!event.toolName.startsWith("agent_")) return;
    const details = event.details as { ok?: boolean; operation?: string; session?: string };
    if (details.operation === "agent_start") handle = details.session;
    if (inspectStopped && details.operation === "agent_stop") {
      const child = getAgent(childName());
      assert.equal(child?.status, "stopped");
      // Invented retained diagnostic probes the readback budget; the native child
      // already closed successfully. This does not simulate a provider failure.
      if (injectedDiagnostic) updateAgent(childName(), { error: injectedDiagnostic });
      stoppedSnapshot = JSON.stringify(getAgent(childName()));
    }
    if (inspectStopped && details.operation === "agent_inspect") {
      // Recorded, never asserted: an assertion here would throw inside a Pi event
      // handler and swallow this receipt with it, leaving the suite to read a
      // missing result instead of a failed one.
      const child = getAgent(childName());
      record({ kind: "inspect-preservation", unchanged: JSON.stringify(child) === stoppedSnapshot,
        rawErrorLength: child?.error?.length ?? 0,
        errorRetained: injectedDiagnostic ? child?.error === injectedDiagnostic : true });
    }
    record({ kind: "receipt", content: event.content, details: event.details,
      structuredContent: event.structuredContent, isError: event.isError });
  });
  pi.on("session_shutdown", () => {
    record({ kind: "shutdown", living: livingAgents().length, results });
  });

  let request = 0;
  pi.registerProvider("subagents-parent-fixture", {
    api: "subagents-parent-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_AGENT_USAGE_AUTH,
    models: [{ id: "scripted", name: "Offline subagent caller", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const index = request++;
      let content: AssistantMessage["content"];
      const startArgs = { label: "calculator", prompt: "计算 1+1，只回复数字。", tools: [], model: "subagents-local-fixture/arithmetic" };
      if (index === 0) {
        content = codemodeLifecycle
          ? [{ type: "toolCall", id: "arithmetic-code", name: "codemode", arguments: { code:
            `const receipt = await tools.agent_start(${JSON.stringify(startArgs)}); if (typeof receipt !== "object" || receipt.ok !== true || !receipt.session) throw new Error("Structured start is required"); text(receipt);` } }]
          : [{ type: "toolCall", id: "arithmetic-start", name: "agent_start", arguments: startArgs }];
      } else if (interruptExpansion && index === 1) {
        assert.ok(handle && steeringText);
        assert.ok(["starting", "working"].includes(getAgent(childName())?.status ?? ""),
          "Accepted startup can be steered before its first progress frame");
        content = [{ type: "toolCall", id: "expand-steering", name: "agent_input",
          arguments: { session: handle, prompt: steeringText, delivery: "steer" } }];
      } else if (cancelStartupWait && index === 2) {
        // A cancelled start returned no route, so there is nothing to stop or
        // inspect. The roster is the only evidence that the dispatched child
        // really exists, and that is exactly what this case has to prove.
        content = [{ type: "toolCall", id: "cancelled-list", name: "agent_list", arguments: {} }];
      } else if (inspectStopped && !cancelStartupWait && (index === 2 || index === 3)) {
        assert.ok(handle, "The original exact handle is required");
        const control = index === 2 ? "agent_stop" : "agent_inspect";
        const argumentsForControl = { session: handle };
        content = codemodeLifecycle
          ? [{ type: "toolCall", id: `after-result-code-${index}`, name: "codemode", arguments: { code:
            `const receipt = await tools.${control}(${JSON.stringify(argumentsForControl)}); if (typeof receipt !== "object" || receipt.ok !== true || receipt.state !== "stopped") throw new Error("Structured stopped facts are required"); text(receipt);` } }]
          : [{ type: "toolCall", id: `after-result-${index}`, name: control, arguments: argumentsForControl }];
      } else {
        content = [{ type: "text", text: interruptExpansion && index === 2 ? "NATIVE_INTERRUPT_READY"
          : index === 1 ? "DELEGATED_INPUT_ACCEPTED"
          : inspectStopped ? "NATIVE_STOPPED_INSPECT_OK" : "SUBAGENT_RESULT_2" }];
      }
      const hasTool = content.some(part => part.type === "toolCall");
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content, stopReason: hasTool ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      const emit = () => {
        stream.push({ type: "start", partial: message });
        stream.push({ type: "done", reason: hasTool ? "toolUse" : "stop", message });
        stream.end();
      };
      // Print exits with its parent run. The offline transport keeps that run
      // alive until the callback, without a caller-side sleep or status poll.
      if (mode !== "tui" && index === 1) void received.then(emit);
      else emit();
      return stream;
    },
  });
}
