import assert from "node:assert/strict";
import path from "node:path";
import { deliverResidentPrompt, type LeaderReport } from "@fradser/pi-subagents";
import { getAgent, getState, resetState } from "../src/state.ts";
import { initTeamMachine, spawnAgent, shutdownTeamMachine, teardownAgents } from "../src/team-machine.ts";
import { appendInboxMessage, inboxPath, stateFilePath } from "../src/statefile.ts";

const cwd = process.env.PI_TEST_DIR!;
assert.ok(cwd && process.env.PI_CODING_AGENT_DIR);
const unreadMail = process.env.PI_TEST_UNREAD_MAIL === "1";
const reports: LeaderReport[] = [];
const closed = Promise.withResolvers<void>();
let startedPid = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
resetState();
initTeamMachine({ cwd, sessionManager: { getSessionFile: () => path.join(cwd, "leader.jsonl") } } as never, {
  sendUpdate: report => reports.push(report),
  notifyChange: () => { if (getAgent("clean-close")?.status === "stopped") closed.resolve(); },
});
try {
  const started = spawnAgent({
    name: "clean-close", role: "native-close-fixture",
    definition: { description: "Native clean-close fixture", prompt: "Do not request a model", tools: [] },
  });
  assert.equal(started.ok, true);
  if (!started.ok) throw new Error(started.error);
  assert.equal(await started.readiness, undefined);
  assert.equal(getAgent("clean-close")?.status, "idle");
  startedPid = started.agent.pid;
  timer = setTimeout(() => closed.reject(new Error("Native child did not close after its shutdown command")), 15_000);
  if (unreadMail) {
    appendInboxMessage(inboxPath(stateFilePath(path.join(cwd, "leader.jsonl"), cwd), "clean-close"), {
      id: "native-unread", from: "leader", subject: "Remaining input", body: "Inspect the remaining evidence",
      ...{ toSpawnId: started.agent.spawnId },
    });
  }
  // This slash command executes inside the native child. It uses no model.
  await deliverResidentPrompt("clean-close", "/clean-close-test");
  await closed.promise;
  const stopped = getAgent("clean-close")!;
  assert.equal(stopped.status, "stopped");
  assert.equal(stopped.error, undefined);
  assert.equal(reports.length, unreadMail ? 1 : 0, "Only a clean close with no unread input may stay passive");
  if (unreadMail) assert.equal(reports[0].harnessEvent?.type, "unexpected-stop");
  assert.equal(getState().leaderMailbox.at(-1)?.subject, unreadMail ? "Agent stopped unexpectedly" : "Agent stopped");
  console.log(JSON.stringify({
    nativePid: startedPid, status: stopped.status, unexpectedReports: reports.length,
    subject: getState().leaderMailbox.at(-1)?.subject,
  }));
} finally {
  if (timer) clearTimeout(timer);
  await teardownAgents();
  shutdownTeamMachine();
  resetState();
}
