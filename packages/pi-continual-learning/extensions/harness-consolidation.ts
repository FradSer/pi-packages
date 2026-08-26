/**
 * Harness consolidation phase — the second half of the /consolidate pipeline.
 *
 * Runs after a verified memory consolidation against the SAME immutable
 * session snapshot: a read-only planner child mines tool-call guardrail
 * evidence (blocked calls and reasons, confirmation outcomes, user
 * corrections) and returns one bounded `harness-consolidation-plan`. The
 * parent alone applies it, merging atomically into the personal project-local
 * layer (<cwd>/.pi/harness.local.json). Shared layers are never written, and
 * any failure here never touches already-applied memory results.
 */

import fs from "node:fs/promises";
import path from "node:path";
import type { ChildProcess } from "node:child_process";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { resolvePiCli, spawnPiChild } from "@fradser/pi-kit";
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
  MAX_STDOUT_BYTES,
  type ConsolidationRun,
} from "./consolidation-run";
import { DEFAULT_POLICIES, mergeLayers } from "./guardrail-engine";
import { configPaths, loadLayers } from "./guardrail-config";

export const HARNESS_PLAN_KIND = "harness-consolidation-plan";
export const MAX_HARNESS_OPS = 12;
export const MAX_POLICY_BYTES = 8_192;
export const MAX_SKILL_PROMPT_CHARS = 2_000;
const HARNESS_PHASE_TIMEOUT_MS = 15 * 60 * 1000;
const HARNESS_OP_KINDS = ["addPolicy", "updatePolicy", "disablePolicy", "addSkillPrompt", "removeSkillPrompt"] as const;
export type HarnessOpKind = (typeof HARNESS_OP_KINDS)[number];

export interface HarnessOp {
  op: HarnessOpKind;
  name?: string;
  policy?: Record<string, unknown>;
  prompt?: string;
  target?: string;
}

export interface HarnessConsolidationPlan {
  kind: typeof HARNESS_PLAN_KIND;
  version?: number;
  schemaVersion?: number;
  runId?: string;
  scopeDigest?: string;
  artifactHash?: string;
  operations?: unknown;
  evidence?: unknown;
  report?: unknown;
}

/** Structural subset of the shared dream state both phases coordinate on. */
export interface ConsolidationPhaseState {
  active: boolean;
  generation: number;
  cancelled: boolean;
}

function policyNameValid(name: unknown): name is string {
  return typeof name === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(name);
}

function boundedString(value: unknown, max: number): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= max;
}

/** Validate shape and bounds of an extracted harness plan. Identity binding is
 * already enforced by extractChildPlan before this runs. */
export function validateHarnessPlan(plan: unknown): string[] {
  const p = plan as HarnessConsolidationPlan;
  const errors: string[] = [];
  if (!p || typeof p !== "object" || Array.isArray(p)) return ["plan is not an object"];
  if (p.kind !== HARNESS_PLAN_KIND) errors.push(`kind must be "${HARNESS_PLAN_KIND}"`);
  if (p.operations === undefined) {
    // A verified no-op may omit operations entirely.
    return errors;
  }
  if (!Array.isArray(p.operations)) {
    errors.push("operations must be an array");
    return errors;
  }
  if (p.operations.length > MAX_HARNESS_OPS) {
    errors.push(`operations exceed the maximum of ${MAX_HARNESS_OPS}`);
    return errors;
  }
  p.operations.forEach((raw, i) => {
    const op = raw as HarnessOp;
    const label = `operations[${i}]`;
    if (!op || typeof op !== "object") {
      errors.push(`${label} is not an object`);
      return;
    }
    if (!HARNESS_OP_KINDS.includes(op.op)) {
      errors.push(`${label}.op must be one of ${HARNESS_OP_KINDS.join(", ")}`);
      return;
    }
    if (op.op === "addSkillPrompt" || op.op === "removeSkillPrompt") {
      if (!policyNameValid(op.name)) errors.push(`${label}.name is invalid`);
      if (op.op === "addSkillPrompt") {
        if (!boundedString(op.prompt, MAX_SKILL_PROMPT_CHARS)) errors.push(`${label}.prompt must be 1..${MAX_SKILL_PROMPT_CHARS} chars`);
        if (op.target !== "system" && op.target !== "user") errors.push(`${label}.target must be "system" or "user"`);
      }
      return;
    }
    if (!boundedString(op.name, 64) || !policyNameValid(op.name)) {
      errors.push(`${label}.name is invalid`);
      return;
    }
    if (op.op === "disablePolicy") return;
    const policyBytes = Buffer.byteLength(JSON.stringify(op.policy ?? null), "utf8");
    if (!op.policy || typeof op.policy !== "object" || Array.isArray(op.policy)) {
      errors.push(`${label}.policy must be an object`);
      return;
    }
    if (policyBytes > MAX_POLICY_BYTES) {
      errors.push(`${label}.policy exceeds ${MAX_POLICY_BYTES} bytes`);
      return;
    }
    if (op.policy.action !== "block" && op.policy.action !== "confirm") errors.push(`${label}.policy.action must be "block" or "confirm"`);
    if (!Array.isArray(op.policy.patterns) || !op.policy.patterns.every((x) => typeof x === "string")) {
      errors.push(`${label}.policy.patterns must be an array of strings`);
    }
  });
  return errors;
}

