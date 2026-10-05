/** Real Pi v1 runtime fixture for the matt-pocock contract matrix.
 *
 * The agent loop, schema validation, state persistence and extension events are
 * native Pi. The model transport is deterministic and local; the compact
 * probe may provide a deterministic session_before_compact summary so the
 * native compaction boundary is testable without a remote summarizer.
 */
import assert from "node:assert/strict";
import { appendFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage, type ToolCall } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import mattPocock from "../src/index.ts";

type ScriptedCall = Pick<ToolCall, "name" | "arguments">;
type Evidence = Record<string, unknown>;

export default function (pi: ExtensionAPI): void {
  const evidencePath = process.env.PI_RUNTIME_EVIDENCE;
  const scriptText = process.env.PI_RUNTIME_CALLS;
  assert.ok(evidencePath && scriptText, "The runtime matrix requires isolated evidence and call paths");
  const calls = JSON.parse(scriptText) as ScriptedCall[];
  const processId = process.pid;
  const record = (value: Evidence): void => appendFileSync(evidencePath, JSON.stringify({ pid: processId, ...value }) + "\n");
  const activeTools = (): string[] => typeof pi.getActiveTools === "function" ? pi.getActiveTools().sort() : [];
  const toolNames = (): string[] => typeof pi.getAllTools === "function" ? pi.getAllTools().map(tool => tool.name).sort() : [];
  let appendCount = 0;

  const observed: ExtensionAPI = {
    ...pi,
    sendMessage(message, options) {
      if (message.customType === "matt-pocock-procedure") {
        const content = typeof message.content === "string" ? message.content : JSON.stringify(message.content);
        record({ kind: "procedure", details: message.details, display: message.display, options,
          contentBytes: content.length, hasProcedureHeading: content.includes("# Matt Pocock workflow procedure") });
      }
      pi.sendMessage(message, options);
    },
    appendEntry(type, data) {
      appendCount += 1;
      record({ kind: "append", type, data });
      pi.appendEntry(type, data);
    },
  };

  mattPocock(observed);
  // The matrix drives this through Pi's command router so session_tree is
  // emitted by the real AgentSession, rather than by calling an extension
  // handler directly. It navigates to the first user message on the branch.
  pi.registerCommand("runtime-tree", {
    description: "Test-only native tree navigation",
    handler: async (args, ctx) => {
      const branch = ctx.sessionManager.getBranch();
      const entries = ctx.sessionManager.getEntries();
      const activeState = [...entries].reverse().find(candidate => candidate.type === "custom"
        && candidate.customType === "matt-pocock-workflow"
        && typeof candidate.data === "object" && candidate.data !== null
        && (candidate.data as { status?: unknown }).status === "active");
      const entry = args.trim() === "active" ? activeState
        : branch.find(candidate => candidate.type === "message" && candidate.message.role === "user");
      record({ kind: "tree_command", requested: args.trim() || "back",
        branchEntries: branch.map(candidate => candidate.type), target: entry?.id,
        targetType: entry?.type, allEntryCount: entries.length });
      if (entry) await ctx.navigateTree(entry.id);
    },
  });

  pi.on("session_start", (_event, ctx) => record({
    kind: "session_start", mode: ctx.mode, reason: _event.reason,
    tools: toolNames(), activeTools: activeTools(), branchEntries: ctx.sessionManager.getBranch().map(entry => entry.type),
  }));
  pi.on("session_tree", (_event, ctx) => record({
    kind: "session_tree", activeTools: activeTools(), leaf: ctx.sessionManager.getLeafId(),
    oldLeaf: _event.oldLeafId, newLeaf: _event.newLeafId,
  }));
  pi.on("session_compact", (_event, ctx) => record({
    kind: "session_compact", activeTools: activeTools(), branchEntries: ctx.sessionManager.getBranch().map(entry => entry.type),
  }));
  pi.on("agent_end", () => record({ kind: "agent_end" }));
  pi.on("tool_execution_end", event => record({
    kind: "tool_result", tool: event.toolName, isError: event.isError,
    details: event.result.details, activeTools: activeTools(), appendCount,
  }));
  pi.on("session_compact_failed", event => record({ kind: "session_compact_failed", reason: event.reason,
    errorMessage: event.errorMessage, aborted: event.aborted, fromExtension: event.fromExtension }));
  if (process.env.PI_RUNTIME_COMPACTION_STUB === "1") {
    pi.on("session_before_compact", event => {
      record({ kind: "session_before_compact", reason: event.reason,
        firstKeptEntryId: event.preparation.firstKeptEntryId, tokensBefore: event.preparation.tokensBefore });
      return { compaction: {
        summary: "Preserve the complete Matt Pocock procedure source and active workflow state.",
        firstKeptEntryId: event.preparation.firstKeptEntryId,
        tokensBefore: event.preparation.tokensBefore,
        details: { procedureSourcePreserved: true },
      } };
    });
  }
  pi.registerProvider("matt-pocock-runtime-matrix", {
    api: "matt-pocock-runtime-matrix",
    baseUrl: "http://127.0.0.1",
    apiKey: process.env.PI_RUNTIME_AUTH,
    models: [{ id: "deterministic", name: "Matt Pocock runtime matrix", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model, context) {
      const resultCount = Math.max(0,
        context.messages.filter(message => message.role === "toolResult").length
          - Number(process.env.PI_RUNTIME_RESULT_OFFSET ?? 0));
      const call = calls[resultCount];
      const procedureMessages = context.messages.flatMap(message => {
        const content = "content" in message
          ? typeof message.content === "string" ? message.content : JSON.stringify(message.content)
          : "";
        return content.includes("# Matt Pocock workflow procedure") ? [content] : [];
      });
      record({ kind: "model_context", toolResults: resultCount,
        procedureSourceCount: procedureMessages.length,
        procedureSourceBytes: procedureMessages.reduce((total, message) => total + message.length, 0),
        procedureSourceIds: [...new Set(procedureMessages.flatMap(message =>
          [...message.replaceAll('\\"', '"').matchAll(/<procedure-source id="([^"]+)"/g)].map(match => match[1])))],
        procedureSourceComplete: procedureMessages.some(message => message.includes("## Workflow state contract")) });
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id,
          timestamp: 1_700_000_000_000 + resultCount, content: call
          ? [{ type: "toolCall", id: `runtime-${resultCount}`, name: call.name, arguments: call.arguments }]
          : [{ type: "text", text: "MP_RUNTIME_READY" }],
        stopReason: call ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: call ? "toolUse" : "stop", message });
      stream.end(message);
      return stream;
    },
  });
}
