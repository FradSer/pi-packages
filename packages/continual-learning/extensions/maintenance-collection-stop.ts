import fs from "node:fs/promises";
import path from "node:path";
import {createHash} from "node:crypto";
import type {ExtensionAPI, TurnEndEvent} from "@earendil-works/pi-coding-agent";
import {registerPlannerRead, type PlannerReadObservation, type PlannerReadScope} from "./planner-read-scope";
import {writeFileAtomic} from "./consolidation-run";

const digest = (text: string) => createHash("sha256").update(text).digest("hex");
const jsonDigest = (value: unknown) => digest(JSON.stringify(value));
const FAILED_WORKER = "Pi worker model failed before successful completion.";
const CANCELLED_WORKER = "Pi worker model reply was cancelled.";
// Stop at a complete turn before the hard cap; a later parallel batch can
// otherwise overshoot and abort an already admitted in-flight read.
const stopThreshold = (maximum: number) => maximum > 2 ? maximum - 2 : maximum;
// Exact abort values emitted by Pi 1.0, native AbortError and the OpenAI SDK.
const isStandardAbort = (message: unknown) => typeof message === "string" && ["This operation was aborted", "The operation was aborted", "The operation was aborted.",
  "Request was aborted", "Request was aborted."].includes(message);
type DeliveredReadTurn = Pick<TurnEndEvent, "message" | "toolResults">;
function record(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

/** Bind completed tool calls and results, never the model's final summary. */
function deliveredReads(turns: readonly DeliveredReadTurn[], observations: readonly PlannerReadObservation[], scope: PlannerReadScope, maximum: number): boolean {
  if (observations.length !== maximum || observations.some(read => read.error !== undefined && read.error !== "Scoped source path missing"
      || !read.toolCallId || read.error === undefined && typeof read.result !== "string")
    || new Set(observations.map(read => read.toolCallId)).size !== maximum) return false;
  const reads = new Map(observations.map(read => [read.toolCallId!, read]));
  const delivered = new Set<string>();
  for (const turn of turns) {
    const message = record(turn.message);
    if (message?.role !== "assistant" || !Array.isArray(message.content) || !Array.isArray(turn.toolResults)) return false;
    const calls = message.content.map(record).filter(item => item?.type === "toolCall");
    if (calls.length !== turn.toolResults.length) return false;
    for (const result of turn.toolResults) {
      const read = reads.get(result.toolCallId);
      const matches = calls.filter(call => call?.id === result.toolCallId);
      const call = matches[0];
      const args = record(call?.arguments);
      if (!read || delivered.has(result.toolCallId) || matches.length !== 1 || call?.name !== "learning_read"
        || typeof args?.path !== "string" || path.resolve(read.path) !== path.resolve(scope.cwd, args.path)
        || (args.offset ?? 1) !== read.offset || (args.limit ?? 200) !== read.limit
        || result.toolName !== "learning_read" || Boolean(result.isError) !== (read.error === "Scoped source path missing") || result.content.length !== 1
        || result.content[0].type !== "text" || result.content[0].text !== (read.error ?? read.result)) return false;
      delivered.add(result.toolCallId);
    }
  }
  return delivered.size === maximum;
}

/** Trusted extension only. Its artifacts lie outside the worker's read scope. */
export function registerMaintenanceCollector(pi: ExtensionAPI, scope: PlannerReadScope, directory: string, nonce: string,
  observe: (read: PlannerReadObservation) => Promise<void>, maximum = 18): void {
  const observations: PlannerReadObservation[] = [];
  const turns: DeliveredReadTurn[] = [];
  let pending = 0;
  let tainted = false;
  let stopped = false;
  registerPlannerRead(pi, scope, async read => {
    pending++;
    observations.push(read);
    if (read.error !== undefined && read.error !== "Scoped source path missing" || observations.length > maximum) tainted = true;
    try { await observe(read); }
    catch (error) { tainted = true; throw error; }
    finally { pending--; }
  }, maximum);
  pi.on("message_end", async (event, ctx) => {
    if (!stopped || event.message.role !== "assistant") return;
    const message = event.message;
    // Parent-controlled categories only: never retain arbitrary provider errors.
    await writeFileAtomic(path.join(directory, "collection-terminal-diagnostic.json"), JSON.stringify({version: 1,
      signalAborted: ctx.signal?.aborted === true,
      stopReason: message.stopReason === "error" || message.stopReason === "aborted" ? message.stopReason : "other",
      standardAbort: isStandardAbort(message.errorMessage), emptyContent: message.content.length === 0,
      zeroUsage: [message.usage.input, message.usage.output, message.usage.cacheRead, message.usage.cacheWrite, message.usage.totalTokens].every(value => value === 0)}), 0o600);
    if (!ctx.signal?.aborted) return;
    if (message.stopReason !== "aborted" && !(message.stopReason === "error" && isStandardAbort(message.errorMessage))) return;
    await writeFileAtomic(path.join(directory, "collection-terminal.json"), JSON.stringify({version: 1, nonce,
      scopeDigest: jsonDigest(scope), prefixDigest: jsonDigest(turns), signalAborted: true, message}), 0o600);
  });
  pi.on("turn_end", async (event, ctx) => {
    if (stopped || ctx.signal?.aborted) return;
    // Native turn context contains cumulative history. Binding it repeatedly
    // exceeds the proof bound even when every required delivery fits. Keep all
    // current calls/results exactly; the verifier never consumes SDK context.
    turns.push(structuredClone({message: event.message, toolResults: event.toolResults}));
    if (pending || !tainted && observations.length < stopThreshold(maximum)) return;
    if (tainted || !deliveredReads(turns, observations, scope, observations.length)) {
      await writeFileAtomic(path.join(directory, "collection-refused.json"), JSON.stringify({version: 1, reason: "incomplete-or-invalid-read-prefix"}), 0o600);
      stopped = true;
      ctx.abort();
      return;
    }
    const prefix = JSON.stringify(turns);
    await writeFileAtomic(path.join(directory, "collection-prefix.json"), prefix, 0o600);
    if (ctx.signal?.aborted) return;
    await writeFileAtomic(path.join(directory, "collection-stop.json"), JSON.stringify({version: 1,
      nonce, scopeDigest: jsonDigest(scope), observationsDigest: jsonDigest(observations),
      prefixDigest: digest(prefix), observationsFileDigest: digest(await fs.readFile(path.join(directory, "observations.jsonl"), "utf8")), maximum, readCount: observations.length, reason: "complete-read-budget-prefix"}), 0o600);
    // This is deliberately a cancelled worker, not a successful audit summary.
    // The parent independently verifies the complete observed prefix below.
    stopped = true;
    ctx.abort();
  });
}

export async function verifyMaintenanceCollectionProof(directory: string, nonce: string, scope: PlannerReadScope,
  observations: readonly PlannerReadObservation[], worker: {exitCode: number; cancelled?: boolean; stderr: string},
  signal?: AbortSignal, maximum = 18): Promise<boolean> {
  if (signal?.aborted || worker.exitCode !== 1 || !(worker.cancelled === true && worker.stderr === CANCELLED_WORKER
    || worker.cancelled !== true && worker.stderr === FAILED_WORKER)) return false;
  try {
    const markerFile = path.join(directory, "collection-stop.json");
    const prefixFile = path.join(directory, "collection-prefix.json");
    if ((await fs.lstat(markerFile)).isSymbolicLink() || (await fs.lstat(prefixFile)).isSymbolicLink()) return false;
    const marker = record(JSON.parse(await fs.readFile(markerFile, "utf8")));
    const prefix = await fs.readFile(prefixFile, "utf8");
    if (Buffer.byteLength(prefix) > 2 * 1024 * 1024 || marker?.version !== 1 || marker.nonce !== nonce
      || marker.reason !== "complete-read-budget-prefix" || marker.maximum !== maximum
      || marker.readCount !== observations.length || observations.length < stopThreshold(maximum) || observations.length > maximum || marker.scopeDigest !== jsonDigest(scope)
      || marker.observationsDigest !== jsonDigest(observations) || marker.prefixDigest !== digest(prefix)
      || marker.observationsFileDigest !== digest(await fs.readFile(path.join(directory, "observations.jsonl"), "utf8"))) return false;
    const terminalFile = path.join(directory, "collection-terminal.json");
    if ((await fs.lstat(terminalFile)).isSymbolicLink()) return false;
    const terminal = record(JSON.parse(await fs.readFile(terminalFile, "utf8")));
    const message = record(terminal?.message);
    const usage = record(message?.usage);
    if (terminal?.version !== 1 || terminal.nonce !== nonce || terminal.scopeDigest !== jsonDigest(scope)
      || terminal.prefixDigest !== marker.prefixDigest || terminal.signalAborted !== true
      || message?.role !== "assistant" || !Array.isArray(message.content) || message.content.length !== 0
      || !usage || ["input", "output", "cacheRead", "cacheWrite", "totalTokens"].some(key => usage[key] !== 0)
      || (worker.cancelled ? message.stopReason !== "aborted"
        : message.stopReason !== "error" || !isStandardAbort(message.errorMessage))) return false;
    const turns: unknown = JSON.parse(prefix);
    return !signal?.aborted && Array.isArray(turns) && deliveredReads(turns, observations, scope, observations.length);
  } catch { return false; }
}
