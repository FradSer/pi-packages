/**
 * AGENTS.md consolidation phase — the third stage of the /consolidate pipeline.
 *
 * Runs after a verified memory phase and the harness phase against the SAME
 * immutable session snapshot: a read-only planner child proposes bounded,
 * evidence-cited edits to the repository-root AGENTS.md — rewrite, remove,
 * add, or extract addressable units. The parent verifies every cited quote
 * verbatim against the snapshot text in code, simulates the resulting
 * document, enforces the byte budget (zero-sum growth at budget), and applies
 * every operation that passes those gates autonomously. User-level
 * instruction files are never touched, and any failure here never touches
 * applied memory or harness results.
 */

import fs from "node:fs/promises";
import { realpathSync } from "node:fs";
import path from "node:path";
import type { ChildProcess } from "node:child_process";
import { getAgentDir, type ExtensionContext } from "@earendil-works/pi-coding-agent";
import { notifyPi, resolvePiCli, spawnPiChild } from "@fradser/pi-kit";
import {
  createConsolidationRun,
  extractChildPlan,
  releaseConsolidationRun,
  sha256Digest,
  terminateConsolidationChild,
  writeFileAtomic,
  MAX_JSONL_LINE_BYTES,
  MAX_JSONL_LINES,
  MAX_PLAN_BYTES,
  MAX_SNAPSHOT_BYTES,
  MAX_STDOUT_BYTES,
  type ConsolidationRun,
} from "./consolidation-run";
import { isMemoryFilename } from "./memory-files";
import { applyHarnessOps, type HarnessOp } from "./harness-consolidation";
import { configPaths } from "./guardrail-config";

export const AGENTS_PLAN_KIND = "agents-md-consolidation-plan";
/** Learning rate: at most five small edits per consolidation run. */
export const MAX_AGENTS_MD_OPS = 5;
/** Refuse to plan against absurd instruction files. */
export const MAX_AGENTS_MD_FILE_BYTES = 262_144;
/** One addressed unit stays bounded and auditable. */
export const MAX_UNIT_TEXT_CHARS = 4_000;
export const MAX_EXTRACT_PROMPT_CHARS = 2_000;
/** Default always-loaded budget (~4k English tokens by the common bytes/4
 * heuristic). Anchored conservatively below two industry reference points:
 * backpass defaults to ~20KB for its memory file, and Claude Code loads only
 * the first 25KB of MEMORY.md. Configurable per project. */
export const DEFAULT_AGENTS_MD_BUDGET_BYTES = 16_384;
export const MIN_BUDGET_BYTES = 2_048;
const AGENTS_PHASE_TIMEOUT_MS = 15 * 60 * 1000;

export type AgentsOpKind = "rewriteUnit" | "removeUnit" | "addUnit" | "extractUnit";
export type EvidenceKind = "violation" | "wrong" | "unused" | "gap";
const OP_KINDS: readonly AgentsOpKind[] = ["rewriteUnit", "removeUnit", "addUnit", "extractUnit"];
const EVIDENCE_KINDS: readonly EvidenceKind[] = ["violation", "wrong", "unused", "gap"];
const MEMORY_TYPES = ["project", "feedback", "reference"] as const;

export interface AgentsEvidence {
  kind?: EvidenceKind;
  quote: string;
  occurrences?: number;
}

interface ExtractionMemory {
  target: "memory";
  memoryName: string;
  description: string;
  type: (typeof MEMORY_TYPES)[number];
}

interface ExtractionSkillPrompt {
  target: "skillPrompt";
  skillName: string;
  prompt: string;
  promptTarget: "system" | "user";
}

type Extraction = ExtractionMemory | ExtractionSkillPrompt;

export interface AgentsOp {
  op: AgentsOpKind;
  oldText?: string;
  newText?: string;
  text?: string;
  anchor?: string;
  position?: "before" | "after";
  reason?: string;
  rationale?: string;
  extraction?: Extraction;
  evidence: AgentsEvidence[];
}

