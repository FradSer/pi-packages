/** Experimental parent resource cap, identical in both arms; never a learned rule. */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export function installStudyToolBudget(pi: ExtensionAPI, limit = 18): void {
  const admitted = new Set<string>();
  let used = 0;
  let removed = false;
  let summaryTurn = false;
  const record = (outcome: string) => pi.appendEntry("continuous-study-tool-budget", {
    limit, admitted: used, outcome,
  });
  const remove = () => {
    pi.setActiveTools([]);
    if (!removed) { removed = true; record("tools-removed"); }
  };
  pi.on("before_agent_start", () => {
    if (limit === 0) { remove(); summaryTurn = true; }
  });
  pi.on("tool_call", event => {
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
