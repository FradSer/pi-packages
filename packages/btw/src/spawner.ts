/**
 * btw spawner — runs a side question in a fresh, read-only child Pi process.
 *
 * The child runs with `--no-session`, so the side exchange never enters the
 * main session history. It is restricted to a strict tool allowlist
 * (read, grep, find, ls): it can verify facts in the codebase, but can
 * never modify, create, or delete anything. `bash`, `edit`, and `write`
 * are explicitly excluded.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ChildProcess } from "node:child_process";
import { spawnPiChild, terminateChildProcess, resolvePiCli } from "@fradser/pi-kit";

/** Read-only builtin tools the side question may use. */
export const READ_ONLY_TOOLS = ["read", "grep", "find", "ls"];

/** Writable / executable tools that are always excluded. */
export const EXCLUDED_TOOLS = ["bash", "edit", "write"];

const PROMPT_ARG_LIMIT = 8000;
export const OUTPUT_CAP = 6_000;
export const DEFAULT_TIMEOUT_MS = 180_000;

export interface BtwUsage {
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
  totalTokens: number;
  cost: number;
}

export interface BtwTurn {
  question: string;
  answer: string;
}

export interface BtwResult {
  text: string;
  usage?: BtwUsage;
  timedOut: boolean;
  exitCode: number;
  stderr: string;
}

export interface RunBtwOptions {
  /** The side question asked by the user. */
  question: string;
  /** Read-only excerpt of recent session conversation. */
  context: string;
  /** Working directory for the child (the current session cwd). */
  cwd: string;
  /** Model pattern (e.g. "anthropic/claude-sonnet-4-5"). Defaults to the child's configured model. */
  model?: string;
  /** Abort signal — aborts the child process. */
  signal?: AbortSignal;
  /** Kill the child after this many milliseconds (default: 180s). */
  timeoutMs?: number;
  /** Completed conversation history from prior side-question turns. */
  history?: BtwTurn[];
}

type JsonEvent = {
  type?: string;
  message?: {
    role?: string;
    content?: Array<{ type?: string; text?: string }>;
    usage?: {
      input?: number;
      output?: number;
      cacheRead?: number;
      cacheWrite?: number;
      totalTokens?: number;
      cost?: { total?: number };
    };
  };
};

/**
 * Parse the JSONL output of a `pi --print --mode json` side run.
 * Returns the final assistant text and the last reported usage.
 */
export function parseBtwOutput(stdout: string): { text: string; usage?: BtwUsage } {
  let text = "";
  let usage: BtwUsage | undefined;
  for (const line of stdout.split("\n")) {
    if (!line.trim()) continue;
    let event: JsonEvent;
    try {
      event = JSON.parse(line) as JsonEvent;
    } catch {
      continue;
    }
    if (event.type !== "message_end" || event.message?.role !== "assistant") continue;
    const parts = (event.message.content ?? [])
      .filter((part) => part.type === "text" && typeof part.text === "string")
      .map((part) => part.text as string)
      .join("");
    if (parts.trim()) text = parts;
    const u = event.message.usage;
    if (u) {
      usage = {
        input: u.input ?? 0,
        output: u.output ?? 0,
        cacheRead: u.cacheRead ?? 0,
        cacheWrite: u.cacheWrite ?? 0,
        totalTokens: u.totalTokens ?? 0,
        cost: u.cost?.total ?? 0,
      };
    }
  }
  return { text: text.trim(), usage };
}

function truncate(text: string, cap: number): string {
  if (text.length <= cap) return text;
  return `${text.slice(0, cap)}\n... [truncated ${text.length - cap} chars]`;
}

/** Compose the prompt for the side-question child: instructions + context + history + question. */
export function buildBtwPrompt(
  question: string,
  context: string,
  history?: BtwTurn[],
): string {
  const lines = [
    'You are answering a quick side question ("btw") about the current coding session.',
    "You have read-only tools (read, grep, find, ls). Use them to verify facts in the codebase when helpful.",
    "You must NOT modify, create, or delete any files.",
    "Answer concisely and directly.",
    "Keep the answer within 150 words or 600 characters, whichever comes first.",
    "Use at most five short bullet points; if one sentence is enough, answer with one sentence.",
    "Do not repeat the question, summarize the session, or write a report with separate analysis and recommendations."
  ];
  if (context.trim()) {
    lines.push("", "=== Recent session context (read-only excerpt) ===", context);
  }
  if (history && history.length > 0) {
    lines.push("", "=== Side conversation history ===");
    for (const turn of history) {
      lines.push(`[User]: ${turn.question}`);
      if (turn.answer.trim()) {
        lines.push(`[Assistant]: ${turn.answer}`);
      }
      lines.push("");
    }
  }
  lines.push("=== Side question ===", question);
  return lines.join("\n");
}

/**
 * Run a side question in a child Pi process.
 *
 * The child exits when done; the resolved BtwResult carries the final
 * assistant text plus token/cost usage from the JSONL event stream.
 */
export function runBtw(options: RunBtwOptions): Promise<BtwResult> {
  return new Promise<BtwResult>((resolve) => {
    const cli = resolvePiCli();
    const args: string[] = [
      ...cli.args,
      "--print",
      "--mode",
      "json",
      "--no-session",
      "--tools",
      READ_ONLY_TOOLS.join(","),
      "--exclude-tools",
      EXCLUDED_TOOLS.join(","),
    ];
    if (options.model) args.push("--model", options.model);

    let promptDirectory: string | undefined;
    const cleanupPrompt = () => {
      if (!promptDirectory) return;
      try {
        fs.rmSync(promptDirectory, { recursive: true, force: true });
      } catch {
        // Cleanup must not hide the child process result.
      }
      promptDirectory = undefined;
    };

    try {
      const prompt = buildBtwPrompt(options.question, options.context, options.history);
      if (prompt.length > PROMPT_ARG_LIMIT) {
        promptDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "btw-"));
        const promptFile = path.join(promptDirectory, "question.md");
        fs.writeFileSync(promptFile, prompt, { mode: 0o600 });
        args.push(`@${promptFile}`);
      } else {
        args.push(prompt);
      }
    } catch (error) {
      cleanupPrompt();
      resolve({
        text: "",
        timedOut: false,
        exitCode: 1,
        stderr: error instanceof Error ? error.message : String(error),
      });
      return;
    }

    let child: ChildProcess | undefined;
    try {
      child = spawnPiChild(cli.command, args, {
        cwd: options.cwd,
        env: process.env,
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (error) {
      cleanupPrompt();
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
    let timer: ReturnType<typeof setTimeout> | undefined;
    let termination: Promise<boolean> | undefined;
    const terminate = () => {
      if (!child) return;
      termination ??= terminateChildProcess(child);
    };
    const settle = (result: BtwResult) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      cleanupPrompt();
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
      const parsed = parseBtwOutput(stdoutChunks.join(""));
      settle({
        text: truncate(parsed.text, OUTPUT_CAP),
        usage: parsed.usage,
        timedOut,
        exitCode: code ?? 0,
        stderr: truncate(stderrChunks.join("").trim(), OUTPUT_CAP),
      });
    });

    const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    timer = setTimeout(() => {
      timedOut = true;
      terminate();
    }, timeoutMs);
    timer.unref?.();

    if (options.signal) {
      if (options.signal.aborted) terminate();
      else options.signal.addEventListener("abort", terminate, { once: true });
    }
  });
}
