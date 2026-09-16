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
  let rendered = template;
  for (const placeholder of requiredPlaceholders) {
    rendered = rendered.replaceAll(`{{${placeholder}}}`, () => bindings[placeholder]);
  }
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

export interface MemorySelectorPromptBindings {
  task: string;
}

export function buildMemorySelectorPrompt(bindings: MemorySelectorPromptBindings): string {
  return renderPlannerPromptTemplate(MEMORY_SELECTOR_PROMPT, ["TASK"] as const, {
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
  });
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
  });
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
  });
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
