/**
 * The loop.
 *
 * One idea holds this together: **a timer, a settled turn, and a queued message
 * are opportunities, not authorization.** Each can create a chance to run; none
 * of them can start one. Authorization is a durable record, and it is spent
 * exactly once by a claim that re-checks everything it depended on at the moment
 * work would actually begin.
 *
 * That is why arming and claiming are separate. Between `schedule` and `claim`
 * the goal can be paused, refocused, revised, or run out of budget, and each of
 * those has to invalidate the armed intent rather than be discovered by a model
 * turn that was already under way.
 *
 * There is no waiting, no polling, and no execution contract to satisfy. The
 * loop runs until the goal is met, until something stops it, or until the run
 * allowance runs out — and the one thing that makes "until the goal is met" a
 * real statement is `GoalCore.check`, which the loop runs itself rather than
 * waiting for the model to remember to ask.
 */

import { budgetReached, nowIso, randomToken, type GoalRecord, type GoalSchedulerState } from "./record.ts";
import type { GoalSettings } from "./settings.ts";
import type { GoalMutationOutcome } from "./store.ts";

/** What the scheduler needs from its host. Kept to this narrow surface so the
 * whole state machine is testable without a Pi session. */
export interface SchedulerHost {
  /** The goal this session has focused, or undefined. */
  readFocused(): GoalRecord | undefined;
  /** The session that owns scheduling. */
  readOwner(): string;
  /** Run one mutation through the store. */
  apply(spec: {
    expectedGoalId: string;
    mutate: (goal: GoalRecord) => GoalRecord | undefined;
    ledger?: import("./ledger.ts").GoalLedgerEvent[];
  }): GoalMutationOutcome;
  /** Record a failure somewhere the user will see. */
  notify(message: string, level: "info" | "warning" | "error"): void;
  /** Ask the runtime to deliver a continuation. */
  queueContinuation(goal: GoalRecord): void;
  /** Cancel any pending continuation. */
  cancelContinuation(goalId: string): void;
}

export type DeclareResult = { ok: true; goal: GoalRecord } | { ok: false; message: string };

export class GoalScheduler {
  private readonly host: SchedulerHost;
  /** Generation armed by `schedule`, spent exactly once by `claim`. Nothing may
   * dispatch unless one is present. */
  private armedGeneration: string | undefined;
  /** The goal that generation was computed for. A claim must never be spent on a
   * different one, and without this the only way to notice would be to mutate
   * the other goal and fail — which pauses a goal nothing is wrong with. */
  private armedGoalId: string | undefined;
  private inRun = false;
  /**
   * Settings last handed to `schedule`, `declare`, `settled`, or `resume`. The
   * scheduler always answers from the latest it was given, because `claim` and
   * the background paths have no settings of their own.
   */
  private lastSettings: GoalSettings = {};
  /** Set when a checkpoint was refused, so the turn that received it cannot do
   * work even if the model ignores the block. */
  private denied = false;

  constructor(host: SchedulerHost) {
    this.host = host;
  }

  private focused(): GoalRecord | undefined {
    const goal = this.host.readFocused();
    if (!goal || goal.status !== "active" || !goal.autoContinue) return undefined;
    return goal;
  }

  private allowanceReason(settings: GoalSettings): string {
    return settings.maxAutonomousRuns === 0
      ? "Automatic continuation is disabled (maxAutonomousRuns=0). Change it in the goal settings file, then /goal resume."
      : "The autonomous-run allowance is spent. Raise or remove maxAutonomousRuns, or /goal resume to start a new period.";
  }

  private runsRemaining(goal: GoalRecord, settings: GoalSettings): boolean {
    if (settings.maxAutonomousRuns === undefined) return true;
    return (goal.scheduler?.used ?? 0) < settings.maxAutonomousRuns;
  }

  private owned(goal: GoalRecord): boolean {
    return goal.scheduler?.owner === this.host.readOwner();
  }

  /**
   * What the loop must settle before arming: the goal is still ours, still live,
   * still affordable.
   *
   * Returns a reason to stop, or undefined to go on. Anything that stops the
   * loop is a pause rather than a silent end, so the goal is never left looking
   * active with nothing running it.
   */
  private blocker(goal: GoalRecord, settings: GoalSettings): string | undefined {
    if (!this.owned(goal)) return "This goal is scheduled by another session. /goal resume takes it over.";
    if (budgetReached(goal)) return "The lifetime token cap for this goal is spent.";
    if (!this.runsRemaining(goal, settings)) return this.allowanceReason(settings);
    return undefined;
  }

