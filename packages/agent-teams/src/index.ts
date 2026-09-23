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
import { getTask, getTeammate, livingTeammates, listTasks, resetState } from "./state.ts";
import { ensureTeamWidget, refreshTeamUI, stopUiTimers } from "./ui.ts";
import { registerLeaderTools, registerTeamCommand } from "./tools.ts";
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
/** Audit entry for a retired attempt's nonterminal report. The evidence stays in the
 * session while the context projection stops treating it as a current instruction;
 * without a renderer the retained entry would be invisible in the transcript. */
export const TEAMMATE_HISTORICAL_ENTRY_TYPE = "agent-teams-historical-report";

/** One entry per retained report, so a re-delivered report cannot multiply its own
 * audit trail. Bounded the same way the finish announcements are. */
const HISTORICAL_ENTRY_LIMIT = 512;
const retainedHistoricalReports = new Set<string>();
function rememberRetainedReport(report: LeaderReport): boolean {
  const key = [
    report.teammate ?? report.agent ?? "",
    report.spawnId ?? "",
    report.eventId ?? "",
    report.timestamp ?? 0,
  ].join(":");
  if (retainedHistoricalReports.has(key)) return false;
  retainedHistoricalReports.add(key);
  while (retainedHistoricalReports.size > HISTORICAL_ENTRY_LIMIT) {
    const oldest = retainedHistoricalReports.values().next().value;
    if (oldest === undefined) break;
    retainedHistoricalReports.delete(oldest);
  }
  return true;
}

/** Accepted outcomes remain evidence even after their process exits. Only
 * nonterminal coordination loses current authority when its attempt retires; the
 * source report stays in the session as the visible audit trail. */
function isHistoricalReport(report: LeaderReport): boolean {
  if (report.origin === "harness" || report.harnessEvent || report.finished
    || report.status === "completed" || report.status === "failed") return false;
  if (!report.spawnId || !report.teammate) return false;
  const worker = getTeammate(report.teammate);
  if (!worker || worker.spawnId !== report.spawnId || worker.status === "stopped") return true;
  if (report.assignmentId !== worker.assignment?.id || worker.assignment?.closed || worker.reportSequenceEnded) return true;
  const task = worker.currentTaskId ? getTask(worker.currentTaskId) : undefined;
  return task?.status === "superseded" || task?.status === "completed";
}

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
  pi.registerEntryRenderer(TEAMMATE_HISTORICAL_ENTRY_TYPE, (entry, _options, theme) => {
    const data = entry.data as { teammate?: string; agent?: string } | undefined;
    const name = data?.teammate ?? data?.agent ?? "teammate";
    return new Text(theme.fg("dim", `Historical report from @${name} retained for audit; it no longer instructs.`), 0, 0);
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

  // Pi cannot retract one already-queued steer. The persisted record stays for
  // audit, and this projection keeps a retired attempt's nonterminal text from
  // acting as a current instruction. Deliberate trade-off: while such a record
  // exists the projection is recomputed per request, so a session that retires a
  // report pays a prompt/tool replay each turn. Correctness wins over cache
  // warmth here; the alternative needs an SDK API to rewrite a stored message.
  pi.on("context", (event) => {
    let changed = false;
    const messages = event.messages.flatMap((message) => {
      if (message.role !== "custom" || message.customType !== TEAMMATE_REPORT_MESSAGE_TYPE) return [message];
      const reports = extractReports(message.details);
      if (reports.length === 0) return [message];
      const current = reports.filter((report) => !isHistoricalReport(report));
      if (current.length === reports.length) return [message];
      changed = true;
      return current.length === 0 ? [] : [{ ...message, content: formatReports(current),
        details: current.length === 1 ? current[0] : { reports: current } }];
    });
    return changed ? { messages } : undefined;
  });

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
      // A retired attempt's nonterminal report keeps its evidence in the session but must
      // stop instructing the leader. The context projection already excludes it from
      // future requests; this entry is what keeps the retained evidence visible rather
      // than silently dropped, and is appended once per report at the delivery seam.
      if (isHistoricalReport(report)) {
        if (rememberRetainedReport(report)) {
          pi.appendEntry(TEAMMATE_HISTORICAL_ENTRY_TYPE, {
            teammate: report.teammate ?? report.agent,
            agent: report.agent,
            spawnId: report.spawnId,
            assignmentId: report.assignmentId,
            workId: report.workId,
            eventId: report.eventId,
            status: report.status,
            timestamp: report.timestamp,
            body: report.body,
          });
        }
        continue;
      }
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
    leaderCtx = ctx;
    ensureTeamWidget(ctx);
    initTeamMachine(ctx, {
      sendUpdate: sendLeaderReport,
      notifyChange: () => {
        refreshTeamUI(leaderCtx);
      },
    });
    clearPiStatus(ctx.ui, "teammate");
    refreshTeamUI(ctx);
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
  });
}

function extractReports(details: unknown): LeaderReport[] {
  if (Array.isArray(details)) return details as LeaderReport[];
  const typed = details as LeaderReport | { reports?: LeaderReport[] } | undefined;
  if (typed && "reports" in typed && Array.isArray(typed.reports)) return typed.reports;
  if (typed && "teammate" in typed) return [typed as LeaderReport];
  return [];
}
