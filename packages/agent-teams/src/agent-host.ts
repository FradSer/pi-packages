/**
 * Publish this package as the `agent` tool's coordinator.
 *
 * `@fradser/pi-subagents` owns the child process and knows nothing about teams. It
 * reaches a team spawn only through this seam, and without a host published it
 * takes its standalone path: the process starts, the roster learns about it, and
 * its output goes nowhere.
 *
 * That last part is why this exists rather than a convenience. The standalone path
 * records only exit status, so a child that did real work would finish and its
 * answer would be discarded. A team runtime is the thing that turns a child's
 * output back into something the leader reads, and the leader is what a team
 * runtime is for.
 *
 * Publishing also moves spawn to the team path as a side effect, and that is
 * intended: the team path is the one that assigns work, records the attempt, and
 * routes the result. The difference is observable — the team path refuses a name
 * with no role, because a resident is a role with a process attached, while the
 * standalone path will synthesise one — and `features/` pins it.
 */

import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { resolveAgent, setAgentHost, snapshotWorkContext, type AgentStartRequest } from "@fradser/pi-subagents";
import { shutdownTeammateExact, spawnTeammate } from "./team-machine.ts";

/** Wire `agent` to this package's spawn and shutdown. Safe to call more than
 *  once: a reload republishes rather than stacking hosts. */
export function publishAgentHost(sessionManager?: ExtensionContext["sessionManager"]): void {
  setAgentHost({
    async start(request: AgentStartRequest) {
      const role = request.definition ?? resolveAgent(request.name);
      const spawned = spawnTeammate({
        name: request.name,
        agent: request.name,
        ...(request.model ? { model: request.model } : {}),
        ...(request.prompt ? { prompt: request.prompt } : {}),
        ...(role
          ? {
            definition: {
              description: role.description,
              prompt: role.prompt,
              tools: request.tools ?? role.tools ?? [],
              ...(role.model ? { model: role.model } : {}),
            },
          }
          : {}),
        // `fork` asks for a snapshot of the leader's active context. The snapshot
        // is taken here rather than in the tool, because the tool has no session
        // manager and the seam is what owns this package's spawn.
        ...(request.fork && sessionManager
          ? { context: snapshotWorkContext(sessionManager) }
          : {}),
      });
      if (!spawned.ok) return spawned;
      const teammate = spawned.teammate;
      // A team spawn proves the child is up before a handle is handed back, so the
      // readiness wait belongs to whoever owns the spawn — here.
      if (spawned.readiness) {
        const failure = await spawned.readiness;
        if (failure) return { ok: false as const, error: failure };
      }
      return {
        ok: true as const,
        session: exactRoute(teammate.name, teammate.spawnId),
      };
    },
    stop: (name, spawnId) => shutdownTeammateExact(name, spawnId),
  });
}

function exactRoute(name: string, spawnId: string): string {
  return `session:${name}:${spawnId}`;
}
