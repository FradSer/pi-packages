import { type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { detailField, eventToolLifecycle, formatAgentTaskName, startedToolLifecycle } from "@fradser/pi-kit";
import {
  createBoardTask,
  formatBoardTaskCreation,
  hasAnnouncedFinish,
  hasTerminalReport,
  publishStateSnapshot,
  sendLeaderMessage,
  shutdownTeammate,
  spawnTeammate,
} from "./team-machine.ts";
import { listTasks, livingTeammates } from "./state.ts";
import { LEADER_RECIPIENT, SendMessageParams, TeammateShutdownParams, TeammateSpawnParams, TaskCreateParams } from "./types.ts";
import { registerTaskListTool } from "./worker.ts";
import { openTeamConsole, refreshTeamUI } from "./ui.ts";
import { discoverAgents } from "./agents.ts";
import { emptyToolCall, renderLifecycleResult } from "./tool-render.ts";

function rosterSummary(): string {
  const alive = livingTeammates();
  if (alive.length === 0) return "No living teammates.";
  return alive.map((t) => `@${t.name} (${t.agent}, ${t.status}${t.currentTaskId ? `, task ${t.currentTaskId}` : ""})`).join("\n");
}

function spawnAssignment(params: { name: string; agent: string; prompt?: string }): string {
  const prompt = params.prompt?.trim();
  if (!prompt) return "check task board";
  const normalizedPrompt = prompt.replace(/^@/, "").trim().toLowerCase();
  const name = params.name.replace(/^@/, "").toLowerCase();
  const agent = params.agent.replace(/^@/, "").toLowerCase();
  if (normalizedPrompt === name || normalizedPrompt === agent) {
    return "check task board";
  }
  return formatAgentTaskName(prompt, "check task board");
}

export function registerLeaderTools(pi: ExtensionAPI): void {
  pi.registerTool({
    name: "teammate_spawn",
    promptSnippet: "Spawn a named resident teammate",
    label: "Spawn Teammate",
    description: "Spawn one named resident teammate. Generated role definitions stay in memory by default; persist one only when the user explicitly asks to keep it for future sessions.",
    parameters: TeammateSpawnParams,
    // Canonical lifecycle rows (same as packages/monitor): empty renderCall,
    // ONE startup row owned by renderResult.
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      const params = context.args as { name: string; agent: string; prompt?: string };
      const assignment = spawnAssignment(params);
      return renderLifecycleResult(
        result,
        options,
        theme,
        context,
        startedToolLifecycle("agent", `@${params.name} started · ${assignment}`),
      );
    },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const result = spawnTeammate(params);
      if (!result.ok) throw new Error(result.error);
      refreshTeamUI(ctx);
      const kickoffNote = params.prompt?.trim()
        ? "It received your kickoff prompt and is working on it."
        : "It received the standard board-check kickoff and is running its first turn; it idles once that settles.";
      return {
        content: [{ type: "text", text: `@${params.name} is alive as ${params.agent}.\n${kickoffNote}\n\n${rosterSummary()}` }],
        details: { started: true },
      };
    },
  });

  pi.registerTool({
    name: "teammate_shutdown",
    promptSnippet: "Shut down a resident teammate",
    label: "Shutdown Teammate",
    description: "Gracefully stop one named teammate. Its claimed task returns to the board; its worktree diff is captured before teardown.",
    parameters: TeammateShutdownParams,
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      const name = String((context.args as { name?: string }).name ?? "");
      // The finish entry already announced this end of life (or its terminal
      // report is queued to); a second event row is noise.
      if (hasAnnouncedFinish(name) || hasTerminalReport(name)) return { render: () => [], invalidate: () => {} };
      return renderLifecycleResult(result, options, theme, context, eventToolLifecycle(
        "agent",
        `@${name} shut down`,
        {},
      ));
    },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const result = await shutdownTeammate(params.name);
      if (!result.ok) throw new Error(result.error);
      refreshTeamUI(ctx);
      return { content: [{ type: "text", text: result.body }], details: {} };
    },
  });

  pi.registerTool({
    name: "send_message",
    promptSnippet: "Send a message to a teammate",
    label: "Send Message",
    description: "The only messaging primitive. Address a living teammate by name; working teammates receive a steer immediately and idle teammates wake with the message.",
    parameters: SendMessageParams,
    // Canonical lifecycle rows (same as packages/monitor): empty call slot,
    // ONE delivery row owned by renderResult.
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      const to = String((context.args as { to?: string }).to ?? "");
      const outcome = detailField<"steered" | "queued" | "not-sent">(result.details, "outcome") ?? "queued";
      const subject = outcome === "not-sent" ? "terminal report available" : outcome;
      return renderLifecycleResult(result, options, theme, context, eventToolLifecycle(
        "message",
        subject,
        { label: `to @${to}`, detailLimit: outcome === "not-sent" ? "all" : undefined },
      ));
    },
    async execute(_toolCallId, params) {
      if (params.to === LEADER_RECIPIENT) throw new Error('The leader cannot send a message to itself.');
      const result = sendLeaderMessage(params.to, params.message, {
        reopen: params.reopen,
        resources: params.resources,
      });
      if (!result.ok) throw new Error(result.error);
      if (result.outcome === "not-sent") {
        return {
          content: [{
            type: "text",
            text: [
              "ROUTING · not sent",
              "NEXT · No new message was delivered. Read the recorded report below; use reopen=true only for a distinct new assignment.",
              `NOTE · @${params.to} already sent a terminal report. Delivery to your context is automatic; asking it to resend produces a duplicate leader turn.`,
              `RECORDED TERMINAL REPORT · ${result.terminalReport}`,
            ].join("\n"),
          }],
          details: { outcome: "not-sent", terminalReportAvailable: true },
        };
      }
      const action = result.outcome === "steered"
        ? "active control stream accepted the steer"
        : "harness will deliver the queued message on the next wake-up";
      let text = `MESSAGING\n${result.outcome.toUpperCase()} · to=@${params.to}\nNEXT · ${action}`;
      // A stray status field (copied from worker report patterns) must not
      // block delivery — it carries no meaning on leader-sent messages.
      if (params.status) text += `\nNOTE · status ignored for leader-directed steering`;
      if (result.priorTerminalReport) {
        text += `\nNOTE · @${params.to} already sent a terminal report (below); it reaches your context automatically. A steer asking it to repeat that report produces a duplicate delivery — use reopen only for a distinct new assignment.`;
        text += `\nPRIOR TERMINAL REPORT · ${result.priorTerminalReport}`;
      }
      return {
        content: [{ type: "text", text }],
        details: { outcome: result.outcome },
      };
    },
  });

  pi.registerTool({
    name: "task_create",
    promptSnippet: "Create a shared board task",
    label: "Create Task",
    description: "Create one pending task on the current session board. Existing idle teammates are notified immediately and may self-claim it; this tool never spawns teammates. An optional verify prompt gates completion through a fresh reviewer.",
    parameters: TaskCreateParams,
    // Canonical lifecycle rows (same as packages/monitor): empty call slot,
    // ONE created row owned by renderResult.
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      const subject = String((context.args as { subject?: string }).subject ?? "");
      return renderLifecycleResult(result, options, theme, context, eventToolLifecycle(
        "board",
        subject,
        { label: "created" },
      ));
    },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const tasks = listTasks();
      const referenced = [...(params.dependsOn ?? []), ...(params.supersedes ?? [])];
      if (referenced.some((id) => !tasks.some((task) => task.id === id))) {
        throw new Error(`Unknown task id in [${referenced.join(", ")}].`);
      }
      const created = createBoardTask(params);
      if (!created.ok) throw new Error(created.error);
      refreshTeamUI(ctx);
      return {
        content: [{ type: "text", text: formatBoardTaskCreation(params.subject, created) }],
        details: {
          notifiedTeammates: created.notifiedTeammates,
          livingTeammates: created.livingTeammates,
          claimable: created.claimable,
          supersededTaskIds: created.supersededTaskIds,
        },
      };
    },
  });

  registerTaskListTool(pi);
}

function teamStatusSummary(): string {
  const roles = [...discoverAgents().keys()].map((name) => `@${name}`);
  const rolesLine = roles.length > 0
    ? `${roles.length} persistent agent role${roles.length === 1 ? "" : "s"}: ${roles.join(", ")}`
    : "No agent roles discovered.";
  return `${rosterSummary()}\n${rolesLine}`;
}

export function registerTeamCommand(pi: ExtensionAPI): void {
  pi.registerCommand("agent-teams", {
    description: "Agent Teams management console: session teammates and persistent agent roles",
    handler: async (_args, ctx) => {
      publishStateSnapshot();
      if (ctx.mode !== "tui") { ctx.ui.notify(teamStatusSummary(), "info"); return; }
      await openTeamConsole(ctx);
      refreshTeamUI(ctx);
    },
  });
}

