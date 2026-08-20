/**
 * pi-agent-teams-fradser — Pi extension for run-centric agent teams.
 *
 * The entry point is composition only: worker capability registration,
 * session lifecycle, and delegation to tools.ts. Scheduling lives in
 * run-machine.ts; the passive widget and console live in ui.ts.
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { buildTeamLeaderGuidance, WORKER_GUIDANCE } from "./guidance";
import { initRunMachine, shutdownRunMachine, type DispatchCtx } from "./run-machine";
import { cleanupExpiredStateDirs, removeSessionStateDir, stateFilePath } from "./statefile";
import { resetState } from "./state";
import { ensureTeamWidget, refreshTeamUI, stopUiTimers } from "./ui";
import { registerLeaderTools, registerTeamCommand } from "./tools";
import { registerWorkerCapabilities, workerOutboxBinding } from "./worker";
import { terminateAllWorkers } from "./spawner";
import { FollowUpQueue } from "./follow-up-queue";

const STATE_DIR_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

let leaderPi: ExtensionAPI | undefined;
let leaderCtx: ExtensionContext | undefined;
let followUpQueue: FollowUpQueue | undefined;

function sendMainSessionFollowUp(subject: string, body: string, runId?: string): void {
  followUpQueue?.enqueue({ subject, body, runId });
}

function dispatchContext(ctx: ExtensionContext): DispatchCtx {
  return { ui: ctx.ui, sessionManager: ctx.sessionManager, cwd: ctx.cwd };
}

export default function (pi: ExtensionAPI) {
  if (workerOutboxBinding()) {
    pi.on("before_agent_start", async (event) => ({
      systemPrompt: event.systemPrompt + WORKER_GUIDANCE,
    }));
    registerWorkerCapabilities(pi);
    return;
  }

  leaderPi = pi;
  registerLeaderTools(pi);
  registerTeamCommand(pi);

  pi.on("session_start", async (_event, ctx) => {
    resetState();
    followUpQueue?.reset();
    leaderCtx = ctx;
    const sessionQueue = new FollowUpQueue({
      isIdle: () => Boolean(leaderCtx?.isIdle()),
      dispatch: (content) => leaderPi?.sendUserMessage(content, { deliverAs: "followUp" }),
      onFailure: (message) => leaderCtx?.ui.notify(message, "warning"),
    });
    followUpQueue = sessionQueue;
    const dispatchCtx = dispatchContext(ctx);
    ensureTeamWidget(ctx);
    const stateFile = stateFilePath(ctx.sessionManager.getSessionFile(), ctx.cwd || process.cwd());
    initRunMachine(dispatchCtx, stateFile, {
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
    await terminateAllWorkers();
    shutdownRunMachine();
    removeSessionStateDir(ctx.sessionManager.getSessionFile(), ctx.cwd || process.cwd());
    followUpQueue?.reset();
    followUpQueue = undefined;
    leaderPi = undefined;
    leaderCtx = undefined;
    resetState();
  });

}
