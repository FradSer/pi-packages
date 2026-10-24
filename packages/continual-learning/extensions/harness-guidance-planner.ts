/**
 * Pure text-guidance lifecycle planner.
 *
 * Scans retained conversation and plans scoped guidance for the next run.
 * Run-start mode reads non-context branch delivery records and contributes all
 * applicable guidance through structured sections. The default delta mode
 * remains available for pure lifecycle inspection. No mode injects context.
 */

import crypto from "node:crypto";
import { evaluateText } from "./guardrail-engine.ts";
import type { ResolvedHarnessConfig, Rule, TextRule } from "./guardrail-types.ts";

export const HARNESS_GUIDANCE_CUSTOM_TYPE = "harness-guidance";
/** Entry type for the retained guidance row the planner prepares. */
export const HARNESS_GUIDANCE_ENTRY_TYPE = "harness-guidance-event";
/** Entry type an earlier release persisted for the same row. Kept renderable so
 * existing session transcripts keep their guidance view. */
export const LEGACY_GUIDANCE_ENTRY_TYPE = "context-guidance-event";
/** Sentinel prefix for the model-visible note Harness attaches to a Bash tool
 * result. The text scanner excludes it so Harness output never self-triggers. */
export const HARNESS_BASH_NOTE_PREFIX = "[harness-bash-note]";
/** Write-result activation diagnostics are Harness-owned, not matching evidence. */
export const HARNESS_CONFIG_NOTE_PREFIX = "[harness-config-note]";

/** Bounded work for one text scan. A single catastrophic regex pattern is not
 * interruptible without a worker; these bounds cap volume and let the caller
 * report incomplete rather than silently claiming "no match". */
export const TEXT_SCAN_BUDGET = { maxSegments: 4000, maxChars: 2_000_000 } as const;

/** Remove the Harness-owned suffix when an adapter flattens result blocks into
 * one string. Keep any native text that preceded the suffix model-visible. */
function stripHarnessNote(text: string): string | undefined {
  const marker = /(?:^|\n)\[harness-(?:bash|config)-note\](?:\n|$)/;
  const match = marker.exec(text);
  if (!match) return text;
  const native = text.slice(0, match.index).trimEnd();
  return native || undefined;
}

export function isHarnessOwnedMessage(msg: unknown): boolean {
  if (!msg || typeof msg !== "object") return false;
  const customType = (msg as { customType?: unknown }).customType;
  return typeof customType === "string" && (customType.startsWith("harness-") || customType === "skill-prompt-guidance");
}

function collectStringLeaves(val: unknown): string[] {
  if (typeof val === "string") return [val];
  if (Array.isArray(val)) return val.flatMap(collectStringLeaves);
  if (val && typeof val === "object") {
    return Object.values(val as Record<string, unknown>).flatMap(collectStringLeaves);
  }
  return [];
}

/** Recognize conventional Harness targets, not arbitrary mentions in content. */
function harnessConfigPath(value: unknown): boolean {
  return typeof value === "string" && /(?:^|[/\\])\.pi[/\\](?:agent[/\\])?harness(?:\.local)?\.json$|(?:^|[/\\])\.pi[/\\]agent[/\\]harness[/\\][^/\\]+\.json$/.test(value);
}

/** Only a single cat of a configuration file is apparatus. Mixed commands
 * retain all of their ordinary command and result text. */
