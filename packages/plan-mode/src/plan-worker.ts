/**
 * Plan worker spawner — runs plan generation with parallel explore workers.
 *
 * Architecture (inspired by Claude Code's plan mode):
 *
 *   Phase 1: Parallel Explore Workers
 *   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
 *   │ Explore 1   │ │ Explore 2   │ │ Explore 3   │
 *   │ (structure) │ │ (patterns)  │ │ (tests)     │
 *   └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
 *          │               │               │
 *          └───────────────┼───────────────┘
 *                          │
 *   Phase 2: Plan Writer   ▼
 *                   ┌─────────────┐
 *                   │ Plan Writer │
 *                   │ (writes     │
 *                   │  PLAN.md)   │
 *                   └─────────────┘
 *
 * Each explore worker runs in isolation with --no-session.
 * Explore workers have read-only tool access.
 * Plan writer has write access to the plan file only.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { runPiWorker, type PiWorkerUsage } from "@fradser/pi-kit";

const DEFAULT_EXPLORE_TIMEOUT_MS = 120_000; // 2 minutes per explore
const DEFAULT_PLAN_TIMEOUT_MS = 180_000; // 3 minutes for plan writing

export interface WorkerUsage extends PiWorkerUsage {}

export interface ExploreResult {
  focus: string;
  status: "completed" | "failed";
  findings: string;
  diagnostics: string;
  usage?: WorkerUsage;
  timedOut: boolean;
  exitCode: number;
}

export interface PlanWorkerResult {
  exploreResults: ExploreResult[];
  planText: string;
  totalUsage?: WorkerUsage;
  timedOut: boolean;
  exitCode: number;
  stderr: string;
}

export interface ExploreTask {
  /** What this explore worker should focus on. */
  focus: string;
  /** Detailed instructions for this explore worker. */
  instructions: string;
}

export interface RunPlanWorkerOptions {
  /** The planning prompt from the user. */
  prompt: string;
  /** Working directory for the child (the current session cwd). */
  cwd: string;
  /** Path to the plan file the writer should write to. */
  planPath: string;
  /** Model pattern (e.g. "anthropic/claude-sonnet-4-5"). */
  model?: string;
  /** Abort signal — aborts all child processes. */
  signal?: AbortSignal;
  /** Explore tasks to run in parallel. If empty, a single explore is generated from the prompt. */
  exploreTasks?: ExploreTask[];
  /** Progress callback for explore/plan status. */
  onProgress?: (message: string) => void;
}

/** Read-only builtin tools explore workers may use. */
const EXPLORE_TOOLS = ["read", "grep", "find", "ls", "bash"];

function formatWorkerDiagnostics(stderr: string, exitCode: number, timedOut: boolean): string {
  const details = stderr.trim();
  if (details) return details;
  if (timedOut) return "Worker timed out before producing a result.";
  if (exitCode !== 0) return `Worker exited with code ${exitCode}.`;
  return "Worker produced no structured result.";
}

/** Tools plan writer may use (read-only + write for plan file). */
const PLAN_WRITER_TOOLS = ["read", "grep", "find", "ls", "bash", "write"];

/**
 * Generate a single explore task from a user prompt.
 * The main session's plan mode prompt handles multi-agent orchestration;
 * the plan-worker is a single-shot fallback for /plan <prompt>.
 */
function generateExploreTask(prompt: string): ExploreTask {
  return {
    focus: "codebase exploration",
    instructions: `Explore the codebase to understand what needs to change for: ${prompt}

Focus on:
- Relevant files and their roles
- Existing patterns and conventions
- Similar implementations to reference
- Test locations and patterns
- Edge cases and potential issues

Be thorough but concise. Report facts, not recommendations.`,
  };
}

/**
 * Run a single explore worker.
 */
async function runExploreWorker(
  task: ExploreTask,
  cwd: string,
  model: string | undefined,
  signal: AbortSignal | undefined,
  onProgress?: (message: string) => void,
): Promise<ExploreResult> {
  onProgress?.(`Explore  ${task.focus}`);

  const prompt = `# Explore Worker

You are an explore worker. Your job is to investigate a specific aspect of the codebase.

## Your Focus
${task.focus}

## Instructions
${task.instructions}

## Output
Provide a concise summary of your findings. Include:
- Key files and their roles
- Relevant code patterns
- Important observations

Be thorough but concise. Focus on facts, not recommendations.`;

  const result = await runPiWorker({
    prompt,
    cwd,
    tools: EXPLORE_TOOLS,
    model,
    signal,
    timeoutMs: DEFAULT_EXPLORE_TIMEOUT_MS,
    extraArgs: ["--no-extensions"],
  });
  const findings = result.text.trim();
  const status = result.exitCode === 0 && !result.timedOut && findings ? "completed" : "failed";

  return {
    focus: task.focus,
    status,
    findings: findings || "(no findings)",
    diagnostics: formatWorkerDiagnostics(result.stderr, result.exitCode, result.timedOut),
    usage: result.usage,
    timedOut: result.timedOut,
    exitCode: result.exitCode,
  };
}