export interface AgentsPlan {
  kind?: string;
  version?: number;
  schemaVersion?: number;
  runId?: string;
  scopeDigest?: string;
  artifactHash?: string;
  operations?: unknown;
  report?: unknown;
}

function boundedString(value: unknown, max: number): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= max;
}

function parseEvidence(raw: unknown, label: string, errors: string[]): AgentsEvidence[] {
  if (!Array.isArray(raw) || raw.length === 0) {
    errors.push(`${label}.evidence must be a non-empty array`);
    return [];
  }
  const parsed: AgentsEvidence[] = [];
  raw.forEach((entry, i) => {
    const itemLabel = `${label}.evidence[${i}]`;
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      errors.push(`${itemLabel} is not an object`);
      return;
    }
    const record = entry as Record<string, unknown>;
    if (!boundedString(record.quote, 2_000)) {
      errors.push(`${itemLabel}.quote must be 1..2000 chars`);
      return;
    }
    if (record.kind !== undefined && !EVIDENCE_KINDS.includes(record.kind as EvidenceKind)) {
      errors.push(`${itemLabel}.kind must be one of ${EVIDENCE_KINDS.join(", ")}`);
      return;
    }
    if (record.occurrences !== undefined && (typeof record.occurrences !== "number" || !Number.isInteger(record.occurrences) || record.occurrences < 1)) {
      errors.push(`${itemLabel}.occurrences must be a positive integer`);
      return;
    }
    parsed.push({ quote: record.quote, occurrences: record.occurrences ?? 1, kind: record.kind as EvidenceKind | undefined });
  });
  return parsed;
}

function parseExtraction(raw: unknown, label: string, errors: string[]): Extraction | undefined {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    errors.push(`${label}.extraction must be an object`);
    return undefined;
  }
  const record = raw as Record<string, unknown>;
  if (record.target === "skillPrompt") {
    if (typeof record.skillName !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(record.skillName)) {
      errors.push(`${label}.extraction.skillName is invalid`);
      return undefined;
    }
    if (!boundedString(record.prompt, MAX_EXTRACT_PROMPT_CHARS)) {
      errors.push(`${label}.extraction.prompt must be 1..${MAX_EXTRACT_PROMPT_CHARS} chars`);
      return undefined;
    }
    if (record.promptTarget !== "system" && record.promptTarget !== "user") {
      errors.push(`${label}.extraction.promptTarget must be "system" or "user"`);
      return undefined;
    }
    return { target: "skillPrompt", skillName: record.skillName, prompt: record.prompt, promptTarget: record.promptTarget };
  }
  if (record.target === "memory") {
    const name = record.memoryName;
    if (
      typeof name !== "string" || !isMemoryFilename(name) || name.toLowerCase() === "memory.md"
    ) {
      errors.push(`${label}.extraction.memoryName is not a canonical memory filename`);
      return undefined;
    }
    if (!boundedString(record.description, 300)) {
      errors.push(`${label}.extraction.description must be 1..300 chars`);
      return undefined;
    }
    if (!MEMORY_TYPES.includes(record.type as (typeof MEMORY_TYPES)[number])) {
      errors.push(`${label}.extraction.type must be one of ${MEMORY_TYPES.join(", ")}`);
      return undefined;
    }
    return { target: "memory", memoryName: name, description: record.description, type: record.type as ExtractionMemory["type"] };
  }
  errors.push(`${label}.extraction.target must be "memory" or "skillPrompt"`);
  return undefined;
}

