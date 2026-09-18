import { truncateHead, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { notifyPi } from "@fradser/pi-kit";
import {
  assignExistingWork,
  releaseExistingWork,
  reopenExistingWork,
  createBoardTask,
  publishStateSnapshot,
  sendLeaderMessage,
  shutdownTeammateExact,
  spawnTeammate,
} from "./team-machine.ts";
import { listTasks, livingTeammates } from "./state.ts";

import { AgentActionParams, LEADER_RECIPIENT, AgentEventParams, WorkToolParams } from "./types.ts";
import { openTeamConsole, refreshTeamUI } from "./ui.ts";
import { discoverAgents } from "./agents.ts";
import { agentRow, leaderWorkRow, messageRow, type AgentRowArgs } from "./tool-copy.ts";
import { emptyToolCall, renderCoordinationRow } from "./tool-render.ts";
import { runAgentAction, type AgentActionRuntime } from "./agent-actions.ts";
import { resolveRecipient } from "./recipient.ts";

function formatWorkList(tasks: ReturnType<typeof listTasks>): string {
  const works = tasks.map((task) => {
    const dependencies = task.dependsOn.length > 0 ? ` · depends=${task.dependsOn.join(",")}` : "";
    const holder = task.claimedBy ? ` · owner=@${task.claimedBy}` : "";
    const result = task.result ? truncateHead(task.result, { maxBytes: 4096, maxLines: 40 }) : undefined;
    const evidence = result ? `\n  RESULT · ${result.content}${result.truncated ? "\n  [Result preview truncated; complete evidence is retained in Work details.]" : ""}` : "";
    return `- ${task.id} · ${task.status} · ${task.subject}${holder}${dependencies}${evidence}`;
  });
  return [
    "WORK · current session",
    `SUMMARY · ${tasks.length} work item${tasks.length === 1 ? "" : "s"}`,
    "WORK ITEMS",
    ...(works.length > 0 ? works : ["(none)"]),
  ].join("\n");
}

function formatWorkCreation(subject: string, created: {
  id: string;
  claimable: boolean;
  resourceBlocked: boolean;
  notifiedTeammates: string[];
}): string {
  const availability = created.claimable ? "pending/claimable" : "pending/blocked";
  const routing = created.notifiedTeammates.length > 0
    ? `eligible residents notified: ${created.notifiedTeammates.map((name) => `@${name}`).join(", ")}`
    : created.resourceBlocked
      ? "resource conflict blocks assignment"
      : "no eligible resident notified";
  return [
    "WORK · current session",
    `CREATED · ${created.id} · ${availability} · ${subject}`,
    `ROUTING · ${routing}`,
  ].join("\n");
}

/** Final surface uses stable registrations; retained for extension lifecycle callers. */
export function refreshLeaderToolDisclosure(): void {}

export function registerLeaderTools(pi: ExtensionAPI, runtime: AgentActionRuntime & { sendLeaderMessage: typeof sendLeaderMessage } = { spawnTeammate, shutdownTeammateExact, sendLeaderMessage }): void {
  pi.registerTool({
    name: "agent",
    promptSnippet: "Delegate, start, inspect, or stop an Agent session",
    label: "Agent",
    description: "Strict Agent lifecycle interface. Delegate creates independent Work; start creates an unassigned resident; inspect and stop use incarnation-bound session handles. Results arrive automatically; inspect is for deliberate diagnosis, not waiting.",
    promptGuidelines: ["After agent delegation, results arrive automatically. Continue independent work or end the turn; do not wait with sleep, repeated agent inspect, or work list polling."],
    parameters: AgentActionParams,
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      return renderCoordinationRow(
        result, options, theme, context,
        "agent",
        agentRow(context.args as AgentRowArgs, result.details, { isError: context.isError, isPartial: options.isPartial }),
      );
    },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const result = await runAgentAction(params, ctx.cwd, runtime, ctx.sessionManager);
      if (params.action !== "inspect") {
        refreshTeamUI(ctx);
        refreshLeaderToolDisclosure();
      }
      return { content: [{ type: "text", text: JSON.stringify(result) }], details: result };
    },
  });

  pi.registerTool({
    name: "agent_event",
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
      if (!params.to) {
        throw new Error("No bound reply route exists. Please specify 'to' explicitly.");
      }
      if (params.to === LEADER_RECIPIENT) throw new Error("The leader cannot send an event to itself.");
      const to = resolveRecipient(params.to, livingTeammates()).name;
      const result = runtime.sendLeaderMessage(to, params.message, {});
      if (!result.ok) throw new Error(result.error);
      const recorded = result.outcome === "not-sent" ? `\nRECORDED TERMINAL REPORT · ${result.terminalReport}` : "";
      const next = "";
      return {
        content: [{ type: "text", text: `EVENT ROUTING · ${result.outcome} · to=@${to}\nINTENT · ${params.intent ?? "inform"}${recorded}${next}` }],
        details: { to, outcome: result.outcome, intent: params.intent ?? "inform" },
      };
    },
  });

  pi.registerTool({
    name: "work",
    promptSnippet: "Create, list, assign, release, reopen, or supersede Work Items",
    label: "Work",
    description: "Manage Work Items: create (subject), list, assign (id, target.session), release (id, reason), reopen (id, reason), or supersede (subject, supersedes). Creation uses the session's single-writer Work state and never starts a resident.",
    parameters: WorkToolParams,
    renderShell: "self",
    renderCall: emptyToolCall,
    renderResult(result, options, theme, context) {
      return renderCoordinationRow(
        result, options, theme, context,
        "work",
        leaderWorkRow(context.args as Record<string, unknown>, result.details, { isError: context.isError }),
      );
    },
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      if (params.action === "supersede") {
        const tasks = listTasks();
        const referenced = [...(params.dependsOn ?? []), ...params.supersedes];
        if (referenced.some((id) => !tasks.some((task) => task.id === id))) {
          throw new Error(`Unknown work id in [${referenced.join(", ")}].`);
        }
        const created = createBoardTask(params);
        if (!created.ok) throw new Error(created.error);
        const work = listTasks().find((task) => task.id === created.id);
        if (!work) throw new Error(`Replacement Work Item "${created.id}" is unavailable.`);
        refreshTeamUI(ctx);
        refreshLeaderToolDisclosure();
        return {
          content: [{ type: "text", text: `WORK · current session\nSUPERSEDED · ${work.id} · ${work.status}\nREPLACED · ${created.supersededTaskIds.join(", ")}\nROUTING · ${created.notifiedTeammates.length > 0 ? `eligible residents notified: ${created.notifiedTeammates.map((name) => `@${name}`).join(", ")}` : "no eligible resident notified"}` }],
          details: {
            action: "supersede", outcome: "superseded", state: work.status,
            work: { id: work.id, subject: work.subject, ...(work.description ? { description: work.description } : {}), dependsOn: work.dependsOn, resources: work.resources, ...(work.verify ? { verify: work.verify } : {}), state: work.status },
            supersededWorkIds: created.supersededTaskIds, notifiedTeammates: created.notifiedTeammates, claimable: created.claimable,
          },
        };
      }
      if (params.action === "reopen") {
        const reopened = reopenExistingWork(params.id);
        if (!reopened.ok) throw new Error(reopened.error);
        refreshTeamUI(ctx);
        refreshLeaderToolDisclosure();
        return {
          content: [{ type: "text", text: `WORK · current session\nREOPENED · ${reopened.workId} · pending\nREASON · ${params.reason}` }],
          details: { action: "reopen", outcome: "reopened", state: "pending", work: { id: reopened.workId, subject: reopened.subject, resources: reopened.resources, state: "pending" }, reason: params.reason },
        };
      }
      if (params.action === "release") {
        const released = releaseExistingWork(params.id, params.reason);
        if (!released.ok) throw new Error(released.error);
        refreshTeamUI(ctx);
        refreshLeaderToolDisclosure();
        const residual = released.holderStillRunning
          ? `\nRISK · @${released.holderStillRunning} was still working; an in-flight tool batch may still write inside ${released.resources.join(", ") || "the released scope"}.`
          : "";
        return {
          content: [{ type: "text", text: `WORK · current session\nRELEASED · ${released.workId} · pending\nREASON · ${params.reason}${residual}` }],
          details: { action: "release", outcome: "released", state: "pending", work: { id: released.workId, subject: released.subject, resources: released.resources, state: "pending" }, reason: params.reason, ...(released.holderStillRunning ? { holderStillRunning: released.holderStillRunning } : {}) },
        };
      }
      if (params.action === "assign") {
        const assigned = assignExistingWork(params.id, params.target.session);
        if (!assigned.ok) throw new Error(assigned.error);
        const task = listTasks().find((entry) => entry.id === assigned.workId);
        if (!task) throw new Error(`Assigned Work Item "${assigned.workId}" is unavailable.`);
        refreshTeamUI(ctx);
        refreshLeaderToolDisclosure();
        return {
          content: [{ type: "text", text: `WORK · current session\nASSIGNED · ${task.id} · claimed · owner=@${assigned.owner}\nATTEMPT · ${assigned.assignmentId} · fresh-session-pending` }],
          details: {
            action: "assign", outcome: "assigned", state: task.status,
            work: { id: task.id, subject: task.subject, resources: task.resources, state: task.status, claimedBy: task.claimedBy },
            assignment: { id: assigned.assignmentId, owner: assigned.owner, kind: "direct" },
            target: params.target, delivery: "fresh-session-pending",
          },
        };
      }
      if (params.action === "list") {
        const works = listTasks().map((task) => ({
          id: task.id,
          subject: task.subject,
          ...(task.description ? { description: task.description } : {}),
          dependsOn: task.dependsOn,
          resources: task.resources,
          ...(task.verify ? { verify: task.verify } : {}),
          state: task.status,
          ...(task.claimedBy ? { claimedBy: task.claimedBy } : {}),
          ...(task.result ? { result: task.result } : {}),
        }));
        return {
          content: [{ type: "text", text: formatWorkList(listTasks()) }],
          details: { action: "list", outcome: "listed", works, count: works.length },
        };
      }
      const tasks = listTasks();
      const referenced = params.dependsOn ?? [];
      if (referenced.some((id) => !tasks.some((task) => task.id === id))) {
        throw new Error(`Unknown work id in [${referenced.join(", ")}].`);
      }
      const created = createBoardTask(params);
      if (!created.ok) throw new Error(created.error);
      const work = listTasks().find((task) => task.id === created.id);
      if (!work) throw new Error(`Created Work Item "${created.id}" is unavailable.`);
      refreshTeamUI(ctx);
      refreshLeaderToolDisclosure();
      return {
        content: [{ type: "text", text: formatWorkCreation(params.subject, created) }],
        details: {
          action: "create",
          outcome: "created",
          state: work.status,
          work: {
            id: work.id,
            subject: work.subject,
            ...(work.description ? { description: work.description } : {}),
            dependsOn: work.dependsOn,
            resources: work.resources,
            ...(work.verify ? { verify: work.verify } : {}),
            state: work.status,
          },
          notifiedTeammates: created.notifiedTeammates,
          claimable: created.claimable,
          supersededWorkIds: created.supersededTaskIds,
        },
      };
    },
  });


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

