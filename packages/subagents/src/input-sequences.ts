/** Bounded next-input reservations. Exact ownership remains with the lifecycle runtime. */
import { randomUUID } from "node:crypto";
import { getAgent, observeAgentRoster, updateAgent } from "./roster.ts";
import { parseExactSessionRoute } from "./session-route.ts";
import { boundedFinalDiagnostic, type SessionNoticeSender } from "./session-result.ts";

export const MAX_PENDING_INPUTS = 8;
export const MAX_PENDING_INPUT_BYTES = 256 * 1024;
export type InputDispatchResult = { ok: boolean; uncertain?: boolean; error?: string };
type InputRecord = { id: string; bytes: number; dispatch: () => Promise<InputDispatchResult>;
  authorize?: () => { ok: boolean; error?: string } };
type Sequence = {
  session: string; sender?: SessionNoticeSender; active?: string; settled: boolean;
  confirmed: boolean;
  confirming: boolean; stopped: boolean; queue: InputRecord[]; bytes: number;
};
const KEY = Symbol.for("fradser.pi-subagents.input-sequences");
const carrier = globalThis as { [KEY]?: Map<string, Sequence> };
const sequences = carrier[KEY] ?? (carrier[KEY] = new Map());

function current(sequence: Sequence) {
  const parsed = parseExactSessionRoute(sequence.session);
  const agent = parsed ? getAgent(parsed.name) : undefined;
  return agent?.spawnId === parsed?.spawnId ? agent : undefined;
}
function recordDiagnostic(sequence: Sequence, error: unknown): void {
  const agent = current(sequence);
  if (agent) updateAgent(agent.name, { error: boundedFinalDiagnostic(error instanceof Error ? error.message : String(error)) });
}
function cancelledNotice(sequence: Sequence, id: string, reason: string): void {
  const agent = current(sequence);
  const parsed = parseExactSessionRoute(sequence.session)!;
  try {
    sequence.sender?.({ kind: "input-cancelled", name: agent?.label ?? parsed.name,
      session: sequence.session, inputId: id, reason, deliveredAt: Date.now() });
  } catch (error) { recordDiagnostic(sequence, error); }
}

/** Called while a new incarnation is reserved, before native startup can settle. */
export function bindInputSequence(session: string, inputId: string, sender?: SessionNoticeSender): void {
  const sequence: Sequence = { session, sender, active: inputId, settled: false, confirmed: false,
    confirming: true, stopped: false, queue: [], bytes: 0 };
  sequences.set(session, sequence);
  const agent = current(sequence);
  if (agent) updateAgent(agent.name, { inputId, sequenceEnded: false });
}
export function currentInputId(session: string): string | undefined { return sequences.get(session)?.active; }
export function hasActiveInput(session: string): boolean {
  const sequence = sequences.get(session);
  return Boolean(sequence && sequence.confirmed && !sequence.stopped && !sequence.settled && sequence.active);
}
export function pendingInputCount(session: string): number { return sequences.get(session)?.queue.length ?? 0; }

/** Settlement never clears an outstanding ACK. Both edges are needed before another dispatch. */
export function settleInputSequence(session: string): void {
  const sequence = sequences.get(session);
  if (!sequence || sequence.stopped) return;
  sequence.settled = true;
  schedule(sequence);
}
export function confirmInputSequence(session: string): void {
  const sequence = sequences.get(session);
  if (!sequence) return;
  sequence.confirming = false;
  sequence.confirmed = true;
  schedule(sequence);
}
export function endInputSequence(session: string, reason: string): void {
  const sequence = sequences.get(session);
  if (!sequence || sequence.stopped) return;
  sequence.stopped = true;
  const pending = sequence.queue.splice(0);
  sequence.bytes = 0;
  sequences.delete(session);
  for (const record of pending) cancelledNotice(sequence, record.id, reason);
}

