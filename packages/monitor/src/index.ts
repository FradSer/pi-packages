import type { ExtensionAPI, ExtensionUIContext, Theme } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import {
  MonitorManager,
  type Monitor,
  type MonitorTerminalResult,
} from "./monitor";
import { MonitorStartParams, MonitorStopParams } from "./types";

const MONITOR_GUIDANCE = `
## Background monitor

- Use monitor_start for long-running commands with a result_pattern.
- After monitor_start returns, end this turn. Do not sleep, poll, wait, or do follow-up work.
- Wait for the monitor's terminal result; it will wake you automatically.
`;

function isEscapeKey(data: string): boolean {
  return data === "\u001b" || /^\u001b\[27(?:[:;\d]*)?u$/.test(data);
}

export default function (pi: ExtensionAPI) {
  let requestRender: (() => void) | undefined;

  const manager = new MonitorManager({
    onTerminal(monitor, result) {
      requestRender?.();
      deliverTerminal(monitor, result);
    },
  });

  function deliverTerminal(monitor: Monitor, result: MonitorTerminalResult): void {
    try {
      pi.sendMessage(
        {
          customType: "monitor-result",
          content: formatTerminalMessage(monitor, result),
          display: true,
          details: { monitorId: monitor.id, result },
        },
        { deliverAs: "steer", triggerTurn: true },
      );
    } catch {
      // The session may be shutting down.
    }
  }

  function widgetRows(theme: Theme, width: number): string[] {
    const monitors = manager.list();
    if (monitors.length === 0) return [];
    const line = `${monitors.length} result monitor(s) waiting — /monitor to inspect`;
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

  function openMonitorConsole(ctx: { ui: ExtensionUIContext }): Promise<void> {
    return ctx.ui.custom<void>((_tui, theme, _keybindings, done) => {
      let selected = 0;
      let showOutput = false;
      const up = /^\u001b\[(?:[0-9;:]*)?A$|^\u001bOA$/;
      const down = /^\u001b\[(?:[0-9;:]*)?B$|^\u001bOB$/;

      const render = (width: number): string[] => {
        const monitors = manager.listAll();
        if (monitors.length === 0) return [theme.fg("dim", "(no active or recent monitors)")];
        if (selected >= monitors.length) selected = Math.max(0, monitors.length - 1);

        const lines: string[] = [
          theme.bold(`Result monitors — ${manager.list().length} active`),
          theme.fg("dim", "─".repeat(Math.max(10, Math.min(width - 1, 48)))),
        ];
        for (let index = 0; index < monitors.length; index += 1) {
          const monitor = monitors[index];
          const marker = index === selected ? theme.fg("accent", "❯ ") : "  ";
          lines.push(truncateToWidth(
            `${marker}${theme.fg(statusColor(monitor.status), monitor.id)} — ${monitor.description} (${monitor.status})`,
            Math.max(10, width - 1),
          ));
        }

        const monitor = monitors[selected];
        lines.push("", theme.fg("dim", "─".repeat(Math.max(10, Math.min(width - 1, 48)))));
        for (const line of monitorDetails(monitor, showOutput)) {
          for (const wrapped of wrapTextWithAnsi(line, Math.max(20, width - 2))) {
            lines.push(wrapped);
          }
        }
        lines.push(
          "",
          theme.fg("dim", "↑/↓ select · Enter output · x stop active · a stop all · q/Esc close"),
        );
        return lines;
      };

      return {
        render,
        invalidate: () => {},
        handleInput: (data: string) => {
          const monitors = manager.listAll();
          if (isEscapeKey(data) || data === "q" || data === "Q") {
            done();
            return;
          }
          if (down.test(data)) {
            selected = Math.min(selected + 1, Math.max(0, monitors.length - 1));
            showOutput = false;
            return;
          }
          if (up.test(data)) {
            selected = Math.max(selected - 1, 0);
            showOutput = false;
            return;
          }
          if (data === "\r" || data === "\n") {
            showOutput = !showOutput;
            return;
          }
          if (data === "x" || data === "X") {
            const monitor = monitors[selected];
            if (monitor?.status === "running") manager.stop(monitor.id);
            requestRender?.();
            return;
          }
          if (data === "a" || data === "A") {
            manager.stop();
            requestRender?.();
          }
        },
      };
    });
  }

  pi.on("session_start", async (_event, ctx) => {
    setupMonitorWidget(ctx);
    requestRender?.();
  });

  pi.on("session_shutdown", async () => {
    await manager.stopAllOnShutdown();
  });

  pi.on("before_agent_start", async (event) => {
    return { systemPrompt: event.systemPrompt + MONITOR_GUIDANCE };
  });

  pi.registerTool({
    name: "monitor_start",
    label: "Start Result Monitor",
    description: [
      "Run a non-interactive shell command in the background and wait for a declared terminal result.",
      "result_pattern is required and scans both stdout and stderr. failure_pattern is optional.",
      "Named regex captures are returned as structured fields; a named 'json' capture is parsed as JSON.",
      "Ordinary output is retained in a bounded buffer and a small diagnostic tail is included in the terminal result.",
      "Exactly one terminal notification is emitted for success, failure, timeout, or result_missing.",
    ].join(" "),
    promptSnippet: "Run a background command and expose one contracted terminal result without streaming progress logs",
    promptGuidelines: [
      "Declare the exact terminal result before starting a monitor; prefer a unique JSON sentinel for commands you can wrap.",
      "Wait for the terminal notification; it includes a bounded diagnostic tail without a polling step.",
    ],
    parameters: MonitorStartParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      if (!params.command.trim()) throw new Error("monitor_start requires a non-empty command.");
      const monitor = manager.start({
        command: params.command,
        description: params.description,
        resultPattern: params.result_pattern,
        failurePattern: params.failure_pattern,
        timeoutMs: params.timeout_ms,
        persistent: params.persistent,
        cwd: ctx.cwd,
      });
      requestRender?.();
      const timeoutNote = monitor.persistent
        ? "persistent until matched or stopped"
        : `timeout ${Math.round(monitor.timeoutMs / 1000)}s`;
      return {
        content: [{
          type: "text",
          text: [
            `Started result monitor ${monitor.id}: ${monitor.description}.`,
            `Success contract: ${monitor.resultPattern}`,
            monitor.failurePattern ? `Failure contract: ${monitor.failurePattern}` : "",
            `Status: waiting (${timeoutNote}). Progress output is retained outside model context.`,
          ].filter(Boolean).join("\n"),
        }],
        details: { monitorId: monitor.id },
        terminate: true,
      };
    },
  });

  pi.registerTool({
    name: "monitor_stop",
    label: "Stop Monitor",
    description: "Stop an active result monitor by id, or all active monitors when monitor_id is omitted.",
    promptSnippet: "Stop one or all active result monitors",
    parameters: MonitorStopParams,

    async execute(_toolCallId, params) {
      const result = manager.stop(params.monitor_id);
      requestRender?.();
      if (result.stopped.length === 0) {
        throw new Error(params.monitor_id
          ? `No active monitor with id "${params.monitor_id}".`
          : "No active monitors.");
      }
      return {
        content: [{ type: "text", text: `Stopped ${result.stopped.length} monitor(s): ${result.stopped.join(", ")}.` }],
        details: { stopped: result.stopped },
      };
    },
  });

  pi.registerCommand("monitor", {
    description: "Inspect active and recent result monitors and their bounded output",
    handler: async (_args, ctx) => {
      if (ctx.mode !== "tui") {
        const monitors = manager.list();
        ctx.ui.notify(monitors.length === 0
          ? "No active result monitors."
          : `${monitors.length} result monitor(s) waiting: ${monitors.map((monitor) => monitor.id).join(", ")}`,
        "info");
        return;
      }
      if (manager.listAll().length === 0) {
        ctx.ui.notify("No active or recent result monitors.", "info");
        return;
      }
      await openMonitorConsole(ctx);
      requestRender?.();
    },
  });

  function monitorDetails(monitor: Monitor, showOutput: boolean): string[] {
    const lines = [
      `Selected: ${monitor.id}`,
      `status: ${monitor.status}`,
      `command: ${monitor.command}`,
      `success: ${monitor.resultPattern}`,
      monitor.failurePattern ? `failure: ${monitor.failurePattern}` : "",
      `logs: ${monitor.retainedLogLines} retained, ${monitor.droppedLogLines} dropped`,
    ].filter(Boolean);
    if (monitor.terminal) lines.push(`result: ${JSON.stringify(monitor.terminal)}`);
    if (showOutput) {
      const output = monitor.terminal?.output ?? manager.tail(monitor.id, 50)?.lines;
      lines.push("", "--- Recent output ---", ...(output ?? ["(no output captured)"]));
    }
    return lines;
  }
}

function formatTerminalMessage(monitor: Monitor, result: MonitorTerminalResult): string {
  const lines = [
    `[monitor ${monitor.id}] ${monitor.description}`,
    `status=${result.status}`,
    `elapsed=${formatElapsed(result.elapsedMs)}`,
  ];

  if (result.result !== undefined) lines.push(`result=${JSON.stringify(result.result)}`);
  if (result.captures) {
    for (const [name, value] of Object.entries(result.captures)) {
      if (name === "json" || value === undefined) continue;
      lines.push(`capture.${name}=${compactValue(value)}`);
    }
  }
  if (result.resultParseError) lines.push(`result_parse_error=${compactValue(result.resultParseError)}`);
  if (result.expected) lines.push(`expected=${compactValue(result.expected)}`);
  if (result.exitCode !== undefined && result.exitCode !== null) lines.push(`exit_code=${result.exitCode}`);
  if (result.signal) lines.push(`signal=${result.signal}`);
  if (result.reason) lines.push(`reason=${compactValue(result.reason)}`);
  if (result.output?.length) lines.push(`output=${JSON.stringify(result.output)}`);
  if (result.outputTruncated) lines.push("output_truncated=true");
  return lines.join("\n");
}

function formatElapsed(milliseconds: number): string {
  if (milliseconds < 1000) return `${milliseconds}ms`;
  return `${(milliseconds / 1000).toFixed(1)}s`;
}

function compactValue(value: string): string {
  return value.replace(/[\r\n]+/g, "\\n");
}

function statusColor(status: Monitor["status"]): "warning" | "success" | "error" | "dim" {
  if (status === "running") return "warning";
  if (status === "success") return "success";
  if (status === "stopped") return "dim";
  return "error";
}
