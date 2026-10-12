/** Read-only study proof. A failed feedback task is never promoted to success. */
import { createHash } from "node:crypto";
import { isDeepStrictEqual } from "node:util";
import { buildContextEntries, parseSessionEntries } from "@earendil-works/pi-coding-agent";
import { currentTaskSlice } from "../extensions/incremental-learning";
import { backlogIdentity, type BacklogEntry } from "../extensions/learning-backlog";

type Hashes = Record<string, string>;
export interface FailureObservationInput {
  originalSession: string;
  currentSession: string;
  verifierText: string;
  verifierPath: string;
  sourceBefore: Hashes;
  sourceAfter: Hashes;
  queued: BacklogEntry & { id: string };
  explicitBackfills: number;
}
const digest = (text: string) => createHash("sha256").update(text).digest("hex");
// Match verifier_observation's Python json.dumps(logs, sort_keys=True).
const pythonString = (text: string) => JSON.stringify(text).replace(/[^\x00-\x7f]/g,
  char => `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`);

export function failureObservationReady(input: FailureObservationInput): { ready: boolean; reason: string; sessionDigest?: string; backlogDigest?: string } {
  return observationReady(input, false);
}

/** Proves the successful full feedback read, never authorizes another backfill. */
export function successfulFailureObservationReady(input: FailureObservationInput): ReturnType<typeof failureObservationReady> {
  return observationReady(input, true);
}

function observationReady(input: FailureObservationInput, successful: boolean): ReturnType<typeof failureObservationReady> {
  const reject = (reason: string) => ({ ready: false, reason });
  try {
    if (input.explicitBackfills !== 0) return reject("backfill-already-consumed");
    if (!input.originalSession.endsWith("\n") || !input.currentSession.startsWith(input.originalSession)) return reject("original-session-changed");
    if (!Object.keys(input.sourceBefore).length || !isDeepStrictEqual(input.sourceBefore, input.sourceAfter)) return reject("source-changed");
    const observation = JSON.parse(input.verifierText);
    if (observation.kind !== "actual-project-verification" || observation.sessionDigest !== digest(input.originalSession)
      || !isDeepStrictEqual(observation.sourceHashes, input.sourceBefore) || observation.taskOutcome?.passed !== false) return reject("observation-binding");
    if (!observation.logs || Object.values(observation.logs).some(value => typeof value !== "string")) return reject("observation-logs");
    const logs = "{" + Object.keys(observation.logs).sort().map(key => `${pythonString(key)}: ${pythonString(observation.logs[key])}`).join(", ") + "}";
    if (digest(logs) !== observation.logsDigest) return reject("observation-logs");
    const all = input.currentSession.trimEnd().split("\n").map(line => JSON.parse(line));
    const rows = input.currentSession.slice(input.originalSession.length).trimEnd().split("\n").map(line => JSON.parse(line));
    const seen = new Set<string>();
    for (const row of all) {
      if (!row.id || seen.has(row.id)) return reject("session-entry-identity");
      seen.add(row.id);
    }
    const calls = rows.flatMap((row, index) => row.message?.role === "assistant"
      ? (row.message.content ?? []).filter((part: { type: string }) => part.type === "toolCall").map((part: object) => ({ ...part, index })) : []);
    const results = rows.flatMap((row, index) => row.message?.role === "toolResult" ? [{ ...row.message, index }] : []);
    const expectedCalls = successful ? 1 : 2;
    if (calls.length !== expectedCalls || results.length !== expectedCalls || new Set(calls.map(call => call.id)).size !== calls.length) return reject("unexpected-execution");
    const [read, denied] = calls;
    if (read.name !== "read" || !isDeepStrictEqual(read.arguments, { path: input.verifierPath })) return reject("verifier-read-boundary");
    const result = results.find(item => item.toolCallId === read.id);
    if (!result || result.toolName !== "read" || result.isError !== false || result.index <= read.index
      || !isDeepStrictEqual(result.content, [{ type: "text", text: input.verifierText }])) return reject("incomplete-verifier-read");
    const removed = rows.findIndex(row => row.customType === "continuous-study-tool-budget"
      && isDeepStrictEqual(row.data, { limit: 1, admitted: 1, outcome: "tools-removed" }));
    const stopped = rows.findIndex(row => row.customType === "continuous-study-tool-budget"
      && isDeepStrictEqual(row.data, { limit: 1, admitted: 1, outcome: "summary-tool-loop-stopped" }));
    if (successful) {
      const last = rows.at(-1)?.message;
      const users = rows.filter(row => row.message?.role === "user");
      if (users.length !== 1 || !isDeepStrictEqual(users[0].message.content, [{type: "text", text: "continue"}])
        || rows.indexOf(users[0]) >= read.index) return reject("unexpected-feedback-turn");
      if (rows.some(row => row.message?.role === "assistant" &&
        (["error", "aborted"].includes(row.message.stopReason) || row.message.errorMessage))) return reject("failed-feedback-summary");
      if (removed <= read.index || stopped !== -1 || last?.role !== "assistant" || last.stopReason !== "stop"
        || rows.filter(row => row.customType === "continuous-study-tool-budget").length !== 1) return reject("unproven-successful-summary");
    } else {
      const deniedResult = results.find(item => item.toolCallId === denied.id);
      if (removed <= read.index || denied.index <= result.index || denied.index <= removed || !deniedResult
        || deniedResult.index <= denied.index || deniedResult.toolName !== denied.name || deniedResult.isError !== true
        || !isDeepStrictEqual(deniedResult.content, [{ type: "text", text: `Tool ${denied.name} not found` }])
        || stopped <= deniedResult.index || rows.at(-1)?.message?.stopReason !== "error") return reject("unproven-tool-rejection");
    }
    if (rows.some(row => row.customType === "continuous-study-tool-budget"
      && !["tools-removed", "summary-tool-loop-stopped"].includes(row.data?.outcome))) return reject("repeated-boundary-violation");
    const parsed = parseSessionEntries(input.currentSession);
    const context = buildContextEntries(parsed.filter(entry => entry.type !== "session"));
    const queued = input.queued;
    if (!queued.scopeKey || backlogIdentity(queued.scopeKey, queued) !== queued.id
      || !Number.isSafeInteger(queued.from) || queued.from < 0 || queued.to !== context.length - 1) return reject("backlog-binding");
    const slice = currentTaskSlice(context.slice(queued.from, queued.to + 1));
    if (slice.omittedEntries || digest(JSON.stringify(slice)) !== queued.digest) return reject("backlog-digest");
    const ids = new Set(slice.entries.map(entry => (entry as { id?: string }).id));
    if (rows.some(row => row.message && !ids.has(row.id))) return reject("backlog-missing-feedback");
    const originalRows = input.originalSession.trimEnd().split("\n").map(line => JSON.parse(line));
    if (originalRows.some(row => ["user", "toolResult"].includes(row.message?.role) && !ids.has(row.id))) return reject("backlog-missing-original-evidence");
    return { ready: true, reason: successful ? "complete-successful-failure-observation" : "complete-observation-with-bounded-rejected-tool", sessionDigest: digest(input.currentSession), backlogDigest: queued.digest };
  } catch { return reject("malformed-evidence"); }
}

