import {
  allowedTransitions,
  modelStandaloneCapabilities,
  normalizeProcedureId,
  workflowEntry,
  workflowPlacement,
  workflowRoutes as catalogWorkflowRoutes,
} from "./catalog.ts";

export const WORKFLOW_STATE_ENTRY = "matt-pocock-workflow";
export const WORKFLOW_STATE_VERSION = 1;

export interface WorkflowState {
  version: 1;
  workItemId: string;
  route: string;
  procedure: string;
  phase: string;
  status: "active";
  loadedReferences: string[];
}

export interface TerminalWorkflowState {
  version: 1;
  workItemId: string;
  route: string;
  procedure: string;
  phase: string;
  status: "completed" | "cancelled";
  reason?: string;
}

export type WorkflowSessionData = WorkflowState | TerminalWorkflowState;

export type WorkflowRoute = ReturnType<typeof catalogWorkflowRoutes>[number];

export function workflowRoutes(): WorkflowRoute[] {
  return catalogWorkflowRoutes();
}

export function findWorkflowRoute(route: string): WorkflowRoute | undefined {
  return workflowRoutes().find((candidate) => candidate.route === route);
}

export function routeEntryState(route: string, workItemId: string): WorkflowState | undefined {
  const entry = workflowEntry(route);
  const placement = entry && workflowPlacement(route, entry.id);
  if (!entry || !placement) return undefined;
  return {
    version: WORKFLOW_STATE_VERSION,
    workItemId,
    route,
    procedure: entry.id,
    phase: placement.phase,
    status: "active",
    loadedReferences: [],
  };
}

export function transitionState(state: WorkflowState, target: string): WorkflowState {
  const normalized = normalizeProcedureId(target);
  const allowed = allowedTransitions(state.route, state.procedure);
  if (!allowed.includes(normalized)) {
    throw new Error(
      `Cannot transition ${state.route} from ${state.procedure} to ${target}. Allowed next procedures: ${allowed.join(", ") || "none"}. Complete or cancel the workflow if no next procedure applies.`,
    );
  }
  const placement = workflowPlacement(state.route, normalized);
  if (!placement) throw new Error(`Procedure ${normalized} is not part of workflow ${state.route}.`);
  return {
    ...state,
    procedure: normalized,
    phase: placement.phase,
    loadedReferences: [],
  };
}

const phaseTitles: Record<string, string> = {
  shaping: "Shaping & Requirements",
  research: "Research & Feasibility",
  prototype: "Prototyping",
  "to-spec": "Specification Design",
  "to-tickets": "Task Decomposition",
  implement: "Implementation",
  "code-review": "Code Review",
  handoff: "Handoff & Summary",
  "feedback-loop": "Reproducing & Diagnostics",
  mapping: "Initiative Mapping",
  survey: "Architecture Survey",
  "design-review": "Architecture Design",
  triage: "Task Triage",
};

export function readableRouteTitle(route: string): string {
  return findWorkflowRoute(route)?.title ?? route.replace(/-/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function readablePhaseTitle(phase: string): string {
  return phaseTitles[phase] ?? phase.replace(/-/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatReadableWorkflowSubject(route: string, phase: string): string {
  return `${readableRouteTitle(route)} · ${readablePhaseTitle(phase)}`;
}

export function isWorkflowState(value: unknown): value is WorkflowState {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return candidate.version === WORKFLOW_STATE_VERSION
    && typeof candidate.workItemId === "string"
    && typeof candidate.route === "string"
    && typeof candidate.procedure === "string"
    && typeof candidate.phase === "string"
    && candidate.status === "active"
    && Array.isArray(candidate.loadedReferences)
    && candidate.loadedReferences.every((reference) => typeof reference === "string");
}

export function isTerminalWorkflowState(value: unknown): value is TerminalWorkflowState {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return candidate.version === WORKFLOW_STATE_VERSION
    && typeof candidate.workItemId === "string"
    && typeof candidate.route === "string"
    && typeof candidate.procedure === "string"
    && typeof candidate.phase === "string"
    && (candidate.status === "completed" || candidate.status === "cancelled");
}

export function latestWorkflowRecord(entries: unknown[]): WorkflowSessionData | undefined {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const entry = entries[index] as { type?: unknown; customType?: unknown; data?: unknown } | undefined;
    if (entry?.type !== "custom" || entry.customType !== WORKFLOW_STATE_ENTRY) continue;
    if (isWorkflowState(entry.data) || isTerminalWorkflowState(entry.data)) return entry.data;
  }
  return undefined;
}

export function latestWorkflowState(entries: unknown[]): WorkflowState | undefined {
  const record = latestWorkflowRecord(entries);
  return record?.status === "active" ? record : undefined;
}

export function workflowGuidance(state: WorkflowState, availableReferences: string[]): string {
  const next = allowedTransitions(state.route, state.procedure);
  return `Matt Pocock workflow active: ${state.route} · ${state.phase}.
Work item: ${state.workItemId}. Follow the loaded ${state.procedure} procedure. Use matt_pocock_active to transition only to: ${next.join(", ") || "none"}; load an available reference; complete the work; or cancel it with a reason. Available references: ${availableReferences.join(", ") || "none"}. Proceed autonomously through non-user-owned work: once the current procedure's deliverables or decisions are ready, transition to the next applicable procedure via matt_pocock_active immediately without stopping to ask permission. Ask only for a genuinely user-owned decision, unavailable fact, or required external action. Use matt_pocock_ask for structured workflow decisions. When the workflow's work is done, call matt_pocock_active with action complete instead of leaving stale active state.`;
}

export function availableWorkflowsGuidance(): string {
  const workflows = workflowRoutes()
    .map((route) => `- ${route.route}: ${route.description}`)
    .join("\n");
  const capabilities = modelStandaloneCapabilities()
    .map((capability) => `- ${capability.id}: ${capability.description}`)
    .join("\n");
  return `## Available Matt Pocock Workflows and Capabilities

Use matt_pocock_workflow for structured engineering workflows or a listed standalone capability. Do not activate a workflow for routine work that another loaded skill already owns.

When a user request matches a multi-step engineering task, proactively activate the structured workflow:
- New feature, requirement, or end-to-end initiative: start idea-to-ship.
- Reproducing, diagnosing, or fixing a hard or non-trivial bug: start hard-bug.
- Exploring and restructuring codebase architecture or deepening shallow modules: start architecture.
- Charting ambiguous initiatives with decision tickets: start wayfinding.
- Categorizing and triaging issue tracker tickets: start triage.

Workflows:
${workflows}

Model-reachable standalone capabilities:
${capabilities}

Workflow state is deliberate and task-scoped. When relevant, start a workflow first with matt_pocock_workflow (mode: "workflow"); the started workflow carries its procedure and next-step guidance.`;
}
