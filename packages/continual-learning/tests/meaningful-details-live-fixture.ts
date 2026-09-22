/** Offline real-Pi fixture for registered entry renderers; no commands or network requests. */
import assert from "node:assert/strict";
import { appendFileSync } from "node:fs";
import { stripVTControlCharacters } from "node:util";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { EntryRenderer, ExtensionAPI, MessageRenderer } from "@earendil-works/pi-coding-agent";
import { visibleWidth } from "@earendil-works/pi-tui";
import registerGuardrails from "../extensions/guardrails.ts";
import registerOutputChecks from "../extensions/output-checks.ts";
import registerHarnessGuidance from "../extensions/harness-guidance.ts";
import { HARNESS_GUIDANCE_ENTRY_TYPE } from "../extensions/harness-guidance-planner.ts";
import registerMemory from "../extensions/inject-memory.ts";
import { buildLearningReceipt } from "../extensions/learning-efficiency.ts";

export default function (pi: ExtensionAPI): void {
  const snapshots = process.env.PI_DETAILS_LIVE_SNAPSHOTS;
  assert.ok(snapshots, "An isolated renderer snapshot path is required");
  const registered: ExtensionAPI = {
    ...pi,
    registerMessageRenderer<T>(customType: string, renderer: MessageRenderer<T>) {
      pi.registerMessageRenderer<T>(customType, (message, options, theme) => {
        const component = renderer(message, options, theme);
        if (!component) return component;
        const render = component.render.bind(component);
        component.render = (width) => {
          const lines = render(width);
          assert.ok(lines.every((line) => visibleWidth(line) <= width));
          appendFileSync(snapshots, JSON.stringify({ kind: "render", customType, data: message.details,
            expanded: options.expanded, width, lines: lines.map(stripVTControlCharacters) }) + "\n");
          return lines;
        };
        return component;
      });
    },
    registerEntryRenderer<T>(customType: string, renderer: EntryRenderer<T>) {
      pi.registerEntryRenderer<T>(customType, (entry, options, theme) => {
        const component = renderer(entry, options, theme);
        if (!component) return component;
        const render = component.render.bind(component);
        component.render = (width) => {
          const lines = render(width);
          assert.ok(lines.every((line) => visibleWidth(line) <= width));
          appendFileSync(snapshots, JSON.stringify({
            kind: "render", customType, data: entry.data, expanded: options.expanded, width,
            lines: lines.map(stripVTControlCharacters),
          }) + "\n");
          return lines;
        };
        return component;
      });
    },
  };
  registerGuardrails(registered);
  registerOutputChecks(registered);
  registerHarnessGuidance(registered);
  registerMemory(registered);
  pi.on("session_start", (_event, ctx) => {
    const select = ctx.ui.select.bind(ctx.ui);
    ctx.ui.select = async (...args) => {
      appendFileSync(snapshots, JSON.stringify({ kind: "menu", title: args[0], options: args[1] }) + "\n");
      return select(...args);
    };
    const notify = ctx.ui.notify.bind(ctx.ui);
    ctx.ui.notify = (message, type) => {
      appendFileSync(snapshots, JSON.stringify({ kind: "notification", message, type }) + "\n");
      notify(message, type);
    };
    const receipt = buildLearningReceipt("automatic", { memory: false, harness: false, agents: true, reasons: ["instruction-evidence"] },
      [{ phase: "agents", attempt: 0, outcome: "applied", durationMs: 10, operations: 1 }]);
    pi.sendMessage({ customType: "continual-learning-result", content: "Learning result", display: true, details: receipt });
    appendFileSync(snapshots, JSON.stringify({ kind: "entry", customType: "continual-learning-result", data: receipt }) + "\n");
    const entries = [
      { customType: "harness-event", data: {
        kind: "policy-matched", policy: "approved-report", action: "confirm", outcome: "allowed once", tool: "write",
        reason: "Preserve the approved report and its documented release constraints while keeping every original evidence reference. Final policy marker.",
        source: "project.local", file: "/fixture/.pi/harness.local.json",
      } },
      { customType: "harness-check", data: {
        kind: "harness-check", phase: "artifact", status: "unsupported", policy: "regular-artifact", path: "reports/final.txt",
        detail: "The artifact cannot be inspected safely because its final path is not a regular workspace file. Final check marker.",
      } },
      { customType: HARNESS_GUIDANCE_ENTRY_TYPE, data: {
        kind: "skill-rule", skill: "review", ruleId: "review-evidence", source: "project", file: "/fixture/.pi/harness.json",
        prompt: Array.from({ length: 65 }, (_, index) => `guidance-${index + 1} Preserve review evidence for this exact task, including the complete approval reference.`).join("\n"),
      } },
    ];
    for (const entry of entries) {
      pi.appendEntry(entry.customType, entry.data);
      appendFileSync(snapshots, JSON.stringify({ kind: "entry", ...entry }) + "\n");
    }
  });
  pi.registerProvider("meaningful-details-fixture", {
    api: "meaningful-details-fixture", baseUrl: "http://127.0.0.1", apiKey: process.env.PI_DETAILS_LIVE_AUTH,
    models: [{ id: "deterministic", name: "Meaningful details fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(),
        content: [{ type: "text", text: "CL_DETAILS_LIVE_READY" }], stopReason: "stop",
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
