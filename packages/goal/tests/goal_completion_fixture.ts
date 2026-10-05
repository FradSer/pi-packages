/** Native offline completion and three-refusal fixture. Never calls a remote provider. */
import { appendFileSync } from "node:fs";
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import goal from "../src/index.ts";

export default function (pi: ExtensionAPI): void {
  const mode = process.env.PI_GOAL_COMPLETION_CASE ?? "complete";
  const trace = process.env.PI_GOAL_COMPLETION_TRACE;
  let index = 0;
  pi.on("session_start", (_event, ctx) => {
    if (!trace || ctx.mode !== "tui") return;
    const setWidget = ctx.ui.setWidget.bind(ctx.ui);
    ctx.ui.setWidget = (key, content, options) => {
      if (key === "goal-status") {
        const mounted = typeof content === "function";
        const placement = mounted && options ? options.placement : undefined;
        appendFileSync(trace, JSON.stringify({ kind: "widget", mounted, placement }) + "\n");
      }
      // Two Pi overloads: plain lines, or a component factory.
      if (typeof content === "function") return setWidget(key, content, options);
      return setWidget(key, content, options);
    };
  });
  goal(pi, {
    runCheck: async options => {
      if (trace) appendFileSync(trace, JSON.stringify({ kind: "check", observations: options.evidence?.observations }) + "\n");
      if (mode !== "complete") return { met: false, report: "Required independent review evidence is missing." };
      const found = options.evidence?.observations.some(item => item.source === "tool" && item.label === "bash" &&
        item.outcome === "success" && item.output.includes("NATIVE_COMPLETION_E2E_PASS"));
      return { met: !!found, report: found ? "The executed native check satisfies the completion contract." : "Actual executed output is missing." };
    },
  });
  pi.registerProvider("goal-completion-offline", {
    api: "goal-completion-offline", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{ id: "scripted", name: "Offline completion fixture", reasoning: false, input: ["text"], contextWindow: 200000, maxTokens: 4096,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model) {
      const step = index++;
      if (trace) appendFileSync(trace, JSON.stringify({ kind: "provider", step }) + "\n");
      const content: AssistantMessage["content"] = step === 0
        ? [{ type: "toolCall", id: "create-completion", name: "create_goal", arguments: {
          objective: "Verify native completion.", verification_contract: mode === "complete"
            ? "The executed bash check outputs NATIVE_COMPLETION_E2E_PASS." : "Independent review evidence is present." } }]
        : mode === "complete" && step === 1
          ? [{ type: "toolCall", id: "verify-completion", name: "bash", arguments: { command: "printf 'NATIVE_COMPLETION_E2E_PASS\\n'" } }]
          : mode === "empty" || step > 3
            ? [{ type: "text", text: "No work remains to attempt." }]
            : [{ type: "toolCall", id: `request-completion-${step}`, name: "update_goal", arguments: { status: "complete", completion_summary: "Please check the observed results." } }];
      const message: AssistantMessage = {
        role: "assistant", api: model.api, provider: model.provider, model: model.id, timestamp: Date.now(), content,
        stopReason: content[0]?.type === "toolCall" ? "toolUse" : "stop",
        usage: { input: 10, output: 5, cacheRead: 0, cacheWrite: 0, totalTokens: 15,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
      };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      stream.push({ type: "done", reason: message.stopReason as "toolUse" | "stop", message });
      stream.end();
      return stream;
    },
  });
}
