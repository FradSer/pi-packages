import { applyKeyboardState } from "./driver";
import { hasOtherRunningSessions } from "./global-sessions";
import {
  KEYBOARD_STATE_DEFINITIONS,
  type KeyboardConfig,
  type KeyboardState,
} from "./types";

export class KeyboardStateMachine {
  private currentState: KeyboardState = "idle";
  private isProcessing = false;
  private hasUnreadChat = false;
  private hasFatalError = false;

  constructor(
    private config: KeyboardConfig,
    private checkOtherRunning: () => boolean = () => hasOtherRunningSessions(),
  ) {}

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

    if (this.checkOtherRunning()) {
      await this.transitionTo("thinking");
    } else {
      await this.transitionTo("idle");
    }
  }

  public async onAgentStart(): Promise<void> {
    this.isProcessing = true;
    this.hasUnreadChat = false;
    this.hasFatalError = false;
    await this.transitionTo("thinking");
  }

  public async onTurnStart(): Promise<void> {
    this.isProcessing = true;
    this.hasUnreadChat = false;
    this.hasFatalError = false;
    await this.transitionTo("thinking");
  }

  public async onToolCall(toolName: string, _input?: Record<string, unknown>): Promise<void> {
    this.isProcessing = true;
    const isInteractive =
      toolName.includes("confirm") ||
      toolName.includes("ask") ||
      toolName.includes("prompt") ||
      toolName === "question";

    if (isInteractive) {
      await this.transitionTo("need_approval");
    } else {
      await this.transitionTo("thinking");
    }
  }

  public async onToolResult(): Promise<void> {
    if (this.isProcessing) {
      await this.transitionTo("thinking");
    }
  }

  public async onProviderResponse(status?: number): Promise<void> {
    if (typeof status === "number" && status >= 400) {
      this.hasFatalError = true;
      this.isProcessing = false;
      this.hasUnreadChat = false;
      await this.transitionTo("error");
    }
  }

  public async onMessageEnd(stopReason?: string, errorMessage?: string): Promise<void> {
    if (stopReason === "error" || stopReason === "aborted" || Boolean(errorMessage)) {
      this.hasFatalError = true;
      this.isProcessing = false;
      this.hasUnreadChat = false;
      await this.transitionTo("error");
    }
  }

  public async onAgentSettled(hasError = false): Promise<void> {
    this.isProcessing = false;
    if (hasError || this.hasFatalError) {
      this.hasFatalError = true;
      this.hasUnreadChat = false;
      await this.transitionTo("error");
    } else {
      this.hasUnreadChat = true;
      await this.transitionTo("unread_chat");
    }
  }

  public async onUserActivated(): Promise<void> {
    if (!this.hasUnreadChat) {
      return;
    }
    this.hasUnreadChat = false;

    if (this.hasFatalError) {
      await this.transitionTo("error");
      return;
    }

    if (this.isProcessing || this.checkOtherRunning()) {
      await this.transitionTo("thinking");
    } else {
      await this.transitionTo("idle");
    }
  }

  public async onUserInput(): Promise<void> {
    this.hasUnreadChat = false;
    this.hasFatalError = false;
    if (this.isProcessing || this.checkOtherRunning()) {
      await this.transitionTo("thinking");
    } else {
      await this.transitionTo("idle");
    }
  }

  public async onError(): Promise<void> {
    this.isProcessing = false;
    this.hasFatalError = true;
    this.hasUnreadChat = false;
    await this.transitionTo("error");
  }

  public async onShutdown(): Promise<void> {
    if (this.checkOtherRunning()) {
      await this.transitionTo("thinking");
    } else {
      await this.transitionTo("idle");
    }
  }
}
