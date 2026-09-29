/**
 * Judging a Memory plan's proposals.
 *
 * The Memory planner proposes `newMemories` and the parent applies all of them.
 * This module asks what a decision surface thinks of each proposal — durable?
 * how general? a restatement of something already indexed? — and records the
 * answers. **It changes nothing.** The parent still applies every proposal
 * exactly as it does today.
 *
 * That is the point. Before asking a planner to produce K candidates and pick
 * one, the baseline has to exist: how good is a single proposal? Without it,
 * "K candidates would help" is an opinion rather than a measurement.
 *
 * The questions here are deliberately a mix of primitives. `noul` alone would
 * leave every answer without a confidence, and the confidence axis of the
 * observation record is the one that distinguishes a settled judgment from a
 * coin flip — so generality is a `score` and duplication is a `choice`, both of
 * which carry one.
 *
 * Proposal content is model-generated and therefore untrusted, exactly like the
 * Task Slice: it is carried as bounded data with no path that promotes it.
 */

import type { SystemOneQuestion } from "@fradser/pi-kit";
import type { NewMemoryProposal } from "./consolidation-run";

export const MAX_PROJECTED_PROPOSALS = 8;
export const MAX_PROJECTED_PROPOSAL_BYTES = 1_200;
export const MAX_PROJECTED_EVIDENCE_QUOTES = 3;
const MAX_PROJECTED_QUOTE_CHARS = 200;

const DURABLE_PREFIX = "durable::";
const GENERAL_PREFIX = "general::";
const DUPLICATE_PREFIX = "duplicate::";
const NO_MATCH = "none";

/** Ordered levels. Each describes a concrete situation and stands on its own;
 *  a level that needed the others to make sense would not be usable. */
const GENERALITY_LEVELS = [
  "Valid only for this exact occurrence: it describes what happened once, and a different instance of the same task would not follow it.",
  "Valid for this class of task in this project: a future task of the same kind here would follow it.",
  "Valid for this class of task in any project: the lesson travels, and the project is incidental.",
  "Valid as a general engineering practice: it holds regardless of project, task, or tool.",
];

export interface MemoryProposalProjectionInput {
  proposals: readonly Pick<NewMemoryProposal, "name" | "kind" | "classification" | "content" | "evidence">[];
  /** Memory metadata for the whole corpus, so duplication can be judged. */
  memories: ReadonlyArray<{ name: string; type: string; description: string }>;
  /** Entries the parent selected for this run, which a proposal may supersede. */
  selected: readonly string[];
}

export interface MemoryProposalProjection {
  state: {
    proposals: Array<{
      id: string;
      kind: string;
      classification: string;
      content: string;
      evidenceQuotes: string[];
    }>;
    memory_index: Array<{ id: string; type: string; description: string }>;
  };
  questions: Record<string, SystemOneQuestion>;
  proposalIds: string[];
}

function clip(value: string, maxBytes: number): string {
  const bytes = Buffer.from(value, "utf-8");
  return bytes.length <= maxBytes ? value : bytes.subarray(0, maxBytes).toString("utf-8");
}

function quotesOf(proposal: Pick<NewMemoryProposal, "evidence">): string[] {
  return (proposal.evidence ?? [])
    .slice(0, MAX_PROJECTED_EVIDENCE_QUOTES)
    .map((entry) => clip(String(entry?.quote ?? ""), MAX_PROJECTED_QUOTE_CHARS))
    .filter((quote) => quote.length > 0);
}

/**
 * Build the bounded proposal projection and its questions. An empty proposal
 * list produces no questions at all, so a plan with nothing to add costs no
 * request.
 */
export function buildProposalProjection(input: MemoryProposalProjectionInput): MemoryProposalProjection {
  const memoryIndex = input.memories.map((memory, index) => ({
    id: `m${index}`,
    type: clip(memory.type, 80),
    description: clip(memory.description, 300),
  }));

  const proposals = input.proposals.slice(0, MAX_PROJECTED_PROPOSALS).map((proposal, index) => ({
    id: `c${index}`,
    kind: String(proposal.kind),
    classification: String(proposal.classification),
    content: clip(proposal.content, MAX_PROJECTED_PROPOSAL_BYTES),
    evidenceQuotes: quotesOf(proposal),
  }));

  const questions: Record<string, SystemOneQuestion> = {};
  proposals.forEach((proposal, position) => {
    questions[`${DURABLE_PREFIX}${proposal.id}`] = {
      type: "noul",
      instructions:
        `Will \`proposals[${position}].content\` still be true and useful in a later, different task that is not this one?`,
      criteria: {
        true: "A reusable lesson or fact, not a record of one occurrence.",
        false: "It describes what happened once, or `memory_index` already records it.",
      },
    };
    // A score, so the answer carries a confidence: the observation record's
    // confidence axis is otherwise empty, and generality is the dimension where
    // a settled judgment and a coin flip look most different.
    questions[`${GENERAL_PREFIX}${proposal.id}`] = {
      type: "score",
      instructions: `How far beyond this single occurrence does \`proposals[${position}].content\` remain valid?`,
      criteria: GENERALITY_LEVELS,
    };
    // A choice, so the answer carries a confidence and can name an entry. The
    // explicit no-match option matters: without it, "none of these" would have
    // to be expressed by picking the least similar entry, and the model cannot
    // choose a value the request did not offer.
    const duplicateCriteria: Record<string, string> = {};
    memoryIndex.forEach((memory, memoryPosition) => {
      duplicateCriteria[memory.id] = `An entry that already records this: ${input.memories[memoryPosition].name}`;
    });
    duplicateCriteria[NO_MATCH] = "No indexed entry records this knowledge.";
    questions[`${DUPLICATE_PREFIX}${proposal.id}`] = {
      type: "choice",
      instructions:
        `Which entry in \`memory_index\` already records the same knowledge as \`proposals[${position}].content\`?`,
      criteria: duplicateCriteria,
    };
  });

  return { state: { proposals, memory_index: memoryIndex }, questions, proposalIds: proposals.map((p) => p.id) };
}

/** Proposal ids whose generality answer clears the reporting level. */
export function proposalsJudgmentWouldKeep(
  verdicts: Record<string, number | string>,
  projection: MemoryProposalProjection,
  /** The level at or above which a proposal is considered reusable anywhere. */
  minimumGenerality: number,
): string[] {
  const kept: string[] = [];
  for (const id of projection.proposalIds) {
    const generality = verdicts[`${GENERAL_PREFIX}${id}`];
    if (typeof generality !== "number" || generality < minimumGenerality) continue;
    const durable = verdicts[`${DURABLE_PREFIX}${id}`];
    if (typeof durable !== "number" || durable < 0.5) continue;
    kept.push(id);
  }
  return kept;
}

export const PROPOSAL_PREFIXES = { durable: DURABLE_PREFIX, general: GENERAL_PREFIX, duplicate: DUPLICATE_PREFIX } as const;
export { NO_MATCH as PROPOSAL_NO_MATCH };
