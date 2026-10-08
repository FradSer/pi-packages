/**
 * Lifecycle handlers.
 *
 * The order of these is the runtime. `turn_start` opens a turn and its stop
 * guard; `context` injects goal state at the tail of the request in a form the
 * provider's implicit prefix cache can reuse; `tool_call` enforces the stop
 * guard and refuses a stale checkpoint; `agent_before_settle` decides whether
 * the loop itself can close the goal before another run is authorized.
 */

import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { detailField } from "@fradser/pi-kit";
import { GOAL_PROCEDURE_ENTRY } from "./procedure.ts";
import type { GoalCore } from "./core.ts";
import { clearDashboard, refreshDashboard } from "./dashboard.ts";
import { LiveContext } from "./live-context.ts";
import { goalCapabilityNote, goalPromptParts, isCheckpointMessage } from "./prompt.ts";
import { allowsAfterStop, refreshGoalToolSurface } from "./tools.ts";

/** Assistant usage as this package reads it. `detailField` is pi-kit's
 * accessor, which keeps a shape change from turning into a crash here. */
function turnTokens(usage: unknown): number {
  const total = detailField<number>(usage, "totalTokens");
  if (typeof total === "number") return total;
  const input = detailField<number>(usage, "input");
  const output = detailField<number>(usage, "output");
  const read = detailField<number>(usage, "cacheRead");
  return (input ?? 0) + (output ?? 0) + (read ?? 0);
}

/** A user message carrying runtime state. It is marked as a runtime reminder
 * rather than something the user said, because the model must be able to tell
 * the two apart when deciding what it was asked to do. */
