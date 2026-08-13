/**
 * @fradser/monitor — Pi extension for background process monitoring.
 *
 * Runs a shell command in the background and streams its stdout to the agent
 * as notifications, so the agent reacts to logs, deploys, CI runs, or file
 * changes the moment something happens — no polling loops.
 *
 * Tools registered:
 *   monitor_start — spawn a background command and stream its stdout
 *   monitor_list  — list active monitors
 *   monitor_stop  — stop a monitor by id, or all of them
 *
 * Command registered:
 *   /monitor — full-screen console to inspect and stop active monitors
 */

import type { ExtensionAPI, ExtensionUIContext, Theme } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import {
  MAX_EVENTS,
  MonitorManager,
  type Monitor,
  type MonitorStatus,
} from "./monitor";
import { EmptyParams, MonitorStartParams, MonitorStopParams } from "./types";

const MONITOR_GUIDANCE = `
## Background Monitor

You have a \`monitor_start\` tool that runs a shell command in the background and streams its stdout to you as notifications — no polling needed. Use it to watch deploy logs, CI runs, file changes, or test output, and react the moment something happens.

- Start: \`monitor_start command="..." description="..."\` (optional \`timeout_ms\`, or \`persistent=true\` to run for the whole session).
- **Avoid noise with \`match\`:** when you are waiting for ONE specific thing, pass \`match="..."\` (a regex, matched case-insensitively). Only matching stdout lines wake you; everything else is suppressed and counted, then reported when the monitor ends. A noisy command without \`match\` will flood you with notifications, so set \`match\` unless you genuinely need to see the whole stream.
- Each batch of matching stdout lines wakes you as a "[monitor ...]" message; stderr and suppressed lines are reported only when the monitor ends.
- Manage with \`monitor_list\` and \`monitor_stop\`; monitors auto-stop on timeout (default 5 min) or after too many notifications.
- Prefer this over bash sleep-polling loops for anything that takes an unknown amount of time.
`;

