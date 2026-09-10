import { readFileSync } from "node:fs";

export interface TriggerEntry {
  id: string;
  implemented: boolean;
  closestImplemented: string | null;
  en: string[];
  zh: string[];
  hint: string;
  does: string;
  aliasOf?: string;
  deprecated?: boolean;
}

export interface RouteResult {
  recognized: string;
  target: string | null;
  queued: string | null;
  runnerUp: string | null;
  unported: string | null;
  aliasNote: string | null;
}

const EVALUATE = new Set(["critique", "audit"]);

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function scoreEntry(prompt: string, lowered: string, entry: TriggerEntry): number {
  let score = 0;
  for (const phrase of entry.en) {
    if (phrase.length <= 4 ? new RegExp(`\\b${escapeRegExp(phrase)}\\b`, "i").test(prompt) : lowered.includes(phrase.toLowerCase())) score += 1;
  }
  for (const phrase of entry.zh) {
    if (phrase && prompt.includes(phrase)) score += 1;
  }
  return score;
}

function resolveTarget(entry: TriggerEntry, isImplemented: (id: string) => boolean): { target: string | null; unported: string | null } {
  if (isImplemented(entry.id)) return { target: entry.id, unported: null };
  if (entry.closestImplemented && isImplemented(entry.closestImplemented)) return { target: entry.closestImplemented, unported: entry.id };
  return { target: null, unported: entry.id };
}

export function routeFreeform(
  prompt: string,
  entries: TriggerEntry[],
  isImplemented: (id: string) => boolean,
): RouteResult | null {
  const byId = new Map(entries.map(entry => [entry.id, entry]));
  const lowered = prompt.toLowerCase();
  const scored = entries
    .map(entry => ({ entry, score: scoreEntry(prompt, lowered, entry) }))
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score);
  if (!scored.length) return null;

  let recognized = scored[0].entry;
  let aliasNote: string | null = null;
  if (recognized.aliasOf && byId.has(recognized.aliasOf)) {
    aliasNote = `${recognized.id} is a deprecated alias and adds no behavior`;
    recognized = byId.get(recognized.aliasOf)!;
  }

  const resolved = resolveTarget(recognized, isImplemented);
  let target = resolved.target;
  let unported = resolved.unported;
  let queued: string | null = null;

  if (target) {
    const targetIsEvaluate = EVALUATE.has(target);
    for (const item of scored) {
      const candidate = item.entry.aliasOf && byId.has(item.entry.aliasOf) ? byId.get(item.entry.aliasOf)! : item.entry;
      const candidateResolved = resolveTarget(candidate, isImplemented);
      if (!candidateResolved.target || candidateResolved.target === target) continue;
      const candidateIsEvaluate = EVALUATE.has(candidateResolved.target);
      if (targetIsEvaluate && !candidateIsEvaluate && !queued) {
        queued = candidateResolved.target;
      } else if (!targetIsEvaluate && candidateIsEvaluate) {
        queued = target;
        target = candidateResolved.target;
        unported = candidateResolved.unported;
        recognized = candidate;
        break;
      }
    }
  }

  let runnerUp: string | null = null;
  if (target) {
    for (const item of scored) {
      if (item.score < scored[0].score - 1) break;
      const candidate = item.entry.aliasOf && byId.has(item.entry.aliasOf) ? byId.get(item.entry.aliasOf)! : item.entry;
      const candidateResolved = resolveTarget(candidate, isImplemented);
      const candidateTarget = candidateResolved.target;
      if (candidateTarget && candidateTarget !== target && candidateTarget !== queued) {
        runnerUp = candidateTarget;
        break;
      }
    }
  }

  return { recognized: recognized.id, target, queued, runnerUp, unported, aliasNote };
}

export function loadTriggers(): TriggerEntry[] {
  const raw = JSON.parse(readFileSync(new URL("./command-triggers.json", import.meta.url), "utf8")) as {
    triggers: TriggerEntry[];
  };
  return raw.triggers;
}