function coerceOperation(raw: unknown, label: string, errors: string[]): AgentsOp | undefined {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    errors.push(`${label} is not an object`);
    return undefined;
  }
  const record = raw as Record<string, unknown>;
  if (!OP_KINDS.includes(record.op as AgentsOpKind)) {
    errors.push(`${label}.op must be one of ${OP_KINDS.join(", ")}`);
    return undefined;
  }
  const op = record.op as AgentsOpKind;
  const evidence = parseEvidence(record.evidence, label, errors);
  const base: AgentsOp = {
    op,
    evidence,
    ...(typeof record.reason === "string" ? { reason: record.reason.slice(0, 500) } : {}),
    ...(typeof record.rationale === "string" ? { rationale: record.rationale.slice(0, 500) } : {}),
  };
  if (op === "addUnit") {
    if (!boundedString(record.text, MAX_UNIT_TEXT_CHARS)) {
      errors.push(`${label}.text must be 1..${MAX_UNIT_TEXT_CHARS} chars`);
      return undefined;
    }
    base.text = record.text;
    if (record.anchor !== undefined || record.position !== undefined) {
      if (!boundedString(record.anchor, MAX_UNIT_TEXT_CHARS)) {
        errors.push(`${label}.anchor must be 1..${MAX_UNIT_TEXT_CHARS} chars`);
        return undefined;
      }
      if (record.position !== "before" && record.position !== "after") {
        errors.push(`${label}.position must be "before" or "after"`);
        return undefined;
      }
      base.anchor = record.anchor;
      base.position = record.position;
    }
  } else {
    if (!boundedString(record.oldText, MAX_UNIT_TEXT_CHARS)) {
      errors.push(`${label}.oldText must be 1..${MAX_UNIT_TEXT_CHARS} chars`);
      return undefined;
    }
    base.oldText = record.oldText;
    if (op === "rewriteUnit") {
      if (!boundedString(record.newText, MAX_UNIT_TEXT_CHARS)) {
        errors.push(`${label}.newText must be 1..${MAX_UNIT_TEXT_CHARS} chars`);
        return undefined;
      }
      base.newText = record.newText;
    }
    if (op === "extractUnit") {
      base.extraction = parseExtraction(record.extraction, label, errors);
      if (!base.extraction) return undefined;
    }
  }
  return base;
}

/** Validate plan shape and bounds. Identity binding is enforced separately. */
export function validateAgentsMdPlan(plan: unknown): { ok: true; operations: AgentsOp[] } | { ok: false; errors: string[] } {
  const p = plan as AgentsPlan;
  if (!p || typeof p !== "object" || Array.isArray(p)) return { ok: false, errors: ["plan is not an object"] };
  if (p.kind !== AGENTS_PLAN_KIND) return { ok: false, errors: [`kind must be "${AGENTS_PLAN_KIND}"`] };
  if (p.operations === undefined) return { ok: true, operations: [] };
  if (!Array.isArray(p.operations)) return { ok: false, errors: ["operations must be an array"] };
  if (p.operations.length > MAX_AGENTS_MD_OPS) {
    return { ok: false, errors: [`operations exceed the maximum of ${MAX_AGENTS_MD_OPS}`] };
  }
  const errors: string[] = [];
  const operations: AgentsOp[] = [];
  p.operations.forEach((raw, i) => {
    const op = coerceOperation(raw, `operations[${i}]`, errors);
    if (op) operations.push(op);
  });
  if (errors.length) return { ok: false, errors };
  return { ok: true, operations };
}

