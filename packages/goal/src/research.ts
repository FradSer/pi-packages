/**
 * Research before creation.
 *
 * A goal's objective has to say what is true when the goal is met, and the
 * model can only write that from facts. This module gathers the facts: one
 * read-only child process that explores the workspace and returns findings as
 * material for the objective.
 *
 * Two boundaries are deliberate.
 *
 * The grant is read, grep, find, and ls — never bash. The completion check
 * earns its guarantee from an empty tool grant; an explorer cannot have an
 * empty grant and still explore, so the next best line is a set with no shell
 * in it. A shell can write anything, and exploration that can write is not
 * exploration.
 *
 * Findings are material, not evidence. They inform the objective the session
 * model writes; they never reach the completion check, which is built from the
 * objective, the contract, and the executor's claim alone. The store is the
 * only writer of the findings file, so a second writer cannot appear on disk
 * beside it.
 */

import { runPiWorker, type PiWorkerUsage } from "@fradser/pi-kit";

/** The read-only grant. An explicit set, so an omitted-list default can never
 * widen it, and a set with no shell in it. */
export const RESEARCH_TOOLS: readonly string[] = ["read", "grep", "find", "ls"];

/** Cap on returned findings, so one deep exploration cannot flood the caller.
 * The cap is stated to the reader rather than silently applied. */
export const MAX_RESEARCH_CHARS = 8_000;

export interface ResearchResult {
  /** Bounded findings, or "" when the research failed. */
  findings: string;
  usage?: PiWorkerUsage;
  /** Why the research produced nothing. Findings and error are exclusive. */
  error?: string;
}

export interface RunResearchOptions {
  /** What to investigate, in the caller's words. */
  focus: string;
  /** Working directory for the child. */
  cwd: string;
  /** Research model, e.g. "anthropic/claude-haiku". Session model if unset. */
  model?: string;
  /** Abort signal to cancel the child. */
  signal?: AbortSignal;
}

/**
 * Escape a focus so it cannot close its own block and have the remainder read
 * as instruction. Same rule as the check prompt: the caller supplies text that
 * arrives inside a tagged section.
 */
function escape(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function buildResearchPrompt(options: { focus: string }): string {
  return [
    "You are a read-only research worker. Explore the codebase and report facts. You have no shell and no write tools; do not try to change anything.",
    "",
    "Answer with the findings and nothing else. Structure them as:",
    "- Key files and what they do",
    "- Current behavior relevant to the focus",
    "- Open questions the conversation did not settle",
    "",
    "Report what is, not what should be. Do not write an implementation plan and do not judge whether any objective is met.",
    "",
    "Focus:",
    "<focus>",
    escape(options.focus),
    "</focus>",
  ].join("\n");
}

function truncate(text: string): string {
  const trimmed = text.trim();
  if (trimmed.length <= MAX_RESEARCH_CHARS) return trimmed;
  return `${trimmed.slice(0, MAX_RESEARCH_CHARS)}\n…[truncated at ${MAX_RESEARCH_CHARS} characters.]`;
}

/**
 * Run one read-only research child and return its findings.
 *
 * A failure is returned, never thrown: research informs creation, so a child
 * that exits bad, prints nothing, or floods its output must reach the caller
 * as a reason, not as an exception that takes the tool call down.
 */
export async function runGoalResearch(options: RunResearchOptions): Promise<ResearchResult> {
  if (options.signal?.aborted) {
    return { findings: "", error: "Research was cancelled before it started." };
  }
  const prompt = buildResearchPrompt({ focus: options.focus });
  const result = await runPiWorker({
    prompt,
    cwd: options.cwd,
    tools: [...RESEARCH_TOOLS],
    model: options.model,
    signal: options.signal,
    minimal: true,
  });
  if (result.exitCode !== 0) {
    const stderr = result.stderr.trim();
    return {
      findings: "",
      usage: result.usage,
      error: stderr || `The research child exited with code ${result.exitCode}.`,
    };
  }
  const text = result.text.trim();
  if (!text) {
    return { findings: "", usage: result.usage, error: "The research child returned nothing." };
  }
  return { findings: truncate(text), usage: result.usage };
}
