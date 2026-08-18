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

const STATE_DIR_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

let leaderPi: ExtensionAPI | undefined;

function sendMainSessionUpdate(subject: string, body: string, runId?: string): void {
  try {
    leaderPi?.sendMessage({
      customType: "teammate-update",
      content: `Teammate update — ${subject}${runId ? ` [${runId}]` : ""}\n${body}`,
      display: true,
      details: { runId },
    }, { triggerTurn: true, deliverAs: "followUp" });
  } catch {
    // Late run events must not prevent shutdown.
  }
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
    const dispatchCtx = dispatchContext(ctx);
    ensureTeamWidget(ctx);
    const stateFile = stateFilePath(ctx.sessionManager.getSessionFile(), ctx.cwd || process.cwd());
    initRunMachine(dispatchCtx, stateFile, {
      sendUpdate: sendMainSessionUpdate,
      notifyChange: () => refreshTeamUI(),
    });
    ctx.ui.setStatus("teammate", undefined);
    refreshTeamUI(ctx);
    void cleanupExpiredStateDirs(STATE_DIR_MAX_AGE_MS);
  });

  pi.on("session_shutdown", async (_event, ctx) => {
    stopUiTimers();
    await terminateAllWorkers();
    shutdownRunMachine();
    removeSessionStateDir(ctx.sessionManager.getSessionFile(), ctx.cwd || process.cwd());
    leaderPi = undefined;
    resetState();
  });

  pi.on("before_agent_start", async (event, ctx) => ({
    systemPrompt: event.systemPrompt + buildTeamLeaderGuidance(ctx?.cwd ?? process.cwd()),
  }));
}
