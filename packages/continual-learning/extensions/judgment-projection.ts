/**
 * The projection a Judgment surface is given.
 *
 * Two properties are structural rather than prompted:
 *
 * - **Containment.** The Task Slice is verbatim user text and tool output, which
 *   this package already treats as untrusted evidence rather than instructions.
 *   A decision model does not treat request content as hostile by default, so
 *   unfiltered content is never sent. What is sent is this projection, and the
 *   projection builder has no path that promotes a value out of the data.
 * - **Opaque identity.** Candidates carry index-derived identifiers, so an
 *   answer cannot name a Memory file. Invalid names, wrong casing, and
 *   duplicates leave parent-side validation rather than gaining checks.
 *
 * Thresholds are deliberately absent. Nothing here decides which entry applies;
 * the parent owns that comparison once measurements exist.
 */

import type { SystemOneQuestion } from "@fradser/pi-kit";
import type { MemoryMetadata } from "./incremental-learning";

export const MAX_PROJECTED_REQUEST_BYTES = 4_096;
export const MAX_PROJECTED_EVENTS = 16;
export const MAX_PROJECTED_PATHS = 32;
export const MAX_PROJECTED_EVENT_CHARS = 240;
const MAX_CANDIDATES = 64;

export interface JudgmentProjectionInput {
  /** User-authored request text from the Task Slice. Tool output is not
   *  projected: it is unbounded, untrusted, and unnecessary for these questions. */
  requestText: string;
  /** Already classified by the package's own regex pass. */
  harnessEvents: readonly string[];
  touchedPaths: readonly string[];
  skills: readonly string[];
  memories: readonly MemoryMetadata[];
}

export interface JudgmentProjection {
  state: {
    request: { text: string };
    harness_events: string[];
    touched_paths: string[];
    memory_index: Array<{ id: string; type: string; description: string }>;
    registered_skills: string[];
  };
  questions: Record<string, SystemOneQuestion>;
  /** Maps an opaque identifier back to a Memory name. Parent-side only. */
  candidateNames: Map<string, string>;
  /** Question id prefix per candidate, so one answer drives one comparison. */
  scopeQuestionPrefix: string;
}

function clip(value: string, maxBytes: number): string {
  const bytes = Buffer.from(value, "utf-8");
  if (bytes.length <= maxBytes) return value;
  return bytes.subarray(0, maxBytes).toString("utf-8");
}

function boundedList(values: readonly string[], limit: number, maxChars: number): string[] {
  return values.filter((value) => typeof value === "string" && value.length > 0)
    .slice(0, limit)
    .map((value) => clip(value, maxChars));
}

const SCOPE_PREFIX = "scope::";

/**
 * Build the bounded projection and its questions.
 *
 * Clip order is fixed and documented because it is a contract: request text is
 * the only unbounded field, and it is clipped first so the index and the event
 * summaries — the parts every question actually needs — always survive.
 */