/** Preserve the one already-retained zero-tool diagnostic; never run it again. */
export function failureObservationExtensionReady(prior: FailureObservationInput, input: FailureObservationInput): ReturnType<typeof failureObservationReady> {
  const reject = (reason: string) => ({ ready: false, reason });
  const proof = failureObservationReady(prior);
  if (!proof.ready) return reject("invalid-prior-observation");
  try {
    if (input.explicitBackfills !== 0) return reject("backfill-already-consumed");
    if (input.originalSession !== prior.currentSession || !input.currentSession.startsWith(input.originalSession)) return reject("failed-prefix-changed");
    if (!isDeepStrictEqual(input.sourceBefore, prior.sourceBefore)
      || !isDeepStrictEqual(input.sourceAfter, input.sourceBefore)) return reject("source-changed");
    const rows = input.currentSession.slice(input.originalSession.length).trimEnd().split("\n").map(line => JSON.parse(line));
    const users = rows.filter(row => row.message?.role === "user");
    if (users.length !== 1 || !isDeepStrictEqual(users[0].message.content, [{ type: "text", text: "continue" }])) return reject("new-substantive-task");
    const calls = rows.flatMap((row, index) => row.message?.role === "assistant"
      ? (row.message.content ?? []).filter((part: { type: string }) => part.type === "toolCall").map((part: object) => ({ ...part, index })) : []);
    const results = rows.flatMap((row, index) => row.message?.role === "toolResult" ? [{ ...row.message, index }] : []);
    const removed = rows.findIndex(row => row.customType === "continuous-study-tool-budget"
      && isDeepStrictEqual(row.data, { limit: 0, admitted: 0, outcome: "tools-removed" }));
    const stopped = rows.findIndex(row => row.customType === "continuous-study-tool-budget"
      && isDeepStrictEqual(row.data, { limit: 0, admitted: 0, outcome: "summary-tool-loop-stopped" }));
    if (calls.length !== 1 || results.length !== 1 || removed < 0 || calls[0].index <= removed
      || results[0].index <= calls[0].index || results[0].toolCallId !== calls[0].id
      || results[0].toolName !== calls[0].name || results[0].isError !== true
      || !isDeepStrictEqual(results[0].content, [{ type: "text", text: `Tool ${calls[0].name} not found` }])
      || stopped <= results[0].index || rows.at(-1)?.message?.stopReason !== "error") return reject("unproven-tool-rejection");
    if (rows.filter(row => row.customType === "continuous-study-tool-budget").length !== 2) return reject("unexpected-budget-events");
    const all = input.currentSession.trimEnd().split("\n").map(line => JSON.parse(line));
    if (new Set(all.map(row => row.id)).size !== all.length || all.some(row => !row.id)) return reject("session-entry-identity");
    const parsed = parseSessionEntries(input.currentSession);
    const context = buildContextEntries(parsed.filter(entry => entry.type !== "session"));
    const queued = input.queued;
    if (!queued.scopeKey || backlogIdentity(queued.scopeKey, queued) !== queued.id || queued.from !== prior.queued.from
      || queued.to !== context.length - 1) return reject("backlog-binding");
    const slice = currentTaskSlice(context.slice(queued.from, queued.to + 1));
    if (slice.omittedEntries || digest(JSON.stringify(slice)) !== queued.digest) return reject("backlog-digest");
    const ids = new Set(slice.entries.map(entry => (entry as { id?: string }).id));
    if (all.some(row => ["user", "toolResult"].includes(row.message?.role) && !ids.has(row.id))
      || rows.some(row => row.message && !ids.has(row.id))) return reject("backlog-missing-feedback");
    return { ready: true, reason: "complete-observation-and-preserved-failed-diagnostic", sessionDigest: digest(input.currentSession), backlogDigest: queued.digest };
  } catch { return reject("malformed-evidence"); }
}
