/**
 * Probe fixture for the delivery-refusal path.
 *
 * Loads the real package under test, runs a scripted local provider so turns
 * settle, and offers the two session replacements that invalidate a captured
 * extension API. `tests/live_delivery_refusal.py` drives it over RPC.
 */
import { appendFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionCommandContext } from "@earendil-works/pi-coding-agent";
import loop from "../src/index.ts";

export default function (pi: ExtensionAPI): void {
  const trace = process.env.LOOP_REFUSAL_TRACE ?? "";
  const log = (data: Record<string, unknown>): void => {
    if (trace) appendFileSync(trace, JSON.stringify({ t: Date.now(), ...data }) + "\n");
  };

  pi.on("session_start", () => log({ kind: "session_start" }));
  pi.on("session_shutdown", () => log({ kind: "session_shutdown" }));
  pi.on("before_agent_start", (event) => {
    const record = event as unknown as { prompt?: unknown; messageType?: unknown };
    log({
      kind: "turn_start",
      prompt: typeof record.prompt === "string" ? record.prompt : null,
      messageType: typeof record.messageType === "string" ? record.messageType : null,
    });
  });

  const replacement = (name: string, act: (ctx: ExtensionCommandContext) => Promise<unknown>): void => {
    pi.registerCommand(name, {
      description: "Invalidate the captured extension API",
      handler: async (_args: string, ctx: ExtensionCommandContext) => {
        log({ kind: "replace:begin", how: name });
        try {
          await act(ctx);
          log({ kind: "replace:done", how: name });
        } catch (error) {
          log({ kind: "replace:error", how: name, message: error instanceof Error ? error.message : String(error) });
        }
      },
    });
  };
  replacement("probe-reload", async (ctx) => await ctx.reload());
  replacement("probe-new-session", async (ctx) => await ctx.newSession());

  // The real package, loaded as an installed user loads it.
  loop(pi);

  let step = 0;
  pi.registerProvider("loop-probe", {
    api: "loop-probe",
    baseUrl: "http://127.0.0.1",
    apiKey: "offline-fixture",
    models: [{
      id: "scripted",
      name: "Refusal probe fixture",
      reasoning: false,
      input: ["text"],
      contextWindow: 200000,
      maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    }],
    streamSimple(model) {
      const index = step;
      step += 1;
      const message: AssistantMessage = {
        role: "assistant",
        api: model.api,
        provider: model.provider,
        model: model.id,
        timestamp: Date.now(),
        content: [{ type: "text", text: "PROBE_TURN_" + index }],
        stopReason: "stop",
        usage: {
          input: 10, output: 5, cacheRead: 0, cacheWrite: 0, totalTokens: 15,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
        },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: "stop", message });
      stream.end();
      return stream;
    },
  });
}