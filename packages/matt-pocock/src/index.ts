import {
  keyHint,
  type ExtensionAPI,
  type ExtensionCommandContext,
  type ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { Text, truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import {
  eventToolLifecycle,
  formatToolErrorLine,
  renderToolLifecycle,
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

function safeExpandHint(): string {
  try {
    const hint = keyHint("app.tools.expand", "to expand");
    return String(hint);
  } catch {
    return "to expand";
  }
}

let activeWorkflow: WorkflowState | undefined;

function persistWorkflow(state: WorkflowState): void {
  activeWorkflow = state;
  pi.appendEntry(WORKFLOW_STATE_ENTRY, state);
}

function loadWorkflowProcedure(state: WorkflowState): string {
  const normalized = normalizeProcedureName(state.procedure);
  const allowedProcedures = transitionProcedures(state.route);
  if (!allowedProcedures.includes(normalized)) {
    throw new Error(`Procedure ${state.procedure} is not available for route ${state.route}`);
  }
  return procedurePrompt(state.route, normalized, state.phase);
}

function injectProcedure(content: string): void {
  pi.sendUserMessage(content, { deliverAs: "followUp" });
}

function activateWorkflow(state: WorkflowState, ctx: ExtensionContext): void {
  const content = loadWorkflowProcedure(state);
  persistWorkflow(state);
  ctx.ui.setStatus("matt-pocock", undefined);
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
  ctx.ui.notify(`Matt Pocock workflow: ${formatReadableWorkflowSubject(activeWorkflow.route, activeWorkflow.phase)}`, "info");
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
      ctx.ui.setStatus("matt-pocock", undefined);
      pi.sendMessage({
        customType: "matt-pocock-procedure",
        content,
        display: false,
        details: activeWorkflow,
      }, { deliverAs: "nextTurn" });
    } catch (error) {
      activeWorkflow = undefined;
      ctx.ui.setStatus("matt-pocock", undefined);
      ctx.ui.notify(`Could not restore Matt Pocock workflow: ${String(error)}`, "warning");
    }
  });

  if (typeof pi.registerMessageRenderer === "function") {
    pi.registerMessageRenderer("matt-pocock-procedure", (message, { expanded }, theme) => {
      const details = (message.details ?? {}) as Partial<WorkflowState>;
      const route = details.route ?? (activeWorkflow?.route || "workflow");
      const phase = details.phase ?? (activeWorkflow?.phase || "active");
      const subject = formatReadableWorkflowSubject(route, phase);
      const content = typeof message.content === "string" ? message.content : "";
      const detailLines = content.split("\n").filter((line) => line.trim());
      const expandable = detailLines.length > 0;
      return {
        render: (width: number) => {
          const lines = expanded
            ? detailLines.flatMap((line) => wrapTextWithAnsi(safeDisplayText(line), Math.max(1, width - 2)))
            : detailLines;
          return renderToolLifecycle(
            eventToolLifecycle("matt pocock · workflow", subject, {
              details: lines,
            }),
            {
              width,
              expanded,
              expandHint: safeExpandHint(),
              expandable,
              theme,
              fit: truncateToWidth,
              visibleWidth,
            },
          );
        },
        invalidate: () => {},
      };
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
    parameters: Type.Object({
      route: stringEnum(["idea-to-ship", "hard-bug", "triage", "wayfinding", "architecture"] as const, {
        description: "Target engineering workflow route to activate or transition.",
      }),
      procedure: Type.Optional(Type.String({ description: "Specific procedure to activate or transition to." })),
      phase: Type.Optional(Type.String({ description: "Target workflow phase." })),
    }),
    renderShell: "self",
    renderCall: () => new Text("", 0, 0),
    renderResult(result, options, theme, context) {
      const text = result.content.find((part) => part.type === "text")?.text ?? "";
      if (context.isError) {
        return new Text(theme.fg("error", formatToolErrorLine(text)), 0, 0);
      }
      const details = (result.details ?? {}) as WorkflowState;
      const route = details.route ?? (context.args as { route?: string })?.route ?? "workflow";
      const phase = details.phase ?? "active";
      const subject = formatReadableWorkflowSubject(route, phase);
      const detailLines = text.split("\n").filter((line) => line.trim());
      const expandable = detailLines.length > 0;
      return {
        render: (width: number) => {
          const lines = options.expanded
            ? detailLines.flatMap((line) => wrapTextWithAnsi(safeDisplayText(line), Math.max(1, width - 2)))
            : detailLines;
          return renderToolLifecycle(
            eventToolLifecycle("matt pocock · workflow", subject, {
              details: lines,
            }),
            {
              width,
              expanded: options.expanded,
              expandHint: safeExpandHint(),
              expandable,
              theme,
              fit: truncateToWidth,
              visibleWidth,
            },
          );
        },
        invalidate: () => {},
      };
    },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const route = findWorkflowRoute(params.route);
      if (!route) {
        throw new Error(`Unknown Matt Pocock route: ${params.route}`);
      }
      const procedure = params.procedure ? normalizeProcedureName(params.procedure) : route.procedure;
      const phase = params.phase ?? (params.procedure ? phaseForProcedure(procedure) : route.phase);
      const state: WorkflowState = {
        route: route.route,
        procedure,
        phase,
      };

      const content = loadWorkflowProcedure(state);
      persistWorkflow(state);
      ctx.ui.setStatus("matt-pocock", undefined);

      return {
        content: [{ type: "text", text: content }],
        details: state,
      };
    },
  });

  pi.registerTool({
    name: "matt_pocock_ask",
    label: "Matt Pocock Ask",
    description: "Ask the user an interactive question with recommended options, timeout handling, and custom answer input using Pi UI selection.",
    promptSnippet: "Ask the user a structured question with suggested choices, timeout fallback, and custom answer support",
    promptGuidelines: [
      "Use matt_pocock_ask when interviewing the user or asking for workflow decisions (e.g. during grilling/shaping/scoping). Provide 2-4 options, put the recommended option first or mark it '(Recommended)', and specify a timeout.",
    ],
    parameters: Type.Object({
      question: Type.String({ description: "The interview or decision question to ask the user." }),
      options: Type.Array(Type.String(), {
        description: "2 to 4 suggested options. Put the recommended option first or mark it '(Recommended)'.",
      }),
      recommended: Type.Optional(Type.String({
        description: "The recommended option (used as default or timeout fallback).",
      })),
      timeout_seconds: Type.Optional(Type.Number({
        description: "Timeout in seconds waiting for user response (default: 60, set <=0 for no timeout).",
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
        timed_out?: boolean;
        source?: string;
      };
      const answer = detailsObj.answer ?? text;
      const question = params.question ? safeDisplayText(params.question) : "question";
      const subject = answer ? `${question} → ${safeDisplayText(answer)}` : question;
      const effectiveDetails = [
        `Question: ${question}`,
        `Answer: ${safeDisplayText(answer || "(none)")}`,
        detailsObj.timed_out ? "Status: timed out (used default/fallback)" : undefined,
        detailsObj.is_custom ? "Source: custom input" : undefined,
        params.options && params.options.length ? `Options:\n${params.options.map((opt) => `  - ${opt}`).join("\n")}` : undefined,
      ].filter((line): line is string => Boolean(line));

      const expandable = effectiveDetails.length > 0;
      return {
        render: (width: number) => {
          const detailLines = options.expanded
            ? effectiveDetails.flatMap((line) => wrapTextWithAnsi(safeDisplayText(line), Math.max(1, width - 2)))
            : effectiveDetails;
          return renderToolLifecycle(
            eventToolLifecycle("matt pocock · ask", subject, {
              details: detailLines,
            }),
            {
              width,
              expanded: options.expanded,
              expandHint: safeExpandHint(),
              expandable,
              theme,
              fit: truncateToWidth,
              visibleWidth,
            },
          );
        },
        invalidate: () => {},
      };
    },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const allowCustom = params.allow_custom ?? true;
      const timeoutSec = params.timeout_seconds !== undefined ? params.timeout_seconds : 60;
      const timeoutMs = timeoutSec > 0 ? timeoutSec * 1000 : undefined;
      const recommendedOption = params.recommended
        ?? params.options.find((opt) => opt.includes("(Recommended)"))
        ?? params.options[0];

      if (!ctx.hasUI) {
        return {
          content: [{
            type: "text",
            text: `[No UI available] Selected fallback: ${recommendedOption ?? "none"}`,
          }],
          details: {
            answer: recommendedOption,
            source: "fallback_no_ui",
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
        if (recommendedOption) {
          return {
            content: [{
              type: "text",
              text: `[Timeout / No selection] Proceeding with recommended option: ${recommendedOption}`,
            }],
            details: {
              answer: recommendedOption,
              timed_out: true,
              source: "timeout_recommended",
            },
          };
        }
        return {
          content: [{
            type: "text",
            text: "[Cancelled] No answer selected and no recommended fallback provided.",
          }],
          details: {
            answer: undefined,
            timed_out: true,
            source: "cancelled",
          },
        };
      }

      if (selected === customOptionLabel) {
        const customInput = await ctx.ui.input(params.question, "Enter your answer...");
        const finalAnswer = customInput?.trim() || recommendedOption || "";
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

