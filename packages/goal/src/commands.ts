/** One slash command for this thread's objective and lifecycle. */
import { deliverGoalProcedure, emitGoalMessage } from "./procedure.ts";
import type { GoalCore } from "./core.ts";
import { refreshDashboard } from "./dashboard.ts";
import { goalRequest } from "./prompt.ts";
import { goalBody, refreshGoalToolSurface } from "./tools.ts";

/** Reserved verbs, typed alone. Words after one stay a request for the model. */
const MANAGEMENT_VERBS = ["pause", "resume", "clear"] as const;

export function registerGoalCommands(core: GoalCore): void {
  core.pi.registerCommand("goal", {
    description: "Set or view this thread's goal; pause, resume, or clear it",
    handler: async (args,ctx) => {
      core.bindUi(ctx);
      const input=args.trim(); const verb=input.split(/\s+/)[0]?.toLowerCase() ?? ""; const goal=core.goal;
      // Only an exact management verb is an action. Anything with words after it is
      // the user's request, which the model turns into an objective: `clear my
      // schedule` is work to plan, not a command to clear the goal.
      const management=input === verb && (MANAGEMENT_VERBS as readonly string[]).includes(verb);
      if (!input) { emitGoalMessage(core.pi,goal ? goal.status : "no active goal",goal ? goalBody(goal) : "Use /goal <objective> to start a goal."); return; }
      if (management) {
        core.cancelGoalActivation();
        if (!goal) { emitGoalMessage(core.pi,"no active goal"); return; }
        if(verb === "pause") {
          if(await core.pauseByUser(ctx,"Paused by the user.")) emitGoalMessage(core.pi,"paused","Use /goal resume to continue.");
        } else if(verb === "resume") {
          if(core.scheduler.resume(goal,core.settings(ctx),"user")) emitGoalMessage(core.pi,"resumed");
        } else {
          core.abortCheck(ctx);
          const outcome=core.store.apply({expectedGoalId:goal.id,expectedRevision:goal.revision,mutate:d=>({...d,status:"complete",autoContinue:false,stopReason:"user",
            scheduler:d.scheduler?{...d.scheduler,phase:"idle",dispatch:undefined}:undefined})});
          if(!outcome.ok) { emitGoalMessage(core.pi,"clear not applied",outcome.message); return; }
          core.markTurnStopped(goal.id); core.clearFocus(ctx,"cleared");
          if(typeof ctx.abort === "function") await ctx.abort();
          emitGoalMessage(core.pi,"cleared");
        }
        refreshGoalToolSurface(core,ctx); refreshDashboard(core,ctx); return;
      }
      // Queue the complete request, never commit a raw additive fragment to disk.
      if (goal) { core.abortCheck(ctx); core.scheduler.takeover(goal); core.refreshUi(ctx); }
      const request=goalRequest(input);
      core.requestGoalActivation(request);
      try { deliverGoalProcedure(core.pi,request,{request:input}); }
      catch(error) { core.cancelGoalActivation(); emitGoalMessage(core.pi,"request not sent",error instanceof Error ? error.message : String(error)); }
    },
  });
}
