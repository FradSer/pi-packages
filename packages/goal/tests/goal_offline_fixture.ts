/** Offline provider for native CLI and TUI goal verification. No external calls. */
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import goal from "../src/index.ts";
import { appendFileSync, writeFileSync } from "node:fs";
import { stripVTControlCharacters } from "node:util";

export default function (pi: ExtensionAPI): void {
  let index = 0;
  let revised = false;
  let oldEditSent = false;
  let revisionPhase: "none" | "finish-turn" | "pause-continuation" = "none";
  pi.on("session_start", (_event, ctx) => {
    const trace = process.env.PI_GOAL_OFFLINE_WIDGET;
    if (!trace || ctx.mode !== "tui") return;
    const setWidget = ctx.ui.setWidget.bind(ctx.ui);
    ctx.ui.setWidget = (key, content, options) => {
      // Pi overloads setWidget for plain lines and for a component factory, so
      // each branch is forwarded on its own terms instead of one union value.
      if (typeof content !== "function") return setWidget(key, content, options);
      const factory = content;
      if (key !== "goal-status") return setWidget(key, factory, options);
      setWidget(key, (tui, theme) => {
        const component = factory(tui, theme);
        return { ...component, render(width) {
          const lines = component.render(width);
          appendFileSync(trace, JSON.stringify({ placement: options?.placement, lines: lines.map(stripVTControlCharacters) }) + "\n");
          return lines;
        } };
      }, options);
    };
  });
  goal(pi, { runCheck: async () => ({ met: false, report: "Offline acceptance is not yet met." }) });
  pi.registerProvider("goal-offline", {
    api: "goal-offline", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{ id: "scripted", name: "Offline goal fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model, context) {
      const step = index++;
      const setting = context.messages.some(message => message.role === "user" &&
        JSON.stringify(message.content).includes("Revised offline acceptance"));
      const oldEdit = !oldEditSent && context.messages.some(message => message.role === "user" &&
        JSON.stringify(message.content).includes("OLD_TURN_EDIT"));
      if (oldEdit) oldEditSent = true;
      const revise = !oldEdit && step > 0 && setting && !revised;
      const finishRevision = revisionPhase === "finish-turn";
      const pause = !finishRevision && (revisionPhase === "pause-continuation" || step % 2 === 1);
      if (revise) { revised = true; revisionPhase = "finish-turn"; }
      else if (finishRevision) revisionPhase = "pause-continuation";
      else if (revisionPhase === "pause-continuation") revisionPhase = "none";
      const content: AssistantMessage["content"] = step === 0
        ? [{ type: "toolCall", id: "offline-create", name: "create_goal", arguments: {
          objective: "Verify the Pi goal lifecycle offline.", verification_contract: "Thread isolation and pause/resume checks pass." } }]
        : oldEdit
          ? [{ type: "toolCall", id: "offline-old-edit", name: "update_goal", arguments: {
            objective: "Unrelated internal edit from the old turn." } }]
        : revise
          ? [{ type: "toolCall", id: "offline-revise", name: "update_goal", arguments: {
            objective: "Revised offline acceptance: E2E passes.", verification_contract: "Native goal lifecycle passes." } }]
          : pause
          ? [{ type: "toolCall", id: `offline-pause-${step}`, name: "update_goal", arguments: { status: "paused", reason: "Offline checkpoint reached." } }]
          : [{ type: "text", text: "GOAL_OFFLINE_READY" }];
      const message: AssistantMessage = { role: "assistant", api: model.api, provider: model.provider, model: model.id,
        timestamp: Date.now(), content, stopReason: content[0]?.type === "toolCall" ? "toolUse" : "stop",
        usage: { input: 10, output: 5, cacheRead: 0, cacheWrite: 0, totalTokens: 15,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
      const stream = createAssistantMessageEventStream();
      stream.push({ type: "start", partial: message });
      const finish = () => {
        stream.push({ type: "done", reason: message.stopReason as "stop" | "toolUse", message });
        stream.end();
      };
      // Keep the revised active state visible to the native terminal renderer.
      if (oldEdit) {
        const trace = process.env.PI_GOAL_OFFLINE_TRACE;
        if (trace) writeFileSync(trace, "OLD_EDIT_STREAMING");
        setTimeout(finish, 1500);
      } else if (finishRevision) setTimeout(finish, 200);
      else finish();
      return stream;
    },
  });
}