export function registerGoalEvents(core: GoalCore): void {
  const { pi } = core;
  // One retention per process, keyed by session: a second session in the same
  // process must never re-insert a note into the wrong transcript.
  const live = new LiveContext();
  const chargedMessages = new WeakSet<object>();
  const runGoals = new Map<string, string | undefined>();
  const messageGoals = new WeakMap<object, { goalId?: string; threadId: string }>();
  const toolArgs = new Map<string, unknown>();
  pi.on("tool_execution_start", event => { toolArgs.set(event.toolCallId, event.args); });
  let usageSequence = 0;
  let elapsedCharged = 0;
  const sessionKey = (ctx: ExtensionContext): string =>
    `${ctx.sessionManager.getSessionId() || "unidentified"}:${ctx.model?.provider ?? ""}/${ctx.model?.id ?? ""}`;

  pi.on("session_start", async (_event, ctx) => {
    core.restore(ctx);
    refreshGoalToolSurface(core, ctx);
    refreshDashboard(core, ctx);
  });

  pi.on("session_tree", async (_event, ctx) => {
    // Branch navigation changes what this session has focused, so anything read
    // from disk and any armed continuation both belong to the branch we left.
    core.scheduler.shutdown();
    core.restore(ctx);
    refreshGoalToolSurface(core, ctx);
    refreshDashboard(core, ctx);
  });

  pi.on("session_shutdown", async (_event, ctx) => {
    live.reset(sessionKey(ctx));
    core.shutdown();
    clearDashboard(ctx);
  });

  pi.on("before_agent_start", async (event) => {
    core.acceptGoalSetting(event.prompt);
  });

  pi.on("agent_start", async (_event, ctx) => {
    core.bindUi(ctx);
    core.beginRun();
    const goal = core.goal;
    runGoals.set(ctx.sessionManager.getSessionId(), goal && core.canChargeGoal(goal) ? goal.id : undefined);
    core.scheduler.begin();
  });

  pi.on("turn_start", async (_event, ctx) => {
    core.advanceTurnSeq();
    elapsedCharged = 0;
    // A new turn means a new claim. Without this a refused checkpoint from the
    // previous turn would keep acting on the new one.
    refreshDashboard(core, ctx);
  });

  /**
   * Inject goal state at the tail of the request, prefix-stably.
   *
   * Three things can be said here and exactly one is: the active goal's state, a
   * note that goals are open but none is focused, or — when nothing is in flight —
   * the capability note. `LiveContext` re-inserts whichever was already sent at
   * the index it was sent from, so this request begins with exactly the previous
   * one. Without that, the first injection point would end the provider's implicit
   * prefix cache and every later request would re-read the whole session.
   */
  pi.on("context", async (event, ctx) => {
    const goal = core.goal;
    let content: string | undefined;
    if (goal) {
      const { state, counters } = goalPromptParts(goal, core.settings(ctx), { unmet: core.currentUnmet() });
      content = `${state}\n\n${counters}`;
    } else {
      // With no goal in flight the model still needs to know it can make one,
      // and to know when that is warranted. Without this the only way to start a
      // goal is typing /goal, which misses the case where the model should
      // recognise by itself that a request is worth making durable.
      content = goalCapabilityNote(false);
    }
    const applied = live.apply(sessionKey(ctx), event.messages, content, Date.now());
    return { messages: applied.messages };
  });

  pi.on("tool_call", async (event, _ctx) => {
    if (core.scheduler.isDenied()) {
      return { block: true, reason: "This turn was triggered by a checkpoint that no longer matches the goal. Stop and report; use /goal resume to continue." };
    }
    const stopped = core.currentTurnStoppedGoalId();
    if (stopped !== null && !allowsAfterStop(event.toolName)) {
      return {
        block: true,
        reason: `The goal was already given its disposition earlier in this turn. Do not call more tools; end the turn with a brief summary.`,
      };
    }
    return;
  });

  pi.on("tool_execution_end", async (event) => {
    core.noteWork(event.toolName, !event.isError, event.result?.details, event.result?.content, toolArgs.get(event.toolCallId));
    toolArgs.delete(event.toolCallId);
  });

  pi.on("message_start", async (event, ctx) => {
    const message = event.message as { details?: unknown; role?: unknown; customType?: unknown; content?: unknown };
    if (message.role === "assistant") {
      const threadId = ctx.sessionManager.getSessionId();
      messageGoals.set(message, { threadId, goalId: runGoals.get(threadId) });
    }
    // Custom-message delivery never fires before_agent_start, so the /goal
    // procedure row accepts here instead. The match is the same stored prompt
    // against the delivered body; a mismatch still drops the intent silently.
    if (message.customType === GOAL_PROCEDURE_ENTRY && typeof message.content === "string") {
      core.acceptGoalSetting(message.content);
    }
    if (!isCheckpointMessage(message)) {
      if (message.role !== "user") return;
      // Real user work supersedes an armed continuation: the user is here, so
      // the goal waits rather than interrupting.
      const goal = core.goal;
      if (goal) core.scheduler.takeover(goal);
      return;
    }
    const accepted = core.scheduler.acceptCheckpoint(
      message.details as { goalId?: unknown; generation?: unknown; dispatchId?: unknown },
    );
    if (!accepted.ok) core.notify(ctx, `Goal checkpoint refused: ${accepted.message}`, "warning");
  });

  pi.on("message_end", async (event, ctx) => {
    const message = event.message as { role?: unknown; usage?: unknown; content?: { type?: string; text?: string }[]; errorMessage?: unknown };
    if (message.role !== "assistant" || chargedMessages.has(message)) return;
    const threadId = ctx.sessionManager.getSessionId();
    const attribution = messageGoals.get(message) ?? { threadId, goalId: runGoals.get(threadId) };
    const focused = core.goal;
    if (!attribution.goalId && focused?.threadId && focused.threadId !== attribution.threadId) { chargedMessages.add(message); return; }
    const goal = attribution.goalId ? core.store.readGoalFromDisk(attribution.goalId) : focused;
    // A released Goal's late usage must never migrate into the replacement.
    if (attribution.goalId && !goal) { chargedMessages.add(message); return; }
    if (!goal) { chargedMessages.add(message); core.recordCreationUsage(turnTokens(message.usage), attribution.threadId); return; }
    if (!attribution.goalId && !core.canChargeGoal(goal)) return;
    chargedMessages.add(message);
    const elapsed = core.currentTurnSeconds();
    core.chargeUsage(ctx, goal, ++usageSequence, turnTokens(message.usage), elapsed - elapsedCharged, !!attribution.goalId);
    elapsedCharged = elapsed;
    refreshGoalToolSurface(core, ctx);
    refreshDashboard(core, ctx);
  });

  // Settling authorizes continuation only after successful effective work.
  pi.on("agent_before_settle", async (event, ctx) => {
    core.bindUi(ctx);
    // Unconsumed setting intent must not activate an unrelated later edit.
    core.cancelGoalActivation();
    const failed = event.outcome !== "completed";
    const goal = core.goal;
    if (!goal) {
      refreshDashboard(core, ctx);
      return;
    }
    core.scheduler.settled(core.goal, core.settings(ctx), !failed, core.performedWork());
    if (failed) {
      refreshGoalToolSurface(core, ctx);
      refreshDashboard(core, ctx);
      return;
    }
    const continuation = core.boundaryContinuation();
    refreshGoalToolSurface(core, ctx);
    refreshDashboard(core, ctx);
    return continuation;
  });

  pi.on("agent_settled", async (_event, ctx) => {
    refreshGoalToolSurface(core, ctx);
    refreshDashboard(core, ctx);
  });
}