  /**
   * Record what comes next and end the turn.
   *
   * The value is a record for the following turn, not an authorization: the loop
   * continues whether or not the model says anything. What this call does buy is
   * that the turn stops, which is what keeps the model from working past the
   * answer it just gave.
   */
  declare(goal: GoalRecord, nextAction: string, settings: GoalSettings): DeclareResult {
    this.lastSettings = settings;
    if (this.denied) {
      return { ok: false, message: "A stale checkpoint already refused this dispatch. Use /goal resume." };
    }
    // A record for a turn that cannot run is a note nobody will read. Refusing
    // with the reason tells the model what stops the goal instead.
    if (this.owned(goal)) {
      // A record for a turn that cannot run is a note nobody will read. Refusing
      // with the reason tells the model what stops the goal instead.
      const blocked = this.blocker(goal, settings);
      if (blocked) return { ok: false, message: blocked };
    }
    const outcome = this.host.apply({
      expectedGoalId: goal.id,
      mutate: (draft) => {
        if (!draft.scheduler || draft.scheduler.owner !== this.host.readOwner()) return undefined;
        return {
          ...draft,
          scheduler: { ...draft.scheduler!, phase: "ready", nextAction, generation: randomToken(), dispatch: undefined },
        };
      },
    });
    if (!outcome.ok) return { ok: false, message: outcome.message };
    return { ok: true, goal: outcome.goal };
  }

  /** A run started. */
  begin(): void {
    if (this.inRun) return;
    this.inRun = true;
    this.denied = false;
  }

  /**
   * The turn ended. Decide what, if anything, authorizes another one.
   *
   * `successful` is false for a turn that errored or was aborted. A failed turn is
   * not completed work, and turning one into another run is how a provider
   * outage becomes a retry storm.
   */
  settled(goal: GoalRecord | undefined, settings: GoalSettings, successful: boolean, performedWork = true): void {
    this.inRun = false;
    this.lastSettings = settings;
    if (this.denied || !goal || goal.status !== "active" || !goal.autoContinue) return;
    const reason = this.blocker(goal, this.lastSettings);
    if (reason) {
      this.pause(goal, reason);
      return;
    }
    if (!successful) return;
    const progress = this.host.apply({
      expectedGoalId: goal.id,
      mutate: draft => draft.scheduler ? {
        ...draft, scheduler: { ...draft.scheduler, idleRuns: performedWork ? 0 : (draft.scheduler.idleRuns ?? 0) + 1 },
      } : undefined,
    });
    if (!progress.ok) {
      this.pause(goal, progress.message);
      return;
    }
    if ((progress.goal.scheduler?.idleRuns ?? 0) >= 3) {
      const reason = "Three consecutive runs performed no work. Run the missing verification or resolve the reported unmet condition, then use /goal resume.";
      this.pause(progress.goal, reason);
      this.host.notify(reason, "warning");
      return;
    }
    this.implicitReady(progress.goal);
  }

  /**
   * Arm the next continuation.
   *
   * Deliberately weak: it records the generation that was valid at this moment
   * and stops. Whether it is *still* valid is `claim`'s question, asked at
   * delivery time.
   */
  schedule(goal: GoalRecord, settings: GoalSettings): void {
    this.lastSettings = settings;
    if (this.inRun) return;
    const wanted = goal.id;
    const check = (): void => {
      const current = this.focused();
      if (!current || current.id !== wanted) return;
      if (current.scheduler?.phase !== "ready") return;
      const reason = this.blocker(current, settings);
      if (reason) {
        this.pause(current, reason);
        return;
      }
      this.armedGeneration = current.scheduler!.generation;
      this.armedGoalId = current.id;
      this.host.queueContinuation(current);
    };
    check();
  }

