import { keyHint, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { formatAgentMessagePrefix, formatAgentTaskName, formatExpandHint, formatToolEventLabel, safeDisplayText } from "@fradser/pi-kit";
import {
  createBoardTask,
  formatSilenceDuration,
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
import { Text, truncateToWidth } from "@earendil-works/pi-tui";

function rosterSummary(): string {
  const alive = livingTeammates();
  if (alive.length === 0) return "No living teammates.";
  return alive.map((t) => `@${t.name} (${t.agent}, ${t.status}${t.currentTaskId ? `, task ${t.currentTaskId}` : ""})`).join("\n");
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
    renderCall: () => new Text("", 0, 0),
    renderResult(result, _options, theme, context) {
      const text = result.content[0]?.type === "text" ? (result.content[0] as { type: string; text: string }).text : "";
      if (context.isError) {
        return new Text(theme.fg("error", text.split("\n")[0] || "Failed to spawn teammate."), 0, 0);
      }
      const params = context.args as { name: string; agent: string; prompt?: string };
      const line = `${theme.fg("toolTitle", theme.bold(formatToolEventLabel("started", "", "agent").trimEnd()))} ${theme.fg("accent", `@${params.name}`)} ${theme.fg("dim", "·")} ${theme.fg("customMessageText", theme.bold(formatAgentTaskName(params.prompt ?? "", params.name)))}`;
      return {
        render: (width: number) => width > 0 ? [truncateToWidth(line, width)] : [],
        invalidate: () => {},
      };
    },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const result = spawnTeammate(params);
      if (!result.ok) throw new Error(result.error);
      refreshTeamUI(ctx);
      const kickoffNote = params.prompt?.trim()
        ? "It received your kickoff prompt and is working on it."
        : "It is idle: it wakes for inbox messages and claimable board tasks.";
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
    renderCall: () => new Text("", 0, 0),
    renderResult(result, options, theme, context) {
      const text = result.content[0]?.type === "text" ? (result.content[0] as { type: string; text: string }).text : "";
      if (context.isError) {
        return new Text(theme.fg("error", text.split("\n")[0] || "Failed to shut down teammate."), 0, 0);
      }
      const name = String((context.args as { name?: string }).name ?? "");
      // The finish entry already announced this end of life (or its terminal
      // report is queued to); a second event row is noise.
      if (hasAnnouncedFinish(name) || hasTerminalReport(name)) return { render: () => [], invalidate: () => {} };
      const title = theme.fg("toolTitle", theme.bold(formatToolEventLabel("event", `@${name} shut down`, "agent")));
      const render = (width: number) => {
        if (width <= 0) return [];
        if (!options.expanded) {
          return [truncateToWidth(`${title}${formatExpandHint(keyHint("app.tools.expand", "to expand"), theme)}`, width)];
        }
        return [
          truncateToWidth(title, width),
          ...text.split("\n").map((line) => truncateToWidth(theme.fg("customMessageText", safeDisplayText(line)), width)),
        ];
      };
      return { render, invalidate: () => {} };
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
    description: "The only messaging primitive. Address a living teammate by name; working teammates receive a steer immediately and idle teammates wake with the message. status is reserved for worker reports to leader.",
    parameters: SendMessageParams,
    // Canonical lifecycle rows (same as packages/monitor): empty call slot,
    // ONE delivery row owned by renderResult.
    renderShell: "self",
    renderCall: () => new Text("", 0, 0),
    renderResult(result, _options, theme, context) {
      const text = result.content[0]?.type === "text" ? (result.content[0] as { type: string; text: string }).text : "";
      if (context.isError) {
        return new Text(theme.fg("error", text.split("\n")[0] || "Failed to send message."), 0, 0);
      }
      const to = String((context.args as { to?: string }).to ?? "");
      const details = result.details as { queued?: boolean; stalledMs?: number } | undefined;
      const suffix = details?.queued ? "queued" : "delivered";
      let line = `${theme.fg("toolTitle", theme.bold(formatAgentMessagePrefix("to")))}${theme.fg("accent", `@${to}`)}${theme.fg("dim", ` · ${suffix}`)}`;
      if (!details?.queued && details?.stalledMs !== undefined) {
        line += theme.fg("dim", ` · stalled ${formatSilenceDuration(details.stalledMs)}`);
      }
      return {
        render: (width: number) => width > 0 ? [truncateToWidth(line, width)] : [],
        invalidate: () => {},
      };
    },
    async execute(_toolCallId, params) {
      if (params.to === LEADER_RECIPIENT) throw new Error('The leader cannot send a message to itself.');
      if (params.status) throw new Error('status is reserved for worker reports to="leader".');
      const result = sendLeaderMessage(params.to, params.message);
      if (!result.ok) throw new Error(result.error);
      const disposition = result.queued ? "Queued for its next wake-up." : "Delivered to its running turn.";
      let text = `Message to @${params.to}: ${disposition}`;
      if (!result.queued && result.stalledMs !== undefined) {
        text += `\nWarning: @${params.to} has been stalled with no output for ${formatSilenceDuration(result.stalledMs)} — the control-stream write succeeded, but the teammate may be wedged. Consider teammate_shutdown if it stays silent.`;
      }
      return {
        content: [{ type: "text", text }],
        details: result.stalledMs !== undefined && !result.queued
          ? { queued: result.queued, stalledMs: result.stalledMs }
          : { queued: result.queued },
      };
    },
  });

  pi.registerTool({
    name: "task_create",
    promptSnippet: "Create a shared board task",
    label: "Create Task",
    description: "Create one shared board task. Resident teammates self-claim it when dependencies are met; an optional verify prompt gates completion through a fresh reviewer.",
    parameters: TaskCreateParams,
    // Canonical lifecycle rows (same as packages/monitor): empty call slot,
    // ONE created row owned by renderResult.
    renderShell: "self",
    renderCall: () => new Text("", 0, 0),
    renderResult(result, _options, theme, context) {
      const text = result.content[0]?.type === "text" ? (result.content[0] as { type: string; text: string }).text : "";
      if (context.isError) {
        return new Text(theme.fg("error", text.split("\n")[0] || "Failed to create task."), 0, 0);
      }
      const subject = String((context.args as { subject?: string }).subject ?? "");
      const line = theme.fg("toolTitle", theme.bold(formatToolEventLabel("created", subject, "board")));
      return {
        render: (width: number) => width > 0 ? [truncateToWidth(line, width)] : [],
        invalidate: () => {},
      };
    },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const tasks = listTasks();
      if (params.dependsOn?.some((dep) => !tasks.some((task) => task.id === dep))) {
        throw new Error(`Unknown dependency id in [${params.dependsOn.join(", ")}].`);
      }
      const created = createBoardTask(params);
      if (!created.ok) throw new Error(created.error);
      refreshTeamUI(ctx);
      return { content: [{ type: "text", text: `Created [${created.id}] "${params.subject}". Idle teammates are notified automatically.` }], details: {} };
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

