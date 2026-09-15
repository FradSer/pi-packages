/**
 * Post execution harness checks.
 *
 * Tool-call policies remain pre-execution gates in guardrails.ts. This module
 * observes finalized assistant output and finalized tool results, then feeds
 * a bounded correction request back to the model when a post-generation rule
 * matches. Pi has already rendered streamed assistant text by message_end;
 * this module reports that fact rather than pretending it was withheld.
 */

import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import type {
  ExtensionAPI,
  ExtensionContext,
  MessageEndEvent,
  ToolResultEvent,
} from "@earendil-works/pi-coding-agent";
import { ToolExecutionComponent } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { createStaticToolLifecycleMessageRenderer, eventToolLifecycle, safeDisplayText } from "@fradser/pi-kit";
import { evaluatePhase } from "./guardrail-engine.ts";
import { resolveHarnessConfig } from "./guardrail-config.ts";
import type { Policy, PolicyPhase } from "./guardrail-types.ts";

export const MAX_REPAIR_ATTEMPTS = 2;
export const MAX_ARTIFACT_BYTES = 1_000_000;
export const MAX_ARTIFACT_PATHS = 32;
export const MAX_ARTIFACT_PATH_CHARS = 1_024;
export const MAX_ARTIFACT_TOTAL_BYTES = 8_000_000;

export type CheckStatus = "checked" | "observed" | "violated" | "unsupported" | "repair-exhausted";

export interface HarnessCheckEvent {
  kind: "harness-check";
  phase: Exclude<PolicyPhase, "tool-call">;
  status: CheckStatus;
  policy?: string;
  action?: "block" | "confirm" | "observe";
  reason?: string;
  source?: string;
  file?: string;
  path?: string;
  detail: string;
  repairAttempt?: number;
  maxRepairAttempts?: number;
}

type ArtifactRead = {
  ok: true;
  text: string;
  bytes: number;
} | {
  ok: false;
  reason: string;
};

interface RepairState {
  attempts: number;
  artifactBytes: number;
  artifacts: Map<string, Set<string>>;
  requestedArtifactViolations: Set<string>;
}

function textFromMessage(message: MessageEndEvent["message"]): string | undefined {
  if (message.role !== "assistant") return undefined;
  if (typeof message.content === "string") return message.content;
  if (!Array.isArray(message.content)) return undefined;
  return message.content
    .flatMap((part) => part?.type === "text" && typeof part.text === "string" ? [part.text] : [])
    .join("\n");
}

function sourceFile(source: string | undefined, paths: ReturnType<typeof resolveHarnessConfig>["paths"]): string {
  switch (source) {
    case "user": return paths.user;
    case "project": return paths.project;
    case "project.local": return paths.projectLocal;
    default: return "(built-in)";
  }
}

function appendCheck(pi: ExtensionAPI, details: HarnessCheckEvent): void {
  pi.appendEntry("harness-check", details);
}

function policyDetails(
  phase: Exclude<PolicyPhase, "tool-call">,
  policy: Policy | undefined,
  status: CheckStatus,
  detail: string,
  paths: ReturnType<typeof resolveHarnessConfig>["paths"],
  extra: Pick<HarnessCheckEvent, "path" | "repairAttempt" | "maxRepairAttempts"> = {},
): HarnessCheckEvent {
  return {
    kind: "harness-check",
    phase,
    status,
    ...(policy ? {
      policy: policy.name,
      action: policy.action ?? "block",
      reason: policy.reason,
      source: policy.source ?? "unknown",
      file: sourceFile(policy.source, paths),
    } : {}),
    detail,
    ...extra,
  };
}