export function buildJudgmentProjection(input: JudgmentProjectionInput): JudgmentProjection {
  const candidateNames = new Map<string, string>();
  const memoryIndex = input.memories.slice(0, MAX_CANDIDATES).map((memory, index) => {
    const id = `m${index}`;
    candidateNames.set(id, memory.name);
    return {
      id,
      type: clip(memory.type, 80),
      description: clip(memory.description, 300),
    };
  });

  const state = {
    request: { text: clip(input.requestText, MAX_PROJECTED_REQUEST_BYTES) },
    harness_events: boundedList(input.harnessEvents, MAX_PROJECTED_EVENTS, MAX_PROJECTED_EVENT_CHARS),
    touched_paths: boundedList(input.touchedPaths, MAX_PROJECTED_PATHS, 200),
    memory_index: memoryIndex,
    registered_skills: boundedList(input.skills, 32, 120),
  };

  const questions: Record<string, SystemOneQuestion> = {};
  for (const entry of memoryIndex) {
    // Literal wording with both directions spelled out. The old selector prompt
    // asked for "the minimum sufficient scope" and "no arbitrary count cap" in
    // the same breath as several exclusions; those were conditions a reader had
    // to infer, and the parent now owns the comparison instead.
    questions[`${SCOPE_PREFIX}${entry.id}`] = {
      type: "noul",
      instructions:
        `Does \`memory_index[${entry.id}]\` supply a specific fact, decision, or constraint that \`request.text\` needs in order to be carried out correctly?`,
      criteria: {
        true: "The task cannot be carried out correctly without this entry.",
        false:
          "It is on the same topic, or it is generally good practice, but this task does not depend on it.",
      },
    };
  }
  questions.warrants_memory = {
    type: "noul",
    instructions:
      "Will this task leave behind knowledge that is reusable in a later, different task and that `memory_index` does not already record?",
    criteria: {
      true: "Something durable and not yet recorded.",
      false: "Nothing durable, or `memory_index` already records it.",
    },
  };
  questions.warrants_harness = {
    type: "noul",
    instructions:
      "Did the user state an explicit, durable constraint on how a tool may be invoked — a command, path, or operation that must always, never, or first be confirmed or blocked — rather than a preference about how the work is done?",
    criteria: {
      true: "An executable, evidence-backed constraint on tool invocation.",
      false: "A preference, a one-time exception, or a topic worth remembering instead.",
    },
  };
  questions.warrants_agents = {
    type: "noul",
    instructions:
      "Did this task establish a project instruction that should be in effect on every future task in this project, rather than only on this one?",
    criteria: {
      true: "Durable, always-loaded project instruction evidence.",
      false: "Task-specific knowledge, or already covered by an existing entry.",
    },
  };

  return { state, questions, candidateNames, scopeQuestionPrefix: SCOPE_PREFIX };
}

/** One answer's value and, when the primitive carries one, its confidence. */
export interface JudgmentVerdict {
  value: number | string;
  confidence?: number;
}

function verdictOf(answer: unknown): JudgmentVerdict | undefined {
  if (!answer || typeof answer !== "object") return undefined;
  const record = answer as Record<string, unknown>;
  if (record.type === "noul" && typeof record.noul === "number") return { value: record.noul };
  if (record.type === "choice" && typeof record.choice === "string") {
    return {
      value: record.choice,
      ...(typeof record.confidence === "number" ? { confidence: record.confidence } : {}),
    };
  }
  if (record.type === "score" && typeof record.score === "number") {
    return {
      value: record.score,
      ...(typeof record.confidence === "number" ? { confidence: record.confidence } : {}),
    };
  }
  return undefined;
}

/**
 * Flatten answers into the comparable record. A noul has no confidence of its
 * own, and inventing one would imply a certainty the primitive never stated.
 */
export function collectJudgmentVerdicts(
  answers: Record<string, unknown>,
): { values: Record<string, number | string>; confidences: Record<string, number> } {
  const values: Record<string, number | string> = {};
  const confidences: Record<string, number> = {};
  for (const [id, answer] of Object.entries(answers)) {
    const verdict = verdictOf(answer);
    if (!verdict) continue;
    values[id] = verdict.value;
    if (verdict.confidence !== undefined) confidences[id] = verdict.confidence;
  }
  return { values, confidences };
}

/**
 * Names the candidates a hypothetical threshold would have selected. This is
 * reported as `judgmentSelected` and is never the answer that reaches the
 * parent — it exists so shadow runs can be compared against the selector.
 *
 * The threshold is a reporting parameter, not a decision. It is not a tunable
 * constant: the promotion report is what tells anyone which value to use.
 */
export function judgmentSelectedNames(
  verdicts: Record<string, number | string>,
  projection: JudgmentProjection,
  threshold: number,
): string[] {
  const selected: string[] = [];
  for (const [id, value] of Object.entries(verdicts)) {
    if (!id.startsWith(projection.scopeQuestionPrefix)) continue;
    if (typeof value !== "number" || value < threshold) continue;
    const name = projection.candidateNames.get(id.slice(projection.scopeQuestionPrefix.length));
    if (name) selected.push(name);
  }
  return selected.sort((left, right) => left.localeCompare(right));
}