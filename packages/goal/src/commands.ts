/** One slash command for the current thread's goal. */
import { notifyPi } from "@fradser/pi-kit";
import type { GoalCore } from "./core.ts";
import { clearDashboard, refreshDashboard } from "./dashboard.ts";
import { goalRequest, statusLabel } from "./prompt.ts";
import { nowIso } from "./record.ts";
import { refreshGoalToolSurface } from "./tools.ts";

export function registerGoalCommands(core: GoalCore): void {
  core.pi.registerCommand("goal", {
    description: "Set or view this thread's goal; pause, resume, or clear it",
    handler: async (args, ctx) => {
      core.bindUi(ctx);
      const input = args.trim();
      const action = input.toLowerCase();
      if (!input) {
        const goal = core.goal;
        notifyPi(ctx.ui, goal ? [
          "Goal", `Status: ${statusLabel(goal)}`, `Objective: ${goal.objective}`,
          goal.verificationContract ? `Completion conditions: ${goal.verificationContract}` : "",
          goal.pauseReason ? `Reason: ${goal.pauseReason}` : "",
          `Tokens used: ${goal.usage.tokensUsed}`,
          goal.tokenBudget !== undefined ? `Token budget: ${goal.tokenBudget}` : "",
          `Commands: /goal ${goal.status === "active" ? "pause" : "resume"}, /goal clear`,
        ].filter(Boolean).join("\n") : "No goal is set for this thread. Use /goal <objective and completion conditions>.", "info");
        return;
      }
      if (action === "pause" || action === "resume" || action === "clear") {
        core.cancelGoalActivation();
        const goal = core.goal;
        if (!goal) {
          notifyPi(ctx.ui, "No goal is set for this thread.", "warning");
          return;
        }
        if (action === "pause") {
          core.abortCheck();
          if (core.scheduler.pause(goal, "Paused by the user.", "user")) {
            notifyPi(ctx.ui, `Goal ${goal.id} paused. Use /goal resume to continue.`, "info");
          }
        } else if (action === "resume") {
          if (core.scheduler.resume(goal, core.settings(ctx))) {
            notifyPi(ctx.ui, `Goal ${goal.id} resumed; one continuation is authorized.`, "info");
          }
        } else {
          if (!ctx.hasUI) {
            notifyPi(ctx.ui, "Clearing a goal requires interactive confirmation.", "warning");
            return;
          }
          const choice = await ctx.ui.select(`Clear goal ${goal.id}?`, ["Clear goal", "Keep goal"]);
          if (choice !== "Clear goal") return;
          core.abortCheck();
          core.cancelContinuation(goal.id);
          const outcome = core.store.apply({
            expectedGoalId: goal.id, archive: true,
            mutate: draft => ({ ...draft, status: "complete", autoContinue: false }),
            ledger: [{ type: "goal_cleared", goalId: goal.id, reason: "user", at: nowIso() }],
          });
          if (!outcome.ok) { notifyPi(ctx.ui, outcome.message, "error"); return; }
          core.scheduler.shutdown();
          core.clearFocus(ctx, "cleared");
          clearDashboard(ctx);
          notifyPi(ctx.ui, `Goal ${goal.id} cleared and archived.`, "info");
        }
        refreshGoalToolSurface(core, ctx);
        refreshDashboard(core, ctx);
        return;
      }
      // Full-text matching keeps “clear my schedule” an objective, not an action.
      if (!ctx.isIdle() || ctx.hasPendingMessages()) {
        notifyPi(ctx.ui, "Pi is processing another request. Wait for it to finish, then enter /goal again.", "warning");
        return;
      }
      const request = goalRequest(input);
      core.requestGoalActivation(request);
      try {
        core.pi.sendUserMessage(request);
      } catch (error) {
        core.cancelGoalActivation();
        notifyPi(ctx.ui, `The goal request was not sent: ${error instanceof Error ? error.message : String(error)}`, "error");
      }
    },
  });
}
