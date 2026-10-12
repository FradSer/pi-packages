import fs from "node:fs";
import { isDeepStrictEqual } from "node:util";
import { failureObservationReady, failureObservationExtensionReady, successfulFailureObservationReady, type FailureObservationInput } from "./failure-observation-proof";
import { recentProjectLearningInput } from "../extensions/learning-input";
import { createHash } from "node:crypto";
import path from "node:path";
import { readBacklog, backlogIdentity, readBoundedBacklogFile } from "../extensions/learning-backlog";

const input: FailureObservationInput & { priorObservation?: FailureObservationInput; observationOutcome?: "successful" | "failed" } = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const backlog = readBacklog("/work/p-limit", "/home/node/agent");
const pending = backlog.pendingEntries.some(({ entry }) => isDeepStrictEqual(
  { ...entry, id: backlogIdentity(input.queued.scopeKey!, entry) }, input.queued));
if (backlog.error || backlog.malformed || !pending) {
  console.log(JSON.stringify({ ready: false, reason: "not-actual-pending-backlog" }));
} else {
  const source = await recentProjectLearningInput({ cwd: "/work/p-limit", agentDir: "/home/node/agent",
    sessionDir: path.dirname(input.queued.sessionFile), requestedSessionFile: input.queued.sessionFile });
  input.currentSession = source ? readBoundedBacklogFile(input.queued.sessionFile, 16 * 1024 * 1024) : "";
  const sameSource = source?.sourceDigest === createHash("sha256").update(input.currentSession).digest("hex");
  console.log(JSON.stringify(sameSource ? (input.priorObservation ? failureObservationExtensionReady(input.priorObservation, input) : input.observationOutcome === "successful" ? successfulFailureObservationReady(input) : failureObservationReady(input)) : { ready: false, reason: "unsafe-session-source" }));
}
