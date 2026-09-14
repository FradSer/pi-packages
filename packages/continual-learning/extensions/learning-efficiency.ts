import fs from "node:fs/promises";
import path from "node:path";
import type { PiWorkerUsage } from "@fradser/pi-kit";

export type LearningMode = "automatic" | "manual";
export type LearningPhase = "explorer" | "memory" | "harness" | "agents";
export type LearningOutcome = "screened" | "skipped" | "noop" | "applied" | "rejected" | "failed" | "cancelled";

export interface LearningScreen {
  memory: boolean;
  harness: boolean;
  agents: boolean;
  reasons: string[];
}

export interface LearningAttempt {
  phase: LearningPhase;
  attempt: number;
  outcome: LearningOutcome;
  durationMs: number;
  operations: number;
  usage?: PiWorkerUsage;
}

const DURABLE_USER_PATTERN = /\b(prefer|always|never|must|should|require|decision|remember|durable|future tasks?)\b|偏好|以后|始终|永远|必须|不要|记住|约束|决定|规则|持久/iu;
const CORRECTION_PATTERN = /\b(wrong|instead|do not|don't|must not|should not|prohibit|blocked|confirmed|retry)\b|不对|改成|而不是|禁止|阻止|确认|重试|纠正/iu;
const AGENTS_PATTERN = /AGENTS\.md|instruction|workflow|process|convention|architecture|指令|流程|规范|架构/iu;

export function snapshotEntries(ctx: { sessionManager?: { buildContextEntries?: () => readonly unknown[]; getBranch?: () => readonly unknown[] } }): readonly unknown[] {
  const manager = ctx.sessionManager;
  if (!manager) return [];
  try {
    const context = manager.buildContextEntries?.();
    if (Array.isArray(context)) return context;
  } catch {
    // Fall back to the branch snapshot.
  }
  try {
    const branch = manager.getBranch?.();
    return Array.isArray(branch) ? branch : [];
  } catch {
    return [];
  }
}

function entryRole(entry: unknown): string {
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return "";
  const value = entry as Record<string, unknown>;
  const message = value.message;
  if (message && typeof message === "object" && !Array.isArray(message)) {
    const role = (message as Record<string, unknown>).role;
    if (typeof role === "string") return role;
  }
  return typeof value.role === "string" ? value.role : "";
}

function collectText(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(collectText).join("\n");
  if (!value || typeof value !== "object") return "";
  const record = value as Record<string, unknown>;
  return [record.text, record.content, record.message, record.reason, record.error].map(collectText).join("\n");
}

export function screenLearningEntries(entries: readonly unknown[], mode: LearningMode): LearningScreen {
  if (mode === "manual") return { memory: true, harness: true, agents: true, reasons: ["manual-full"] };
  const userTexts = entries.filter((entry) => entryRole(entry) === "user").map(collectText).filter(Boolean);
  const toolTexts = entries.filter((entry) => entryRole(entry) === "toolResult" || collectText(entry).includes("tool_execution")).map(collectText);
  const durable = userTexts.some((text) => DURABLE_USER_PATTERN.test(text));
  const correction = userTexts.some((text) => CORRECTION_PATTERN.test(text));
  const harnessEvent = toolTexts.some((text) => /blocked|confirm|violation|policy|harness|isError/iu.test(text));
  const agents = userTexts.some((text) => CORRECTION_PATTERN.test(text) && AGENTS_PATTERN.test(text));
  const harness = correction || harnessEvent;
  return {
    memory: durable,
    harness,
    agents,
    reasons: [durable ? "durable-user-evidence" : "no-durable-memory-evidence", harness ? "constraint-evidence" : "no-harness-evidence", agents ? "instruction-evidence" : "no-agents-evidence"],
  };
}

export type PlannerFailure = "syntax" | "validation" | "model" | "timeout" | "cancelled" | "output-limit" | "stale" | "other";

export function shouldRetryPlanner(input: {
  mode: LearningMode;
  phase: Exclude<LearningPhase, "explorer">;
  attempt: number;
  failure: PlannerFailure;
  mutated: boolean;
}): boolean {
  if (input.attempt > 0 || input.mutated) return false;
  if (["model", "timeout", "cancelled", "output-limit", "stale", "other"].includes(input.failure)) return false;
  if (input.mode === "manual") return input.failure === "syntax" || input.failure === "validation";
  return input.phase === "memory" && input.failure === "syntax";
}

export interface LearningPipelineReceipt {
  kind: "learning-pipeline-receipt";
  version: 1;
  mode: LearningMode;
  screen: LearningScreen;
  attempts: LearningAttempt[];
  totals: PiWorkerUsage;
  operations: number;
  retries: number;
}

export function buildLearningReceipt(mode: LearningMode, screen: LearningScreen, attempts: LearningAttempt[]): LearningPipelineReceipt {
  return {
    kind: "learning-pipeline-receipt",
    version: 1,
    mode,
    screen,
    attempts,
    totals: totalLearningUsage(attempts),
    operations: attempts.reduce((total, attempt) => total + attempt.operations, 0),
    retries: attempts.filter((attempt) => attempt.attempt > 0).length,
  };
}

export async function writeLearningReceipt(directory: string, receipt: LearningPipelineReceipt): Promise<string> {
  await fs.mkdir(directory, { recursive: true });
  const target = path.join(directory, "learning-pipeline-receipt.json");
  const temporary = `${target}.${process.pid}.tmp`;
  await fs.writeFile(temporary, `${JSON.stringify(receipt, null, 2)}\n`, { mode: 0o600 });
  await fs.rename(temporary, target);
  return target;
}

export function formatLearningSummary(receipt: LearningPipelineReceipt): string {
  const phases = receipt.attempts.map((attempt) => `${attempt.phase}:${attempt.outcome}`).join(", ") || "screened:skipped";
  return `Learning complete: ${receipt.operations} operation(s) · ${receipt.attempts.length} call(s) · ${receipt.totals.totalTokens} token(s) · $${receipt.totals.cost.toFixed(4)} · ${phases}`;
}

export function totalLearningUsage(attempts: readonly LearningAttempt[]): PiWorkerUsage {
  return attempts.reduce<PiWorkerUsage>((total, attempt) => {
    const usage = attempt.usage;
    if (!usage) return total;
    return {
      input: total.input + usage.input,
      output: total.output + usage.output,
      cacheRead: total.cacheRead + usage.cacheRead,
      cacheWrite: total.cacheWrite + usage.cacheWrite,
      totalTokens: total.totalTokens + usage.totalTokens,
      cost: total.cost + usage.cost,
    };
  }, { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0, cost: 0 });
}