function normalizeForMatch(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/** A quote is admissible only when it appears verbatim in the snapshot text.
 * Whitespace runs are collapsed on both sides, and the JSON-escaped form is
 * tried too, because tool output lives inside JSON string literals. */
export function quoteInSnapshot(quote: string, snapshotText: string): boolean {
  if (!quote.trim()) return false;
  const haystack = normalizeForMatch(snapshotText);
  if (haystack.includes(normalizeForMatch(quote))) return true;
  let escaped = "";
  try {
    escaped = JSON.stringify(quote).slice(1, -1);
  } catch {
    return false;
  }
  return haystack.includes(normalizeForMatch(escaped));
}

export interface QuoteVerification {
  /** Operations whose evidence survived verification, quotes filtered. */
  operations: AgentsOp[];
  /** Original indexes of dropped operations. */
  dropped: number[];
  /** Verified quotes per surviving operation (aligned with `operations`). */
  verifiedQuotes: string[][];
}

/** Discard unverifiable quotes in code; drop operations left without any. */
export function verifyPlanQuotes(operations: readonly AgentsOp[], snapshotText: string): QuoteVerification {
  const result: QuoteVerification = { operations: [], dropped: [], verifiedQuotes: [] };
  operations.forEach((op, index) => {
    const verified = op.evidence.filter((entry) => quoteInSnapshot(entry.quote, snapshotText)).map((entry) => entry.quote);
    if (verified.length === 0) {
      result.dropped.push(index);
      return;
    }
    result.operations.push({ ...op, evidence: op.evidence.filter((entry) => verified.includes(entry.quote)) });
    result.verifiedQuotes.push(verified);
  });
  return result;
}

/** Batched-evidence gate for brand-new units: at least two DISTINCT verified
 * quotes, or one quote observed at least twice. Planner-supplied occurrence
 * counts never stack across duplicate quotes. */
export function addUnitEvidenceSufficient(op: AgentsOp): boolean {
  if (op.op !== "addUnit") return true;
  const byQuote = new Map<string, number>();
  for (const entry of op.evidence) {
    const key = entry.quote.replace(/\s+/g, " ").trim();
    const previous = byQuote.get(key) ?? 0;
    byQuote.set(key, Math.max(previous, entry.occurrences ?? 1));
  }
  if (byQuote.size >= 2) return true;
  return [...byQuote.values()].some((occurrences) => occurrences >= 2);
}

export function fingerprintOp(op: AgentsOp): string {
  const material = JSON.stringify({
    op: op.op,
    oldText: op.oldText ?? null,
    newText: op.newText ?? null,
    text: op.text ?? null,
    anchor: op.anchor ?? null,
    position: op.position ?? null,
    extraction: op.extraction ?? null,
  });
  return sha256Digest(material);
}

/** Simulate applying operations to the document exactly like the edit tool
 * contract: every `oldText` / `anchor` must match exactly once. The whole
 * simulation fails closed on any ambiguity so no partial state is possible. */
export function simulateAgentsOps(
  doc: string,
  ops: readonly AgentsOp[],
): { ok: true; doc: string; applied: string[] } | { ok: false; error: string } {
  let next = doc;
  const applied: string[] = [];
  for (const [index, op] of ops.entries()) {
    const label = `operations[${index}]`;
    if (op.op === "addUnit") {
      const text = op.text!;
      if (op.anchor === undefined) {
        const separator = next.endsWith("\n") ? (next.endsWith("\n\n") ? "" : "\n") : "\n\n";
        next = `${next}${separator}${text}${text.endsWith("\n") ? "" : "\n"}`;
        applied.push(`addUnit[${index}] (append)`);
        continue;
      }
      const anchor = op.anchor;
      const first = next.indexOf(anchor);
      if (first < 0) return { ok: false, error: `${label}.anchor does not match the document` };
      if (next.indexOf(anchor, first + 1) >= 0) return { ok: false, error: `${label}.anchor matches more than once` };
      const inserted = `${text.replace(/\n$/, "")}\n`;
      // Insertion lands on whole-line boundaries relative to the anchor's line.
      if (op.position === "before") {
        const lineStart = next.lastIndexOf("\n", first) + 1;
        next = `${next.slice(0, lineStart)}${inserted}${next.slice(lineStart)}`;
      } else {
        const lineEnd = next.indexOf("\n", first + anchor.length);
        const insertAt = lineEnd === -1 ? next.length : lineEnd + 1;
        next = `${next.slice(0, insertAt)}${inserted}${next.slice(insertAt)}`;
      }
      applied.push(`addUnit[${index}] (${op.position} anchor)`);
      continue;
    }
    const oldText = op.oldText!;
    const first = next.indexOf(oldText);
    if (first < 0) return { ok: false, error: `${label}.oldText does not match the document` };
    if (next.indexOf(oldText, first + 1) >= 0) return { ok: false, error: `${label}.oldText matches more than once` };
    if (op.op === "rewriteUnit") next = next.slice(0, first) + op.newText! + next.slice(first + oldText.length);
    else next = next.slice(0, first) + next.slice(first + oldText.length);
    applied.push(`${op.op}[${index}]`);
  }
  return { ok: true, doc: next, applied };
}

/** Budget gate: growth is allowed only below budget; at or above it updates
 * are zero-sum — the post-edit document may not exceed the current one. */
export function budgetAllows(preBytes: number, postBytes: number, budgetBytes: number): boolean {
  return postBytes <= Math.max(preBytes, budgetBytes);
}

/** The consolidation target is exactly <cwd>/AGENTS.md. When that path would
 * resolve — lexically or through symlinks — to the user-level agent
 * instructions, it must never be touched. */
export function isUserLevelInstructionsFile(target: string, agentDir: string): boolean {
  const resolvedTarget = path.resolve(target);
  const agentInstructions = path.resolve(agentDir, "AGENTS.md");
  if (resolvedTarget === agentInstructions) return true;
  // Lexical equality misses symlinked project directories; compare real paths,
  // falling back to the real parent when the target does not exist yet.
  const realOf = (candidate: string): string | undefined => {
    try {
      return realpathSync(candidate);
    } catch {
      try {
        return path.join(realpathSync(path.dirname(candidate)), path.basename(candidate));
      } catch {
        return undefined;
      }
    }
  };
  const realTarget = realOf(resolvedTarget);
  const realAgent = realOf(agentInstructions);
  if (!realTarget || !realAgent) return false;
  return realTarget === realAgent;
}

export interface AgentsTargetResolution {
  path?: string;
  skipReason?: string;
}

export function resolveAgentsTargetFile(cwd: string, agentDir: string): AgentsTargetResolution {
  const target = path.resolve(cwd, "AGENTS.md");
  if (isUserLevelInstructionsFile(target, agentDir)) {
    return { skipReason: "project AGENTS.md resolves to user-level instructions; refusing to touch them" };
  }
  return { path: target };
}

interface PhaseOpts {
  pkgDir: string;
  cwd: string;
  reason: string;
  budgetBytes: number;
  disabled: boolean;
}

async function readRegularFileIfExists(filePath: string, maxBytes: number): Promise<Buffer | null> {
  try {
    const st = await fs.lstat(filePath);
    if (!st.isFile()) return null;
    if (st.size > maxBytes) throw new Error(`AGENTS.md exceeds ${maxBytes} bytes; refusing to plan against it`);
    return await fs.readFile(filePath);
  } catch (error: unknown) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

async function readSnapshotText(run: ConsolidationRun): Promise<string> {
  try {
    return (await fs.readFile(run.paths.snapshotFile, { encoding: "utf8", flag: "r" })).slice(0, MAX_SNAPSHOT_BYTES);
  } catch {
    return "";
  }
}

/** Third pipeline phase. Requires an already-completed memory phase (the
 * caller gates on that). Every failure path is self-contained: it notifies
 * and returns without throwing or touching memory or harness results. */
export async function runAgentsMdConsolidationPhase(
  ctx: ExtensionContext,
  state: { active: boolean; generation: number; cancelled: boolean; child?: ChildProcess },
  opts: PhaseOpts,
): Promise<void> {
  if (state.active) return;
  if (opts.disabled) return;
  state.active = true;
  const generation = state.generation + 1;
  state.generation = generation;
  state.cancelled = false;
  const current = (): boolean => !state.cancelled && generation === state.generation;

  let run: ConsolidationRun;
  try {
    run = await createConsolidationRun(ctx, opts.cwd, false);
    if (!current()) {
      await releaseConsolidationRun(run);
      state.active = false;
      return;
    }
  } catch (err) {
    state.active = false;
    if (current()) notifyPi(ctx.ui, `AGENTS.md consolidation skipped: ${(err as Error).message}`, "warning");
    return;
  }

  let child: ChildProcess | undefined;
  try {
    const finalTarget = resolveAgentsTargetFile(opts.cwd, getAgentDir());
    if (!finalTarget.path) {
      notifyPi(ctx.ui, `AGENTS.md consolidation skipped: ${finalTarget.skipReason}`, "info");
      return;
    }
    const targetPath = finalTarget.path;
    const docBytes = await readRegularFileIfExists(targetPath, MAX_AGENTS_MD_FILE_BYTES);
    if (!docBytes) {
      notifyPi(ctx.ui, "AGENTS.md consolidation: no project AGENTS.md found; nothing to consolidate.", "info");
      return;
    }
    const preBytes = docBytes.byteLength;
    const doc = docBytes.toString("utf8");
    const snapshotText = await readSnapshotText(run);
    const cli = resolvePiCli();
    if (!cli) throw new Error("could not resolve the Pi CLI");
    let procedure = (
      await fs.readFile(path.join(opts.pkgDir, "procedures", "consolidate-agents.md"), "utf-8")
    )
      .replaceAll("{{PKG_DIR}}", opts.pkgDir)
      .replaceAll("{{RUN_ID}}", run.manifest.runId)
      .replaceAll("{{SCOPE_DIGEST}}", run.manifest.scopeDigest)
      .replaceAll("{{ARTIFACT_HASH}}", run.manifest.snapshotDigest)
      .replaceAll("{{SNAPSHOT_PATH}}", run.manifest.snapshotPath)
      .replaceAll("{{REPO_ROOT}}", run.manifest.cwd)
      .replaceAll("{{BUDGET_BYTES}}", String(opts.budgetBytes));
    if (!current()) return;
    const taskText = [
      `Task: produce a read-only structured AGENTS.md consolidation plan for the project at ${opts.cwd}.`,
      `- Reason: ${opts.reason}`,
      `- Run ID: ${run.manifest.runId}`,
      `- Scope digest: ${run.manifest.scopeDigest}`,
      `- Artifact/snapshot digest: ${run.manifest.snapshotDigest}`,
      `- Immutable context snapshot: ${run.manifest.snapshotPath}`,
      `- Budget bytes: ${opts.budgetBytes}`,
      `- Current AGENTS.md (${preBytes} bytes), authoritative for anchoring operations:`,
      "<<<AGENTS.MD>>>",
      doc,
      "<<<END AGENTS.MD>>>",
      "- Target file for every change: the embedded document's path on disk.",
      "- Your final assistant message must be exactly one JSON object.",
      "",
      procedure,
    ].join("\n");

    const taskFile = path.join(run.manifest.runDir, "task.md");
    await fs.writeFile(taskFile, taskText, { mode: 0o600 });
    child = spawnPiChild(
      cli.command,
      [
        ...cli.args,
        "--print", "--mode", "json", "--no-session", "--no-extensions",
        "--tools", "read,grep,find,ls",
        `@${taskFile}`,
      ],
      { cwd: opts.cwd, stdio: ["ignore", "pipe", "pipe"] },
    );
    if (!current()) {
      void terminateConsolidationChild(child, 5_000).catch(() => {});
      return;
    }
    state.child = child;

    const result = await new Promise<{ ok: boolean; detail: string }>((resolve) => {
      let stdout = "";
      let stderr = "";
      let done = false;
      const finish = (r: { ok: boolean; detail: string }) => { if (!done) { done = true; clearTimeout(timer); resolve(r); } };
      const timer = setTimeout(() => {
        void terminateConsolidationChild(child!, 5_000).catch(() => {});
        finish({ ok: false, detail: "AGENTS.md planner timed out" });
      }, AGENTS_PHASE_TIMEOUT_MS);
      timer.unref?.();
      child!.stdout?.on("data", (chunk: Buffer) => {
        stdout += chunk.toString("utf-8");
        if (Buffer.byteLength(stdout, "utf8") > MAX_STDOUT_BYTES) {
          void terminateConsolidationChild(child!, 5_000).catch(() => {});
          finish({ ok: false, detail: `child stdout exceeded ${MAX_STDOUT_BYTES} bytes` });
        }
      });
      child!.stderr?.on("data", (chunk: Buffer) => {
        stderr = (stderr + chunk.toString("utf-8")).slice(-64_000);
      });
      child!.on("error", (err) => finish({ ok: false, detail: err.message }));
      child!.on("close", (code) => {
        if (code !== 0) return finish({ ok: false, detail: stderr.trim() || `exit code ${code}` });
        const extracted = extractChildPlan(stdout, {
          expectedIdentity: {
            runId: run.manifest.runId,
            scopeDigest: run.manifest.scopeDigest,
            artifactHash: run.manifest.snapshotDigest,
          },
          maxOutputBytes: MAX_STDOUT_BYTES,
          maxLines: MAX_JSONL_LINES,
          maxLineBytes: MAX_JSONL_LINE_BYTES,
          maxPlanBytes: MAX_PLAN_BYTES,
        });
        if (!extracted.ok) return finish({ ok: false, detail: extracted.error });
        finish({ ok: true, detail: JSON.stringify({ plan: extracted.plan, stderr: stderr.trim() }) });
      });
    });
    if (!current()) return;

    if (!result.ok) {
      await writeFileAtomic(path.join(run.manifest.runDir, "agents-error.txt"), result.detail.slice(-8_000)).catch(() => {});
      notifyPi(ctx.ui, `AGENTS.md consolidation finished without changes: ${result.detail.slice(-300)}`, "warning");
      return;
    }
    const rawPlan = (JSON.parse(result.detail) as { plan: unknown }).plan;
    const shape = validateAgentsMdPlan(rawPlan);
    if (!shape.ok) {
      notifyPi(ctx.ui, `AGENTS.md plan rejected: ${shape.errors.join("; ").slice(-300)}`, "warning");
      return;
    }
    const quoteCheck = verifyPlanQuotes(shape.operations, snapshotText);
    const candidateOps = quoteCheck.operations.filter((op) => addUnitEvidenceSufficient(op));
    const droppedCount = quoteCheck.dropped.length + quoteCheck.operations.length - candidateOps.length;
    if (candidateOps.length === 0) {
      await writeFileAtomic(path.join(run.manifest.runDir, "agents-noop.txt"), "verified no-op\n").catch(() => {});
      notifyPi(ctx.ui, `AGENTS.md consolidation: verified no-op${droppedCount > 0 ? ` (${droppedCount} operation(s) failed evidence gates)` : ""}.`, "info");
      return;
    }
    const ops = candidateOps;
    const simulated = simulateAgentsOps(doc, ops);
    if (!simulated.ok) {
      notifyPi(ctx.ui, `AGENTS.md plan rejected during simulation: ${simulated.error.slice(-300)}`, "warning");
      return;
    }
    if (!budgetAllows(preBytes, Buffer.byteLength(simulated.doc, "utf8"), opts.budgetBytes)) {
      notifyPi(ctx.ui, `AGENTS.md plan rejected: post-edit size exceeds the ${opts.budgetBytes}-byte budget and is not zero-sum.`, "warning");
      return;
    }

    // Structural, evidence, simulation, and budget checks are the complete
    // safety gate. Validated operations apply without an interactive prompt.
    const planDigest = sha256Digest(JSON.stringify(rawPlan));
    const digestBefore = docBytes.toString("base64");

    const resimulated = simulateAgentsOps(doc, ops);
    if (!resimulated.ok || !budgetAllows(preBytes, Buffer.byteLength(resimulated.doc, "utf8"), opts.budgetBytes)) {
      notifyPi(ctx.ui, "AGENTS.md plan failed re-validation; nothing was written.", "warning");
      return;
    }

    // Extraction side-effects go first: a failed document write then leaves
    // the unit in place WITH its artifact (duplicate guidance, self-healing
    // on the next run) instead of a removed unit without one.
    const harnessOps: HarnessOp[] = [];
    const extractionNotes: string[] = [];
    for (const op of ops) {
      if (op.op !== "extractUnit" || !op.extraction) continue;
      if (op.extraction.target === "skillPrompt") {
        harnessOps.push({ op: "addSkillPrompt", name: op.extraction.skillName, prompt: op.extraction.prompt, target: op.extraction.promptTarget });
      } else {
        const memoryPath = path.join(run.manifest.harnessDir, op.extraction.memoryName);
        try {
          const frontmatter = [
            "---",
            `name: ${op.extraction.memoryName.replace(/\.md$/i, "")}`,
            `description: ${op.extraction.description}`,
            `type: ${op.extraction.type}`,
            "---",
            "",
          ].join("\n");
          await writeFileAtomic(memoryPath, `${frontmatter}${(op.oldText ?? "").trim()}\n`, 0o600);
          extractionNotes.push(`memory:${op.extraction.memoryName}`);
        } catch {
          extractionNotes.push(`memory:${op.extraction.memoryName} FAILED`);
        }
      }
    }
    if (harnessOps.length > 0) {
      const appliedHarness = await applyHarnessOps(configPaths(opts.cwd).projectLocal, harnessOps);
      if (appliedHarness.ok) extractionNotes.push(...appliedHarness.applied);
      else extractionNotes.push(`skillPrompts FAILED: ${appliedHarness.error.slice(0, 120)}`);
    }

    const stat = await fs.lstat(targetPath);
    const mode = stat.isFile() && !stat.isSymbolicLink() ? stat.mode & 0o777 : 0o644;
    await writeFileAtomic(targetPath, Buffer.from(resimulated.doc, "utf8"), mode);
    if (!current()) {
      // Session shut down mid-apply: restore the pre-apply bytes.
      await writeFileAtomic(targetPath, docBytes, mode).catch(() => {});
      return;
    }

    const afterBytes = Buffer.from(resimulated.doc, "utf8");
    const receipt = {
      kind: "agents-md-consolidation-receipt",
      phase: "post",
      runId: run.manifest.runId,
      scopeDigest: run.manifest.scopeDigest,
      snapshotDigest: run.manifest.snapshotDigest,
      targetFile: targetPath,
      budgetBytes: opts.budgetBytes,
      bytesBefore: preBytes,
      bytesAfter: afterBytes.byteLength,
      digestEncoding: "base64 of raw file bytes",
      digestBefore,
      digestAfter: afterBytes.toString("base64"),
      sha256Before: sha256Digest(docBytes),
      sha256After: sha256Digest(afterBytes),
      applied: ops.map((op) => ({ op: op.op, fingerprint: fingerprintOp(op) })),
      rejected: [],
      extractions: extractionNotes,
      planDigest,
    };
    await writeFileAtomic(path.join(run.manifest.runDir, "agents-post-receipt.json"), `${JSON.stringify(receipt, null, 2)}\n`).catch(() => {});
    const parts = [`${ops.length} edit(s) applied`];
    if (extractionNotes.length > 0) parts.push(`extractions: ${extractionNotes.join(", ")}`);
    notifyPi(ctx.ui, `AGENTS.md consolidated: ${parts.join(" · ")} (${path.basename(targetPath)}).`, "info");
  } catch (err) {
    if (current()) notifyPi(ctx.ui, `AGENTS.md consolidation failed: ${(err as Error).message.slice(-300)}`, "warning");
  } finally {
    const owned = current();
    try {
      if (owned && state.child) {
        const c = state.child;
        state.child = undefined;
        if (!c.killed) void terminateConsolidationChild(c, 5_000).catch(() => {});
      }
    } finally {
      await releaseConsolidationRun(run, { keepArtifacts: owned }).catch(() => {});
      if (owned) state.active = false;
    }
  }
}
