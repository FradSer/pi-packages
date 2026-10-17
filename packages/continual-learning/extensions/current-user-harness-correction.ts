/** Early nomination only: ordinary validation and semantic review own authority. */
import { isDeepStrictEqual } from "node:util";
import { ruleRevision } from "./guardrail-engine";
const CORRECTION = /\b(?:correct(?:ion|ed)?|replace|retire|revoke|no longer)\b|纠正|更正|修正|退役|撤销|废弃|替换/iu;
const LASTING = /\b(?:permanent(?:ly)?|lasting|durable|from now on|for future)\b|永久|以后|今后|持久/iu;

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function currentUserCorrectionEntry(entries: readonly unknown[], prompt: string): Record<string, unknown> | undefined {
  const entry = [...entries].reverse().find(value => record(value) && record(value.message) && value.message.role === "user");
  if (!record(entry) || entry.type !== "message" || typeof entry.id !== "string" || !entry.id || !record(entry.message)) return;
  const content = entry.message.content;
  // Images, reconstructed text and extension continuations cannot supply this
  // early path. The normal settled-task learner still sees complete evidence.
  const text = typeof content === "string" ? content
    : Array.isArray(content) && content.length === 1 && record(content[0]) && content[0].type === "text" ? content[0].text : undefined;
  if (typeof text !== "string" || text !== prompt || !CORRECTION.test(text) || !LASTING.test(text)) return;
  return entry;
}

/** Never trim a mixed plan to obtain an admissible subset. */
export function ownedCorrectionPlan(plan: unknown, revisions: Readonly<Record<string, string>>): boolean {
  if (!record(plan) || !Array.isArray(plan.operations)) return false;
  return plan.operations.every(operation => record(operation) && operation.op === "updateRule"
    && record(operation.rule) && typeof operation.rule.id === "string"
    && Object.hasOwn(revisions, operation.rule.id) && record(operation.correction)
    && operation.correction.eventIndex === 0
    && operation.correction.priorRevision === revisions[operation.rule.id]);
}

function ownedRules(config: unknown): Record<string, unknown>[] {
  if (!record(config) || !record(config.learnedRules) || !Array.isArray(config.rules)) return [];
  const markers = config.learnedRules;
  return config.rules.filter((rule): rule is Record<string, unknown> => {
    if (!record(rule) || typeof rule.id !== "string") return false;
    const marker = markers[rule.id];
    return record(marker) && marker.origin === "consolidation" && marker.revision === ruleRevision(rule);
  });
}

/** Raw task writes must not silently turn a parent-owned rule into manual state,
 * or add a shadow that prevents its later corrections from taking effect. */
export function preservesOwnedHarnessRules(previous: unknown, candidate: unknown, otherLayers: readonly unknown[] = []): boolean {
  if (!record(candidate)) return false;
  const before = record(previous) ? previous : {};
  for (const rule of ownedRules(before)) {
    const id = rule.id as string;
    const marker = record(before.learnedRules) ? before.learnedRules[id] : undefined;
    const replacement = Array.isArray(candidate.rules) ? candidate.rules.filter(value => record(value) && value.id === rule.id) : [];
    if (replacement.length !== 1 || !isDeepStrictEqual(replacement[0], rule)
      || !record(candidate.learnedRules) || !isDeepStrictEqual(candidate.learnedRules[id], marker)) return false;
  }
  for (const rule of otherLayers.flatMap(ownedRules)) {
    const shadows = (config: Record<string, unknown>): unknown[] => Array.isArray(config.rules)
      ? config.rules.filter(value => record(value) && value.id === rule.id) : [];
    if (!isDeepStrictEqual(shadows(before), shadows(candidate))) return false;
  }
  return true;
}
