/**
 * Test-side composition of the bundle.
 *
 * In production the agent-teams manifest loads the pi-subagents extension
 * alongside its own. The task domain is internal and registers no model-facing
 * tool, so a test composes exactly the two tool owners a real install has.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { exactSessionRoute, registerIntentTools, setAgentHost, type AgentStartRequest } from "@fradser/pi-subagents";
import { registerLeaderTools } from "../src/tools.ts";
import type { AgentActionRuntime } from "../src/agent-actions.ts";
import { sendResidentSequence, interruptResidentSequence } from "../src/team-machine.ts";

/** The shape a test mocks the team spawner with. Matches `spawnAgent`. */
export interface FakeTeamRuntime extends AgentActionRuntime {
  shutdownAgentExact(name: string, spawnId: string): Promise<{ ok: true; body?: string } | { ok: false; error: string }>;
}

/** Register the tools a real install exposes: `message` and the agent family. */
export function registerComposedTools(
  pi: Pick<ExtensionAPI, "registerTool">,
  runtime?: FakeTeamRuntime & { sendLeaderMessage: (...args: never[]) => never },
  options: { agent?: boolean } = {},
): void {
  registerLeaderTools(pi as ExtensionAPI, runtime as never);
  if (options.agent !== false) registerIntentTools(pi as ExtensionAPI);
}

/**
 * Publish a team runtime as the `agent` tool's coordinator.
 *
 * The `agent` tool belongs to @fradser/pi-subagents, which owns the child
 * process and nothing about how a team spawns one. That is why the seam is a
 * published host rather than a constructor argument: a test that mocks the team
 * spawner has to publish it, exactly as a real team runtime does, or the tool
 * would quietly take the raw-spawner path and the mock would never run.
 */
export function publishTeamHost(runtime: FakeTeamRuntime): void {
  setAgentHost({
    async start(request: AgentStartRequest) {
      const definition = request.definition
        ? {
          description: request.definition.description,
          prompt: request.definition.prompt,
          ...(request.definition.tools ? { tools: request.definition.tools } : {}),
          ...(request.definition.model ? { model: request.definition.model } : {}),
        }
        : undefined;
      const spawned = runtime.spawnAgent({
        name: request.name,
        role: request.name,
        ...(request.model ? { model: request.model } : {}),
        ...(request.prompt ? { prompt: request.prompt } : {}),
        ...(definition ? { definition } : {}),
        ...(request.tools && !definition ? { tools: request.tools } : {}),
      } as never);
      if (!spawned.ok) return spawned;
      const agent = (spawned as { agent: { name: string; spawnId: string } }).agent;
      // A team spawn proves the child is up before it hands back a handle, so the
      // host awaits its own readiness rather than leaving "started" unverified.
      const readiness = (spawned as { readiness?: Promise<string | undefined> }).readiness;
      if (readiness) {
        const failure = await readiness;
        if (failure) return { ok: false, error: failure };
      }
      return { ok: true, session: exactSessionRoute(agent.name, agent.spawnId) };
    },
    send: sendResidentSequence,
    interrupt: interruptResidentSequence,
    stop: (name, spawnId) => runtime.shutdownAgentExact(name, spawnId),
  });
}
