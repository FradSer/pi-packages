import { buildSessionContext, type AgentToolResult, type ExtensionAPI, type ExtensionContext, type ToolDefinition } from "@earendil-works/pi-coding-agent";
import { emptyToolCall } from "@fradser/pi-kit";
import type { ChildExecutionOptions } from "./child-execution.ts";
import { boundedFinalDiagnostic } from "./session-result.ts";
import { INTENT_TOOL_NAMES } from "./intent-tools.ts";

const LOADER = "subagents_enable";
/** Model-facing tools that no longer exist. Kept only to scrub them from a
 *  selection recorded before they were removed: a tool outside the family is not
 *  caught by the family filter, so without this list a stale recorded name would
 *  stay active on a transport that never registered it (ADR-0008). */
const RETIRED_TOOLS = new Set(["agent", "agent_inspect"]);
const LOADER_PARAMS = { type: "object", properties: {}, additionalProperties: false } as const;

/** Activation changes tool selection only, never delegation authority. */
export type SubagentActivationData =
  | { outcome: "enabled"; enabled: string[]; childStarted: false }
  | { outcome: "refused"; code: "unavailable"; unavailable: string[]; error: string; childStarted: false }
  | { outcome: "refused"; code: "activation-failed"; missing: string[]; error: string; childStarted: false };

export type SubagentActivationResult = AgentToolResult<SubagentActivationData> & { structuredContent: SubagentActivationData };

const LOADER_OUTPUT = {
  type: "object",
  anyOf: [
    {
      type: "object",
      properties: {
        outcome: { type: "string", const: "enabled" }, enabled: { type: "array", items: { type: "string" } },
        childStarted: { type: "boolean", const: false },
      },
      required: ["outcome", "enabled", "childStarted"], additionalProperties: false,
    },
    {
      type: "object",
      properties: {
        outcome: { type: "string", const: "refused" }, code: { type: "string", const: "unavailable" },
        unavailable: { type: "array", items: { type: "string" } }, error: { type: "string" },
        childStarted: { type: "boolean", const: false },
      },
      required: ["outcome", "code", "unavailable", "error", "childStarted"], additionalProperties: false,
    },
    {
      type: "object",
      properties: {
        outcome: { type: "string", const: "refused" }, code: { type: "string", const: "activation-failed" },
        missing: { type: "array", items: { type: "string" } }, error: { type: "string" },
        childStarted: { type: "boolean", const: false },
      },
      required: ["outcome", "code", "missing", "error", "childStarted"], additionalProperties: false,
    },
  ],
} as const;

function activationResult(data: SubagentActivationData, text: string): SubagentActivationResult {
  return { content: [{ type: "text", text }], details: data, structuredContent: data,
    ...(data.outcome === "refused" ? { isError: true } : {}) };
}

/** Require the exact transport's transcript-addition support, not tool choice. */
function supportsAnchoredAdditions(model: ExtensionContext["model"]): boolean {
  if (!model || !model.compat) return false;
  const compat = model.compat;
  if (!("supportsMidConvoSystemMessages" in compat) || compat.supportsMidConvoSystemMessages !== true) return false;
  switch (model.api) {
    case "anthropic-messages":
      return "supportsMidConvoToolChanges" in compat && compat.supportsMidConvoToolChanges === true;
    case "openai-completions":
      return "supportsMidConvoToolAdditions" in compat && compat.supportsMidConvoToolAdditions === true;
    case "openai-responses":
    case "openai-codex-responses":
    case "azure-openai-responses":
      return ("supportsAdditionalTools" in compat && compat.supportsAdditionalTools === true)
        || ("supportsToolSearch" in compat && compat.supportsToolSearch === true);
    default: return false;
  }
}