function requestRepair(
  pi: ExtensionAPI,
  state: RepairState,
  phase: Exclude<PolicyPhase, "tool-call">,
  policy: Policy,
  decisionReason: string,
  detail: string,
  paths: ReturnType<typeof resolveHarnessConfig>["paths"],
  pathName?: string,
  contentFingerprint?: string,
): void {
  if (policy.action === "observe") return;
  const artifactViolation = phase === "artifact" ? `${policy.name}\0${pathName ?? ""}\0${contentFingerprint ?? ""}` : undefined;
  if (artifactViolation && state.requestedArtifactViolations.has(artifactViolation)) return;
  if (state.attempts >= MAX_REPAIR_ATTEMPTS) {
    appendCheck(pi, policyDetails(
      phase,
      policy,
      "repair-exhausted",
      `repair limit reached after ${MAX_REPAIR_ATTEMPTS} attempts; ${detail}`,
      paths,
      { path: pathName, maxRepairAttempts: MAX_REPAIR_ATTEMPTS },
    ));
    return;
  }
  const attempt = state.attempts + 1;
  state.attempts = attempt;
  if (artifactViolation) state.requestedArtifactViolations.add(artifactViolation);
  appendCheck(pi, policyDetails(
    phase,
    policy,
    "violated",
    detail,
    paths,
    { path: pathName, repairAttempt: attempt, maxRepairAttempts: MAX_REPAIR_ATTEMPTS },
  ));

  const subject = phase === "output"
    ? "the assistant response"
    : `the file${pathName ? ` ${pathName}` : " artifact"}`;
  const visibility = phase === "output"
    ? "The response has already been shown to the user; do not claim it was retracted."
    : "Inspect and correct the actual file on disk before reporting completion.";
  pi.sendMessage(
    {
      customType: "harness-post-generation-repair",
      content: [
        `Harness ${phase} policy "${policy.name}" found prohibited content in ${subject}.`,
        `Reason: ${decisionReason}`,
        visibility,
        "Provide a corrected response and stop after this bounded repair request.",
      ].join("\n"),
      display: false,
      details: { phase, policy: policy.name, path: pathName, attempt, maxAttempts: MAX_REPAIR_ATTEMPTS },
    },
    { deliverAs: "followUp", triggerTurn: true },
  );
}

function contentFingerprint(text: string): string {
  return createHash("sha256").update(text).digest("hex");
}

function appendNoMatch(
  pi: ExtensionAPI,
  phase: Exclude<PolicyPhase, "tool-call">,
  policy: Policy | undefined,
  detail: string,
  paths: ReturnType<typeof resolveHarnessConfig>["paths"],
  pathName?: string,
): void {
  appendCheck(pi, policyDetails(phase, policy, "checked", detail, paths, { path: pathName }));
}

function appendUnsupported(
  pi: ExtensionAPI,
  phase: "artifact",
  policy: Policy | undefined,
  reason: string,
  paths: ReturnType<typeof resolveHarnessConfig>["paths"],
  pathName?: string,
): void {
  appendCheck(pi, policyDetails(phase, policy, "unsupported", reason, paths, { path: pathName }));
}

async function readSafeArtifact(
  cwd: string,
  rawPath: string | undefined,
  maxBytes = MAX_ARTIFACT_BYTES,
): Promise<ArtifactRead> {
  if (!rawPath || rawPath.length > MAX_ARTIFACT_PATH_CHARS) return { ok: false, reason: "artifact path is missing or too long" };
  const workspace = path.resolve(cwd);
  const resolved = path.resolve(workspace, rawPath);
  const relative = path.relative(workspace, resolved);
  if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    return { ok: false, reason: "artifact path is outside the workspace" };
  }

  let workspaceReal: string;
  let realPath: string;
  let initialStat: fs.Stats;
  try {
    workspaceReal = await fs.promises.realpath(workspace);
    initialStat = await fs.promises.lstat(resolved);
    if (initialStat.isSymbolicLink()) return { ok: false, reason: "artifact path is a symlink" };
    if (!initialStat.isFile()) return { ok: false, reason: "artifact path is not a regular file" };
    realPath = await fs.promises.realpath(resolved);
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    return { ok: false, reason: code === "ENOENT" ? "artifact file does not exist" : "artifact path could not be inspected safely" };
  }

  const realRelative = path.relative(workspaceReal, realPath);
  if (realRelative === ".." || realRelative.startsWith(`..${path.sep}`) || path.isAbsolute(realRelative)) {
    return { ok: false, reason: "artifact path resolves outside the workspace" };
  }

  let handle: fs.promises.FileHandle | undefined;
  try {
    const noFollow = fs.constants.O_NOFOLLOW ?? 0;
    handle = await fs.promises.open(resolved, fs.constants.O_RDONLY | noFollow);
    const opened = await handle.stat();
    if (!opened.isFile()) return { ok: false, reason: "artifact path is not a regular file" };
    if (opened.dev !== initialStat.dev || opened.ino !== initialStat.ino) {
      return { ok: false, reason: "artifact path changed while it was being opened" };
    }
    if (opened.size > maxBytes) return { ok: false, reason: `artifact exceeds ${maxBytes} byte read limit` };
    const bytes = Buffer.allocUnsafe(maxBytes + 1);
    let bytesRead = 0;
    while (bytesRead < bytes.length) {
      const result = await handle.read(bytes, bytesRead, bytes.length - bytesRead, bytesRead);
      if (result.bytesRead === 0) break;
      bytesRead += result.bytesRead;
    }
    const finalStat = await handle.stat();
    const finalRealPath = await fs.promises.realpath(resolved);
    if (
      finalRealPath !== realPath ||
      finalStat.dev !== opened.dev ||
      finalStat.ino !== opened.ino ||
      finalStat.size !== opened.size ||
      finalStat.mtimeMs !== opened.mtimeMs ||
      finalStat.ctimeMs !== opened.ctimeMs ||
      bytesRead !== opened.size
    ) {
      return { ok: false, reason: "artifact changed while it was being read" };
    }
    if (bytesRead > maxBytes) return { ok: false, reason: `artifact exceeds ${maxBytes} byte read limit` };
    return { ok: true, text: bytes.subarray(0, bytesRead).toString("utf8"), bytes: bytesRead };
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    return { ok: false, reason: code === "ELOOP" ? "artifact path is a symlink" : "artifact file could not be read safely" };
  } finally {
    await handle?.close().catch(() => {});
  }
}

