/** One slash command for the current thread's goal. */
import { notifyPi } from "@fradser/pi-kit";
import { deliverGoalProcedure } from "./procedure.ts";
import type { GoalCore } from "./core.ts";
import { clearDashboard, refreshDashboard } from "./dashboard.ts";
import { goalRequest, statusLabel } from "./prompt.ts";
import { nowIso } from "./record.ts";
import { applyRevision, refreshGoalToolSurface } from "./tools.ts";

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
            notifyPi(ctx.ui, "Goal paused. Use /goal resume to continue.", "info");
          }
        } else if (action === "resume") {
          if (core.scheduler.resume(goal, core.settings(ctx), "user")) {
            notifyPi(ctx.ui, "Goal resumed; one continuation is authorized.", "info");
          }
        } else {
          if (!ctx.hasUI) {
            notifyPi(ctx.ui, "Clearing a goal requires interactive confirmation.", "warning");
            return;
          }
          const choice = await ctx.ui.select("Clear this goal?", ["Clear goal", "Keep goal"]);
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
          notifyPi(ctx.ui, "Goal cleared and archived.", "info");
        }
        refreshGoalToolSurface(core, ctx);
        refreshDashboard(core, ctx);
        return;
      }
      // Full-text matching keeps “clear my schedule” an objective, not an action.
      if (!ctx.isIdle() || ctx.hasPendingMessages()) {
        // A goal actually being pursued takes the new text as a revision
        // rather than a rejection: the user is redirecting work under way, and
        // the loop picks the new objective up on its next turn. A paused goal
        // has nothing running, so retyping there must not silently rewrite it
        // while something else is in flight.
        const active = core.goal;
        if (!active || active.status !== "active" || !active.autoContinue) {
          notifyPi(ctx.ui, "Pi is processing another request. Wait for it to finish, then enter /goal again.", "warning");
          return;
        }
        // Routed through the same writer as `update_goal`, so a revision from
        // the command cannot skip what a revision from the tool does: prompt
        // prose, the evidence boundary and the refusal count move together.
        const revised = applyRevision(core.store, active.id, input);
        if (!revised.ok) { notifyPi(ctx.ui, revised.message, "error"); return; }
        refreshDashboard(core, ctx);
        // One lifecycle row for a revision under way. The model already runs,
        // so this row is display plus a follow-up turn, not a new prompt.
        try {
          const revisionRequest = goalRequest(input);
          core.requestGoalActivation(revisionRequest);
          deliverGoalProcedure(core.pi, revisionRequest, { request: input });
        } catch {
          core.cancelGoalActivation();
        }
        notifyPi(ctx.ui, "Goal updated. The work continues on it.", "info");
        return;
      }
      const request = goalRequest(input);
      core.requestGoalActivation(request);
      try {
        deliverGoalProcedure(core.pi, request, { request: input });
      } catch (error) {
        core.cancelGoalActivation();
        notifyPi(ctx.ui, `The goal request was not sent: ${error instanceof Error ? error.message : String(error)}`, "error");
      }
    },
  });
}
