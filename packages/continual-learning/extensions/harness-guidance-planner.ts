/**
 * Pure text-guidance lifecycle planner.
 *
 * Scans the model-visible retained conversation, decides which text-rule
 * guidance must be delivered on the NEXT agent start, and keeps delivery stable
 * for prefix caching: already-delivered guidance stays where it is, only new,
 * updated, or retired guidance is emitted as a fresh tail message.
 *
 * Delivery itself is a persistent before_agent_start message (durable, retained
 * on the branch). This planner is pure application logic with no Pi imports.
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

/**
 * Extract model-visible text fragments from a retained conversation snapshot.
 * Excludes Harness-owned guidance messages and appended Bash/config notes
 * (no self-trigger), thinking blocks, image binaries, and non-text metadata.
 */
export function extractModelVisibleTexts(messages: unknown[]): string[] {
  const texts: string[] = [];
  for (const raw of messages) {
    if (!raw || typeof raw !== "object") continue;
    const msg = raw as Record<string, unknown>;
    if (isHarnessOwnedMessage(msg)) continue;

    const role = msg.role;
    const pushBlocks = (content: unknown) => {
      if (typeof content === "string") {
        texts.push(content);
      } else if (Array.isArray(content)) {
        for (const block of content) {
          if (!block || typeof block !== "object") continue;
          const b = block as Record<string, unknown>;
          if (b.type === "text" && typeof b.text === "string") {
            if (b.text.startsWith(HARNESS_BASH_NOTE_PREFIX) || b.text.startsWith(HARNESS_CONFIG_NOTE_PREFIX)) continue;
            texts.push(b.text);
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
          else if (b.type === "toolCall" && b.arguments && typeof b.arguments === "object") {
            texts.push(...collectStringLeaves(b.arguments));
          }
        }
      }
    } else if (role === "toolResult") {
      pushBlocks(msg.content);
    } else if (role === "compactionSummary" || role === "branchSummary") {
      if (typeof msg.summary === "string") texts.push(msg.summary);
    } else if (role === "bashExecution") {
      if (!msg.excludeFromContext) {
        if (typeof msg.command === "string") texts.push(msg.command);
        if (typeof msg.output === "string" && !msg.output.startsWith(HARNESS_BASH_NOTE_PREFIX)) texts.push(msg.output);
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
}

export interface TextGuidancePlan {
  /** New, updated, or retired entries to deliver on the next agent start. */
  entries: TextGuidanceEntry[];
  /** True when matching did not complete (budget) or the config read was
   * incomplete. Callers must preserve prior delivery state and report this
   * rather than treating it as "no match" or a confirmed retirement. */
  incomplete: boolean;
}

interface DeliveredState {
  revision?: string;
  status: GuidanceStatus;
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
    const details = msg.details as { entries?: Array<{ id?: string; revision?: string; status?: GuidanceStatus }> } | undefined;
    for (const e of details?.entries ?? []) {
      if (typeof e?.id !== "string") continue;
      // Last delivered state per id wins (messages are in branch order).
      state.set(e.id, { revision: e.revision, status: e.status ?? "active" });
    }
  }
  return state;
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
): TextGuidancePlan {
  const delivered = readDeliveredState(retainedMessages);
  const texts = [...extractModelVisibleTexts(retainedMessages), currentPromptText];
  const { matches, incomplete } = evaluateText(config, texts, TEXT_SCAN_BUDGET);

  // Indeterminate matching: preserve state, deliver nothing, report incomplete.
  if (incomplete) return { entries: [], incomplete: true };

  const entries: TextGuidanceEntry[] = [];

  // 1. New or changed matches.
  for (const rule of matches) {
    const revision = hashRuleRevision(rule);
    const prior = delivered.get(rule.id);
    if (!prior) {
      entries.push({ id: rule.id, revision, status: "active", text: scopedTextGuidance(rule) });
    } else if (prior.status === "retired" || prior.revision !== revision) {
      const reactivation = prior.status === "retired";
      entries.push({
        id: rule.id,
        revision,
        status: reactivation ? "active" : "update",
        text: scopedTextGuidance(rule),
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
    if (!goneOrDisabled && !outdatedUnmatched) continue;
    // A vanished rule under an incomplete config read is indeterminate, not a
    // confirmed removal — do not emit a definitive retirement.
    if (config.configReadIncomplete) continue;
    entries.push({
      id,
      status: "retired",
      text: `[harness:${id} retired] The earlier guidance for this rule no longer applies to this task or reflects the current delivery.`,
    });
  }

  return { entries, incomplete: false };
}
