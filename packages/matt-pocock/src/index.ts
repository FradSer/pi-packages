import type {
  ExtensionAPI,
  ExtensionCommandContext,
  ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { procedurePrompt } from "./procedures.ts";
import {
  availableWorkflowsGuidance,
  findWorkflowRoute,
  latestWorkflowState,
  phaseForProcedure,
  transitionProcedures,
  WORKFLOW_STATE_ENTRY,
  workflowGuidance,
  workflowRoutes,
  type WorkflowState,
} from "./workflow.ts";

function stringEnum<T extends readonly string[]>(values: T, options?: Record<string, unknown>) {
  return Type.Unsafe<T[number]>({
    type: "string",
    enum: [...values],
    ...options,
  });
}

let activeWorkflow: WorkflowState | undefined;

function workflowStatus(state: WorkflowState): string {
  return `Matt Pocock: ${state.route} · ${state.phase}`;
}

function persistWorkflow(state: WorkflowState): void {
  activeWorkflow = state;
  pi.appendEntry(WORKFLOW_STATE_ENTRY, state);
}

function loadWorkflowProcedure(state: WorkflowState): string {
  const allowedProcedures = transitionProcedures(state.route);
  if (!allowedProcedures.includes(state.procedure)) {
    throw new Error(`Procedure ${state.procedure} is not available for route ${state.route}`);
  }
  return procedurePrompt(state.route, state.procedure, state.phase);
}

function injectProcedure(content: string): void {
  pi.sendUserMessage(content, { deliverAs: "followUp" });
}

function activateWorkflow(state: WorkflowState, ctx: ExtensionContext): void {
  const content = loadWorkflowProcedure(state);
  persistWorkflow(state);
  ctx.ui.setStatus("matt-pocock", workflowStatus(state));
  injectProcedure(content);
}

function routeChoices(): string[] {
  return workflowRoutes().map((route) => `${route.label} — ${route.description}`);
}

function routeFromChoice(choice: string): WorkflowState | undefined {
  const route = workflowRoutes().find((candidate) => choice.startsWith(candidate.label));
  return route && {
    route: route.route,
    procedure: route.procedure,
    phase: route.phase,
  };
}

async function chooseRoute(ctx: ExtensionCommandContext): Promise<void> {
  const choice = await ctx.ui.select("Start Matt Pocock workflow", routeChoices());
  if (!choice) return;
  const state = routeFromChoice(choice);
  if (state) activateWorkflow(state, ctx);
}

async function showMenu(ctx: ExtensionCommandContext): Promise<void> {
  const choices = ["Start a workflow", "View current workflow", "Transition current workflow", "End current workflow"];
  const choice = await ctx.ui.select("Matt Pocock workflow", choices);
  if (!choice) return;
  if (choice === "Start a workflow") {
    await chooseRoute(ctx);
    return;
  }
  if (choice === "View current workflow") {
    showStatus(ctx);
    return;
  }
  if (choice === "Transition current workflow") {
    await chooseTransition(ctx);
    return;
  }
  activeWorkflow = undefined;
  pi.appendEntry(WORKFLOW_STATE_ENTRY, { active: false });
  ctx.ui.setStatus("matt-pocock", undefined);
  ctx.ui.notify("Matt Pocock workflow ended.", "info");
}

async function chooseTransition(ctx: ExtensionCommandContext): Promise<void> {
  if (!activeWorkflow) {
    ctx.ui.notify("No active Matt Pocock workflow.", "warning");
    return;
  }

  const procedures = transitionProcedures(activeWorkflow.route);
  const choice = await ctx.ui.select(
    `Transition ${activeWorkflow.route} from ${activeWorkflow.phase}`,
    procedures,
  );
  if (!choice) return;

  activateWorkflow({
    route: activeWorkflow.route,
    procedure: choice,
    phase: phaseForProcedure(choice),
  }, ctx);
}

function showStatus(ctx: ExtensionContext): void {
  if (!activeWorkflow) {
    ctx.ui.notify("Matt Pocock workflow: inactive", "info");
    return;
  }
  ctx.ui.notify(workflowStatus(activeWorkflow), "info");
}

function parseRoute(args: string): WorkflowState | undefined {
  const route = findWorkflowRoute(args);
  return route && { route: route.route, procedure: route.procedure, phase: route.phase };
}

let pi: ExtensionAPI;

export default function mattPocock(extensionApi: ExtensionAPI): void {
  pi = extensionApi;

  pi.on("session_start", async (_event, ctx) => {
    const restoredWorkflow = latestWorkflowState(ctx.sessionManager.getBranch());
    if (!restoredWorkflow) {
      activeWorkflow = undefined;
      ctx.ui.setStatus("matt-pocock", undefined);
      return;
    }

    try {
      const content = loadWorkflowProcedure(restoredWorkflow);
      activeWorkflow = restoredWorkflow;
      ctx.ui.setStatus("matt-pocock", workflowStatus(activeWorkflow));
      pi.sendMessage({
        customType: "matt-pocock-procedure",
        content,
        display: false,
      }, { deliverAs: "nextTurn" });
    } catch (error) {
      activeWorkflow = undefined;
      ctx.ui.setStatus("matt-pocock", undefined);
      ctx.ui.notify(`Could not restore Matt Pocock workflow: ${String(error)}`, "warning");
    }
  });

  pi.on("before_agent_start", async (event) => {
    if (activeWorkflow) {
      return { systemPrompt: `${event.systemPrompt}\n\n${workflowGuidance(activeWorkflow)}` };
    }
    return { systemPrompt: `${event.systemPrompt}\n\n${availableWorkflowsGuidance()}` };
  });

  pi.registerTool({
    name: "matt_pocock_workflow",
    label: "Matt Pocock Workflow",
    description: "Activate or transition a Matt Pocock engineering workflow procedure (idea-to-ship, hard-bug, triage, wayfinding, architecture). Use when a structured workflow is appropriate for the task.",
    promptSnippet: "Activate or transition a Matt Pocock engineering workflow procedure",
    promptGuidelines: [
      "Use matt_pocock_workflow when the task matches a structured engineering workflow: idea-to-ship for features, hard-bug for difficult bugs, triage for raw issues, wayfinding for large ambiguous goals, or architecture for refactoring.",
    ],
    parameters: Type.Object({
      route: stringEnum(["idea-to-ship", "hard-bug", "triage", "wayfinding", "architecture"] as const, {
        description: "Target engineering workflow route to activate or transition.",
      }),
      procedure: Type.Optional(Type.String({ description: "Specific procedure to activate or transition to." })),
      phase: Type.Optional(Type.String({ description: "Target workflow phase." })),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const route = findWorkflowRoute(params.route);
      if (!route) {
        throw new Error(`Unknown Matt Pocock route: ${params.route}`);
      }
      const procedure = params.procedure ?? route.procedure;
      const phase = params.phase ?? (params.procedure ? phaseForProcedure(params.procedure) : route.phase);
      const state: WorkflowState = {
        route: route.route,
        procedure,
        phase,
      };

      const content = loadWorkflowProcedure(state);
      persistWorkflow(state);
      ctx.ui.setStatus("matt-pocock", workflowStatus(state));

      return {
        content: [{ type: "text", text: content }],
        details: state,
      };
    },
  });

  pi.registerCommand("matt-pocock", {
    description: "Route and manage Matt Pocock engineering workflows",
    handler: async (args, ctx) => {
      const command = args.trim();
      if (!command) {
        if (!ctx.hasUI) {
          ctx.ui.notify("Usage: /matt-pocock <route | status | transition | end>", "error");
          return;
        }
        await showMenu(ctx);
        return;
      }
      if (command === "status") {
        showStatus(ctx);
        return;
      }
      if (command === "transition") {
        if (!ctx.hasUI) {
          ctx.ui.notify("Choose a transition from the interactive /matt-pocock menu.", "error");
          return;
        }
        await chooseTransition(ctx);
        return;
      }
      if (command === "end") {
        activeWorkflow = undefined;
        pi.appendEntry(WORKFLOW_STATE_ENTRY, { active: false });
        ctx.ui.setStatus("matt-pocock", undefined);
        ctx.ui.notify("Matt Pocock workflow ended.", "info");
        return;
      }

      const state = parseRoute(command);
      if (!state) {
        ctx.ui.notify("Usage: /matt-pocock [route | status | transition | end]", "error");
        return;
      }
      activateWorkflow(state, ctx);
    },
  });
}

