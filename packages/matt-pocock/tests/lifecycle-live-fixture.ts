// Offline Pi CLI fixture: real workflow execution and renderers, scripted model responses.
import assert from "node:assert/strict";
import { appendFileSync } from "node:fs";
import { stripVTControlCharacters } from "node:util";
import { createAssistantMessageEventStream, type AssistantMessage, type ToolCall } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import mattPocock from "../src/index.ts";

export default function (pi: ExtensionAPI): void {
  const snapshots = process.env.PI_PHASE_LIVE_SNAPSHOTS;
  assert.ok(snapshots, "The live fixture requires an isolated snapshot path");
  mattPocock({
    ...pi,
    registerTool(tool) {
      const renderResult = tool.renderResult;
      assert.ok(renderResult);
      pi.registerTool({
        ...tool,
        renderResult(result, options, theme, context) {
          const component = renderResult(result, options, theme, context);
          return {
            invalidate: () => component.invalidate(),
            render(width) {
              const lines = component.render(width);
              appendFileSync(snapshots, JSON.stringify({
                kind: "render", tool: tool.name, details: result.details,
                expanded: options.expanded, width, lines: lines.map(stripVTControlCharacters),
              }) + "\n");
              return lines;
            },
          };
        },
      });
    },
    registerMessageRenderer(customType, renderer) {
      pi.registerMessageRenderer(customType, (message, options, theme) => {
        const component = renderer(message, options, theme);
        if (!component) return component;
        return {
          invalidate: () => component.invalidate(),
          render(width) {
            const lines = component.render(width);
            appendFileSync(snapshots, JSON.stringify({
              kind: "message", customType, details: message.details,
              expanded: options.expanded, width, lines: lines.map(stripVTControlCharacters), raw: lines,
            }) + "\n");
            return lines;
          },
        };
      });
    },
  });
  const calls: Pick<ToolCall, "name" | "arguments">[] = [
    { name: "matt_pocock_workflow", arguments: { mode: "workflow", route: "hard-bug" } },
    { name: "matt_pocock_active", arguments: { action: "complete" } },
    { name: "matt_pocock_workflow", arguments: { mode: "workflow", route: "hard-bug" } },
    { name: "matt_pocock_active", arguments: { action: "transition", target: "implement" } },
    { name: "matt_pocock_active", arguments: { action: "transition", target: "code-review" } },
    { name: "matt_pocock_active", arguments: { action: "complete" } },
    { name: "matt_pocock_workflow", arguments: { mode: "workflow", route: "architecture" } },
    { name: "matt_pocock_active", arguments: { action: "transition", target: "implement" } },
    { name: "matt_pocock_active", arguments: { action: "cancel", reason: "Offline fixture finished" } },
  ];
  let index = 0;
  pi.registerProvider("phase-lifecycle-fixture", {
    api: "phase-lifecycle-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_PHASE_LIVE_AUTH,
    models: [{ id: "deterministic", name: "Phase lifecycle fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const call = calls[index++];
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: call ? [{ type: "toolCall", id: `phase-${index}`, ...call }]
          : [{ type: "text", text: "MP_PHASE_LIVE_READY" }],
        stopReason: call ? "toolUse" : "stop",
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: call ? "toolUse" : "stop", message });
      stream.end();
      return stream;
    },
  });
  pi.on("tool_execution_end", (event) => {
    appendFileSync(snapshots, JSON.stringify({ kind: "result", tool: event.toolName, ...event.result, isError: event.isError }) + "\n");
  });
}
