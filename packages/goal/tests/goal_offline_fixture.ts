/** Offline provider for native CLI and TUI goal verification. No external calls. */
import { createAssistantMessageEventStream, type AssistantMessage } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import goal from "../src/index.ts";
import { GoalStore } from "../src/store.ts";
import { GOAL_FOCUS_ENTRY } from "../src/core.ts";
import { appendFileSync, writeFileSync } from "node:fs";
import { stripVTControlCharacters } from "node:util";

export default function (pi: ExtensionAPI): void {
  let index = 0;
  let revised = false;
  let oldEditSent = false;
  let revisionPhase: "none" | "finish-turn" | "pause-continuation" = "none";
  let liveStep = 0;
  let supersedeStep = 0;
  pi.on("session_start", (_event, ctx) => {
    const trace = process.env.PI_GOAL_OFFLINE_WIDGET;
    // Every mount, key and placement only. The live-rows probe reads it to
    // prove research mounts nothing above the editor.
    const mounts = process.env.PI_GOAL_OFFLINE_MOUNTS;
    if ((!trace && !mounts) || ctx.mode !== "tui") return;
    const setWidget = ctx.ui.setWidget.bind(ctx.ui);
    ctx.ui.setWidget = (key, content, options) => {
      if (mounts) {
        appendFileSync(mounts, JSON.stringify({
          key,
          placement: (options as { placement?: string } | undefined)?.placement,
          cleared: content === undefined,
        }) + "\n");
      }
      // Pi overloads setWidget for plain lines and for a component factory, so
      // each branch is forwarded on its own terms instead of one union value.
      if (typeof content !== "function") return setWidget(key, content, options);
      if (key !== "goal-status" || !trace) return setWidget(key, content, options);
      const watchedFile = trace;
      const factory = content;
      setWidget(key, (tui, theme) => {
        const component = factory(tui, theme);
        return { ...component, render(width) {
          const lines = component.render(width);
          appendFileSync(watchedFile, JSON.stringify({ key, placement: options?.placement, lines: lines.map(stripVTControlCharacters) }) + "\n");
          return lines;
        } };
      }, options);
    };
  });
  const goalOptions: { runCheck: () => Promise<{ met: boolean; report: string }>; runResearch?: unknown } = {
    runCheck: async () => ({ met: false, report: "Offline acceptance is not yet met." }),
  };
  // Live-rows probe only: a scripted progressive child that reports its tool
  // and its raw command through the real onUpdate chain, so the real transcript
  // row is observed inside a real pi TUI session.
  if (process.env.PI_GOAL_OFFLINE_RESEARCH === "progressive") {
    goalOptions.runResearch = async (options: { focus: string; onUpdate?: (update: { activeTool?: string; activity?: string }) => void }) => {
      for (const step of [
        { activeTool: "read", activity: "**reading** `export.ts`" },
        { activeTool: "grep", activity: "grep -rn csv . | head -20" },
        { activeTool: undefined, activity: "export.ts builds the CSV" },
      ]) {
        if (typeof options.onUpdate === "function") options.onUpdate(step);
        await new Promise((resolve) => setTimeout(resolve, 350));
      }
      return { findings: "# Findings\n\n- **export.ts** writes the CSV; the tests live beside it." };
    };
  }
  // Supersede probe only: an existing, focused goal, so that one /goal request
  // arrives when this thread already has a goal.
  if (process.env.PI_GOAL_OFFLINE_SEED_EXISTING === "1") {
    pi.on("session_start", (_event, ctx) => {
      const store = new GoalStore({ projectRoot: ctx.cwd });
      store.create({
        id: "goal_existing_probe",
        owner: ctx.sessionManager.getSessionId() || "probe-session",
        objective: "Probe the live goal rows.",
        contract: "The supersede probe passes.",
      });
      // Paused, so the loop does not start running it and the /goal request
      // arrives with the session idle.
      store.apply({
        expectedGoalId: "goal_existing_probe",
        mutate: (draft) => ({ ...draft, status: "paused", autoContinue: false }),
      });
      pi.appendEntry(GOAL_FOCUS_ENTRY, { version: 1, focusedGoalId: "goal_existing_probe", reason: "created" });
    });
  }
  goal(pi, goalOptions as never);
  pi.registerProvider("goal-offline", {
    api: "goal-offline", baseUrl: "http://127.0.0.1", apiKey: "offline-fixture",
    models: [{ id: "scripted", name: "Offline goal fixture", reasoning: false, input: ["text"],
      contextWindow: 200000, maxTokens: 4096, cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
    streamSimple(model, context) {
      const step = index++;
      // Supersede probe only: a scripted model calls create_goal with supersedes
      // directly. /goal itself now asks for an in-place revision, so this is the
      // escape hatch for a goal that stopped for good.
      const supersede = process.env.PI_GOAL_OFFLINE_LIVE === "1" && context.messages.some(message => message.role === "user" &&
        JSON.stringify(message.content).includes("PROBE_SUPERSEDE"));
      if (supersede) {
        const carried: AssistantMessage["content"] = supersedeStep === 0
          ? [{ type: "toolCall", id: "offline-supersede-research", name: "research_goal", arguments: { focus: "What does the export path do today?" } }]
          : supersedeStep === 1
            ? [{ type: "toolCall", id: "offline-supersede-create", name: "create_goal", arguments: {
              objective: "Probe the live goal rows, and now also audit the export path.",
              verification_contract: "The supersede probe passes.",
              supersedes: true,
            } }]
            : [{ type: "text", text: "PROBE_SUPERSEDE_READY" }];
        supersedeStep++;
        const supersedeMessage: AssistantMessage = { role: "assistant", api: model.api, provider: model.provider, model: model.id,
          timestamp: Date.now(), content: carried, stopReason: supersedeStep === 3 ? "stop" : "toolUse",
          usage: { input: 10, output: 5, cacheRead: 0, cacheWrite: 0, totalTokens: 15,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
        const supersedeStream = createAssistantMessageEventStream();
        supersedeStream.push({ type: "start", partial: supersedeMessage });
        supersedeStream.push({ type: "done", reason: supersedeStep === 3 ? "stop" : "toolUse", message: supersedeMessage });
        supersedeStream.end();
        return supersedeStream;
      }
      // Live-rows probe only: PROBE_LIVE turns research, then create, then pause.
      const live = process.env.PI_GOAL_OFFLINE_LIVE === "1" && context.messages.some(message => message.role === "user" &&
        JSON.stringify(message.content).includes("PROBE_LIVE"));
      if (live) {
        const liveContent: AssistantMessage["content"] = liveStep === 0
          ? [{ type: "toolCall", id: "offline-live-research", name: "research_goal", arguments: { focus: "Where is the CSV export written?" } }]
          : liveStep === 1
            ? [{ type: "toolCall", id: "offline-live-create", name: "create_goal", arguments: {
              objective: "Probe the live goal rows.", verification_contract: "The live probe passes." } }]
            : [{ type: "toolCall", id: `offline-live-pause-${liveStep}`, name: "update_goal", arguments: { status: "paused", reason: "Live probe reached its checkpoint." } }];
        liveStep++;
        const liveMessage: AssistantMessage = { role: "assistant", api: model.api, provider: model.provider, model: model.id,
          timestamp: Date.now(), content: liveContent, stopReason: "toolUse",
          usage: { input: 10, output: 5, cacheRead: 0, cacheWrite: 0, totalTokens: 15,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
        const liveStream = createAssistantMessageEventStream();
        liveStream.push({ type: "start", partial: liveMessage });
        liveStream.push({ type: "done", reason: "toolUse", message: liveMessage });
        liveStream.end();
        return liveStream;
      }
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
