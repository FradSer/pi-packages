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
 * the goal can be paused, refocused, revised, or stopped, and each of
 * those has to invalidate the armed intent rather than be discovered by a model
 * turn that was already under way.
 *
 * Effective work may authorize one further run. Completion requires an
 * explicit request and a separate tool-less check.
 */

import { randomToken, type GoalRecord, type ResumeReason } from "./record.ts";
import { NO_NEW_WORK_RUN_LIMIT, type GoalSettings } from "./settings.ts";
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
    expectedRevision?: number;
    mutate: (goal: GoalRecord) => GoalRecord | undefined;
  }): GoalMutationOutcome;
  /** Record a failure somewhere the user will see. */
  notify(message: string, level: "info" | "warning" | "error"): void;
  /** Ask the runtime to deliver a continuation. */
  queueContinuation(goal: GoalRecord): void;
  /** Cancel any pending continuation. */
  cancelContinuation(goalId: string): void;
}


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
   * Settings last handed to `schedule`, `settled`, or `resume`. The
   * scheduler always answers from the latest it was given, because `claim` and
   * the background paths have no settings of their own.
   */
  private lastSettings: GoalSettings = {};
  /** Set when a checkpoint was refused, so the turn that received it cannot do
   * work even if the model ignores the block. */
  private denied = false;
  /** Runs since the last run that produced something new. The loop's bound: a goal
   * that keeps doing the same thing, or nothing, stops itself. */
  private noNewWorkRuns = 0;

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
      : "The autonomous-run allowance is spent. Raise or remove maxAutonomousRuns before resuming.";
  }

  private runsRemaining(goal: GoalRecord, settings: GoalSettings): boolean {
    if (settings.maxAutonomousRuns === undefined) return true;
    return (goal.scheduler?.used ?? 0) < settings.maxAutonomousRuns;
  }

  private owned(goal: GoalRecord): boolean {
    return goal.scheduler?.owner === this.host.readOwner();
  }

  /** Whether this session still owns the goal. Callers that write `status`
   * directly instead of through pause() must ask before they stop it. */
  owns(goal: GoalRecord): boolean {
    return this.owned(goal);
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
   * outage becomes a retry storm, so it stops the loop at once.
   *
   * `didWork` says whether the run produced anything this session had not already
   * seen: a receipt new to it, or the user's own turn. Progress is novelty, not a
   * particular tool, so an autonomous run that only explored still earns the next
   * one — what stops the loop is *repetition*. Consecutive runs with nothing new
   * stop it, which covers the run that answered instead of acting, the run that
   * produced nothing at all, and the run that only repeated earlier receipts. The
   * caller counts a user's own turn as new work, so a `/goal <text>` request that
   * only records the objective spends no run and the work that follows keeps the
   * full window.
   */
  settled(goal: GoalRecord | undefined, settings: GoalSettings, successful: boolean, didWork = true): void {
    this.inRun = false;
    this.lastSettings = settings;
    if (this.denied || !goal || goal.status !== "active" || !goal.autoContinue) return;
    const reason = this.blocker(goal, this.lastSettings);
    if (reason) {
      this.pause(goal, reason, "agent", { requireRevision: goal.revision });
      return;
    }
    if (!successful) {
      const reason = "Execution was interrupted or failed. Use /goal resume to continue.";
      if (this.pause(goal, reason, "agent", { requireRevision: goal.revision })) this.host.notify(reason, "warning");
      return;
    }
    if (!didWork) {
      this.noNewWorkRuns += 1;
      if (this.noNewWorkRuns >= NO_NEW_WORK_RUN_LIMIT) {
        const reason = `${this.noNewWorkRuns} consecutive runs produced nothing new. Use /goal resume to continue.`;
        if (this.pause(goal, reason, "agent", { requireRevision: goal.revision })) this.host.notify(reason, "warning");
        return;
      }
    } else {
      this.noNewWorkRuns = 0;
    }
    this.implicitReady(goal, goal.revision);

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
   * because between the two the goal can be paused, refocused, revised, or stopped.
   * A failure means the decision can no longer authorize anything,
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
        // Only the armed decision may authorize a run. A user pause, a takeover
        // or an idle transition can move the phase on between arming and this
        // write, and an idle or interrupted decision authorizes nothing.
        if (scheduler.phase !== "ready") {
          throw new GoalStopped(`The decision is no longer ready to run.`);
        }
        // Every precondition is judged again here, on the record the lock
        // protects. The check above read a snapshot, and a writer can pause,
        // uncouple or stop this goal in the window before the lock was taken. A
        // claim on a stopped goal would spend a run and record a dispatch that
        // nothing is authorized to perform.
        const stopped = this.blocker(draft, this.lastSettings);
        if (stopped || !draft.autoContinue || draft.status !== "active") {
          throw new GoalStopped(`The goal stopped before the claim took its lock: ${stopped ?? draft.status}.`);
        }
        const dispatchId = randomToken();
        scheduler.used += 1;
        scheduler.phase = "claimed";
        scheduler.dispatch = { id: dispatchId, claimedAt: Date.now() };
        authorization = { goalId: draft.id, generation: scheduler.generation, dispatchId, run: scheduler.used };

        return { ...draft, scheduler };
      },

    });
    if (!outcome.ok) {
      // Losing the race to claim is not a fault: another scheduler on this same
      // owner took the run, and that run is now in progress. Standing down is the
      // only correct answer — pausing would end legitimate work.
      if (this.raceWasBenign()) return null;
      // The goal also stops here when it stopped itself: a capped, paused or
      // refocused goal already carries the reason, and pausing it again would
      // overwrite that reason with this claim's message.
      // `focused()` can still answer from the snapshot the pre-lock read handed out,
      // so the stop is judged on the record the lock just released.
      const current = this.host.readFocused();
      if (current && (current.status !== "active" || !this.owned(current))) return null;
      this.host.notify(`Goal continuation stopped: ${outcome.message}`, "warning");
      const stillFocused = this.focused();
      // Ownership is re-checked inside the pause write itself, not only here.
      if (stillFocused) this.pause(stillFocused, outcome.message, "agent");
      return null;
    }
    return authorization ?? null;
  }

  private implicitReady(goal: GoalRecord, expectedRevision: number): void {
    const outcome = this.host.apply({
      expectedGoalId: goal.id,
      mutate: (draft) => {
        // Promote only the record the progress write produced. A replacement
        // that started after it carries its own dispatch and generation, and
        // promoting then would delete that dispatch and rotate its generation,
        // handing the goal a decision nothing earned. There is deliberately no
        // phase or owner check here: settlement legitimately arrives from this
        // execution's own running dispatch or from a ready decision it saved.
        if (!draft.scheduler || draft.revision !== expectedRevision) return undefined;
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
        const current = draft.scheduler;
        if (!current) return undefined;
        // Everything above read a snapshot. A user can pause this goal, or
        // another session can take it, in the window before the lock.
        //
        // The run allowance is deliberately NOT rejudged here. The claim already
        // discharged it, so a goal on its last authorized run would refuse its
        // own checkpoint and strand a run it was legitimately given.
        if (
          current.owner !== this.host.readOwner() ||
          draft.status !== "active" ||
          !draft.autoContinue ||
          current.phase !== "claimed" ||
          current.generation !== details.generation ||
          current.dispatch?.id !== details.dispatchId
        ) {
          throw new GoalStopped("The goal no longer matches this checkpoint.");
        }
        // `current` is the same object `draft.scheduler` holds, and the guard
        // above proves it exists, so the write narrows nothing new.
        current.phase = "running";
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
  pause(
    goal: GoalRecord,
    reason: string,
    stopReason: "user" | "agent" = "agent",
    options: { requireRevision?: number; notifyFailure?: boolean } = {},
  ): boolean {
    // Every agent-initiated stop is guarded here, not at the call sites: there
    // are many, and only one of them remembered to ask. Ownership can rotate
    // between deciding to pause and taking the write lock, and stopping a goal
    // another session now owns is a real user action taken on someone else's
    // work. A user pause carries its own authority and is exempt.
    const requireOwnership = stopReason !== "user";
    const outcome = this.host.apply({
      expectedGoalId: goal.id,
      mutate: (draft) => {
        // Ownership can rotate between deciding to pause and taking the lock.
        // Stopping a goal another session now owns would be a real user
        // action taken on someone else's work, so the write declines instead.
        if (requireOwnership && draft.scheduler?.owner !== this.host.readOwner()) {
          return undefined;
        }
        // A stop justified by one revision may not be written to another. A
        // replacement that started after the reason was read carries its own
        // live dispatch, and pausing it on the old grounds ends work this
        // session has already handed over.
        if (options.requireRevision !== undefined && draft.revision !== options.requireRevision) {
          return undefined;
        }
        return {
          ...draft,
          status: stopReason === "user" ? "paused" : "active",
          autoContinue: false,
          stopReason,
          pauseReason: reason,
          scheduler: draft.scheduler
            ? { ...draft.scheduler, phase: "idle", dispatch: undefined, generation: randomToken() }
            : undefined,
        };
      },

    });
    if (outcome.ok) {
      this.armedGeneration = undefined;
      this.armedGoalId = undefined;
      this.host.cancelContinuation(goal.id);
    } else if (options.notifyFailure !== false) {
      this.host.notify(`Could not pause the goal: ${outcome.message}`, "warning");
    }
    return outcome.ok;
  }

  /** A resume preserves the lifetime usage and allowance. The actor is recorded because the
   * two routes are different facts: the management verb has the user in front
   * of it, while a revision under an accepted `/goal <text>` request is the
   * runtime lifting a pause on the user's behalf. */
  resume(goal: GoalRecord, settings: GoalSettings, _reason: ResumeReason): boolean {
    this.lastSettings = settings;
    this.inRun = false;
    this.denied = false;
    // A user resume is a fresh opportunity: the window starts again, or a goal
    // stopped by it could never be resumed more than once.
    this.noNewWorkRuns = 0;
    if (settings.maxAutonomousRuns === 0) {
      this.host.notify(this.allowanceReason(settings), "warning");
      return false;
    }
    if (goal.status === "complete") {
      this.host.notify("A completed goal cannot resume. Start a new goal.", "warning");
      return false;
    }
    if (!this.runsRemaining(goal, settings)) {
      this.host.notify(this.allowanceReason(settings), "warning");
      return false;
    }
    const outcome = this.host.apply({
      expectedGoalId: goal.id,
      expectedRevision: goal.revision,
      mutate: (draft) => draft.status !== "complete" && this.runsRemaining(draft, settings) ? ({
        ...draft,
        status: "active",
        autoContinue: true,
        stopReason: undefined,
        pauseReason: undefined,
        scheduler: draft.scheduler
          ? { ...draft.scheduler, owner: this.host.readOwner(), phase: "ready", dispatch: undefined, generation: randomToken() }
          : { owner: this.host.readOwner(), phase: "ready", used: 0, generation: randomToken() },
      }) : undefined,

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

  shutdown(): void {
    this.armedGeneration = undefined;
    this.armedGoalId = undefined;
    this.inRun = false;
  }

  isRunning(): boolean {
    return this.inRun;
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

/** The goal stopped before this claim took its lock, so nothing may claim it. */
export class GoalStopped extends Error {}