async function readLayerFileBytes(filePath: string): Promise<Buffer | null> {
  try {
    const st = await fs.stat(filePath);
    if (!st.isFile()) return null;
    return await fs.readFile(filePath);
  } catch {
    return null;
  }
}

/** Apply harness ops by merging the project-local layer in ONE atomic write.
 * Semantic conflicts (e.g. addPolicy for an existing name) reject the whole
 * plan before anything is written, so no partial application is possible. */
export async function applyHarnessOps(
  projectLocalPath: string,
  ops: readonly HarnessOp[],
): Promise<{ ok: true; applied: string[] } | { ok: false; error: string }> {
  const applied: string[] = [];
  let base: Record<string, unknown> = {};
  const prior = await readLayerFileBytes(projectLocalPath);
  if (prior) {
    try {
      const parsed = JSON.parse(prior.toString("utf8")) as Record<string, unknown>;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) base = parsed;
    } catch {
      return { ok: false, error: `existing ${projectLocalPath} is not valid JSON` };
    }
  }
  const policies = Array.isArray(base.policies) ? [...(base.policies as Array<Record<string, unknown>>)] : [];
  const disabled = Array.isArray(base.disabled) ? [...(base.disabled as string[])] : [];
  const skillPrompts = base.skillPrompts && typeof base.skillPrompts === "object" && !Array.isArray(base.skillPrompts)
    ? { ...(base.skillPrompts as Record<string, unknown>) }
    : {};
  for (const [i, op] of ops.entries()) {
    const label = `operations[${i}]`;
    if (op.op === "addPolicy") {
      const policy = { ...(op.policy as Record<string, unknown>), name: op.name };
      const name = policy.name as string;
      if (policies.some((x) => x.name === name)) return { ok: false, error: `${label}: policy "${name}" already exists in the project-local layer` };
      policies.push(policy);
      applied.push(`addPolicy:${name}`);
    } else if (op.op === "updatePolicy") {
      const idx = policies.findIndex((x) => x.name === op.name);
      const policy = { ...(op.policy as Record<string, unknown>), name: op.name };
      if (idx >= 0) policies[idx] = policy;
      else policies.push(policy);
      applied.push(`updatePolicy:${op.name}${idx >= 0 ? "" : " (added)"}`);
    } else if (op.op === "disablePolicy") {
      if (!disabled.includes(op.name as string)) disabled.push(op.name as string);
      applied.push(`disablePolicy:${op.name}`);
    } else if (op.op === "addSkillPrompt") {
      skillPrompts[op.name as string] = { prompt: op.prompt, target: op.target };
      applied.push(`addSkillPrompt:${op.name}`);
    } else if (op.op === "removeSkillPrompt") {
      delete skillPrompts[op.name as string];
      applied.push(`removeSkillPrompt:${op.name}`);
    }
  }
  const next = { ...base, policies, disabled, skillPrompts };
  await writeFileAtomic(projectLocalPath, `${JSON.stringify(next, null, 2)}\n`, 0o600);
  return { ok: true, applied };
}

