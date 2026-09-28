/**
 * Test-side composition of the bundle.
 *
 * In production the agent-teams manifest loads the pi-subagents and pi-tasks
 * extension entries alongside its own, which is how one package ends up with
 * three tools while each tool still has exactly one registrant. A test that
 * needs more than `message` has to compose the same way, or it would be asserting
 * against a hand-built surface no install can produce.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { registerTaskTool } from "@fradser/pi-tasks";
import { exactSessionRoute, registerAgentTool, setAgentHost, type AgentStartRequest } from "@fradser/pi-subagents";
import { registerLeaderTools } from "../src/tools.ts";
import type { AgentActionRuntime } from "../src/agent-actions.ts";

/** The shape a test mocks the team spawner with. Matches `spawnTeammate`. */
export interface FakeTeamRuntime extends AgentActionRuntime {
  shutdownTeammateExact(name: string, spawnId: string): Promise<{ ok: true; body?: string } | { ok: false; error: string }>;
}

/** Register all three tools, each by its owning package. */
export function registerComposedTools(
  pi: Pick<ExtensionAPI, "registerTool">,
  runtime?: FakeTeamRuntime & { sendLeaderMessage: (...args: never[]) => never },
  options: { agent?: boolean; task?: boolean } = {},
): void {
  registerLeaderTools(pi as ExtensionAPI, runtime as never);
  if (options.agent !== false) registerAgentTool(pi as ExtensionAPI);
  if (options.task !== false) registerTaskTool(pi as ExtensionAPI);
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
      const spawned = runtime.spawnTeammate({
        name: request.name,
        agent: request.name,
        ...(request.model ? { model: request.model } : {}),
        ...(request.prompt ? { prompt: request.prompt } : {}),
        ...(definition ? { definition } : {}),
        ...(request.tools && !definition ? { tools: request.tools } : {}),
      } as never);
      if (!spawned.ok) return spawned;
      const teammate = (spawned as { teammate: { name: string; spawnId: string } }).teammate;
      // A team spawn proves the child is up before it hands back a handle, so the
      // host awaits its own readiness rather than leaving "started" unverified.
      const readiness = (spawned as { readiness?: Promise<string | undefined> }).readiness;
      if (readiness) {
        const failure = await readiness;
        if (failure) return { ok: false, error: failure };
      }
      return { ok: true, session: exactSessionRoute(teammate.name, teammate.spawnId) };
    },
    stop: (name, spawnId) => runtime.shutdownTeammateExact(name, spawnId),
  });
}
