import { execFile } from "node:child_process";
import { basename } from "node:path";

/** A Pi process identity from one bounded, read-only OS process snapshot. */
export interface PiProcess {
  pid: number;
  startedAt: number;
}

const MAX_PROCESS_BYTES = 1024 * 1024;
const PROCESS_TIMEOUT_MS = 2000;

function piExecutable(value: string): boolean {
  return /^pi(?:-rpc)?(?:\.[cm]?js)?$/i.test(basename(value));
}

function isPiInvocation(comm: string, args: string): boolean {
  if (piExecutable(comm)) return true;
  const tokens = args.trim().split(/\s+/);
  const executable = tokens[0] ?? "";
  if (piExecutable(executable)) return true;
  // Inspect the executable/script positions only, never arbitrary arguments
  // (a grep or shell command mentioning pi is not evidence of a Pi process).
  if (!["node", "bun", "deno"].includes(basename(executable))) return false;
  const script = tokens[1] ?? "";
  return piExecutable(script)
    || /[/\\]@earendil-works[/\\]pi-coding-agent[/\\]dist[/\\](?:bundle[/\\])?(?:cli|rpc-entry)\.js$/.test(script);
}

function elapsedSeconds(value: string): number | null {
  if (/^\d+$/.test(value)) return Number(value);
  const match = value.match(/^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$/);
  if (!match) return null;
  return Number(match[1] ?? 0) * 86400 + Number(match[2] ?? 0) * 3600 + Number(match[3]) * 60 + Number(match[4]);
}

export function parsePiProcesses(output: string, now: number): PiProcess[] {
  const processes: PiProcess[] = [];
  for (const line of output.split(/\r?\n/)) {
    const match = line.trim().match(/^(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s*(.*)$/);
    if (!match || /^[ZX]/i.test(match[3]!) || !isPiInvocation(match[4]!, match[5]!)) continue;
    const pid = Number(match[1]);
    const elapsed = elapsedSeconds(match[2]!);
    if (!Number.isSafeInteger(pid) || pid <= 0 || elapsed === null) continue;
    processes.push({ pid, startedAt: Math.max(0, now - elapsed * 1000) });
  }
  return processes;
}

/** Never log command lines; discard the bounded process table after parsing. */
export function listPiProcesses(): Promise<PiProcess[]> {
  const now = Date.now();
  const args = process.platform === "darwin"
    ? ["-axo", "pid=,etime=,stat=,comm=,args="]
    : ["-eo", "pid=,etimes=,stat=,comm=,args="];
  return new Promise((resolve) => {
    execFile("ps", args, { encoding: "utf8", maxBuffer: MAX_PROCESS_BYTES, timeout: PROCESS_TIMEOUT_MS }, (error, stdout) => {
      resolve(error ? [] : parsePiProcesses(stdout, now));
    });
  });
}
