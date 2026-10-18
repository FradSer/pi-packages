import { resolveToolTargetPath as harnessTargetPath } from "./tool-target-path";
import { preservesOwnedHarnessRules } from "./current-user-harness-correction";
/**
 * Guardrails — the harness surface of continual learning: declarative
 * Bash gates and flat rules that evolve through layered JSON config.
 *
 * Rules live in user-shared ~/.pi/agent/harness.json, project-shared
 * <project>/.pi/harness.json, and project-personal harness.local.json. Curated defaults ship with the
 * package and can be overridden by id from any layer.
 */

import fs from "node:fs";
import {Type} from "typebox";
import {previewHarnessCandidate} from "./harness-authoring-preview.ts";
import type { Stats } from "node:fs";
import path from "node:path";
import { isDeepStrictEqual } from "node:util";
import { keyHint, ToolExecutionComponent, type ExtensionAPI, type ExtensionContext } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { bindLifecycleRenderers, eventToolLifecycle, fieldLine, notifyPi, safeDisplayText, startedToolLifecycle } from "@fradser/pi-kit";

/** Geometry bound once: every guardrail row shares hint and wrapping. */
const guardrailRows = bindLifecycleRenderers({
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
  hostComponent: ToolExecutionComponent,
});
const renderHarnessPreview = guardrailRows.result<{content: unknown; details?: {passed?: boolean; errors?: string[]; cases?: unknown[]}}>(result => eventToolLifecycle("harness", "rule preview", {
      label: result.details?.passed === undefined ? "checking" : result.details.passed ? "verified" : "rejected",
      tone: result.details?.passed === undefined ? undefined : result.details.passed ? "success" : "error",
      details: [fieldLine("fixtures", result.details?.cases?.length ?? 0), ...(result.details?.errors ?? []).map(error => safeDisplayText(error))],
      detailLimit: 5,
    }));

import {
  evaluateBash,
  validateRuleDeclaration,
  validateRuleContainer,
  mergeLayers,
  DEFAULT_RULES,
} from "./guardrail-engine.ts";
import { compareHarnessLayers, configPaths, loadLayers, resolveHarnessConfig } from "./guardrail-config.ts";
import { HARNESS_BASH_NOTE_PREFIX, HARNESS_CONFIG_NOTE_PREFIX } from "./harness-guidance-planner.ts";
import { evaluateLegacyTools, LEGACY_FIELDS } from "./legacy-harness.ts";
import type { LayerReadIssue, RuleLayer } from "./guardrail-types.ts";
import { runHarnessMenu, type HarnessMenuScope } from "./harness-menu.ts";

interface HarnessPolicyEvent {
  kind: "policy-matched";
  policy: string;
  action: "block" | "confirm" | "observe";
  tool: string;
  reason: string;
  outcome: "observed" | "allowed once" | "blocked by rule" | "blocked by user choice" | "blocked: confirmation timed out" | "no UI available to confirm";
  source: string;
  file: string;
}

type HarnessEventData = HarnessPolicyEvent;



function harnessSourcePath(source: string | undefined, paths: ReturnType<typeof configPaths>): string {
  switch (source) {
    case "user":
      return paths.user;
    case "user.scoped":
      return paths.userScoped;
    case "project":
      return paths.project;
    case "project.local":
      return paths.projectLocal;
    case "built-in defaults":
      return "(built-in)";
    default:
      return "(unknown)";
  }
}

/** Name the file and the exact reason for each layer whose current bytes could
 *  not be interpreted. The blocked tool result and /harness diagnostics share
 *  one wording, so the reader can identify the bytes that need repair instead of
 *  being told only that evaluation is incomplete. Text stays bounded: at most
 *  four layers, each reason truncated to a fixed width. */
function harnessReadIssueLines(issues: readonly LayerReadIssue[], paths: ReturnType<typeof configPaths>): string[] {
  return issues.slice(0, 4).map(issue => {
    const file = harnessSourcePath(issue.source, paths);
    const reason = safeDisplayText(issue.errors.join("; ") || "unreadable layer")
      // The layer error already carries the file; the reader needs it once.
      .split(`${file}: `).join("").slice(0, 240);
    return `${issue.source} (${file}): ${reason}`;
  });
}

function withinRoot(root: string, candidate: string): boolean {
  const relative = path.relative(root, candidate);
  return relative === "" || (relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative));
}

async function deepestExistingDirectory(candidate: string): Promise<string> {
  let current = candidate;
  while (true) {
    try {
      const stat = await fs.promises.lstat(current);
      if (stat.isSymbolicLink()) throw new Error(`Harness target parent is a symlink: ${current}`);
      if (!stat.isDirectory()) throw new Error(`Harness target parent is not a directory: ${current}`);
      return current;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      const parent = path.dirname(current);
      if (parent === current) throw error;
      current = parent;
    }
  }
}

export async function assertHarnessTargetContained(targetFile: string, workspace?: string): Promise<void> {
  const target = path.resolve(targetFile);
  const root = path.resolve(workspace ?? path.dirname(target));
  if (!withinRoot(root, target)) throw new Error(`Harness target is outside the workspace: ${targetFile}`);

  const existingRoot = await deepestExistingDirectory(root);
  const existingRootReal = await fs.promises.realpath(existingRoot);
  const prospectiveRootReal = path.join(existingRootReal, path.relative(existingRoot, root));
  let current = existingRoot;
  const parent = path.dirname(target);
  const segments = path.relative(existingRoot, parent).split(path.sep).filter(Boolean);
  for (const segment of segments) {
    current = path.join(current, segment);
    let stat: Stats;
    try {
      stat = await fs.promises.lstat(current);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
      throw error;
    }
    if (stat.isSymbolicLink()) throw new Error(`Harness target parent is a symlink: ${current}`);
    if (!stat.isDirectory()) throw new Error(`Harness target parent is not a directory: ${current}`);
    if (withinRoot(root, current)) {
      const currentReal = await fs.promises.realpath(current);
      if (!withinRoot(prospectiveRootReal, currentReal)) throw new Error(`Harness target parent resolves outside the workspace: ${current}`);
    }
  }
}

