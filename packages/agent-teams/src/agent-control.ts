import { randomUUID } from "node:crypto";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { resolveAgent } from "./agents.ts";
import { isValidTeammateName, listTeammates } from "./state.ts";
import { sendLeaderMessage, spawnTeammate, unknownAgentError } from "./team-machine.ts";
import type { Teammate } from "./types.ts";
import { snapshotWorkContext } from "./work-context.ts";
import { sessionRoute } from "./recipient.ts";

export interface AgentControlRuntime {
  spawnTeammate: typeof spawnTeammate;
  sendLeaderMessage: typeof sendLeaderMessage;
}

function workSessionPresence(teammate: Teammate) {
  return {
    workId: teammate.workId ?? teammate.assignment?.id,
    route: sessionRoute(teammate.name),
    context: teammate.context ?? "fresh",
    status: teammate.status,
    assignmentOpen: teammate.assignment !== undefined && !teammate.assignment.closed,
  };
}

export function agentPresence(name: string, cwd?: string) {
  const sessions = listTeammates().filter((teammate) => teammate.agent === name).map(workSessionPresence);
  const defined = resolveAgent(name, cwd) !== undefined;
  const active = sessions.find((session) => session.status === "working" || session.status === "starting");
  const status = active?.status ?? sessions.find((session) => session.status === "idle")?.status
    ?? sessions.at(-1)?.status ?? (defined ? "idle" : "unknown");
  return { name, status, scope: "current-session", defined, sessions };
}

export function controlAgent(
  params: { name: string; prompt?: string; work?: string; model?: string; fork?: boolean },
  cwd: string | undefined,
  runtime: AgentControlRuntime,
  sessionManager?: ExtensionContext["sessionManager"],
) {
  if (params.fork !== undefined && (params.work !== undefined || !params.prompt?.trim())) {
    throw new Error("fork is valid only for a new prompt without work.");
  }
  if (!isValidTeammateName(params.name)) throw new Error(`Invalid Agent name "${params.name}".`);
  const selected = params.work === undefined ? undefined : listTeammates().find((teammate) =>
    teammate.agent === params.name && (teammate.workId ?? teammate.assignment?.id) === params.work);
  if (params.work !== undefined && !selected) throw new Error(`Unknown work ID "${params.work}" for @${params.name}.`);
  const prompt = params.prompt?.trim();
  if (params.prompt !== undefined && !prompt) throw new Error("Agent prompt must not be empty.");
  if (!prompt) return presenceResult(params.name, cwd, "inspected", selected);
  if (selected) {
    if (selected.status === "stopped") throw new Error("Cannot steer stopped work; start a new assignment without a work ID.");
    if (params.model) throw new Error("Model overrides apply only when starting an Agent, not steering existing work.");
    const result = runtime.sendLeaderMessage(selected.name, prompt, { reopen: "if-closed" });
    if (!result.ok) throw new Error(result.error);
    const response = presenceResult(params.name, cwd, result.outcome, selected);
    if (result.outcome === "not-sent") {
      response.content[0].text += `\nNEXT · No message was delivered; read the recorded report.\nRECORDED TERMINAL REPORT · ${result.terminalReport}`;
    }
    return response;
  }
  const definition = resolveAgent(params.name, cwd);
  if (!definition) throw new Error(`Unknown Agent @${params.name}. ${unknownAgentError(params.name, cwd ?? process.cwd())}`);
  const context = params.fork ? snapshotWorkContext(sessionManager) : undefined;
  const id = randomUUID();
  const result = runtime.spawnTeammate({
    name: `${params.name.slice(0, 27)}-${id}`,
    agent: params.name,
    workId: `work:${id}`,
    context,
    prompt,
    model: params.model,
  });
  if (!result.ok) throw new Error(result.error);
  return presenceResult(params.name, cwd, "started", result.teammate);
}

function coordinationNext(
  outcome: "inspected" | "started" | "steered" | "queued" | "not-sent",
  status: string,
): string[] {
  if (outcome === "started") {
    return [
      "KICKOFF · supplied once to this Work Session",
      "NEXT · Do not echo the kickoff through another message. Continue independent work or end the turn; the final result arrives automatically.",
    ];
  }
  if (outcome === "steered" || outcome === "queued") {
    return [
      "ROUTING · Routing acknowledgment is not worker consumption.",
      "NEXT · Do not inspect for confirmation, repeat this guidance, or ask for progress or the final report. Continue independent work or end the turn; the final result arrives automatically.",
    ];
  }
  if (outcome === "inspected") {
    const next = status === "working" || status === "starting"
      ? "Active work reports completion automatically."
      : "No active completion is pending for this Agent Presence.";
    return [
      "PRESENCE · point-in-time projection, not a completion signal",
      `NEXT · Use Agent Presence only for deliberate diagnosis, not progress polling. ${next}`,
    ];
  }
  return [];
}

function presenceResult(
  name: string,
  cwd: string | undefined,
  outcome: "inspected" | "started" | "steered" | "queued" | "not-sent",
  selected?: Teammate,
) {
  const presence = agentPresence(name, cwd);
  const work = selected ? workSessionPresence(selected) : undefined;
  const status = work?.status ?? presence.status;
  const rows = presence.sessions.map((session) =>
    `- ${session.workId ?? "unassigned"} · ${session.status} · ${session.assignmentOpen ? "open" : "none open"} · to=${session.route}`);
  return {
    content: [{ type: "text" as const, text: [
      `AGENT PRESENCE · @${name}`, "SCOPE · current session", `STATUS · ${status}`,
      `OUTCOME · ${outcome}`, ...coordinationNext(outcome, status),
      ...(work ? [`WORK · ${work.workId ?? "none"}`, `ROUTE · ${work.route}`, `CONTEXT · ${work.context}`] : []),
      "WORK SESSIONS", ...rows.length ? rows : ["(none)"],
    ].join("\n") }],
    details: { ...presence, ...work, outcome },
  };
}
