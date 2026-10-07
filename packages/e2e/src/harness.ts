import type {
  AgentBeforeSettleEvent,
  AgentBeforeSettleEventResult,
  ExtensionAPI,
  ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { notifyPi } from "@fradser/pi-kit";
import { injectE2ECapabilityNote } from "./presence.ts";
import type { Verdict } from "./types.ts";

export const E2E_CHECKPOINT_MESSAGE_TYPE = "pi-e2e-checkpoint";
export const MAX_E2E_CONTINUATIONS = 2;

export interface E2EHarnessState {
  lastVerdict?: Verdict;
  verdictInCurrentTurn: boolean;
  userRequestedVerification: boolean;
  featureFilesModified: Set<string>;
  continuations: number;
}

export class E2EGate {
  private state: E2EHarnessState = {
    verdictInCurrentTurn: false,
    userRequestedVerification: false,
    featureFilesModified: new Set(),
    continuations: 0,
  };

  reset(): void {
    this.state = {
      lastVerdict: undefined,
      verdictInCurrentTurn: false,
      userRequestedVerification: false,
      featureFilesModified: new Set(),
      continuations: 0,
    };
  }

  recordVerdict(verdict: Verdict): void {
    this.state.lastVerdict = verdict;
    this.state.verdictInCurrentTurn = true;
    if (verdict.status === "fulfilled") {
      this.state.userRequestedVerification = false;
    }
  }

  recordUserPrompt(text: string): void {
    // Invalidate stale verdicts from previous turns
    this.state.lastVerdict = undefined;
    this.state.verdictInCurrentTurn = false;
    this.state.continuations = 0;

    // Check for negative/read-only requests to avoid false positives
    const isNegativeOrReview = /(?:do not|don't|no|never|skip|without|不要|别|不跑|仅审查|只审查|仅看|只看).*?(?:run|execute|verify|test|测试|验证|运行|跑)/i.test(text);
    if (isNegativeOrReview) {
      this.state.userRequestedVerification = false;
      return;
    }

    // Positive request to run e2e / acceptance testing
    const isE2ERequest = /(?:(?:run|test|verify|check|验证|运行|测试|跑).*?(?:e2e|acceptance|验收|\.feature|端到端)|(?:e2e|acceptance|验收|端到端).*?(?:test|run|verify|check|测试|验证|运行|跑))/i.test(text);
    this.state.userRequestedVerification = isE2ERequest;
  }

  recordToolResult(toolName: string, input: Record<string, unknown>): void {
    if (toolName === "edit" || toolName === "write") {
      const targetPath = String(input["path"] ?? "");
      if (targetPath.endsWith(".feature")) {
        this.state.featureFilesModified.add(targetPath);
      }
    }
  }

  /**
   * The harness-level checkpoint evaluated before an agent turn settles.
   *
   * Intervenes in two actionable cases:
   * 1. A scenario verification was executed in the current turn and failed (or needs review) — forces the
   *    agent to address the unmet clauses rather than abandoning them.
   * 2. The user explicitly asked for e2e / acceptance testing, code was touched,
   *    but no verification was ever executed.
   */
  checkBeforeSettle(
    event: AgentBeforeSettleEvent,
    _ctx: ExtensionContext,
  ): AgentBeforeSettleEventResult | undefined {
    // If the run was cancelled or errored, do not force continuation.
    if (event.outcome !== "completed") return undefined;

    const { lastVerdict, verdictInCurrentTurn, userRequestedVerification, continuations } = this.state;

    // Case 1: Verification executed in this turn failed or needs review
    if (verdictInCurrentTurn && lastVerdict && lastVerdict.status !== "fulfilled") {
      if (continuations < MAX_E2E_CONTINUATIONS) {
        this.state.continuations += 1;
        const unmet = lastVerdict.clauses
          .filter((c) => c.status !== "met")
          .map((c) => `- #${c.clause}: "${c.text}" [${c.status}]${c.detail ? ` (${c.detail})` : ""}`)
          .join("\n");

        const message = [
          `[e2e verification checkpoint]`,
          `Scenario "${lastVerdict.scenario}" in ${lastVerdict.feature} did not pass:`,
          `Status: ${lastVerdict.status} (exit ${lastVerdict.exitCode}).`,
          `Reason: ${lastVerdict.reason}.`,
          `Unmet / unjudged clauses:`,
          unmet,
          `Fix the implementation to satisfy the acceptance criteria, or run e2e_verify again before completing.`,
        ].join("\n");

        return {
          continue: true,
          entries: [
            ...event.entries,
            {
              type: "custom_message",
              customType: E2E_CHECKPOINT_MESSAGE_TYPE,
              content: message,
              display: true,
              details: { verdict: lastVerdict },
            },
          ],
        };
      }
      // Reached continuation limit: do not force further turns, but record that verification is blocked
      return undefined;
    }

    // Case 2: User explicitly requested e2e verification, but none was run in this turn
    if (userRequestedVerification && !lastVerdict && continuations < 1) {
      this.state.continuations += 1;
      const message = [
        `[e2e verification checkpoint]`,
        `Acceptance/E2E verification was requested, but e2e_verify has not been executed yet.`,
        `Please run e2e_verify on the relevant .feature scenario to confirm fulfillment before completing.`,
      ].join("\n");

      return {
        continue: true,
        entries: [
          ...event.entries,
          {
            type: "custom_message",
            customType: E2E_CHECKPOINT_MESSAGE_TYPE,
            content: message,
            display: true,
            details: { missing: true },
          },
        ],
      };
    }

    return undefined;
  }

  notifyOnSettled(ctx: ExtensionContext): void {
    const { lastVerdict } = this.state;
    if (lastVerdict?.status === "fulfilled") {
      notifyPi(ctx.ui, `e2e verification passed: ${lastVerdict.scenario}`, "info");
    }
  }
}

/**
 * Registers all e2e harness hooks:
 * 1. `context_with_system` for prompt injection.
 * 2. `input` and `tool_result` for session tracking.
 * 3. `agent_before_settle` for harness enforcement.
 * 4. `agent_settled` for UI notification.
 */
export function registerE2EHarness(pi: ExtensionAPI, gate: E2EGate): void {
  // 1. Prompt injection: stable, bounded capability note after system prompt
  pi.on("context_with_system", async (event) => ({
    messages: injectE2ECapabilityNote(event.messages),
  }));

  // 2. Lifecycle resets
  pi.on("session_start", () => gate.reset());
  pi.on("session_shutdown", () => gate.reset());

  // 3. User intent observation
  pi.on("input", (event) => {
    if (event.source !== "extension") {
      gate.recordUserPrompt(event.text);
    }
  });

  // 4. Tool observation
  pi.on("tool_result", (event) => {
    gate.recordToolResult(event.toolName, event.input as Record<string, unknown>);
  });

  // 5. Harness confirmation gate before settling
  pi.on("agent_before_settle", (event, ctx) => gate.checkBeforeSettle(event, ctx));

  // 6. Final settled notification
  pi.on("agent_settled", (_event, ctx) => gate.notifyOnSettled(ctx));
}
