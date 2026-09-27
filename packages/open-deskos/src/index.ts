import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { open } from "node:fs/promises";
import { readDeskLinkConfigs } from "./config.ts";
import { registerConsoleExtension } from "./console-extension.ts";
import { createControlTcpTransport } from "./control-transport.ts";
import { aggregateDeskSnapshots, selectConsoleDesk } from "./desk-set.ts";
import { eventsFromMessage, promptFromMessage } from "./events.ts";
import { scanDirectorySessions, SessionDiscovery } from "./discovery.ts";
import { DeskReporter, type DeskLinkSnapshot } from "./reporter.ts";
import { CurrentSessionReplay } from "./session-replay.ts";
import { createTcpTransport } from "./transport.ts";

const CONFIG_HINT = "set ODK_DESK_LINK_ADDRESS and ODK_DESK_LINK_TOKEN, or list desks in ~/.config/open-deskos/desks.json, to report this machine";
/** Read only a bounded tail before it enters the reporter's own 300-event/1MiB retention pipeline. */
const MAX_DURABLE_SESSION_BYTES = 4 * 1024 * 1024;

function workspaceName(cwd: string): string {
  const parts = cwd.split(/[/\\]/).filter((part) => part.length > 0);
  return parts.length > 0 ? (parts[parts.length - 1] ?? cwd) : cwd;
}

/**
 * The current session manager points at its own trusted durable log. Read its
 * bounded tail in chronological order; other sessions never enter this path.
 */
async function durableSessionEvents(sessionFile: string | undefined): Promise<ReturnType<typeof eventsFromMessage>> {
  if (!sessionFile) return [];
  try {
    const handle = await open(sessionFile, "r");
    try {
      const stat = await handle.stat();
      if (!stat.isFile() || stat.size <= 0) return [];
      const bytes = Math.min(stat.size, MAX_DURABLE_SESSION_BYTES);
      const tail = Buffer.alloc(bytes);
      await handle.read(tail, 0, bytes, stat.size - bytes);
      const text = tail.toString("utf8");
      const lines = text.split("\n");
      // A writer can have produced valid JSON before its terminating newline.
      // It is still an incomplete append and must wait for message_end instead
      // of being replayed now and then sent a second time live.
      if (!text.endsWith("\n")) lines.pop();
      // A bounded tail can begin mid-record; that first fragment is never an entry.
      if (stat.size > bytes) lines.shift();
      return lines.flatMap((line) => {
        if (!line.trim()) return [];
        try {
          const entry = JSON.parse(line) as { type?: unknown; message?: unknown };
          return entry.type === "message" && entry.message !== undefined ? eventsFromMessage(entry.message) : [];
        } catch {
          return [];
        }
      });
    } finally {
      await handle.close();
    }
  } catch {
    return [];
  }
}

/**
 * Report this machine's Pi sessions and, with an independent credential, drive
 * Hosted Pi sessions over a separate Desk Link v2 control connection.
 */
export default function (pi: ExtensionAPI): void {
  const { configs, refusals } = readDeskLinkConfigs();
  const reporters = configs.map((config) => new DeskReporter({ config, createTransport: createTcpTransport }));
  const endpoints = configs.map((config) => `${config.host}:${config.port}`);
  // This is one machine reporting, however many desks listen: discovery runs
  // once and every desk receives the same session, status, and event updates,
  // so one desk being unreachable never stops the others.
  const each = (run: (reporter: DeskReporter) => void): void => {
    for (const reporter of reporters) run(reporter);
  };
  const aggregate = (): DeskLinkSnapshot | null =>
    aggregateDeskSnapshots(reporters.map((reporter, index) => ({ ...reporter.snapshot(), endpoint: endpoints[index] ?? "desk" })));
  const discovery = reporters.length === 0 ? null : new SessionDiscovery({
    discover: () => scanDirectorySessions(),
    onSnapshot: (sessions) => each((reporter) => reporter.replaceDiscoveredSessions(sessions)),
  });
  const replay = reporters.length === 0 ? null : new CurrentSessionReplay(durableSessionEvents);
  let currentSessionId = "";

  if (reporters.length > 0 && discovery) {
    function beginSession(ctx: Parameters<Parameters<ExtensionAPI["on"]>[1]>[1]): string {
      if (currentSessionId.length > 0 && currentSessionId !== ctx.sessionManager.getSessionId()) {
        each((reporter) => reporter.markStatus(currentSessionId, "exited"));
      }
      currentSessionId = ctx.sessionManager.getSessionId();
      const name = ctx.sessionManager.getSessionName();
      const timestamp = ctx.sessionManager.getHeader()?.timestamp;
      const startedAt = timestamp ? Date.parse(timestamp) : Number.NaN;
      each((reporter) => reporter.recordSession({
        sessionId: currentSessionId,
        ...(name === undefined ? {} : { name }),
        cwd: ctx.cwd,
        workspaceName: workspaceName(ctx.cwd),
        status: ctx.isIdle() ? "settled" : "running",
        startedAt: Number.isFinite(startedAt) ? startedAt : Date.now(),
      }));
      return currentSessionId;
    }

    pi.on("session_start", async (event, ctx) => {
      const sessionId = beginSession(ctx);
      each((reporter) => reporter.start());
      discovery.start();
      // A resumed/reloaded Pi can have a durable JSONL history that is longer
      // than its in-memory branch. Start the gate for every session; only the
      // resumed/reloaded/forked cases provide a durable tail. New sessions still
      // queue their first message_end event behind this empty replay boundary.
      const replayFile = ["resume", "reload", "fork"].includes((event as { reason?: string }).reason ?? "")
        ? ctx.sessionManager.getSessionFile?.()
        : undefined;
      await replay?.start(sessionId, replayFile, (id, events) => each((reporter) => reporter.recordEvents(id, events)));
    });
    pi.on("session_info_changed", (event) => {
      if (currentSessionId.length > 0) each((reporter) => reporter.renameSession(currentSessionId, event.name));
    });
    pi.on("agent_start", () => each((reporter) => reporter.markStatus(currentSessionId, "running")));
    pi.on("agent_settled", () => each((reporter) => reporter.markStatus(currentSessionId, "settled")));
    pi.on("message_end", (event) => {
      if (currentSessionId.length === 0) return;
      const prompt = promptFromMessage(event.message);
      if (prompt.length > 0) each((reporter) => reporter.recordSession({ sessionId: currentSessionId, latestGoal: prompt }));
      const events = eventsFromMessage(event.message);
      replay?.append(currentSessionId, events, (id, fresh) => each((reporter) => reporter.recordEvents(id, fresh)));
    });
    pi.on("session_shutdown", () => {
      replay?.invalidate();
      discovery.stop();
      each((reporter) => reporter.markStatus(currentSessionId, "exited"));
      each((reporter) => reporter.disconnect());
    });
  }

  registerConsoleExtension({
    pi,
    // The Console drives one desk: the one that issued a control credential,
    // unless the operator named the desk they mean.
    config: selectConsoleDesk(configs, process.env.ODK_DESK_LINK_CONSOLE_DESK ?? ""),
    desks: configs,
    refusals,
    createControlTransport: createControlTcpTransport,
    reporterSnapshot: aggregate,
    configHint: CONFIG_HINT,
  });
}
