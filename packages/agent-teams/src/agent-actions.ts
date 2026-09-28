import { WORKER_BUILTIN_TOOLS } from "@fradser/pi-subagents";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { isValidTeammateName, listTeammates } from "./state.ts";
import { resolveAgent } from "@fradser/pi-subagents";
import { shutdownTeammateExact, spawnTeammate } from "./team-machine.ts";
import { normalizeCoordinationParams, requireParsedParams, type Teammate } from "./types.ts";
import { snapshotWorkContext } from "@fradser/pi-subagents";
import { exactSessionRoute, resolveExactSession } from "./recipient.ts";

export interface AgentActionRuntime {
  spawnTeammate: typeof spawnTeammate;
  shutdownTeammateExact: typeof shutdownTeammateExact;
}

type Definition = Parameters<typeof spawnTeammate>[0]["definition"];

function session(teammate: Teammate) {
  const tools = teammate.tools;
  const coordinationOnly = tools !== undefined && tools.every((tool) => tool === "message" || tool === "task");
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
    action: "start" | "inspect" | "stop";
    name?: string;
    prompt?: string;
    definition?: Definition;
    model?: string;
    fork?: boolean;
    session?: string;
  },
  _cwd: string | undefined,
  runtime: AgentActionRuntime,
  sessionManager?: ExtensionContext["sessionManager"],
) {
  // Harnesses that cannot infer object types from union-root schemas deliver
  // `definition`/`resources` as JSON strings; parse before branching on them.
  params = requireParsedParams(normalizeCoordinationParams(params as Record<string, unknown>, ["definition", "resources"]), ["definition", "resources"]) as typeof params;
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
      // The name comes from the resolved session, not from the request: a stop
      // carries only a handle, so a receipt keyed on the request would be unnamed
      // and a row drawn from it would have nothing to show.
      return { action: "stop", outcome: "stopped", agent: matched.name, session: params.session, body: result.body };
    });
  }
  if (!params.name) throw new Error("Agent start requires a name.");
  requireName(params.name);
  if (params.definition !== undefined) {
    const role = params.definition as { description?: string; prompt?: string };
    const hasDescription = typeof role.description === "string" && role.description.trim().length > 0;
    const hasPrompt = typeof role.prompt === "string" && role.prompt.trim().length > 0;
    // Both halves or neither. Half a role produces a child that reports a result
    // nobody asked for, because it has no instructions and nothing told it to
    // wait.
    if (hasDescription !== hasPrompt) {
      throw new Error("An inline role needs both description and role_prompt, or neither.");
    }
  }
  // A prompt needs a role; an idle resident does not. A prompted child with no
  // role would run without instructions and report a result nobody asked for,
  // which is worse than refusing. A child started with no prompt is waiting for
  // work, and requiring a role up front would make the normal two spawn shapes —
  // do this one thing, or sit ready — behave differently from the tool.
  if (params.prompt && !params.definition && !resolveAgent(params.name, _cwd)) {
    throw new Error(`A prompt needs a role. @${params.name} has no definition: pass description and role_prompt, or use a name that already has one. Choose only needed canonical tools: ${WORKER_BUILTIN_TOOLS.join(", ")}. Omitted tools or [] grant coordination-only access.`);
  }
  // One spawn verb with an optional prompt. `delegate` and `start` were the same
  // operation dispatched twice, and the only difference was whether a prompt was
  // delivered; two names meant a caller had to pick between two identically
  // shaped paths and the wrong pick was invisible.
  const prompt = params.prompt?.trim();
  if (params.prompt !== undefined && !prompt) throw new Error("An empty prompt is not a task. Omit it to leave the agent idle.");
  const context = params.fork ? snapshotWorkContext(sessionManager) : undefined;
  const result = runtime.spawnTeammate({
    name: params.name,
    agent: params.name,
    // A prompt is delivered, not recorded: spawning creates no task, so there is
    // no work id, no resource lease, and no verify gate to attach. Anything that
    // needs a record is a task the caller creates and the participant takes.
    ...(prompt ? { prompt } : {}),
    ...(params.model ? { model: params.model } : {}),
    ...(params.definition ? { definition: params.definition } : {}),
    ...(context ? { context } : {}),
  });
  if (!result.ok) throw new Error(result.error);
  const receipt = (teammate: Teammate) => ({
    action: "start",
    outcome: "started",
    agent: params.name,
    prompted: Boolean(prompt),
    session: session(teammate),
  });
  // Readiness is awaited whenever the host offers it. A handle is the caller's
  // only evidence that anything exists, and a child that answered proves more than
  // one that was forked off.
  if (result.readiness) {
    return result.readiness.then((error) => {
      if (error) throw new Error(error);
      const current = resolveExactSession(exactSessionRoute(result.teammate.name, result.teammate.spawnId), listTeammates());
      if (!current || current.status === "stopped") throw new Error("Resident exited or was replaced before startup readiness completed.");
      return receipt(current);
    });
  }
  return receipt(result.teammate);
}
