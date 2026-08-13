/**
 * @fradser/memory — native pi /memory command.
 *
 * Replaces the /skill:consolidate skill surface with a pi-native command menu:
 *
 *   /memory
 *     Auto-memory: on
 *     1. Consolidate memory now        (inline procedure from procedures/consolidate.md)
 *     2. Edit user instructions        (~/.pi/agent/AGENTS.md)
 *     3. Edit project instructions     (./AGENTS.md or ./CLAUDE.md — whichever exists)
 *     4. Open auto-memory folder
 *     5. Toggle auto-memory
 *
 * Auto-memory on → `before_agent_start` injects a guidance block that tells the
 * agent to actively capture durable decisions/preferences into memory (same
 * pattern as @fradser/teammate injecting its guidance). Existing memories are
 * always injected into the system prompt; the toggle only controls the
 * auto-write guidance.
 */

import fs from "fs/promises";
import path from "path";
import os from "os";
import { spawn } from "node:child_process";
import * as nodeFs from "node:fs";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { CONFIG_DIR_NAME } from "@earendil-works/pi-coding-agent";

export function getEscapedCwd(cwd: string): string {
  return cwd.replace(/\//g, "-");
}

export interface MemoryEntry {
  filename: string;
  source: "harness" | "public";
  content: string;
}

export async function loadAndDeduplicateMemories(cwd: string): Promise<MemoryEntry[]> {
  const escaped = getEscapedCwd(cwd);
  const homeDir = os.homedir();

  // Pi harness memory location (project-scoped, includes private files)
  const harnessDir = path.join(homeDir, CONFIG_DIR_NAME, "agent", "memory", escaped);
  const publicDir = path.join(cwd, ".memory");
  const memoriesMap = new Map<string, MemoryEntry>();

  // 1. Read public .memory/ first
  try {
    const files = await fs.readdir(publicDir);
    for (const file of files) {
      if (file.endsWith(".md") && file.toLowerCase() !== "memory.md") {
        const filePath = path.join(publicDir, file);
        const content = await fs.readFile(filePath, "utf-8");
        memoriesMap.set(file, {
          filename: file,
          source: "public",
          content,
        });
      }
    }
  } catch (err: unknown) {
    // ENOENT (dir missing) and other errors: skip silently
    void err;
  }

  // 2. Read harness location (takes precedence, includes private files)
  try {
    const files = await fs.readdir(harnessDir);
    for (const file of files) {
      if (file.endsWith(".md") && file.toLowerCase() !== "memory.md") {
        const filePath = path.join(harnessDir, file);
        const content = await fs.readFile(filePath, "utf-8");
        memoriesMap.set(file, {
          filename: file,
          source: "harness",
          content,
        });
      }
    }
  } catch (err: unknown) {
    // ENOENT (dir missing) and other errors: skip silently
    void err;
  }

  return Array.from(memoriesMap.values());
}

export function formatMemoriesBlock(memories: MemoryEntry[]): string {
  if (memories.length === 0) return "";

  const lines = ["# Active Project Memories\n"];
  for (const item of memories) {
    lines.push(`## Memory: ${item.filename}`);
    lines.push(item.content.trim());
    lines.push("");
  }

  return lines.join("\n");
}

// ── auto-memory settings (user-level, persisted) ───────────────────

interface MemorySettings {
  autoMemory: boolean;
  /** Context-window fraction (0-1) at which auto-consolidation fires. 0 disables. */
  consolidateAtContextFraction: number;
}

const DEFAULT_CONSOLIDATE_AT_CONTEXT_FRACTION = 0.4;

function settingsFilePath(): string {
  return path.join(os.homedir(), CONFIG_DIR_NAME, "agent", "memory", "settings.json");
}

async function readSettings(): Promise<MemorySettings> {
  try {
    const raw = await fs.readFile(settingsFilePath(), "utf-8");
    const parsed = JSON.parse(raw) as Partial<MemorySettings>;
    return {
      autoMemory: parsed.autoMemory ?? true,
      consolidateAtContextFraction:
        parsed.consolidateAtContextFraction ?? DEFAULT_CONSOLIDATE_AT_CONTEXT_FRACTION,
    };
  } catch {
    return {
      autoMemory: true,
      consolidateAtContextFraction: DEFAULT_CONSOLIDATE_AT_CONTEXT_FRACTION,
    };
  }
}

async function writeSettings(s: MemorySettings): Promise<void> {
  await fs.mkdir(path.dirname(settingsFilePath()), { recursive: true });
  await fs.writeFile(settingsFilePath(), JSON.stringify(s, null, 2) + "\n", "utf-8");
}

// ── auto-memory guidance (injected when enabled) ───────────────────

const AUTO_MEMORY_GUIDANCE = `

## Auto-memory

You maintain a durable project memory. When you encounter a decision, user
preference, lesson, gotcha, or non-obvious project fact during this session,
**write it down immediately** — do not wait for a memory command:

- Search existing memory files first; if one covers the topic, edit it instead of creating a near-duplicate.
- One decision per file. Format: frontmatter (name, description, type) + **Why** + **How to apply** + **Related** [[links]].
- Mirror safe technical content to the project's \`.memory/\`; keep private content (credentials, personal preferences) harness-only.
- Do not log pure operations or timelines — those belong in git history.

Run \`/memory\` to review, edit, or consolidate memory at any time.
- When the session context reaches the configured fraction of the active model's
  context window (\`consolidateAtContextFraction\`, default 0.4 = 40%), the
  extension spawns a **background child Pi process** to consolidate memory while
  you keep working — a \`Memory: dreaming\` widget shows above the input box
  until it finishes; your session is never blocked.
`;

// ── locate this package (consolidate procedure doc) ────────────────

async function pathExists(p: string): Promise<boolean> {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}

/**
 * Project instructions live in AGENTS.md (pi-native) or CLAUDE.md (Claude Code
 * convention) — pi loads either from cwd, so they are the same concept under
 * two names. Prefer AGENTS.md, fall back to CLAUDE.md, default to AGENTS.md.
 */
async function resolveProjectInstructionsFile(
  cwd: string,
): Promise<{ path: string; display: string }> {
  const agents = path.join(cwd, "AGENTS.md");
  const claude = path.join(cwd, "CLAUDE.md");
  if (await pathExists(agents)) return { path: agents, display: "./AGENTS.md" };
  if (await pathExists(claude)) return { path: claude, display: "./CLAUDE.md" };
  return { path: agents, display: "./AGENTS.md" };
}

/**
 * Resolve the @fradser/memory package dir. Covers npm/git installs under
 * ~/.pi/agent (via settings.json packages, including relative-path dev
 * checkouts) and the monorepo layout relative to cwd.
 */
async function resolvePackageDir(): Promise<string> {
  try {
    const settingsRaw = await fs.readFile(
      path.join(os.homedir(), CONFIG_DIR_NAME, "agent", "settings.json"),
      "utf-8",
    );
    const settings = JSON.parse(settingsRaw) as { packages?: string[] };
    const base = path.join(os.homedir(), CONFIG_DIR_NAME, "agent");
    for (const p of settings.packages ?? []) {
      if (typeof p !== "string" || !p.includes("memory")) continue;
      const dir = path.normalize(path.join(base, p));
      if (await pathExists(path.join(dir, "procedures", "consolidate.md"))) {
        return dir;
      }
    }
  } catch {
    // settings.json missing/unreadable — fall through
  }

  const fromCwd = path.join(process.cwd(), "packages", "memory");
  if (await pathExists(path.join(fromCwd, "procedures", "consolidate.md"))) {
    return fromCwd;
  }
  return process.cwd();
}

// ── child Pi process for async consolidation ("dreaming") ──────────

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
    // Unreadable paths are not candidates
  }
  return false;
}

