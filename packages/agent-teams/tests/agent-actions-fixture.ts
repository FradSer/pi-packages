import assert from "node:assert/strict";
import { runAgentAction } from "../src/agent-actions.ts";
import { registerSessionAgent } from "../src/agents.ts";
import { registerTeammate, resetState } from "../src/state.ts";

resetState();
registerSessionAgent({ name: "reviewer", description: "Review", prompt: "Review", tools: [] });
const spawned: any[] = [];
const runtime = {
  spawnTeammate(input: any) {
    const teammate = { name: input.name, agent: input.agent, spawnId: `s-${spawned.length}`, workId: input.workId, status: "starting", assignment: input.prompt ? { id: `direct-${spawned.length}` } : undefined };
    spawned.push({ input, teammate });
    registerTeammate({ ...teammate, pid: 0, isolation: "none", createdAt: 1, updatedAt: 1 });
    return { ok: true as const, teammate };
  },
  async shutdownTeammateExact(_name: string, spawnId: string) {
    return spawnId === "s-0" ? { ok: true as const, body: "stopped" } : { ok: false as const, error: "wrong session" };
  },
};

const delegated = runAgentAction({ action: "delegate", name: "reviewer", prompt: "Audit", resources: ["src/auth"] }, undefined, runtime);
assert.equal(delegated.action, "delegate");
assert.equal(spawned[0].input.name, "reviewer");
assert.equal(delegated.session.id, "session:reviewer:s-0");
assert.equal(delegated.work.id, spawned[0].teammate.workId);
const started = runAgentAction({ action: "start", name: "context-markdown-fix", definition: { description: "Fix Markdown", prompt: "Fix Markdown" } }, undefined, runtime);
assert.equal(spawned[1].input.name, "context-markdown-fix");
assert.equal(started.session.id, "session:context-markdown-fix:s-1");
assert.equal(started.action, "start");
assert.equal(started.work, undefined);
const inspected = runAgentAction({ action: "inspect", name: "reviewer", session: delegated.session.id }, undefined, runtime);
assert.deepEqual(inspected.sessions.map((entry) => entry.id), [delegated.session.id]);
assert.throws(() => runAgentAction({ action: "inspect", name: "reviewer", session: "session:reviewer-0:stale" }, undefined, runtime), /No current session/);
const stopped = await runAgentAction({ action: "stop", session: delegated.session.id }, undefined, runtime);
assert.equal(stopped.outcome, "stopped");
const inline = runAgentAction({ action: "delegate", name: "inline", prompt: "Audit", definition: { description: "inline", prompt: "audit" } }, undefined, runtime);
assert.equal(inline.action, "delegate");
console.log("AGENT_ACTIONS_OK");
