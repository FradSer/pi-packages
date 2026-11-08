/**
 * Lifecycle handlers.
 *
 * The order of these is the runtime. `turn_start` opens a turn and its stop
 * guard; `before_agent_start` contributes prompt sections once per run;
 * `tool_call` enforces the stop
 * guard and refuses a stale checkpoint; `agent_before_settle` decides whether
 * the loop itself can close the goal before another run is authorized.
 */

import { detailField } from "@fradser/pi-kit";
import { hasInFlightDelegatedWork, isDelegatedWorkResult } from "./inflight.ts";
import { GOAL_PROCEDURE_ENTRY } from "./procedure.ts";
import type { GoalCore } from "./core.ts";
import { clearDashboard, refreshDashboard } from "./dashboard.ts";
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

/** Register runtime handlers and run-start prompt sections. */
export function registerGoalEvents(core: GoalCore): void {
  const { pi } = core;
  const chargedMessages = new WeakSet<object>();
  const runGoals = new Map<string, string | undefined>();
  const messageGoals = new WeakMap<object, { goalId?: string; threadId: string }>();
  const toolArgs = new Map<string, unknown>();
  pi.on("tool_execution_start", event => { toolArgs.set(event.toolCallId, event.args); });
  let usageSequence = 0;
  let elapsedCharged = 0;
  /** Whether the run now settling was started by the user. The no-change window
   * bounds autonomous work, so a user's own turn is a fresh opportunity rather
   * than another run that changes nothing. */
  let userRun = false;
  /** A run that reaches its settle boundary has already judged failure and
   * progress. `agent_settled` closes only runs that skipped that boundary, and
   * must never turn a provider error into another automatic model turn. */
  let settleBoundaryReached = false;
  /** The roster is process-global. Remember that THIS thread saw a child of its
   * own project in flight, and which Goal owned that wait, so only that wait's
   * terminal result can count as its work. A cleared or replaced Goal cannot
   * inherit an unrelated session's result. */
  let observedOwnDelegatedWait: string | undefined;

  pi.on("session_start", async (_event, ctx) => {
    observedOwnDelegatedWait = undefined;
    settleBoundaryReached = false;
    core.restore(ctx);
    refreshGoalToolSurface(core, ctx);
    refreshDashboard(core, ctx);
  });

  pi.on("session_tree", async (_event, ctx) => {
    // Branch navigation changes what this session has focused, so anything read
    // from disk and any armed continuation both belong to the branch we left.
    observedOwnDelegatedWait = undefined;
    settleBoundaryReached = false;
    core.restore(ctx);
    refreshGoalToolSurface(core, ctx);
    refreshDashboard(core, ctx);
  });

  pi.on("session_shutdown", async (_event, ctx) => {
    observedOwnDelegatedWait = undefined;
    settleBoundaryReached = false;
    core.shutdown();
    clearDashboard(ctx);
  });

  pi.on("before_agent_start", async (event, ctx) => {
    // A user run carries the prompt. A custom start carries the message instead and no prompt,
    // so its pending procedure is accepted later, when that message arrives. The presence test
    // is what makes this correct against both the older event shape, where the prompt is always
    // declared, and the current one, where the event is a union discriminated by run kind.
    const prompt = "prompt" in event ? event.prompt : undefined;
    if (typeof prompt === "string") core.acceptGoalSetting(prompt);
    const goal = core.goal;
    const sections = event.systemPromptOptions.sections;
    sections.goal_capability = goalCapabilityNote(Boolean(goal));
    if (goal) {
      const { state, counters } = goalPromptParts(goal, core.settings(ctx), {
        unmet: core.currentUnmet(),
        noNewWorkRuns: typeof core.scheduler.noNewWorkStreak === "function" ? core.scheduler.noNewWorkStreak() : 0,
        waitingOnDelegatedWork: hasInFlightDelegatedWork(ctx.cwd, ctx.sessionManager?.getBranch?.() ?? []),
      });
      sections.goal_runtime = `${state}\n\n${counters}`;
    } else {
      delete sections.goal_runtime;
    }
  });

  pi.on("agent_start", async (_event, ctx) => {
    core.bindUi(ctx);
    core.beginRun();
    settleBoundaryReached = false;
    // A run's mutable credit belongs to that run alone. Resetting it here as
    // well as after settlement keeps a run that never reached its settle
    // boundary from leaking a user's credit into the next autonomous run.
    userRun = false;
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
    // The custom startup event has no prompt. Accept the /goal procedure body here. The match is the same stored prompt
    // against the delivered body; a mismatch still drops the intent silently.
    const requestBody = typeof message.content === "string" ? message.content : undefined;
    const goalRequest = message.customType === GOAL_PROCEDURE_ENTRY && requestBody !== undefined;
    if (goalRequest) core.acceptGoalSetting(requestBody);
    // A completed delegated result arrives as a custom message, not a tool
    // receipt. Treat it as new work so the quiet turns spent waiting for it do
    // not end the loop: re-arm only a goal whose continuation was lost, through
    // the scheduler's ordinary store write and claim checks.
    const waitingGoalId = observedOwnDelegatedWait;
    if (!goalRequest && !isCheckpointMessage(message) && isDelegatedWorkResult(message) && waitingGoalId) {
      observedOwnDelegatedWait = undefined;
      const waitingGoal = core.store.readGoal(waitingGoalId);
      const goal = core.goal;
      if (goal?.id === waitingGoalId && waitingGoal?.status === "active") {
        core.noteWork("delegated-result", true, message.details, message.content);
        if (!goal.autoContinue && !hasInFlightDelegatedWork(ctx.cwd, ctx.sessionManager?.getBranch?.() ?? [])) {
          core.scheduler.rearmAfterResult(goal, core.settings(ctx));
        }
      }
    }
    if (!isCheckpointMessage(message)) {
      // The `/goal <text>` request is the user's own turn. The command delivers
      // it as a custom message, so its role is not `user`, but the words are the
      // user's and the run must be judged like one they typed: a model that only
      // records the objective in that turn earns its first real run instead of
      // stopping the goal before any work happens. A checkpoint is never a user
      // turn; it is the continuation the loop already authorized.
      if (message.role !== "user" && !goalRequest) return;
      userRun = true;
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
    const goal = attribution.goalId ? core.store.readGoal(attribution.goalId) : focused;
    // A released Goal's late usage must never migrate into the replacement, and a
    // finished Goal is not charged: its record is kept, but nothing may revive it.
    if (attribution.goalId && (!goal || goal.status === "complete")) { chargedMessages.add(message); return; }
    if (!goal) { chargedMessages.add(message); return; }
    if (!attribution.goalId && !core.canChargeGoal(goal)) return;
    chargedMessages.add(message);
    const elapsed = core.currentTurnSeconds();
    core.chargeUsage(ctx, goal, ++usageSequence, turnTokens(message.usage), elapsed - elapsedCharged, !!attribution.goalId);
    elapsedCharged = elapsed;
    refreshGoalToolSurface(core, ctx);
    refreshDashboard(core, ctx);
  });

  // Settling authorizes continuation only after a successful run with something new in it.
  pi.on("agent_before_settle", async (event, ctx) => {
    core.bindUi(ctx);
    // Unconsumed setting intent must not activate an unrelated later edit.
    core.cancelGoalActivation();
    settleBoundaryReached = true;
    const failed = event.outcome !== "completed";
    const userInitiated = userRun;
    userRun = false;
    const goal = core.goal;
    if (!goal) {
      refreshDashboard(core, ctx);
      return;
    }
    // A report-only turn that is honestly waiting on a living child is not a
    // no-op: it holds the window instead of spending a chance. It still earns no
    // completion check and no run of its own; the result's arrival re-arms.
    const waitingOnWork = !failed && hasInFlightDelegatedWork(ctx.cwd, ctx.sessionManager?.getBranch?.() ?? []);
    if (waitingOnWork) observedOwnDelegatedWait = goal.id;
    const wasStopped = goal.autoContinue === false;
    core.scheduler.settled(core.goal, core.settings(ctx), !failed,
      core.performedWork() || userInitiated, waitingOnWork);
    // A user's own turn is always new work. When it also produced a new receipt,
    // lift a stop the runtime itself wrote for a quiet window: progress resumed,
    // so requiring a separate /goal resume would leave the goal stranded. Run
    // after settled(), which closes the run and lets a fresh decision be armed.
    // The scheduler's guarded write preserves usage, run count and ownership,
    // and never lifts a user pause, a blocker, a spent allowance or completion.
    if (!failed && userInitiated && core.performedWork() && wasStopped) {
      core.scheduler.rearmAfterResult(goal, core.settings(ctx));
    }
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

  pi.on("agent_settled", async (event, ctx) => {
    // Pi fires this from a finally block on every run, including an aborted run
    // whose agent_before_settle is skipped. Close the run and drop its credit
    // here, so a transient interruption cannot strand the scheduler in a run or
    // make the next autonomous run look like a user's own turn. A real failed
    // run still stops the loop at its settle boundary; this only recovers the
    // state an aborted run left behind.
    if (core.scheduler.isRunning()) {
      // A normal run already closed itself in settled(); only a run that skipped
      // its settle boundary reaches here. Drop its credit and close it.
      userRun = false;
      const aborted = event.aborted === true;
      core.scheduler.abandonRun();
      const goal = core.goal;
      // An explicit abort (Escape or an extension's ctx.abort) is the user's
      // decision to stop this run. Keep the goal open but do not quietly start
      // another model turn: the next user turn or /goal resume drives that.
      // A skipped settle boundary after an otherwise completed run is a host
      // anomaly; only that case may re-arm through the ordinary store write.
      // A provider error also skips the boundary and must stop the loop at once.
      if (!settleBoundaryReached && !aborted && goal && goal.autoContinue && !core.scheduler.isArmed()) {
        const messages = (ctx.sessionManager?.getBranch?.() ?? []).flatMap(entry => entry.type === "message" ? [entry.message] : []);
        const error = messages.some(message => message.role === "assistant"
          && (message.stopReason === "error" || message.errorMessage !== undefined));
        if (error) {
          core.scheduler.settled(goal, core.settings(ctx), false, false);
        } else {
          core.scheduler.rearm(goal, core.settings(ctx));
        }
      }
    } else {
      userRun = false;
    }
    refreshGoalToolSurface(core, ctx);
    refreshDashboard(core, ctx);
  });
}
