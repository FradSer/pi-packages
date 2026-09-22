/**
 * One minimal, read-only Pi planner by default. Explicit research tasks may
 * precede it; the host alone saves the returned plan after success and abort checks.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import {
  runPiWorker,
  type PiWorkerProgressUpdate,
  type PiWorkerUsage,
} from "@fradser/pi-kit";

export interface WorkerUsage extends PiWorkerUsage {}

export interface ExploreResult {
  focus: string;
  status: "completed" | "failed";
  findings: string;
  diagnostics: string;
  usage?: WorkerUsage;
  exitCode: number;
}

export interface PlanWorkerResult {
  exploreResults: ExploreResult[];
  planText: string;
  totalUsage?: WorkerUsage;
  exitCode: number;
  stderr: string;
}

export interface ExploreTask {
  /** What this explore worker should focus on. */
  focus: string;
  /** Detailed instructions for this explore worker. */
  instructions: string;
}

export type PlanWorkerPhase = "explore" | "writer";
export type PlanWorkerStatus = "pending" | "running" | "completed" | "failed";

export interface PlanWorkerUpdate {
  id: string;
  phase: PlanWorkerPhase;
  label: string;
  status: PlanWorkerStatus;
  activeTool?: string;
  detail?: string;
}

export interface RunPlanWorkerOptions {
  /** The planning prompt from the user. */
  prompt: string;
  /** Working directory for the child (the current session cwd). */
  cwd: string;
  /** Path where the host saves the returned plan. */
  planPath: string;
  /** Model pattern (e.g. "anthropic/claude-sonnet-4-5"). */
  model?: string;
  /** Abort signal — aborts all child processes. */
  signal?: AbortSignal;
  /** Optional explicit research tasks. Omit for a single read-only planning child. */
  exploreTasks?: ExploreTask[];
  /** Progress callback for explore/plan status. */
  onProgress?: (message: string) => void;
  /** Live worker state callback for the plan-mode status widget. */
  onUpdate?: (update: PlanWorkerUpdate) => void;
}

/** Read-only builtin tools explore workers may use. */
const EXPLORE_TOOLS = ["read", "grep", "find", "ls"];

function formatWorkerDiagnostics(stderr: string, exitCode: number): string {
  const details = stderr.trim();
  if (details) return details;
  if (exitCode !== 0) return `Worker exited with code ${exitCode}.`;
  return "Worker produced no structured result.";
}

/** Plan writer returns content; the host owns the only plan-file write. */
const PLAN_WRITER_TOOLS = ["read", "grep", "find", "ls"];

/**
 * Run a single explore worker.
 */
