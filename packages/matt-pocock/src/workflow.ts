export interface WorkflowState {
  route: string;
  procedure: string;
  phase: string;
}

export interface WorkflowRoute extends WorkflowState {
  label: string;
  description: string;
}

export const WORKFLOW_STATE_ENTRY = "matt-pocock-workflow";
export type WorkflowSessionData = WorkflowState | { active: false };

const routes: WorkflowRoute[] = [
  {
    route: "idea-to-ship",
    label: "Start an idea-to-ship flow",
    description: "Shape an idea before planning and implementation.",
    procedure: "grill-with-docs",
    phase: "shaping",
  },
  {
    route: "hard-bug",
    label: "Diagnose a hard bug",
    description: "Build a tight feedback loop before forming a theory.",
    procedure: "diagnosing-bugs",
    phase: "feedback-loop",
  },
  {
    route: "triage",
    label: "Triage incoming work",
    description: "Turn incoming issues into agent-ready briefs.",
    procedure: "triage",
    phase: "triage",
  },
  {
    route: "wayfinding",
    label: "Map a large ambiguous initiative",
    description: "Resolve decision tickets before creating a build plan.",
    procedure: "wayfinder",
    phase: "mapping",
  },
  {
    route: "architecture",
    label: "Improve codebase architecture",
    description: "Find and develop deepening opportunities.",
    procedure: "improve-codebase-architecture",
    phase: "survey",
  },
];

const phaseProcedures: Record<string, string[]> = {
  "idea-to-ship": ["grill-with-docs", "to-spec", "to-tickets", "implement", "code-review"],
  "hard-bug": ["diagnosing-bugs", "code-review"],
  triage: ["triage", "implement", "code-review"],
  wayfinding: ["wayfinder", "to-spec", "to-tickets", "implement", "code-review"],
  architecture: ["improve-codebase-architecture", "codebase-design", "implement", "code-review"],
};

export function workflowRoutes(): WorkflowRoute[] {
  return routes;
}

export function findWorkflowRoute(route: string): WorkflowRoute | undefined {
  return routes.find((candidate) => candidate.route === route);
}

export function transitionProcedures(route: string): string[] {
  return phaseProcedures[route] ?? [];
}

export function phaseForProcedure(procedure: string): string {
  return procedure;
}

export function isWorkflowState(value: unknown): value is WorkflowState {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.route === "string"
    && typeof candidate.procedure === "string"
    && typeof candidate.phase === "string";
}

export function latestWorkflowState(entries: unknown[]): WorkflowState | undefined {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const entry = entries[index] as { type?: unknown; customType?: unknown; data?: unknown } | undefined;
    if (entry?.type !== "custom" || entry.customType !== WORKFLOW_STATE_ENTRY) continue;
    if (isWorkflowState(entry.data)) return entry.data;
    if ((entry.data as { active?: unknown } | undefined)?.active === false) return undefined;
  }
  return undefined;
}

export function workflowGuidance(state: WorkflowState): string {
  return `Matt Pocock workflow active: ${state.route} · ${state.phase}.
Follow the loaded ${state.procedure} procedure. The user manually advances phases; do not infer phase completion from model output or tool activity.`;
}

export function availableWorkflowsGuidance(): string {
  return `## Available Engineering Workflows (Matt Pocock)
Activate structured workflows via the matt_pocock_workflow tool when relevant:
- idea-to-ship: Complex features and multi-step implementations (shaping → spec → tickets → implement → review).
- hard-bug: Difficult, intermittent, or regressed bugs (build tight red loop before forming a theory).
- triage: Incoming issues and raw requests (turn into agent-ready briefs).
- wayfinding: Large, ambiguous efforts (resolve decision tickets before creating a build plan).
- architecture: Codebase refactoring and deepening opportunities.`;
}
