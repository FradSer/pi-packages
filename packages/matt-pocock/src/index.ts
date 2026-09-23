import { randomUUID } from "node:crypto";
import {
  keyHint,
  type ExtensionAPI,
  type ExtensionCommandContext,
  type ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";
import {
  bindLifecycleRenderers,
  clearPiStatus,
  eventToolLifecycle,
  fieldLine,
  notifyPi,
  safeDisplayText,
  startedToolLifecycle,
} from "@fradser/pi-kit";
import {
  isNativeDialogSupported,
  loadConfig,
  macosChooseFromList,
  macosInputDialog,
} from "./native-dialog.ts";
import { Type } from "typebox";
import {
  findProcedure,
  modelStandaloneCapabilities,
  standaloneCapabilities,
  workflowDefinitions,
  workflowPlacement,
} from "./catalog.ts";
import { resolveAccessibleReference, resolveProcedureBundle, resolveProcedureDelta, resolveWorkflowContext } from "./resolver.ts";
/** Geometry bound once: every Matt Pocock row shares hint and wrapping. */
const mattPocockRows = bindLifecycleRenderers({
  fit: truncateToWidth,
  visibleWidth,
  wrapDetail: (line, width) => wrapTextWithAnsi(line, Math.max(1, width)),
  expandHint: () => keyHint("app.tools.expand", "to expand"),
});

import {
  availableWorkflowsGuidance,
  findWorkflowRoute,
  formatReadableWorkflowSubject,
  latestWorkflowRecord,
  readablePhaseTitle,
  readableRouteTitle,
  routeEntryState,
  transitionState,
  workflowGuidance,
  workflowRoutes,
  withDeliveryDefaults,
  WORKFLOW_STATE_ENTRY,
  WORKFLOW_STATE_VERSION,
  type TerminalWorkflowState,
  type WorkflowState,
} from "./workflow.ts";

const ACTIVE_TOOLS = ["matt_pocock_active", "matt_pocock_ask"] as const;
const PROCEDURE_ENTRY = "matt-pocock-procedure";

/** Session details for one delivered procedure: a workflow state, a standalone capability, and the user's own task. */
type ProcedureDetails = Partial<WorkflowState> & { mode?: string; capability?: string; request?: string };

/** The block body: the user's own task when given, otherwise what they started. */
function procedureSubject(details: ProcedureDetails): string {
  const request = details.request?.trim();
  if (request) return request;
  if (details.phase) return readablePhaseTitle(details.phase);
  return details.capability ?? "";
}

function stringEnum(values: string[], options?: Record<string, unknown>) {
  return Type.Unsafe<string>({ type: "string", enum: values, ...options });
}

function workflowGatewayParameters() {
  const routes = workflowRoutes().map((route) => route.route);
  const capabilities = modelStandaloneCapabilities().map((capability) => capability.id);
  return Type.Union([
    Type.Object({
      mode: Type.Literal("workflow", { description: "Start a persisted multi-step engineering workflow." }),
      route: stringEnum(routes, { description: "Workflow route to start." }),
    }),
    Type.Object({
      mode: Type.Literal("capability", { description: "Run a curated standalone capability without persistent workflow state." }),
      capability: stringEnum(capabilities, { description: "Standalone capability to run." }),
    }),
    Type.Object({
      mode: Type.Literal("reference", { description: "Load a reference disclosed by a standalone capability." }),
      capability: Type.String({ description: "Standalone capability id from the injected capability context." }),
      reference: Type.String({ description: "Disclosed reference id returned by the capability." }),
    }),
  ]);
}

function activeWorkflowParameters() {
  return Type.Union([
    Type.Object({
      action: Type.Literal("transition"),
      target: Type.String({ description: "One procedure id from the current state's allowedNext list." }),
    }, { additionalProperties: false }),
    Type.Object({
      action: Type.Literal("load"),
      reference: Type.String({ description: "One reference id from the current state's availableReferences list." }),
    }, { additionalProperties: false }),
    Type.Object({ action: Type.Literal("complete") }, { additionalProperties: false }),
    Type.Object({
      action: Type.Literal("cancel"),
      reason: Type.String({ description: "Why this workflow is being cancelled." }),
    }, { additionalProperties: false }),
  ]);
}

function workflowEventSubject(action: "transition" | "complete" | "cancel", phase: string): string {
  const title = readablePhaseTitle(phase);
  return action === "transition" ? title : `${title} ${action === "complete" ? "completed" : "cancelled"}`;
}

let pi: ExtensionAPI;
let activeWorkflow: WorkflowState | undefined;

function refreshActiveTools(active: boolean): void {
  if (typeof pi.getActiveTools !== "function" || typeof pi.setActiveTools !== "function") return;
  const tools = pi.getActiveTools();
  const withoutActive = tools.filter((tool) => !ACTIVE_TOOLS.includes(tool as typeof ACTIVE_TOOLS[number]));
  pi.setActiveTools(active ? [...withoutActive, ...ACTIVE_TOOLS] : withoutActive);
}

/** Deliver a procedure as one lifecycle row: users see their own task, the model sees the whole body. */
function deliverProcedure(content: string, details: ProcedureDetails): void {
  pi.sendMessage({ customType: PROCEDURE_ENTRY, content, display: true, details }, { deliverAs: "followUp", triggerTurn: true });
}

function persistWorkflow(state: WorkflowState | TerminalWorkflowState): void {
  pi.appendEntry(WORKFLOW_STATE_ENTRY, state);
  activeWorkflow = state.status === "active" ? state : undefined;
  refreshActiveTools(state.status === "active");
}

function terminalState(status: "completed" | "cancelled", reason?: string): TerminalWorkflowState {
  if (!activeWorkflow) throw new Error("No active Matt Pocock workflow.");
  return {
    version: WORKFLOW_STATE_VERSION,
    workItemId: activeWorkflow.workItemId,
    route: activeWorkflow.route,
    procedure: activeWorkflow.procedure,
    phase: activeWorkflow.phase,
    status,
    reason,
  };
}

function availableReferences(state: WorkflowState): string[] {
  return resolveWorkflowContext(state.procedure, state.loadedReferences).availableReferences;
}

function stateContract(state: WorkflowState, action: string): string {
  const placement = workflowPlacement(state.route, state.procedure);
  return `\n\n## Workflow state contract\n- Addressed: ${state.workItemId} · ${state.route} · ${state.procedure}\n- Synchronous action: ${action}\n- Allowed next: ${placement?.allowedNext.join(", ") || "none"}\n- Available references: ${availableReferences(state).join(", ") || "none"}\n- Pending: workflow remains active\n- Next actor: agent`;
}

/** Delivered to the model, never rendered: the user's own words belong in the prompt. */
function userRequestSection(request: string): string {
  return request ? `\n\nUser target/request:\n${request}` : "";
}

/** Delivered when a procedure's body is already in the session, so the prompt is never empty. */
const ALREADY_DELIVERED = "Its instructions were delivered earlier in this session and are unchanged. Continue against them; do not re-request them.";

/**
 * The prompt for a workflow step, plus the state that records what it delivered.
 *
 * Only procedures this session has not been shown are embedded. A transition re-delivers
 * the active context every time, and a bundle carries its whole dependency closure, so
 * re-sending that closure would spend the context the work needs and end a long task early
 * for want of room rather than for want of work.
 */
function deliveryStep(state: WorkflowState, action: string, request = "", full = false): { text: string; state: WorkflowState } {
  const delta = resolveProcedureDelta(
    state.procedure,
    state.loadedReferences,
    full ? [] : state.deliveredProcedures,
  );
  const next: WorkflowState = { ...state, deliveredProcedures: delta.delivered };
  const body = delta.content ? delta.content : ALREADY_DELIVERED;
  return {
    text: `# Matt Pocock workflow procedure\n\nRoute: ${next.route}\nPhase: ${next.phase}\nWork item: ${next.workItemId}\n\n${body}${userRequestSection(request)}${stateContract(next, action)}`,
    state: next,
  };
}

function standalonePrompt(capability: string, request = ""): string {
  const definition = findProcedure(capability);
  if (!definition?.standalone) throw new Error(`Unknown standalone Matt Pocock capability: ${capability}`);
  const bundle = resolveProcedureBundle(definition.id);
  return `# Matt Pocock standalone capability\n\nCapability: ${definition.id}\nPersistent workflow state: none\nAvailable references: ${bundle.availableReferences.join(", ") || "none"}\n\n${bundle.content}${userRequestSection(request)}`;
}

function standaloneReferencePrompt(capability: string, reference: string): string {
  const definition = findProcedure(capability);
  if (!definition?.standalone) {
    throw new Error(`Capability ${capability} is not a standalone Matt Pocock capability.`);
  }
  const bundle = resolveAccessibleReference(definition.id, [], reference);
  return `# Matt Pocock standalone reference\n\nCapability: ${definition.id}\nReference: ${bundle.root}\nPersistent workflow state: none\nAvailable references: ${bundle.availableReferences.join(", ") || "none"}\n\n${bundle.content}`;
}

function startWorkflow(route: string): WorkflowState {
  if (!findWorkflowRoute(route)) throw new Error(`Unknown Matt Pocock route: ${route}`);
  const state = routeEntryState(route, randomUUID());
  if (!state) throw new Error(`Workflow ${route} has no catalog entry procedure.`);
  resolveProcedureBundle(state.procedure);
  persistWorkflow(state);
  return state;
}

function loadActiveReference(reference: string): { state: WorkflowState; content: string } {
  if (!activeWorkflow) throw new Error("No active Matt Pocock workflow.");
  const bundle = resolveAccessibleReference(activeWorkflow.procedure, activeWorkflow.loadedReferences, reference);
  const loadedReferences = [...new Set([...activeWorkflow.loadedReferences, ...bundle.loaded])];
  // The reference's own closure is deduplicated too: a reference whose body is already in
  // the session does not need to arrive twice.
  const delta = resolveProcedureDelta(reference, [], activeWorkflow.deliveredProcedures);
  const state: WorkflowState = { ...activeWorkflow, loadedReferences, deliveredProcedures: delta.delivered };
  persistWorkflow(state);
  return {
    state,
    content: `# Matt Pocock workflow reference\n\nWork item: ${state.workItemId}\nReference: ${bundle.root}\n\n${delta.content || ALREADY_DELIVERED}${stateContract(state, `loaded reference ${bundle.root}`)}`,
  };
}

function routeChoices(): string[] {
  return workflowRoutes().map((route) => `${route.label} — ${route.description}`);
}

function routeFromChoice(choice: string): string | undefined {
  return workflowRoutes().find((route) => choice.startsWith(route.label))?.route;
}

function capabilityChoices(): string[] {
  return standaloneCapabilities().map((capability) => `${capability.label} — ${capability.description ?? capability.id}`);
}

function capabilityFromChoice(choice: string): string | undefined {
  return standaloneCapabilities().find((capability) => choice.startsWith(`${capability.label} —`))?.id;
}

async function chooseRoute(ctx: ExtensionCommandContext): Promise<void> {
  const choice = await ctx.ui.select("Start Matt Pocock workflow", routeChoices());
  if (!choice) return;
  const route = routeFromChoice(choice);
  if (!route) return;
  const state = startWorkflow(route);
  clearPiStatus(ctx.ui, "matt-pocock");
  const step = deliveryStep(state, "started workflow");
  persistWorkflow(step.state);
  deliverProcedure(step.text, { ...step.state, request: "" });
}

async function chooseCapability(ctx: ExtensionCommandContext): Promise<void> {
  const choice = await ctx.ui.select("Run Matt Pocock capability", capabilityChoices());
  if (!choice) return;
  const capability = capabilityFromChoice(choice);
  if (capability) deliverProcedure(standalonePrompt(capability), { mode: "capability", capability, request: "" });
}

/** Apply one catalog-legal transition, whether chosen from the menu or named on the command. */
function applyTransition(ctx: ExtensionCommandContext, target: string): void {
  if (!activeWorkflow) {
    notifyPi(ctx.ui, "No active Matt Pocock workflow.", "warning");
    return;
  }
  const state = transitionState(activeWorkflow, target);
  resolveProcedureBundle(state.procedure);
  const step = deliveryStep(state, `transitioned to ${state.procedure}`);
  persistWorkflow(step.state);
  deliverProcedure(step.text, { ...step.state, request: "" });
}

async function chooseTransition(ctx: ExtensionCommandContext): Promise<void> {
  if (!activeWorkflow) {
    notifyPi(ctx.ui, "No active Matt Pocock workflow.", "warning");
    return;
  }
  const next = workflowPlacement(activeWorkflow.route, activeWorkflow.procedure)?.allowedNext ?? [];
  if (next.length === 0) {
    notifyPi(ctx.ui, "This workflow has no next procedure. Complete or cancel it.", "info");
    return;
  }
  const choice = await ctx.ui.select(`Transition ${activeWorkflow.route} from ${activeWorkflow.procedure}`, next);
  if (!choice) return;
  applyTransition(ctx, choice);
}

function completeWorkflow(ctx: ExtensionContext): void {
  const terminal = terminalState("completed");
  persistWorkflow(terminal);
  clearPiStatus(ctx.ui, "matt-pocock");
  notifyPi(ctx.ui, `Matt Pocock workflow completed: ${terminal.workItemId}`, "info");
}

function cancelWorkflow(ctx: ExtensionContext, reason: string): void {
  const terminal = terminalState("cancelled", reason);
  persistWorkflow(terminal);
  clearPiStatus(ctx.ui, "matt-pocock");
  notifyPi(ctx.ui, `Matt Pocock workflow cancelled: ${terminal.workItemId}`, "info");
}

function showStatus(ctx: ExtensionContext): void {
  if (!activeWorkflow) {
    notifyPi(ctx.ui, "Matt Pocock workflow: inactive", "info");
    return;
  }
  notifyPi(
    ctx.ui,
    `Matt Pocock workflow: ${formatReadableWorkflowSubject(activeWorkflow.route, activeWorkflow.phase)} · ${activeWorkflow.workItemId}`,
    "info",
  );
}

async function showMenu(ctx: ExtensionCommandContext): Promise<void> {
  const choices = activeWorkflow
    ? [START_TASK_CHOICE, "View current workflow", "Transition current workflow", "Complete current workflow", "Cancel current workflow", "Run a standalone capability"]
    : [START_TASK_CHOICE, "Start a workflow", "Run a standalone capability", "View current workflow"];
  const choice = await ctx.ui.select("Matt Pocock", choices);
  if (!choice) return;
  if (choice === START_TASK_CHOICE) return startFromContext(ctx);
  if (choice === "Start a workflow") return chooseRoute(ctx);
  if (choice === "Run a standalone capability") return chooseCapability(ctx);
  if (choice === "View current workflow") return showStatus(ctx);
  if (choice === "Transition current workflow") return chooseTransition(ctx);
  if (choice === "Complete current workflow") return completeWorkflow(ctx);
  cancelWorkflow(ctx, "Cancelled by user from the Matt Pocock menu.");
}

const START_TASK_CHOICE = "Start a task";

function contextRoutingPrompt(cancelledWorkflow: boolean): string {
  return `Infer the user's current task from recent conversation context and route and execute it through the relevant Matt Pocock workflow or standalone capability.\n\n${cancelledWorkflow ? "The previous active workflow has been cancelled because this is a new request. " : ""}Use matt_pocock_workflow with mode workflow for a structured multi-step engineering task, or mode capability for a matching standalone capability. If neither applies, handle the request normally. Begin immediately once the route is clear.`;
}

function startFromContext(ctx: ExtensionCommandContext): void {
  const cancelledWorkflow = Boolean(activeWorkflow);
  if (activeWorkflow) {
    persistWorkflow(terminalState("cancelled", "Superseded by a new /matt-pocock context routing request."));
  }
  clearPiStatus(ctx.ui, "matt-pocock");
  deliverProcedure(contextRoutingPrompt(cancelledWorkflow), { request: "" });
}

function workflowRoutingPrompt(prompt: string, cancelledWorkflow: boolean): string {
  return `Route and execute this request through the relevant Matt Pocock workflow or standalone capability: ${prompt}\n\n${cancelledWorkflow ? "The previous active workflow has been cancelled because this is a new request. " : ""}Use matt_pocock_workflow with mode workflow for a structured multi-step engineering task, or mode capability for a matching standalone capability. If neither applies, handle the request normally. Begin immediately once the route is clear.`;
}

export default function mattPocock(extensionApi: ExtensionAPI): void {
  pi = extensionApi;

  pi.on("session_start", async (_event, ctx) => {
    const record = latestWorkflowRecord(ctx.sessionManager.getBranch());
    if (!record || record.status !== "active") {
      activeWorkflow = undefined;
      refreshActiveTools(false);
      clearPiStatus(ctx.ui, "matt-pocock");
      return;
    }

    try {
      if (!workflowPlacement(record.route, record.procedure)) {
        throw new Error(`Procedure ${record.procedure} is not part of workflow ${record.route}.`);
      }
      // A restore is a context boundary: this session may have been compacted or restarted,
      // so the whole active context is re-delivered rather than deduplicated. Delivery
      // tracking only suppresses repeats inside one continuous session.
      const restored = withDeliveryDefaults(record);
      const step = deliveryStep(restored, "restored workflow", "", true);
      // Not persisted here: session_start must not write to the branch. The next transition
      // records the delivery set it has actually shown.
      activeWorkflow = step.state;
      refreshActiveTools(true);
      clearPiStatus(ctx.ui, "matt-pocock");
      pi.sendMessage({
        customType: PROCEDURE_ENTRY,
        content: step.text,
        display: false,
        details: step.state,
      }, { deliverAs: "nextTurn" });
    } catch (error) {
      activeWorkflow = record;
      const cancelled = terminalState("cancelled", `Restore validation failed: ${String(error)}`);
      persistWorkflow(cancelled);
      clearPiStatus(ctx.ui, "matt-pocock");
      const valid = workflowDefinitions(record.route).map((definition) => definition.id);
      notifyPi(
        ctx.ui,
        `Could not restore Matt Pocock workflow: ${String(error)} Valid procedures for ${record.route}: ${valid.join(", ") || "none"}.`,
        "warning",
      );
    }
  });

  if (typeof pi.registerMessageRenderer === "function") {
    pi.registerMessageRenderer(PROCEDURE_ENTRY, (message, options, theme) => {
      const details = (message.details ?? {}) as ProcedureDetails;
      // The user's own task stays verbatim in a block under the head, on pi's native user-message band.
      return mattPocockRows.message(() => startedToolLifecycle("matt pocock", procedureSubject(details), {
        label: "started",
        verbatimSubject: true,
        subjectBlock: true,
        bgToken: "userMessageBg",
      }))(message, options, theme);
    });
  }

  pi.on("before_agent_start", async (event) => ({
    systemPrompt: `${event.systemPrompt}\n\n${activeWorkflow
      ? workflowGuidance(activeWorkflow, availableReferences(activeWorkflow))
      : availableWorkflowsGuidance()}`,
  }));

  pi.registerTool({
    name: "matt_pocock_workflow",
    label: "Matt Pocock Gateway",
    description: "Start a Matt Pocock engineering workflow, run a curated standalone capability, or load a reference disclosed by that capability. Workflows cover structured multi-step engineering; standalone capabilities cover focused methods and are listed in the injected capability catalog.",
    promptSnippet: "Start a Matt Pocock workflow or run a standalone capability",
    promptGuidelines: [
      "mode workflow: structured multi-step engineering task (idea-to-ship for features, hard-bug for non-trivial bugs, architecture for deepening/refactoring, wayfinding for ambiguous maps, triage for issues).",
      "mode capability: a curated capability directly matches the request.",
      "mode reference: a reference named in a capability result.",
      "Start with matt_pocock_workflow; the started workflow carries its procedure and next-step guidance.",
    ],
    parameters: workflowGatewayParameters(),
    renderShell: "self",
    renderCall: () => mattPocockRows.emptyCall(),
    renderResult(result, options, theme, context) {
      const details = (result.details ?? {}) as { mode?: string; route?: string; phase?: string; capability?: string; reference?: string };
      const subject = details.mode === "workflow"
        ? readablePhaseTitle(details.phase ?? "active")
        : details.mode === "reference"
          ? `${details.capability ?? "capability"} · ${details.reference ?? "reference"}`
          : details.capability ?? "standalone capability";
      const routeTitle = details.mode === "workflow" ? readableRouteTitle(details.route ?? "workflow") : undefined;
      const fields = routeTitle && routeTitle !== subject ? [fieldLine("route", routeTitle)] : [];
      return mattPocockRows.result(() => eventToolLifecycle("matt pocock", subject, { label: "started", details: fields }))(result, options, theme, context);
    },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      clearPiStatus(ctx.ui, "matt-pocock");
      if (params.mode === "workflow") {
        if (activeWorkflow) {
          throw new Error(`Workflow ${activeWorkflow.workItemId} is already active. Complete or cancel it before starting another.`);
        }
        const state = startWorkflow(params.route);
        const step = deliveryStep(state, "started workflow");
        persistWorkflow(step.state);
        return {
          content: [{ type: "text", text: step.text }],
          details: { mode: "workflow", ...step.state },
        };
      }
      if (params.mode === "reference") {
        const content = standaloneReferencePrompt(params.capability, params.reference);
        return {
          content: [{ type: "text", text: content }],
          details: { mode: "reference", capability: params.capability, reference: params.reference },
        };
      }
      const definition = findProcedure(params.capability);
      if (!definition?.standalone || definition.invocation !== "model") {
        throw new Error(`Capability ${params.capability} is not available to the model gateway.`);
      }
      return {
        content: [{ type: "text", text: standalonePrompt(definition.id) }],
        details: { mode: "capability", capability: definition.id },
      };
    },
  });

  pi.registerTool({
    name: "matt_pocock_active",
    label: "Matt Pocock Active Workflow",
    description: "Operate on the active Matt Pocock workflow: transition (target), load a reference (reference), complete, or cancel (reason).",
    promptSnippet: "Transition, load a reference, complete, or cancel the active Matt Pocock workflow",
    promptGuidelines: [
      'action transition: {"action": "transition", "target": "<one allowedNext id>"} — target is required.',
      'action load: {"action": "load", "reference": "<one availableReferences id>"} — reference is required.',
      'action complete: {"action": "complete"}.',
      'action cancel: {"action": "cancel", "reason": "<why>"} — reason is required.',
    ],
    parameters: activeWorkflowParameters(),
    renderShell: "self",
    renderCall: () => mattPocockRows.emptyCall(),
    renderResult(result, options, theme, context) {
      const details = (result.details ?? {}) as { action?: string; subject?: string; state?: { phase?: string; reason?: string } };
      // Saved results may still have route-based subjects; render from that event's phase, not active state.
      const subject = details.state?.phase && (details.action === "transition" || details.action === "complete" || details.action === "cancel")
        ? workflowEventSubject(details.action, details.state.phase)
        : details.subject ?? details.action ?? "workflow updated";
      const reason = details.action === "cancel" ? safeDisplayText(details.state?.reason ?? "").trim() : undefined;
      return mattPocockRows.result(() => eventToolLifecycle("matt pocock", subject, {
        label: "event",
        details: reason ? [fieldLine("reason", reason)] : [],
      }))(result, options, theme, context);
    },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      if (!activeWorkflow) throw new Error("No active Matt Pocock workflow.");
      if (params.action === "transition") {
        const state = transitionState(activeWorkflow, params.target);
        resolveProcedureBundle(state.procedure);
        const step = deliveryStep(state, `transitioned to ${state.procedure}`);
        persistWorkflow(step.state);
        clearPiStatus(ctx.ui, "matt-pocock");
        return {
          content: [{ type: "text", text: step.text }],
          details: { action: "transition", subject: workflowEventSubject("transition", state.phase), state: step.state },
        };
      }
      if (params.action === "load") {
        const loaded = loadActiveReference(params.reference);
        return {
          content: [{ type: "text", text: loaded.content }],
          details: { action: "load", subject: `loaded ${params.reference}`, state: loaded.state },
        };
      }
      const terminal = params.action === "complete"
        ? terminalState("completed")
        : terminalState("cancelled", params.reason);
      persistWorkflow(terminal);
      clearPiStatus(ctx.ui, "matt-pocock");
      const verb = terminal.status === "completed" ? "completed" : "cancelled";
      return {
        content: [{
          type: "text",
          text: `Workflow ${terminal.workItemId} ${verb}. Persistent active state cleared. Pending: none. Next actor: agent may handle unrelated work normally.`,
        }],
        details: { action: params.action, subject: workflowEventSubject(params.action, terminal.phase), state: terminal },
      };
    },
  });

  function isChineseText(text: string): boolean {
    return /[\u4e00-\u9fa5]/.test(text);
  }

  function deriveDialogTitle(explicitTitle?: string): string {
    if (explicitTitle && explicitTitle.trim()) return explicitTitle.trim();
    if (activeWorkflow) {
      return formatReadableWorkflowSubject(activeWorkflow.route, activeWorkflow.phase);
    }
    return "Decision";
  }

  function deriveDialogButtonNames(question: string): { ok: string; cancel: string } {
    const isZh = isChineseText(question);
    return {
      ok: isZh ? "确认" : "Select",
      cancel: isZh ? "取消" : "Cancel",
    };
  }

  pi.registerTool({
    name: "matt_pocock_ask",
    label: "Matt Pocock Ask",
    description: "Ask a structured workflow decision question via Pi UI selection.",
    promptSnippet: "Ask a structured question during the active Matt Pocock workflow",
    parameters: Type.Object({
      title: Type.Optional(Type.String({ description: "Short title summarizing the decision context; defaults to workflow route and phase." })),
      question: Type.String({ description: "The interview or decision question to ask the user." }),
      options: Type.Array(Type.String(), { description: "2 to 4 suggested options, recommended option first." }),
      recommended: Type.Optional(Type.String({ description: "The recommended option. When provided, timeout automatically adopts this option." })),
      timeout_seconds: Type.Optional(Type.Number({ description: "Seconds to wait; default 60; needs a recommended option." })),
      allow_custom: Type.Optional(Type.Boolean({ description: "Allow a custom typed answer; default true." })),
    }),
    renderShell: "self",
    renderCall: () => mattPocockRows.emptyCall(),
    renderResult(result, options, theme, context) {
      const text = result.content.find((part) => part.type === "text")?.text ?? "";
      const params = (context.args ?? {}) as { question?: string };
      const details = (result.details ?? {}) as { answer?: string; is_custom?: boolean; pending?: boolean; timed_out?: boolean; source?: string };
      const cleanAnswer = safeDisplayText(details.answer ?? text ?? "(none)").replace(/\t/g, "  ").trim();
      const answerLines = cleanAnswer.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
      const summary = details.pending
        ? ["Status: pending user decision"]
        : answerLines.map((line, index) => index === 0 ? `Answer: ${line}` : `  ${line}`);
      const metadata = [
        details.timed_out && details.source === "timeout_recommended" ? fieldLine("reason", "selection timed out (used recommendation)") : undefined,
        details.timed_out && details.pending ? fieldLine("reason", "selection timed out") : undefined,
        details.source === "no_ui" ? fieldLine("reason", "no UI available") : undefined,
        details.is_custom ? fieldLine("source", "custom input") : undefined,
      ].filter((line): line is string => Boolean(line));
      return mattPocockRows.result(() => eventToolLifecycle("matt pocock", safeDisplayText(params.question ?? "question"), {
        label: "ask",
        summary: summary.length > 0 ? summary : ["Answer: (none)"],
        details: metadata,
      }))(result, options, theme, context);
    },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      if (!activeWorkflow) throw new Error("No active Matt Pocock workflow.");
      if (!ctx.hasUI) {
        return {
          content: [{ type: "text", text: "[Pending user decision] No UI is available. Do not proceed until the user responds." }],
          details: { pending: true, source: "no_ui" },
        };
      }
      const allowCustom = params.allow_custom ?? true;
      const hasRecommended = typeof params.recommended === "string" && params.recommended.trim().length > 0;
      const timeoutMs = hasRecommended
        ? ((params.timeout_seconds !== undefined && params.timeout_seconds > 0) ? params.timeout_seconds * 1000 : 60 * 1000)
        : undefined;

      const customOption = "Type custom answer...";
      const choices = [...params.options];
      if (allowCustom && !choices.includes(customOption)) choices.push(customOption);

      const config = loadConfig();
      if (config.useNativeDialog && isNativeDialogSupported()) {
        try {
          const defaultItem = (hasRecommended && choices.includes(params.recommended!.trim()))
            ? params.recommended!.trim()
            : choices[0];
          const timeoutSeconds = hasRecommended
            ? ((params.timeout_seconds !== undefined && params.timeout_seconds > 0) ? params.timeout_seconds : 60)
            : undefined;

          const dialogTitle = deriveDialogTitle(params.title);
          const buttonNames = deriveDialogButtonNames(params.question);

          const nativeChoice = await macosChooseFromList({
            title: dialogTitle,
            prompt: params.question,
            items: choices,
            defaultItem,
            okButtonName: buttonNames.ok,
            cancelButtonName: buttonNames.cancel,
            timeoutSeconds,
          });

          if (nativeChoice.action === "timed_out") {
            if (hasRecommended) {
              const answer = params.recommended!.trim();
              return {
                content: [{ type: "text", text: `User selected (timeout default): ${answer}` }],
                details: { answer, is_custom: false, timed_out: true, pending: false, source: "timeout_recommended" },
              };
            }
            return {
              content: [{ type: "text", text: "[Pending user decision] Selection timed out. Do not proceed until the user responds." }],
              details: { pending: true, timed_out: true, source: "cancelled" },
            };
          }

          if (nativeChoice.action === "cancelled" || !nativeChoice.item) {
            return {
              content: [{ type: "text", text: "[Pending user decision] No answer was selected. Do not proceed until the user responds." }],
              details: { pending: true, timed_out: false, source: "cancelled" },
            };
          }

          if (nativeChoice.item === customOption) {
            const inputRes = await macosInputDialog({
              title: dialogTitle,
              prompt: params.question,
              defaultAnswer: "",
              buttons: [buttonNames.cancel, buttonNames.ok],
              defaultButton: buttonNames.ok,
              cancelButton: buttonNames.cancel,
            });
            const answer = inputRes.action === "confirmed" ? inputRes.text?.trim() : undefined;
            if (!answer) {
              return {
                content: [{ type: "text", text: "[Pending user decision] No custom answer was provided. Do not proceed until the user responds." }],
                details: { pending: true, source: "custom_input_cancelled" },
              };
            }
            return {
              content: [{ type: "text", text: `User answered (custom): ${answer}` }],
              details: { answer, is_custom: true, source: "custom_input" },
            };
          }

          return {
            content: [{ type: "text", text: `User selected: ${nativeChoice.item}` }],
            details: { answer: nativeChoice.item, is_custom: false, source: "choice_selected" },
          };
        } catch {
          // Graceful fallback to TUI on any native dialog error
        }
      }

      const selected = await ctx.ui.select(params.question, choices, timeoutMs !== undefined ? { timeout: timeoutMs } : undefined);
      if (selected === undefined) {
        if (hasRecommended) {
          const answer = params.recommended!.trim();
          return {
            content: [{ type: "text", text: `User selected (timeout default): ${answer}` }],
            details: { answer, is_custom: false, timed_out: true, pending: false, source: "timeout_recommended" },
          };
        }
        return {
          content: [{ type: "text", text: "[Pending user decision] No answer was selected. Do not proceed until the user responds." }],
          details: { pending: true, timed_out: false, source: "cancelled" },
        };
      }
      if (selected === customOption) {
        const answer = (await ctx.ui.input(params.question, "Enter your answer..."))?.trim();
        if (!answer) {
          return {
            content: [{ type: "text", text: "[Pending user decision] No custom answer was provided. Do not proceed until the user responds." }],
            details: { pending: true, source: "custom_input_cancelled" },
          };
        }
        return {
          content: [{ type: "text", text: `User answered (custom): ${answer}` }],
          details: { answer, is_custom: true, source: "custom_input" },
        };
      }
      return {
        content: [{ type: "text", text: `User selected: ${selected}` }],
        details: { answer: selected, is_custom: false, source: "choice_selected" },
      };
    },
  });

  pi.registerCommand("matt-pocock", {
    description: "Route and manage Matt Pocock workflows and standalone capabilities",
    handler: async (args, ctx) => {
      const command = args.trim();
      if (!command) {
        if (!ctx.hasUI) {
          notifyPi(ctx.ui, "Usage: /matt-pocock <route | capability> [task] | status | transition [target] | complete | cancel [reason]", "error");
          return;
        }
        await showMenu(ctx);
        return;
      }
      // `<route|capability> [task]` mirrors /impeccable: the first word selects, the rest is the user's own task.
      const token = command.match(/^\S+/)?.[0] ?? command;
      const task = command.slice(token.length).trim();
      if (token === "status" && !task) return showStatus(ctx);
      if (token === "transition" && !task) {
        if (!ctx.hasUI) {
          notifyPi(ctx.ui, "Name a target: /matt-pocock transition <target>, or use the interactive menu.", "error");
          return;
        }
        return chooseTransition(ctx);
      }
      if (token === "transition") return applyTransition(ctx, task);
      if (token === "complete" && !task) return completeWorkflow(ctx);
      if (token === "cancel" || token === "end") {
        return cancelWorkflow(ctx, task || `Cancelled by user with /matt-pocock ${token}.`);
      }

      if (findWorkflowRoute(token)) {
        if (activeWorkflow) throw new Error(`Workflow ${activeWorkflow.workItemId} is already active.`);
        const state = startWorkflow(token);
        clearPiStatus(ctx.ui, "matt-pocock");
        const step = deliveryStep(state, "started workflow", task);
        persistWorkflow(step.state);
        deliverProcedure(step.text, { ...step.state, request: task });
        return;
      }
      const capability = findProcedure(token);
      if (capability?.standalone) {
        deliverProcedure(standalonePrompt(capability.id, task), { mode: "capability", capability: capability.id, request: task });
        return;
      }

      const cancelledWorkflow = Boolean(activeWorkflow);
      if (activeWorkflow) {
        const terminal = terminalState("cancelled", "Superseded by a new /matt-pocock routing request.");
        persistWorkflow(terminal);
      }
      deliverProcedure(workflowRoutingPrompt(command, cancelledWorkflow), { request: command });
    },
  });
}
