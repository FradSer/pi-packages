/**
 * pi-agent-teams-fradser — Pi extension for Claude-style resident agent
 * teams. Composition only: worker capability registration, session lifecycle,
 * and delegation to tools.ts. Coordination lives in team-machine.ts; the
 * passive widget and console live in ui.ts.
 */

import { getMarkdownTheme, keyHint, ToolExecutionComponent } from "@earendil-works/pi-coding-agent";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { buildIdleLeaderGuidance, buildTeamLeaderGuidance, WORKER_GUIDANCE } from "./guidance.ts";
import { clearSessionAgents } from "./agents.ts";
import { getConfirmedStopTime, initTeamMachine, markTeammateFinished, removeRuntimeDir, shutdownTeamMachine, syncLeaderContext, teardownTeammates } from "./team-machine.ts";
import { cleanupExpiredStateDirs } from "./statefile.ts";
import { livingTeammates, listTasks, resetState } from "./state.ts";
import { ensureTeamWidget, refreshTeamUI, stopUiTimers } from "./ui.ts";
import { refreshLeaderToolDisclosure, registerLeaderTools, registerTeamCommand } from "./tools.ts";
import { registerWorkerCapabilities, workerBinding } from "./worker.ts";
import { plainText } from "./tool-copy.ts";
import { agentColor, bindLifecycleRenderers, clearPiStatus, createToolExecutionWrapper, eventToolLifecycle, formatAgentMessagePrefix, notifyPi, renderAgentMessageBand } from "@fradser/pi-kit";
import { annotateReportDelivery, formatReports, groupReportsByTeammate, TEAMMATE_HARNESS_MESSAGE_TYPE, TEAMMATE_REPORT_MESSAGE_TYPE, type LeaderReport } from "./leader-reports.ts";
import { Box, Markdown, Text, truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";

/** Geometry bound once: harness event rows share hint and wrapping. */
const harnessRows = bindLifecycleRenderers({
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
});

const STATE_DIR_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

let leaderPi: ExtensionAPI | undefined;
let leaderCtx: ExtensionContext | undefined;

export const TEAMMATE_FINISHED_ENTRY_TYPE = "agent-teams-teammate-finished";

function sendLeaderReport(report: LeaderReport): void {
  try {
    leaderPi?.sendMessage({
      customType: report.origin === "harness" || report.harnessEvent
        ? TEAMMATE_HARNESS_MESSAGE_TYPE
        : TEAMMATE_REPORT_MESSAGE_TYPE,
      content: formatReports([report]),
      display: true,
      details: report,
    }, { triggerTurn: true, deliverAs: "steer" });
  } catch (error) {
    if (leaderCtx) {
      const detail = error instanceof Error ? error.message : String(error);
      notifyPi(leaderCtx.ui, `Agent Teams report delivery failed: ${detail}. The report remains in /agent-teams.`, "warning");
    }
  }
}

export function hasActiveTeamState(): boolean {
  return livingTeammates().length > 0 || listTasks().length > 0;
}

function extractHarnessReport(details: unknown): LeaderReport | undefined {
  const report = details as LeaderReport | undefined;
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
  const deliveries = new WeakMap<object, LeaderReport[]>();
  pi.registerEntryRenderer(TEAMMATE_FINISHED_ENTRY_TYPE, (entry, _options, theme) => {
    const data = entry.data as { teammate?: string; agent?: string } | undefined;
    const name = data?.teammate ?? data?.agent ?? "teammate";
    return new Text(theme.fg("success", `Assignment for @${name} finished.`), 0, 0);
  });
  pi.registerMessageRenderer(TEAMMATE_HARNESS_MESSAGE_TYPE, (message, { expanded }, theme) => {
    const report = extractHarnessReport(message.details);
    if (!report) return new Text(String(message.content), 0, 0);
    const event = report.harnessEvent;
    return harnessRows.message(
      () => eventToolLifecycle("agent", plainText(event?.subject ?? "Agent Teams event")),
      { hostComponent: ToolExecutionComponent, ui: leaderCtx?.ui, cwd: leaderCtx?.cwd },
    )(message, { expanded }, theme);
  });
  pi.registerMessageRenderer(TEAMMATE_REPORT_MESSAGE_TYPE, (message, { expanded, outputPad }, theme) => {
    const reports = deliveries.get(message) ?? extractReports(message.details);
    if (reports.length === 0) {
      const box = new Box(outputPad, 1, (text) => theme.bg("customMessageBg", text));
      box.addChild(new Markdown(String(message.content), 0, 0, getMarkdownTheme()));
      return box;
    }

    return createToolExecutionWrapper(
      (opt, currentTheme) => {
        const effTheme = currentTheme ?? theme;
        if (!opt.expanded) {
          const groups = groupReportsByTeammate(reports);
          const band = renderAgentMessageBand(
            groups.map((group) => ({ direction: "from", teammate: group.teammate, count: group.reports.length })),
            { theme: effTheme, fit: truncateToWidth, visibleWidth, wrapDetail: wrapTextWithAnsi, expandHint: keyHint("app.tools.expand", "to expand") },
          );
          if (!reports.some((report) => report.deliveredAfterStop)) return band;
          const box = new Box(0, 0);
          box.addChild(band);
          box.addChild(new Text(effTheme.fg("warning", "Late delivery: process already stopped."), 0, 0));
          return box;
        }
        const box = new Box(outputPad, 1, (text) => effTheme.bg("customMessageBg", text));
        for (const [index, report] of reports.entries()) {
          const teammate = report.teammate ?? report.agent ?? "teammate";
          const prefix = effTheme.fg("customMessageLabel", effTheme.bold(formatAgentMessagePrefix("from")));
          const name = effTheme.fg(agentColor(teammate), `@${teammate}`);
          const delivery = report.deliveredAfterStop ? effTheme.fg("warning", " (late delivery; process stopped)") : "";
          box.addChild(new Text(`${prefix}${name}${delivery}`, 0, 0));
          box.addChild(new Markdown(report.body, 0, 0, getMarkdownTheme(), {
            color: (text) => effTheme.fg("customMessageText", text),
          }));
          if (index < reports.length - 1) box.addChild(new Text("", 0, 0));
        }
        return box;
      },
      {
        hostComponent: ToolExecutionComponent,
        toolName: "message",
        expanded,
        ui: leaderCtx?.ui,
        cwd: leaderCtx?.cwd,
      },
      theme,
    );
  });
  registerLeaderTools(pi);
  registerTeamCommand(pi);

  pi.on("message_start", (event) => {
    if (event.message.role !== "custom" || event.message.customType !== TEAMMATE_REPORT_MESSAGE_TYPE) return;
    const deliveredAt = Date.now();
    deliveries.set(event.message, extractReports(event.message.details).map((report) => annotateReportDelivery(
      report, deliveredAt, report.spawnId ? getConfirmedStopTime(report.spawnId) : undefined,
    )));
  });

  pi.on("message_end", async (event) => {
    if (event.message.role !== "custom" || event.message.customType !== TEAMMATE_REPORT_MESSAGE_TYPE) return;
    const deliveredAt = Date.now();
    const reports = deliveries.get(event.message) ?? extractReports(event.message.details).map((report) => annotateReportDelivery(
      report, deliveredAt, report.spawnId ? getConfirmedStopTime(report.spawnId) : undefined,
    ));
    if (reports.length === 0) return;
    for (const report of reports) {
      if (!markTeammateFinished(report)) continue;
      pi.appendEntry(TEAMMATE_FINISHED_ENTRY_TYPE, {
        teammate: report.teammate ?? report.agent,
        agent: report.agent,
        assignmentId: report.assignmentId,
        workId: report.workId,
        spawnId: report.spawnId,
      });
    }
    return {
      message: { ...event.message, content: formatReports(reports), details: reports.length === 1 ? reports[0] : { reports } },
    };
  });

  pi.on("model_select", async (_event, ctx) => {
    leaderCtx = ctx;
    syncLeaderContext(ctx);
  });

  pi.on("thinking_level_select", async (_event, ctx) => {
    leaderCtx = ctx;
    syncLeaderContext(ctx);
  });

  pi.on("session_start", async (_event, ctx) => {
    clearSessionAgents();
    resetState();
    refreshLeaderToolDisclosure();
    leaderCtx = ctx;
    ensureTeamWidget(ctx);
    initTeamMachine(ctx, {
      sendUpdate: sendLeaderReport,
      notifyChange: () => {
        refreshTeamUI(leaderCtx);
        refreshLeaderToolDisclosure();
      },
    });
    clearPiStatus(ctx.ui, "teammate");
    refreshTeamUI(ctx);
    refreshLeaderToolDisclosure();
    void cleanupExpiredStateDirs(STATE_DIR_MAX_AGE_MS);
  });

  pi.on("before_agent_start", async (event, ctx) => {
    leaderCtx = ctx;
    const teamIsActive = hasActiveTeamState();
    return {
      systemPrompt: event.systemPrompt + (teamIsActive
        ? buildTeamLeaderGuidance(ctx?.cwd ?? process.cwd())
        : buildIdleLeaderGuidance(ctx?.cwd ?? process.cwd())),
    };
  });

  pi.on("session_shutdown", async (_event, ctx) => {
    stopUiTimers();
    const diagnostics = await teardownTeammates();
    for (const message of diagnostics) {
      notifyPi(ctx.ui, message, "warning");
    }
    shutdownTeamMachine();
    removeRuntimeDir(ctx);
    leaderPi = undefined;
    leaderCtx = undefined;
    resetState();
    refreshLeaderToolDisclosure();
  });
}

function extractReports(details: unknown): LeaderReport[] {
  if (Array.isArray(details)) return details as LeaderReport[];
  const typed = details as LeaderReport | { reports?: LeaderReport[] } | undefined;
  if (typed && "reports" in typed && Array.isArray(typed.reports)) return typed.reports;
  if (typed && "teammate" in typed) return [typed as LeaderReport];
  return [];
}
