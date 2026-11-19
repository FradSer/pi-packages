import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { CoordinationToolResult } from "./types.ts";
import { notifyPi } from "@fradser/pi-kit";
import {
  publishStateSnapshot,
  sendLeaderMessage,
  shutdownAgentExact,
  spawnAgent,
} from "./team-machine.ts";
import { livingAgents } from "./state.ts";

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
        messageRow(context.args as { to?: string; body?: string }, result.details, { isError: context.isError }),
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
        to = resolveRecipient(params.to, livingAgents()).name;
      } catch (error) {
        return refuse(error instanceof Error ? error.message : String(error));
      }
      const result = runtime.sendLeaderMessage(to, params.body, {});
      if (!result.ok) return refuse(result.error);
      const recorded = result.outcome === "not-sent" ? `\nRECORDED TERMINAL REPORT · ${result.terminalReport}` : "";
      return {
        content: [{ type: "text", text: `MESSAGE ROUTING · ${result.outcome} · to=@${to}\nKIND · ${params.kind ?? "inform"}${recorded}` }],
        details: { to, outcome: result.outcome, kind: params.kind ?? "inform", ok: true },
      };
    },
  });
}

/** Register this package's own tool, and only that one.
 *
 * `agent` is registered by @fradser/pi-subagents. Task tools are retired: the
 * internal task domain coordinates residents without exposing a model-facing
 * task tool, so this package registers only `message`.
 */
export function registerLeaderTools(pi: ExtensionAPI, runtime: AgentActionRuntime & { sendLeaderMessage: typeof sendLeaderMessage } = { spawnAgent, shutdownAgentExact, sendLeaderMessage }): void {
  registerMessageTool(pi, runtime);
}

function teamStatusSummary(): string {
  const roles = [...discoverAgents().keys()].map((name) => `@${name}`);
  const rolesLine = roles.length > 0
    ? `${roles.length} persistent agent role${roles.length === 1 ? "" : "s"}: ${roles.join(", ")}`
    : "No agent roles discovered.";
  const roster = livingAgents().map((t) => `@${t.name} (${t.role}, ${t.status})`).join("\n") || "No living sessions.";
  return `${roster}\n${rolesLine}`;
}

export function registerTeamCommand(pi: ExtensionAPI): void {
  pi.registerCommand("agent-teams", {
    description: "Agent Teams management console: session agents and persistent agent roles",
    handler: async (_args, ctx) => {
      publishStateSnapshot();
      if (ctx.mode !== "tui") { notifyPi(ctx.ui, teamStatusSummary(), "info"); return; }
      await openTeamConsole(ctx);
      refreshTeamUI(ctx);
    },
  });
}

