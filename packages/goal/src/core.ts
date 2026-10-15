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
import { runCompletionCheck, type CheckVerdict } from "./check.ts";
import { emitGoalMessage } from "./procedure.ts";
import { createHash } from "node:crypto";
import { collectGoalEvidence } from "./evidence.ts";
import { GoalScheduler } from "./scheduler.ts";
import { loadGoalSettings, type GoalSettings } from "./settings.ts";
import { GoalStore, newGoalId, type GoalMutationOutcome } from "./store.ts";
import { budgetReached, randomToken, type GoalRecord } from "./record.ts";

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
  /** Injected so a test can run against a temporary project rather than the
   * process's real working directory. */
  projectRoot?: string;
}

export class GoalCore {
  readonly pi: ExtensionAPI;
  readonly store: GoalStore;
  readonly scheduler: GoalScheduler;

  private focusedGoalId: string | undefined;
  /** Abort for the check in flight, so focus change or shutdown stops it. */
  private checkAbort: AbortController | undefined;
  /** One neutral activity line for the below-editor surface while a check runs.
   * The line is the whole row: that surface already belongs to the running goal,
   * so a heading above it would only repeat what the position says. */
  checkProgress: string | undefined;
  /** Tool names this extension owns, re-asserted on every surface change. */
  private readonly runCheck: typeof runCompletionCheck;
  private activationGoalId: string | undefined;
  private pendingSetting: { prompt: string; goalId: string; owner: string } | undefined;

  constructor(pi: ExtensionAPI, projectRoot: string, options: GoalCoreOptions = {}) {
    this.pi = pi;
    this.store = new GoalStore({ projectRoot });
    this.runCheck = options.runCheck ?? runCompletionCheck;
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
          emitGoalMessage(this.pi, level === "error" ? "failed" : "waiting", message);
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
    const goal = this.store.readGoal(this.focusedGoalId);
    // The goal may have been cleared or completed by another session since it
    // was focused. Reporting it as still focused would let a command act on a
    // goal that no longer exists.
    if (!goal || goal.status === "complete") return undefined;
    if (goal.threadId && goal.threadId !== this.owner()) return undefined;
    return goal;
  }

  settings(ctx: ExtensionContext): GoalSettings {
    return loadGoalSettings(ctx.cwd);
  }

  /** Reload state at a session boundary: reread from disk and rebuild focus
   * from the session's own entries, so another session's work is seen and this
   * session's focus is not inherited from anywhere else. */
  restore(ctx: ExtensionContext): void {
    this.cancelGoalActivation();
    this.cancelContinuation(this.focusedGoalId ?? "");
    this.scheduler.shutdown();
    this.abortCheck(ctx);
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
    const restored = this.goal;
    if (restored?.status === "active") this.scheduler.takeover(restored);
    this.seenWork.clear();
    this.blocker = undefined;
    this.setUnmet(undefined);
    // Only this thread's persisted entries identify its goal.
  }

