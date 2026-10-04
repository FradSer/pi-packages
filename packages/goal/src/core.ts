/**
 * The goal runtime core: one object that owns the store, the focused goal, the
 * scheduler, and the completion check in flight.
 *
 * Everything that needs to change goal state goes through here, so there is one
 * place that knows what "the focused goal" means and one place that can be
 * asked to reconcile it. Tool executors, command handlers, and lifecycle hooks
 * hold a reference to this and never reach past it.
 */

import type { BoundaryResult, CustomMessageEntryDraft, ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { notifyPi } from "@fradser/pi-kit";
import { completionAdvice, runCompletionCheck, type CheckVerdict } from "./check.ts";
import { runGoalResearch, type ResearchResult } from "./research.ts";
import { collectGoalEvidence } from "./evidence.ts";
import type { GoalLedgerEvent } from "./ledger.ts";
import { GoalScheduler } from "./scheduler.ts";
import { loadGoalSettings, type GoalSettings } from "./settings.ts";
import { GoalStore, newGoalId, type GoalMutationOutcome } from "./store.ts";
import { budgetReached, nowIso, randomToken, type GoalRecord } from "./record.ts";

/** Session entry that records which goal this session is working on. Focus is
 * session-scoped on purpose: two sessions in one project can work different
 * goals at the same time without fighting over a project-global pointer. */
export const GOAL_FOCUS_ENTRY = "pi-goal-focus";

export interface GoalFocusEntry {
  version: 1;
  focusedGoalId: string | null;
  reason: "created" | "selected" | "unfocused" | "resumed" | "completed" | "cleared";
}

export interface GoalCoreOptions {
  /** Injected so the test harness can decide the verdict without a real model. */
  runCheck?: typeof runCompletionCheck;
  /** Injected so the test harness can supply research without a real child. */
  runResearch?: typeof runGoalResearch;
  /** Injected so a test can run against a temporary project rather than the
   * process's real working directory. */
  projectRoot?: string;
}

/** Research gathered before any goal exists. Held for this session only: it
 * is material waiting for the objective it will inform, and losing it costs a
 * re-run, not a goal. Consumed by the next `create_goal`. */
export interface PendingResearch {
  focus: string;
  findings: string;
  tokens: number;
}

export class GoalCore {
  readonly pi: ExtensionAPI;
  readonly store: GoalStore;
  readonly scheduler: GoalScheduler;

  private focusedGoalId: string | undefined;
  /** Abort for the check in flight, so focus change or shutdown stops it. */
  private checkAbort: AbortController | undefined;
  /** Check progress for the surface. */
  checkProgress: { label: string; detail?: string } | undefined;
  /** Tool names this extension owns, re-asserted on every surface change. */
  private readonly runCheck: typeof runCompletionCheck;
  private readonly runResearch: typeof runGoalResearch;
  private pendingResearch: PendingResearch | undefined;
  private researchGeneration = 0;
  private activationGoalId: string | undefined;
  private pendingSetting: { prompt: string; goalId: string; owner: string } | undefined;

  constructor(pi: ExtensionAPI, projectRoot: string, options: GoalCoreOptions = {}) {
    this.pi = pi;
    this.store = new GoalStore({ projectRoot });
    this.runCheck = options.runCheck ?? runCompletionCheck;
    this.runResearch = options.runResearch ?? runGoalResearch;
    this.scheduler = new GoalScheduler({
      readFocused: () => this.goal,
      readOwner: () => this.owner(),
      apply: (spec) => this.store.apply({ ...spec }),
      notify: (message, level) => this.lastUi?.notify(message, level),
      queueContinuation: (goal) => this.queueContinuation(goal),
      cancelContinuation: (goalId) => this.cancelContinuation(goalId),
    });
  }

  /** The UI of the most recent handler, so background paths can still notify. */
  private lastUi: { notify(message: string, level: "info" | "warning" | "error"): void } | undefined;

  /**
   * Remember how to reach the user.
   *
   * Background paths — the continuation timer, the scheduler's failure handling —
   * report through a context captured earlier. That context goes stale on a
   * session replacement or rebind, and the host throws when it is used. Since
   * these callers are timers and tool handlers rather than a user waiting on a
   * reply, a lost notification must never take the runtime down with it.
   */
  bindUi(ctx: ExtensionContext): void {
    this.lastCtx = ctx;
    this.lastUi = {
      notify: (message, level) => {
        try {
          notifyPi(ctx.ui, message, level);
        } catch {
          // The session this context belonged to is gone. The state change that
          // prompted the message is already durable, so there is nothing to
          // repair here — only a message that cannot be delivered.
        }
      },
    };
  }

  private owner(): string {
    return this.lastSessionId ?? "unknown-session";
  }

  private lastSessionId: string | undefined;

  // ── focus ──────────────────────────────────────────────────────────

  get goal(): GoalRecord | undefined {
    if (!this.focusedGoalId) return undefined;
    const goal = this.store.readGoalFromDisk(this.focusedGoalId);
    // The goal may have been cleared or archived by another session since it
    // was focused. Reporting it as still focused would let a command act on a
    // goal that no longer exists.
    if (!goal || goal.status === "complete") return undefined;
    if (goal.threadId && goal.threadId !== this.owner()) return undefined;
    return goal;
  }

  get focusedId(): string | undefined {
    return this.focusedGoalId;
  }

  get openGoals(): GoalRecord[] {
    return this.store.readPool();
  }

  settings(ctx: ExtensionContext): GoalSettings {
    return loadGoalSettings(ctx.cwd);
  }

  /** Reload state at a session boundary: drop every cached copy and rebuild
   * focus from the session's own entries, so another session's work is seen
   * and this session's focus is not inherited from anywhere else. */
  restore(ctx: ExtensionContext): void {
    this.cancelGoalActivation();
    this.cancelContinuation(this.focusedGoalId ?? "");
    this.scheduler.shutdown();
    this.abortCheck();
    this.pendingResearch = undefined;
    this.researchGeneration += 1;
    this.store.invalidate();
    this.lastSessionId = ctx.sessionManager.getSessionId();
    this.bindUi(ctx);
    let focused: string | undefined;
    for (const entry of ctx.sessionManager.getBranch()) {
      if (entry.type !== "custom" || entry.customType !== GOAL_FOCUS_ENTRY) continue;
      const data = entry.data as { focusedGoalId?: unknown } | undefined;
      focused = typeof data?.focusedGoalId === "string" ? data.focusedGoalId : undefined;
    }
    this.focusedGoalId = focused;
    if (focused && !this.goal) this.focusedGoalId = undefined;
    // Only this thread's persisted entries identify its goal.
  }

  focus(goalId: string, ctx: ExtensionContext, reason: GoalFocusEntry["reason"]): boolean {
    const record = this.store.readGoalFromDisk(goalId);
    if (!record || (record.threadId && record.threadId !== this.owner())) {
      this.notify(ctx, `No goal ${goalId} is open.`, "warning");
      return false;
    }
    this.focusedGoalId = goalId;
    this.appendFocusEntry(goalId, reason);
    this.store.apply({
      expectedGoalId: goalId,
      mutate: (goal) => goal,
      ledger: [{ type: "goal_focused", goalId, reason, at: nowIso() }],
    });
    this.refreshUi(ctx);
    return true;
  }

  unfocus(ctx: ExtensionContext): void {
    const previous = this.focusedGoalId;
    this.focusedGoalId = undefined;
    this.appendFocusEntry(null, "unfocused");
    this.abortCheck();
    if (previous) {
      this.cancelContinuation(previous);
      // The goal itself stays open and unchanged: unfocusing detaches this
      // session, it does not end anybody's work.
      this.scheduler.takeover(this.store.readGoal(previous) ?? { ...emptyGoal(previous) });
    }
    this.refreshUi(ctx);
  }

  private appendFocusEntry(goalId: string | null, reason: GoalFocusEntry["reason"]): void {
    const entry: GoalFocusEntry = { version: 1, focusedGoalId: goalId, reason };
    this.pi.appendEntry(GOAL_FOCUS_ENTRY, entry);
  }

  // ── continuations ──────────────────────────────────────────────────

  /** Poll cadence while waiting for the host to go idle. Deliberately short: it
   * costs one timer per wait and the loop only wakes to check. */
  private continuationTimer: ReturnType<typeof setTimeout> | undefined;
  private continuationPendingFor: string | undefined;
  private checkpointSeq = 0;
  private lastCtx: ExtensionContext | undefined;

  /**
   * Ask for one continuation when the host is actually idle.
   *
   * A fixed delay would fire while a request is still in flight and merge this
   * turn into one the user had not finished. So this retries until the host
   * reports itself idle with nothing queued, and each retry re-arms rather than
   * stacking.
   */
  queueContinuation(goal: GoalRecord): void {
    if (this.continuationPendingFor === goal.id) return;
    this.cancelContinuation(goal.id);
    this.continuationPendingFor = goal.id;
    const waitIdle = () => {
      let ready: boolean;
      try {
        const last = this.lastCtx;
        ready = last !== undefined && last.isIdle() && !last.hasPendingMessages();
      } catch {
        ready = false;
      }
      if (!ready) {
        if (this.continuationPendingFor !== goal.id) return;
        this.continuationTimer = setTimeout(waitIdle, 50);
        this.continuationTimer.unref?.();
        return;
      }
      this.continuationTimer = undefined;
      this.deliver(goal.id);
    };
    this.continuationTimer = setTimeout(waitIdle, 0);
    this.continuationTimer.unref?.();
  }

  cancelContinuation(goalId: string): void {
    if (this.continuationTimer !== undefined) clearTimeout(this.continuationTimer);
    this.continuationTimer = undefined;
    if (this.continuationPendingFor === goalId) this.continuationPendingFor = undefined;
  }

  /** Deliver one authorized continuation. The claim is what authorizes it, and
   * the claim is re-validated at this moment rather than at arming time. */
  private deliver(goalId: string): void {
    if (this.focusedGoalId !== goalId) return;
    const authorization = this.scheduler.claim();
    this.continuationPendingFor = undefined;
    if (!authorization) return;
    // Delivery happens on a timer, so anything thrown here escapes as an
    // unhandled rejection. A session replacement or rebind makes the captured
    // `pi` stale, and the run has already been claimed: losing it silently would
    // be worse than stopping the goal and saying why.
    try {
      this.sendContinuation(authorization);
    } catch (error) {
      const goal = this.goal;
      if (goal) this.scheduler.dispatchFailed(goal);
      this.lastUi?.notify(
        `Goal continuation could not be delivered: ${error instanceof Error ? error.message : String(error)}`,
        "warning",
      );
    }
  }

  private sendContinuation(authorization: { goalId: string; generation: string; dispatchId: string }): void {
    this.checkpointSeq += 1;
    const details = {
      version: 1 as const,
      kind: "checkpoint" as const,
      goalId: authorization.goalId,
      generation: authorization.generation,
      dispatchId: authorization.dispatchId,
      checkpointSeq: this.checkpointSeq,
      timestamp: Date.now(),
    };
    this.pi.sendMessage(
      { customType: "pi-goal-checkpoint", content: "", display: false, details },
      { deliverAs: "followUp", triggerTurn: true },
    );
  }

  /** Claim a ready decision inside Pi's actionable settlement boundary. */
  boundaryContinuation(): BoundaryResult | undefined {
    const goal = this.goal;
    if (!goal || !this.scheduler.isArmed()) return;
    this.cancelContinuation(goal.id);
    const authorization = this.scheduler.claim();
    if (!authorization) return;
    const accepted = this.scheduler.acceptCheckpoint(authorization);
    if (!accepted.ok) return;
    this.checkpointSeq += 1;
    const entry: CustomMessageEntryDraft = {
      type: "custom_message", customType: "pi-goal-checkpoint", content: "", display: false,
      details: { version: 1, kind: "checkpoint", ...authorization, checkpointSeq: this.checkpointSeq, timestamp: Date.now() },
    };
    this.beginRun();
    return { entries: [entry], continue: true };
  }

  /** Explicit /goal text permits activation only after this goal is revised. */
  requestGoalActivation(prompt: string): void {
    this.cancelGoalActivation();
    const goal = this.goal;
    if (goal) this.pendingSetting = { prompt, goalId: goal.id, owner: this.owner() };
  }

  /** Preflight acceptance, not the void send call, grants revision activation. */
  acceptGoalSetting(prompt: string): void {
    this.activationGoalId = undefined;
    const request = this.pendingSetting;
    this.pendingSetting = undefined;
    if (request && request.prompt === prompt && request.owner === this.owner() && this.goal?.id === request.goalId) {
      this.activationGoalId = request.goalId;
    }
  }

  cancelGoalActivation(): void {
    this.activationGoalId = undefined;
    this.pendingSetting = undefined;
  }

  activateRequestedRevision(goalId: string, ctx: ExtensionContext): boolean | undefined {
    if (this.activationGoalId !== goalId) return undefined;
    this.activationGoalId = undefined;
    const goal = this.goal;
    if (!goal || goal.id !== goalId) return false;
    return this.scheduler.resume(goal, this.settings(ctx));
  }

  // ── research ────────────────────────────────────────────────────────

  /** Hold the latest successful research for creation. A failed run keeps earlier findings.
   * A session boundary invalidates results from children that are still running. */
  async research(focus: string, cwd: string, signal?: AbortSignal): Promise<ResearchResult> {
    const settings = loadGoalSettings(cwd);
    const model = settings.researchProvider && settings.researchModel
      ? `${settings.researchProvider}/${settings.researchModel}`
      : undefined;
    const generation = ++this.researchGeneration;
    const result = await this.runResearch({ focus, cwd, model, signal });
    if (generation !== this.researchGeneration) {
      return { findings: "", usage: result.usage, error: "The research session changed. Run research again." };
    }
    if (result.error || !result.findings) return result;
    this.pendingResearch = {
      focus,
      findings: result.findings,
      tokens: result.usage?.totalTokens ?? 0,
    };
    return result;
  }

  /** The research waiting for the next goal, without consuming it. */
  peekPendingResearch(): PendingResearch | undefined {
    return this.pendingResearch;
  }

  /** Consume the research waiting for the next goal, if any. Called only
   * after the goal it informed is safely written, so a failed creation keeps
   * its material for the retry. */
  takePendingResearch(): PendingResearch | undefined {
    const research = this.pendingResearch;
    this.pendingResearch = undefined;
    return research;
  }

  // ── completion check ─────────────────────────────────────────────────

  get checkInFlight(): boolean {
    return this.checkAbort !== undefined;
  }

  abortCheck(): void {
    this.checkAbort?.abort();
    this.checkAbort = undefined;
    this.checkProgress = undefined;
  }

  /**
   * Ask a fresh model whether the objective is met.
   *
   * Deliberately not an inspector: the check gets no tools and no history, so it
   * judges the stated contract against the stated evidence and nothing else. The
   * goal stays in the open pool for the whole call, so an interrupted check can
   * never leave a half-finished goal marked complete.
   */
  async check(
    ctx: ExtensionContext,
    goal: GoalRecord,
    claim: string | undefined,
    settings: GoalSettings,
    finalAttempt = false,
  ): Promise<CheckVerdict> {
    this.abortCheck();
    const abort = new AbortController();
    const generation = goal.scheduler?.generation;
    this.checkAbort = abort;
    this.checkProgress = { label: "Checking whether the goal is met" };
    const model = settings.provider && settings.model ? `${settings.provider}/${settings.model}` : undefined;
    const evidence = collectGoalEvidence(ctx.sessionManager.getBranch(), goal, this.owner());
    this.appendEvents(ctx, [{ type: "check_started", goalId: goal.id, model, at: nowIso() }]);
    this.refreshUi(ctx);
    try {
      const result = await this.runCheck({
        objective: goal.objective,
        claim,
        contract: settings.disableContracts ? undefined : goal.verificationContract,
        evidence,
        cwd: ctx.cwd,
        signal: abort.signal,
        model,
      });
      const current = this.goal;
      if (abort.signal.aborted || this.checkAbort !== abort || !current || current.id !== goal.id ||
          current.objective !== goal.objective || current.verificationContract !== goal.verificationContract ||
          current.evidenceSince !== goal.evidenceSince || current.status !== goal.status || current.scheduler?.generation !== generation) {
        return { met: false, report: "The goal changed while the completion check ran.", stale: true };
      }
      this.appendEvents(ctx, [{
        type: "check_result",
        goalId: goal.id,
        met: result.met,
        // The report is why this decision was reached, so it is kept whole. A
        // ledger record that cannot be appended is a diagnostic, not a reason to
        // throw away the verdict just reached.
        report: (result.report || result.error || "").slice(0, 4000),
        at: nowIso(),
      }]);
      if (finalAttempt && !result.met && !result.error && !result.stale) {
        const attempts = (current.completionFailures ?? 0) + 1;
        const advice = completionAdvice(result, evidence);
        const stop = attempts >= 3;
        const outcome = this.store.apply({
          expectedGoalId: goal.id,
          expectedRevision: current.revision,
          mutate: draft => ({
            ...draft, completionFailures: attempts,
            ...(stop ? {
              status: "paused" as const, autoContinue: false, stopReason: "agent" as const,
              pauseReason: `Three final completion attempts were refused.\n${advice}`,
              scheduler: draft.scheduler ? { ...draft.scheduler, phase: "idle" as const, dispatch: undefined, generation: randomToken() } : undefined,
            } : {}),
          }),
          ledger: [{ type: "completion_refused", goalId: goal.id, attempts, report: result.report, advice, at: nowIso() }],
        });
        if (!outcome.ok) return { met: false, report: outcome.message, stale: true };
        if (stop) {
          this.cancelContinuation(goal.id);
          this.scheduler.shutdown();
          this.cancelGoalActivation();
          this.markTurnStopped();
        }
        this.setUnmet(result.report);
        return { ...result, attempts, advice, stopped: stop };
      }
      return result;
    } finally {
      if (this.checkAbort === abort) {
        this.checkAbort = undefined;
        this.checkProgress = undefined;
      }
      this.refreshUi(ctx);
    }
  }

  /** Archive only the revision whose contract was checked, for both completion paths. */
  completeCheckedGoal(ctx: ExtensionContext, checked: GoalRecord): GoalMutationOutcome {
    const outcome = this.store.apply({
      expectedGoalId: checked.id,
      expectedRevision: checked.revision,
      archive: true,
      mutate: draft => ({ ...draft, status: "complete", autoContinue: false }),
      ledger: [{ type: "goal_completed", goalId: checked.id, archivePath: `.pi/goals/archived/${checked.id}/record.json`, at: nowIso() }],
    });
    if (outcome.ok) {
      this.cancelContinuation(checked.id);
      this.clearFocus(ctx, "completed");
      this.setUnmet(undefined);
      this.refreshUi(ctx);
    }
    return outcome;
  }

  /** Whether the current turn already ran the completion check for an explicit
   * request from the model. The loop's own check must not duplicate it. */
  private turnCompletionChecked = false;

  noteCompletionRequested(): void {
    this.turnCompletionChecked = true;
  }

  /** Whether the executor asked to close the goal this turn. */
  turnRequestedCompletion(): boolean {
    return this.turnCompletionChecked;
  }

  private runPerformedWork = false;

  /** A provider run can contain several tool turns. Work belongs to the whole run. */
  beginRun(): void {
    this.runPerformedWork = false;
  }

  noteWork(toolName: string, successful: boolean, details?: unknown): void {
    if (!successful || ["create_goal", "get_goal", "update_goal", "research_goal", "monitor_stop"].includes(toolName)) return;
    if (toolName === "monitor_start") {
      if (typeof details !== "object" || details === null || !("result" in details)) return;
      const terminal = details.result;
      if (typeof terminal !== "object" || terminal === null || !("status" in terminal) || terminal.status !== "success") return;
    }
    this.runPerformedWork = true;
  }

  performedWork(): boolean {
    return this.runPerformedWork;
  }

  /** Reset bookkeeping when a new turn opens. */
  beginTurn(): void {
    this.turnCompletionChecked = false;
  }

  /** What the executor said it did, if it said anything that could be evidence. */
  lastExecutorClaim(): string | undefined {
    return this.pendingClaim;
  }

  /** The model may leave evidence on its way through a turn. */
  recordClaim(claim: string): void {
    this.pendingClaim = claim;
  }

  private pendingClaim: string | undefined;

  /** Clear the executor's claim when a turn ends or is disposed. */
  clearClaim(): void {
    this.pendingClaim = undefined;
  }

  /** What the last check said is still missing. Volatile: it belongs in the
   * counters block, never in the record. */
  private unmetLine: string | undefined;

  setUnmet(line: string | undefined): void {
    this.unmetLine = line;
  }

  currentUnmet(): string | undefined {
    return this.unmetLine;
  }

  // ── accounting ─────────────────────────────────────────────────────

  /**
   * Charge one turn's tokens.
   *
   * Idempotent per (turnSeq, tokens): a turn that reports its usage on two
   * events is charged once, because a goal that double-counted its own spend
   * would stop early for a reason the user never caused.
   */
  private chargedTurns = new Set<string>();

  chargeUsage(ctx: ExtensionContext, goal: GoalRecord, turnSeq: number, tokens: number, activeSeconds: number): GoalMutationOutcome | undefined {
    const current = this.goal;
    if (!current || current.id !== goal.id || current.status !== "active" || !current.autoContinue) return undefined;
    if (tokens <= 0 && activeSeconds <= 0) return undefined;
    const key = `${goal.id}:${turnSeq}`;
    if (this.chargedTurns.has(key)) return undefined;
    this.chargedTurns.add(key);
    if (this.chargedTurns.size > 1000) this.chargedTurns.clear();
    const outcome = this.store.apply({
      expectedGoalId: goal.id,
      mutate: (draft) => ({
        ...draft,
        usage: {
          tokensUsed: draft.usage.tokensUsed + Math.max(0, tokens),
          activeSeconds: draft.usage.activeSeconds + Math.max(0, activeSeconds),
        },
      }),
      ledger: [],
    });
    if (outcome.ok && outcome.goal.tokenBudget !== undefined && budgetReached(outcome.goal) && outcome.goal.status === "active") {
      this.markBudgetLimited(ctx, outcome.goal);
    }
    this.refreshUi(ctx);
    return outcome;
  }

  private markBudgetLimited(ctx: ExtensionContext, goal: GoalRecord): void {
    this.store.apply({
      expectedGoalId: goal.id,
      mutate: (draft) => ({
        ...draft,
        status: "budget_limited",
        autoContinue: false,
        pauseReason: `The lifetime token cap of ${draft.tokenBudget} tokens was reached.`,
      }),
      ledger: [{ type: "goal_budget_limited", goalId: goal.id, tokenBudget: goal.tokenBudget ?? 0, at: nowIso() }],
    });
    this.cancelContinuation(goal.id);
    this.notify(ctx, `Goal ${goal.id} reached its token cap and stopped.`, "warning");
  }

  appendEvents(ctx: ExtensionContext, events: GoalLedgerEvent[]): void {
    const diagnostics = this.store.appendLedger(events);
    if (diagnostics.length > 0) this.notify(ctx, diagnostics.join("\n"), "warning");
  }

  notify(ctx: ExtensionContext, message: string, level: "info" | "warning" | "error"): void {
    notifyPi(ctx.ui, message, level);
  }

  /** Ask the surface to redraw. Set by the installer; optional so the core is
   * usable headless and in tests. */
  onRefresh: ((ctx: ExtensionContext) => void) | undefined;

  refreshUi(ctx: ExtensionContext): void {
    this.onRefresh?.(ctx);
  }

  // ── turn-stop guard ───────────────────────────────────────────────

  private turnSeq = 0;
  private turnStartedAt = Date.now();
  private turnStopped: { goalId: string; turnSeq: number } | undefined;

  /** Called at the start of each model turn. A stop marker from the previous
   * turn must not carry over, or a new turn would begin already blocked. */
  advanceTurnSeq(): number {
    this.turnSeq += 1;
    this.turnStartedAt = Date.now();
    this.turnStopped = undefined;
    return this.turnSeq;
  }

  currentTurnSeq(): number {
    return this.turnSeq;
  }

  currentTurnSeconds(): number {
    return Math.max(0, Math.floor((Date.now() - this.turnStartedAt) / 1000));
  }

  /** A saved next action ended this turn. Work tools after this are refused. */
  markTurnStopped(): void {
    if (this.goal) this.turnStopped = { goalId: this.goal.id, turnSeq: this.turnSeq };
  }

  /** The goal whose recorded next action stopped this turn, or null. */
  currentTurnStoppedGoalId(): string | null {
    if (!this.turnStopped) return null;
    if (this.turnStopped.turnSeq !== this.turnSeq) {
      this.turnStopped = undefined;
      return null;
    }
    return this.turnStopped.goalId;
  }

  /** Drop focus without touching the goal. Used when a goal completes or is
   * cleared: there is nothing left for this session to be focused on. */
  clearFocus(_ctx: ExtensionContext, reason: GoalFocusEntry["reason"]): void {
    if (this.focusedGoalId) this.cancelContinuation(this.focusedGoalId);
    this.scheduler.shutdown();
    this.cancelGoalActivation();
    this.focusedGoalId = undefined;
    this.appendFocusEntry(null, reason);
  }

  shutdown(): void {
    this.cancelGoalActivation();
    this.pendingResearch = undefined;
    this.researchGeneration += 1;
    this.scheduler.shutdown();
    this.abortCheck();
    if (this.continuationTimer !== undefined) clearTimeout(this.continuationTimer);
    this.continuationTimer = undefined;
  }

  newId(): string {
    return newGoalId();
  }
}

function emptyGoal(id: string): GoalRecord {
  return {
    id,
    objective: "",
    status: "paused",
    autoContinue: false,
    usage: { tokensUsed: 0, activeSeconds: 0 },
    createdAt: nowIso(),
    updatedAt: nowIso(),
    revision: 0,
  };
}