function builtInDefaultsLayer(): { source: string; policies: Array<Record<string, unknown>> } {
  return { source: "built-in defaults", policies: DEFAULT_POLICIES as unknown as Array<Record<string, unknown>> };
}

/** Current resolved harness surface handed to the planner as context. */
export async function harnessSurfaceSummary(cwd: string, agentDir?: string): Promise<string> {
  const paths = configPaths(cwd, agentDir);
  const config = mergeLayers([builtInDefaultsLayer(), ...loadLayers(cwd, agentDir)]);
  const summary = {
    layers: Object.entries(paths).map(([k, v]) => ({ layer: k, file: v })),
    activePolicies: config.policies.map((p) => ({ name: p.name, action: (p as { action?: string }).action })),
    skillPrompts: Object.keys(config.skillPrompts),
    errors: config.errors,
    note: "the planner targets ONLY the project.local layer file",
  };
  return JSON.stringify(summary, null, 1);
}

interface PhaseOpts { pkgDir: string; cwd: string; reason: string }

/**
 * Second pipeline phase. Requires an already-completed, verified memory phase
 * (the caller gates on that) and captured context. Every failure path is
 * self-contained: it notifies and returns without throwing or touching memory.
 */
export async function runHarnessConsolidationPhase(
  ctx: ExtensionContext,
  state: ConsolidationPhaseState & { child?: ChildProcess },
  opts: PhaseOpts,
): Promise<void> {
  if (state.active) return;
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
    if (current()) ctx.ui.notify(`Harness consolidation skipped: ${(err as Error).message}`, "warning");
    return;
  }

  try {
    const cli = resolvePiCli();
    if (!cli) throw new Error("could not resolve the Pi CLI");
    let procedure = (
      await fs.readFile(path.join(opts.pkgDir, "procedures", "consolidate-harness.md"), "utf-8")
    )
      .replaceAll("{{PKG_DIR}}", opts.pkgDir)
      .replaceAll("{{RUN_ID}}", run.manifest.runId)
      .replaceAll("{{SCOPE_DIGEST}}", run.manifest.scopeDigest)
      .replaceAll("{{ARTIFACT_HASH}}", run.manifest.snapshotDigest)
      .replaceAll("{{SNAPSHOT_PATH}}", run.manifest.snapshotPath)
      .replaceAll("{{REPO_ROOT}}", run.manifest.cwd);
    const surface = await harnessSurfaceSummary(opts.cwd);
    if (!current()) return;
    const taskText = [
      `Task: produce a read-only structured harness consolidation plan for the project at ${opts.cwd}.`,
      `- Reason: ${opts.reason}`,
      `- Run ID: ${run.manifest.runId}`,
      `- Scope digest: ${run.manifest.scopeDigest}`,
      `- Artifact/snapshot digest: ${run.manifest.snapshotDigest}`,
      `- Immutable context snapshot: ${run.manifest.snapshotPath}`,
      `- Current harness surface summary:`,
      surface,
      "- Target layer for every change: <project>/.pi/harness.local.json only.",
      "- Your final assistant message must be exactly one JSON object with kind \"harness-consolidation-plan\".",
      "",
      procedure,
    ].join("\n");

    const taskFile = path.join(run.manifest.runDir, "task.md");
    await fs.writeFile(taskFile, taskText, { mode: 0o600 });
    const child: ChildProcess = spawnPiChild(
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
      let lines = 0;
      let done = false;
      const finish = (r: { ok: boolean; detail: string }) => { if (!done) { done = true; clearTimeout(timer); resolve(r); } };
      const timer = setTimeout(() => {
        void terminateConsolidationChild(child, 5_000).catch(() => {});
        finish({ ok: false, detail: "harness planner timed out" });
      }, HARNESS_PHASE_TIMEOUT_MS);
      timer.unref?.();
      child.stdout?.on("data", (chunk: Buffer) => {
        stdout += chunk.toString("utf-8");
        if (Buffer.byteLength(stdout, "utf8") > MAX_STDOUT_BYTES) {
          void terminateConsolidationChild(child, 5_000).catch(() => {});
          finish({ ok: false, detail: `child stdout exceeded ${MAX_STDOUT_BYTES} bytes` });
        }
      });
      child.stderr?.on("data", (chunk: Buffer) => {
        stderr = (stderr + chunk.toString("utf-8")).slice(-64_000);
      });
      child.on("error", (err) => finish({ ok: false, detail: err.message }));
      child.on("close", (code) => {
        const planLines = stdout.split("\n").filter((l) => l.trim());
        lines = planLines.length;
        if (lines > MAX_JSONL_LINES) return finish({ ok: false, detail: `child JSONL exceeded ${MAX_JSONL_LINES} records` });
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
        const shapeErrors = validateHarnessPlan(extracted.plan);
        if (shapeErrors.length) return finish({ ok: false, detail: shapeErrors.join("; ").slice(-600) });
        finish({ ok: true, detail: JSON.stringify({ plan: extracted.plan, stderr: stderr.trim() }) });
      });
    });
    if (!current()) return;

    if (!result.ok) {
      await writeFileAtomic(path.join(run.manifest.runDir, "harness-error.txt"), result.detail.slice(-8_000)).catch(() => {});
      ctx.ui.notify(`Harness consolidation finished without applying changes: ${result.detail.slice(-300)}`, "warning");
      return;
    }
    const plan = (JSON.parse(result.detail) as { plan: unknown }).plan as { operations?: HarnessOp[] };
    const ops = Array.isArray(plan.operations) ? plan.operations : [];
    if (ops.length === 0) {
      await writeFileAtomic(path.join(run.manifest.runDir, "harness-noop.txt"), "verified no-op\n").catch(() => {});
      ctx.ui.notify("Harness consolidation: verified no-op — no guardrail evidence worth encoding.", "info");
      return;
    }
    const paths = configPaths(opts.cwd);
    const target = paths.projectLocal;
    const digestBefore = (await readLayerFileBytes(target))?.toString("base64") ?? null;
    const applied = await applyHarnessOps(target, ops);
    if (!applied.ok) {
      ctx.ui.notify(`Harness consolidation rejected: ${applied.error.slice(-300)}`, "warning");
      return;
    }
    if (!current()) {
      // Session shut down mid-apply: restore the pre-apply bytes so a dead
      // generation never leaves mutations behind.
      if (digestBefore === null) await fs.rm(target, { force: true }).catch(() => {});
      else await writeFileAtomic(target, Buffer.from(digestBefore, "base64"), 0o600).catch(() => {});
      return;
    }
    const digestAfter = (await readLayerFileBytes(target))?.toString("base64") ?? null;
    const receipt = {
      kind: "harness-consolidation-receipt",
      phase: "post",
      runId: run.manifest.runId,
      scopeDigest: run.manifest.scopeDigest,
      snapshotDigest: run.manifest.snapshotDigest,
      targetFile: target,
      digestBefore,
      digestAfter,
      applied: applied.applied,
      planDigest: sha256Digest(JSON.stringify(plan)),
    };
    await writeFileAtomic(path.join(run.manifest.runDir, "harness-post-receipt.json"), `${JSON.stringify(receipt, null, 2)}\n`).catch(() => {});
    ctx.ui.notify(`Harness consolidated: ${applied.applied.length} change(s) applied to ${path.basename(target)} (${ops.length} proposed).`, "info");
  } catch (err) {
    if (current()) ctx.ui.notify(`Harness consolidation failed: ${(err as Error).message.slice(-300)}`, "warning");
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
