import {
  keyHint,
  type ExtensionAPI,
  type ExtensionCommandContext,
  type ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { Text, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import {
  createStaticToolLifecycleMessageRenderer,
  clearPiStatus,
  createToolLifecycleResultRenderer,
  eventToolLifecycle,
  formatToolErrorLine,
  formatToolLifecycleTitle,
  notifyPi,
  safeDisplayText,
} from "@fradser/pi-kit";
import { Type } from "typebox";
import { procedurePrompt } from "./procedures.ts";
import {
  availableWorkflowsGuidance,
  findWorkflowRoute,
  formatReadableWorkflowSubject,
  latestWorkflowState,
  normalizeProcedureName,
  phaseForProcedure,
  transitionProcedureOptions,
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

function workflowRouteParameters<T extends string>(route: T) {
  return Type.Object({
    route: Type.Literal(route, { description: "Target engineering workflow route." }),
    procedure: Type.Optional(stringEnum(transitionProcedureOptions(route), {
      description: `Specific ${route} procedure. Omit it to use the route default.`,
    })),
    phase: Type.Optional(Type.String({ description: "Target workflow phase." })),
  });
}

function workflowToolParameters() {
  return Type.Union([
    workflowRouteParameters("idea-to-ship"),
    workflowRouteParameters("hard-bug"),
    workflowRouteParameters("triage"),
    workflowRouteParameters("wayfinding"),
    workflowRouteParameters("architecture"),
  ]);
}

function safeExpandHint(): string {
  try {
    const hint = keyHint("app.tools.expand", "to expand");
    return String(hint);
  } catch {
    return "to expand";
  }
}

let activeWorkflow: WorkflowState | undefined;

function setInterviewToolActive(active: boolean): void {
  const tools = pi.getActiveTools();
  const nextTools = active
    ? [...new Set([...tools, "matt_pocock_ask"])]
    : tools.filter((tool) => tool !== "matt_pocock_ask");
  pi.setActiveTools(nextTools);
}

function endWorkflow(ctx: ExtensionContext): void {
  activeWorkflow = undefined;
  pi.appendEntry(WORKFLOW_STATE_ENTRY, { active: false });
  setInterviewToolActive(false);
  clearPiStatus(ctx.ui, "matt-pocock");
}

function persistWorkflow(state: WorkflowState): void {
  activeWorkflow = state;
  pi.appendEntry(WORKFLOW_STATE_ENTRY, state);
}

function unavailableProcedureMessage(route: string, procedure: string): string {
  const allowedProcedures = transitionProcedures(route);
  const defaultProcedure = findWorkflowRoute(route)?.procedure ?? allowedProcedures[0];
  return `Procedure ${procedure} is not available for route ${route}. Valid procedures: ${allowedProcedures.join(", ")}. Omit procedure to use the route default (${defaultProcedure}). Do not switch routes to work around a procedure error.`;
}

function loadWorkflowProcedure(state: WorkflowState): string {
  const normalized = normalizeProcedureName(state.procedure);
  if (!transitionProcedures(state.route).includes(normalized)) {
    throw new Error(unavailableProcedureMessage(state.route, state.procedure));
  }
  return procedurePrompt(state.route, normalized, state.phase);
}

function injectProcedure(content: string): void {
  pi.sendUserMessage(content, { deliverAs: "followUp" });
}

function activateWorkflow(state: WorkflowState, ctx: ExtensionContext): void {
  const content = loadWorkflowProcedure(state);
  persistWorkflow(state);
  setInterviewToolActive(true);
  clearPiStatus(ctx.ui, "matt-pocock");
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
  endWorkflow(ctx);
  notifyPi(ctx.ui, "Matt Pocock workflow ended.", "info");
}

async function chooseTransition(ctx: ExtensionCommandContext): Promise<void> {
  if (!activeWorkflow) {
    notifyPi(ctx.ui, "No active Matt Pocock workflow.", "warning");
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
    notifyPi(ctx.ui, "Matt Pocock workflow: inactive", "info");
    return;
  }
  notifyPi(ctx.ui, `Matt Pocock workflow: ${formatReadableWorkflowSubject(activeWorkflow.route, activeWorkflow.phase)}`, "info");
}

function parseRoute(args: string): WorkflowState | undefined {
  const route = findWorkflowRoute(args);
  return route && { route: route.route, procedure: route.procedure, phase: route.phase };
}

function workflowRoutingPrompt(prompt: string, endedWorkflow: boolean): string {
  return `Route and execute this engineering request through the relevant Matt Pocock workflow: ${prompt}

${endedWorkflow ? "End any active Matt Pocock workflow first; that workflow has now been ended. " : ""}Determine whether the request needs a structured workflow. If it does, call matt_pocock_workflow with the matching route and procedure, then begin that procedure immediately. If it does not, explain briefly that no Matt Pocock workflow applies and handle the request normally. Do not ask whether to continue once the next action is clear.`;
}

let pi: ExtensionAPI;

export default function mattPocock(extensionApi: ExtensionAPI): void {
  pi = extensionApi;

  pi.on("session_start", async (_event, ctx) => {
    const restoredWorkflow = latestWorkflowState(ctx.sessionManager.getBranch());
    if (!restoredWorkflow) {
      activeWorkflow = undefined;
      setInterviewToolActive(false);
      clearPiStatus(ctx.ui, "matt-pocock");
      return;
    }

    try {
      const content = loadWorkflowProcedure(restoredWorkflow);
      activeWorkflow = restoredWorkflow;
      setInterviewToolActive(true);
      clearPiStatus(ctx.ui, "matt-pocock");
      pi.sendMessage({
        customType: "matt-pocock-procedure",
        content,
        display: false,
        details: activeWorkflow,
      }, { deliverAs: "nextTurn" });
    } catch (error) {
      endWorkflow(ctx);
      notifyPi(ctx.ui, `Could not restore Matt Pocock workflow: ${String(error)}`, "warning");
    }
  });

  if (typeof pi.registerMessageRenderer === "function") {
    pi.registerMessageRenderer("matt-pocock-procedure", (message, { expanded }, theme) => {
      const details = (message.details ?? {}) as Partial<WorkflowState>;
      const route = details.route ?? (activeWorkflow?.route || "workflow");
      const phase = details.phase ?? (activeWorkflow?.phase || "active");
      const subject = formatReadableWorkflowSubject(route, phase);
      return createStaticToolLifecycleMessageRenderer({
        createSpec: () => eventToolLifecycle("matt pocock", subject, { label: "workflow" }),
        expandHint: safeExpandHint(),
        fit: truncateToWidth,
        visibleWidth,
      })(message, { expanded }, theme);
    });
  }

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
    parameters: workflowToolParameters(),
    renderShell: "self",
    renderCall: () => new Text("", 0, 0),
    renderResult(result, _options, theme, context) {
      const text = result.content.find((part) => part.type === "text")?.text ?? "";
      if (context.isError) return new Text(theme.fg("error", formatToolErrorLine(text)), 0, 0);
      const details = (result.details ?? {}) as WorkflowState;
      const route = details.route ?? (context.args as { route?: string })?.route ?? "workflow";
      const phase = details.phase ?? "active";
      const title = formatToolLifecycleTitle({
        kind: "event",
        tool: "matt pocock",
        subject: formatReadableWorkflowSubject(route, phase),
        label: "workflow",
      });
      return new Text(theme.fg("customMessageLabel", theme.bold(title)), 0, 0);
    },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const route = findWorkflowRoute(params.route);
      if (!route) {
        throw new Error(`Unknown Matt Pocock route: ${params.route}`);
      }
      const requestedProcedure = params.procedure ? normalizeProcedureName(params.procedure) : route.procedure;
      const allowedProcedures = transitionProcedures(route.route);
      const fallsBackToRouteDefault = !allowedProcedures.includes(requestedProcedure);
      const state: WorkflowState = fallsBackToRouteDefault
        ? { route: route.route, procedure: route.procedure, phase: route.phase }
        : {
          route: route.route,
          procedure: requestedProcedure,
          phase: params.phase ?? (params.procedure ? phaseForProcedure(requestedProcedure) : route.phase),
        };
      const correction = fallsBackToRouteDefault && params.procedure
        ? `Note: requested procedure "${params.procedure}" is not available for route ${route.route}; activated the route default "${route.procedure}" at phase "${route.phase}" instead. Valid procedures for ${route.route}: ${allowedProcedures.join(", ")}. Do not switch routes to work around a procedure error.\n\n`
        : "";
      const content = `${correction}${loadWorkflowProcedure(state)}`;
      persistWorkflow(state);
      setInterviewToolActive(true);
      clearPiStatus(ctx.ui, "matt-pocock");

      return {
        content: [{ type: "text", text: content }],
        details: state,
      };
    },
  });

  pi.registerTool({
    name: "matt_pocock_ask",
    label: "Matt Pocock Ask",
    description: "Ask a structured interview or workflow decision question during the current Matt Pocock workflow using Pi UI selection.",
    promptSnippet: "Ask a structured question during the active Matt Pocock workflow",
    promptGuidelines: [
      "Use matt_pocock_ask only during the active Matt Pocock workflow for interview or workflow decisions (e.g. grilling/shaping/scoping). Provide 2-4 options, put the recommended option first or mark it '(Recommended)', and specify a timeout.",
    ],
    parameters: Type.Object({
      question: Type.String({ description: "The interview or decision question to ask the user." }),
      options: Type.Array(Type.String(), {
        description: "2 to 4 suggested options. Put the recommended option first or mark it '(Recommended)'.",
      }),
      recommended: Type.Optional(Type.String({
        description: "The recommended option shown to the user; it is never selected without an answer.",
      })),
      timeout_seconds: Type.Optional(Type.Number({
        description: "Seconds to wait for a user response (default: 60; timeout leaves the decision pending; set <=0 for no timeout).",
      })),
      allow_custom: Type.Optional(Type.Boolean({
        description: "Whether to allow the user to type a custom answer (default: true).",
      })),
    }),
    renderShell: "self",
    renderCall: () => new Text("", 0, 0),
    renderResult(result, options, theme, context) {
      const text = result.content.find((part) => part.type === "text")?.text ?? "";
      if (context.isError) {
        return new Text(theme.fg("error", formatToolErrorLine(text)), 0, 0);
      }
      const params = (context.args ?? {}) as { question?: string; options?: string[] };
      const detailsObj = (result.details ?? {}) as {
        answer?: string;
        is_custom?: boolean;
        pending?: boolean;
        timed_out?: boolean;
        source?: string;
      };
      const answer = detailsObj.answer ?? text;
      const question = params.question ? safeDisplayText(params.question) : "question";
      const subject = question;
      const summary = [detailsObj.pending
        ? "Status: pending user decision"
        : `Answer: ${safeDisplayText(answer || "(none)")}`];
      const effectiveDetails = [
        detailsObj.timed_out && detailsObj.pending ? "Reason: selection timed out" : undefined,
        detailsObj.source === "no_ui" ? "Reason: no UI available" : undefined,
        detailsObj.is_custom ? "Source: custom input" : undefined,
      ].filter((line): line is string => Boolean(line));

      return createToolLifecycleResultRenderer({
        createSpec: () => eventToolLifecycle("matt pocock", subject, {
          label: "ask",
          summary,
          details: effectiveDetails,
        }),
        expandHint: safeExpandHint(),
        fit: truncateToWidth,
        visibleWidth,
        renderError: (line, currentTheme) => new Text(currentTheme.fg("error", line), 0, 0),
      })(result, options, theme, context);
    },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const allowCustom = params.allow_custom ?? true;
      const timeoutSec = params.timeout_seconds !== undefined ? params.timeout_seconds : 60;
      const timeoutMs = timeoutSec > 0 ? timeoutSec * 1000 : undefined;
      if (!ctx.hasUI) {
        return {
          content: [{
            type: "text",
            text: "[Pending user decision] No UI is available to collect an answer. Do not proceed until the user responds.",
          }],
          details: {
            pending: true,
            source: "no_ui",
          },
        };
      }

      const customOptionLabel = "Type custom answer...";
      const choices = [...params.options];
      if (allowCustom && !choices.includes(customOptionLabel)) {
        choices.push(customOptionLabel);
      }

      const selected = await ctx.ui.select(
        params.question,
        choices,
        timeoutMs !== undefined ? { timeout: timeoutMs } : undefined,
      );

      if (selected === undefined) {
        return {
          content: [{
            type: "text",
            text: "[Pending user decision] No answer was selected. Do not proceed until the user responds.",
          }],
          details: {
            pending: true,
            timed_out: true,
            source: "timeout",
          },
        };
      }

      if (selected === customOptionLabel) {
        const finalAnswer = (await ctx.ui.input(params.question, "Enter your answer..."))?.trim();
        if (!finalAnswer) {
          return {
            content: [{
              type: "text",
              text: "[Pending user decision] No custom answer was provided. Do not proceed until the user responds.",
            }],
            details: {
              pending: true,
              source: "custom_input_cancelled",
            },
          };
        }
        return {
          content: [{
            type: "text",
            text: `User answered (custom): ${finalAnswer}`,
          }],
          details: {
            answer: finalAnswer,
            is_custom: true,
            source: "custom_input",
          },
        };
      }

      return {
        content: [{
          type: "text",
          text: `User selected: ${selected}`,
        }],
        details: {
          answer: selected,
          is_custom: false,
          source: "choice_selected",
        },
      };
    },
  });

  pi.registerCommand("matt-pocock", {
    description: "Route and manage Matt Pocock engineering workflows",
    handler: async (args, ctx) => {
      const command = args.trim();
      if (!command) {
        if (!ctx.hasUI) {
          notifyPi(ctx.ui, "Usage: /matt-pocock <route | status | transition | end>", "error");
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
          notifyPi(ctx.ui, "Choose a transition from the interactive /matt-pocock menu.", "error");
          return;
        }
        await chooseTransition(ctx);
        return;
      }
      if (command === "end") {
        endWorkflow(ctx);
        notifyPi(ctx.ui, "Matt Pocock workflow ended.", "info");
        return;
      }

      const state = parseRoute(command);
      if (state) {
        activateWorkflow(state, ctx);
        return;
      }

      const endedWorkflow = activeWorkflow !== undefined;
      if (endedWorkflow) endWorkflow(ctx);
      pi.sendUserMessage(workflowRoutingPrompt(command, endedWorkflow), { deliverAs: "followUp" });
    },
  });
}

