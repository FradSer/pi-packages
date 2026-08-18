import crypto from "node:crypto";
import { applyKeyboardState } from "./driver";
import {
  evaluateGlobalLightingState,
  removeSessionGlowState,
  writeSessionGlowState,
  type GlobalStateSummary,
  type SessionGlowRecord,
} from "./global-sessions";
import {
  KEYBOARD_STATE_DEFINITIONS,
  type KeyboardConfig,
  type KeyboardState,
} from "./types";

export class KeyboardStateMachine {
  /**
   * After this long without any user activity, a settled/unread glow state is
   * considered stale and decays back to idle instead of keeping the green light.
   * Mirrors the 5-minute staleness window used for other sessions' on-disk records
   * so the self session cannot keep unread alive indefinitely in memory.
   */
  static readonly STALE_UNREAD_MS = 5 * 60 * 1000;

  private currentState: KeyboardState = "idle";
  private isProcessing = false;
  private hasUnreadChat = false;
  private hasFatalError = false;
  private lastUserActivityAt = 0;
  private sessionId: string;
  private cwd: string;

  constructor(
    private config: KeyboardConfig,
    sessionId?: string,
    cwd?: string,
    private evalGlobalState: (id: string, record: SessionGlowRecord) => GlobalStateSummary = (id, rec) =>
      evaluateGlobalLightingState(id, rec),
    private now: () => number = () => Date.now(),
  ) {
    this.sessionId = sessionId || crypto.randomUUID();
    this.cwd = cwd || process.cwd();
  }

  public getSessionId(): string {
    return this.sessionId;
  }

  public getCwd(): string {
    return this.cwd;
  }

  public setSessionContext(sessionId?: string, cwd?: string): void {
    if (sessionId) this.sessionId = sessionId;
    if (cwd) this.cwd = cwd;
  }

  public getConfig(): KeyboardConfig {
    return { ...this.config };
  }

  public updateConfig(newConfig: Partial<KeyboardConfig>): void {
    this.config = { ...this.config, ...newConfig };
    this.applyCurrentState(true);
  }

  public getCurrentState(): KeyboardState {
    return this.currentState;
  }

  public isUnread(): boolean {
    return this.hasUnreadChat;
  }

  public hasError(): boolean {
    return this.hasFatalError;
  }

  public getStateLabel(state: KeyboardState = this.currentState): string {
    return KEYBOARD_STATE_DEFINITIONS[state]?.labelZh ?? state;
  }

  private buildSelfRecord(statusOverride?: SessionGlowRecord["status"]): SessionGlowRecord {
    // A settled/unread state that has not been refreshed by user activity within
    // the staleness window is stale: decay it to idle so a session that was left
    // unread for a long time does not keep the global green light on forever.
    if (this.hasUnreadChat && this.lastUserActivityAt > 0) {
      if (this.now() - this.lastUserActivityAt > KeyboardStateMachine.STALE_UNREAD_MS) {
        this.hasUnreadChat = false;
      }
    }

    let status: SessionGlowRecord["status"] = "idle";
    if (this.hasFatalError) {
      status = "error";
    } else if (this.isProcessing) {
      status = "running";
    } else if (this.hasUnreadChat) {
      status = "settled";
    }

    return {
      sessionId: this.sessionId,
      pid: process.pid,
      cwd: this.cwd,
      status: statusOverride ?? status,
      hasUnread: this.hasUnreadChat,
      updatedAt: this.now(),
    };
  }

  private async syncAndEvaluate(statusOverride?: SessionGlowRecord["status"]): Promise<void> {
    const record = this.buildSelfRecord(statusOverride);
    writeSessionGlowState(record);

    const summary = this.evalGlobalState(this.sessionId, record);
    await this.transitionTo(summary.effectiveState);
  }

  public async transitionTo(nextState: KeyboardState, force = false): Promise<void> {
    if (this.currentState === nextState && !force) {
      return;
    }
    this.currentState = nextState;
    await this.applyCurrentState(force);
  }