function schedule(sequence: Sequence): void {
  queueMicrotask(() => { void drain(sequence).catch(error => recordDiagnostic(sequence, error)); });
}
async function drain(sequence: Sequence): Promise<InputDispatchResult | undefined> {
  if (sequences.get(sequence.session) !== sequence || sequence.stopped || sequence.confirming || !sequence.settled) return;
  const agent = current(sequence);
  if (!agent || agent.status === "stopped" || agent.leaderRequestedEnd) {
    endInputSequence(sequence.session, "The exact child is closed or stopping; queued input did not start.");
    return;
  }
  if (agent.status !== "idle") return;
  const record = sequence.queue[0];
  if (!record) return;
  const policy = record.authorize?.();
  if (sequences.get(sequence.session) !== sequence || sequence.stopped) return;
  // Report draining can synchronously change settlement, ownership, or state.
  // Never consume a record based only on the snapshot from before that callback.
  const ready = current(sequence);
  if (!ready || ready.leaderRequestedEnd || ready.status === "stopped") {
    endInputSequence(sequence.session, "The exact child changed during input preparation; queued input did not start.");
    return { ok: false, error: "The exact child changed during input preparation." };
  }
  if (ready.status !== "idle" || sequence.confirming || !sequence.settled) return;
  sequence.queue.shift();
  sequence.bytes -= record.bytes;
  if (policy && !policy.ok) {
    const result = { ok: false, error: policy.error ?? "Input reservation policy prevents dispatch." };
    cancelledNotice(sequence, record.id, result.error);
    schedule(sequence);
    return result;
  }
  sequence.active = record.id;
  sequence.settled = false;
  sequence.confirming = true;
  sequence.confirmed = false;
  updateAgent(ready.name, { inputId: record.id, sequenceEnded: false });
  let result: InputDispatchResult;
  try { result = await record.dispatch(); }
  catch (error) { result = { ok: false, uncertain: true, error: error instanceof Error ? error.message : String(error) }; }
  if (sequences.get(sequence.session) !== sequence) {
    return { ok: false, uncertain: true, error: "The exact child stopped or was replaced before input confirmation." };
  }
  sequence.confirming = false;
  sequence.confirmed = result.ok || sequence.settled;
  if (!result.ok && !sequence.settled) {
    if (result.uncertain) {
      // The native sequence can still settle. Never retry or restore guessed idle state.
      if (result.error) recordDiagnostic(sequence, result.error);
      return result;
    }
    cancelledNotice(sequence, record.id, result.error ?? "The queued input was rejected before a sequence started.");
    sequence.settled = true;
  }
  schedule(sequence);
  return result;
}

export function reserveNextInput(session: string, prompt: string, dispatch: () => Promise<InputDispatchResult>,
  authorize?: () => { ok: boolean; error?: string }):
  | { ok: true; inputId: string; queued: boolean; confirmation?: Promise<InputDispatchResult | undefined> }
  | { ok: false; code: "queue-full" | "no-input-owner"; error: string } {
  const sequence = sequences.get(session);
  if (!sequence || sequence.stopped) return { ok: false, code: "no-input-owner", error: "This exact child has no active input owner." };
  const bytes = Buffer.byteLength(prompt, "utf8");
  if (sequence.queue.length >= MAX_PENDING_INPUTS || sequence.bytes + bytes > MAX_PENDING_INPUT_BYTES) {
    return { ok: false, code: "queue-full", error: "Next input exceeds eight pending records or the 256 KiB pending body limit." };
  }
  const inputId = randomUUID();
  const agent = current(sequence);
  const queued = sequence.confirming || !sequence.settled || agent?.status !== "idle" || sequence.queue.length > 0;
  sequence.queue.push({ id: inputId, bytes, dispatch, authorize });
  sequence.bytes += bytes;
  const confirmation = queued ? undefined : drain(sequence);
  if (queued) schedule(sequence);
  return { ok: true, inputId, queued, ...(confirmation ? { confirmation } : {}) };
}

// State notifications cover hosted execution and explicit shutdown through either interface.
observeAgentRoster(() => {
  for (const sequence of sequences.values()) {
    const agent = current(sequence);
    if (!agent || agent.status === "stopped" || agent.leaderRequestedEnd) {
      endInputSequence(sequence.session, "The exact child is closed or stopping; queued input did not start.");
    } else if (!agent.standalone && agent.sequenceEnded === true && agent.status === "idle") {
      settleInputSequence(sequence.session);
    }
  }
});