  /**
   * Authorize exactly one run.
   *
   * Every precondition is re-checked here rather than trusted from arming time,
   * because between the two the goal can be paused, refocused, revised, or run
   * out of budget. A failure means the decision can no longer authorize anything,
   * so the goal stops rather than continuing on an intent nothing decided on.
   */
  claim(): { goalId: string; generation: string; dispatchId: string; run: number } | null {
    const armed = this.armedGeneration;
    const armedFor = this.armedGoalId;
    if (!armed) return null;
    this.armedGeneration = undefined;
    this.armedGoalId = undefined;

    // The session moved to a different goal after this was armed. Standing down
    // is the only correct answer: the decision belongs to a goal this session is
    // no longer working on, and mutating the new one to discover that would pause
    // a goal nothing is wrong with.
    if (armedFor !== this.focused()?.id) return null;

    const goal = this.focused();
    if (!goal?.scheduler || !this.owned(goal)) return null;
    const reason = this.blocker(goal, this.lastSettings);
    if (reason) {
      this.pause(goal, reason);
      return null;
    }

    let authorization: { goalId: string; generation: string; dispatchId: string; run: number } | undefined;
    const outcome = this.host.apply({
      expectedGoalId: goal.id,
      mutate: (draft) => {
        const scheduler = draft.scheduler;
        if (!scheduler) return undefined;
        if (scheduler.generation !== armed) {
          throw new StaleGeneration(`The armed generation ${armed} is now ${scheduler.generation}.`);
        }
        // A decision is spent by being claimed. Losing that race is not a fault
        // in the goal, so it is its own condition rather than a reason to stop.
        if (scheduler.phase === "claimed" || scheduler.phase === "running") {
          throw new AlreadyClaimed(`Dispatch ${scheduler.dispatch?.id ?? "unknown"} already claimed this decision.`);
        }
        const dispatchId = randomToken();
        scheduler.used += 1;
        scheduler.phase = "claimed";
        scheduler.dispatch = { id: dispatchId, claimedAt: Date.now() };
        authorization = { goalId: draft.id, generation: scheduler.generation, dispatchId, run: scheduler.used };
        return { ...draft, scheduler };
      },
      ledger: authorization === undefined ? [] : [{ type: "goal_claimed", goalId: authorization.goalId, dispatchId: authorization.dispatchId, run: authorization.run, at: nowIso() }],
    });
    if (!outcome.ok) {
      // Losing the race to claim is not a fault: another scheduler on this same
      // owner took the run, and that run is now in progress. Standing down is the
      // only correct answer — pausing would end legitimate work.
      if (this.raceWasBenign()) return null;
      this.host.notify(`Goal continuation stopped: ${outcome.message}`, "warning");
      const stillFocused = this.focused();
      if (stillFocused) this.pause(stillFocused, outcome.message);
      return null;
    }
    return authorization ?? null;
  }


  private implicitReady(goal: GoalRecord): void {
    const outcome = this.host.apply({
      expectedGoalId: goal.id,
      mutate: (draft) => {
        if (!draft.scheduler) return undefined;
        return { ...draft, scheduler: { ...draft.scheduler, phase: "ready", dispatch: undefined, generation: randomToken() } };
      },
    });
    if (outcome.ok) this.schedule(outcome.goal, this.lastSettings);
  }

  /**
   * Whether this claim lost a benign race.
   *
   * Read from state rather than from the failure message: a message is prose a
   * caller could word differently, and the answer that matters is whether the
   * goal is still live and already dispatched.
   */
  private raceWasBenign(): boolean {
    const goal = this.focused();
    if (!goal?.scheduler) return false;
    return goal.scheduler.phase === "claimed" || goal.scheduler.phase === "running";
  }

  /** A checkpoint arrived. It is accepted only if it still matches the claim. */
  acceptCheckpoint(details: { goalId?: unknown; generation?: unknown; dispatchId?: unknown }): { ok: true } | { ok: false; message: string } {
    if (this.denied) {
      // A turn that already received a refused checkpoint stays refused: a model
      // that retries with the same details must not get a second hearing.
      return { ok: false, message: "This dispatch was already refused. Use /goal resume." };
    }
    const goal = this.focused();
    const scheduler = goal?.scheduler;
    if (
      !goal || !scheduler ||
      details.goalId !== goal.id ||
      details.generation !== scheduler.generation ||
      details.dispatchId !== scheduler.dispatch?.id ||
      scheduler.phase !== "claimed"
    ) {
      this.denied = true;
      return { ok: false, message: "This checkpoint does not match the goal's current claim." };
    }
    const outcome = this.host.apply({
      expectedGoalId: goal.id,
      mutate: (draft) => {
        if (!draft.scheduler) return undefined;
        // The dispatch is retained as context; the phase is what stops the same
        // authorization from being spent a second time.
        draft.scheduler.phase = "running";
        return draft;
      },
    });
    if (!outcome.ok) {
      this.denied = true;
      return { ok: false, message: outcome.message };
    }
    return { ok: true };
  }