  private async applyCurrentState(force = false): Promise<void> {
    await applyKeyboardState(this.currentState, this.config);
  }

  public async onSessionStart(): Promise<void> {
    this.isProcessing = false;
    this.hasUnreadChat = false;
    this.hasFatalError = false;
    this.lastUserActivityAt = 0;
    await this.syncAndEvaluate("idle");
  }

  public async onAgentStart(): Promise<void> {
    this.isProcessing = true;
    this.hasUnreadChat = false;
    this.hasFatalError = false;
    this.lastUserActivityAt = 0;
    await this.syncAndEvaluate("running");
  }

  public async onTurnStart(): Promise<void> {
    this.isProcessing = true;
    this.hasUnreadChat = false;
    this.hasFatalError = false;
    await this.syncAndEvaluate("running");
  }

  public async onToolCall(toolName: string, _input?: Record<string, unknown>): Promise<void> {
    this.isProcessing = true;
    const isInteractive =
      toolName.includes("confirm") ||
      toolName.includes("ask") ||
      toolName.includes("prompt") ||
      toolName === "question";

    if (isInteractive) {
      await this.syncAndEvaluate("need_approval");
    } else {
      await this.syncAndEvaluate("running");
    }
  }

  public async onToolResult(): Promise<void> {
    if (this.isProcessing) {
      await this.syncAndEvaluate("running");
    }
  }

  public async onProviderResponse(status?: number): Promise<void> {
    if (typeof status === "number" && status >= 400) {
      this.hasFatalError = true;
      this.isProcessing = false;
      this.hasUnreadChat = false;
      await this.syncAndEvaluate("error");
    }
  }

  public async onMessageEnd(stopReason?: string, errorMessage?: string): Promise<void> {
    if (stopReason === "aborted") {
      // User manually stopped/cancelled session — NOT an error!
      this.isProcessing = false;
      this.hasFatalError = false;
      this.hasUnreadChat = false;
      await this.syncAndEvaluate("idle");
      return;
    }

    if (stopReason === "error" || Boolean(errorMessage)) {
      this.hasFatalError = true;
      this.isProcessing = false;
      this.hasUnreadChat = false;
      await this.syncAndEvaluate("error");
    }
  }

  public async onAgentSettled(hasError = false): Promise<void> {
    this.isProcessing = false;
    if (hasError || this.hasFatalError) {
      this.hasFatalError = true;
      this.hasUnreadChat = false;
      await this.syncAndEvaluate("error");
    } else {
      this.hasFatalError = false;
      this.hasUnreadChat = true;
      // Stamp the user-activity timestamp so the unread state can be time-bounded.
      this.lastUserActivityAt = this.lastUserActivityAt || this.now();
      await this.syncAndEvaluate("settled");
    }
  }

  /**
   * Called when user focuses the terminal window or interacts (key press / FocusIn).
   * Marks current session as read and re-evaluates global system status:
   * - If any OTHER session still has unread messages -> stays in unread_chat (green)
   * - Else if any session is running -> thinking (blue)
   * - Else -> idle (white)
   */
  public async onUserActivated(): Promise<void> {
    this.lastUserActivityAt = this.now();
    this.hasUnreadChat = false;
    this.hasFatalError = false;
    await this.syncAndEvaluate(this.isProcessing ? "running" : "idle");
  }

  public async onUserInput(): Promise<void> {
    this.lastUserActivityAt = this.now();
    this.hasUnreadChat = false;
    this.hasFatalError = false;
    this.isProcessing = true;
    await this.syncAndEvaluate("running");
  }

  public async onError(): Promise<void> {
    this.isProcessing = false;
    this.hasFatalError = true;
    this.hasUnreadChat = false;
    await this.syncAndEvaluate("error");
  }

  public async onShutdown(): Promise<void> {
    removeSessionGlowState(this.cwd, this.sessionId);
    const summary = evaluateGlobalLightingState();
    await this.transitionTo(summary.effectiveState);
  }
}
