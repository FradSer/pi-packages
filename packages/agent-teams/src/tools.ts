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
import { createRun, getRun, getSummary, listNodes, markRunCompletionDelivered, retryRun, MAX_FANOUT_ITEMS } from "./state";
import { TeammateCancelParams, TeammateFanoutParams, TeammateLeaderMessageParams, TeammateRetryParams, TeammateRunParams } from "./types";
import { sendWorkerSteer } from "./spawner";
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

function resolveTargetNode(target: string): { node: import("./types").Node } | undefined {
  return listNodes().map((node) => ({ node })).find(({ node }) => node.id === target || node.workerKey === target);
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
        summarize: params.summarize,
        summaryAgent: params.summaryAgent,
        nodes: params.tasks.map((task) => ({
          id: task.id,
          agent: task.agent,
          prompt: task.prompt,
          paths: task.paths,
          access: task.access ?? "read",
          model: task.model,
          mode: task.mode,
          turnBudget: task.turnBudget,
          forkContext: task.forkContext,
          inputBindings: task.inputBindings,
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
          content: [],
          details: {},
        };
      }
      return { content: [{ type: "text", text: await gatherForeground(run.id, signal) }], details: {} };
    },
  });

  pi.registerTool({
    name: "teammate_fanout",
    promptSnippet: "Fan out a completed node's structured array output",
    label: "Fan Out Tasks",
    description: "Leader-only bounded fanout. Validates a completed structured array before creating a separate child run.",
    parameters: TeammateFanoutParams,
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const source = getRun(params.runId)?.nodes[params.nodeId];
      if (!source || source.status !== "completed") throw new Error("Fanout source must be a completed node.");
      if (!Array.isArray(source.structuredOutput)) throw new Error("Fanout source must be a structured array.");
      if (source.structuredOutput.length > MAX_FANOUT_ITEMS) throw new Error(`Fanout is limited to ${MAX_FANOUT_ITEMS} items.`);
      const cwd = ctx.cwd ?? process.cwd();
      const dctx = dispatchContext(ctx);
      ensureRunContext(dctx);
      const tasks = source.structuredOutput.map((item, index) => ({
        id: `${params.nodeId}-${index + 1}`,
        agent: params.agent,
        prompt: `${params.prompt}\n\nFanout item:\n${JSON.stringify(item)}`,
        paths: params.paths,
        access: params.access ?? "read" as const,
        model: params.model,
        mode: "json" as const,
        turnBudget: params.turnBudget,
        dependsOn: [],
      }));
      if (!resolveAgent(params.agent, cwd)) throw new Error(`Agent "${params.agent}" not found.`);
      const created = createRun({ cwd, concurrency: params.concurrency ?? 4, worktree: false, background: params.background ?? true, summarize: true, nodes: tasks });
      if (!created.ok) throw new Error(created.error ?? "Failed to create fanout run.");
      publishStateSnapshot();
      scheduleRun(created.run.id, dctx);
      return { content: [{ type: "text", text: `Started fanout run [${created.run.id}] with ${tasks.length} item(s).` }], details: {} };
    },
  });

  pi.registerTool({
    name: "teammate_message",
    promptSnippet: "Send a runtime steer to a running RPC teammate",
    label: "Message Teammate",
    description: "Leader-only runtime steer. Sends through the existing teammate_message protocol to a running RPC worker; no message is available for JSON-mode workers.",
    parameters: TeammateLeaderMessageParams,
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      if (!params.target.includes(":")) throw new Error("Target must be a run-qualified worker key.");
      const target = resolveTargetNode(params.target);
      if (!target?.node.spawn || target.node.status !== "running" || target.node.spawn.mode !== "rpc") {
        throw new Error("Target worker is not a running RPC teammate.");
      }
      const sent = sendWorkerSteer(target.node.workerKey, params.body);
      if (!sent) throw new Error("Target worker steering stream is unavailable.");
      return { content: [{ type: "text", text: `Steer sent to ${target.node.workerKey}.` }], details: {} };
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