  /** The claim could not be delivered. The run was already counted, so the goal
   *  stops rather than assuming it will be retried. */
  dispatchFailed(goal: GoalRecord): void {
    this.pause(goal, "The goal checkpoint could not be delivered after claiming a run. Use /goal resume; it will not be replayed.");
  }

  /** Pause now. */
  pause(goal: GoalRecord, reason: string, stopReason: "user" | "agent" = "agent"): boolean {
    this.armedGeneration = undefined;
    this.armedGoalId = undefined;
    this.host.cancelContinuation(goal.id);
    const at = nowIso();
    const outcome = this.host.apply({
      expectedGoalId: goal.id,
      mutate: (draft) => ({
        ...draft,
        status: "paused",
        autoContinue: false,
        stopReason,
        pauseReason: reason,
        scheduler: draft.scheduler
          ? { ...draft.scheduler, phase: "idle", dispatch: undefined, generation: randomToken() }
          : undefined,
      }),
      ledger: [{ type: "goal_paused", goalId: goal.id, reason, stopReason, at }],
    });
    if (!outcome.ok) {
      this.host.notify(`Could not pause goal ${goal.id}: ${outcome.message}`, "warning");
    }
    return outcome.ok;
  }

  /** Explicit user resume starts a new allowance period. */
  resume(goal: GoalRecord, settings: GoalSettings): boolean {
    this.lastSettings = settings;
    this.inRun = false;
    this.denied = false;
    if (settings.maxAutonomousRuns === 0) {
      this.host.notify(this.allowanceReason(settings), "warning");
      return false;
    }
    if (goal.status === "complete" || budgetReached(goal)) {
      this.host.notify("A completed or token-capped goal cannot resume.", "warning");
      return false;
    }
    const outcome = this.host.apply({
      expectedGoalId: goal.id,
      mutate: (draft) => ({
        ...draft,
        status: "active",
        autoContinue: true,
        completionFailures: 0,
        stopReason: undefined,
        pauseReason: undefined,
        scheduler: draft.scheduler
          ? { ...draft.scheduler, owner: this.host.readOwner(), phase: "ready", used: 0, idleRuns: 0, dispatch: undefined, generation: randomToken() }
          : { owner: this.host.readOwner(), phase: "ready", used: 0, idleRuns: 0, generation: randomToken() },
      }),
      ledger: [{ type: "goal_resumed", goalId: goal.id, reason: "user", at: nowIso() }],
    });
    if (!outcome.ok) {
      this.host.notify(outcome.message, "warning");
      return false;
    }
    this.schedule(outcome.goal, settings);
    return true;
  }

  /** Another session's real work supersedes an armed claim. */
  takeover(goal: GoalRecord): void {
    this.armedGeneration = undefined;
    this.armedGoalId = undefined;
    if (!goal.scheduler) return;
    this.host.apply({
      expectedGoalId: goal.id,
      mutate: (draft) =>
        draft.scheduler ? { ...draft, scheduler: { ...draft.scheduler, phase: "idle", dispatch: undefined, generation: randomToken() } } : undefined,
    });
  }

  /** A session ended while a run was in flight. The dispatch that would have
   *  finished it never will, so the goal is paused rather than resumed. */
  markInterrupted(goal: GoalRecord): boolean {
    const scheduler = goal.scheduler;
    if (!scheduler || (scheduler.phase !== "claimed" && scheduler.phase !== "running")) return false;
    this.host.apply({
      expectedGoalId: goal.id,
      mutate: (draft) =>
        draft.scheduler ? { ...draft, scheduler: { ...draft.scheduler, phase: "interrupted" } } : undefined,
    });
    return true;
  }

  shutdown(): void {
    this.armedGeneration = undefined;
    this.armedGoalId = undefined;
    this.inRun = false;
  }

  isDenied(): boolean {
    return this.denied;
  }

  isArmed(): boolean {
    return this.armedGeneration !== undefined;
  }
}

/** A decision that no longer applies because the goal moved on. */
export class StaleGeneration extends Error {}

/** Another writer already consumed this decision. Benign. */
export class AlreadyClaimed extends Error {}

export type { GoalSchedulerState };
