import fs from "node:fs/promises";
import path from "node:path";
import { createPackageAgentRun, runPiWorker, type PiWorkerUsage } from "@fradser/pi-kit";
import { sha256Digest, writeFileAtomic } from "./consolidation-run";

export interface LearningExplorationResult {
  path: string;
  digest: string;
  durationMs: number;
  usage?: PiWorkerUsage;
  outcome: "applied" | "failed" | "cancelled";
  error?: string;
}

interface Exploration {
  kind: "learning-exploration";
  version: 1;
  contextDigest: string;
  memory: unknown[];
  harness: unknown[];
  agents: unknown[];
  paths: unknown[];
}

function boundedStrings(value: unknown, allowedSources = false): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  return Object.entries(value as Record<string, unknown>).every(([key, item]) => {
    if (typeof item !== "string" || item.length > 1_000) return false;
    return !allowedSources || key !== "source" || item === "user" || item === "tool";
  });
}

function parseExploration(text: string, contextDigest: string): Exploration | undefined {
  try {
    const value = JSON.parse(text) as Partial<Exploration>;
    if (value.kind !== "learning-exploration" || value.version !== 1 || value.contextDigest !== contextDigest) return undefined;
    if (![value.memory, value.harness, value.agents, value.paths].every(Array.isArray)) return undefined;
    if (value.memory!.length > 12 || value.harness!.length > 12 || value.agents!.length > 12 || value.paths!.length > 24) return undefined;
    if (![...value.memory!, ...value.harness!, ...value.agents!].every((item) => boundedStrings(item, true))) return undefined;
    if (!value.paths!.every((item) => typeof item === "string" && item.length <= 1_000 && !path.isAbsolute(item) && !item.split(/[\\/]/).includes(".."))) return undefined;
    return value as Exploration;
  } catch {
    return undefined;
  }
}

export async function exploreLearningContext(input: {
  pkgDir: string;
  cwd: string;
  snapshotPath: string;
  contextDigest: string;
  outputDir: string;
  model?: string;
  signal?: AbortSignal;
}): Promise<LearningExplorationResult> {
  const startedAt = Date.now();
  const procedure = createPackageAgentRun({
    packageRootUrl: new URL("../", import.meta.url).href,
    resourcePath: "agents/learning-explorer.md",
    namePrefix: "learning-explorer",
    toolCallId: `learning-explorer:${input.contextDigest.slice(0, 12)}`,
    request: "Follow the parent-provided task below.",
  }).prompt;
  const prompt = [
    "Task: build one bounded read-only learning dossier for later planners.",
    `- Context digest: ${input.contextDigest}`,
    `- Immutable snapshot: ${input.snapshotPath}`,
    `- Repository root: ${input.cwd}`,
    "- Read the snapshot first and return exactly one JSON object.",
    "",
    procedure,
  ].join("\n");
  const result = await runPiWorker({
    prompt,
    cwd: input.cwd,
    tools: ["read", "grep", "find", "ls"],
    model: input.model,
    signal: input.signal,
    minimal: true,
  });
  const durationMs = Date.now() - startedAt;
  if (result.cancelled) return { path: "", digest: "", durationMs, usage: result.usage, outcome: "cancelled", error: result.stderr };
  if (result.exitCode !== 0) return { path: "", digest: "", durationMs, usage: result.usage, outcome: "failed", error: result.stderr };
  const exploration = parseExploration(result.text, input.contextDigest);
  if (!exploration) return { path: "", digest: "", durationMs, usage: result.usage, outcome: "failed", error: "explorer returned an invalid dossier" };
  const bytes = `${JSON.stringify(exploration, null, 2)}\n`;
  const outputPath = path.join(input.outputDir, "learning-exploration.json");
  await fs.mkdir(input.outputDir, { recursive: true });
  await writeFileAtomic(outputPath, bytes, 0o600);
  return { path: outputPath, digest: sha256Digest(bytes), durationMs, usage: result.usage, outcome: "applied" };
}