/** Select model-facing tools; this is not a security authorization gate. */
export function registerSubagentToolActivation(pi: ExtensionAPI, options: Pick<ChildExecutionOptions, "renderResult"> = {}): void {
  if (typeof pi.getAllTools !== "function" || typeof pi.getActiveTools !== "function" || typeof pi.setActiveTools !== "function") return;
  const family = new Set<string>(INTENT_TOOL_NAMES);
  // What the loader would activate, and whether it is active right now. A
  // transport that can add tools mid-conversation keeps the family registered but
  // unsent, so the loader still has a family to offer; that is why the two facts
  // are separate instead of encoded by emptying `chosen`.
  let chosen: string[] = [...INTENT_TOOL_NAMES];
  let active = true;
  const select = (activate: boolean, loader: boolean) => {
    active = activate && chosen.length > 0;
    // The retired `agent` name is scrubbed as well: a selection recorded before its
    // removal would otherwise keep advertising a tool that no longer exists.
    const next = pi.getActiveTools().filter(name => !family.has(name) && name !== LOADER && !RETIRED_TOOLS.has(name));
    if (active) next.push(...chosen);
    if (loader && typeof pi.getAllTools().some(tool => tool.name === LOADER)) next.push(LOADER);
    pi.setActiveTools(next);
  };
  pi.registerTool<typeof LOADER_PARAMS, SubagentActivationData>({
    name: LOADER,
    label: "Enable Subagents",
    promptSnippet: "Select the agent tools without starting a child; delegation authorization stays separate.",
    description: "Select the recorded agent tool family without starting a child. Tool selection is not delegation authorization.",
    promptGuidelines: [
      "Use subagents_enable only when delegation is authorized by the user or applicable instructions; complexity alone is not authorization. Activation changes availability, not permission.",
    ],
    parameters: LOADER_PARAMS,
    outputSchema: LOADER_OUTPUT,
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    renderShell: "self",
    renderCall: emptyToolCall,
    ...(options.renderResult ? { renderResult: options.renderResult({ createSpec: () => ({
      kind: "event", tool: "subagents", label: "enabled", subject: "agent execution", summary: [],
    }) }) as ToolDefinition<typeof LOADER_PARAMS, SubagentActivationData>["renderResult"] } : {}),
    async execute(): Promise<SubagentActivationResult> {
      try {
        const available = new Set(pi.getAllTools().map(tool => tool.name));
        // The loader offers the whole family or refuses: a host that excluded a
        // member cannot be handed half a family, and the refusal names what was
        // wanted rather than whatever a previous restore happened to leave behind.
        const registered = INTENT_TOOL_NAMES.filter(name => available.has(name));
        if (registered.length !== INTENT_TOOL_NAMES.length) {
          const error = "Agent execution is excluded or unavailable.";
          return activationResult({ outcome: "refused", code: "unavailable", unavailable: [...INTENT_TOOL_NAMES], error, childStarted: false }, error);
        }
        select(true, true);
        if (!chosen.every(name => pi.getActiveTools().includes(name))) throw new Error("Agent execution could not be activated.");
        return activationResult({ outcome: "enabled", enabled: [...chosen], childStarted: false },
          `Enabled: ${chosen.join(", ")}. Use exact-session controls on the next request; no child was started.`);
      } catch (error) {
        const diagnostic = boundedFinalDiagnostic(error instanceof Error ? error.message : String(error)) || "Agent execution could not be activated.";
        return activationResult({ outcome: "refused", code: "activation-failed", missing: [...chosen], error: diagnostic, childStarted: false }, diagnostic);
      }
    },
  });
  const restore = (_event: unknown, ctx: ExtensionContext) => {
    const available = new Set(pi.getAllTools().map(tool => tool.name));
    // The family is all four tools or nothing: a host that excludes one member
    // cannot be offered a half family, because every member addresses the same
    // exact sessions and a caller would have to guess which controls survived.
    const selectable = INTENT_TOOL_NAMES.filter(name => available.has(name));
    const complete = selectable.length === INTENT_TOOL_NAMES.length;
    // A host that excludes the family keeps no selection: an invented one would
    // advertise tools the host will not send to the model.
    if (!complete) {
      chosen = [];
      select(false, false);
      return;
    }
    const manager = ctx.sessionManager;
    const messages = buildSessionContext(manager.getBranch(), manager.getLeafId()).messages;
    const recorded = new Set<string>();
    let hasSelection = false;
    for (const message of messages) {
      if (message.role !== "system") continue;
      if ([...(message.toolsAdded ?? []), ...(message.toolsRemoved ?? [])]
        .some(tool => family.has(tool.name) || tool.name === LOADER || RETIRED_TOOLS.has(tool.name))) hasSelection = true;
      for (const tool of message.toolsRemoved ?? []) recorded.delete(tool.name);
      for (const tool of message.toolsAdded ?? []) recorded.add(tool.name);
    }
    if (!hasSelection) {
      // A new session: the family is what the loader offers, and it stays off the
      // wire until the transport can add tools mid-conversation. Laziness needs a
      // loader to exist, so a host that excluded one is served eagerly instead of
      // losing delegation to nobody.
      const dynamic = supportsAnchoredAdditions(ctx.model);
      const lazy = dynamic && available.has(LOADER);
      chosen = selectable;
      select(!lazy, lazy);
      return;
    }
    // A branch that recorded a retired `agent` selection keeps its work and gets
    // the intent family: the removed tool cannot come back, and an empty
    // selection would take delegation away instead of moving it (ADR-0008).
    const recordedFamily = selectable.filter(name => recorded.has(name));
    // A branch that recorded the retired tool keeps its delegation: the family takes
    // its place. A branch that recorded nothing active stays inactive.
    const moved = recordedFamily.length > 0 || [...RETIRED_TOOLS].some((name) => recorded.has(name));
    chosen = recordedFamily.length > 0 ? recordedFamily : selectable;
    select(moved, recorded.has(LOADER) && available.has(LOADER));
  };
  pi.on("session_start", restore);
  pi.on("session_tree", restore);
  // model_select intentionally keeps the selection already sent to the provider.
}