/**
 * Run the plan writer worker with explore results as context.
 */
async function runPlanWriter(
  userPrompt: string,
  planPath: string,
  exploreResults: ExploreResult[],
  cwd: string,
  model: string | undefined,
  signal: AbortSignal | undefined,
  onProgress?: (message: string) => void,
): Promise<{ planText: string; usage?: WorkerUsage; timedOut: boolean; exitCode: number; stderr: string }> {
  onProgress?.("Writing plan");

  const exploreSummary = exploreResults
    .map((r) => `## Explore: ${r.focus} [${r.status}]\n\n${r.findings}\n\nDiagnostics: ${r.diagnostics}`)
    .join("\n\n---\n\n");

  const prompt = `# Plan Writer

You are a plan writer. Based on the exploration results below, write a concrete implementation plan.

## User Request
${userPrompt}

## Exploration Results

${exploreSummary}

## Instructions
Write the plan to: ${planPath}

Use the write tool to create the plan file with this structure:

# Plan: <title>

## Context
Why this change is needed.

## Approach
Recommended solution with alternatives considered.

## Files to Modify
Specific paths and what changes each needs.

## Implementation Order
Step-by-step implementation plan.

## Verification
How to test the changes.

Be specific and actionable. The plan should be implementable without additional questions.`;

  const result = await runPiWorker({
    prompt,
    cwd,
    tools: PLAN_WRITER_TOOLS,
    model,
    signal,
    timeoutMs: DEFAULT_PLAN_TIMEOUT_MS,
  });

  return {
    planText: result.text,
    usage: result.usage,
    timedOut: result.timedOut,
    exitCode: result.exitCode,
    stderr: result.stderr,
  };
}

/**
 * Main entry point: run parallel explore workers, then plan writer.
 */
export async function runPlanWorker(options: RunPlanWorkerOptions): Promise<PlanWorkerResult> {
  const {
    prompt,
    cwd,
    planPath,
    model,
    signal,
    exploreTasks: userTasks,
    onProgress,
  } = options;

  // Ensure the plan directory exists
  fs.mkdirSync(path.dirname(planPath), { recursive: true });

  const exploreTasks = userTasks && userTasks.length > 0 ? userTasks : [generateExploreTask(prompt)];

  // Phase 1: Parallel explore
  onProgress?.(`Starting ${exploreTasks.length} explore workers...`);

  const explorePromises = exploreTasks.map((task) =>
    runExploreWorker(task, cwd, model, signal, onProgress),
  );
  const exploreResults = await Promise.all(explorePromises);

  // Check if any explore succeeded
  const successfulExplores = exploreResults.filter((r) => r.status === "completed");
  if (successfulExplores.length === 0) {
    const diagnostics = exploreResults
      .map((result) => `${result.focus}: ${result.diagnostics}`)
      .join(" | ");
    return {
      exploreResults,
      planText: "",
      timedOut: exploreResults.every((r) => r.timedOut),
      exitCode: 1,
      stderr: `All explore workers failed. ${diagnostics}`,
    };
  }

  // Phase 2: Plan writer
  const planResult = await runPlanWriter(
    prompt,
    planPath,
    successfulExplores,
    cwd,
    model,
    signal,
    onProgress,
  );

  // Aggregate usage
  const allUsages = [...exploreResults.map((r) => r.usage).filter(Boolean), planResult.usage].filter(
    (u): u is WorkerUsage => u !== undefined,
  );
  const totalUsage =
    allUsages.length > 0
      ? {
          input: allUsages.reduce((sum, u) => sum + u.input, 0),
          output: allUsages.reduce((sum, u) => sum + u.output, 0),
          cacheRead: allUsages.reduce((sum, u) => sum + u.cacheRead, 0),
          cacheWrite: allUsages.reduce((sum, u) => sum + u.cacheWrite, 0),
          totalTokens: allUsages.reduce((sum, u) => sum + u.totalTokens, 0),
          cost: allUsages.reduce((sum, u) => sum + u.cost, 0),
        }
      : undefined;

  return {
    exploreResults,
    planText: planResult.planText,
    totalUsage,
    timedOut: planResult.timedOut,
    exitCode: planResult.exitCode,
    stderr: planResult.stderr,
  };
}
