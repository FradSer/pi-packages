import assert from "node:assert/strict";
import { runAgentAction } from "../src/agent-actions.ts";
import { registerSessionAgent } from "@fradser/pi-subagents";
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

// A prompt is delivered, not recorded. There is no work id and no resource
// lease, because a spawn creates no task and a task is the only thing that can
// hold resources.
const prompted = runAgentAction({ action: "start", name: "reviewer", prompt: "Audit" }, undefined, runtime);
assert.equal(prompted.action, "start");
assert.equal(prompted.prompted, true);
assert.equal(spawned[0].input.name, "reviewer");
assert.equal(spawned[0].input.prompt, "Audit");
assert.equal(spawned[0].input.workId, undefined, "a spawn must not fabricate a work identity");
assert.equal(prompted.session.id, "session:reviewer:s-0");
assert.equal(prompted.work, undefined, "a spawn receipt carries no work");
// Without a prompt it is an idle resident, and that is not an error.
const started = runAgentAction({ action: "start", name: "context-markdown-fix", definition: { description: "Fix Markdown", prompt: "Fix Markdown" } }, undefined, runtime);
assert.equal(spawned[1].input.name, "context-markdown-fix");
assert.equal(spawned[1].input.prompt, undefined, "no prompt means no kickoff turn");
assert.equal(started.session.id, "session:context-markdown-fix:s-1");
assert.equal(started.action, "start");
assert.equal(started.prompted, false);
// fork is legal with and without a prompt: it seeds context, it does not demand work.
const sessionManager = { getBranch: () => "", getLeafId: () => undefined } as never;
const forked = runAgentAction({ action: "start", name: "forked", prompt: "go", fork: true, definition: { description: "fork probe", prompt: "probe" } }, undefined, runtime, sessionManager);
assert.equal(forked.outcome, "started");
const forkedIdle = runAgentAction({ action: "start", name: "forked-idle", fork: true, definition: { description: "fork probe", prompt: "probe" } }, undefined, runtime, sessionManager);
assert.equal(forkedIdle.prompted, false);
// A prompt with no role is refused: the child would run without instructions and
// report a result nobody asked for. A name-only start stays an idle resident.
assert.throws(() => runAgentAction({ action: "start", name: "roleless", prompt: "go" }, undefined, runtime), /prompt needs a role/);
assert.equal(runAgentAction({ action: "start", name: "roleless" }, undefined, runtime).prompted, false);
const inspected = runAgentAction({ action: "inspect", name: "reviewer", session: prompted.session.id }, undefined, runtime);
assert.deepEqual(inspected.sessions.map((entry) => entry.id), [prompted.session.id]);
assert.throws(() => runAgentAction({ action: "inspect", name: "reviewer", session: "session:reviewer-0:stale" }, undefined, runtime), /No current session/);
const stopped = await runAgentAction({ action: "stop", session: prompted.session.id }, undefined, runtime);
assert.equal(stopped.outcome, "stopped");
const inline = runAgentAction({ action: "start", name: "inline", prompt: "Audit", definition: { description: "inline", prompt: "audit" } }, undefined, runtime);
assert.equal(inline.action, "start");
assert.equal(spawned[spawned.length - 1].input.definition.prompt, "audit");
// Half a role is refused: the missing half would produce a child with no
// instructions and no error.
assert.throws(() => runAgentAction({ action: "start", name: "half", definition: { description: "only this" } as never }, undefined, runtime),
  /prompt|description/);
console.log("AGENT_ACTIONS_OK");
