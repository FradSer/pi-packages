import { EventEmitter } from "node:events";
import { readFileSync, writeFileSync } from "node:fs";
import { PassThrough } from "node:stream";
import { mock } from "node:test";
import * as kit from "@fradser/pi-kit";

const child = Object.assign(new EventEmitter(), {
  pid: 100,
  stdin: new PassThrough(),
  stdout: new PassThrough(),
  stderr: new PassThrough(),
});
child.stdin.on("data", chunk => {
  const command = JSON.parse(String(chunk));
  if (command.type !== "get_state") return;
  setImmediate(() => child.stdout.write(`${JSON.stringify({
    type: "response", id: command.id, command: "get_state", success: true,
    data: { isStreaming: false, isCompacting: false, pendingMessageCount: 0 },
  })}\n`));
});
let terminationCalls = 0;
let confirmTermination = false;
mock.module("@fradser/pi-kit", {
  namedExports: {
    ...kit,
    resolvePiCli: () => ({ command: "unused-mock", args: [] }),
    spawnPiChild: () => child,
    terminateChildProcess: async (target: unknown) => {
      if (target !== child) throw new Error("Expected registered mock child");
      terminationCalls++;
      if (confirmTermination) child.emit("close", 0, null);
      return confirmTermination;
    },
  },
});
mock.method(Date, "now", () => 1234567890000);
const { isProcessCloseObserved } = await import("@fradser/pi-subagents");
const { initTeamMachine, shutdownTeamMachine, shutdownAgent, spawnAgent, sendLeaderMessage, getConfirmedStopTime } = await import("../src/team-machine.ts");
const { resetState, registerAgent, updateAgent, getAgent, createTask, takeTask, completeTaskWithOutcome, getTask, getState,
  getPeerInboxOffset, markPeerDelivered } = await import("../src/state.ts");
const { appendInboxMessage, inboxPath, stateFilePath } = await import("../src/statefile.ts");
const reports: Array<{ harnessEvent?: { type: string }; body: string }> = [];
const mode = process.argv[2];
resetState();
initTeamMachine({ cwd: process.env.HOME! }, { sendUpdate: report => reports.push(report), notifyChange: () => {} });
try {
  const spawned = spawnAgent({ name: "worker", role: "fixture-role", definition: { description: "Isolated fixture", prompt: "Do not execute", tools: [] } });
  if (!spawned.ok) throw new Error(spawned.error);
  const spawnId = spawned.agent.spawnId;
  const task = createTask({ subject: "owned work", resources: ["src/owned"] }).task!;
  takeTask(task.id, "worker");
  if (mode?.startsWith("close-")) {
    const readinessError = await spawned.readiness;
    if (readinessError) throw new Error(readinessError);
    if (mode !== "close-owned" && mode !== "close-unreported") {
      const completed = completeTaskWithOutcome(task.id, "worker", "success", "Accepted review evidence");
      if (!completed.ok) throw new Error(completed.reason);
    }
    const starting = mode === "close-unreported";
    updateAgent("worker", {
      status: starting ? "working" : "idle",
      // A report can finish before acceptance. Held work still needs an alarm.
      ...(mode === "close-owned" ? { reportSequenceEnded: true } : {}),
    });
    const inbox = inboxPath(stateFilePath(undefined, process.env.HOME!), "worker");
    let inboxBefore: string | undefined;
    let inboxStateBefore: string | undefined;
    if (mode.startsWith("close-mail-")) {
      if (mode === "close-mail-late") {
        for (let index = 0; index < 6; index += 1) {
          appendInboxMessage(inbox, {
            id: `stale-${index}`, from: "leader", subject: "Earlier request", body: "x".repeat(60000),
            ...{ toSpawnId: "earlier-incarnation" },
          });
        }
      }
      const message = {
        id: "unread-request", from: "leader", subject: "Pending request", body: "Inspect the remaining evidence",
        ...(mode === "close-mail-unbound" ? {} : { toSpawnId: mode === "close-mail-stale" ? "earlier-incarnation" : spawnId }),
      };
      appendInboxMessage(inbox, message);
      // Invent corrupted input at the existing file seam, not in the parser.
      if (mode === "close-mail-invalid-body") writeFileSync(inbox, `${JSON.stringify({ ...message, body: null })}\n`);
      if (mode === "close-mail-invalid-binding") writeFileSync(inbox, `${JSON.stringify({ ...message, toSpawnId: 7 })}\n`);
      if (mode === "close-mail-broken-json") writeFileSync(inbox, "{invalid JSON}\n");
      if (mode === "close-mail-incomplete") writeFileSync(inbox, JSON.stringify(message));
      if (mode === "close-mail-delivered") markPeerDelivered("worker", message.id);
      inboxBefore = readFileSync(inbox, "utf8");
      inboxStateBefore = JSON.stringify([getPeerInboxOffset("worker"), getState().peerDeliveredIds, getState().peerDeliveryStates]);
    }
    const exitCode = mode === "close-crash" ? 1 : mode === "close-signal" ? null : 0;
    const signal = mode === "close-signal" ? "SIGTERM" : null;
    child.emit("close", exitCode, signal);
    await new Promise(resolve => setImmediate(resolve));
    child.emit("close", exitCode, signal);
    await new Promise(resolve => setImmediate(resolve));
    console.log(JSON.stringify({
      status: getAgent("worker")?.status,
      error: getAgent("worker")?.error ?? null,
      stopTime: getConfirmedStopTime(spawnId),
      task: getTask(task.id), reports,
      inboxUnchanged: inboxBefore === undefined || inboxBefore === readFileSync(inbox, "utf8"),
      deliveryStateUnchanged: inboxStateBefore === undefined || inboxStateBefore
        === JSON.stringify([getPeerInboxOffset("worker"), getState().peerDeliveredIds, getState().peerDeliveryStates]),
      mailbox: getState().leaderMailbox.map(message => ({ subject: message.subject, body: message.body })),
    }));
  } else {
    const result = await shutdownAgent("worker");
    const initial = { result, terminationCalls, closeObserved: isProcessCloseObserved("worker"), status: getAgent("worker")?.status, task: { ...getTask(task.id) }, stopTime: getConfirmedStopTime(spawnId) ?? null, stoppedSummaries: getState().leaderMailbox.filter((message) => message.subject === "Agent stopped").length };
    const rejected = sendLeaderMessage("worker", "new work", { reopen: true });
    if (mode === "retry") {
      confirmTermination = true;
      const retry = await shutdownAgent("worker");
      console.log(JSON.stringify({ initial, rejected, retry, status: getAgent("worker")?.status, stopTime: getConfirmedStopTime(spawnId), task: getTask(task.id) }));
    } else if (mode === "delayed") {
      child.emit("close", 0, null);
      await new Promise((resolve) => setImmediate(resolve));
      const stopped = { ...getAgent("worker") };
      const stopTime = getConfirmedStopTime(spawnId);
      registerAgent({ name: "worker", role: "role", spawnId: "replacement", pid: 101, status: "working", createdAt: 1, updatedAt: 1 });
      const absent = await shutdownAgent("worker");
      const retained = getConfirmedStopTime(spawnId);
      const replacementTime = getConfirmedStopTime("replacement");
      shutdownTeamMachine();
      console.log(JSON.stringify({ initial, rejected, stopped, stopTime, retained, absent, replacementTime, resetTime: getConfirmedStopTime(spawnId) ?? null }));
    } else {
      console.log(JSON.stringify(initial));
    }
  }
} finally {
  shutdownTeamMachine();
  child.emit("close", 0, null);
  mock.restoreAll();
}
