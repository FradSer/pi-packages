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

import { createAssistantMessageEventStream, type AssistantMessage, type Message } from "@earendil-works/pi-ai";
import * as nodeFs from "node:fs";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** One turn of the script: a tool call, or the terminal report. */
export type ScriptedTurn =
  | { tool: string; args: Record<string, unknown> }
  | { report: true };

export interface ScriptedOptions {
  /** Provider id, unique per suite so two suites cannot collide in one run. */
  provider: string;
  /** The tool that reports the tool surface the host actually registered. */
  probe: string;
  turns: ScriptedTurn[];
  /** When set, the live tool list is written here on the first probe call.
   *  Used by the install-wiring check, which needs the surface a real configured
   *  install produced rather than the surface this harness chose. */
  dumpPath?: string;
  /** Fills a scripted argument from an earlier tool result, so a task id a create
   *  call returned is the same id a later call acts on. Given every result so far,
   *  because a script usually reads a list in between. */
  resolve?: (value: unknown, results: unknown[]) => unknown;
}

/** Prefixed to the final assistant text so the harness can find the report. */
export const E2E_REPORT = "E2E_REPORT";
/** Marker printed by a passing suite. A run that produced no report failed. */
export const E2E_OK = "E2E_OK";

/** The shape the harness parses back out of the transcript. */
export interface E2EReport {
  tools: string[];
  calls: Array<{ name: string; isError: boolean; text: string; details: unknown }>;
}

/** Substitute a resolved argument for every placeholder in a scripted arg set. */
function mapValues(
  args: Record<string, unknown>,
  resolve: (value: unknown) => unknown,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(args)) {
    out[key] = Array.isArray(value) ? value.map((entry) => resolve(entry)) : resolve(value);
  }
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
  const tools = probeCall && probeCall.details && typeof probeCall.details === "object"
    ? ((probeCall.details as { tools?: unknown }).tools as string[] | undefined) ?? []
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
  const { provider, probe, turns, resolve, dumpPath } = options;
  let surface: string[] = [];
  const observed: E2EReport["calls"] = [];

  pi.registerTool({
    name: probe,
    label: "Surface probe",
    description: "Report the tools this host actually registered.",
    parameters: { type: "object", properties: {}, required: [], additionalProperties: false } as never,
    renderShell: "self",
    renderCall: () => undefined as never,
    execute() {
      surface = typeof pi.getAllTools === "function"
        ? pi.getAllTools().map((tool) => tool.name).sort()
        : [];
      if (dumpPath && surface.length > 0) {
        // Synchronous on purpose: the host may tear the extension module down as
        // soon as the turn settles, and a pending write would be lost exactly when
        // the answer was the thing being looked for.
        const { writeFileSync } = nodeFs;
        writeFileSync(dumpPath, JSON.stringify(surface));
      }
      return {
        content: [{ type: "text", text: JSON.stringify({ tools: surface }) }],
        details: { tools: surface },
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
      const seen = results.map((result) => (result as { details?: unknown }).details ?? null);
      const args = useTool && pending !== undefined
        ? mapValues(pending.args, (value) => resolve?.(value, seen) ?? value)
        : {};
      const content = useTool && pending !== undefined
        ? [{ type: "toolCall" as const, id: `e2e-${results.length}`, name: pending.tool, arguments: args }]
        : [{ type: "text" as const, text: `${E2E_REPORT} ${JSON.stringify(finalise(context.messages))}` }];
      const message: AssistantMessage = {
        role: "assistant",
        api: model.api,
        provider: model.provider,
        model: model.id,
        timestamp: 1_700_000_000_000 + results.length,
        content,
        stopReason: useTool ? "toolUse" : "stop",
        usage: {
          input: 0, output: 0, cacheRead: 0, cacheWrite: 0,
          totalTokens: 0, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
        },
      };
      const stream = createAssistantMessageEventStream();
      void stream.push(message);
      void stream.end(message);
      return stream;
    },
  });

  /** Merge the probe's live reading into the transcript-derived calls. */
  function finalise(messages: Message[]): E2EReport {
    const derived = reportFrom(messages, probe);
    for (const call of derived.calls) {
      if (call.name === probe) observed.push(call);
    }
    return { tools: surface.length > 0 ? surface : derived.tools, calls: derived.calls };
  }
}
