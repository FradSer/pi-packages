import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { CoordinationToolResult } from "./types.ts";
import { notifyPi } from "@fradser/pi-kit";
import {
  publishStateSnapshot,
  sendLeaderMessage,
  shutdownTeammateExact,
  spawnTeammate,
} from "./team-machine.ts";
import { livingTeammates } from "./state.ts";

import { AgentEventParams, LEADER_RECIPIENT } from "./types.ts";
import { openTeamConsole, refreshTeamUI } from "./ui.ts";
import { discoverAgents } from "@fradser/pi-subagents";
import { messageRow } from "./tool-copy.ts";
import { emptyToolCall, renderCoordinationRow } from "./tool-render.ts";
import type { AgentActionRuntime } from "./agent-actions.ts";
import { resolveRecipient } from "./recipient.ts";

/** Point-to-point communication. Stays with @fradser/pi-agent-teams. */
export function registerMessageTool(pi: ExtensionAPI, runtime: { sendLeaderMessage: typeof sendLeaderMessage } = { sendLeaderMessage }): void {
  pi.registerTool({
    name: "message",
    promptSnippet: "Send an event or message to a participant",
    label: "Agent Event",
    description: "Shared communication interface across Leader, Worker, and Peers. Leader-to-Agent messages carry only new evidence, changed constraints, or decisions — never kickoff echoes, progress requests, completion requests, or confirmation probes.",
    parameters: AgentEventParams,
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      return renderCoordinationRow(
        result, options, theme, context,
        "message",
        messageRow(context.args as { to?: string; message?: string }, result.details, { isError: context.isError }),
      );
    },
    async execute(_toolCallId, params) {
      // A refusal is returned, not thrown, so every tool in the coordination
      // surface reports failure the same way and a caller reads one shape
      // whatever went wrong. Throwing here would make `message` the only tool
      // that needs a try/catch.
      const refuse = (error: string): CoordinationToolResult => ({
        content: [{ type: "text", text: error }],
        details: { ok: false, error },
        isError: true,
      });
      if (!params.to) {
        return refuse("No bound reply route exists. Please specify 'to' explicitly.");
      }
      if (params.to === LEADER_RECIPIENT) return refuse("The leader cannot send a message to itself.");
      let to: string;
      try {
        to = resolveRecipient(params.to, livingTeammates()).name;
      } catch (error) {
        return refuse(error instanceof Error ? error.message : String(error));
      }
      const result = runtime.sendLeaderMessage(to, params.message, {});
      if (!result.ok) return refuse(result.error);
      const recorded = result.outcome === "not-sent" ? `\nRECORDED TERMINAL REPORT · ${result.terminalReport}` : "";
      return {
        content: [{ type: "text", text: `MESSAGE ROUTING · ${result.outcome} · to=@${to}\nKIND · ${params.intent ?? "inform"}${recorded}` }],
        details: { to, outcome: result.outcome, intent: params.intent ?? "inform", ok: true },
      };
    },
  });
}

// The `task` tool is registered by @fradser/pi-tasks' own extension entry. This
// package loads it through its manifest rather than calling its registrar, so
// there is exactly one registrant of that tool in every install combination.
// The leader learns about board transitions on `pi-tasks:*` events instead.

/** Temporary seam. Each registrar moves to its owning package; this keeps the
 *  existing entry point and its test fixtures intact until that lands. */
/** Register this package's own tool, and only that one.
 *
 * `agent` is registered by @fradser/pi-subagents and `task` by
 * @fradser/pi-tasks. This package's manifest loads those two extension entries
 * alongside its own, which is how one install ends up with three tools and each
 * tool still has exactly one registrant. A tool with two registrants either
 * collides or is silently dropped depending on load order, and neither failure is
 * visible from here.
 *
 * The leader learns about board transitions on `pi-tasks:*` events rather than
 * being called by pi-tasks, so the domain never has to know a resident exists.
 */
export function registerLeaderTools(pi: ExtensionAPI, runtime: AgentActionRuntime & { sendLeaderMessage: typeof sendLeaderMessage } = { spawnTeammate, shutdownTeammateExact, sendLeaderMessage }): void {
  registerMessageTool(pi, runtime);
}

function teamStatusSummary(): string {
  const roles = [...discoverAgents().keys()].map((name) => `@${name}`);
  const rolesLine = roles.length > 0
    ? `${roles.length} persistent agent role${roles.length === 1 ? "" : "s"}: ${roles.join(", ")}`
    : "No agent roles discovered.";
  const roster = livingTeammates().map((t) => `@${t.name} (${t.agent}, ${t.status})`).join("\n") || "No living sessions.";
  return `${roster}\n${rolesLine}`;
}

export function registerTeamCommand(pi: ExtensionAPI): void {
  pi.registerCommand("agent-teams", {
    description: "Agent Teams management console: session teammates and persistent agent roles",
    handler: async (_args, ctx) => {
      publishStateSnapshot();
      if (ctx.mode !== "tui") { notifyPi(ctx.ui, teamStatusSummary(), "info"); return; }
      await openTeamConsole(ctx);
      refreshTeamUI(ctx);
    },
  });
}

