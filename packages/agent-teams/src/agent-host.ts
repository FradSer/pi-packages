/**
 * Publish this package as the `agent` tool's coordinator.
 *
 * `@fradser/pi-subagents` owns the child process and knows nothing about teams. It
 * reaches a team spawn only through this seam, and without a host published it
 * takes its standalone path and delivers a Session Result itself. A hosted child
 * instead uses the team's attempt-bound report pipeline; exactly one path owns
 * each result.
 *
 * Publishing also moves spawn to the team path as a side effect, and that is
 * intended: the team path is the one that assigns work, records the attempt, and
 * routes the result. The difference is observable — the team path refuses a name
 * with no role, because a resident is a role with a process attached, while the
 * standalone path will synthesise one — and `features/` pins it.
 */

import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { setAgentHost, snapshotWorkContext, type AgentStartRequest } from "@fradser/pi-subagents";
import { authorizeResidentInput, interruptResidentSequence, sendResidentSequence, shutdownAgentExact, spawnAgent } from "./team-machine.ts";

/** Wire `agent` to this package's spawn and shutdown. Safe to call more than
 *  once: a reload republishes rather than stacking hosts. */
export function publishAgentHost(sessionManager?: ExtensionContext["sessionManager"]): void {
  setAgentHost({
    async start(request: AgentStartRequest) {
      const spawned = spawnAgent({
        name: request.name,
        role: request.name,
        ...(request.model ? { model: request.model } : {}),
        ...(request.prompt ? { prompt: request.prompt } : {}),
        ...(request.tools !== undefined ? { tools: request.tools } : {}),
        // Resolve disk roles against the machine's project cwd, not this
        // module's process.cwd(); the disk definition always wins inline input.
        ...(request.definition ? { definition: request.definition } : {}),
        // `fork` asks for a snapshot of the leader's active context. The snapshot
        // is taken here rather than in the tool, because the tool has no session
        // manager and the seam is what owns this package's spawn.
        ...(request.fork && sessionManager
          ? { context: snapshotWorkContext(sessionManager) }
          : {}),
      });
      if (!spawned.ok) return spawned;
      const agent = spawned.agent;
      // Prompted starts await accepted input; idle starts await native readiness.
      // Neither outcome is proof the child's work has completed.
      if (spawned.readiness) {
        const failure = await spawned.readiness;
        if (failure) return { ok: false as const, error: failure };
      }
      return {
        ok: true as const,
        session: exactRoute(agent.name, agent.spawnId),
      };
    },
    authorizeInput: authorizeResidentInput,
    send: sendResidentSequence,
    interrupt: interruptResidentSequence,
    stop: (name, spawnId) => shutdownAgentExact(name, spawnId),
  });
}

function exactRoute(name: string, spawnId: string): string {
  return `session:${name}:${spawnId}`;
}