export function referencesHarnessConfig(value: unknown): boolean {
  if (typeof value !== "string") return false;
  const cat = /^\s*cat[ \t]+(?:--[ \t]+)?(?:"([^"\n]+)"|'([^'\n]+)'|([^\s;&|<>`$]+))[ \t]*$/.exec(value);
  if (!cat || cat[1] !== undefined && /[$`\\]/.test(cat[1])
    || cat[3] !== undefined && /[\\*?\[\]{}~"']/.test(cat[3])) return false;
  return harnessConfigPath(cat[1] ?? cat[2] ?? cat[3]);
}

/** Rule-layer configuration reads are identified before extraction so a result
 * is excluded by its own call identity rather than by guessing at its bytes. */
function harnessConfigToolCalls(messages: unknown[]): Map<string, string> {
  const calls = new Map<string, string>();
  const seen = new Set<string>();
  for (const raw of messages) {
    if (!raw || typeof raw !== "object") continue;
    const msg = raw as Record<string, unknown>;
    if (msg.role !== "assistant" || !Array.isArray(msg.content)) continue;
    for (const block of msg.content) {
      if (!block || typeof block !== "object") continue;
      const b = block as Record<string, unknown>;
      if (b.type !== "toolCall" || typeof b.id !== "string") continue;
      // Reused IDs cannot authenticate a result as configuration material.
      if (seen.has(b.id)) { calls.delete(b.id); continue; }
      seen.add(b.id);
      if (!b.arguments || typeof b.arguments !== "object") continue;
      const args = b.arguments as Record<string, unknown>;
      if (["read", "write", "edit"].includes(String(b.name)) && harnessConfigPath(args.path)
        || b.name === "bash" && referencesHarnessConfig(args.command)) calls.set(b.id, String(b.name));
    }
  }
  return calls;
}

/**
 * Extract model-visible text fragments from a retained conversation snapshot.
 * Excludes Harness-owned guidance messages and appended Bash/config notes
 * (no self-trigger), Harness configuration apparatus (its own definition), and
 * thinking blocks, image binaries, and non-text metadata.
 */
export function extractModelVisibleTexts(messages: unknown[]): string[] {
  const texts: string[] = [];
  const configCalls = harnessConfigToolCalls(messages);
  for (const raw of messages) {
    if (!raw || typeof raw !== "object") continue;
    const msg = raw as Record<string, unknown>;
    if (isHarnessOwnedMessage(msg)) continue;

    const role = msg.role;
    const pushBlocks = (content: unknown, stripHarnessNotes = false) => {
      if (typeof content === "string") {
        // Pi normally represents tool results as content blocks, but adapters
        // and older sessions may retain a plain string.  Tool-result callers
        // opt into the Harness-note boundary so diagnostics cannot become
        // fresh text-rule evidence while user/custom text remains literal.
        const value = stripHarnessNotes ? stripHarnessNote(content) : content;
        if (value) texts.push(value);
      } else if (Array.isArray(content)) {
        for (const block of content) {
          if (!block || typeof block !== "object") continue;
          const b = block as Record<string, unknown>;
          if (b.type === "text" && typeof b.text === "string") {
            const value = stripHarnessNotes ? stripHarnessNote(b.text) : b.text;
            if (value) texts.push(value);
          }
        }
      }
    };

    if (role === "user" || role === "custom") {
      pushBlocks(msg.content);
    } else if (role === "assistant") {
      if (Array.isArray(msg.content)) {
        for (const block of msg.content) {
          if (!block || typeof block !== "object") continue;
          const b = block as Record<string, unknown>;
          if (b.type === "text" && typeof b.text === "string") texts.push(b.text);
          else if (b.type === "toolCall" && b.arguments && typeof b.arguments === "object"
            && !(typeof b.id === "string" && configCalls.has(b.id))) {
            texts.push(...collectStringLeaves(b.arguments));
          }
        }
      }
    } else if (role === "toolResult") {
      const configReader = configCalls.get(String(msg.toolCallId));
      if (msg.isError !== false || msg.toolName !== configReader || configReader !== "read" && configReader !== "bash") pushBlocks(msg.content, true);
    } else if (role === "compactionSummary" || role === "branchSummary") {
      if (typeof msg.summary === "string") texts.push(msg.summary);
    } else if (role === "bashExecution") {
      if (!msg.excludeFromContext && !(msg.exitCode === 0 && referencesHarnessConfig(msg.command))) {
        if (typeof msg.command === "string") texts.push(msg.command);
        if (typeof msg.output === "string") {
          const native = stripHarnessNote(msg.output);
          if (native) texts.push(native);
        }
      }
    }
  }
  return texts;
}

/** Delivery revision covers rule semantics and model-visible message format.
 * A format change refreshes retained guidance without rewriting history. */
export function hashRuleRevision(rule: Rule): string {
  let canonical: Record<string, unknown>;
  if ("skill" in rule) canonical = { k: "skill", skill: rule.skill, instructions: rule.instructions };
  else if ("bash" in rule) canonical = { k: "bash", bash: rule.bash, action: rule.action ?? null, message: rule.message };
  else if ("text" in rule) canonical = { k: "text", text: rule.text, instructions: rule.instructions };
  else canonical = { k: "disabled" };
  return crypto.createHash("sha256").update(JSON.stringify({ deliveryFormat: 2, id: rule.id, ...canonical })).digest("hex").slice(0, 16);
}

export type GuidanceStatus = "active" | "update" | "retired";

export interface TextGuidanceEntry {
  id: string;
  revision?: string;
  status: GuidanceStatus;
  /** Model-visible text for this entry. */
  text: string;
  /** Effective config layer that delivered this guidance. Optional for old sessions. */
  source?: string;
}

export interface TextGuidancePlan {
  /** New, updated, or retired entries to deliver on the next agent start. */
  entries: TextGuidanceEntry[];
  /** True when matching did not complete (budget) or the config read was
   * incomplete. Callers must preserve prior delivery state and report this
   * rather than treating it as "no match" or a confirmed retirement. */
  incomplete: boolean;
  preservationNotice?: string;
}

interface DeliveredState {
  text?: string;
  revision?: string;
  status: GuidanceStatus;
  source?: string;
}

function scopedTextGuidance(rule: TextRule): string {
  return `[harness:${rule.id}] Only for subjects matching ${JSON.stringify(rule.text)}; a historical match does not extend this guidance to unrelated tasks.\n${rule.instructions}`;
}

function readDeliveredState(messages: unknown[]): Map<string, DeliveredState> {
  const state = new Map<string, DeliveredState>();
  for (const raw of messages) {
    if (!raw || typeof raw !== "object") continue;
    const msg = raw as Record<string, unknown>;
    if (msg.customType !== HARNESS_GUIDANCE_CUSTOM_TYPE) continue;
    const details = msg.details as { entries?: Array<{ id?: string; text?: string; revision?: string; status?: GuidanceStatus; source?: string }> } | undefined;
    for (const e of details?.entries ?? []) {
      if (typeof e?.id !== "string") continue;
      // Last delivered state per id wins (messages are in branch order).
      state.set(e.id, { text: e.text, revision: e.revision, status: e.status ?? "active", source: e.source });
    }
  }
  return state;
}

/** Delivered state per rule id, read from branch order. Callers use it to
 * append a delivery record only when the state actually changed, so an
 * unchanged re-delivery neither grows the transcript nor the branch ledger. */
export function deliveredGuidanceState(messages: unknown[]): Map<string, { text?: string; revision?: string; status: GuidanceStatus; source?: string }> {
  return readDeliveredState(messages);
}

/** Admit only the exact scoped delivery format. A saved body alone cannot
 * establish its selector, and the current rule cannot scope an older revision.
 */
function hasCompleteTextScope(id: string, text: string | undefined): text is string {
  if (!text) return false;
  const prefix = `[harness:${id}] Only for subjects matching `;
  const suffix = "; a historical match does not extend this guidance to unrelated tasks.";
  const end = text.indexOf("\n");
  const header = text.slice(0, end);
  if (end < 0 || !text.slice(end + 1).trim() || !header.startsWith(prefix) || !header.endsWith(suffix)) return false;
  const encoded = header.slice(prefix.length, -suffix.length);
  try {
    const selector: unknown = JSON.parse(encoded);
    return typeof selector === "string" && selector.length > 0 && JSON.stringify(selector) === encoded;
  } catch { return false; }
}

/** Preserve complete scoped deliveries when a scan cannot establish new state. */
export function retainedTextGuidance(messages: unknown[]): TextGuidanceEntry[] {
  return [...readDeliveredState(messages)].flatMap(([id, state]) =>
    state.status !== "retired" && hasCompleteTextScope(id, state.text)
      ? [{ id, ...state, text: state.text, status: state.status }]
      : []);
}

export function incompleteTextGuidance(messages: unknown[]): TextGuidancePlan {
  const scopeUnavailable = [...readDeliveredState(messages)].some(([id, state]) =>
    state.status !== "retired" && !hasCompleteTextScope(id, state.text));
  return {
    entries: retainedTextGuidance(messages), incomplete: true,
    preservationNotice: scopeUnavailable
      ? "Prior guidance without a complete verified scope remains in history but is not delivered. Complete scoped guidance is preserved."
      : "Complete prior scoped guidance is preserved; matching or configuration is incomplete.",
  };
}

/**
 * Plan the text-guidance entries to deliver on the next agent start.
 * `retainedMessages` is the branch's model-visible conversation (compaction
 * applied); `currentPromptText` is the new user prompt that may not yet be in
 * the retained snapshot.
 */
export function planTextGuidance(
  retainedMessages: unknown[],
  currentPromptText: string,
  config: ResolvedHarnessConfig,
  runStart = false,
): TextGuidancePlan {
  const delivered = readDeliveredState(retainedMessages);
  const texts = [...extractModelVisibleTexts(retainedMessages), currentPromptText];
  const { matches, incomplete } = evaluateText(config, texts, TEXT_SCAN_BUDGET);

  // Indeterminate matching: preserve state, deliver nothing, report incomplete.
  if (incomplete || config.configReadIncomplete) return runStart
    ? incompleteTextGuidance(retainedMessages)
    : { entries: [], incomplete: true };

  const entries: TextGuidanceEntry[] = [];

  // 1. New or changed matches.
  for (const rule of matches) {
    const revision = hashRuleRevision(rule);
    const prior = delivered.get(rule.id);
    if (!prior || runStart) {
      entries.push({ id: rule.id, revision, status: "active", text: scopedTextGuidance(rule), source: rule.source });
    } else if (prior.status === "retired" || prior.revision !== revision) {
      const reactivation = prior.status === "retired";
      entries.push({
        id: rule.id,
        revision,
        status: reactivation ? "active" : "update",
        text: scopedTextGuidance(rule),
        source: rule.source,
      });
    }
    // Same revision, still active: already retained in place, no new copy.
  }

  // Retire removed/disabled guidance and outdated revisions that no longer
  // apply. An unchanged scoped delivery stays in retained history.
  const matchedIds = new Set(matches.map((rule) => rule.id));
  const configRuleById = new Map<string, Rule>();
  for (const r of config.rules) configRuleById.set(r.id, r);

  for (const [id, prior] of delivered) {
    if (prior.status === "retired") continue;
    const rule = configRuleById.get(id);
    const goneOrDisabled = !rule || rule.enabled === false;
    const outdatedUnmatched = rule && !matchedIds.has(id) &&
      (!("text" in rule) || prior.revision !== hashRuleRevision(rule));
    if (!goneOrDisabled && !outdatedUnmatched) {
      // Structured sections do not persist as custom context, so a rule that
      // still matches the retained conversation is re-delivered each turn. A
      // rule whose matching evidence has left the retained conversation is not:
      // its scope names the subjects the selector detects, and an expired
      // trigger cannot keep the guidance in force for unrelated tasks.
      continue;
    }
    // A vanished rule under an incomplete config read is indeterminate, not a
    // confirmed removal — do not emit a definitive retirement.
    if (config.configReadIncomplete) continue;
    entries.push({
      id,
      status: "retired",
      text: `[harness:${id} retired] The earlier guidance for this rule no longer applies to this task or reflects the current delivery.`,
      ...(prior.source === undefined ? {} : { source: prior.source }),
    });
  }

  return { entries, incomplete: false };
}
