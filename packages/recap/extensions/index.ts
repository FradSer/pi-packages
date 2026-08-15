/**
 * @fradser/pi-recap — session recap for Pi.
 *
 * After each turn, generates a concise one-line summary of what the session
 * is doing and displays it at the top of the TUI input box (above the editor).
 * Toggleable via `/recap`.
 *
 * Inspired by Claude Code's `※ recap:` feature, keeping the same scannable
 * prefix convention but adapted for pi's extension widget system.
 *
 * Settings persisted at `~/.pi/agent/recap/settings.json`:
 *   - recapEnabled: boolean (default: true)
 *   - autoRecap: boolean (default: true) — generate recap after each turn
 *   - recapModel: string (optional) — model override for recap generation
 */

import fs from "fs/promises";
import path from "path";
import os from "os";
import { spawn } from "node:child_process";
import * as nodeFs from "node:fs";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { CONFIG_DIR_NAME } from "@earendil-works/pi-coding-agent";
import { buildRecapPrompt, getLastExchange, parseRecapOutput } from "./recap";

// ── Settings ───────────────────────────────────────────────────────

interface RecapSettings {
  /** Master toggle — recap shown above the editor when true. */
  recapEnabled: boolean;
  /** Generate recap automatically after each turn. */
  autoRecap: boolean;
  /** Optional model override for recap generation (e.g. "anthropic/claude-haiku-3-5"). */
  recapModel?: string;
}

const DEFAULT_SETTINGS: RecapSettings = {
  recapEnabled: true,
  autoRecap: true,
};

function settingsFilePath(): string {
  return path.join(os.homedir(), CONFIG_DIR_NAME, "agent", "recap", "settings.json");
}