/** Esc arrives as bare \\x1b or as CSI-u \\x1b[27u under the Kitty protocol pi negotiates. */
function isEscapeKey(data: string): boolean {
  return data === "\u001b" || /^\u001b\[27(?:[:;\d]*)?u$/.test(data);
}

export default function (pi: ExtensionAPI) {
  let requestRender: (() => void) | undefined;

  const manager = new MonitorManager({
    onEvent(monitor, lines) {
      requestRender?.();
      deliver([`[monitor ${monitor.id}] ${monitor.description}`, ...lines].join("\n"), monitor.id);
    },
    onStop(monitor, reason) {
      requestRender?.();
      if (reason === "stopped") return; // agent-initiated, no notification needed
      deliver(stopMessage(monitor, reason), monitor.id);
    },
  });

  function deliver(content: string, monitorId: string): void {
    try {
      pi.sendMessage(
        { customType: "monitor", content, display: true, details: { monitorId } },
        { deliverAs: "steer", triggerTurn: true },
      );
    } catch {
      // Agent may be shutting down; drop the event rather than crash.
    }
  }

  function stopMessage(
    monitor: { id: string; description: string; timeoutMs: number; finalOutput: string },
    reason: MonitorStatus,
  ): string {
    const header = `[monitor ${monitor.id}] ${monitor.description}`;
    let body: string;
    if (reason === "completed") body = `${header} completed.`;
    else if (reason === "timeout") body = `${header} timed out after ${Math.round(monitor.timeoutMs / 1000)}s.`;
    else if (reason === "event_limit") body = `${header} stopped after ${MAX_EVENTS} notifications.`;
    else body = `${header} stopped with an error.`;
    const final = monitor.finalOutput.trim();
    return final ? `${body}\nFinal output:\n${final.slice(-4000)}` : body;
  }

  // ── Passive widget (below the editor) — display only, no key interception ──
  // Shows "N monitor(s) running" while monitors are active; interaction lives in
  // the /monitor full-screen console, which owns its input.

  function widgetRows(theme: Theme, width: number): string[] {
    const monitors = manager.list();
    if (monitors.length === 0) return [];
    const line = `${monitors.length} monitor(s) running — /monitor to inspect`;
    return [truncateToWidth(theme.fg("warning", line), Math.max(10, width - 1))];
  }

  function setupMonitorWidget(ctx: { mode: string; ui: ExtensionUIContext }): void {
    if (ctx.mode !== "tui") return;
    ctx.ui.setWidget("monitor", (tui, theme) => {
      requestRender = () => tui.requestRender();
      return {
        render: (width) => widgetRows(theme, width),
        invalidate: () => {},
        dispose: () => {
          requestRender = undefined;
        },
      };
    }, { placement: "belowEditor" });
  }

  // ── Full-screen console (/monitor) — owns input ──────────────────

  function openMonitorConsole(ctx: { ui: ExtensionUIContext }): Promise<void> {
    return ctx.ui.custom<void>((_tui, theme, _keybindings, done) => {
      let selected = 0;
      const up = /^\u001b\[(?:[0-9;:]*)?A$|^\u001bOA$/;
      const down = /^\u001b\[(?:[0-9;:]*)?B$|^\u001bOB$/;

      const stopOne = (id: string): void => {
        manager.stop(id);
        requestRender?.();
      };

      const render = (width: number): string[] => {
        const monitors = manager.list();
        if (monitors.length === 0) return [theme.fg("dim", "(no active monitors)")];

        if (selected >= monitors.length) selected = Math.max(0, monitors.length - 1);
        const lines: string[] = [
          theme.bold(`Monitors — ${monitors.length} running`),
          theme.fg("dim", "─".repeat(28)),
        ];
        for (let i = 0; i < monitors.length; i++) {
          const m = monitors[i];
          const marker = i === selected ? theme.fg("accent", "❯ ") : "  ";
          const age = Math.round((Date.now() - m.startedAt) / 1000);
          lines.push(
            truncateToWidth(
              `${marker}${theme.fg("warning", m.id)} — ${m.description} (${m.events} event(s), ${age}s)`,
              Math.max(10, width - 1),
            ),
          );
        }

        const m = monitors[selected];
        lines.push(
          "",
          theme.fg("dim", "─".repeat(28)),
          theme.bold(`Selected: ${m.id}`),
        );
        for (const detail of wrapTextWithAnsi(`command: ${m.command}`, Math.max(20, width - 2))) {
          lines.push(theme.fg("dim", detail));
        }
        const timing = m.persistent
          ? "persistent (no timeout)"
          : `timeout in ${Math.max(0, Math.round(m.timeoutMs / 1000) - Math.round((Date.now() - m.startedAt) / 1000))}s`;
        lines.push(theme.fg("dim", `status: ${m.status} | notifications: ${m.events} | ${timing}`));
        if (m.skipped > 0) lines.push(theme.fg("dim", `suppressed: ${m.skipped} non-matching line(s)`));
        lines.push(
          "",
          theme.fg("dim", "↑/↓ select · Enter refresh · x stop · a stop all · q/Esc close"),
        );
        return lines;
      };

      return {
        render,
        invalidate: () => {},
        handleInput: (data: string) => {
          const monitors = manager.list();
          if (isEscapeKey(data) || data === "q" || data === "Q") {
            done();
            return;
          }
          if (down.test(data)) {
            selected = Math.min(selected + 1, Math.max(0, monitors.length - 1));
            return;
          }
          if (up.test(data)) {
            selected = Math.max(selected - 1, 0);
            return;
          }
          if (data === "x" || data === "X") {
            const m = monitors[selected];
            if (m) stopOne(m.id);
            if (manager.list().length === 0) done();
            return;
          }
          if (data === "a" || data === "A") {
            manager.stop();
            done();
          }
        },
      };
    });
  }

  // ── Lifecycle ───────────────────────────────────────────────────

  pi.on("session_start", async (_event, ctx) => {
    setupMonitorWidget(ctx);
    requestRender?.();
  });

  pi.on("session_shutdown", async () => {
    manager.stopAllOnShutdown();
  });

  pi.on("before_agent_start", async (event) => {
    return { systemPrompt: event.systemPrompt + MONITOR_GUIDANCE };
  });

  // ── Tools ───────────────────────────────────────────────────────

  pi.registerTool({
    name: "monitor_start",
    label: "Start Monitor",
    description: [
      "Run a shell command in the background and stream its stdout to the conversation.",
      "Each batch of matching output lines wakes the agent as a notification, so it can react to",
      "logs, deploys, CI runs, or file changes without polling. stderr is captured and reported when",
      "the monitor ends; it does not trigger notifications. Pass match= (case-insensitive regex) to",
      "only wake on lines that matter and suppress the rest as noise. Monitors are session-scoped and",
      "auto-stop after a timeout (default 5 min, max 1 hr) or after too many notifications.",
      "The command must not require interactive input.",
    ].join(" "),
    promptSnippet: "Run a shell command in the background and stream matching stdout lines to the agent as notifications (no polling)",
    promptGuidelines: [
      "Use monitor_start to watch logs, deploys, CI runs, or test output instead of bash sleep-polling loops.",
      "When waiting for one specific thing, pass monitor_start's match= regex so only matching stdout lines wake the agent — non-matching lines are suppressed as noise.",
    ],
    parameters: MonitorStartParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      if (!params.command.trim()) {
        throw new Error("monitor_start requires a non-empty command.");
      }

      const monitor = manager.start({
        command: params.command,
        description: params.description,
        timeoutMs: params.timeout_ms,
        persistent: params.persistent,
        match: params.match,
        cwd: ctx.cwd,
      });
      requestRender?.();

      const timeoutNote = monitor.persistent
        ? "persistent (runs until stopped or the session ends)"
        : `auto-stops after ${Math.round(monitor.timeoutMs / 1000)}s`;

      return {
        content: [
          {
            type: "text",
            text: [
              `Started monitor ${monitor.id} watching "${monitor.description}".`,
              `Command: ${monitor.command}`,
              `Status: running (${timeoutNote})`,
              params.match ? `Filtering to lines matching: ${params.match}` : "",
              `stdout lines will stream here as notifications; stop with monitor_stop monitor_id="${monitor.id}".`,
            ]
              .filter(Boolean)
              .join("\n"),
          },
        ],
        details: { monitorId: monitor.id },
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "monitor_list",
    label: "List Monitors",
    description: "List active background monitors (id, description, command, status, notification count, age).",
    promptSnippet: "List active background monitors",
    parameters: EmptyParams,

    async execute() {
      const monitors = manager.list();
      if (monitors.length === 0) {
        return { content: [{ type: "text", text: "No active monitors." }], details: {} };
      }

      const lines = monitors.map((m: Monitor) => {
        const ageSec = Math.round((Date.now() - m.startedAt) / 1000);
        const timing = m.persistent
          ? "persistent"
          : `timeout in ${Math.max(0, Math.round(m.timeoutMs / 1000) - ageSec)}s`;
        return [
          `- ${m.id}: ${m.description}`,
          `  command: ${m.command}`,
          `  status: ${m.status} | notifications: ${m.events} | age: ${ageSec}s | ${timing}`,
          m.skipped > 0 ? `  suppressed: ${m.skipped} non-matching line(s)` : "",
        ]
          .filter(Boolean)
          .join("\n");
      });

      return {
        content: [{ type: "text", text: `## Active Monitors (${monitors.length})\n\n${lines.join("\n")}` }],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "monitor_stop",
    label: "Stop Monitor",
    description: "Stop a background monitor by id, or stop all active monitors when monitor_id is omitted.",
    promptSnippet: "Stop a background monitor by id, or all of them",
    parameters: MonitorStopParams,

    async execute(_toolCallId, params) {
      const result = manager.stop(params.monitor_id);
      requestRender?.();
      if (result.stopped.length === 0) {
        throw new Error(
          params.monitor_id ? `No active monitor with id "${params.monitor_id}".` : "No active monitors.",
        );
      }
      return {
        content: [{ type: "text", text: `Stopped ${result.stopped.length} monitor(s): ${result.stopped.join(", ")}.` }],
        details: { stopped: result.stopped },
      };
    },
  });

  // ── Command ─────────────────────────────────────────────────────

  pi.registerCommand("monitor", {
    description: "Open the monitor console: inspect and stop active background monitors",
    handler: async (_args, ctx) => {
      if (ctx.mode !== "tui") {
        const monitors = manager.list();
        ctx.ui.notify(
          monitors.length === 0
            ? "No active monitors."
            : `${monitors.length} monitor(s) running: ${monitors.map((m) => m.id).join(", ")}`,
          "info",
        );
        return;
      }
      if (manager.list().length === 0) {
        ctx.ui.notify("No active monitors.", "info");
        return;
      }
      await openMonitorConsole(ctx);
      requestRender?.();
    },
  });
}
