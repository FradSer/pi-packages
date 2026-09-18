import { randomUUID } from "node:crypto";
import { WORKER_BUILTIN_TOOLS } from "./worker-tools.ts";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { isValidTeammateName, listTeammates } from "./state.ts";
import { resolveAgent } from "./agents.ts";
import { shutdownTeammateExact, spawnTeammate } from "./team-machine.ts";
import type { Teammate } from "./types.ts";
import { snapshotWorkContext } from "./work-context.ts";
import { exactSessionRoute, resolveExactSession } from "./recipient.ts";

export interface AgentActionRuntime {
  spawnTeammate: typeof spawnTeammate;
  shutdownTeammateExact: typeof shutdownTeammateExact;
}

type Definition = Parameters<typeof spawnTeammate>[0]["definition"];

function session(teammate: Teammate) {
  const tools = teammate.tools;
  const coordinationOnly = tools !== undefined && tools.every((tool) => tool === "agent_event" || tool === "work");
  return {
    tools,
    ...(coordinationOnly ? { warning: "coordination-only: no file or shell tools granted. Delegate execution work with explicit canonical tools; no bash is granted by default." } : {}),
    id: exactSessionRoute(teammate.name, teammate.spawnId),
    status: teammate.status,
    workId: teammate.workId,
    assignmentId: teammate.assignment?.id,
  };
}

function requireName(name: string): void {
  if (!isValidTeammateName(name)) throw new Error(`Invalid Agent name "${name}".`);
}

export function runAgentAction(
  params: {
    action: "delegate" | "start" | "inspect" | "stop";
    name?: string;
    prompt?: string;
    definition?: Definition;
    resources?: string[];
    verify?: string;
    model?: string;
    fork?: boolean;
    session?: string;
  },
  _cwd: string | undefined,
  runtime: AgentActionRuntime,
  sessionManager?: ExtensionContext["sessionManager"],
) {
  if (params.action === "inspect") {
    if (!params.name) throw new Error("Agent inspect requires a name.");
    requireName(params.name);
    if (!params.session) throw new Error("Agent inspect requires an exact session handle.");
    const matched = resolveExactSession(params.session, listTeammates());
    if (!matched || matched.agent !== params.name) throw new Error(`No current session "${params.session}" belongs to @${params.name}.`);
    return { action: "inspect", outcome: "inspected", agent: params.name, sessions: [session(matched)] };
  }
  if (params.action === "stop") {
    if (!params.session) throw new Error("Agent stop requires an exact session handle.");
    const matched = resolveExactSession(params.session, listTeammates());
    if (!matched) throw new Error(`No living session named "${params.session}".`);
    return runtime.shutdownTeammateExact(matched.name, matched.spawnId).then((result) => {
      if (!result.ok) throw new Error(result.error);
      return { action: "stop", outcome: "stopped", session: params.session, body: result.body };
    });
  }
  if (!params.name) throw new Error(`Agent ${params.action} requires a name.`);
  requireName(params.name);
  if (!params.definition && !resolveAgent(params.name, _cwd)) {
    throw new Error(`Unknown Agent @${params.name}. Define it inline through agent action=delegate or start; for example definition: { description: "Read evidence", prompt: "Read the assigned file and report evidence", tools: ["read"] }. Choose only needed canonical tools: ${WORKER_BUILTIN_TOOLS.join(", ")}. Omitted tools or [] grant coordination-only access.`);
  }
  const prompt = params.action === "delegate" ? params.prompt?.trim() : undefined;
  if (params.action === "delegate" && !prompt) throw new Error("Agent delegate requires a prompt.");
  if (params.action === "start" && params.fork !== undefined) throw new Error("Agent start cannot fork context.");
  const context = params.fork ? snapshotWorkContext(sessionManager) : undefined;
  const result = runtime.spawnTeammate({
    name: params.name,
    agent: params.name,
    ...(params.action === "delegate" ? { workId: `work:${randomUUID()}`, prompt, resources: params.resources, verify: params.verify, context } : {}),
    ...(params.model ? { model: params.model } : {}),
    ...(params.definition ? { definition: params.definition } : {}),
  });
  if (!result.ok) throw new Error(result.error);
  const receipt = (teammate: Teammate) => ({
    action: params.action,
    outcome: "started",
    agent: params.name,
    session: session(teammate),
    ...(params.action === "delegate" ? { work: { id: teammate.workId, state: "claimed" }, assignment: { id: teammate.assignment?.id } } : {}),
  });
  if (params.action === "start" && result.readiness) {
    return result.readiness.then((error) => {
      if (error) throw new Error(error);
      const current = resolveExactSession(exactSessionRoute(result.teammate.name, result.teammate.spawnId), listTeammates());
      if (!current || current.status === "stopped") throw new Error("Resident exited or was replaced before startup readiness completed.");
      return receipt(current);
    });
  }
  return receipt(result.teammate);
}
