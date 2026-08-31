/**
 * pi-agent-teams-fradser — Pi extension for Claude-style resident agent
 * teams. Composition only: worker capability registration, session lifecycle,
 * and delegation to tools.ts. Coordination lives in team-machine.ts; the
 * passive widget and console live in ui.ts.
 */

import { getMarkdownTheme, keyHint } from "@earendil-works/pi-coding-agent";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { buildTeamLeaderGuidance, WORKER_GUIDANCE } from "./guidance.ts";
import { clearSessionAgents } from "./agents.ts";
import { formatSilenceDuration, initTeamMachine, markTeammateFinished, removeRuntimeDir, shutdownTeamMachine, teardownTeammates } from "./team-machine.ts";
import { cleanupExpiredStateDirs } from "./statefile.ts";
import { livingTeammates, listTasks, resetState } from "./state.ts";
import { ensureTeamWidget, refreshTeamUI, stopUiTimers } from "./ui.ts";
import { refreshLeaderToolDisclosure, registerLeaderTools, registerTeamCommand } from "./tools.ts";
import { registerWorkerCapabilities, workerBinding } from "./worker.ts";
import { agentColor, eventToolLifecycle, formatAgentMessagePrefix, renderAgentMessageBand, renderToolLifecycle } from "@fradser/pi-kit";
import { FollowUpQueue, groupReportsByTeammate, TEAMMATE_HARNESS_MESSAGE_TYPE, TEAMMATE_REPORT_MESSAGE_TYPE, type FollowUpReport } from "./follow-up-queue.ts";
import { Box, Markdown, Text, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";

const STATE_DIR_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

let leaderPi: ExtensionAPI | undefined;
let leaderCtx: ExtensionContext | undefined;
let followUpQueue: FollowUpQueue | undefined;

export const TEAMMATE_FINISHED_ENTRY_TYPE = "agent-teams-teammate-finished";
export const TEAMMATE_HEALTH_MESSAGE_TYPE = "agent-teams-health";

function sendMainSessionFollowUp(report: FollowUpReport): void {
  followUpQueue?.enqueue(report);
}

function extractHealthReport(details: unknown): FollowUpReport | undefined {
  const report = details as FollowUpReport | undefined;
  return report?.health?.state === "stalled" ? report : undefined;
}

export function hasActiveTeamState(): boolean {
  return livingTeammates().length > 0 || listTasks().length > 0;
}

function extractHarnessReport(details: unknown): FollowUpReport | undefined {
  const report = details as FollowUpReport | undefined;
  return report?.origin === "harness" || report?.harnessEvent ? report : undefined;
}

export default function (pi: ExtensionAPI) {
  if (workerBinding()) {
    const workerToolDisclosure = registerWorkerCapabilities(pi);
    pi.on("session_start", async () => {
      workerToolDisclosure.reset();
    });
    pi.on("before_agent_start", async (event) => {
      workerToolDisclosure.update(event.prompt);
      return { systemPrompt: event.systemPrompt + WORKER_GUIDANCE };
    });
    pi.on("session_shutdown", async () => {
      workerToolDisclosure.reset();
    });
    return;
  }

  leaderPi = pi;
  pi.registerEntryRenderer(TEAMMATE_FINISHED_ENTRY_TYPE, (entry, _options, theme) => {
    const data = entry.data as { teammate?: string; agent?: string } | undefined;
    const name = data?.teammate ?? data?.agent ?? "teammate";
    return new Text(theme.fg("success", `Teammate @${name} finished.`), 0, 0);
  });
  pi.registerMessageRenderer(TEAMMATE_HEALTH_MESSAGE_TYPE, (message, { expanded }, theme) => {
    const health = extractHealthReport(message.details);
    if (!health?.health) return new Text(String(message.content), 0, 0);
    const spec = eventToolLifecycle(
      "agent",
      `@${health.teammate} ${health.health.state} · silent ${formatSilenceDuration(health.health.silenceMs)}`,
      { details: String(message.content).split("\n").filter((line) => line.trim()) },
    );
    return {
      render: (width: number) => renderToolLifecycle(spec, {
        width,
        expanded,
        expandHint: keyHint("app.tools.expand", "to expand"),
        theme,
        fit: truncateToWidth,
        visibleWidth,
      }),
      invalidate: () => {},
    };
  });
  pi.registerMessageRenderer(TEAMMATE_HARNESS_MESSAGE_TYPE, (message, { expanded }, theme) => {
    const report = extractHarnessReport(message.details);
    if (!report) return new Text(String(message.content), 0, 0);
    const event = report.harnessEvent;
    const spec = eventToolLifecycle(
      "agent",
      event?.subject ?? "Agent Teams event",
      { details: report.body.split("\n").filter((line) => line.trim()) },
    );
    return {
      render: (width: number) => renderToolLifecycle(spec, {
        width,
        expanded,
        expandHint: keyHint("app.tools.expand", "to expand"),
        theme,
        fit: truncateToWidth,
        visibleWidth,
      }),
      invalidate: () => {},
    };
  });
  pi.registerMessageRenderer(TEAMMATE_REPORT_MESSAGE_TYPE, (message, { expanded, outputPad }, theme) => {
    const reports = extractReports(message.details);
    const box = new Box(outputPad, 1, (text) => theme.bg("customMessageBg", text));
    if (reports.length === 0) {
      box.addChild(new Markdown(String(message.content), 0, 0, getMarkdownTheme()));
      return box;
    }
    if (!expanded) {
      const groups = groupReportsByTeammate(reports);
      return renderAgentMessageBand(
        groups.map((group) => ({ direction: "from", teammate: group.teammate, count: group.reports.length })),
        { theme, fit: truncateToWidth, expandHint: keyHint("app.tools.expand", "to expand") },
      );
    }
    for (const [index, report] of reports.entries()) {
      const teammate = report.teammate ?? report.agent ?? "teammate";
      const prefix = theme.fg("customMessageLabel", theme.bold(formatAgentMessagePrefix("from")));
      const name = theme.fg(agentColor(teammate), `@${teammate}`);
      box.addChild(new Text(`${prefix}${name}`, 0, 0));
      box.addChild(new Markdown(report.body, 0, 0, getMarkdownTheme(), {
        color: (text) => theme.fg("customMessageText", text),
      }));
      if (index < reports.length - 1) box.addChild(new Text("", 0, 0));
    }
    return box;
  });
  registerLeaderTools(pi);
  registerTeamCommand(pi);

  pi.on("message_end", async (event) => {
    if (event.message.role !== "custom" || event.message.customType !== TEAMMATE_REPORT_MESSAGE_TYPE) return;
    const reports = extractReports(event.message.details);
    for (const report of reports) {
      if (!markTeammateFinished(report)) continue;
      pi.appendEntry(TEAMMATE_FINISHED_ENTRY_TYPE, {
        teammate: report.teammate ?? report.agent,
        agent: report.agent,
      });
    }
  });

  pi.on("session_start", async (_event, ctx) => {
    clearSessionAgents();
    resetState();
    refreshLeaderToolDisclosure();
    followUpQueue?.reset();
    leaderCtx = ctx;
    followUpQueue = new FollowUpQueue({
      isIdle: () => Boolean(leaderCtx?.isIdle()),
      prepareOnDispatch: true,
      dispatch: (reports, content) => leaderPi?.sendMessage({
        customType: reports.length === 1 && reports[0]?.health
          ? TEAMMATE_HEALTH_MESSAGE_TYPE
          : reports.length === 1 && (reports[0]?.origin === "harness" || reports[0]?.harnessEvent)
            ? TEAMMATE_HARNESS_MESSAGE_TYPE
            : TEAMMATE_REPORT_MESSAGE_TYPE,
        // Health remains a compact diagnostic for its dedicated renderer;
        // other harness events retain their explicit envelope in model context.
        content: reports.length === 1 && reports[0]?.health ? reports[0].body : content,
        display: true,
        details: reports.length === 1 ? reports[0] : { reports },
      }, { triggerTurn: true, deliverAs: "followUp" }),
      onFailure: (message) => leaderCtx?.ui.notify(message, "warning"),
    });
    ensureTeamWidget(ctx);
    initTeamMachine(ctx, {
      sendUpdate: sendMainSessionFollowUp,
      archiveQueuedReports: (spawnId) => followUpQueue?.archiveSpawn(spawnId) ?? [],
      notifyChange: () => {
        refreshTeamUI(leaderCtx);
        refreshLeaderToolDisclosure();
      },
    });
    ctx.ui.setStatus("teammate", undefined);
    refreshTeamUI(ctx);
    refreshLeaderToolDisclosure();
    void cleanupExpiredStateDirs(STATE_DIR_MAX_AGE_MS);
  });

  pi.on("before_agent_start", async (event, ctx) => {
    followUpQueue?.onBeforeAgentStart(event.prompt);
    const teamIsActive = hasActiveTeamState();
    return {
      systemPrompt: teamIsActive
        ? event.systemPrompt + buildTeamLeaderGuidance(ctx?.cwd ?? process.cwd())
        : event.systemPrompt,
    };
  });

  pi.on("agent_start", async () => {
    followUpQueue?.onAgentStart();
  });

  pi.on("agent_settled", async () => {
    followUpQueue?.onAgentSettled();
  });

  pi.on("session_shutdown", async (_event, ctx) => {
    stopUiTimers();
    const diagnostics = await teardownTeammates();
    for (const message of diagnostics) {
      ctx.ui.notify(message, "warning");
    }
    shutdownTeamMachine();
    removeRuntimeDir(ctx);
    followUpQueue?.reset();
    followUpQueue = undefined;
    leaderPi = undefined;
    leaderCtx = undefined;
    resetState();
  });
}

function extractReports(details: unknown): FollowUpReport[] {
  const typed = details as FollowUpReport | { reports?: FollowUpReport[] } | undefined;
  if (typed && "reports" in typed && Array.isArray(typed.reports)) return typed.reports;
  if (typed && "teammate" in typed) return [typed as FollowUpReport];
  return [];
}