/**
 * Resolve the Pi CLI for child-process spawning: the current process entry
 * (verified against the package manifest), the installed package's
 * dist/cli.js, or a `pi` binary on PATH (best effort).
 */
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
    // best effort — fall through to PATH
  }
  return { command: "pi", args: [] };
}

interface DreamState {
  active: boolean;
}

const DREAM_TIMEOUT_MS = 20 * 60 * 1000;
const SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

let dreamingTimer: NodeJS.Timeout | undefined;
let dreamingActivity = "";

function setDreamingWidget(ctx: ExtensionContext): void {
  if (ctx.mode !== "tui") return;

  if (dreamingTimer) {
    clearInterval(dreamingTimer);
    dreamingTimer = undefined;
  }

  ctx.ui.setWidget("memory-dreaming", (tui, theme) => {
    let frameIndex = 0;
    dreamingTimer = setInterval(() => {
      frameIndex++;
      tui.requestRender();
    }, 80);
    dreamingTimer.unref?.();

    return {
      render: (_width: number) => {
        const frame = SPINNER_FRAMES[frameIndex % SPINNER_FRAMES.length];
        const icon = theme?.fg ? theme.fg("accent", frame) : frame;
        const text = theme?.fg ? theme.fg("accent", "Dreaming...") : "Dreaming...";
        const detail = dreamingActivity
          ? theme?.fg
            ? theme.fg("muted", ` · ${dreamingActivity}`)
            : ` · ${dreamingActivity}`
          : "";
        // Leading space aligns the spinner with the native " ⠋ Working..." row.
        return [` ${icon} ${text}${detail}`];
      },
      invalidate: () => {},
      dispose: () => {
        if (dreamingTimer) {
          clearInterval(dreamingTimer);
          dreamingTimer = undefined;
        }
      },
    };
  });
}