function artifactPolicies(config: ReturnType<typeof resolveHarnessConfig>["config"], toolName: string): Policy[] {
  return config.policies.filter((policy) =>
    (policy.phase ?? "tool-call") === "artifact" && (!policy.tools || policy.tools.includes(toolName)),
  );
}

function artifactPaths(policy: Policy, event: ToolResultEvent): string[] {
  if (policy.artifactPaths) return policy.artifactPaths;
  if (event.toolName !== "write" && event.toolName !== "edit") return [];
  const candidate = event.input.path;
  return typeof candidate === "string" && candidate ? [candidate] : [];
}

function rememberArtifacts(state: RepairState, policy: Policy, files: readonly string[]): void {
  if (!files.length) return;
  const paths = state.artifacts.get(policy.name) ?? new Set<string>();
  for (const file of files) paths.add(file);
  state.artifacts.set(policy.name, paths);
}

async function readArtifactWithinBudget(
  cwd: string,
  file: string | undefined,
  state: RepairState,
): Promise<ArtifactRead> {
  const remaining = MAX_ARTIFACT_TOTAL_BYTES - state.artifactBytes;
  if (remaining <= 0) return { ok: false, reason: `task artifact read budget of ${MAX_ARTIFACT_TOTAL_BYTES} bytes is exhausted` };
  const read = await readSafeArtifact(cwd, file, Math.min(MAX_ARTIFACT_BYTES, remaining));
  if (read.ok) state.artifactBytes += read.bytes;
  return read;
}

function isFinalAssistantMessage(message: MessageEndEvent["message"]): boolean {
  if (message.role !== "assistant") return false;
  const stopReason = (message as unknown as { stopReason?: unknown }).stopReason;
  if (stopReason === undefined) return true;
  return stopReason === "stop" || stopReason === "length";
}

async function checkFinalArtifacts(
  pi: ExtensionAPI,
  ctx: ExtensionContext,
  state: RepairState,
  resolved: ReturnType<typeof resolveHarnessConfig>,
): Promise<void> {
  const policies = resolved.config.policies.filter((policy) => (policy.phase ?? "tool-call") === "artifact");
  let pathCount = 0;
  for (const policy of policies) {
    const touched = state.artifacts.get(policy.name) ?? new Set<string>();
    const files = [...new Set([...(policy.artifactPaths ?? []), ...touched])];
    for (const file of files) {
      pathCount += 1;
      if (pathCount > MAX_ARTIFACT_PATHS) {
        appendUnsupported(pi, "artifact", policy, `task artifact path limit of ${MAX_ARTIFACT_PATHS} entries was reached`, resolved.paths, file);
        return;
      }
      const read = await readArtifactWithinBudget(ctx.cwd || process.cwd(), file, state);
      if (!read.ok) {
        appendUnsupported(pi, "artifact", policy, read.reason, resolved.paths, file);
        continue;
      }
      const decision = evaluatePhase(resolved.config, {
        phase: "artifact",
        text: read.text,
        policyName: policy.name,
        ignoreTools: true,
      });
      if (!decision) {
        appendNoMatch(pi, "artifact", policy, "final regular file was checked and no prohibited pattern matched", resolved.paths, file);
        continue;
      }
      if (decision.action === "observe") {
        appendCheck(pi, policyDetails("artifact", policy, "observed", "final regular file matched an observe policy", resolved.paths, { path: file }));
        continue;
      }
      requestRepair(pi, state, "artifact", policy, decision.cleanReason ?? decision.reason, "final regular file matched a prohibited pattern", resolved.paths, file, contentFingerprint(read.text));
    }
  }
}

