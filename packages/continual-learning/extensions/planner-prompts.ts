import { projectPushCoverage } from "./harness-command-coverage";
import { readFileSync } from "node:fs";

const PLACEHOLDER_PATTERN = /\{\{([A-Z][A-Z0-9_]*)\}\}/g;
const PLACEHOLDER_TOKEN_PATTERN = /\{\{[^{}]+\}\}/g;

function placeholders(template: string): string[] {
  return [...template.matchAll(PLACEHOLDER_PATTERN)].map((match) => match[1]);
}

function placeholderTokens(template: string): string[] {
  return template.match(PLACEHOLDER_TOKEN_PATTERN) ?? [];
}

export function validatePlannerPromptTemplate(
  template: string,
  requiredPlaceholders: readonly string[],
): void {
  const found = placeholders(template);
  const allowedTokens = new Set(requiredPlaceholders.map((placeholder) => `{{${placeholder}}}`));
  const unknown = [...new Set(placeholderTokens(template).filter((token) => !allowedTokens.has(token)))];
  if (unknown.length > 0) {
    throw new Error(`Planner prompt has unknown placeholder(s): ${unknown.join(", ")}`);
  }
  const missing = requiredPlaceholders.filter((placeholder) => !found.includes(placeholder));
  if (missing.length > 0) {
    throw new Error(`Planner prompt has missing placeholder(s): ${missing.join(", ")}`);
  }
}

export function validateRenderedPlannerPrompt(
  rendered: string,
  literalBindings: readonly string[],
): void {
  const bindingTokens = new Set(literalBindings.flatMap((binding) => placeholderTokens(binding)));
  const unexpected = placeholderTokens(rendered).filter((token) => !bindingTokens.has(token));
  if (unexpected.length > 0) {
    throw new Error(`Planner prompt has unresolved placeholder(s): ${[...new Set(unexpected)].join(", ")}`);
  }
}

export function renderPlannerPromptTemplate<K extends string>(
  template: string,
  requiredPlaceholders: readonly K[],
  bindings: Record<K, string>,
): string {
  validatePlannerPromptTemplate(template, requiredPlaceholders);
  const rendered = template.replace(PLACEHOLDER_PATTERN, (_token, placeholder: K) => bindings[placeholder]);
  validateRenderedPlannerPrompt(rendered, requiredPlaceholders.map((placeholder) => bindings[placeholder]));
  return rendered;
}

function loadPrompt(name: string): string {
  const prompt = readFileSync(new URL(`../prompts/${name}.md`, import.meta.url), "utf8").trim();
  if (!prompt) throw new Error(`Planner prompt is empty: prompts/${name}.md`);
  return prompt;
}

const MEMORY_SELECTOR_PROMPT = loadPrompt("memory-selector");
const INCREMENTAL_MEMORY_PROMPT = loadPrompt("incremental-memory-consolidator");
const MEMORY_PROMPT = loadPrompt("memory-consolidator");
const HARNESS_PROMPT = loadPrompt("harness-consolidator");
const AGENTS_MD_PROMPT = loadPrompt("agents-md-consolidator");
const PLANNER_SYSTEM_PROMPT = loadPrompt("planner-system");

export const MEMORY_CITATION_GUIDANCE = `For each body and description claim, cite the relevant original user or tool-result source that establishes it. A future-task instruction does not prove a verified current state or successful execution. For current configuration or verification claims, include the actual configuration observation or successful tool result when present in the supplied frozen evidence; otherwise keep only the supported intended use and do not claim verification. Preserve later corrections, revocations and exceptions relevant to the same claim. Quotes must be verbatim with their original snapshot indexes. Do not attach all entries or unrelated observations to every candidate. Keep at most 8 evidence items per proposal and 2,000 characters per quote; select complete relevant quoted statements within those bounds, never invent or truncate away a condition. Preserve privacy classifications, candidate identity and independently grounded durable knowledge. Never quote secrets, infer success from missing evidence, add knowledge outside the requested scope or create Harness constraints. During semantic repair, an additional relevant original citation may resolve incomplete support without changing an already grounded fact; all parent structure, quote, privacy and full semantic checks still apply.`;

export function learningPlannerArgs(): string[] {
  return ["--append-system-prompt", PLANNER_SYSTEM_PROMPT];
}

export interface MemorySelectorPromptBindings {
  task: string;
  contextDigest: string;
}

export function buildMemorySelectorPrompt(bindings: MemorySelectorPromptBindings): string {
  return renderPlannerPromptTemplate(MEMORY_SELECTOR_PROMPT, ["CONTEXT_DIGEST", "TASK"] as const, {
    CONTEXT_DIGEST: bindings.contextDigest,
    TASK: bindings.task,
  });
}