function clearDreamingWidget(ctx: ExtensionContext): void {
  dreamingActivity = "";
  if (ctx.mode === "tui") ctx.ui.setWidget("memory-dreaming", undefined);
}

/**
 * Run the inline consolidate procedure in a fresh, non-interactive child Pi
 * process (--print --mode json --no-session) so the current session is never
 * blocked. The child gets the procedure text, the session file path (for the
 * procedure's Step 0 session-context capture), and the memory dirs. A
 * "dreaming" widget shows above the input editor until the child exits.
 */
async function spawnAsyncConsolidation(
  ctx: ExtensionContext,
  state: DreamState,
  opts: { pkgDir: string; cwd: string; sessionFile?: string; reason: string },
): Promise<void> {
  const procedure = (
    await fs.readFile(path.join(opts.pkgDir, "procedures", "consolidate.md"), "utf-8")
  ).replaceAll("{{PKG_DIR}}", opts.pkgDir);
  const harnessDir = path.join(
    os.homedir(),
    CONFIG_DIR_NAME,
    "agent",
    "memory",
    getEscapedCwd(opts.cwd),
  );

  const taskText = [
    `Task: run the memory consolidation procedure below for the project at ${opts.cwd}.`,
    `- Reason: ${opts.reason}`,
    `- Session file (Step 0: capture durable content from its tail): ${opts.sessionFile ?? "none"}`,
    `- Harness memory dir: ${harnessDir}`,
    `- Public memory dir: ${opts.cwd}/.memory`,
    "",
    procedure,
  ].join("\n");

  const cli = resolvePiCli();
  if (!cli) {
    ctx.ui.notify("Auto-consolidation: could not resolve the Pi CLI", "error");
    return;
  }

  const tempDir = nodeFs.mkdtempSync(path.join(os.tmpdir(), "memory-dream-"));
  const taskFile = path.join(tempDir, "task.md");
  nodeFs.writeFileSync(taskFile, taskText, { mode: 0o600 });

  let child;
  try {
    child = spawn(
      cli.command,
      [...cli.args, "--print", "--mode", "json", "--no-session", `@${taskFile}`],
      { cwd: opts.cwd, env: process.env, stdio: ["ignore", "pipe", "pipe"] },
    );
  } catch (err: unknown) {
    nodeFs.rmSync(tempDir, { recursive: true, force: true });
    ctx.ui.notify(`Auto-consolidation spawn failed: ${(err as Error).message}`, "error");
    return;
  }

  state.active = true;
  setDreamingWidget(ctx);

  let stdoutBuffer = "";
  let lastJsonError = "";
  child.stdout?.on("data", (chunk: Buffer) => {
    stdoutBuffer += chunk.toString();
    const lines = stdoutBuffer.split("\n");
    stdoutBuffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const event = JSON.parse(line) as {
          type?: string;
          toolName?: string;
          args?: Record<string, unknown>;
          error?: string;
        };
        if (event.error) {
          lastJsonError = typeof event.error === "string" ? event.error : JSON.stringify(event.error);
        }
        if (event.type === "tool_execution_start" && event.toolName) {
          const name = event.toolName;
          let detail = "";
          if (event.args) {
            if (typeof event.args.path === "string") {
              detail = path.basename(event.args.path);
            } else if (typeof event.args.command === "string") {
              const cmd = event.args.command.trim();
              if (cmd.includes("validate-consolidate")) {
                detail = "validate-consolidate.py";
              } else {
                // Collapse whitespace and cap length so the row stays short.
                const compact = cmd.replace(/\s+/g, " ");
                detail = compact.length > 32 ? `${compact.slice(0, 32)}…` : compact;
              }
            }
          }
          // bash <cmd> reads oddly — show the command itself; other tools show "tool path".
          dreamingActivity = name === "bash" ? detail : detail ? `${name} ${detail}` : name;
        }
      } catch {
        // ignore non-json
      }
    }
  });

  let stderr = "";
  child.stderr.on("data", (c: Buffer) => {
    stderr += c.toString();
  });

  const timer = setTimeout(() => child.kill("SIGKILL"), DREAM_TIMEOUT_MS);
  timer.unref?.();

  const finish = (code: number | null, error?: Error): void => {
    clearTimeout(timer);
    state.active = false;
    clearDreamingWidget(ctx);
    try {
      nodeFs.rmSync(tempDir, { recursive: true, force: true });
    } catch {
      // best effort
    }
    if (error) {
      ctx.ui.notify(`Memory dreaming failed to start: ${error.message}`, "error");
    } else if (code === 0) {
      ctx.ui.notify("Memory dreaming complete — memory consolidated.", "info");
    } else {
      const errReason = stderr.trim() || lastJsonError || `exit code ${code}`;
      ctx.ui.notify(
        `Memory dreaming failed: ${errReason.slice(-300)}`,
        "error",
      );
    }
  };

  child.on("error", (err) => finish(null, err));
  child.on("close", (code) => finish(code));
  child.unref();
}