async function checkArtifactResult(pi: ExtensionAPI, event: ToolResultEvent, ctx: ExtensionContext, state: RepairState): Promise<void> {
  const resolved = resolveHarnessConfig(ctx.cwd || process.cwd());
  const policies = artifactPolicies(resolved.config, event.toolName);
  if (!policies.length) return;

  for (const policy of policies) {
    const files = artifactPaths(policy, event);
    rememberArtifacts(state, policy, files);
    if (files.length > MAX_ARTIFACT_PATHS) {
      appendUnsupported(pi, "artifact", policy, `artifact path list exceeds ${MAX_ARTIFACT_PATHS} entries`, resolved.paths);
      continue;
    }
    if (event.isError) {
      for (const file of files.length ? files : [undefined]) {
        appendUnsupported(pi, "artifact", policy, "tool execution failed; artifact state was not verified", resolved.paths, file);
      }
      continue;
    }
    if (!files.length) {
      appendUnsupported(pi, "artifact", policy, "no artifact path was supplied; declare artifactPaths for command tools", resolved.paths);
      continue;
    }
    for (const file of files) {
      const read = await readArtifactWithinBudget(ctx.cwd || process.cwd(), file, state);
      if (!read.ok) {
        appendUnsupported(pi, "artifact", policy, read.reason, resolved.paths, file);
        continue;
      }
      const decision = evaluatePhase(resolved.config, {
        phase: "artifact",
        toolName: event.toolName,
        text: read.text,
        policyName: policy.name,
      });
      if (!decision) {
        appendNoMatch(pi, "artifact", policy, "regular file was checked and no prohibited pattern matched", resolved.paths, file);
        continue;
      }
      if (decision.action === "observe") {
        appendCheck(pi, policyDetails("artifact", policy, "observed", "regular file matched an observe policy", resolved.paths, { path: file }));
        continue;
      }
      requestRepair(pi, state, "artifact", policy, decision.cleanReason ?? decision.reason, "regular file matched a prohibited pattern", resolved.paths, file, contentFingerprint(read.text));
    }
  }
}

async function checkAssistantOutput(
  pi: ExtensionAPI,
  event: MessageEndEvent,
  ctx: ExtensionContext,
  state: RepairState,
): Promise<void> {
  const finalAssistant = isFinalAssistantMessage(event.message);
  const text = textFromMessage(event.message);
  const resolved = resolveHarnessConfig(ctx.cwd || process.cwd());
  if (finalAssistant && text !== undefined) {
    const policy = resolved.config.policies.find((entry) => (entry.phase ?? "tool-call") === "output");
    if (policy) {
      const decision = evaluatePhase(resolved.config, { phase: "output", text });
      if (!decision) {
        appendNoMatch(pi, "output", policy, "final assistant text was checked and no prohibited pattern matched", resolved.paths);
      } else {
        const matchedPolicy = resolved.config.policies.find((entry) => entry.name === decision.policyName) ?? policy;
        if (decision.action === "observe") {
          appendCheck(pi, policyDetails("output", matchedPolicy, "observed", "final assistant text matched an observe policy", resolved.paths));
        } else {
          requestRepair(pi, state, "output", matchedPolicy, decision.cleanReason ?? decision.reason, "final assistant text matched a prohibited pattern", resolved.paths);
        }
      }
    }
  }
  if (finalAssistant) await checkFinalArtifacts(pi, ctx, state, resolved);
}

/** Register post-generation checks. Call this alongside registerGuardrails;
 * keeping the registration separate prevents context guidance from becoming
 * an enforcement dependency. */
export default function registerOutputChecks(pi: ExtensionAPI): void {
  const state: RepairState = { attempts: 0, artifactBytes: 0, artifacts: new Map(), requestedArtifactViolations: new Set() };
  const reset = () => {
    state.attempts = 0;
    state.artifactBytes = 0;
    state.artifacts.clear();
    state.requestedArtifactViolations.clear();
  };
  pi.on("session_start", reset);
  pi.on("session_shutdown", reset);
  pi.on("input", (event) => {
    if (event.source !== "extension") reset();
  });
  pi.registerEntryRenderer("harness-check", (entry, { expanded }, theme) => {
    const details = entry.data as HarnessCheckEvent | undefined;
    const reason = safeDisplayText(details?.detail ?? "harness check");
    return createStaticToolLifecycleMessageRenderer({
      createSpec: () => eventToolLifecycle("harness", reason, {
        label: details?.status === "unsupported" ? "check unsupported" : `check ${details?.status ?? "recorded"}`,
        details: details ? [
          `phase=${details.phase}`,
          `status=${details.status}`,
          ...(details.policy ? [`policy=${details.policy}`] : []),
          ...(details.path ? [`path=${details.path}`] : []),
          reason,
        ] : undefined,
      }),
      expandHint: "ctrl+o to expand",
      fit: truncateToWidth,
      visibleWidth,
      wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
      hostComponent: ToolExecutionComponent,
    })({ content: "", details }, { expanded }, theme);
  });
  pi.on("message_end", (event, ctx) => checkAssistantOutput(pi, event, ctx, state));
  pi.on("tool_result", (event, ctx) => checkArtifactResult(pi, event, ctx, state));
}

export { readSafeArtifact, textFromMessage };
