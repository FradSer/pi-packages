// Offline Pi CLI fixture: the real impeccable procedure row, scripted model responses.
import assert from "node:assert/strict";
import { appendFileSync } from "node:fs";
import { stripVTControlCharacters } from "node:util";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { registerImpeccable } from "../src/index.ts";
import { resolver } from "../src/resolver.ts";
import { loadTriggers } from "../src/routing.ts";

export default function (pi: ExtensionAPI): void {
  const snapshots = process.env.PI_IMPECCABLE_LIVE_SNAPSHOTS;
  assert.ok(snapshots, "The live fixture requires an isolated snapshot path");
  registerImpeccable({
    ...pi,
    registerMessageRenderer(customType, renderer) {
      pi.registerMessageRenderer(customType, (message, options, theme) => {
        const component = renderer(message, options, theme);
        if (!component) return component;
        return {
          invalidate: () => component.invalidate(),
          render(width) {
            const lines = component.render(width);
            appendFileSync(snapshots, JSON.stringify({
              kind: "procedure", customType, details: message.details,
              expanded: options.expanded, width,
              lines: lines.map(stripVTControlCharacters), raw: lines,
            }) + "\n");
            return lines;
          },
        };
      });
    },
  }, resolver, loadTriggers());

  pi.registerProvider("procedure-row-fixture", {
    api: "procedure-row-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_IMPECCABLE_LIVE_AUTH,
    models: [{ id: "deterministic", name: "Procedure row fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: [{ type: "text", text: "IM_ROW_LIVE_READY" }],
        stopReason: "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: "stop", message });
      stream.end();
      return stream;
    },
  });
}