async function editInstructions(ctx: ExtensionCommandContext, filePath: string): Promise<void> {
  let current = "";
  try {
    current = await fs.readFile(filePath, "utf-8");
  } catch {
    // new file — start empty
  }

  if (ctx.mode !== "tui") {
    ctx.ui.notify(`Instructions file: ${filePath}`, "info");
    return;
  }

  const edited = await ctx.ui.editor(`Edit ${filePath}:`, current);
  if (edited === undefined) return; // cancelled

  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, edited, "utf-8");
  ctx.ui.notify(`Saved ${filePath}`, "info");
}

// ── extension ──────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  // Inject existing memories + auto-memory guidance before every turn
  pi.on("before_agent_start", async (event, ctx) => {
    const cwd = ctx.cwd || process.cwd();
    const memories = await loadAndDeduplicateMemories(cwd);
    const settings = await readSettings();

    if (memories.length === 0 && !settings.autoMemory) return;

    let systemPrompt = event.systemPrompt;
    if (memories.length > 0) {
      systemPrompt = systemPrompt + "\n\n" + formatMemoriesBlock(memories);
    }
    if (settings.autoMemory) {
      systemPrompt = systemPrompt + AUTO_MEMORY_GUIDANCE;
    }
    return { systemPrompt };
  });

  // /memory command with the management menu
  pi.registerCommand("memory", {
    description: "Manage project memory: instructions, auto-memory folder, consolidation",
    handler: async (_args, ctx) => {
      const settings = await readSettings();
      const status = settings.autoMemory ? "on" : "off";
      const cwd = ctx.cwd || process.cwd();
      const escaped = getEscapedCwd(cwd);
      const harnessDir = path.join(os.homedir(), CONFIG_DIR_NAME, "agent", "memory", escaped);
      const home = os.homedir();
      const pkgDir = await resolvePackageDir();
      const procedureFile = path.join(pkgDir, "procedures", "consolidate.md");
      const projectInstructions = await resolveProjectInstructionsFile(cwd);

      const options = [
        "Consolidate memory now",
        "Edit user instructions (~/.pi/agent/AGENTS.md)",
        `Edit project instructions (${projectInstructions.display})`,
        "Open auto-memory folder",
        `Toggle auto-memory (currently ${status})`,
      ];

      if (!ctx.hasUI) {
        ctx.ui.notify(
          [
            `Auto-memory: ${status}`,
            `Harness memory: ${harnessDir}`,
            `Public memory: ${cwd}/.memory`,
            `Consolidate procedure: ${procedureFile}`,
          ].join("\n"),
          "info",
        );
        return;
      }

      const choice = await ctx.ui.select(`Auto-memory: ${status}\n\nMemory management:`, options);
      if (!choice) return; // cancelled

      if (choice.startsWith("Consolidate memory now")) {
        if (dreamState.active) {
          ctx.ui.notify("Memory consolidation is already running in background.", "info");
          return;
        }
        ctx.ui.notify("Starting memory consolidation in background worker…", "info");
        await spawnAsyncConsolidation(ctx, dreamState, {
          pkgDir,
          cwd,
          sessionFile: ctx.sessionManager?.getSessionFile(),
          reason: "Consolidate the project memory now (user-invoked via /memory menu).",
        });
      } else if (choice.startsWith("Edit user instructions")) {
        await editInstructions(ctx, path.join(home, CONFIG_DIR_NAME, "agent", "AGENTS.md"));
      } else if (choice.startsWith("Edit project instructions")) {
        await editInstructions(ctx, projectInstructions.path);
      } else if (choice.startsWith("Open auto-memory folder")) {
        await fs.mkdir(harnessDir, { recursive: true });
        if (ctx.mode === "tui" && process.platform === "darwin") {
          await pi.exec("open", [harnessDir]);
          ctx.ui.notify(`Opened ${harnessDir}`, "info");
        } else {
          ctx.ui.notify(`Auto-memory folder: ${harnessDir}`, "info");
        }
      } else if (choice.startsWith("Toggle auto-memory")) {
        const next = { ...settings, autoMemory: !settings.autoMemory };
        await writeSettings(next);
        ctx.ui.notify(`Auto-memory: ${next.autoMemory ? "on" : "off"}`, "info");
      }
    },
  });

  // ── auto-consolidation (per-session-instance state) ───────────────
  // When the session's context fill reaches a fraction of the active model's
  // context window (default 0.4 = 40%, based on research that long-context
  // quality degrades from ~40-50% fill), deliver the inline consolidate
  // procedure while idle. Tier-based firing — one trigger per fraction
  // boundary (40%, 80%, …) — means the consolidation run itself never
  // re-triggers; gated on user-typed turns (input source "interactive") and
  // interactive TUI sessions.
  let lastTriggeredTier = 0;
  let userTurnSeen = false;
  const dreamState: DreamState = { active: false };

  pi.on("input", (event) => {
    if (event.source === "interactive") userTurnSeen = true;
  });

  pi.on("agent_settled", async (_event, ctx) => {
    if (ctx.mode !== "tui") return;
    const settings = await readSettings();
    const fraction = settings.consolidateAtContextFraction;
    if (!settings.autoMemory || fraction <= 0) return;
    if (!userTurnSeen) return; // extension-injected run (e.g. consolidation)
    userTurnSeen = false;

    const usage = ctx.getContextUsage();
    if (!usage || usage.percent == null || usage.contextWindow <= 0) return;

    const tier = Math.floor(usage.percent / (fraction * 100));
    if (tier < 1 || tier <= lastTriggeredTier) return;
    lastTriggeredTier = tier;
    if (dreamState.active) return; // single-flight: one dreaming run at a time

    const pkgDir = await resolvePackageDir();
    ctx.ui.notify(
      `Memory dreaming: context ${usage.percent.toFixed(0)}% ≥ ${Math.round(fraction * 100)}% of ${usage.contextWindow} tokens — consolidating in background…`,
      "info",
    );
    await spawnAsyncConsolidation(ctx, dreamState, {
      pkgDir,
      cwd: ctx.cwd || process.cwd(),
      sessionFile: ctx.sessionManager.getSessionFile(),
      reason: `session context reached ${usage.percent.toFixed(0)}% of the ${usage.contextWindow}-token context window (≥ ${Math.round(fraction * 100)}%)`,
    });
  });
}