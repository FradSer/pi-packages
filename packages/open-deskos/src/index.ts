import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { readDeskLinkConfig } from "./config.ts";
import { registerConsoleExtension } from "./console-extension.ts";
import { createControlTcpTransport } from "./control-transport.ts";
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
 * Report this machine's Pi sessions and, with an independent credential, drive
 * Hosted Pi sessions over a separate Desk Link v2 control connection.
 */
export default function (pi: ExtensionAPI): void {
  const config = readDeskLinkConfig();
  const reporter = config === null ? null : new DeskReporter({ config, createTransport: createTcpTransport });
  const discovery = reporter === null ? null : new SessionDiscovery({
    discover: () => scanDirectorySessions(),
    onSnapshot: (sessions) => reporter.replaceDiscoveredSessions(sessions),
  });
  let currentSessionId = "";

  if (reporter && discovery) {
    function beginSession(ctx: Parameters<Parameters<ExtensionAPI["on"]>[1]>[1]): void {
      if (currentSessionId.length > 0 && currentSessionId !== ctx.sessionManager.getSessionId()) {
        reporter?.markStatus(currentSessionId, "exited");
      }
      currentSessionId = ctx.sessionManager.getSessionId();
      const name = ctx.sessionManager.getSessionName();
      const timestamp = ctx.sessionManager.getHeader()?.timestamp;
      const startedAt = timestamp ? Date.parse(timestamp) : Number.NaN;
      reporter?.recordSession({
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
      if (currentSessionId.length > 0) reporter.renameSession(currentSessionId, event.name);
    });
    pi.on("agent_start", () => reporter.markStatus(currentSessionId, "running"));
    pi.on("agent_settled", () => reporter.markStatus(currentSessionId, "settled"));
    pi.on("message_end", (event) => {
      if (currentSessionId.length === 0) return;
      const prompt = promptFromMessage(event.message);
      if (prompt.length > 0) reporter.recordSession({ sessionId: currentSessionId, latestGoal: prompt });
      reporter.recordEvents(currentSessionId, eventsFromMessage(event.message));
    });
    pi.on("session_shutdown", () => {
      discovery.stop();
      reporter.markStatus(currentSessionId, "exited");
      reporter.disconnect();
    });
  }

  registerConsoleExtension({
    pi,
    config,
    createControlTransport: createControlTcpTransport,
    reporterSnapshot: () => reporter?.snapshot() ?? null,
    configHint: CONFIG_HINT,
  });
}
