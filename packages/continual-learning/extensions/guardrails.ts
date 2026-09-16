/**
 * Guardrails — the harness surface of continual learning: declarative
 * tool-call policies and flat rules that evolve through layered JSON config.
 *
 * Rules live in user-shared ~/.pi/agent/harness.json, project-shared
 * <project>/.pi/harness.json, and project-personal harness.local.json. Curated defaults ship with the
 * package and can be overridden by id from any layer.
 */

import fs from "node:fs";
import type { Stats } from "node:fs";
import path from "node:path";
import { isDeepStrictEqual } from "node:util";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";
import { keyHint, ToolExecutionComponent, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import { bindLifecycleRenderers, eventToolLifecycle, fieldBlock, fieldLine, notifyPi, safeDisplayText } from "@fradser/pi-kit";

/** Geometry bound once: every guardrail row shares hint and wrapping. */
const guardrailRows = bindLifecycleRenderers({
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
  hostComponent: ToolExecutionComponent,
});
import {
  evaluate,
  evaluateBash,
  validatePolicyDeclaration,
  validateRuleDeclaration,
  validateSkillPromptDeclaration,
} from "./guardrail-engine.ts";
import { configPaths, resolveHarnessConfig } from "./guardrail-config.ts";
import { HARNESS_BASH_NOTE_PREFIX } from "./harness-guidance-planner.ts";

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

// Pi 0.84 exposes no native path resolver; keep this gate-local normalization
// covered against createWriteTool rather than loading private runtime modules.
function harnessTargetPath(input: string, cwd: string): string {
  let target = input.replace(/[\u00A0\u2000-\u200A\u202F\u205F\u3000]/g, " ").replace(/^@/, "");
  if (process.platform === "win32" && target.startsWith("/") && !target.startsWith("//") && !target.includes("\\")) {
    const drive = target.match(/^\/(?:mnt\/|cygdrive\/)?([a-z])(?:\/(.*))?$/i);
    if (drive) target = `${drive[1].toUpperCase()}:\\${drive[2]?.replaceAll("/", "\\") ?? ""}`;
  }
  if (target === "~") target = homedir();
  else if (target.startsWith("~/") || (process.platform === "win32" && target.startsWith("~\\"))) target = path.join(homedir(), target.slice(2));
  else if (target.startsWith("file://")) target = fileURLToPath(target);
  return path.resolve(cwd, target);
}

function harnessSourcePath(source: string | undefined, paths: ReturnType<typeof configPaths>): string {
  switch (source) {
    case "user":
      return paths.user;
    case "project":
      return paths.project;
    case "project.local":
      return paths.projectLocal;
    default:
      return "(built-in)";
  }
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

export async function ensureHarnessTarget(targetFile: string, workspace?: string): Promise<{ path: string; created: boolean }> {
  await assertHarnessTargetContained(targetFile, workspace);
  const existing = await readHarnessTarget(targetFile);
  if (existing) return { path: targetFile, created: false };

  await fs.promises.mkdir(path.dirname(targetFile), { recursive: true });
  await assertHarnessTargetContained(targetFile, workspace);
  const initial = `${JSON.stringify({ rules: [] }, null, 2)}\n`;
  let handle: fs.promises.FileHandle | undefined;
  let created = false;
  try {
    handle = await fs.promises.open(targetFile, "wx", 0o600);
    await handle.writeFile(initial, "utf8");
    await handle.sync();
    created = true;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
  } finally {
    await handle?.close().catch(() => {});
  }

  const verified = await readHarnessTarget(targetFile);
  if (!verified) throw new Error(`Harness target could not be read after initialization: ${targetFile}`);
  try {
    const parsed = JSON.parse(verified.toString("utf8")) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error(`Harness target is not a JSON object: ${targetFile}`);
    }
  } catch (error) {
    throw new Error(`Harness target could not be verified: ${(error as Error).message}`);
  }
  return { path: targetFile, created };
}

export const ensureGlobalHarnessTarget = ensureHarnessTarget;

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

export function buildHarnessRulePrompt(request: string, targetFile: string, scopeLabel?: string, availableSkills: readonly string[] = []): string {
  const label = scopeLabel ?? (targetFile.endsWith("harness.local.json") ? "personal harness.local.json" : "harness.json");
  const skillRegistry = availableSkills.length ? availableSkills.join(", ") : "(none registered in this session)";
  return [
    "Create or update one Pi harness rule from the user's request below. Complete this as an explicit write task.",
    "",
    `User request: ${request}`,
    "",
    "Global configuration uses ~/.pi/agent/harness.json (honoring PI_CODING_AGENT_DIR). Authoring defaults to the project shared .pi/harness.json; .pi/harness.local.json is an explicit personal choice.",
    "Required creation protocol:",
    `- Work exclusively in ${targetFile}, the ${label}; preserve other harness files, memory, and unrelated files unchanged.`,
    `- Treat ${targetFile} as authoritative and read it directly; keep all target access on this supplied path.`,
    `- Execute this exact sequence: read ${targetFile} directly; if it is missing, immediately call the write tool with path=${targetFile}; then read ${targetFile} again to verify it.`,
    `- If ${targetFile} returns ENOENT, create it at that exact path instead of searching elsewhere. The write tool creates missing parent directories.`,
    `- For a missing target, write this complete initial JSON object before adding the requested rule: {"rules":[]}.`,
    "- Preserve every existing rule, and make the smallest change that satisfies the request.",
    "- If existing entries are invalid or unknown, report the diagnostics and leave the file unchanged unless explicit user authorization permits repairing or removing those entries. Retain those entries intact until authorized repairs produce valid data.",
    "- Preserve the user's semantic boundary: fullscreen popup means an overlay relationship. Ask before adding opacity, input, or scroll restrictions; clarify ambiguous requirements.",
    "- Choose the entry that matches the lesson's real scope. A project-wide working convention belongs in the project AGENTS.md; a skill-workflow supplement belongs in a skill rule; a keyword-triggered project fact belongs in a text rule; a command-time check belongs in a bash rule.",
    `- The configuration is a flat "rules" array. Each rule carries a stable descriptive "id" and exactly one selector. Registered skill names for this session (the only valid "skill" values): ${skillRegistry}`,
    `- A skill rule is {"id","skill":<exact registered skill name>,"instructions":<affirmative guidance>}. It applies on that exact expanded skill invocation, not a plain read of SKILL.md; it is contextual guidance, not global interception or guaranteed project-wide semantic enforcement.`,
    `- A bash rule is {"id","bash":<regex over the command text>,"message":<affirmative guidance>} with an optional "action" of "confirm" or "block". Omit "action" to execute the command and deliver the message to the model with the real result; use "confirm" to require one approval for that call; use "block" to hold the call and return the message.`,
    `- A text rule is {"id","text":<regex over the retained conversation>,"instructions":<affirmative guidance>}. It is delivered as retained context when the pattern matches the model-visible conversation.`,
    "- Resolve an unknown skill name against this registry before writing. When no supported entry can represent the lesson safely, report the limitation and preserve existing rules unchanged; this safety exception takes precedence over performing a rule change, and the exact target creation protocol stays unchanged.",
    "- Generalize project lessons through evidence -> reusable error class -> supported mechanism. Describe the behavior to preserve or prevent before choosing a selector.",
    "- Treat incident document tokens, row numbers, or verbatim phrases as evidence for reusable rule boundaries. Retain resource identifiers only for an explicit resource-specific user requirement; distinguish the authoritative harness output path from the resources a rule governs.",
    "- Transfer-test the candidate against another same-kind document and a rephrasing of the same mistake, and verify unrelated actions remain allowed. Generalize the error class while keeping confirmation scoped to the requested action surface.",
    "- Same \"id\" in a nearer layer replaces the whole rule; a rule stays enabled unless it sets \"enabled\": false. Validate each regex before writing.",
    "- Verify persistence by reading the JSON back; separately trigger-test the exact expanded skill invocation or a matching bash command, or report that the runtime trigger was not verified. Reading the file back proves persistence only.",
    `- Write the complete valid JSON back to ${targetFile}, then read that same path back and verify the resulting structure and behavior.`,
    "- If the request is ambiguous or cannot be represented safely, explain the issue instead of guessing or changing a different file.",
    "- Perform the supported change and report the exact rule id, file changed, and verification outcome.",
  ].join("\n");
}

export function validateHarnessWrite(input: unknown, availableSkills: ReadonlySet<string>, previous?: unknown): string[] {
  if (!input || typeof input !== "object" || Array.isArray(input)) return ["harness write input must be an object"];
  const value = input as Record<string, unknown>;
  const parsed = value.content;
  if (typeof parsed !== "string") return ["harness write content must be JSON text"];
  let json: unknown;
  try { json = JSON.parse(parsed); } catch { return ["harness write content must be valid JSON"]; }
  if (!json || typeof json !== "object" || Array.isArray(json)) return ["harness config must be an object"];
  const config = json as Record<string, unknown>;
  const prior = previous && typeof previous === "object" && !Array.isArray(previous)
    ? previous as Record<string, unknown>
    : {};
  const errors: string[] = [];

  // If new flat rules array is present
  if (Array.isArray(config.rules)) {
    const seen = new Set<string>();
    config.rules.forEach((rule, index) => {
      const id = rule && typeof rule === "object" && typeof (rule as Record<string, unknown>).id === "string"
        ? ((rule as Record<string, unknown>).id as string).trim()
        : undefined;
      if (id) {
        if (seen.has(id)) {
          errors.push(`rules[${index}] duplicate rule id "${id}"`);
        }
        seen.add(id);
      }
      errors.push(...validateRuleDeclaration(rule, availableSkills).map((error) => `rules[${index}] ${error}`));
    });

    const supported = new Set(["rules"]);
    // Migrating from the legacy format drops these containers on purpose; that
    // is the authorized replacement, not a lost unrelated field.
    const legacyHarnessFields = new Set(["policies", "disabled", "skillPrompts"]);
    for (const [name, entry] of Object.entries(config)) {
      if (supported.has(name)) continue;
      if (!Object.prototype.hasOwnProperty.call(prior, name)) {
        errors.push(`unsupported top-level field "${name}" cannot be added by a harness write`);
      } else if (!isDeepStrictEqual(prior[name], entry)) {
        errors.push(`pre-existing top-level field "${name}" must be preserved unchanged`);
      }
    }
    for (const name of Object.keys(prior)) {
      if (supported.has(name) || legacyHarnessFields.has(name)) continue;
      if (!Object.prototype.hasOwnProperty.call(config, name)) {
        errors.push(`pre-existing top-level field "${name}" must be preserved unchanged`);
      }
    }
    return errors;
  }

  // Legacy validation for backward compatibility during migration
  if (!Array.isArray(config.policies)) {
    errors.push("policies must be an array");
  } else {
    config.policies.forEach((policy, index) => {
      errors.push(...validatePolicyDeclaration(policy).map((error) => `policies[${index}] ${error}`));
    });
  }

  if (!Array.isArray(config.disabled)) {
    errors.push("disabled must be an array");
  } else {
    config.disabled.forEach((name, index) => {
      if (typeof name !== "string" || !name.trim()) errors.push(`disabled[${index}] must be a non-empty policy name string`);
    });
  }

  if (!config.skillPrompts || typeof config.skillPrompts !== "object" || Array.isArray(config.skillPrompts)) {
    errors.push("skillPrompts must be an object");
  } else {
    for (const [name, entry] of Object.entries(config.skillPrompts)) {
      errors.push(...validateSkillPromptDeclaration(name, entry, availableSkills));
    }
  }

  const supported = new Set(["policies", "disabled", "skillPrompts"]);
  for (const [name, entry] of Object.entries(config)) {
    if (supported.has(name)) continue;
    if (!Object.prototype.hasOwnProperty.call(prior, name)) {
      errors.push(`unsupported top-level field "${name}" cannot be added by a harness write`);
    } else if (!isDeepStrictEqual(prior[name], entry)) {
      errors.push(`pre-existing top-level field "${name}" must be preserved unchanged`);
    }
  }
  for (const name of Object.keys(prior)) {
    if (!supported.has(name) && !Object.prototype.hasOwnProperty.call(config, name)) {
      errors.push(`pre-existing top-level field "${name}" must be preserved unchanged`);
    }
  }
  return errors;
}

/** The confirm gate blocks the agent loop while its dialog waits, so an
 * unattended session must fail closed after a bounded wait instead of
 * hanging. pi renders the remaining time as a live countdown. */
const GUARDRAILS_CONFIRM_TIMEOUT_MS = 60_000;

export default function registerGuardrails(pi: ExtensionAPI) {
  const pendingBashMessages = new Map<string, Array<{ id: string; message: string }>>();

  pi.registerEntryRenderer("harness-event", (entry, { expanded }, theme) => {
    const details = entry.data as HarnessEventData | undefined;
    if (details?.kind === "policy-matched") {
      const reason = safeDisplayText(details.reason);
      const label = details.action === "observe"
        ? "policy observed"
        : details.action === "confirm" && details.outcome === "allowed once"
          ? "policy allowed"
          : "policy blocked";
      return guardrailRows.message(() => eventToolLifecycle("harness", reason, {
        label,
        details: [
          fieldLine("policy", details.policy),
          fieldLine("action", details.action),
          fieldLine("outcome", details.outcome),
          fieldLine("tool", details.tool),
          fieldLine("source", details.source),
          fieldLine("file", details.file),
          ...fieldBlock("reason", reason),
        ],
      }))({ content: "", details }, { expanded }, theme);
    }
    const message = "harness policy event";
    return guardrailRows.message(() => eventToolLifecycle("harness", message, { label: "event" }))({ content: "", details }, { expanded }, theme);
  });

  pi.on("tool_call", async (event, ctx) => {
    const cwd = ctx.cwd || process.cwd();
    const { config, paths } = resolveHarnessConfig(cwd);
    if (event.toolName === "write" || event.toolName === "edit") {
      const input = (event.input ?? {}) as Record<string, unknown>;
      const target = typeof input.path === "string" ? input.path : "";
      const targetPath = harnessTargetPath(target, cwd);
      if (targetPath === path.join(path.dirname(paths.user), "harness.local.json")) {
        return { block: true, reason: "Use ~/.pi/agent/harness.json for global configuration. Project shared .pi/harness.json is the default; select .pi/harness.local.json for explicitly requested personal configuration." };
      }
      const harnessPaths = new Set(Object.values(paths).map((file) => path.resolve(file)));
      if (harnessPaths.has(targetPath)) {
        if (event.toolName === "edit") return { block: true, reason: "Harness configuration requires a complete validated JSON write. Read the target, preserve its entries, and use write instead of edit." };
        try {
          await assertHarnessTargetContained(targetPath, targetPath === path.resolve(paths.user) ? undefined : cwd);
        } catch (error) {
          return { block: true, reason: `Unsafe harness target: ${(error as Error).message}` };
        }
        const availableSkills = new Set(pi.getCommands().filter((command) => command.source === "skill").map((command) => command.name.replace(/^skill:/, "")));
        let previous: unknown;
        try { previous = JSON.parse(fs.readFileSync(targetPath, "utf8")); } catch { /* new target or malformed predecessor */ }
        const errors = validateHarnessWrite(input, availableSkills, previous);
        if (errors.length) return { block: true, reason: `Invalid harness configuration: ${errors.join("; ")}. The file was not written. Report existing invalid entries; obtain explicit user authorization before repairing or removing them.` };
      }
    }

    // New bash rule evaluation
    if (event.toolName === "bash" && config.rules && config.rules.length > 0) {
      const command = typeof (event.input as Record<string, unknown>)?.command === "string"
        ? (event.input as Record<string, unknown>).command as string
        : "";
      const bashEval = evaluateBash(config, command);

      if (bashEval.decision === "incomplete") {
        pi.appendEntry("harness-event", {
          kind: "policy-matched",
          policy: (bashEval.incompleteRuleIds ?? []).join(", ") || "(unidentified)",
          action: "block",
          tool: event.toolName,
          reason: bashEval.reason ?? "Bash evaluation incomplete",
          outcome: "blocked by rule",
          source: "unknown",
          file: harnessSourcePath(undefined, paths),
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

        const choice = await ctx.ui.select(
          `harness confirmation:\n\n${cleanReason}\n\nCommand: ${command}\n\nAllow this call?`,
          ["Allow once", "Block"],
          { timeout: GUARDRAILS_CONFIRM_TIMEOUT_MS },
        );
        if (choice === "Allow once") {
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
          if (bashEval.messages.length > 0) {
            pendingBashMessages.set(event.toolCallId, bashEval.matchedRules.map((r) => ({ id: r.id, message: r.message })));
          }
          return undefined;
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
      if (bashEval.messages.length > 0) {
        pendingBashMessages.set(event.toolCallId, bashEval.matchedRules.map((r) => ({ id: r.id, message: r.message })));
      }
    }

    // Legacy policy evaluation
    const decision = evaluate(config, {
      toolName: event.toolName,
      args: (event.input ?? {}) as Record<string, unknown>,
    });
    if (!decision) return undefined;

    const source = decision.source ?? "unknown";
    const file = harnessSourcePath(decision.source, paths);
    const cleanReason = decision.cleanReason ?? decision.reason;

    if (decision.action === "observe") {
      pi.appendEntry("harness-event", {
        kind: "policy-matched",
        policy: decision.policyName,
        action: "observe",
        tool: event.toolName,
        reason: cleanReason,
        outcome: "observed",
        source,
        file,
      });
      return undefined;
    }

    if (decision.action === "confirm") {
      if (!ctx.hasUI) {
        pi.appendEntry("harness-event", {
          kind: "policy-matched",
          policy: decision.policyName,
          action: "confirm",
          tool: event.toolName,
          reason: cleanReason,
          outcome: "no UI available to confirm",
          source,
          file,
        });
        return { block: true, reason: `${decision.reason}\n(no UI available to confirm)` };
      }
      const choice = await ctx.ui.select(
        `harness: ${decision.policyName}\n\n${cleanReason}\n\nAllow this call?`,
        ["Allow once", "Block"],
        { timeout: GUARDRAILS_CONFIRM_TIMEOUT_MS },
      );
      if (choice === "Allow once") {
        pi.appendEntry("harness-event", {
          kind: "policy-matched",
          policy: decision.policyName,
          action: "confirm",
          tool: event.toolName,
          reason: cleanReason,
          outcome: "allowed once",
          source,
          file,
        });
        return undefined;
      }
      const timedOut = choice === undefined;
      const outcome = timedOut ? "blocked: confirmation timed out" : "blocked by user choice";
      pi.appendEntry("harness-event", {
        kind: "policy-matched",
        policy: decision.policyName,
        action: "confirm",
        tool: event.toolName,
        reason: cleanReason,
        outcome,
        source,
        file,
      });
      return {
        block: true,
        reason: `${decision.reason}\n(${outcome})`,
      };
    }

    pi.appendEntry("harness-event", {
      kind: "policy-matched",
      policy: decision.policyName,
      action: "block",
      tool: event.toolName,
      reason: cleanReason,
      outcome: "blocked by rule",
      source,
      file,
    });
    return { block: true, reason: decision.reason };
  });

  pi.on("tool_result", async (event) => {
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
    description: "Show active guardrails or create a rule from a prompt (default: project .pi/harness.json, --local for personal, --global for user)",
    handler: async (rawArgs, ctx) => {
      const cwd = ctx.cwd || process.cwd();
      const { request, targetFile, scope, scopeLabel } = resolveHarnessTarget(rawArgs, cwd);
      if (request) {
        try {
          await ensureHarnessTarget(targetFile, scope === "user" ? undefined : cwd);
        } catch (error) {
          notifyPi(ctx.ui, `Cannot prepare harness target: ${(error as Error).message}`, "error");
          return;
        }
        const availableSkills = pi.getCommands()
          .filter((command) => command.source === "skill")
          .map((command) => command.name.replace(/^skill:/, ""));
        pi.sendUserMessage(buildHarnessRulePrompt(request, targetFile, scopeLabel, availableSkills), { deliverAs: "followUp" });
        return;
      }
      const availableSkills = new Set(pi.getCommands().filter(command => command.source === 'skill').map(command => command.name.replace(/^skill:/, '')));
      const { config, paths } = resolveHarnessConfig(cwd, undefined, availableSkills);
      const DEFAULT_IDS = new Set(["no-bulk-memory-deletion", "no-interactive-auth-automation", "no-otp-in-chat"]);
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
      }
      const legacySkills = config.skillPrompts ? Object.keys(config.skillPrompts) : [];
      const legacyPolicies = (config.policies ?? []).map((p) => p.name).filter((n) => !DEFAULT_IDS.has(n));
      if (legacySkills.length) {
        const active = legacySkills.filter((name) => availableSkills.has(name));
        const inactive = legacySkills.filter((name) => !availableSkills.has(name));
        lines.push(`legacy skill prompts (registered; trigger not verified): ${active.join(", ") || "(none)"}`);
        if (inactive.length) lines.push(`legacy skill prompts (no registered skill): ${inactive.join(", ")}`);
      }
      if (legacyPolicies.length) lines.push(`legacy policies: ${legacyPolicies.join(", ")}`);
      lines.push(
        "built-in defaults are active unless overridden by id",
        "config paths:",
        `  ${paths.user}`,
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
