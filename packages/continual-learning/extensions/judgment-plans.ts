/**
 * Judging every remaining plan surface.
 *
 * Shadow mode already observes the selector and the Memory plan's new entries.
 * Three surfaces were still invisible: the Memory plan's *operations* on
 * existing entries, the Harness plan's rules, and the AGENTS.md plan's
 * instructions. This closes them, so a decision surface participates in the
 * whole learning process rather than one corner of it.
 *
 * One module for all three because the questions are the same shape: is this
 * durable, how far does it generalize, and — where the parent accepts a closed
 * set — which value of that set is right. Three near-identical modules would
 * drift.
 *
 * As everywhere else: **nothing here changes what the parent writes.** It
 * records what a decision surface would have said, so that the later question
 * of letting one decide has measurements behind it.
 *
 * Every plan field is model-generated and therefore untrusted, exactly like a
 * Task Slice. It is carried as bounded data with no path that promotes it.
 */

import type { SystemOneQuestion } from "@fradser/pi-kit";
import { MAX_PROJECTED_PROPOSAL_BYTES } from "./judgment-proposals";

export const MAX_PROJECTED_OPERATIONS = 12;
const MAX_PROJECTED_SELECTED = 32;
const MAX_PROJECTED_INSTRUCTION_BYTES = 800;

/** Ordered levels reused from the proposal surface, so the two record the same
 *  dimension on the same scale. */
const GENERALITY_LEVELS = [
  "Valid only for this exact occurrence: it describes what happened once, and a different instance of the same task would not follow it.",
  "Valid for this class of task in this project: a future task of the same kind here would follow it.",
  "Valid for this class of task in any project: the lesson travels, and the project is incidental.",
  "Valid as a general engineering practice: it holds regardless of project, task, or tool.",
];

/** The closed set the parent already accepts for a Memory entry's staleness.
 *  Asking for the same vocabulary means an answer can be compared with a plan
 *  rather than needing a translation. */
export const STALENESS_VALUES = ["keep", "contradicted", "superseded", "subsumed"] as const;
export const MEMORY_OPERATION_VALUES = ["none", "create", "rewrite", "delete"] as const;
export const HARNESS_SELECTOR_VALUES = ["skill", "bash", "text"] as const;
export const HARNESS_ACTION_VALUES = ["guidance", "confirm", "block"] as const;

export type Surface = "memory-operations" | "harness-operations" | "agents-operations";

export interface PlanOperationInput {
  name: string;
  /** Bounded, model-generated, and therefore untrusted. */
  body: string;
  /** The operation the plan proposed, when the plan proposed one. */
  proposed?: string;
  /** Closed-set questions specific to the surface. */
  [extra: string]: unknown;
}

export interface PlanProjectionInput {
  surface: Surface;
  operations: readonly PlanOperationInput[];
  /** Existing Memory the run selected; staleness is asked about each. */
  selected?: ReadonlyArray<{ name: string; description: string }>;
}

export interface PlanProjection {
  surface: Surface;
  state: {
    surface: Surface;
    operations: Array<{ id: string; name: string; body: string; proposed: string | null }>;
    selected: Array<{ id: string; name: string; description: string }>;
  };
  questions: Record<string, SystemOneQuestion>;
  operationIds: string[];
  selectedIds: string[];
}

function clip(value: unknown, maxBytes: number): string {
  const text = typeof value === "string" ? value : "";
  const bytes = Buffer.from(text, "utf-8");
  return bytes.length <= maxBytes ? text : bytes.subarray(0, maxBytes).toString("utf-8");
}

const asArray = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);
const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

/** Read a plan's operations without trusting any of it. */
export function planOperationsOf(plan: unknown, kindKey: "kind" | "op"): PlanOperationInput[] {
  return asArray(asRecord(plan).operations)
    .map((raw, index) => {
      const record = asRecord(raw);
      const rule = asRecord(record.rule);
      // The three surfaces name their operations differently: Memory uses
      // `name`, Harness a rule id, AGENTS.md neither — its operation is an
      // edit to a unit. Falling back to the operation kind keeps an AGENTS
      // instruction observable instead of silently filtered out.
      const name = typeof record.name === "string"
        ? record.name
        : typeof rule.id === "string"
          ? rule.id
          : typeof record.op === "string"
            ? `${record.op}#${index}`
            : typeof record.kind === "string"
              ? `${record.kind}#${index}`
              : "";
      const body = typeof record.content === "string"
        ? record.content
        : [
            typeof rule.instructions === "string" ? rule.instructions : "",
            typeof rule.message === "string" ? rule.message : "",
            typeof record.newText === "string" ? record.newText : "",
            typeof record.text === "string" ? record.text : "",
            typeof record.replacementText === "string" ? record.replacementText : "",
          ].filter(Boolean).join("\n");
      const declared = typeof record[kindKey] === "string" ? (record[kindKey] as string) : undefined;
      const selector = ["skill", "bash", "text"].find((key) => rule[key] !== undefined);
      const action = typeof rule.action === "string" ? rule.action : undefined;
      return {
        name,
        body: clip(body, MAX_PROJECTED_PROPOSAL_BYTES),
        ...(declared ? { proposed: declared } : {}),
        ...(selector ? { selector } : {}),
        ...(action ? { action } : {}),
      };
    })
    .filter((operation) => operation.name.length > 0);
}

