import { safeDisplayText } from "@fradser/pi-kit";
import type { MonitorTerminalResult } from "./monitor.ts";

/** Model-facing text preserves each distinct value and references exact duplicates.
 * Structured results and expanded human details retain the original capture map. */
export function formatTerminalContent(description: string, result: MonitorTerminalResult, monitorId?: string, compact = false, directToolReply = false): string {
  // A direct Pi reply already carries toolCallId. For opted-in valid success,
  // duplicate label/ID/timing stays in structured data and expanded UI details.
  // Custom messages and results with diagnostics retain explicit metadata.
  const minimalSuccess = compact && directToolReply && result.status === "success"
    && !result.resultParseError && !result.capturesTruncated && !result.outputTruncated
    && !result.output?.length && !result.expected && !result.reason && !result.signal && !result.stoppedBy
    && (result.exitCode === undefined || result.exitCode === null || result.exitCode === 0);
  const lines = minimalSuccess ? [`status=${result.status}`] : [
    `Monitor: ${safeDisplayText(description)}`,
    ...(monitorId ? [`monitor_id=${safeDisplayText(monitorId)}`] : []),
    `status=${result.status}`,
    `elapsed=${formatElapsed(result.elapsedMs)}`,
  ];
  const payloadStart = lines.length;
  const firstFields = new Map<string, string>();
  if (result.result !== undefined) {
    const json = JSON.stringify(result.result);
    lines.push(`result=${safeDisplayText(escapeJsonControls(json))}`);
    firstFields.set(json, "json");
  }
  for (const [name, value] of Object.entries(result.captures ?? {})) {
    if (name === "json" || value === undefined) continue;
    const first = firstFields.get(value);
    if (first !== undefined) {
      lines.push(`capture_alias.${safeDisplayText(name)}=${safeDisplayText(first)}`);
    } else {
      lines.push(`capture.${safeDisplayText(name)}=${compactValue(value)}`);
      firstFields.set(value, name);
    }
  }
  // The matched line is the contract's own evidence. When a result or a capture
  // already carries it, the reference replaces the duplicate bytes.
  if (result.matched !== undefined && !minimalSuccess) {
    const first = firstFields.get(result.matched);
    if (first !== undefined) lines.push(`matched_alias=${safeDisplayText(first)}`);
    else {
      lines.push(`matched=${compactValue(result.matched)}`);
      firstFields.set(result.matched, "matched");
    }
  }
  if (compact) {
    const encoded = encodeRepeatedPayload(lines.slice(payloadStart).join("\n"));
    if (encoded) lines.splice(payloadStart, lines.length - payloadStart,
      "payload_encoding=rle-v1 (concat strings; [text,count] repeats text)",
      `payload_rle=${encoded}`);
  }
  if (result.resultParseError) lines.push(`result_parse_error=${compactValue(result.resultParseError)}`);
  if (result.capturesTruncated) lines.push("captures_truncated=true");
  if (result.completion !== undefined && !minimalSuccess) lines.push(`completion=${result.completion}`);
  // A run the contract ended never reached the command's own end. Without this
  // line a match-mode success reads exactly like a finished command.
  if (result.stoppedBy !== undefined) lines.push(`stopped_by=${result.stoppedBy}`);
  if (result.expected) lines.push(`expected=${compactValue(result.expected)}`);
  if (result.exitCode !== undefined && result.exitCode !== null) lines.push(`exit_code=${result.exitCode}`);
  if (result.signal) lines.push(`signal=${result.signal}`);
  if (result.reason) lines.push(`reason=${compactValue(result.reason)}`);
  if (result.timeoutMs !== undefined) lines.push(`timeout_ms=${result.timeoutMs}`);
  if (result.output?.length) lines.push(`output=${safeDisplayText(escapeJsonControls(JSON.stringify(result.output)))}`);
  if (result.outputTruncated) lines.push("output_truncated=true");
  const next = nextStep(result);
  if (next) lines.push(`next=${next}`);
  return lines.join("\n");
}

/** One instruction for the actor who receives a run that did not pass. A
 * passing run carries evidence instead, so it never pays for advice. */
function nextStep(result: MonitorTerminalResult): string | undefined {
  if (result.status === "success") return undefined;
  if (result.status === "stopped") return "the monitor was stopped; no further result arrives";
  if (result.status === "timeout") return "rerun with a larger timeout_ms, or finish the work faster";
  if (result.status === "result_missing") return "inspect output and expected, then rerun or broaden result_pattern";
  if (result.reason?.startsWith("matcher_")) return "the matcher stopped; retry with simpler patterns";
  if (result.reason === "invalid_json_result") return "fix the json group, or stop requesting parsed json";
  if (result.stoppedBy === "failure_match") return "inspect the captured failure output, then fix the cause";
  if (result.exitCode !== undefined && result.exitCode !== null && result.exitCode !== 0) {
    return "inspect output, then fix the command";
  }
  return "inspect output and reason, then rerun or report the blocker";
}

// JSON.stringify leaves C1 and Unicode line separators literal. Escape them
// before display sanitization so valid JSON data cannot become terminal controls
// or be removed from the model-facing payload.
function escapeJsonControls(json: string): string {
  return json.replace(/[\u007f-\u009f\u2028\u2029]/g, (character) =>
    `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`);
}

/** Encode only materially smaller payloads. Counts refer to exact JS string
 * repetition; literal segments and repeat units cannot collide with user data. */
function encodeRepeatedPayload(value: string): string | undefined {
  if (Buffer.byteLength(value) < 1024) return;
  const parts: Array<string | [string, number]> = [];
  let literalStart = 0;
  let offset = 0;
  while (offset < value.length) {
    let unit = "";
    let count = 0;
    for (let width = 1; width <= 8 && offset + width <= value.length; width++) {
      const candidate = value.slice(offset, offset + width);
      let repetitions = 1;
      while (value.startsWith(candidate, offset + repetitions * width)) repetitions++;
      if (repetitions >= 8 && repetitions * width > unit.length * count) {
        unit = candidate;
        count = repetitions;
      }
    }
    if (unit.length * count < 64) { offset++; continue; }
    if (literalStart < offset) parts.push(value.slice(literalStart, offset));
    parts.push([unit, count]);
    offset += unit.length * count;
    literalStart = offset;
  }
  if (literalStart < value.length) parts.push(value.slice(literalStart));
  // Keep the encoded JSON on one logical line for text consumers as well as
  // newline splitting; JSON.parse restores both Unicode line separators.
  const encoded = JSON.stringify(parts).replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
  const originalBytes = Buffer.byteLength(value);
  const encodedBytes = Buffer.byteLength(encoded) + 96;
  return originalBytes - encodedBytes >= 512 && encodedBytes < originalBytes * 0.75 ? encoded : undefined;
}

function formatElapsed(milliseconds: number): string {
  if (milliseconds < 1000) return `${Math.round(milliseconds)}ms`;
  return `${(milliseconds / 1000).toFixed(1)}s`;
}

function compactValue(value: string): string {
  return safeDisplayText(value).replace(/[\r\n]+/g, "\\n");
}
