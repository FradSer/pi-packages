import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { discoverAgents, resolveAgent } from "./agents";
import {
  applyWorkerEvents,
  buildRunSummary,
  cancelNodeAndTerminate,
  cancelRunAndTerminate,
  ensureRunContext,
  publishStateSnapshot,
  scheduleRun,
  type DispatchCtx,
} from "./run-machine";
import { createRun, getRun, getSummary, markRunCompletionDelivered, retryRun } from "./state";
import { TeammateCancelParams, TeammateRetryParams, TeammateRunParams } from "./types";
import { ensureTeamWidget, openTeamConsole, refreshTeamUI } from "./ui";

function dispatchContext(ctx: ExtensionContext): DispatchCtx {
  return { ui: ctx.ui, sessionManager: ctx.sessionManager, cwd: ctx.cwd };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function gatherForeground(runId: string, signal: AbortSignal | undefined): Promise<string> {
  const foregroundTimeoutMs = 5 * 60 * 1000;
  const deadline = Date.now() + foregroundTimeoutMs;
  while (true) {
    applyWorkerEvents();
    const run = getRun(runId);
    if (!run || run.status !== "running") break;
    if (signal?.aborted) {
      run.background = true;
      run.completionNotified = false;
      publishStateSnapshot();
      throw new Error(`Run [${runId}] continues in the background — workers will message team-leader upon completion.`);
    }
    if (Date.now() >= deadline) {
      run.background = true;
      run.completionNotified = false;
      publishStateSnapshot();
      return `Run [${runId}] is still running after ${Math.round(foregroundTimeoutMs / 1000)}s — detached to background. Workers will message team-leader upon completion.`;
    }
    await sleep(150);
  }
  markRunCompletionDelivered(runId);
  publishStateSnapshot();
  return buildRunSummary(runId);
}

export function registerLeaderTools(pi: ExtensionAPI): void {
  pi.registerTool({
    name: "teammate_run",
    promptSnippet: "Dispatch a dependency-aware task graph in one call",
    label: "Run Tasks",
    description: "Dispatch a dependency-aware task graph in one call. Root nodes start immediately; downstream nodes auto-start after dependencies complete. Concurrency is bounded per run and across the session. Teammates run in the background by default and deliver completion through a follow-up. Do not sleep to wait.",
    parameters: TeammateRunParams,
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const cwd = params.cwd ?? ctx.cwd ?? process.cwd();
      const dctx = dispatchContext(ctx);
      ensureRunContext(dctx);
      ensureTeamWidget(ctx);
      for (const task of params.tasks) {
        if (!resolveAgent(task.agent, cwd)) {
          const available = [...discoverAgents(cwd).keys()].join(", ");
          throw new Error(`Agent "${task.agent}" not found in any scope. Available agents: ${available || "(none)"}.`);
        }
      }
      const created = createRun({
        cwd,
        concurrency: params.concurrency ?? 4,
        worktree: params.worktree ?? false,
        background: params.background ?? true,
        timeoutMs: params.timeoutMs,
        summarize: params.summarize,
        summaryAgent: params.summaryAgent,
        nodes: params.tasks.map((task) => ({
          id: task.id,
          agent: task.agent,
          prompt: task.prompt,
          paths: task.paths,
          access: task.access ?? "read",
          model: task.model,
          timeoutMs: task.timeoutMs,
          dependsOn: task.dependsOn ?? [],
        })),
      });
      if (!created.ok) throw new Error(created.error ?? "Failed to create run.");
      const run = created.run;
      publishStateSnapshot();
      refreshTeamUI(ctx);
      scheduleRun(run.id, dctx);

      if (run.background) {
        return {
          content: [{ type: "text", text: `Started run [${run.id}] "${Object.keys(run.nodes).length} node(s)" — background.\nConcurrency: ${run.concurrency} | Worktree: ${run.worktree ? "yes" : "no"}\n\nWorkers will report their deliverables through the automatic completion follow-up. Do not sleep to wait.` }],
          details: {},
        };
      }
      return { content: [{ type: "text", text: await gatherForeground(run.id, signal) }], details: {} };
    },
  });

  pi.registerTool({
    name: "teammate_cancel",
    promptSnippet: "Cancel a run and stop its workers",
    label: "Cancel Run",
    description: "Cancel a run or one node. Running workers receive SIGTERM with bounded SIGKILL escalation; pending nodes are cancelled.",
    parameters: TeammateCancelParams,
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const dctx = dispatchContext(ctx);
      ensureRunContext(dctx);
      const result = params.nodeId
        ? await cancelNodeAndTerminate(params.runId, params.nodeId, dctx)
        : await cancelRunAndTerminate(params.runId, dctx);
      if (!result.ok) throw new Error(result.error);
      return { content: [{ type: "text", text: params.nodeId
        ? `Node [${params.runId}/${params.nodeId}] cancelled — the rest of the run continues.`
        : `Run [${params.runId}] cancelled — pending nodes were cancelled and running workers were stopped.` }], details: {} };
    },
  });

  pi.registerTool({
    name: "teammate_retry",
    promptSnippet: "Retry the failed or cancelled nodes of a settled run",
    label: "Retry Run Nodes",
    description: "Retry failed and cancelled nodes of a settled run without re-running completed nodes.",
    parameters: TeammateRetryParams,
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const dctx = dispatchContext(ctx);
      ensureRunContext(dctx);
      const retried = retryRun(params.runId, params.nodeIds);
      if (!retried.ok) throw new Error(retried.error ?? "Failed to retry run.");
      publishStateSnapshot();
      scheduleRun(params.runId, dctx);
      refreshTeamUI(ctx);
      return { content: [{ type: "text", text: `Run [${params.runId}] retried — reset ${retried.reset.length} node(s): ${retried.reset.join(", ")}. Completed nodes are retained.` }], details: {} };
    },
  });
}

export function registerTeamCommand(pi: ExtensionAPI): void {
  pi.registerCommand("teammate", {
    description: "Open the full-screen teammate team console: run/node status, node details, interrupt/stop",
    handler: async (_args, ctx) => {
      if (ctx.mode !== "tui") {
        ctx.ui.notify(getSummary() ?? "No runs yet — dispatch work with teammate_run.", "info");
        return;
      }
      await openTeamConsole(ctx);
      refreshTeamUI(ctx);
    },
  });
}
