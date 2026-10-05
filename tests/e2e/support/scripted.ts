/**
 * Shared support for the three-package E2E suites.
 *
 * Determinism comes from a scripted provider: Pi's agent loop is real, the tool
 * executions are real, and the only thing replaced is the model, which replays a
 * fixed sequence of tool calls and then reports what the transcript actually
 * contains. So these suites exercise the real registration, schema validation,
 * execution and result paths without credentials, and without asserting anything
 * about how a model would phrase a turn.
 *
 * The report is produced by reading the transcript rather than by having the
 * fixture pre-declare the answer, so a value that reaches an assertion came out of
 * a real tool execution. `pi --print` prints only the final assistant text, which
 * is why the last scripted turn is a report rather than a fixed string.
 */

import { createAssistantMessageEventStream, type AssistantMessage, type JsonObject, type JsonValue, type Message } from "@earendil-works/pi-ai";
import * as nodeFs from "node:fs";
import type { AgentToolResult, ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

/** One turn of the script: a tool call, or the terminal report. */
export type ScriptedTurn =
  | { tool: string; args: JsonObject }
  | { report: true };

export interface ScriptedOptions {
  /** Provider id, unique per suite so two suites cannot collide in one run. */
  provider: string;
  /** The tool that reports the tool surface the host actually registered. */
  probe: string;
  turns: ScriptedTurn[];
  /** Defaults to {@link resolveFromResults}; override only to test the harness. */
  resolve?: (value: unknown, results: unknown[]) => unknown;
  /** When set, the live tool list is written here on the first probe call.
   *  Used by the install-wiring check, which needs the surface a real configured
   *  install produced rather than the surface this harness chose. */
  dumpPath?: string;
}

/** Prefixed to the final assistant text so the harness can find the report. */
export const E2E_REPORT = "E2E_REPORT";
/** Marker printed by a passing suite. A run that produced no report failed. */
export const E2E_OK = "E2E_OK";

/** The shape the harness parses back out of the transcript. */
export interface E2EReport {
  tools: string[];
  activeTools?: string[];
  calls: Array<{ name: string; isError: boolean; text: string; details: unknown }>;
}

/**
 * Resolve `$prev.path` against the tool results so far, newest first.
 *
 * Lives here rather than in a fixture because it is harness machinery, not
 * scenario data: a script names the field it wants and the harness finds the call
 * that produced it, rather than every fixture re-implementing a fallback walk. A
 * script also usually reads a list between creating a record and acting on it, so
 * the value being referenced is rarely in the immediately preceding result.
 */
export function resolveFromResults(value: unknown, results: unknown[]): unknown {
  if (typeof value !== "string" || !value.startsWith("$prev")) return value;
  const path = value.slice("$prev".length).replace(/^\./, "");
  for (const details of [...results].reverse()) {
    let current: unknown = details;
    let found = true;
    for (const key of path.split(".").filter(Boolean)) {
      if (current === null || typeof current !== "object") { found = false; break; }
      current = (current as Record<string, unknown>)[key];
    }
    if (found && current !== undefined) return current;
  }
  return undefined;
}

/** Resolvers cross an unknown tool-details boundary; prove JSON before calling Pi. */
function jsonValue(value: unknown): JsonValue {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (Array.isArray(value)) return value.map(jsonValue);
  if (typeof value === "object" && value !== null
    && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null)) {
    const object: JsonObject = {};
    for (const [key, entry] of Object.entries(value)) object[key] = jsonValue(entry);
    return object;
  }
  throw new TypeError("A scripted tool argument must resolve to a JSON value.");
}

/** Substitute every placeholder, including nested objects and array entries. */
function mapValues(args: JsonObject, resolve: (value: unknown) => unknown): JsonObject {
  const map = (value: JsonValue): JsonValue => {
    if (Array.isArray(value)) return value.map(map);
    if (value !== null && typeof value === "object") {
      const out: JsonObject = {};
      for (const [key, entry] of Object.entries(value)) out[key] = map(entry);
      return out;
    }
    return jsonValue(resolve(value));
  };
  const out: JsonObject = {};
  for (const [key, value] of Object.entries(args)) out[key] = map(value);
  return out;
}

function reportFrom(messages: Message[], probe: string): E2EReport {
  const calls: E2EReport["calls"] = [];
  for (const message of messages) {
    if (message.role !== "toolResult") continue;
    const text = message.content
      .map((block) => ("text" in block && typeof block.text === "string" ? block.text : ""))
      .join("\n");
    calls.push({
      name: message.toolName,
      isError: message.isError === true,
      text,
      details: message.details ?? null,
    });
  }
  // The surface is read from the live tool list at the moment the probe ran, not
  // reconstructed here, so a tool Pi refused to register cannot appear.
  const probeCall = calls.find((call) => call.name === probe);
  const candidate = probeCall && probeCall.details && typeof probeCall.details === "object"
    && "tools" in probeCall.details ? probeCall.details.tools : undefined;
  const tools = Array.isArray(candidate)
    ? candidate.filter((name): name is string => typeof name === "string")
    : [];
  return { tools, calls };
}

