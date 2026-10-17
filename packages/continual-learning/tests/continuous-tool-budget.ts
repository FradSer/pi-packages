/** Experimental parent resource cap, identical in both arms; never a learned rule. */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export function installStudyToolBudget(pi: ExtensionAPI, limit = 18, verifierFile = process.env.PI_STUDY_VERIFIER_FILE): void {
  const admitted = new Set<string>();
  let used = 0;
  let invalidVerifierCalls = 0;
  let removed = false;
  let summaryTurn = false;
  const record = (outcome: string) => pi.appendEntry("continuous-study-tool-budget", {
    limit, admitted: used, outcome,
  });
  const remove = () => {
    pi.setActiveTools([]);
    if (!removed) { removed = true; record("tools-removed"); }
  };
  pi.on("before_provider_request", (event, ctx) => {
    if (ctx.model?.api !== "openai-completions") return;
    const payload = event.payload;
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) return;
    const request = payload as Record<string, unknown>;
    if (!Array.isArray(request.messages)) return;
    if (!removed) {
      if (!verifierFile || limit !== 1 || !Array.isArray(request.tools)) return;
      let changed = false;
      const tools = request.tools.map(value => {
        if (!value || typeof value !== "object" || Array.isArray(value)) return value;
        const tool = value as Record<string, unknown>;
        const fn = tool.function as Record<string, unknown> | undefined;
        if (tool.type !== "function" || !fn || fn.name !== "read") return value;
        changed = true;
        // Advertise the same complete-read authority that tool_call enforces.
        // No observations or messages are injected, and no read is forced.
        return {...tool, function: {...fn, parameters: {type: "object",
          properties: {path: {type: "string", enum: [verifierFile]}},
          required: ["path"], additionalProperties: false}}};
      });
      return changed ? {...request, tools} : undefined;
    }
    if (pi.getActiveTools().length !== 0 || (request.tools !== undefined
      && (!Array.isArray(request.tools) || request.tools.length !== 0))) return;
    // Empty definitions leave past tool calls in context. Make the exhausted
    // authorization explicit on the service wire; never discard observations.
    return { ...request, tool_choice: "none" };
  });
  pi.on("before_agent_start", () => {
    if (limit === 0) { remove(); summaryTurn = true; }
  });
  pi.on("tool_call", (event, ctx) => {
    if (verifierFile && invalidVerifierCalls >= 3) {
      record("blocked");
      return { block: true, reason: "This verification continuation was aborted after repeated unauthorized reads." };
    }
    // The feedback phase admits only the complete, source-bound observation.
    // Rejected source/pagination calls must not spend its one authorized read.
    if (verifierFile && (event.toolName !== "read" || event.input.path !== verifierFile
      || event.input.offset !== undefined || event.input.limit !== undefined
      || Object.keys(event.input).some(key => key !== "path"))) {
      invalidVerifierCalls++;
      record("verifier-read-blocked");
      if (invalidVerifierCalls >= 3) { remove(); ctx.abort(); }
      return { block: true, reason: `This verification continuation only permits read of ${verifierFile} with no offset or limit. Read the complete observation once, then summarize without tools.` };
    }
    if (used >= limit) {
      remove();
      record("blocked");
      return { block: true, reason: "The study task tool budget is exhausted. Summarize existing observations without further tools." };
    }
    used++;
    admitted.add(event.toolCallId);
  });
  pi.on("tool_result", event => {
    if (admitted.has(event.toolCallId) && used >= limit) remove();
  });
  pi.on("turn_end", (event, ctx) => {
    if (!removed) return;
    // Tool removal prevents execution but some providers keep requesting absent tools.
    // Permit one summary response, then stop that loop at the persisted boundary.
    if (summaryTurn && Array.isArray(event.message.content)
      && event.message.content.some(part => part.type === "toolCall")) {
      record("summary-tool-loop-stopped");
      ctx.abort();
    }
    summaryTurn = true;
  });
}

export default function studyToolBudget(pi: ExtensionAPI): void {
  const limit = process.env.PI_STUDY_TASK_TOOL_LIMIT;
  installStudyToolBudget(pi, limit === "1" ? 1 : limit === "0" ? 0 : 18);
}
