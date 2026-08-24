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
import { initTeamMachine, markTeammateFinished, removeRuntimeDir, shutdownTeamMachine, teardownTeammates } from "./team-machine.ts";
import { cleanupExpiredStateDirs } from "./statefile.ts";
import { resetState } from "./state.ts";
import { ensureTeamWidget, refreshTeamUI, stopUiTimers } from "./ui.ts";
import { registerLeaderTools, registerTeamCommand } from "./tools.ts";
import { registerWorkerCapabilities, workerBinding } from "./worker.ts";
import { formatAgentMessagePrefix, formatExpandHint } from "@fradser/pi-kit";
import { FollowUpQueue, groupReportsByTeammate, TEAMMATE_REPORT_MESSAGE_TYPE, type FollowUpReport } from "./follow-up-queue.ts";
import { Box, Markdown, Text } from "@earendil-works/pi-tui";

const STATE_DIR_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

let leaderPi: ExtensionAPI | undefined;
let leaderCtx: ExtensionContext | undefined;
let followUpQueue: FollowUpQueue | undefined;

const REPORT_COLORS = ["success", "warning", "error", "mdLink"] as const;
export const TEAMMATE_FINISHED_ENTRY_TYPE = "agent-teams-teammate-finished";

function reportColor(name: string): (typeof REPORT_COLORS)[number] {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) | 0;
  return REPORT_COLORS[Math.abs(hash) % REPORT_COLORS.length];
}

function sendMainSessionFollowUp(report: FollowUpReport): void {
  followUpQueue?.enqueue(report);
}

export default function (pi: ExtensionAPI) {
  if (workerBinding()) {
    pi.on("before_agent_start", async (event) => ({
      systemPrompt: event.systemPrompt + WORKER_GUIDANCE,
    }));
    registerWorkerCapabilities(pi);
    return;
  }

  leaderPi = pi;
  pi.registerEntryRenderer(TEAMMATE_FINISHED_ENTRY_TYPE, (entry, _options, theme) => {
    const data = entry.data as { teammate?: string; agent?: string } | undefined;
    const name = data?.teammate ?? data?.agent ?? "teammate";
    return new Text(theme.fg("success", `Teammate @${name} finished.`), 0, 0);
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
      const hint = formatExpandHint(keyHint("app.tools.expand", "to expand"), theme);
      for (const group of groups) {
        const prefix = theme.fg("customMessageLabel", theme.bold(formatAgentMessagePrefix("from", group.reports.length)));
        const name = theme.fg(reportColor(group.teammate), `@${group.teammate}`);
        box.addChild(new Text(`${prefix}${name}${hint}`, 0, 0));
      }
      return box;
    }
    for (const [index, report] of reports.entries()) {
      const teammate = report.teammate ?? report.agent ?? "teammate";
      const prefix = theme.fg("customMessageLabel", theme.bold(formatAgentMessagePrefix("from")));
      const name = theme.fg(reportColor(teammate), `@${teammate}`);
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
    followUpQueue?.reset();
    leaderCtx = ctx;
    followUpQueue = new FollowUpQueue({
      isIdle: () => Boolean(leaderCtx?.isIdle()),
      prepareOnDispatch: true,
      dispatch: (reports, content) => leaderPi?.sendMessage({
        customType: TEAMMATE_REPORT_MESSAGE_TYPE,
        content,
        display: true,
        details: reports.length === 1 ? reports[0] : { reports },
      }, { triggerTurn: true, deliverAs: "followUp" }),
      onFailure: (message) => leaderCtx?.ui.notify(message, "warning"),
    });
    ensureTeamWidget(ctx);
    initTeamMachine(ctx, {
      sendUpdate: sendMainSessionFollowUp,
      notifyChange: () => refreshTeamUI(leaderCtx),
    });
    ctx.ui.setStatus("teammate", undefined);
    refreshTeamUI(ctx);
    void cleanupExpiredStateDirs(STATE_DIR_MAX_AGE_MS);
  });

  pi.on("before_agent_start", async (event, ctx) => {
    followUpQueue?.onBeforeAgentStart(event.prompt);
    return {
      systemPrompt: event.systemPrompt + buildTeamLeaderGuidance(ctx?.cwd ?? process.cwd()),
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