/**
 * Register the scripted provider and the surface probe.
 *
 * The probe exists so a suite can assert what the *host* registered rather than
 * what a test believes it registered: it reads the live tool list through the
 * extension API, which is the only thing that distinguishes "my call to
 * registerTool worked" from "Pi accepted my tool".
 */
export function installScriptedProvider(pi: ExtensionAPI, options: ScriptedOptions): void {
  const { provider, probe, turns, dumpPath } = options;
  const resolve = options.resolve ?? resolveFromResults;
  let surface: string[] = [];
  let activeSurface: string[] = [];

  pi.registerTool({
    name: probe,
    label: "Surface probe",
    description: "Report the tools this host actually registered.",
    parameters: Type.Object({ probe: Type.Optional(Type.String()) }, { additionalProperties: false }),
    renderShell: "self",
    renderCall: () => undefined as never,
    async execute(_id, params): Promise<AgentToolResult> {
      const asked = params.probe;
      if (asked === "reports") {
        const seen = jsonValue((globalThis as Record<string, unknown>)["live-child-report"] ?? null);
        return {
          content: [{ type: "text", text: JSON.stringify({ reports: seen }) }],
          details: { reports: seen },
        };
      }
      if (asked === "wait") {
        return {
          content: [{ type: "text", text: JSON.stringify({ waited: true }) }],
          details: { waited: true },
        };
      }
      surface = typeof pi.getAllTools === "function"
        ? pi.getAllTools().map((tool) => tool.name).sort()
        : [];
      activeSurface = typeof pi.getActiveTools === "function" ? pi.getActiveTools().sort() : [];
      if (dumpPath && surface.length > 0) {
        // Synchronous on purpose: the host may tear the extension module down as
        // soon as the turn settles, and a pending write would be lost exactly when
        // the answer was the thing being looked for.
        const { writeFileSync } = nodeFs;
        writeFileSync(dumpPath, JSON.stringify(surface));
      }
      return {
        content: [{ type: "text", text: JSON.stringify({ tools: surface }) }],
        details: { tools: surface, activeTools: activeSurface },
      };
    },
  });

  pi.registerProvider(provider, {
    api: provider,
    baseUrl: "http://127.0.0.1",
    apiKey: process.env.PI_E2E_AUTH,
    models: [{
      id: "deterministic",
      name: "E2E scripted provider",
      reasoning: false,
      input: ["text"],
      contextWindow: 200000,
      maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    }],
    streamSimple(model, context) {
      // Progress is derived from the transcript rather than a counter, so a retry or
      // a refused call cannot desynchronise the script from what actually ran.
      // One scripted turn per tool result, so the script advances by exactly one
      // step per execution — including a step the host refused, which still
      // produces a result. Indexing rather than searching is what makes a refusal
      // move the script on instead of retrying the same call forever.
      const script = turns.filter((turn): turn is Extract<ScriptedTurn, { tool: string }> => "tool" in turn);
      const results = context.messages.filter((message: Message) => message.role === "toolResult");
      const pending = script[results.length];
      const useTool = pending !== undefined;
      const seen = results.map((result) => result.details ?? null);
      const args = useTool && pending !== undefined
        ? mapValues(pending.args, (value) => resolve(value, seen))
        : {};
      const content: AssistantMessage["content"] = useTool && pending !== undefined
        ? [{ type: "toolCall" as const, id: `e2e-${results.length}`, name: pending.tool, arguments: args }]
        : [{ type: "text" as const, text: `${E2E_REPORT} ${JSON.stringify(finalise(context.messages))}` }];
      const message: AssistantMessage = {
        role: "assistant",
        api: model.api,
        provider: model.provider,
        model: model.id,
        timestamp: 1_700_000_000_000 + results.length,
        content: [],
        stopReason: "pending",
        usage: {
          input: 0, output: 0, cacheRead: 0, cacheWrite: 0,
          totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
        },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      for (const block of content) {
        const contentIndex = message.content.length;
        if (block.type === "toolCall") {
          const toolCall = { ...block, arguments: {} };
          message.content.push(toolCall);
          stream.push({ type: "toolcall_start", contentIndex, partial: message });
          toolCall.arguments = block.arguments;
          stream.push({ type: "toolcall_delta", contentIndex, delta: JSON.stringify(block.arguments), partial: message });
          stream.push({ type: "toolcall_end", contentIndex, toolCall, partial: message });
        } else if (block.type === "text") {
          const text = { ...block, text: "" };
          message.content.push(text);
          stream.push({ type: "text_start", contentIndex, partial: message });
          text.text = block.text;
          stream.push({ type: "text_delta", contentIndex, delta: block.text, partial: message });
          stream.push({ type: "text_end", contentIndex, content: block.text, partial: message });
        }
      }
      const reason = useTool ? "toolUse" : "stop";
      message.stopReason = reason;
      stream.push({ type: "done", reason, message });
      stream.end(message);
      return stream;
    },
  });

  /** Merge the probe's live reading into the transcript-derived calls. */
  function finalise(messages: Message[]): E2EReport {
    const derived = reportFrom(messages, probe);
    return { tools: surface.length > 0 ? surface : derived.tools, activeTools: activeSurface, calls: derived.calls };
  }
}