async function runExploreWorker(
  task: ExploreTask,
  workerId: string,
  cwd: string,
  model: string | undefined,
  signal: AbortSignal | undefined,
  onProgress?: (message: string) => void,
  onUpdate?: (update: PlanWorkerUpdate) => void,
): Promise<ExploreResult> {
  onProgress?.(`Explore  ${task.focus}`);
  onUpdate?.({ id: workerId, phase: "explore", label: task.focus, status: "running" });

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
    minimal: true,
    onUpdate: (progress) => onUpdate?.(workerProgress(workerId, "explore", task.focus, progress)),
  });
  const findings = result.text.trim();
  const status = result.exitCode === 0 && findings ? "completed" : "failed";
  onUpdate?.({
    id: workerId,
    phase: "explore",
    label: task.focus,
    status,
    detail: status === "completed" ? "Findings ready" : formatWorkerDiagnostics(result.stderr, result.exitCode),
  });

  return {
    focus: task.focus,
    status,
    findings: findings || "(no findings)",
    diagnostics: status === "completed" ? result.stderr.trim() : formatWorkerDiagnostics(result.stderr, result.exitCode),
    usage: result.usage,
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
  onUpdate?: (update: PlanWorkerUpdate) => void,
): Promise<{ planText: string; usage?: WorkerUsage; exitCode: number; stderr: string }> {
  onProgress?.("Writing plan");
  onUpdate?.({ id: "plan-writer", phase: "writer", label: "plan writer", status: "running" });

  const exploreSummary = exploreResults
    .map((r) => `## Explore: ${r.focus} [${r.status}]\n\n${r.findings}\n\nDiagnostics: ${r.diagnostics}`)
    .join("\n\n---\n\n");

  const prompt = `# Plan Writer

You are a read-only planning agent. Explore the codebase FIRST with read, grep, find and ls, then write a concrete implementation plan. Do not implement changes. Return the plan as text; never modify files.

## User Request
${userPrompt}

## Exploration Results

${exploreSummary}

## Instructions
Return the complete plan content as your final response. The host process will write it to the configured plan path: ${planPath}
Disclose unresolved research gaps from failed explore results; do not treat unexamined areas as verified.

Use this structure:

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
    minimal: true,
    onUpdate: (progress) => onUpdate?.(workerProgress("plan-writer", "writer", "plan writer", progress)),
  });
  signal?.throwIfAborted();
  const planText = result.text.trim();
  const valid = result.exitCode === 0 && planText.length > 0;
  const stderr = valid ? result.stderr : result.stderr || formatWorkerDiagnostics(result.stderr, result.exitCode);
  if (valid) fs.writeFileSync(planPath, `${planText}\n`, "utf8");
  onUpdate?.({
    id: "plan-writer",
    phase: "writer",
    label: "plan writer",
    status: valid ? "completed" : "failed",
    detail: valid ? "Plan file ready" : stderr,
  });

  return {
    planText: valid ? planText : "",
    usage: result.usage,
    exitCode: valid ? 0 : result.exitCode || 1,
    stderr,
  };
}

function workerProgress(
  id: string,
  phase: PlanWorkerPhase,
  label: string,
  progress: PiWorkerProgressUpdate,
): PlanWorkerUpdate {
  const detail = progress.activeTool ?? firstProgressLine(progress.liveThinking) ?? firstProgressLine(progress.text);
  return { id, phase, label, status: "running", activeTool: progress.activeTool, detail };
}

function firstProgressLine(text: string | undefined): string | undefined {
  return text?.split("\n").map((line) => line.trim()).find((line) => line.length > 0);
}

export async function runPlanWorker(options: RunPlanWorkerOptions): Promise<PlanWorkerResult> {
  const {
    prompt,
    cwd,
    planPath,
    model,
    signal,
    exploreTasks: userTasks,
    onProgress,
    onUpdate,
  } = options;

  signal?.throwIfAborted();

  // Ensure the plan directory exists
  fs.mkdirSync(path.dirname(planPath), { recursive: true });

  if (!userTasks?.length) {
    const result = await runPlanWriter(prompt, planPath, [], cwd, model, signal, onProgress, onUpdate);
    return { exploreResults: [], planText: result.planText, totalUsage: result.usage, exitCode: result.exitCode, stderr: result.stderr };
  }
  const exploreTasks = userTasks;

  // Phase 1: Parallel explore
  onProgress?.(`Starting ${exploreTasks.length} explore workers...`);

  const explorePromises = exploreTasks.map((task, index) =>
    runExploreWorker(task, `explore-${index + 1}`, cwd, model, signal, onProgress, onUpdate),
  );
  const exploreResults = await Promise.all(explorePromises);
  signal?.throwIfAborted();

  // Check if any explore succeeded
  const successfulExplores = exploreResults.filter((r) => r.status === "completed");
  if (successfulExplores.length === 0) {
    const diagnostics = exploreResults
      .map((result) => `${result.focus}: ${result.diagnostics}`)
      .join(" | ");
    return {
      exploreResults,
      planText: "",
      exitCode: 1,
      stderr: `All explore workers failed. ${diagnostics}`,
    };
  }

  // Phase 2: Plan writer
  const planResult = await runPlanWriter(
    prompt,
    planPath,
    exploreResults,
    cwd,
    model,
    signal,
    onProgress,
    onUpdate,
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
    exitCode: planResult.exitCode,
    stderr: planResult.stderr,
  };
}