  focus(goalId: string, ctx: ExtensionContext, reason: GoalFocusEntry["reason"]): boolean {
    const record = this.store.readGoal(goalId);
    if (!record || (record.threadId && record.threadId !== this.owner())) {
      this.notify(ctx, "No goal is open.", "warning");
      return false;
    }
    if (this.focusedGoalId !== goalId || reason === "created") this.setUnmet(undefined);
    this.focusedGoalId = goalId;
    if (reason === "created") { this.seenWork.clear(); this.blocker = undefined; }
    this.appendFocusEntry(goalId, reason);
    this.store.apply({
      expectedGoalId: goalId,
      mutate: (goal) => goal,

    });
    this.refreshUi(ctx);
    return true;
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
    if (this.lastCtx?.hasPendingMessages()) { this.cancelContinuation(goal.id); this.scheduler.takeover(goal); return; }
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

  canChargeGoal(goal: GoalRecord): boolean {
    return (goal.status === "active" && goal.autoContinue) || this.activationGoalId === goal.id;
  }

  cancelGoalActivation(): void {
    this.activationGoalId = undefined;
    this.pendingSetting = undefined;
  }

  /** A revision under an accepted `/goal <text>` request. The user asked, but
   * the revision is what lifted the pause, so the accepted request grants that. */
  activateRequestedRevision(goalId: string, ctx: ExtensionContext): boolean | undefined {
    if (this.activationGoalId !== goalId) return undefined;
    this.activationGoalId = undefined;
    const goal = this.goal;
    if (!goal || goal.id !== goalId) return false;
    return this.scheduler.resume(goal, this.settings(ctx), "revision");
  }

  // ── checker model ───────────────────────────────────────────────────

  /** The model a child uses: the configured one, else the session's.
   *
   * A child given no model falls back to the persisted CLI default, which is a
   * different model from the session's and may be unavailable. The settings
   * already describe the configured model as used "instead of the session's", so
   * an unset model means the session's. */
  private childModel(
    configuredProvider: string | undefined,
    configuredModel: string | undefined,
    session: { provider?: string; id?: string } | undefined,
  ): string | undefined {
    if (configuredProvider && configuredModel) return `${configuredProvider}/${configuredModel}`;
    return session?.provider && session?.id ? `${session.provider}/${session.id}` : undefined;
  }

  // ── completion check ─────────────────────────────────────────────────

  get checkInFlight(): boolean {
    return this.checkAbort !== undefined;
  }

  abortCheck(ctx?: ExtensionContext): void {
    this.checkAbort?.abort();
    this.checkAbort = undefined;
    this.checkProgress = undefined;
    if (ctx) this.refreshUi(ctx);
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
    signal?: AbortSignal | boolean,
  ): Promise<CheckVerdict> {
    this.abortCheck();
    const abort = new AbortController();
    const generation = goal.scheduler?.generation;
    this.checkAbort = abort;
    const cancel = () => abort.abort();
    const toolSignal = typeof signal === "object" ? signal : undefined;
    toolSignal?.addEventListener("abort", cancel, { once: true });
    if (toolSignal?.aborted) cancel();
    this.checkProgress = "Evaluating the objective and recorded evidence...";
    this.refreshUi(ctx);
    const model = this.childModel(settings.provider, settings.model, ctx.model);
    const evidence = collectGoalEvidence(ctx.sessionManager.getBranch(), goal, this.owner());
    try {
      const result = await this.runCheck({
        objective: goal.objective,
        claim,
        contract: goal.verificationContract,
        evidence,
        cwd: ctx.cwd,
        signal: abort.signal,
        model,
      });
      const current = this.goal;
      // Account the child even when it was cancelled or superseded. Charges
      // target the same goal id, never a replacement goal, and do not certify it.
      let charged = this.store.readGoal(goal.id);
      if (charged && result.usage?.totalTokens) {
        const usage = this.store.apply({ expectedGoalId: goal.id, mutate: draft => {
          const charged = { ...draft, usage: { ...draft.usage, tokensUsed: draft.usage.tokensUsed + Math.max(0, result.usage!.totalTokens) } };
          if (!budgetReached(charged)) return charged;
          return { ...charged, status: "budget_limited", autoContinue: false,
            pauseReason: `The lifetime token cap of ${charged.tokenBudget} tokens was reached.`,
            scheduler: charged.scheduler ? { ...charged.scheduler, phase: "idle", dispatch: undefined } : undefined };
        } });
        if (!usage.ok) return { met: false, report: usage.message, error: usage.message };
        charged = usage.goal;
      }
      if (current?.id === goal.id && charged && budgetReached(charged) &&
          charged.objective === goal.objective && charged.verificationContract === goal.verificationContract) {
        this.markBudgetLimited(ctx, charged, false);
        return { met: false, report: "The goal budget was reached during the check.", error: "Budget reached." };
      }
      const changed = current?.id !== goal.id || !charged || charged.id !== goal.id || charged.objective !== goal.objective ||
        charged.verificationContract !== goal.verificationContract || charged.evidenceSince !== goal.evidenceSince ||
        charged.status !== goal.status || charged.scheduler?.generation !== generation;
      if (changed) return { met: false, report: "The goal changed; the old check result was discarded.", stale: true };
      if (abort.signal.aborted || this.checkAbort !== abort) return { met: false, report: "The completion check was cancelled.", cancelled: true };
      if (charged && budgetReached(charged)) {
        this.markBudgetLimited(ctx, charged, false);
        return { met: false, report: "The goal budget was reached during the check.", error: "Budget reached." };
      }
      if (result.error) {
        if (!this.scheduler.pause(charged!, `Completion check failed: ${result.error}`, "agent", { requireRevision: charged!.revision, notifyFailure: false })) {
          return { met: false, report: "The goal changed; the old check result was discarded.", stale: true };
        }
        this.markTurnStopped();
      } else if (!result.met) this.setUnmet(result.report);
      return result;
    } finally {
      toolSignal?.removeEventListener("abort", cancel);
      if (this.checkAbort === abort) {
        this.checkAbort = undefined;
        this.checkProgress = undefined;
        this.refreshUi(ctx);
      }
    }
  }

  /** Release only the requirements whose contract was checked. */
  completeCheckedGoal(ctx: ExtensionContext, checked: GoalRecord): GoalMutationOutcome {
    const outcome = this.store.apply({
      expectedGoalId: checked.id,
      finish: true,
      mutate: draft => {
        if (!this.scheduler.owns(draft) || budgetReached(draft) || draft.objective !== checked.objective || draft.verificationContract !== checked.verificationContract ||
            draft.evidenceSince !== checked.evidenceSince || draft.status !== checked.status ||
            draft.scheduler?.generation !== checked.scheduler?.generation) return undefined;
        return { ...draft, status: "complete", autoContinue: false };
      },
    });
    if (outcome.ok) {
      this.markTurnStopped(checked.id);
      this.cancelContinuation(checked.id);
      this.clearFocus(ctx, "completed");
      this.setUnmet(undefined);
      this.refreshUi(ctx);
    }
    return outcome;
  }

  private runPerformedWork = false;
  private creationTokens = 0;
  recordCreationUsage(tokens: number, threadId?: string): void {
    if (threadId && threadId !== this.owner()) return;
    this.creationTokens += Math.max(0, tokens);
  }
  pendingCreationTokens(): number { return this.creationTokens; }
  clearCreationUsage(): void { this.creationTokens = 0; }

  /** A provider run can contain several tool turns. Work belongs to the whole run. */
  beginRun(): void {
    this.runPerformedWork = false;
    this.creationTokens = 0;
  }

  private readonly seenWork = new Set<string>();
  noteWork(toolName: string, successful: boolean, details?: unknown, output?: unknown, args?: unknown): void {
    if (!successful || ["create_goal", "get_goal", "update_goal", "monitor_stop"].includes(toolName)) return;
    if (toolName === "monitor_start") {
      if (typeof details !== "object" || details === null || !("result" in details)) return;
      const terminal = details.result;
      if (typeof terminal !== "object" || terminal === null || !("status" in terminal) || terminal.status !== "success") return;
    }
    // A receipt is new work only once. Repeating a successful read is not a
    // reason to run forever; changing its result or making an edit is useful.
    const key = createHash("sha256").update(JSON.stringify([toolName, args, output ?? details])).digest("hex");
    if (this.seenWork.has(key)) return;
    this.seenWork.add(key);
    this.runPerformedWork = true;
    this.blocker = undefined;
  }

  performedWork(): boolean { return this.runPerformedWork; }

  requirementsChanged(): void { this.blocker = undefined; this.seenWork.clear(); this.setUnmet(undefined); }

  private blocker: { reason: string; count: number; turn: number } | undefined;
  reportBlocker(reason: string): boolean {
    const previous = this.blocker;
    const same = previous?.reason === reason;
    const count = same && previous.turn === this.turnSeq ? previous.count
      : same && previous.turn === this.turnSeq - 1 ? previous.count + 1 : 1;
    this.blocker = { reason, count, turn: this.turnSeq };
    if (count < 3) return false;
    const goal = this.goal;
    if (!goal) return false;
    const outcome = this.store.apply({ expectedGoalId: goal.id, expectedRevision: goal.revision, mutate: draft => this.scheduler.owns(draft) ? ({
      ...draft, status: "blocked", autoContinue: false, pauseReason: reason,
      scheduler: draft.scheduler ? { ...draft.scheduler, phase: "idle", dispatch: undefined, generation: randomToken() } : undefined,
    }) : undefined });
    if (outcome.ok) { this.scheduler.shutdown(); this.cancelContinuation(goal.id); this.markTurnStopped(); }
    return outcome.ok;
  }

  async pauseByUser(ctx: ExtensionContext, reason: string): Promise<boolean> {
    const goal = this.goal;
    if (!goal) return false;
    this.cancelGoalActivation(); this.abortCheck(ctx);
    if (!this.scheduler.pause(goal, reason, "user")) return false;
    this.markTurnStopped();
    if (typeof ctx.abort === "function") await ctx.abort();
    this.refreshUi(ctx);
    return true;
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

  chargeUsage(ctx: ExtensionContext, goal: GoalRecord, turnSeq: number, tokens: number, activeSeconds: number, attributed = false): GoalMutationOutcome | undefined {
    const current = this.goal;
    if (!attributed && (!current || current.id !== goal.id || !this.canChargeGoal(current))) return undefined;
    if (tokens <= 0 && activeSeconds <= 0) return undefined;
    const key = `${goal.id}:${turnSeq}`;
    if (this.chargedTurns.has(key)) return undefined;
    this.chargedTurns.add(key);
    if (this.chargedTurns.size > 1000) this.chargedTurns.clear();
    const outcome = this.store.apply({
      expectedGoalId: goal.id,
      mutate: (draft) => {
        if (!this.scheduler.owns(draft) && !(attributed && draft.threadId === goal.threadId)) return undefined;
        const charged = { ...draft, usage: {
          tokensUsed: draft.usage.tokensUsed + Math.max(0, tokens),
          activeSeconds: draft.usage.activeSeconds + Math.max(0, activeSeconds),
        } };
        if (!budgetReached(charged)) return charged;
        return { ...charged, status: "budget_limited", autoContinue: false,
          pauseReason: `The lifetime token cap of ${charged.tokenBudget} tokens was reached.`,
          scheduler: charged.scheduler ? { ...charged.scheduler, phase: "idle", dispatch: undefined } : undefined };
      },

    });
    if (outcome.ok && budgetReached(outcome.goal) && current?.id === goal.id) {
      this.markBudgetLimited(ctx, outcome.goal);
    }
    this.refreshUi(ctx);
    return outcome;
  }

  private markBudgetLimited(_ctx: ExtensionContext, goal: GoalRecord, announce = true): void {
    const outcome = this.store.apply({
      expectedGoalId: goal.id,
      mutate: (draft) => {
        // This write sets `status` directly rather than going through pause(),
        // so it carries its own ownership guard. Ownership can rotate between
        // the usage write that reaches the cap and this stop, and stopping a
        // goal this session no longer owns is a real action taken on someone
        // else's work.
        if (!this.scheduler.owns(draft)) return undefined;
        return {
          ...draft,
          status: "budget_limited",
          autoContinue: false,
          pauseReason: `The lifetime token cap of ${draft.tokenBudget} tokens was reached.`,
        };
      },

    });
    this.cancelContinuation(goal.id);
    // Report what happened, not what was attempted: a stop declined because
    // another session took the goal over must not tell this user it stopped.
    if (outcome.ok) { this.markTurnStopped(); if (announce) emitGoalMessage(this.pi, "budget reached", outcome.goal.pauseReason ?? "Token budget reached."); }
  }

  notify(_ctx: ExtensionContext, message: string, level: "info" | "warning" | "error"): void {
    emitGoalMessage(this.pi, level === "error" ? "failed" : "waiting", message);
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

  currentTurnSeconds(): number {
    return Math.max(0, Math.floor((Date.now() - this.turnStartedAt) / 1000));
  }

  /** A stopped goal ended this turn. Work tools after this are refused. */
  markTurnStopped(goalId = this.goal?.id): void {
    if (goalId) this.turnStopped = { goalId, turnSeq: this.turnSeq };
  }

  /** The goal whose disposition stopped this turn, or null. */
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
    this.setUnmet(undefined);
    this.appendFocusEntry(null, reason);
  }

  shutdown(): void {
    this.cancelGoalActivation();
    this.scheduler.shutdown();
    this.abortCheck();
    if (this.continuationTimer !== undefined) clearTimeout(this.continuationTimer);
    this.continuationTimer = undefined;
  }

  newId(): string {
    return newGoalId();
  }
}

