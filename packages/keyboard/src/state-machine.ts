import { applyKeyboardState } from "./driver";
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

  constructor(private config: KeyboardConfig) {}

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
    await this.transitionTo("idle");
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

  public async onToolCall(toolName: string, input?: Record<string, unknown>): Promise<void> {
    this.isProcessing = true;
    // Check if tool implies an interactive question / approval
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
    // Normal tool execution results (including bash non-zero exit codes or test failures)
    // are part of normal agent reasoning and loop execution — they do NOT trigger an error state.
    if (this.isProcessing) {
      await this.transitionTo("thinking");
    }
  }

  public async onMessageEnd(stopReason?: string): Promise<void> {
    if (stopReason === "error") {
      this.hasFatalError = true;
      this.isProcessing = false;
      this.hasUnreadChat = false;
      await this.transitionTo("error");
    }
  }

  public async onAgentSettled(hasError = false): Promise<void> {
    this.isProcessing = false;
    if (hasError || this.hasFatalError) {
      this.hasUnreadChat = false;
      await this.transitionTo("error");
    } else {
      this.hasUnreadChat = true;
      await this.transitionTo("unread_chat");
    }
  }

  public async onUserInput(): Promise<void> {
    this.hasUnreadChat = false;
    this.hasFatalError = false;
    if (this.isProcessing) {
      await this.transitionTo("thinking");
    } else {
      await this.transitionTo("idle");
    }
  }

  public async onError(): Promise<void> {
    this.isProcessing = false;
    this.hasFatalError = true;
    await this.transitionTo("error");
  }

  public async onShutdown(): Promise<void> {
    await this.transitionTo("idle");
  }
}
