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
import { detailField, notifyPi } from "@fradser/pi-kit";
import type { GoalCore } from "./core.ts";
import { describeUnmet } from "./check.ts";
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
    core.scheduler.begin();
  });

  pi.on("turn_start", async (_event, ctx) => {
    core.advanceTurnSeq();
    elapsedCharged = 0;
    // A new turn means a new claim. Without this a refused checkpoint from the
    // previous turn would keep acting on the new one.
    core.beginTurn();
    core.clearClaim();
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
    core.noteWork(event.toolName, !event.isError, event.result?.details);
  });

  pi.on("message_start", async (event, ctx) => {
    const message = event.message as { details?: unknown; role?: unknown };
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
    if (!accepted.ok) notifyPi(ctx.ui, `Goal checkpoint refused: ${accepted.message}`, "warning");
  });

  pi.on("message_end", async (event, ctx) => {
    const message = event.message as { role?: unknown; usage?: unknown; content?: { type?: string; text?: string }[]; errorMessage?: unknown };
    if (message.role !== "assistant" || chargedMessages.has(message)) return;
    const goal = core.goal;
    if (!goal || goal.status !== "active" || !goal.autoContinue) return;
    chargedMessages.add(message);
    if (!message.errorMessage) {
      const claim = message.content?.filter(block => block.type === "text").map(block => block.text ?? "").join("\n").trim();
      if (claim) core.recordClaim(claim);
    }
    const elapsed = core.currentTurnSeconds();
    core.chargeUsage(ctx, goal, ++usageSequence, turnTokens(message.usage), elapsed - elapsedCharged);
    elapsedCharged = elapsed;
    refreshGoalToolSurface(core, ctx);
    refreshDashboard(core, ctx);
  });

  /**
   * The loop's own completion check.
   *
   * Nothing here waits for the model to remember `update_goal({status:
   * "complete"})`. After every execution the runtime asks the check whether the
   * objective is met from what the executor just did. An answer of MET closes
   * the goal without another run; anything else becomes the next turn's input.
   * The model asking for completion itself is the same check, only earlier.
   */
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
    // The check comes before settling. A goal that turns out to be met closes
    // here and never queues a continuation for a goal that no longer exists.
    if (!failed && goal.status === "active" && goal.autoContinue && !core.turnRequestedCompletion() && !core.hasActiveBackgroundWork()) {
      const settled = await runLoopCheck(core, ctx, goal);
      if (settled) return;
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
/**
 * Run the completion check for a settled turn that did not ask for one.
 *
 * MET archives the goal here rather than queuing another run and reports that
 * the goal is over. NOT MET records the missing requirement so the next
 * continuation carries it; the turn continues, because an open goal keeps
 * working and the unmet line is what it works on next.
 */
async function runLoopCheck(core: GoalCore, ctx: import("@earendil-works/pi-coding-agent").ExtensionContext, goal: import("./record.ts").GoalRecord): Promise<boolean> {
  const claim = core.lastExecutorClaim();
  const turn = core.currentTurnSeq();
  const generation = goal.scheduler?.generation;
  const verdict = await core.check(ctx, goal, claim, core.settings(ctx));
  const current = core.goal;
  // A cancelled check must end its old lifecycle path, not settle a resumed run.
  if (verdict.stale || !current || current.id !== goal.id || current.status !== goal.status ||
      current.scheduler?.generation !== generation || core.currentTurnSeq() !== turn ||
      current.objective !== goal.objective || current.verificationContract !== goal.verificationContract ||
      current.evidenceSince !== goal.evidenceSince) return true;
  if (verdict.met) {
    const outcome = core.completeCheckedGoal(ctx, goal);
    if (!outcome.ok) {
      core.notify(ctx, outcome.message, "error");
      return false;
    }
    core.notify(ctx, "Goal met its objective and is archived.", "info");
    return true;
  }
  core.setUnmet(verdict.report);
  core.appendEvents(ctx, [{ type: "check_deferred", goalId: goal.id, report: verdict.report, at: new Date().toISOString() }]);
  core.notify(ctx, describeUnmet(verdict), "info");
  return false;
}
