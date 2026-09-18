import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { notifyPi } from "@fradser/pi-kit";
import { readDeskLinkConfig } from "./config.ts";
import { eventsFromMessage, promptFromMessage } from "./events.ts";
import { scanDirectorySessions, SessionDiscovery } from "./discovery.ts";
import { DeskReporter } from "./reporter.ts";
import { createTcpTransport } from "./transport.ts";

const CONFIG_HINT = "set ODK_DESK_LINK_ADDRESS and ODK_DESK_LINK_TOKEN to report this machine";

function workspaceName(cwd: string): string {
  const parts = cwd.split(/[/\\]/).filter((part) => part.length > 0);
  return parts.length > 0 ? (parts[parts.length - 1] ?? cwd) : cwd;
}

/**
 * Report this machine's Pi sessions to Open DeskOS over a Desk Link.
 *
 * The reporter is deliberately passive inside the session: it observes the
 * events Pi already emits and never injects, blocks, or mutates a turn.
 */
export default function (pi: ExtensionAPI): void {
  const config = readDeskLinkConfig();

  if (config === null) {
    // Keep configuration diagnostics available on demand without automatic UI.
    pi.registerCommand("open-deskos", {
      description: "Show this machine's Open DeskOS Desk Link state",
      handler: async (_args, ctx) => {
        notifyPi(ctx.ui, `[open-deskos] not configured · ${CONFIG_HINT}`, "warning");
      },
    });
    return;
  }

  const reporter = new DeskReporter({
    config,
    createTransport: createTcpTransport,
  });
  const discovery = new SessionDiscovery({
    discover: () => scanDirectorySessions(),
    onSnapshot: (sessions) => reporter.replaceDiscoveredSessions(sessions),
  });
  let currentSessionId = "";

  function beginSession(ctx: Parameters<Parameters<ExtensionAPI["on"]>[1]>[1]): void {
    if (currentSessionId.length > 0 && currentSessionId !== ctx.sessionManager.getSessionId()) {
      reporter.markStatus(currentSessionId, "exited");
    }
    currentSessionId = ctx.sessionManager.getSessionId();
    const name = ctx.sessionManager.getSessionName();
    const timestamp = ctx.sessionManager.getHeader()?.timestamp;
    const startedAt = timestamp ? Date.parse(timestamp) : Number.NaN;
    reporter.recordSession({
      sessionId: currentSessionId,
      ...(name === undefined ? {} : { name }),
      cwd: ctx.cwd,
      workspaceName: workspaceName(ctx.cwd),
      status: ctx.isIdle() ? "settled" : "running",
      startedAt: Number.isFinite(startedAt) ? startedAt : Date.now(),
    });
  }

  pi.on("session_start", (_event, ctx) => {
    beginSession(ctx);
    reporter.start();
    discovery.start();
  });

  pi.on("session_info_changed", (event) => {
    if (currentSessionId.length === 0) return;
    reporter.renameSession(currentSessionId, event.name);
  });

  pi.on("agent_start", () => reporter.markStatus(currentSessionId, "running"));
  pi.on("agent_settled", () => reporter.markStatus(currentSessionId, "settled"));

  pi.on("message_end", (event) => {
    if (currentSessionId.length === 0) return;
    const prompt = promptFromMessage(event.message);
    if (prompt.length > 0) {
      reporter.recordSession({ sessionId: currentSessionId, latestGoal: prompt });
    }
    reporter.recordEvents(currentSessionId, eventsFromMessage(event.message));
  });

  pi.on("session_shutdown", () => {
    discovery.stop();
    reporter.markStatus(currentSessionId, "exited");
    // Pi emits this for /new, switch, fork, and resume inside one process, so
    // the link is closed rather than retired: the next session must report too.
    reporter.disconnect();
  });

  pi.registerCommand("open-deskos", {
    description: "Show this machine's Open DeskOS Desk Link state",
    handler: async (_args, ctx) => {
      const state = reporter.snapshot();
      const level = state.link === "connected" ? "info" : "warning";
      const detail = `${state.link} · ${state.machine} → ${config.host}:${config.port} · ${state.sessions} session(s) · ${state.events} event(s)${state.omittedSessions > 0 ? ` · ${state.omittedSessions} session(s) omitted: frame limit` : ""}${state.lastError === undefined ? "" : ` · ${state.lastError}`}`;
      notifyPi(ctx.ui, `[open-deskos] ${detail}`, level);
    },
  });
}
