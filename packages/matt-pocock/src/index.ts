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
  setOwnedTools,
  startedToolLifecycle,
} from "@fradser/pi-kit";
import {
  isNativeDialogSupported,
  loadConfig,
  macosChooseFromList,
  macosInputDialog,
  type MacosChooseFromListResult,
} from "./native-dialog.ts";
import { Type, type Static } from "typebox";
import {
  findProcedure,
  modelStandaloneCapabilities,
  standaloneCapabilities,
  validateProcedureCatalog,
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

/** Tools activated only while a workflow is active. */
const ACTIVE_TOOLS = ["matt_pocock_active", "matt_pocock_ask"] as const;
/** Tool ids this extension registers. The gateway is unconditional: every routing
 *  prompt names it, so a session must never be left without it. */
const OWNED_TOOLS = ["matt_pocock_workflow", ...ACTIVE_TOOLS] as const;
const PROCEDURE_ENTRY = "matt-pocock-procedure";

/** Session details for one delivered procedure: a workflow state, a standalone capability, and the user's own task. */
type ProcedureDetails = Partial<WorkflowState> & { mode?: string; capability?: string; request?: string };

function readableProcedureTitle(id: string): string {
  return findProcedure(id)?.label ?? id;
}

/** The block body: the user's own task when given, otherwise what they started. */
function procedureSubject(details: ProcedureDetails): string {
  const request = details.request?.trim();
  if (request) return request;
  if (details.phase) return readablePhaseTitle(details.phase);
  return details.capability ? readableProcedureTitle(details.capability) : "";
}

function stringEnum(values: string[], options?: Record<string, unknown>) {
  return Type.Unsafe<string>({ type: "string", enum: values, ...options });
}

function workflowGatewayParameters() {
  const routes = workflowRoutes().map((route) => route.route);
  const capabilities = modelStandaloneCapabilities().map((capability) => capability.id);
  const branches = Type.Union([
    Type.Object({
      mode: Type.Literal("workflow", { description: "Start a persisted multi-step engineering workflow." }),
      route: stringEnum(routes, { description: "Workflow route to start." }),
    }, { additionalProperties: false }),
    Type.Object({
      mode: Type.Literal("capability", { description: "Run a curated standalone capability without persistent workflow state." }),
      capability: stringEnum(capabilities, { description: "Standalone capability to run." }),
    }, { additionalProperties: false }),
    Type.Object({
      mode: Type.Literal("reference", { description: "Load a reference disclosed by a standalone capability." }),
      capability: Type.String({ description: "Standalone capability id from the injected capability context." }),
      reference: Type.String({ description: "Disclosed reference id returned by the capability." }),
    }, { additionalProperties: false }),
  ]);
  // Keep exact branch validation and static narrowing while exposing every
  // operation to providers that inspect root properties before union branches.
  // Nullable hints prevent Pi v1 from dropping optional nulls before the original
  // branches perform their existing coercion/validation. They add no valid calls.
  return Type.Unsafe<Static<typeof branches>>({
    type: "object",
    properties: {
      mode: stringEnum(["workflow", "capability", "reference"]),
      route: Type.Union([stringEnum(routes), Type.Null()]),
      capability: Type.Union([Type.String(), Type.Null()]),
      reference: Type.Union([Type.String(), Type.Null()]),
    },
    required: ["mode"],
    additionalProperties: false,
    anyOf: branches.anyOf,
  });
}

function activeWorkflowParameters() {
  const branches = Type.Union([
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
  return Type.Unsafe<Static<typeof branches>>({
    type: "object",
    properties: {
      action: stringEnum(["transition", "load", "complete", "cancel"]),
      target: Type.Union([Type.String(), Type.Null()]),
      reference: Type.Union([Type.String(), Type.Null()]),
      reason: Type.Union([Type.String(), Type.Null()]),
    },
    required: ["action"],
    additionalProperties: false,
    anyOf: branches.anyOf,
  });
}

function workflowEventSubject(action: "transition" | "complete" | "cancel", phase: string): string {
  const title = readablePhaseTitle(phase);
  return action === "transition" ? title : `${title} ${action === "complete" ? "completed" : "cancelled"}`;
}

/** A timeout recommendation requires this deadline to actually dismiss the selector. */
async function selectDecision(
  ctx: ExtensionContext, question: string, choices: string[], signal?: AbortSignal, timeout?: number,
): Promise<MacosChooseFromListResult> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  if (signal?.aborted) abort();
  let timedOut = false;
  const timer = timeout === undefined ? undefined : setTimeout(() => {
    if (!controller.signal.aborted) {
      timedOut = true;
      controller.abort();
    }
  }, timeout);
  try {
    const item = await ctx.ui.select(question, choices, { signal: controller.signal, timeout });
    return { item, action: item !== undefined ? "selected" : timedOut ? "timed_out" : "cancelled" };
  } finally {
    if (timer) clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}

export default function mattPocock(extensionApi: ExtensionAPI): void {
  const errors = validateProcedureCatalog();
  if (errors.length > 0) throw new Error(`Invalid Matt Pocock catalog: ${errors.join("; ")}`);
  const pi = extensionApi;
  const standaloneReferences = new Map<string, string[]>();
  const pendingUI = new Set<AbortController>();
  let activeWorkflow: WorkflowState | undefined;

  function interruptPendingUI(): void {
    const controllers = [...pendingUI];
    pendingUI.clear();
    for (const controller of controllers) controller.abort();
  }

  async function withWorkflowSignal<T>(signal: AbortSignal | undefined, run: (signal: AbortSignal) => Promise<T>): Promise<T> {
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();
    pendingUI.add(controller);
    try {
      return await run(controller.signal);
    } finally {
      pendingUI.delete(controller);
      signal?.removeEventListener("abort", abort);
    }
  }

  async function selectWorkflowOption(
    ctx: ExtensionCommandContext,
    title: string,
    choices: string[],
    apply: (choice: string) => void | Promise<void>,
  ): Promise<void> {
    const workflow = activeWorkflow;
    await withWorkflowSignal(undefined, async (signal) => {
      const choice = await ctx.ui.select(title, choices, { signal });
      if (!choice || signal.aborted || activeWorkflow !== workflow) return;
      // Invoke the action before yielding: another await would let a replacement
      // workflow start between this identity check and the selected action.
      await apply(choice);
    });
  }

  function refreshActiveTools(active: boolean): void {
    if (typeof pi.getActiveTools !== "function" || typeof pi.setActiveTools !== "function") return;
    // The gateway is re-asserted on every write, never read back from the snapshot:
    // /matt-pocock delivers a routing prompt that names it, so a session that lost
    // it would instruct the model to call a tool it cannot see. See setOwnedTools.
    setOwnedTools(pi, { owned: OWNED_TOOLS, always: ["matt_pocock_workflow"], toggled: ACTIVE_TOOLS, enabled: active });
  }

  /** Deliver a procedure as one lifecycle row: users see their own task, the model sees the whole body. */
  function deliverProcedure(content: string, details: ProcedureDetails): void {
    pi.sendMessage({ customType: PROCEDURE_ENTRY, content, display: true, details }, { deliverAs: "followUp", triggerTurn: true });
  }

  function persistWorkflow(state: WorkflowState | TerminalWorkflowState): void {
    pi.appendEntry(WORKFLOW_STATE_ENTRY, state);
    activeWorkflow = state.status === "active" ? state : undefined;
    interruptPendingUI();
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

  function stateContract(state: WorkflowState, action: string, references: string[]): string {
    const placement = workflowPlacement(state.route, state.procedure);
    const calls = [
      ...(placement?.allowedNext ?? []).map((target) => JSON.stringify({ action: "transition", target })),
      ...references.map((reference) => JSON.stringify({ action: "load", reference })),
      JSON.stringify({ action: "complete" }),
      JSON.stringify({ action: "cancel", reason: "<why>" }),
    ];
    return `\n\n## Workflow state contract\n- Addressed: ${state.workItemId} · ${state.route} · ${state.procedure}\n- Synchronous action: ${action}\n- Allowed next: ${placement?.allowedNext.join(", ") || "none"}\n- Available references: ${references.join(", ") || "none"}\n- Pending: workflow remains active\n- Next actor: agent\n- Exact matt_pocock_active calls: ${calls.join("; ") || "none"}\n- Failed controls do not change the current procedure. Follow its returned state; do not act as if a failed transition succeeded.`;
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
      text: `# Matt Pocock workflow procedure\n\nRoute: ${next.route}\nPhase: ${next.phase}\nWork item: ${next.workItemId}\n\n${body}${userRequestSection(request)}${stateContract(next, action, delta.availableReferences)}`,
      state: next,
    };
  }

  function standalonePrompt(capability: string, request = ""): string {
    const definition = findProcedure(capability);
    if (!definition?.standalone) throw new Error(`Unknown standalone Matt Pocock capability: ${capability}`);
    const bundle = resolveProcedureBundle(definition.id);
    standaloneReferences.set(definition.id, []);
    return `# Matt Pocock standalone capability\n\nCapability: ${definition.id}\nPersistent workflow state: none\nAvailable references: ${bundle.availableReferences.join(", ") || "none"}\nStandalone decisions: ask the user in conversation; workflow-only tools do not belong to this capability.\n\n${bundle.content}${userRequestSection(request)}`;
  }

  function standaloneReferencePrompt(capability: string, reference: string): string {
    const definition = findProcedure(capability);
    if (!definition?.standalone) {
      throw new Error(`Capability ${capability} is not a standalone Matt Pocock capability.`);
    }
    const previous = standaloneReferences.get(definition.id) ?? [];
    const bundle = resolveAccessibleReference(definition.id, previous, reference);
    const loaded = [...new Set([...previous, ...bundle.loaded])];
    const context = resolveWorkflowContext(definition.id, loaded);
    standaloneReferences.set(definition.id, loaded);
    return `# Matt Pocock standalone reference\n\nCapability: ${definition.id}\nReference: ${bundle.root}\nPersistent workflow state: none\nAvailable references: ${context.availableReferences.join(", ") || "none"}\n\n${bundle.content}`;
  }

  /**
   * Begin a workflow and persist its state exactly once, carrying the delivery set
   * this first step shows. A second entry would read as two workflows begun, and a
   * persisted state without the set would re-deliver the whole closure on restore.
   */
  function startWorkflow(route: string, request = ""): { state: WorkflowState; text: string } {
    if (activeWorkflow) {
      throw new Error(`Workflow ${activeWorkflow.workItemId} is already active. Complete or cancel it before starting another.`);
    }
    if (!findWorkflowRoute(route)) throw new Error(`Unknown Matt Pocock route: ${route}`);
    const created = routeEntryState(route, randomUUID());
    if (!created) throw new Error(`Workflow ${route} has no catalog entry procedure.`);
    const step = deliveryStep(created, "started workflow", request);
    persistWorkflow(step.state);
    return step;
  }

  function loadActiveReference(reference: string): { state: WorkflowState; content: string } {
    if (!activeWorkflow) throw new Error("No active Matt Pocock workflow.");
    const bundle = resolveAccessibleReference(activeWorkflow.procedure, activeWorkflow.loadedReferences, reference);
    const loadedReferences = [...new Set([...activeWorkflow.loadedReferences, ...bundle.loaded])];
    // The reference's own closure is deduplicated too: a reference whose body is already in
    // the session does not need to arrive twice.
    const delta = resolveProcedureDelta(activeWorkflow.procedure, loadedReferences, activeWorkflow.deliveredProcedures);
    const state: WorkflowState = { ...activeWorkflow, loadedReferences, deliveredProcedures: delta.delivered };
    persistWorkflow(state);
    return {
      state,
      content: `# Matt Pocock workflow reference\n\nWork item: ${state.workItemId}\nReference: ${bundle.root}\n\n${delta.content || ALREADY_DELIVERED}${stateContract(state, `loaded reference ${bundle.root}`, delta.availableReferences)}`,
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
    await selectWorkflowOption(ctx, "Start Matt Pocock workflow", routeChoices(), (choice) => {
      const route = routeFromChoice(choice);
      if (!route) return;
      const step = startWorkflow(route);
      clearPiStatus(ctx.ui, "matt-pocock");
      deliverProcedure(step.text, { ...step.state, request: "" });
    });
  }

  async function chooseCapability(ctx: ExtensionCommandContext): Promise<void> {
    await selectWorkflowOption(ctx, "Run Matt Pocock capability", capabilityChoices(), (choice) => {
      const capability = capabilityFromChoice(choice);
      if (capability) deliverProcedure(standalonePrompt(capability), { mode: "capability", capability, request: "" });
    });
  }

  function transitionWorkflow(target: string): { state: WorkflowState; text: string } {
    if (!activeWorkflow) throw new Error("No active Matt Pocock workflow.");
    const state = transitionState(activeWorkflow, target);
    const step = deliveryStep(state, `transitioned to ${state.procedure}`);
    persistWorkflow(step.state);
    return step;
  }

  /** Both command and tool transitions use the same validated state change. */
  function applyTransition(ctx: ExtensionCommandContext, target: string): void {
    if (!activeWorkflow) {
      notifyPi(ctx.ui, "No active Matt Pocock workflow.", "warning");
      return;
    }
    const step = transitionWorkflow(target);
    deliverProcedure(step.text, { ...step.state, request: "" });
  }

  async function chooseTransition(ctx: ExtensionCommandContext): Promise<void> {
    if (!activeWorkflow) {
      notifyPi(ctx.ui, "No active Matt Pocock workflow.", "warning");
      return;
    }
    const { route, procedure } = activeWorkflow;
    const next = workflowPlacement(route, procedure)?.allowedNext ?? [];
    if (next.length === 0) {
      notifyPi(ctx.ui, "This workflow has no next procedure. Complete or cancel it.", "info");
      return;
    }
    const choices = next.map((id) => ({ id, label: readablePhaseTitle(workflowPlacement(route, id)!.phase) }));
    await selectWorkflowOption(ctx, `Transition ${readableRouteTitle(activeWorkflow.route)} from ${readablePhaseTitle(activeWorkflow.phase)}`, choices.map((choice) => choice.label),
      (label) => {
        const target = choices.find((choice) => choice.label === label)?.id;
        if (target) applyTransition(ctx, target);
      });
  }

  function endWorkflow(ctx: ExtensionContext, status: "completed" | "cancelled", reason?: string): void {
    const terminal = terminalState(status, reason);
    persistWorkflow(terminal);
    clearPiStatus(ctx.ui, "matt-pocock");
    notifyPi(ctx.ui, `Matt Pocock workflow ${status}: ${terminal.workItemId}`, "info");
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
    await selectWorkflowOption(ctx, "Matt Pocock", choices, (choice) => {
      if (choice === START_TASK_CHOICE) return startFromContext(ctx);
      if (choice === "Start a workflow") return chooseRoute(ctx);
      if (choice === "Run a standalone capability") return chooseCapability(ctx);
      if (choice === "View current workflow") return showStatus(ctx);
      if (choice === "Transition current workflow") return chooseTransition(ctx);
      if (choice === "Complete current workflow") return endWorkflow(ctx, "completed");
      endWorkflow(ctx, "cancelled", "Cancelled by user from the Matt Pocock menu.");
    });
  }

  const START_TASK_CHOICE = "Start a task";

  function startFromContext(ctx: ExtensionCommandContext): void {
    const cancelledWorkflow = Boolean(activeWorkflow);
    if (activeWorkflow) {
      persistWorkflow(terminalState("cancelled", "Superseded by a new /matt-pocock context routing request."));
    }
    clearPiStatus(ctx.ui, "matt-pocock");
    deliverProcedure(workflowRoutingPrompt("", cancelledWorkflow), { request: "" });
  }

  function workflowRoutingPrompt(prompt: string, cancelledWorkflow: boolean): string {
    const task = prompt
      ? `Route and execute this request through the relevant Matt Pocock workflow or standalone capability: ${prompt}`
      : "Infer the user's current task from recent conversation context and route and execute it through the relevant Matt Pocock workflow or standalone capability.";
    return `${task}\n\n${cancelledWorkflow ? "The previous active workflow has been cancelled because this is a new request. " : ""}Use matt_pocock_workflow with mode workflow for a structured multi-step engineering task, or mode capability for a matching standalone capability. If neither applies, handle the request normally. Begin immediately once the route is clear.`;
  }

  const restoreWorkflow = async (ctx: ExtensionContext): Promise<void> => {
    interruptPendingUI();
    standaloneReferences.clear();
    const branch = ctx.sessionManager.getBranch();
    const record = latestWorkflowRecord(branch);
    const newest = [...branch].reverse().find((entry) => entry.type === "custom" && entry.customType === WORKFLOW_STATE_ENTRY);
    if (newest && !record) {
      notifyPi(ctx.ui, "Could not restore Matt Pocock workflow: latest record is malformed or incompatible.", "warning");
    }
    if (!record || record.status !== "active") {
      activeWorkflow = undefined;
      refreshActiveTools(false);
      clearPiStatus(ctx.ui, "matt-pocock");
      return;
    }

    try {
      const placement = workflowPlacement(record.route, record.procedure);
      if (!placement || placement.phase !== record.phase) {
        throw new Error(`Procedure ${record.procedure} is not part of workflow ${record.route}.`);
      }
      // A restore is a context boundary: this session may have been compacted or restarted,
      // so the whole active context is re-delivered rather than deduplicated. Delivery
      // tracking only suppresses repeats inside one continuous session.
      const restored = withDeliveryDefaults(record);
      const step = deliveryStep(restored, "restored workflow", "", true);
      // Restore the in-memory delivery set without adding workflow state entries.
      // The silent custom message must enter context before automatic compaction retries.
      activeWorkflow = step.state;
      refreshActiveTools(true);
      clearPiStatus(ctx.ui, "matt-pocock");
      pi.sendMessage({
        customType: PROCEDURE_ENTRY,
        content: step.text,
        display: false,
        details: step.state,
      }, { triggerTurn: false });
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
  };
  pi.on("session_start", async (_event, ctx) => restoreWorkflow(ctx));
  pi.on("session_tree", async (_event, ctx) => restoreWorkflow(ctx));
  pi.on("session_compact", async (_event, ctx) => restoreWorkflow(ctx));

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
      'mode workflow: {"mode": "workflow", "route": "<route id>"} for structured multi-step engineering (idea-to-ship for features, hard-bug for non-trivial bugs, architecture for deepening/refactoring, wayfinding for ambiguous maps, triage for issues).',
      'mode capability: {"mode": "capability", "capability": "<capability id>"} for a focused method. A capability id is not a workflow route; use mode capability even when its subject is engineering.',
      'mode reference: {"mode": "reference", "capability": "<capability id>", "reference": "<disclosed reference id>"}.',
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
          ? `${readableProcedureTitle(details.capability ?? "capability")} · ${readableProcedureTitle(details.reference ?? "reference")}`
          : readableProcedureTitle(details.capability ?? "standalone capability");
      const routeTitle = details.mode === "workflow" ? readableRouteTitle(details.route ?? "workflow") : undefined;
      const fields = routeTitle && routeTitle !== subject ? [fieldLine("route", routeTitle)] : [];
      return mattPocockRows.result(() => eventToolLifecycle("matt pocock", subject, { label: "started", details: fields }))(result, options, theme, context);
    },
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      signal?.throwIfAborted();
      clearPiStatus(ctx.ui, "matt-pocock");
      if (params.mode === "workflow") {
        const step = startWorkflow(params.route);
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
    description: 'Operate on the active workflow using exactly one shape: {"action":"transition","target":"<allowedNext id>"}, {"action":"load","reference":"<availableReferences id>"}, {"action":"complete"}, or {"action":"cancel","reason":"<why>"}. Transition requires target; a reference uses action load. Copy a call from the latest workflow state contract.',
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
      const details = (result.details ?? {}) as { action?: string; subject?: string; reference?: string; state?: { phase?: string; reason?: string } };
      // Saved results may still have route-based subjects; render from that event's phase, not active state.
      const subject = details.state?.phase && (details.action === "transition" || details.action === "complete" || details.action === "cancel")
        ? workflowEventSubject(details.action, details.state.phase)
        : details.action === "load"
          ? `loaded ${readableProcedureTitle(details.reference ?? details.subject?.replace(/^loaded /, "") ?? "reference")}`
          : details.subject ?? details.action ?? "workflow updated";
      const reason = details.action === "cancel" ? safeDisplayText(details.state?.reason ?? "").trim() : undefined;
      return mattPocockRows.result(() => eventToolLifecycle("matt pocock", subject, {
        label: "event",
        details: reason ? [fieldLine("reason", reason)] : [],
      }))(result, options, theme, context);
    },
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      signal?.throwIfAborted();
      if (!activeWorkflow) throw new Error("No active Matt Pocock workflow.");
      if (params.action === "transition") {
        const step = transitionWorkflow(params.target);
        clearPiStatus(ctx.ui, "matt-pocock");
        return {
          content: [{ type: "text", text: step.text }],
          details: { action: "transition", subject: workflowEventSubject("transition", step.state.phase), state: step.state },
        };
      }
      if (params.action === "load") {
        const loaded = loadActiveReference(params.reference);
        return {
          content: [{ type: "text", text: loaded.content }],
          details: { action: "load", reference: params.reference, subject: `loaded ${readableProcedureTitle(params.reference)}`, state: loaded.state },
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

  pi.registerTool({
    name: "matt_pocock_ask",
    label: "Matt Pocock Ask",
    description: "Ask a structured workflow decision question via Pi UI selection.",
    promptSnippet: "Ask a structured question during the active Matt Pocock workflow",
    promptGuidelines: [
      "Recommendations may time out to a default for routine preferences. For approval-required external or destructive actions, omit recommended and wait for an explicit user response.",
      "Escape, cancellation, abort, and no UI leave a decision pending; do not interpret them as consent.",
    ],
    parameters: Type.Object({
      title: Type.Optional(Type.String({ description: "Short title summarizing the decision context; defaults to workflow route and phase." })),
      question: Type.String({ description: "The interview or decision question to ask the user." }),
      options: Type.Array(Type.String({ minLength: 1 }), { minItems: 2, maxItems: 4, uniqueItems: true, description: "2 to 4 suggested options, recommended option first." }),
      recommended: Type.Optional(Type.String({ description: "An exact copy of one options entry, including annotations such as (Recommended) and whitespace. When provided, timeout automatically adopts this option." })),
      timeout_seconds: Type.Optional(Type.Number({ exclusiveMinimum: 0, maximum: 3600, description: "Seconds to wait; default 60; needs a recommended option." })),
      allow_custom: Type.Optional(Type.Boolean({ description: "Allow a custom typed answer; default true." })),
    }, { additionalProperties: false }),
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
    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      if (!activeWorkflow) throw new Error("No active Matt Pocock workflow.");
      const askedWorkflow = activeWorkflow;
      return withWorkflowSignal(signal, async (decisionSignal) => {
        const interrupted = () => decisionSignal.aborted || activeWorkflow !== askedWorkflow;
        const pendingAbort = () => ({
          content: [{ type: "text" as const, text: "[Pending user decision] Question interrupted. Do not proceed until the user responds." }],
          details: { pending: true, source: "aborted" },
        });
        if (interrupted()) return pendingAbort();
        const recommended = params.recommended === undefined ? undefined
          : params.options.includes(params.recommended) ? params.recommended : params.recommended.trim();
        if (recommended !== undefined && !params.options.includes(recommended)) {
          throw new Error("The recommended answer must match an offered option.");
        }
        if (!ctx.hasUI) {
          return {
            content: [{ type: "text", text: "[Pending user decision] No UI is available. Do not proceed until the user responds." }],
            details: { pending: true, source: "no_ui" },
          };
        }
        const timeoutSeconds = recommended ? params.timeout_seconds ?? 60 : undefined;
        const timeoutMs = timeoutSeconds === undefined ? undefined : timeoutSeconds * 1000;
        let customOption = "Type custom answer...";
        while (params.options.includes(customOption)) customOption += " (custom)";
        const choices = [...params.options];
        const allowCustom = params.allow_custom ?? true;
        if (allowCustom) choices.push(customOption);
        const title = params.title?.trim() || formatReadableWorkflowSubject(askedWorkflow.route, askedWorkflow.phase);
        const isChinese = /[\u4e00-\u9fa5]/.test(params.question);
        const buttons = { ok: isChinese ? "确认" : "Select", cancel: isChinese ? "取消" : "Cancel" };

        // Each UI adapter returns the same selection outcome; decision handling is shared.
        async function ask(native: boolean) {
          if (interrupted()) return pendingAbort();
          const choice = native
            ? await macosChooseFromList({
              title, prompt: params.question, items: choices, defaultItem: recommended ?? choices[0],
              okButtonName: buttons.ok, cancelButtonName: buttons.cancel, timeoutSeconds, signal: decisionSignal,
            })
            : await selectDecision(ctx, params.question, choices, decisionSignal, timeoutMs);
          if (interrupted()) return pendingAbort();
          if (choice.action === "timed_out" && recommended) {
            return {
              content: [{ type: "text" as const, text: `User selected (timeout default): ${recommended}` }],
              details: { answer: recommended, is_custom: false, timed_out: true, pending: false, source: "timeout_recommended" },
            };
          }
          if (choice.action !== "selected" || !choice.item) {
            const timedOut = choice.action === "timed_out";
            return {
              content: [{ type: "text" as const, text: `[Pending user decision] ${timedOut ? "Selection timed out." : "No answer was selected."} Do not proceed until the user responds.` }],
              details: { pending: true, timed_out: timedOut, source: "cancelled" },
            };
          }
          const isCustom = allowCustom && choice.item === customOption;
          let answer = choice.item;
          if (isCustom) {
            const input = native
              ? await macosInputDialog({
                title, prompt: params.question, defaultAnswer: "", buttons: [buttons.cancel, buttons.ok],
                defaultButton: buttons.ok, cancelButton: buttons.cancel, signal: decisionSignal,
              }).then((result) => result.action === "confirmed" ? result.text : undefined)
              : await ctx.ui.input(params.question, "Enter your answer...", { signal: decisionSignal });
            if (interrupted()) return pendingAbort();
            answer = input?.trim() ?? "";
            if (!answer) {
              return {
                content: [{ type: "text" as const, text: "[Pending user decision] No custom answer was provided. Do not proceed until the user responds." }],
                details: { pending: true, source: "custom_input_cancelled" },
              };
            }
          }
          return {
            content: [{ type: "text" as const, text: `${isCustom ? "User answered (custom)" : "User selected"}: ${answer}` }],
            details: { answer, is_custom: isCustom, source: isCustom ? "custom_input" : "choice_selected" },
          };
        }

        if (loadConfig().useNativeDialog && isNativeDialogSupported()) {
          try { return await ask(true); } catch {
            // Process and parsing failures fall back to Pi UI; user cancellation does not.
          }
        }
        return await ask(false);
      });
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
      if ((token === "status" || token === "complete") && task) {
        notifyPi(ctx.ui, `Usage: /matt-pocock ${token}`, "error");
        return;
      }
      if (token === "transition" && !task) {
        if (!ctx.hasUI) {
          notifyPi(ctx.ui, "Name a target: /matt-pocock transition <target>, or use the interactive menu.", "error");
          return;
        }
        return chooseTransition(ctx);
      }
      if (token === "transition") return applyTransition(ctx, task);
      if (token === "complete" && !task) return endWorkflow(ctx, "completed");
      if (token === "cancel" || token === "end") {
        return endWorkflow(ctx, "cancelled", task || `Cancelled by user with /matt-pocock ${token}.`);
      }

      if (findWorkflowRoute(token)) {
        const step = startWorkflow(token, task);
        clearPiStatus(ctx.ui, "matt-pocock");
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
