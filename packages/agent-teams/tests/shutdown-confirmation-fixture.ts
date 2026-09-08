import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { mock } from "node:test";
import * as kit from "@fradser/pi-kit";

const child = Object.assign(new EventEmitter(), {
  pid: 100,
  stdin: new PassThrough(),
  stdout: new PassThrough(),
  stderr: new PassThrough(),
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
const { isWorkerCloseObserved } = await import("../src/spawner.ts");
const { initTeamMachine, shutdownTeamMachine, shutdownTeammate, spawnTeammate, sendLeaderMessage, getConfirmedStopTime } = await import("../src/team-machine.ts");
const { resetState, registerTeammate, getTeammate, createTask, setTaskClaimed, getTask, getState } = await import("../src/state.ts");
resetState();
initTeamMachine({ cwd: process.env.HOME! }, { sendUpdate: () => {}, notifyChange: () => {} });
try {
  const spawned = spawnTeammate({ name: "worker", agent: "fixture-role", definition: { description: "Isolated fixture", prompt: "Do not execute", tools: [] } });
  if (!spawned.ok) throw new Error(spawned.error);
  const spawnId = spawned.teammate.spawnId;
  const task = createTask({ subject: "owned work", resources: ["src/owned"] }).task!;
  setTaskClaimed(task.id, "worker");
  const result = await shutdownTeammate("worker");
  const initial = { result, terminationCalls, closeObserved: isWorkerCloseObserved("worker"), status: getTeammate("worker")?.status, task: { ...getTask(task.id) }, stopTime: getConfirmedStopTime(spawnId) ?? null, stoppedSummaries: getState().leaderMailbox.filter((message) => message.subject === "Agent stopped").length };
  const rejected = sendLeaderMessage("worker", "new work", { reopen: true });
  const mode = process.argv[2];
  if (mode === "retry") {
    confirmTermination = true;
    const retry = await shutdownTeammate("worker");
    console.log(JSON.stringify({ initial, rejected, retry, status: getTeammate("worker")?.status, stopTime: getConfirmedStopTime(spawnId), task: getTask(task.id) }));
  } else if (mode === "delayed") {
    child.emit("close", 0, null);
    await new Promise((resolve) => setImmediate(resolve));
    const stopped = { ...getTeammate("worker") };
    const stopTime = getConfirmedStopTime(spawnId);
    registerTeammate({ name: "worker", agent: "role", spawnId: "replacement", pid: 101, status: "working", isolation: "none", createdAt: 1, updatedAt: 1 });
    const absent = await shutdownTeammate("worker");
    const retained = getConfirmedStopTime(spawnId);
    const replacementTime = getConfirmedStopTime("replacement");
    shutdownTeamMachine();
    console.log(JSON.stringify({ initial, rejected, stopped, stopTime, retained, absent, replacementTime, resetTime: getConfirmedStopTime(spawnId) ?? null }));
  } else {
    console.log(JSON.stringify(initial));
  }
} finally {
  shutdownTeamMachine();
  child.emit("close", 0, null);
  mock.restoreAll();
}