function surfaceQuestions(surface: Surface, operationCount: number): Record<string, SystemOneQuestion> {
  const questions: Record<string, SystemOneQuestion> = {};
  for (let index = 0; index < operationCount; index += 1) {
    const id = `o${index}`;
    const at = `operations[${index}]`;
    questions[`durable::${id}`] = {
      type: "noul",
      instructions:
        `Will \`${at}.body\` still be true and useful in a later, different task that is not this one?`,
      criteria: {
        true: "A durable lesson, constraint, or instruction.",
        false: "It records one occurrence, or it is already covered elsewhere.",
      },
    };
    // A score, so the answer carries a confidence.
    questions[`general::${id}`] = {
      type: "score",
      instructions: `How far beyond this single occurrence does \`${at}.body\` remain valid?`,
      criteria: GENERALITY_LEVELS,
    };
    if (surface === "memory-operations") {
      questions[`op::${id}`] = {
        type: "choice",
        instructions: `What should happen to the Memory entry \`${at}.name\`?`,
        criteria: {
          none: "It stays as it is; nothing needs to change.",
          create: "A new entry should be written.",
          rewrite: "The existing entry should be rewritten.",
          delete: "The existing entry should be removed as stale.",
        },
      };
    }
    if (surface === "harness-operations") {
      questions[`selector::${id}`] = {
        type: "choice",
        instructions: `Which match entry identifies where \`${at}.body\` is relevant?`,
        criteria: {
          skill: "A named skill invocation.",
          bash: "A command string.",
          text: "A retained conversation fragment.",
        },
      };
      questions[`strength::${id}`] = {
        type: "choice",
        instructions: `How strongly should \`${at}.name\` constrain execution?`,
        criteria: {
          guidance: "Attach corrective guidance to the real result and proceed.",
          confirm: "Ask the user to confirm before proceeding.",
          block: "Refuse the operation.",
        },
      };
    }
    if (surface === "agents-operations") {
      questions[`always::${id}`] = {
        type: "noul",
        instructions:
          `Should \`${at}.body\` be in effect on every future task in this project, rather than only on the task that produced it?`,
        criteria: {
          true: "Durable, always-loaded project instruction evidence.",
          false: "Task-specific knowledge that belongs in Memory or a Harness rule instead.",
        },
      };
    }
  }
  return questions;
}

/** Build the bounded projection and questions for one plan surface. */
export function buildPlanProjection(input: PlanProjectionInput): PlanProjection {
  const operations = input.operations.slice(0, MAX_PROJECTED_OPERATIONS).map((operation, index) => ({
    id: `o${index}`,
    name: clip(operation.name, 200),
    body: clip(operation.body, MAX_PROJECTED_INSTRUCTION_BYTES),
    proposed: typeof operation.proposed === "string" ? operation.proposed : null,
  }));
  const selected = (input.selected ?? []).slice(0, MAX_PROJECTED_SELECTED).map((entry, index) => ({
    id: `m${index}`,
    name: clip(entry.name, 200),
    description: clip(entry.description, 300),
  }));

  const questions = surfaceQuestions(input.surface, operations.length);
  // Staleness is asked about every selected entry the plan did not already
  // touch, using the parent's own closed vocabulary so an answer is comparable
  // with the plan rather than needing a translation.
  selected.forEach((entry, position) => {
    questions[`stale::${entry.id}`] = {
      type: "choice",
      instructions: `Is the existing Memory entry \`selected[${position}]\` still accurate, or has it been overtaken?`,
      criteria: {
        keep: "It is still accurate and still applies.",
        contradicted: "Later evidence in this run contradicts it.",
        superseded: "A newer entry in this plan replaces it.",
        subsumed: "Another entry now covers everything it says.",
      },
    };
  });

  return {
    surface: input.surface,
    state: { surface: input.surface, operations, selected },
    questions,
    operationIds: operations.map((operation) => operation.id),
    selectedIds: selected.map((entry) => entry.id),
  };
}

export { GENERALITY_LEVELS };
