/** Bounded execution observations from Pi's active branch, not executor arguments. */
import type { ContextEditEntry, SessionEntry } from "@earendil-works/pi-coding-agent";
import type { GoalRecord } from "./record.ts";

export interface GoalObservation {
  entryId: string;
  at: string;
  source: "tool" | "shell" | "monitor" | "review";
  label: string;
  input?: string;
  inputEntryId?: string;
  outcome: "success" | "failure" | "reported";
  output: string;
  truncated: boolean;
}

export interface GoalEvidence {
  threadId: string;
  goalId: string;
  since: string;
  observations: GoalObservation[];
  omitted: number;
}

/** Goal tools report the goal, not work on it, so they are never evidence. `research_goal`
 * is retired and stays listed: a legacy transcript's findings must not become evidence for a
 * goal that never owned them. */
const EXCLUDED_TOOLS = new Set(["create_goal", "get_goal", "update_goal", "research_goal"]);
const MAX_OBSERVATIONS = 16;
const MAX_OUTPUT_CHARS = 3_000;
const MAX_INPUT_CHARS = 1_000;
const MAX_LABEL_CHARS = 200;

function text(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.flatMap(block => {
    if (typeof block !== "object" || block === null) return [];
    return block.type === "text" && typeof block.text === "string" ? [block.text] : [];
  }).join("\n");
}

function object(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown> : undefined;
}

