import assert from "node:assert/strict";
import { registerLeaderTools } from "../src/tools.ts";
import { initTeamMachine, processTaskIntents, setVerifyGateRunner, shutdownTeamMachine } from "../src/team-machine.ts";
import { applyClaimIntent, createDirectWork, createTask, getState, registerTeammate, resetState, updateTeammate } from "../src/state.ts";
import { attemptSubmission } from "../src/team-machine.ts";

const root = process.env.PI_TEST_DIR;
assert.ok(root, "PI_TEST_DIR is required");
resetState();
initTeamMachine({ sessionManager: undefined, cwd: root }, { sendUpdate() {}, notifyChange() {} });
const tools = new Map();
registerLeaderTools({ registerTool(tool) { tools.set(tool.name, tool); }, getActiveTools: () => [], setActiveTools() {} });
const work = tools.get("work");
assert.ok(work, "work must be registered");
registerTeammate({ name: "holder", agent: "reviewer", spawnId: "s1", pid: 1, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 });
createDirectWork({ id: "held-work", subject: "Held Work", resources: ["firmware/storage"], workerName: "holder", assignment: { id: "direct:s1", kind: "direct", resources: ["firmware/storage"] } });

const released = await work.execute("release", { action: "release", id: "held-work", reason: "Scope changed" });
assert.equal(released.details.action, "release");
assert.equal(released.details.outcome, "released");
assert.equal(released.details.state, "pending");
assert.equal(released.details.work.id, "held-work");
// The holder was still working, so the residual write window is reported.
assert.equal(released.details.holderStillRunning, "holder");
assert.match(released.content[0].text, /RISK · @holder was still working/);
assert.equal(getState().tasks["held-work"]?.status, "pending");
assert.equal(getState().tasks["held-work"]?.claimedBy, undefined);
assert.equal(getState().tasks["held-work"]?.errorMessage, "Scope changed");
assert.equal(getState().teammates.holder.assignment, undefined);

const board = createTask({ subject: "Board held" }).task;
applyClaimIntent({ taskId: board.id, worker: "holder", spawnId: "s1", timestamp: 1 });
const boardReleased = await work.execute("board-release", { action: "release", id: board.id, reason: "Board scope changed" });
assert.equal(boardReleased.details.state, "pending");
assert.equal(getState().tasks[board.id]?.status, "pending");
assert.equal(getState().teammates.holder.assignment, undefined);

const superseded = createTask({ subject: "Superseded held" }).task;
applyClaimIntent({ taskId: superseded.id, worker: "holder", spawnId: "s1", timestamp: 2 });
getState().tasks[superseded.id].status = "superseded";
await assert.rejects(work.execute("superseded", { action: "release", id: superseded.id, reason: "not leader release" }), /not claimed/i);
assert.equal(getState().tasks[superseded.id]?.status, "superseded");
updateTeammate("holder", { assignment: undefined, currentTaskId: undefined });
getState().tasks[superseded.id].claimedBy = undefined;

const gated = createTask({ subject: "Gated held", verify: "verify" }).task;
applyClaimIntent({ taskId: gated.id, worker: "holder", spawnId: "s1", timestamp: 3 });
let releaseGate: (() => void) | undefined;
setVerifyGateRunner(() => new Promise((resolve) => { releaseGate = () => resolve({ kind: "pass" }); }));
attemptSubmission("holder", "s1", gated.id, "completed", "candidate");
processTaskIntents();
await new Promise((resolve) => setImmediate(resolve));
await work.execute("gate-release", { action: "release", id: gated.id, reason: "Cancel review" });
releaseGate!();
await new Promise((resolve) => setImmediate(resolve));
assert.equal(getState().tasks[gated.id]?.status, "pending");
assert.equal(getState().tasks[gated.id]?.claimedBy, undefined);
setVerifyGateRunner(undefined);

await assert.rejects(work.execute("pending", { action: "release", id: "held-work", reason: "again" }), /not claimed/i);
getState().tasks["held-work"].status = "completed";
await assert.rejects(work.execute("completed", { action: "release", id: "held-work", reason: "again" }), /not claimed/i);

shutdownTeamMachine();
console.log("WORK_RELEASE_OK");