async function readSettings(): Promise<RecapSettings> {
  try {
    const raw = await fs.readFile(settingsFilePath(), "utf-8");
    const parsed = JSON.parse(raw) as Partial<RecapSettings>;
    return { ...DEFAULT_SETTINGS, ...parsed };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

async function writeSettings(s: RecapSettings): Promise<void> {
  const dir = path.dirname(settingsFilePath());
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(settingsFilePath(), JSON.stringify(s, null, 2) + "\n", "utf-8");
}

// ── Pi CLI resolution ──────────────────────────────────────────────

function isPiPackageScript(filePath: string): boolean {
  try {
    const resolved = nodeFs.realpathSync(filePath);
    if (!/\.(mjs|cjs|js)$/.test(resolved)) return false;
    let dir = path.dirname(resolved);
    while (dir !== path.dirname(dir)) {
      const pkgPath = path.join(dir, "package.json");
      if (nodeFs.existsSync(pkgPath)) {
        const pkg = JSON.parse(nodeFs.readFileSync(pkgPath, "utf-8")) as { name?: unknown };
        return pkg.name === "@earendil-works/pi-coding-agent";
      }
      dir = path.dirname(dir);
    }
  } catch {
    // Unreadable paths are simply not candidates.
  }
  return false;
}

function resolvePiCli(): { command: string; args: string[] } | undefined {
  const argv1 = process.argv[1];
  if (argv1 && isPiPackageScript(argv1)) {
    return { command: process.execPath, args: [path.resolve(argv1)] };
  }

  try {
    const entry = fileURLToPath(import.meta.resolve("@earendil-works/pi-coding-agent"));
    const packageRoot = path.dirname(path.dirname(entry));
    const cliPath = path.join(packageRoot, "dist", "cli.js");
    if (nodeFs.existsSync(cliPath)) {
      return { command: process.execPath, args: [cliPath] };
    }
  } catch {
    // Package resolution is best-effort; fall through to PATH.
  }

  return { command: "pi", args: [] };
}

// ── Recap generation (child process) ───────────────────────────────

const RECAP_TIMEOUT_MS = 15_000;
const RECAP_OUTPUT_CAP = 200;

interface RecapResult {
  text: string;
  timedOut: boolean;
  exitCode: number;
  stderr: string;
}

/**
 * Run the recap generation in a child Pi process (no tools, no session,
 * JSON mode). Returns the generated recap text or an empty string on failure.
 */
export function generateRecap(
  user: string,
  assistant: string,
  model?: string,
  signal?: AbortSignal,
): Promise<RecapResult> {
  return new Promise<RecapResult>((resolve) => {
    const cli = resolvePiCli();
    if (!cli) {
      resolve({ text: "", timedOut: false, exitCode: 1, stderr: "Could not resolve Pi CLI" });
      return;
    }

    const args: string[] = [
      ...cli.args,
      "--print",
      "--mode",
      "json",
      "--no-session",
      "--no-tools",
    ];
    if (model) args.push("--model", model);

    const prompt = buildRecapPrompt(user, assistant);
    args.push(prompt);

    let child;
    try {
      child = spawn(cli.command, args, {
        cwd: process.cwd(),
        env: process.env,
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (error) {
      resolve({
        text: "",
        timedOut: false,
        exitCode: 1,
        stderr: error instanceof Error ? error.message : String(error),
      });
      return;
    }

    const stdoutChunks: string[] = [];
    const stderrChunks: string[] = [];
    let timedOut = false;
    let settled = false;
    const settle = (result: RecapResult) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      resolve(result);
    };

    child.stdout?.on("data", (chunk: Buffer) => stdoutChunks.push(chunk.toString()));
    child.stderr?.on("data", (chunk: Buffer) => stderrChunks.push(chunk.toString()));
    child.on("error", (error) => {
      settle({
        text: "",
        timedOut,
        exitCode: 1,
        stderr: error instanceof Error ? error.message : String(error),
      });
    });
    child.on("close", (code) => {
      const text = parseRecapOutput(stdoutChunks.join(""));
      settle({
        text: text.slice(0, RECAP_OUTPUT_CAP),
        timedOut,
        exitCode: code ?? 0,
        stderr: stderrChunks.join("").trim().slice(0, RECAP_OUTPUT_CAP),
      });
    });

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, RECAP_TIMEOUT_MS);
    timer.unref?.();

    if (signal) {
      if (signal.aborted) child.kill("SIGTERM");
      else signal.addEventListener("abort", () => child.kill("SIGTERM"), { once: true });
    }
  });
}

// ─── Widget ────────────────────────────────────────────────────────

const SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

interface RecapWidgetState {
  /** Current recap text (empty = generating). */
  text: string;
  /** True while the child process is generating a recap. */
  generating: boolean;
}

let recapWidgetState: RecapWidgetState = { text: "", generating: false };
let recapTimer: NodeJS.Timeout | undefined;

/**
 * Register or update the recap widget above the editor.
 * Pass undefined to remove the widget entirely.
 */
function updateRecapWidget(ctx: ExtensionContext, settings: RecapSettings): void {
  if (!settings.recapEnabled || ctx.mode !== "tui") {
    if (ctx.mode === "tui") ctx.ui.setWidget("recap", undefined);
    return;
  }

  ctx.ui.setWidget(
    "recap",
    (tui, theme) => {
      let frameIndex = 0;
      if (recapTimer) {
        clearInterval(recapTimer);
        recapTimer = undefined;
      }

      if (recapWidgetState.generating) {
        recapTimer = setInterval(() => {
          frameIndex++;
          tui.requestRender();
        }, 80);
        recapTimer.unref?.();
      }

      return {
        render: (_width: number) => {
          if (recapWidgetState.generating) {
            const frame = SPINNER_FRAMES[frameIndex % SPINNER_FRAMES.length];
            const icon = theme.fg("accent", frame);
            const text = theme.fg("dim", " recapping...");
            return [` ${icon}${text}`];
          }

          const text = recapWidgetState.text;
          if (!text) return [];

          const prefix = theme.fg("accent", "recap");
          const body = theme.fg("muted", text);
          return [` ${prefix}  ${body}`];
        },
        invalidate: () => {},
        dispose: () => {
          if (recapTimer) {
            clearInterval(recapTimer);
            recapTimer = undefined;
          }
        },
      };
    },
    { placement: "aboveEditor" },
  );
}

/**
 * Start generating a recap in the background.
 * Updates the widget state when done.
 */
async function refreshRecap(
  ctx: ExtensionContext,
  user: string,
  assistant: string,
  settings: RecapSettings,
): Promise<void> {
  // Clear previous text and show spinner
  recapWidgetState.text = "";
  recapWidgetState.generating = true;
  updateRecapWidget(ctx, settings);

  const result = await generateRecap(user, assistant, settings.recapModel);

  recapWidgetState.generating = false;
  if (result.text) {
    recapWidgetState.text = result.text;
  } else {
    recapWidgetState.text = "";
  }
  updateRecapWidget(ctx, settings);
}

// ── Extension ──────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  // Track whether the next agent_settled should generate a recap.
  // Reset to true on each user input, set to false after we generate.
  let shouldRecap = false;

  pi.on("input", (event) => {
    if (event.source === "interactive") {
      shouldRecap = true;
    }
  });

  pi.on("agent_settled", async (_event, ctx) => {
    if (!shouldRecap) return;
    shouldRecap = false;

    const settings = await readSettings();
    if (!settings.recapEnabled || !settings.autoRecap) return;

    if (ctx.mode !== "tui") return;

    // Get the last exchange from the session
    const entries = ctx.sessionManager.getBranch();
    const exchange = getLastExchange(entries);
    if (!exchange) return;

    // Generate recap in background (don't await — it's fire-and-forget)
    refreshRecap(ctx, exchange.user, exchange.assistant, settings);
  });

  // Restore previous recap when session is reloaded
  pi.on("session_start", async (_event, ctx) => {
    const settings = await readSettings();
    updateRecapWidget(ctx, settings);
  });

  // /recap command — toggle, configure, or generate manually
  pi.registerCommand("recap", {
    description: "Toggle session recap or configure settings",
    handler: async (_args, ctx) => {
      const settings = await readSettings();
      const args = _args.trim().toLowerCase();

      if (args === "off" || args === "0" || args === "disable") {
        settings.recapEnabled = false;
        await writeSettings(settings);
        updateRecapWidget(ctx, settings);
        if (ctx.hasUI) ctx.ui.notify("Recap: off", "info");
        return;
      }

      if (args === "on" || args === "1" || args === "enable") {
        settings.recapEnabled = true;
        await writeSettings(settings);
        updateRecapWidget(ctx, settings);
        if (ctx.hasUI) ctx.ui.notify("Recap: on", "info");
        return;
      }

      if (args === "auto" || args === "automatic") {
        settings.autoRecap = !settings.autoRecap;
        await writeSettings(settings);
        if (ctx.hasUI) {
          ctx.ui.notify(`Auto-recap: ${settings.autoRecap ? "on" : "off"}`, "info");
        }
        return;
      }

      if (args === "now" || args === "generate") {
        const entries = ctx.sessionManager.getBranch();
        const exchange = getLastExchange(entries);
        if (!exchange) {
          if (ctx.hasUI) ctx.ui.notify("No recent exchange to recap", "warning");
          return;
        }
        if (ctx.hasUI) ctx.ui.notify("Generating recap...", "info");
        await refreshRecap(ctx, exchange.user, exchange.assistant, settings);
        if (ctx.hasUI) {
          ctx.ui.notify(
            recapWidgetState.text
              ? `Recap: ${recapWidgetState.text}`
              : "Recap generation failed",
            "info",
          );
        }
        return;
      }

      if (!ctx.hasUI) {
        ctx.ui.notify(
          [
            `Recap: ${settings.recapEnabled ? "on" : "off"}`,
            `Auto-recap: ${settings.autoRecap ? "on" : "off"}`,
            settings.recapModel ? `Model: ${settings.recapModel}` : "Model: (session default)",
          ].join("\n"),
          "info",
        );
        return;
      }

      const options = [
        `Toggle recap (currently ${settings.recapEnabled ? "on" : "off"})`,
        `Toggle auto-recap (currently ${settings.autoRecap ? "on" : "off"})`,
        "Generate recap now",
        "Set recap model (session default)",
        settings.recapModel ? `Clear recap model override` : "",
      ].filter(Boolean);

      const choice = await ctx.ui.select(
        `Recap settings\n\n${recapWidgetState.text ? `Current recap: ${recapWidgetState.text}` : ""}`,
        options,
      );
      if (!choice) return;

      if (choice.startsWith("Toggle recap")) {
        settings.recapEnabled = !settings.recapEnabled;
        await writeSettings(settings);
        updateRecapWidget(ctx, settings);
        ctx.ui.notify(`Recap: ${settings.recapEnabled ? "on" : "off"}`, "info");
      } else if (choice.startsWith("Toggle auto-recap")) {
        settings.autoRecap = !settings.autoRecap;
        await writeSettings(settings);
        ctx.ui.notify(`Auto-recap: ${settings.autoRecap ? "on" : "off"}`, "info");
      } else if (choice.startsWith("Generate recap now")) {
        const entries = ctx.sessionManager.getBranch();
        const exchange = getLastExchange(entries);
        if (!exchange) {
          ctx.ui.notify("No recent exchange to recap", "warning");
          return;
        }
        await refreshRecap(ctx, exchange.user, exchange.assistant, settings);
        ctx.ui.notify(
          recapWidgetState.text
            ? `Recap: ${recapWidgetState.text}`
            : "Recap generation failed",
          "info",
        );
      } else if (choice.startsWith("Set recap model")) {
        const model = await ctx.ui.input(
          "Recap model override (e.g. anthropic/claude-haiku-3-5, or empty to use session default):",
          settings.recapModel ?? "",
        );
        if (model === undefined) return; // cancelled
        settings.recapModel = model.trim() || undefined;
        await writeSettings(settings);
        ctx.ui.notify(
          settings.recapModel
            ? `Recap model: ${settings.recapModel}`
            : "Recap model: session default",
          "info",
        );
      } else if (choice.startsWith("Clear recap model")) {
        settings.recapModel = undefined;
        await writeSettings(settings);
        ctx.ui.notify("Recap model: session default", "info");
      }
    },
  });
}