/** Redact common assignments and JSON credential fields; this is not generic secret detection. */
function redact(value: string): string {
  return value
    .replace(/\b(Bearer)\s+[^\s"']+/gi, "$1 <REDACTED>")
    .replace(/(\b[A-Z_]*(?:API_KEY|ACCESS_TOKEN|AUTH_TOKEN|SECRET|PASSWORD)["']?\s*[:=]\s*)(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;}\]]+)/gi, "$1<REDACTED>")
    .replace(/\bsk-[A-Za-z0-9_-]{16,}\b/g, "<REDACTED>");
}

function observation(args: Omit<GoalObservation, "truncated">): GoalObservation {
  const output = redact(args.output);
  const input = args.input === undefined ? undefined : redact(args.input);
  const label = redact(args.label);
  return {
    ...args,
    label: label.slice(0, MAX_LABEL_CHARS),
    ...(input === undefined ? {} : { input: input.slice(0, MAX_INPUT_CHARS) }),
    output: output.slice(0, MAX_OUTPUT_CHARS),
    truncated: label.length > MAX_LABEL_CHARS || output.length > MAX_OUTPUT_CHARS || (input?.length ?? 0) > MAX_INPUT_CHARS,
  };
}

function monitorOutcome(status: unknown): GoalObservation["outcome"] {
  if (status === "success") return "success";
  if (status === "failure" || status === "timeout" || status === "result_missing") return "failure";
  return "reported";
}

/** Extract only the known terminal payload; do not stringify arbitrary extension details. */
function monitorOutput(content: unknown, result: Record<string, unknown> | undefined, edited: boolean): string {
  if (edited) return text(content);
  return [
    text(content),
    typeof result?.exitCode === "number" ? `Exit code: ${result.exitCode}` : "",
    typeof result?.matched === "string" ? `Matched output: ${result.matched}` : "",
    Array.isArray(result?.output) ? result.output.filter(line => typeof line === "string").join("\n") : "",
    result?.outputTruncated === true ? "Terminal output was truncated." : "",
  ].filter(Boolean).join("\n");
}

/** Honor edits of prior model-visible entries without changing execution metadata. */
function evidenceEdits(entries: readonly SessionEntry[]): Map<string, ContextEditEntry["replacement"]> {
  const prior = new Map<string, SessionEntry>();
  const edits = new Map<string, ContextEditEntry["replacement"]>();
  for (const entry of entries) {
    if (entry.type === "context_edit") {
      const target = prior.get(entry.targetId);
      if (target?.type === "custom_message" || (target?.type === "message" &&
          (target.message.role === "user" || target.message.role === "assistant" || target.message.role === "toolResult"))) {
        edits.set(entry.targetId, entry.replacement);
      }
    }
    prior.set(entry.id, entry);
  }
  return edits;
}

interface ExecutedCall {
  name: string;
  input: string;
  inputEntryId: string;
  at: number;
}
interface MonitorLaunch extends ExecutedCall {
  monitorId?: string;
  description?: string;
}

/** Source/outcome metadata is observed; output remains untrusted data, never instruction. */
export function collectGoalEvidence(entries: readonly SessionEntry[], goal: GoalRecord, threadId: string): GoalEvidence {
  const since = goal.evidenceSince ?? goal.createdAt;
  const sinceTime = Date.parse(since);
  const observations: GoalObservation[] = [];
  const calls = new Map<string, ExecutedCall>();
  const launches: MonitorLaunch[] = [];
  const monitorObservations = new Map<string, GoalObservation>();
  const edits = evidenceEdits(entries);

  function addMonitor(args: Omit<GoalObservation, "truncated">, details: Record<string, unknown> | undefined): void {
    const item = observation(args);
    const candidate = typeof details?.monitorId === "string" && details.monitorId ? details.monitorId : undefined;
    // Legacy counters can name different processes after restart; never merge them.
    const id = candidate && !/^monitor_\d+$/.test(candidate) ? candidate : undefined;
    const existing = id === undefined ? undefined : monitorObservations.get(id);
    if (existing !== undefined) observations.splice(observations.indexOf(existing), 1);
    if (id !== undefined) monitorObservations.set(id, item);
    observations.push(item);
  }

  for (const entry of entries) {
    const replacement = edits.get(entry.id);
    if (replacement === null) continue;
    const projectedContent = replacement?.content;
    const edited = edits.has(entry.id);
    const at = Date.parse(entry.timestamp);
    if (entry.type === "message" && entry.message.role === "assistant") {
      // Display-edited calls cannot establish what command really executed.
      if (edited) continue;
      for (const block of entry.message.content) {
        if (block.type === "toolCall") calls.set(block.id, {
          name: block.name, input: JSON.stringify(block.arguments), inputEntryId: entry.id, at,
        });
      }
    }
    if (entry.type === "message" && entry.message.role === "toolResult" && entry.message.toolName === "monitor_start") {
      const message = entry.message;
      const call = calls.get(message.toolCallId);
      const details = object(message.details);
      if (call?.name === "monitor_start" && !message.isError) {
        launches.push({ ...call,
          monitorId: typeof details?.monitorId === "string" ? details.monitorId : undefined,
          description: typeof details?.description === "string" ? details.description : undefined,
        });
      }
    }
    if (!Number.isFinite(sinceTime) || !Number.isFinite(at) || at < sinceTime) continue;
    if (entry.type === "message") {
      const message = entry.message;
      if (message.role === "toolResult" && !EXCLUDED_TOOLS.has(message.toolName)) {
        const call = calls.get(message.toolCallId);
        if (!call || call.name !== message.toolName || !Number.isFinite(call.at) || call.at < sinceTime) continue;
        const details = object(message.details);
        if (message.toolName === "monitor_start") {
          const result = object(details?.result);
          if (!message.isError && (!result || result.status === "running")) continue;
          addMonitor({ entryId: entry.id, at: entry.timestamp, source: "monitor",
            label: typeof details?.description === "string" ? details.description : "monitor",
            input: call.input, inputEntryId: call.inputEntryId,
            outcome: message.isError ? "failure" : monitorOutcome(result?.status),
            output: monitorOutput(projectedContent ?? message.content, result, edited) }, details);
        } else {
          observations.push(observation({ entryId: entry.id, at: entry.timestamp, source: "tool", label: message.toolName,
            input: call.input, inputEntryId: call.inputEntryId,
            outcome: message.isError ? "failure" : message.toolName === "monitor_stop" ? "reported" : "success",
            output: text(projectedContent ?? message.content) }));
        }
      } else if (message.role === "bashExecution" && !message.cancelled) {
        observations.push(observation({ entryId: entry.id, at: entry.timestamp, source: "shell", label: "user shell",
          input: message.command, outcome: message.exitCode === 0 ? "success" : "failure", output: message.output }));
      }
    } else if (entry.type === "custom_message") {
      const details = object(entry.details);
      if (entry.customType === "monitor-result") {
        const result = object(details?.result);
        const candidates = launches.filter(launch => typeof details?.monitorId === "string"
          ? launch.monitorId === details.monitorId
          : typeof details?.description === "string" && launch.description === details.description);
        const launch = candidates.length === 1 ? candidates[0] : undefined;
        if (launch && (!Number.isFinite(launch.at) || launch.at < sinceTime)) continue;
        const outcome = monitorOutcome(result?.status);
        addMonitor({ entryId: entry.id, at: entry.timestamp, source: "monitor",
          label: typeof details?.description === "string" ? details.description : "monitor",
          ...(launch ? { input: launch.input, inputEntryId: launch.inputEntryId } : {}),
          outcome: outcome === "success" && !launch ? "reported" : outcome,
          output: monitorOutput(projectedContent ?? entry.content, result, edited) }, details);
      } else if (entry.customType === "agent-teams-report" && details?.origin === "agent" &&
          details.status === "completed" && details.finished === true &&
          typeof details.agent === "string" && typeof details.spawnId === "string") {
        observations.push(observation({ entryId: entry.id, at: entry.timestamp, source: "review",
          label: `${details.agent} ${details.spawnId}`, outcome: "reported", output: text(projectedContent ?? entry.content) }));
      } else if (entry.customType === "subagents-session-result" && details?.kind === "result" &&
          typeof details.session === "string" && typeof details.turn === "number") {
        observations.push(observation({ entryId: entry.id, at: entry.timestamp, source: "review",
          label: `${details.session} turn ${details.turn}`, outcome: "reported", output: text(projectedContent ?? entry.content) }));
      }
    }
  }
  return { threadId, goalId: goal.id, since, observations: observations.slice(-MAX_OBSERVATIONS), omitted: Math.max(0, observations.length - MAX_OBSERVATIONS) };
}