export interface IncrementalMemoryConsolidatorPromptBindings {
  runId: string;
  scopeKey: string;
  scopeDigest: string;
  artifactHash: string;
  snapshotDigest: string;
  dossierPath: string;
}

export function buildIncrementalMemoryConsolidatorPrompt(
  bindings: IncrementalMemoryConsolidatorPromptBindings,
): string {
  return renderPlannerPromptTemplate(INCREMENTAL_MEMORY_PROMPT, [
    "RUN_ID",
    "SCOPE_KEY",
    "SCOPE_DIGEST",
    "ARTIFACT_HASH",
    "SNAPSHOT_DIGEST",
    "DOSSIER_PATH",
  ] as const, {
    RUN_ID: bindings.runId,
    SCOPE_KEY: bindings.scopeKey,
    SCOPE_DIGEST: bindings.scopeDigest,
    ARTIFACT_HASH: bindings.artifactHash,
    SNAPSHOT_DIGEST: bindings.snapshotDigest,
    DOSSIER_PATH: bindings.dossierPath,
  }) + "\n\n" + MEMORY_CITATION_GUIDANCE;
}

export interface MemoryConsolidatorPromptBindings {
  pkgDir: string;
  runId: string;
  scopeDigest: string;
  scopeKey: string;
  artifactHash: string;
  snapshotDigest: string;
  runDir: string;
  snapshotPath: string;
  harnessDir: string;
  publicDir: string;
  repoRoot: string;
}

export function buildMemoryConsolidatorPrompt(bindings: MemoryConsolidatorPromptBindings): string {
  return renderPlannerPromptTemplate(MEMORY_PROMPT, [
    "RUN_ID",
    "SCOPE_DIGEST",
    "SCOPE_KEY",
    "ARTIFACT_HASH",
    "SNAPSHOT_DIGEST",
    "RUN_DIR",
    "SNAPSHOT_PATH",
    "HARNESS_DIR",
    "PUBLIC_DIR",
    "REPO_ROOT",
    "PKG_DIR",
  ] as const, {
    RUN_ID: bindings.runId,
    SCOPE_DIGEST: bindings.scopeDigest,
    SCOPE_KEY: bindings.scopeKey,
    ARTIFACT_HASH: bindings.artifactHash,
    SNAPSHOT_DIGEST: bindings.snapshotDigest,
    RUN_DIR: bindings.runDir,
    SNAPSHOT_PATH: bindings.snapshotPath,
    HARNESS_DIR: bindings.harnessDir,
    PUBLIC_DIR: bindings.publicDir,
    REPO_ROOT: bindings.repoRoot,
    PKG_DIR: bindings.pkgDir,
  }) + "\n\n" + MEMORY_CITATION_GUIDANCE;
}

export interface HarnessConsolidatorPromptBindings {
  runId: string;
  scopeDigest: string;
  artifactHash: string;
  snapshotPath: string;
  dossierPath: string;
  repoRoot: string;
}

export function buildHarnessConsolidatorPrompt(bindings: HarnessConsolidatorPromptBindings): string {
  return renderPlannerPromptTemplate(HARNESS_PROMPT, [
    "RUN_ID",
    "SCOPE_DIGEST",
    "ARTIFACT_HASH",
    "SNAPSHOT_PATH",
    "DOSSIER_PATH",
    "REPO_ROOT",
  ] as const, {
    RUN_ID: bindings.runId,
    SCOPE_DIGEST: bindings.scopeDigest,
    ARTIFACT_HASH: bindings.artifactHash,
    SNAPSHOT_PATH: bindings.snapshotPath,
    DOSSIER_PATH: bindings.dossierPath,
    REPO_ROOT: bindings.repoRoot,
  }) + "\n\n" + projectPushCoverage(bindings.repoRoot);
}

export interface AgentsMdConsolidatorPromptBindings extends HarnessConsolidatorPromptBindings {
  budgetBytes: number;
}

export function buildAgentsMdConsolidatorPrompt(bindings: AgentsMdConsolidatorPromptBindings): string {
  return renderPlannerPromptTemplate(AGENTS_MD_PROMPT, [
    "RUN_ID",
    "SCOPE_DIGEST",
    "ARTIFACT_HASH",
    "SNAPSHOT_PATH",
    "DOSSIER_PATH",
    "REPO_ROOT",
    "BUDGET_BYTES",
  ] as const, {
    RUN_ID: bindings.runId,
    SCOPE_DIGEST: bindings.scopeDigest,
    ARTIFACT_HASH: bindings.artifactHash,
    SNAPSHOT_PATH: bindings.snapshotPath,
    DOSSIER_PATH: bindings.dossierPath,
    REPO_ROOT: bindings.repoRoot,
    BUDGET_BYTES: String(bindings.budgetBytes),
  });
}
