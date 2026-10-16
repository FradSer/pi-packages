/**
 * Offline native fixture for /loop.
 *
 * The real extension is loaded, and a scripted local provider replaces the
 * model. Every run start is written to the trace file, so the test can prove
 * that a scheduled injection arrives as a native user turn.
 */
import { appendFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import loop from "../src/index.ts";

export default function (pi: ExtensionAPI): void {
  const trace = process.env.PI_LOOP_TRACE;
  const log = (data: Record<string, unknown>): void => {
    if (trace) appendFileSync(trace, JSON.stringify(data) + "\n");
  };

  pi.on("session_start", () => log({ kind: "ready" }));
  // `messageType` and `prompt` are Pi 1.2 fields. An older host reports
  // neither, so the record carries whatever the running host provides and the
  // test reads that, instead of failing on a version difference.
  pi.on("before_agent_start", (event) => {
    const record = event as unknown as { messageType?: unknown; prompt?: unknown };
    log({
      kind: "start",
      messageType: typeof record.messageType === "string" ? record.messageType : null,
      prompt: typeof record.prompt === "string" ? record.prompt : null,
    });
  });

  // The real package, including the real /loop command and its renderer.
  loop(pi);

  let step = 0;
  pi.registerProvider("loop-offline", {
    api: "loop-offline",
    baseUrl: "http://127.0.0.1",
    apiKey: "offline-fixture",
    models: [{
      id: "scripted",
      name: "Offline Loop fixture",
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
        content: [{ type: "text", text: "LOOP_TURN_" + index }],
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