async function readHarnessTarget(targetFile: string): Promise<Buffer | null> {
  let stat: Stats;
  try {
    stat = await fs.promises.lstat(targetFile);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
  if (stat.isSymbolicLink() || !stat.isFile()) {
    throw new Error(`Harness target is not a regular file: ${targetFile}`);
  }
  return fs.promises.readFile(targetFile);
}

interface HarnessWriteApproval {
  target: string;
  workspace?: string;
  input: string;
  files: ReadonlyMap<string, Buffer | null>;
}

/** A repair preview authorizes exact bytes, not just their parsed diagnostics.
 * Keep this snapshot alive through every subsequent asynchronous approval. */
async function recheckHarnessWriteApproval(
  approval: HarnessWriteApproval,
  input: () => unknown,
  signal?: AbortSignal,
): Promise<string | undefined> {
  const invalidInput = (): string | undefined => {
    if (signal?.aborted) return "Harness replacement authorization cancelled; original bytes preserved.";
    if (JSON.stringify(input()) !== approval.input) return "Harness tool arguments changed during authorization; read and validate again. Original bytes preserved.";
    return undefined;
  };
  const initial = invalidInput();
  if (initial) return initial;
  try {
    await assertHarnessTargetContained(approval.target, approval.workspace);
    for (const [file, bytes] of approval.files) {
      if (!isDeepStrictEqual(await readHarnessTarget(file), bytes)) {
        return file === approval.target
          ? "Harness target changed during authorization; read and validate it again."
          : `Harness layer changed during authorization: ${file}; read and validate it again.`;
      }
    }
  } catch (error) {
    return `Harness configuration could not be rechecked after authorization: ${(error as Error).message}. No file was written.`;
  }
  return invalidInput();
}

export interface ResolvedHarnessTarget {
  request: string;
  targetFile: string;
  scope: "project.local" | "project" | "user";
  scopeLabel: string;
}

export function resolveHarnessTarget(
  rawArgs: string,
  cwd: string,
  agentDir?: string,
): ResolvedHarnessTarget {
  const paths = configPaths(cwd, agentDir);
  const trimmed = rawArgs.trim();

  let scope: "project.local" | "project" | "user" = "project";
  let request = trimmed;

  const flagMatch = trimmed.match(
    /^(--global-shared|--user-shared|--global|--user|--shared|--project-local|--project|--repo|--local|-g|-p|-l)\b\s*(.*)$/i,
  );

  if (flagMatch) {
    const flag = flagMatch[1].toLowerCase();
    request = flagMatch[2].trim();
    if (flag === "--global-shared" || flag === "--user-shared" || flag === "--global" || flag === "--user" || flag === "-g") {
      scope = "user";
    } else if (flag === "--shared" || flag === "--project" || flag === "--repo" || flag === "-p") {
      scope = "project";
    } else {
      scope = "project.local";
    }
  }

  let targetFile: string;
  let scopeLabel: string;
  switch (scope) {
    case "user":
      targetFile = paths.user;
      scopeLabel = "global shared harness.json";
      break;
    case "project":
      targetFile = paths.project;
      scopeLabel = "project shared harness.json (git-tracked)";
      break;
    case "project.local":
    default:
      targetFile = paths.projectLocal;
      scopeLabel = "project personal harness.local.json";
      break;
  }

  return { request, targetFile, scope, scopeLabel };
}

export function buildHarnessRulePrompt(request: string, targetFile: string, scopeLabel?: string, availableSkills: readonly string[] = [], targetState?: "absent" | "existing", cwd?: string): string {
  const relative = cwd ? path.relative(cwd, targetFile) : undefined;
  const accessPath = relative && !path.isAbsolute(relative) && relative !== ".." && !relative.startsWith(`..${path.sep}`) ? relative : targetFile;
  return [
    "Create or update one Pi harness rule only when the requested outcome is safely expressible.",
    `User request: ${request}`,
    `Work exclusively in ${accessPath} (${scopeLabel ?? "harness.json"}). Use the exact tool path ${accessPath}; do not expand or substitute it. Preserve other harness files, memory, and unrelated files unchanged.`,
    "Read only the exact target; do not read AGENTS.md or explore other files. The supplied target resolves the chosen layer. Do not inspect other layers, home configuration, or the parent directory. A missing target requires no directory read; write creates its parents.",
    ...(targetState ? [`Target state checked by the parent: ${targetState}. Recheck before writing; this observation does not bypass validation or authorize overwriting intervening changes.`] : []),
    "Missing configuration is not a blocker: this command authorizes first creation of the requested supported rule. ENOENT means an absent predecessor; continue. Do not create an empty placeholder.",
    "For resource protection, identify the resource and safeguards from the current conversation. Without exact command interception, consider scoped text guidance for future relevant work. Do not invent service identity, quotas, numeric concurrency, or rate limits; guidance must not claim to enforce a rate limit. If essential scope or behavior is still ambiguous, ask one concise actionable question and explain the proposed mechanism instead of ending at file absence. Report impossible guarantees.",
    "Use the schema below. Do not search SDK documentation or source for another schema. The parent validates the complete candidate before write; report rejections honestly.",
    "Required protocol, in order:",
    `1. Read the exact target ${accessPath}. If it returns ENOENT, treat the predecessor as absent in memory; no preliminary empty file or parent directory creation.`,
    "2. Assess expressibility before mutation. Preserve the user's semantic boundary; clarify rather than add restrictions or narrow a project-wide request to one skill. Unsupported or ambiguous means no file writes. Recommending AGENTS.md, skills or verification does not authorize editing them. Report the limitation; preserve existing rules.",
    "3. Construct one complete candidate. Preserve every existing rule outside the requested change. Compatible legacy policies/disabled/skillPrompts/learnedPolicies remain active read-only: flat additions must preserve every legacy container value unchanged. Never author or modify legacy entries or translate them into weaker flat rules. Removing legacy containers requires native before/after protection-loss preview and explicit user authorization. Invalid entries require authorized repair; otherwise leave original bytes unchanged. Validate every declaration, regex, registered skill and the effective merge; preview same-id replacement, changed execution conditions and nearer-layer shadowing. If only unchanged other layers have remaining diagnostics, submit the valid target-only replacement via write for native confirmation; report incomplete activation and leave other layers unchanged. This exception requires an invalid target and explicit approval, never a malformed candidate or headless repair. Keep parent-owned learnedRules metadata unchanged.",
    `4. Call harness_preview with content (the entire JSON text) and cases:[{ruleId,input,matches}]. Use plain future text/command/skill strings, not regex literals or authoring discussion; every changed enabled rule needs positive and negative cases. Include another resource with the same action as a negative when scope is resource-specific. Never broaden a resource-specific rule with a standalone incident phrase. Repair failures before mutation. Write once: after validation and passing preview, use write at ${accessPath} with the entire JSON including the requested rule. Write creates missing parents; never use edit or preliminary initialization.`,
    `5. Read back ${accessPath} and compare the complete structure. Persistence is not trigger verification. The non-executing evaluator is harness_preview. Do not create verification scripts or scratch files or rewrite the saved candidate. If no non-executing evaluator is available, report trigger verification as unverified and do not write. Never execute dangerous or side-effecting example commands merely to test a rule.`,
    'Schema: a flat "rules" array; each rule has a stable non-empty "id", optional boolean "enabled", and exactly one selector. A minimal disable is {"id":"existing-id","enabled":false}. Same id in a nearer layer replaces the whole definition.',
    `Registered skill values (exact keys only): ${availableSkills.length ? availableSkills.join(", ") : "(none registered in this session)"}. A skill rule uses id, skill, instructions; it applies only on that expanded skill invocation, not a plain read of SKILL.md. It is contextual guidance, not global interception or guaranteed compliance.`,
    'New bash positive fixtures must be exact backtick-quoted user commands or successful Bash calls from this session; otherwise use text guidance or ask for an example. A bash rule uses id, bash (JavaScript regex over the raw command), message, and optional action:"confirm"|"block". Omit "action" to execute the command and deliver the message with its real result. Confirm requires approval for that call; block keeps it unexecuted with corrective guidance.',
    "A text rule uses id, text (regex over retained model-visible conversation), instructions. It provides relevant guidance, not semantic enforcement. New output/artifact and arbitrary tool-argument checks are unsupported; existing persisted legacy checks remain enforced.",
    `Regex JSON escaping: ${JSON.stringify({text: String.raw`\bRESOURCE\b`})} means word boundaries; ${JSON.stringify({text: String.raw`\\bRESOURCE\\b`})} means literal backslashes. Prefer a simple literal selector. Test plain positive/negative strings without authoring history or regex literals.`,
    "Generalize evidence -> reusable error class -> supported mechanism. Incident document tokens, row numbers, or verbatim phrases are evidence, not automatic boundaries; retain identifiers only for an explicit resource-specific user requirement. Transfer-test another same-kind document and a rephrasing; unrelated actions remain allowed, keeping confirmation scoped to the requested action surface.",
    "Perform the supported change and report the exact rule id and file changed. Distinguish saved, resolved, delivered and executed outcomes; a successful save is not proof the model followed guidance. If personal configuration was requested, check existing ignore settings and report whether the file is ignored, without changing ignore files.",
  ].join("\n");
}

export function validateHarnessWrite(input: unknown, availableSkills: ReadonlySet<string>, previous?: unknown): string[] {
  if (!input || typeof input !== "object" || Array.isArray(input)) return ["harness write input must be an object"];
  const content = (input as Record<string, unknown>).content;
  if (typeof content !== "string") return ["harness write content must be JSON text"];
  let parsed: unknown;
  try { parsed = JSON.parse(content); } catch { return ["harness write content must be valid JSON"]; }
  const errors = validateRuleContainer(parsed);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return errors;
  const config = parsed as Record<string, unknown>;
  if (Array.isArray(config.rules)) config.rules.forEach((rule, index) => {
    errors.push(...validateRuleDeclaration(rule, availableSkills).map(error => `rules[${index}] ${error}`));
  });
  const prior = previous && typeof previous === "object" && !Array.isArray(previous) ? previous as Record<string, unknown> : {};
  for (const field of LEGACY_FIELDS) {
    if (Object.hasOwn(config, field) && !isDeepStrictEqual(config[field], prior[field])) errors.push(`legacy ${field} is read-only: preserve it unchanged; new authoring uses flat rules`);
  }
  if (!errors.length) errors.push(...mergeLayers([{ ...config, source: "candidate" } as RuleLayer], availableSkills).errors);
  if (!isDeepStrictEqual(config.learnedRules, prior.learnedRules)) errors.push("parent-owned learnedRules provenance must be preserved unchanged");
  return errors;
}

function incompleteActivationNotice(config: ReturnType<typeof mergeLayers>): string | undefined {
  if (!config.errors.length) return undefined;
  return [
    "Harness activation remains incomplete; saving this file does not repair other layers or verify triggers.",
    ...config.errors.slice(0, 5).map(error => safeDisplayText(error).slice(0, 500)),
    ...(config.errors.length > 5 ? [`${config.errors.length - 5} more diagnostics; use /harness to inspect configuration.`] : []),
    ...(!config.bashEvaluationComplete ? ["Bash remains fail-closed until the remaining configuration is repaired."] : []),
  ].join("\n");
}

/** The confirm gate blocks the agent loop while its dialog waits, so an
 * unattended session must fail closed after a bounded wait instead of
 * hanging. pi renders the remaining time as a live countdown. */
const GUARDRAILS_CONFIRM_TIMEOUT_MS = 60_000;

export function harnessCommandExamples(request: string, ctx: Pick<ExtensionContext, "sessionManager">): Set<string> {
  const examples = new Set<string>();
  for (const match of request.matchAll(/`([^`\n]+)`/g)) examples.add(match[1]);
  for (const match of request.matchAll(/```(?:bash|sh|shell)?\n([\s\S]*?)```/g)) if (match[1].trim()) examples.add(match[1].trim());
  const calls = new Map<string, {command: string; results: number; succeeded: boolean; duplicate: boolean}>();
  for (const entry of ctx.sessionManager?.getBranch?.() ?? []) {
    if (entry.type !== "message") continue;
    const message = entry.message;
    if (message.role === "assistant") {
      for (const part of message.content) if (part.type === "toolCall" && part.name === "bash" && typeof part.arguments.command === "string") {
        const prior = calls.get(part.id);
        if (prior) prior.duplicate = true;
        else calls.set(part.id, {command:part.arguments.command, results:0, succeeded:false, duplicate:false});
      }
    } else if (message.role === "toolResult" && message.toolName === "bash") {
      const call = calls.get(message.toolCallId);
      if (call) { call.results += 1; call.succeeded = message.isError === false; }
    }
  }
  for (const call of calls.values()) if (call.succeeded && call.results === 1 && !call.duplicate) examples.add(call.command);
  return examples;
}

export default function registerGuardrails(pi: ExtensionAPI) {
  let authoring: {cwd: string; target: string; previewed?: string; predecessor?: Buffer | null; commandExamples: Set<string>} | undefined;
  const finishAuthoring = () => {
    authoring = undefined;
    if (pi.getActiveTools && pi.setActiveTools) pi.setActiveTools(pi.getActiveTools().filter(name => name !== "harness_preview"));
  };
  pi.on("agent_end", finishAuthoring);
  pi.on("session_start", finishAuthoring);
  pi.on("session_shutdown", finishAuthoring);
  pi.registerTool?.({
    name: "harness_preview", label: "Preview Harness rule", description: "Read-only parent evaluator for the active /harness candidate. Executes plain positive/negative string fixtures without commands, network calls or file writes. Every changed enabled rule needs both outcomes. This does not authorize mutation.",
    renderShell: "self",
    renderCall: () => guardrailRows.emptyCall(),
    renderResult(result, options, theme, context) {
      // A rejected fixture is a structured outcome, not an unexpected tool
      // exception. Keep model isError unchanged while showing its bounded row.
      const details = result.details;
      const passed = details && typeof details === "object" && "passed" in details && typeof details.passed === "boolean" ? details.passed : undefined;
      const errors: unknown[] = details && typeof details === "object" && "errors" in details && Array.isArray(details.errors) ? details.errors : [];
      const cases: unknown[] = details && typeof details === "object" && "cases" in details && Array.isArray(details.cases) ? details.cases : [];
      return renderHarnessPreview({content:result.content, details:passed === undefined ? undefined : {passed, errors:errors.filter((value): value is string => typeof value === "string"), cases}}, options, theme, passed === undefined ? context : {...context, isError:false});
    },
    parameters: Type.Object({content: Type.String({maxLength:128000}), cases: Type.Array(Type.Object({ruleId: Type.String(), input: Type.String({maxLength:8000}), matches: Type.Boolean()}), {maxItems:64})}),
    async execute(_id, params, signal, _update, ctx) {
      const current = authoring;
      if (!current || current.cwd !== (ctx.cwd || process.cwd()) || signal?.aborted) return {content:[{type:"text", text:"No active Harness authoring request"}], details:{passed:false}, isError:true};
      current.previewed = undefined;
      await assertHarnessTargetContained(current.target, current.target === path.resolve(configPaths(current.cwd).user) ? undefined : current.cwd);
      const bytes = await readHarnessTarget(current.target);
      let previous: unknown;
      try { previous = bytes ? JSON.parse(bytes.toString("utf8")) : undefined; } catch { /* Native repair authorization still governs invalid predecessors. */ }
      const skills = new Set(pi.getCommands().filter(command => command.source === "skill").map(command => command.name.replace(/^skill:/, "")));
      const errors = validateHarnessWrite({content:params.content}, skills, previous);
      const result = errors.length ? {passed:false, errors, cases:[]} : previewHarnessCandidate(params.content, params.cases, skills, previous, current.commandExamples);
      if (authoring !== current || signal?.aborted) return {content:[{type:"text", text:"Harness authoring request changed or cancelled"}], details:{passed:false}, isError:true};
      if (result.passed) { current.previewed = params.content; current.predecessor = bytes; }
      return {content:[{type:"text", text:JSON.stringify(result)}], details:result, isError:!result.passed};
    },
  });
  const pendingBashMessages = new Map<string, Array<{ id: string; message: string }>>();

  pi.registerEntryRenderer("harness-event", (entry, { expanded }, theme) => {
    const details = entry.data as HarnessEventData | undefined;
    if (details?.kind === "policy-matched") {
      const reason = safeDisplayText(details.reason);
      const label = details.action === "observe" ? "policy observed"
        : details.action === "confirm" && details.outcome === "allowed once" ? "policy allowed" : "policy blocked";
      return guardrailRows.message(() => eventToolLifecycle("harness", reason, {
        label,
        tone: label === "policy blocked" ? "error" : label === "policy observed" ? "warning" : "success",
        details: [
          fieldLine("policy", details.policy),
          fieldLine("action", details.action),
          fieldLine("outcome", details.outcome),
          fieldLine("tool", details.tool),
          fieldLine("source", details.source),
          fieldLine("file", details.file),
        ],
      }))({ content: "", details }, { expanded }, theme);
    }
    const message = "harness policy event";
    return guardrailRows.message(() => eventToolLifecycle("harness", message, { label: "event" }))({ content: "", details }, { expanded }, theme);
  });

  pi.registerMessageRenderer?.("harness-procedure", guardrailRows.message(message => startedToolLifecycle("harness", String((message.details as { subject?: string } | undefined)?.subject ?? "rule request"), { label: "started" })));
  const startRuleProcedure = (request: string, target: string, scope: string, skills: readonly string[], targetState: "absent" | "existing", cwd: string, commandExamples: Set<string>): void => {
    authoring = {cwd, target:path.resolve(target), commandExamples};
    if (pi.getActiveTools && pi.setActiveTools) pi.setActiveTools([...new Set([...pi.getActiveTools(), "harness_preview"])]);
    pi.sendMessage({ customType: "harness-procedure", content: buildHarnessRulePrompt(request, target, scope, skills, targetState, cwd), display: true, details: { subject: safeDisplayText(request) } }, { deliverAs: "followUp", triggerTurn: true });
  };

  pi.on("tool_call", async (event, ctx) => {
    const cwd = ctx.cwd || process.cwd();
    const paths = configPaths(cwd);
    let configRecovery = false;
    const authoringRequest = authoring?.cwd === cwd ? authoring : undefined;
    const authoringInput = JSON.stringify(event.input);
    const finalizeAuthoring = async () => {
      if (!authoringRequest || event.toolName !== "write") return undefined;
      const bytes = await readHarnessTarget(authoringRequest.target);
      // Compare and consume synchronously after the last await, including when
      // another admitted call or confirmation overlaps this one.
      if (authoring !== authoringRequest || ctx.signal?.aborted || JSON.stringify(event.input) !== authoringInput || authoringRequest.previewed !== (event.input as Record<string, unknown>).content || !isDeepStrictEqual(bytes, authoringRequest.predecessor)) return {block:true, reason:"Harness preview changed, expired, was consumed, or its predecessor changed. Preview again before writing."};
      authoringRequest.previewed = undefined;
      return undefined;
    };
    let writeApproval: HarnessWriteApproval | undefined;
    if (event.toolName === "write" || event.toolName === "edit") {
      const input = (event.input ?? {}) as Record<string, unknown>;
      const inputSnapshot = JSON.stringify(input);
      const target = typeof input.path === "string" ? input.path : "";
      const targetPath = harnessTargetPath(target, cwd);
      if (authoringRequest && targetPath !== authoringRequest.target) return {block:true, reason:"Active Harness authoring permits only its chosen target. No file was written."};
      if (targetPath === path.join(path.dirname(paths.user), "harness.local.json")) {
        return { block: true, reason: "Use ~/.pi/agent/harness.json for global configuration. Project shared .pi/harness.json is the default; select .pi/harness.local.json for explicitly requested personal configuration." };
      }
      const harnessPaths = new Set(Object.values(paths).map((file) => path.resolve(file)));
      if (harnessPaths.has(targetPath)) {
        if (authoring?.cwd === cwd && authoring.target === targetPath && authoring.previewed !== input.content) return {block:true, reason:"Run harness_preview with this exact complete candidate and passing positive/negative fixtures before writing. No file was written."};
        if (event.toolName === "edit") return { block: true, reason: "Harness configuration requires a complete validated JSON write. Read the target, preserve its entries, and use write instead of edit." };
        try {
          await assertHarnessTargetContained(targetPath, targetPath === path.resolve(paths.user) ? undefined : cwd);
        } catch (error) {
          return { block: true, reason: `Unsafe harness target: ${(error as Error).message}` };
        }
        const availableSkills = new Set(pi.getCommands().filter((command) => command.source === "skill").map((command) => command.name.replace(/^skill:/, "")));
        let priorBytes: Buffer | null;
        try { priorBytes = await readHarnessTarget(targetPath); }
        catch (error) { return { block: true, reason: `Unsafe harness target: ${(error as Error).message}` }; }
        if (authoringRequest && !isDeepStrictEqual(priorBytes, authoringRequest.predecessor)) return {block:true, reason:"Harness predecessor changed since preview; read and preview again. No file was written."};
        let previous: unknown;
        let predecessorErrors: string[] = [];
        if (priorBytes) {
          try {
            previous = JSON.parse(priorBytes.toString("utf8"));
            predecessorErrors = validateHarnessWrite({ content: priorBytes.toString("utf8") }, availableSkills, previous);
          } catch { predecessorErrors = ["existing target is not valid JSON"]; }
        }
        const errors = validateHarnessWrite(input, availableSkills, previous);
        if (errors.length) return { block: true, reason: `Invalid harness configuration: ${errors.join("; ")}. The file was not written. Report existing invalid entries; obtain explicit user authorization before repairing or removing them.` };
        const targetSource = targetPath === path.resolve(paths.user) ? "user" : targetPath === path.resolve(paths.project) ? "project" : "project.local";
        const candidate = JSON.parse(input.content as string) as Record<string, unknown>;
        if (!authoringRequest && !preservesOwnedHarnessRules(previous, candidate, loadLayers(cwd).filter(layer => layer.source !== targetSource))) {
          return {block: true, reason: "Automatically learned Harness rules require parent-reviewed correction or explicit /harness authoring with preview. Ordinary task writes must preserve their exact declarations and ownership markers. No file was written."};
        }
        const priorConfig = previous && typeof previous === "object" && !Array.isArray(previous) ? previous as Record<string, unknown> : {};
        const removedLegacy = LEGACY_FIELDS.filter(field => Object.hasOwn(priorConfig, field) && !Object.hasOwn(candidate, field));
        const needsApproval = predecessorErrors.length > 0 || removedLegacy.length > 0;
        const otherBytes = new Map<string, Buffer | null>();
        if (needsApproval) {
          try {
            for (const file of harnessPaths) {
              if (file !== targetPath) otherBytes.set(file, await readHarnessTarget(file));
            }
          } catch (error) {
            return { block: true, reason: `Cannot verify unchanged harness layers: ${(error as Error).message}. No file was written.` };
          }
        }
        const otherLayers = loadLayers(cwd).filter(layer => layer.source !== targetSource);
        const layers = [...otherLayers, { ...candidate, source: targetSource } as RuleLayer];
        layers.sort(compareHarnessLayers);
        const effective = mergeLayers([{ source: "built-in defaults", rules: DEFAULT_RULES as unknown as Array<Record<string, unknown>> }, ...layers], availableSkills);
        // Compare independently resolved diagnostics, not source-like text in an
        // error or rule id. Only an invalid target's authorized repair may leave
        // exactly the diagnostics from the byte-checked, untouched other layers.
        const otherErrors = mergeLayers(otherLayers, availableSkills).errors;
        if (effective.errors.length && (!predecessorErrors.length || !isDeepStrictEqual(effective.errors, otherErrors))) {
          return { block: true, reason: `Invalid effective harness configuration: ${effective.errors.join("; ")}. No file was written.` };
        }
        if (needsApproval) {
          if (!ctx.hasUI) return { block: true, reason: `Existing invalid configuration or legacy protection removal requires explicit user authorization before replacement: ${[...predecessorErrors, ...removedLegacy].join("; ")}. No UI is available; original bytes preserved.` };
          if (ctx.signal?.aborted) return { block: true, reason: "Harness replacement authorization cancelled; original bytes preserved." };
          writeApproval = {
            target: targetPath,
            workspace: targetPath === path.resolve(paths.user) ? undefined : cwd,
            input: inputSnapshot,
            files: new Map([[targetPath, priorBytes], ...otherBytes]),
          };
          const remaining = incompleteActivationNotice(effective);
          const preview = [targetPath, predecessorErrors.join("; "), ...(removedLegacy.length ? [`Removing legacy containers (${removedLegacy.join(", ")}) can remove enforced protection or guidance. No equivalence to weaker flat selectors is assumed.`] : []), `Previous complete configuration:\n${priorBytes?.toString("utf8")}`, ...(remaining ? [remaining] : []), `Proposed complete replacement:\n${input.content}`].join("\n\n");
          const approved = await ctx.ui.confirm("Replace harness configuration and affected protection?", preview, { timeout: GUARDRAILS_CONFIRM_TIMEOUT_MS, signal: ctx.signal });
          if (!approved || ctx.signal?.aborted) return { block: true, reason: "Harness replacement not authorized; original bytes preserved." };
          const changed = await recheckHarnessWriteApproval(writeApproval, () => event.input, ctx.signal);
          if (changed) return { block: true, reason: changed };
          if (remaining) notifyPi(ctx.ui, `Replacement authorized but not yet written. ${remaining}`, "warning");
        }
        if (JSON.stringify(event.input) !== inputSnapshot) return { block: true, reason: "Harness tool arguments changed during validation; read and validate again. Original bytes preserved." };
        // Only incomplete evaluation is bypassed for a validated config write.
        // Already-valid matching protection still participates below.
        configRecovery = true;
      }
    }
    if (event.toolName === "read" && typeof event.input.path === "string" && Object.values(paths).some(file => path.resolve(file) === harnessTargetPath(event.input.path as string, cwd))) configRecovery = true;

    // Preflight and repair approval can await while another actor edits policy.
    // Resolve execution policy only now, not from before those asynchronous checks.
    const { config } = resolveHarnessConfig(cwd);
    // One decision across both representations: no early allow can bypass a
    // stronger protection, and all confirmations share one native dialog.
    const args = (event.input ?? {}) as Record<string, unknown>;
    const command = typeof args.command === "string" ? args.command : "";
    const legacy = evaluateLegacyTools(config.legacy, event.toolName, args);
    if (configRecovery) legacy.incomplete = [];
    const flat = event.toolName === "bash" ? evaluateBash(config, command) : undefined;
    const matches = [
      ...(flat?.matchedRules.map(rule => ({ id: rule.id, message: rule.message, action: rule.action, source: rule.source })) ?? []),
      ...legacy.matches.map(match => ({ id: match.policyName, message: match.cleanReason, action: match.action, source: match.source })),
    ];
    for (const match of matches.filter(match => match.action === "observe")) pi.appendEntry("harness-event", {
      kind: "policy-matched", policy: match.id, action: "observe", tool: event.toolName,
      reason: match.message, outcome: "observed", source: match.source ?? "unknown", file: harnessSourcePath(match.source, paths),
    } satisfies HarnessPolicyEvent);
    {
      const readIssueLines = harnessReadIssueLines(config.layerReadIssues, paths);
      const unreadableFiles = config.layerReadIssues.filter(issue => issue.unavailable)
        .map(issue => harnessSourcePath(issue.source, paths));
      const bashEval = {
        decision: flat?.decision === "incomplete" || legacy.incomplete.length ? "incomplete"
          : matches.some(match => match.action === "block") ? "block"
            : matches.some(match => match.action === "confirm") ? "confirm" : "execute",
        matchedRules: matches,
        messages: matches.filter(match => match.action !== "observe").map(match => match.message),
        incompleteRuleIds: [...(flat?.incompleteRuleIds ?? []), ...legacy.incomplete],
        reason: legacy.incomplete.length ? `Harness evaluation is incomplete for ${event.toolName}: ${legacy.incomplete.join(", ")}${readIssueLines.length ? ` — ${readIssueLines.join("; ")}` : ""}. Use /harness to inspect diagnostics, read the affected config, and submit a complete validated native write for authorized repair; no protection needs to be disabled.` : flat?.reason,
      };

      if (bashEval.decision === "incomplete") {
        pi.appendEntry("harness-event", {
          kind: "policy-matched",
          policy: (bashEval.incompleteRuleIds ?? []).join(", ") || "(unidentified)",
          action: "block",
          tool: event.toolName,
          reason: bashEval.reason ?? "Bash evaluation incomplete",
          outcome: "blocked by rule",
          source: "unknown",
          file: unreadableFiles.join(", ") || harnessSourcePath(undefined, paths),
        });
        return { block: true, reason: bashEval.reason ?? "Bash evaluation incomplete" };
      }

      if (bashEval.decision === "block") {
        const source = bashEval.matchedRules[0]?.source ?? "unknown";
        const file = harnessSourcePath(source, paths);
        pi.appendEntry("harness-event", {
          kind: "policy-matched",
          policy: bashEval.matchedRules.map((r) => r.id).join(", "),
          action: "block",
          tool: event.toolName,
          reason: bashEval.messages.join("\n"),
          outcome: "blocked by rule",
          source,
          file,
        });
        return { block: true, reason: bashEval.messages.join("\n") };
      }

      if (bashEval.decision === "confirm") {
        const cleanReason = bashEval.messages.join("\n");
        const source = bashEval.matchedRules[0]?.source ?? "unknown";
        const file = harnessSourcePath(source, paths);

        if (!ctx.hasUI) {
          pi.appendEntry("harness-event", {
            kind: "policy-matched",
            policy: bashEval.matchedRules.map((r) => r.id).join(", "),
            action: "confirm",
            tool: event.toolName,
            reason: cleanReason,
            outcome: "no UI available to confirm",
            source,
            file,
          });
          return { block: true, reason: `${cleanReason}\n(no UI available to confirm)` };
        }

        if (ctx.signal?.aborted) return { block: true, reason: `${cleanReason}\n(confirmation cancelled)` };
        const inputSnapshot = JSON.stringify(event.input);
        const choice = await ctx.ui.select(
          `harness confirmation:\n\n${cleanReason}\n\nTool: ${event.toolName}\nArguments: ${inputSnapshot}\n\nAllow this call?`,
          ["Allow once", "Block"],
          { timeout: GUARDRAILS_CONFIRM_TIMEOUT_MS, signal: ctx.signal },
        );
        if (ctx.signal?.aborted) return { block: true, reason: `${cleanReason}\n(confirmation cancelled)` };
        if (choice === "Allow once") {
          if (writeApproval) {
            const changed = await recheckHarnessWriteApproval(writeApproval, () => event.input, ctx.signal);
            if (changed) return { block: true, reason: changed };
          }
          const current = resolveHarnessConfig(cwd).config;
          if (JSON.stringify(current) !== JSON.stringify(config) || JSON.stringify(event.input) !== inputSnapshot) return { block: true, reason: "Harness configuration or tool arguments changed during confirmation; retry for fresh evaluation." };
          pi.appendEntry("harness-event", {
            kind: "policy-matched",
            policy: bashEval.matchedRules.map((r) => r.id).join(", "),
            action: "confirm",
            tool: event.toolName,
            reason: cleanReason,
            outcome: "allowed once",
            source,
            file,
          });
          if (flat?.messages.length) {
            pendingBashMessages.set(event.toolCallId, flat.matchedRules.map((r) => ({ id: r.id, message: r.message })));
          }
          return await finalizeAuthoring();
        }

        const timedOut = choice === undefined;
        const outcome = timedOut ? "blocked: confirmation timed out" : "blocked by user choice";
        pi.appendEntry("harness-event", {
          kind: "policy-matched",
          policy: bashEval.matchedRules.map((r) => r.id).join(", "),
          action: "confirm",
          tool: event.toolName,
          reason: cleanReason,
          outcome,
          source,
          file,
        });
        return {
          block: true,
          reason: `${cleanReason}\n(${outcome})`,
        };
      }

      // decision === "execute"
      if (flat?.messages.length) {
        pendingBashMessages.set(event.toolCallId, flat.matchedRules.map((r) => ({ id: r.id, message: r.message })));
      }
    }

    if (writeApproval) {
      const changed = await recheckHarnessWriteApproval(writeApproval, () => event.input, ctx.signal);
      if (changed) return { block: true, reason: changed };
    }
    return await finalizeAuthoring();
  });

  pi.on("tool_result", async (event, ctx) => {
    if (event.toolName === "write" && !event.isError && typeof event.input.path === "string") {
      const cwd = ctx.cwd || process.cwd();
      const targetPath = harnessTargetPath(event.input.path, cwd);
      if (Object.values(configPaths(cwd)).some(file => path.resolve(file) === targetPath)) {
        const availableSkills = new Set(pi.getCommands().filter(command => command.source === "skill").map(command => command.name.replace(/^skill:/, "")));
        const remaining = incompleteActivationNotice(resolveHarnessConfig(cwd, undefined, availableSkills).config);
        if (remaining) return { content: [...event.content, { type: "text", text: `${HARNESS_CONFIG_NOTE_PREFIX}\n${remaining}` }] };
      }
    }
    if (event.toolName === "bash") {
      const pending = pendingBashMessages.get(event.toolCallId);
      if (pending && pending.length > 0) {
        pendingBashMessages.delete(event.toolCallId);
        // Separate, identifiable part carrying each rule id. Native output blocks
        // stay intact; the sentinel prefix keeps the text scanner from treating
        // this Harness note as conversation content (no self-trigger).
        const note = `${HARNESS_BASH_NOTE_PREFIX}\n${pending.map((p) => `[harness:${p.id}] ${p.message}`).join("\n")}`;
        const content = Array.isArray(event.content) ? [...event.content] : [];
        content.push({ type: "text", text: note });
        return { content };
      }
    }
    return undefined;
  });

  pi.registerCommand("harness", {
    description: "Manage Harness rules or describe a rule request (default: project shared; --local/--global supported)",
    handler: async (rawArgs, ctx) => {
      const cwd = ctx.cwd || process.cwd();
      const { request, targetFile, scope, scopeLabel } = resolveHarnessTarget(rawArgs, cwd);
      if (request) {
        let targetState: "absent" | "existing";
        try {
          await assertHarnessTargetContained(targetFile, scope === "user" ? undefined : cwd);
          targetState = await readHarnessTarget(targetFile) === null ? "absent" : "existing";
        } catch (error) {
          notifyPi(ctx.ui, `Cannot prepare harness target: ${(error as Error).message}`, "error");
          return;
        }
        const availableSkills = pi.getCommands()
          .filter((command) => command.source === "skill")
          .map((command) => command.name.replace(/^skill:/, ""));
        startRuleProcedure(request, targetFile, scopeLabel, availableSkills, targetState, cwd, harnessCommandExamples(request, ctx));
        return;
      }
      const availableSkills = new Set(pi.getCommands().filter(command => command.source === 'skill').map(command => command.name.replace(/^skill:/, '')));
      const { config, paths } = resolveHarnessConfig(cwd, undefined, availableSkills);
      if (ctx.hasUI) {
        await runHarnessMenu(ctx.ui, config, paths, async ({ request: menuRequest, scope: menuScope }: { request: string; scope: HarnessMenuScope }) => {
          const scopeArg = menuScope === "user" ? "--global" : menuScope === "project.local" ? "--local" : "";
          const target = resolveHarnessTarget(scopeArg, cwd);
          let targetState: "absent" | "existing";
          try {
            await assertHarnessTargetContained(target.targetFile, target.scope === "user" ? undefined : cwd);
            targetState = await readHarnessTarget(target.targetFile) === null ? "absent" : "existing";
          } catch (error) {
            notifyPi(ctx.ui, `Cannot prepare harness target: ${(error as Error).message}`, "error");
            return;
          }
          const skills = pi.getCommands()
            .filter((command) => command.source === "skill")
            .map((command) => command.name.replace(/^skill:/, ""));
          startRuleProcedure(menuRequest, target.targetFile, target.scopeLabel, skills, targetState, cwd, harnessCommandExamples(menuRequest, ctx));
        }, ctx.mode);
        return;
      }
      const describe = (r: (typeof config.rules)[number]): string => {
        const selector = "skill" in r ? `skill:${r.skill}` : "bash" in r ? "bash" : "text" in r ? "text" : "(disabled)";
        const action = "bash" in r ? ` action:${r.action ?? "pass+message"}` : "";
        const state = r.enabled === false ? " disabled" : "";
        return `  - ${r.id} [${selector}]${action}${state} (source: ${r.source ?? "built-in"})`;
      };
      const lines: string[] = [
        `rules (${config.rules.length}):`,
        ...(config.rules.length ? config.rules.map(describe) : ["  (none)"]),
      ];
      if (config.notices.length) lines.push("compatibility notices:", ...config.notices.map(notice => `  - ${notice}`));
      if (config.legacy.policies.length) lines.push("read-only legacy policies:", ...config.legacy.policies.map(policy => `  - ${policy.name} [${policy.phase}] action:${policy.action} (source: ${policy.source})`));
      if (Object.keys(config.legacy.skillPrompts).length) lines.push("read-only legacy skill prompts:", ...Object.entries(config.legacy.skillPrompts).map(([name, prompt]) => `  - ${name} target:${prompt.target} (source: ${prompt.source})`));
      if (config.legacy.invalidPolicies.length) lines.push("invalid legacy policies: affected scopes remain unverified; unknown scopes hold tools pending repair. Exact config diagnosis/validated repair bypasses incomplete coverage, not valid matching protection");
      if (config.invalidRules.length) {
        lines.push(`invalid rules (${config.invalidRules.length}):`);
        for (const inv of config.invalidRules.slice(0, 5)) {
          lines.push(`  - ${inv.id} (source: ${inv.source}): ${inv.errors[0] ?? "invalid"}`);
        }
      }
      if (!config.bashEvaluationComplete) {
        lines.push("bash evaluation incomplete: an invalid bash-scoped or ambiguous rule holds matching bash calls until repaired");
      }
      if (config.configReadIncomplete) {
        lines.push("config read incomplete: a layer used its previous valid snapshot or failed to read; missing rules are indeterminate, not removed");
        for (const issue of harnessReadIssueLines(config.layerReadIssues, paths)) lines.push(`  - ${issue}${config.layerReadIssues.find(entry => issue.startsWith(entry.source))?.unavailable ? " [execution held: no trustworthy snapshot]" : " [previous valid snapshot in use]"}`);
      }
      lines.push(
        "built-in defaults are active unless overridden by id",
        "config paths:",
        `  ${paths.user}`,
        `  ${paths.userScoped} (project-scoped personal)`,
        `  ${paths.project}`,
        `  ${paths.projectLocal} (optional)`,
      );
      if (config.errors.length) {
        lines.push(`errors (${config.errors.length}):`, ...config.errors.slice(0, 5).map((e) => `  - ${e}`));
      }
      notifyPi(ctx.ui, lines.join("\n"), "info");
    },
  });
}
