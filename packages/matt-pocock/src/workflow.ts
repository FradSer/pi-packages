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
  "idea-to-ship": [
    "grill-with-docs",
    "grill-me",
    "grilling",
    "research",
    "prototype",
    "to-spec",
    "to-tickets",
    "implement",
    "code-review",
    "handoff",
  ],
  "hard-bug": ["diagnosing-bugs", "implement", "code-review"],
  triage: ["triage", "to-spec", "to-tickets", "implement", "code-review"],
  wayfinding: ["wayfinder", "research", "prototype", "to-spec", "to-tickets", "implement", "code-review"],
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

const procedureAliases: Record<string, string> = {
  "tight-red-loop": "diagnosing-bugs",
  "clarify-goal": "wayfinder",
};

export function normalizeProcedureName(procedure: string): string {
  const normalized = procedure.trim().replace(/\.md$/i, "");
  return procedureAliases[normalized] ?? normalized;
}

export function transitionProcedureOptions(route: string): string[] {
  const procedures = new Set(transitionProcedures(route));
  for (const [alias, procedure] of Object.entries(procedureAliases)) {
    if (procedures.has(procedure)) procedures.add(alias);
  }
  return [...procedures];
}

const procedurePhases: Record<string, string> = {
  "grill-with-docs": "shaping",
  "grill-me": "shaping",
  grilling: "shaping",
  "diagnosing-bugs": "feedback-loop",
  wayfinder: "mapping",
};

export function phaseForProcedure(procedure: string): string {
  const norm = normalizeProcedureName(procedure);
  return procedurePhases[norm] ?? norm;
}

const routeTitles: Record<string, string> = {
  "idea-to-ship": "Idea to Ship",
  "hard-bug": "Hard Bug Diagnosis",
  triage: "Task Triage",
  wayfinding: "Architecture Wayfinding",
  architecture: "Codebase Architecture",
};

const phaseTitles: Record<string, string> = {
  shaping: "Shaping & Requirements",
  "grill-with-docs": "Shaping & Requirements",
  "grill-me": "Shaping & Requirements",
  grilling: "Shaping & Requirements",
  research: "Research & Feasibility",
  prototype: "Prototyping",
  "to-spec": "Specification Design",
  "to-tickets": "Task Decomposition",
  implement: "Implementation",
  "code-review": "Code Review",
  handoff: "Handoff & Summary",
  "feedback-loop": "Reproducing & Diagnostics",
  "diagnosing-bugs": "Reproducing & Diagnostics",
  mapping: "Initiative Mapping",
  wayfinder: "Initiative Mapping",
  survey: "Architecture Survey",
  "improve-codebase-architecture": "Architecture Survey",
  "codebase-design": "Architecture Design",
};

export function readableRouteTitle(route: string): string {
  return routeTitles[route] ?? route.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function readablePhaseTitle(phase: string): string {
  return phaseTitles[phase] ?? phase.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatReadableWorkflowSubject(route: string, phase: string): string {
  return `${readableRouteTitle(route)} · ${readablePhaseTitle(phase)}`;
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
Follow the loaded ${state.procedure} procedure. Proceed autonomously from established context: do not stop to recommend, ask whether to continue, or request redundant confirmation. When the procedure's done condition is met and the next applicable procedure is clear, call matt_pocock_workflow to transition immediately, then execute it. Continue through every newly unblocked AFK ticket or task; choose the next frontier ticket yourself when the user did not name one. Ask only for a genuinely user-owned decision, a fact unavailable through exploration, or a required external action. When asking interview or decision questions (e.g. during grilling/shaping), use the matt_pocock_ask tool to present structured options with recommendations, timeout, and custom response support. Do not treat a procedure summary, closed decision ticket, or phase boundary as a reason to wait for the user.`;
}

export function availableWorkflowsGuidance(): string {
  return `## Available Engineering Workflows (Matt Pocock)

Use matt_pocock_workflow only after you have determined that the current request needs one of these structured, multi-step engineering workflows. Do not activate it for routine work, document creation, research or testing performed through another loaded skill, simple questions, or because a previous session happened to use a workflow.

Activate it when relevant:
- idea-to-ship: Complex features and multi-step implementations (shaping → spec → tickets → implement → review).
- hard-bug: Difficult, intermittent, or regressed bugs (build tight red loop before forming a theory).
- triage: Incoming issues and raw requests that need converting into agent-ready briefs.
- wayfinding: Large, ambiguous engineering efforts requiring decision tickets before a build plan.
- architecture: Codebase refactoring and deepening opportunities.

A workflow remains active only for the deliberate engineering task that started it. When that task is finished or the user changes to unrelated work, call /matt-pocock end before proceeding.`;
}
