import { execFile } from "node:child_process";

/** A Pi process identity from one bounded, read-only OS process snapshot. */
export interface PiProcess {
  pid: number;
  startedAt: number;
}

const MAX_PROCESS_BYTES = 1024 * 1024;
const PROCESS_TIMEOUT_MS = 2000;
const WINDOWS_PROCESS_SCRIPT = [
  '$ErrorActionPreference = "Stop";',
  '[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false);',
  'Get-CimInstance Win32_Process |',
  'Select-Object ProcessId, Name, CommandLine,',
  "@{n='startedAtMs'; e={ [int64]([DateTimeOffset]$_.CreationDate).ToUnixTimeMilliseconds() }} |",
  'ConvertTo-Json -Compress -Depth 3',
].join(" ");

function executableName(value: string): string {
  return (value.split(/[/\\]/).at(-1) ?? "").replace(/\.exe$/i, "");
}

function piExecutable(value: string): boolean {
  return /^pi(?:-rpc)?(?:\.[cm]?js)?$/i.test(executableName(value));
}

function isPiInvocation(comm: string, args: string, suppliedTokens?: string[]): boolean {
  if (piExecutable(comm)) return true;
  const tokens = suppliedTokens ?? args.trim().split(/\s+/);
  const executable = tokens[0] ?? "";
  if (piExecutable(executable)) return true;
  // Inspect the executable/script positions only, never arbitrary arguments
  // (a grep or shell command mentioning pi is not evidence of a Pi process).
  if (!["node", "bun", "deno"].includes(executableName(executable).toLowerCase())) return false;
  const script = tokens[1] ?? "";
  return piExecutable(script)
    || /[/\\]@earendil-works[/\\]pi-coding-agent[/\\]dist[/\\](?:bundle[/\\])?(?:cli|rpc-entry)\.js$/.test(script);
}

/** Windows quoting keeps paths with spaces together; backslashes escape quotes only. */
function windowsCommandTokens(value: string): string[] {
  const tokens: string[] = [];
  let token = "", quoted = false, started = false;
  for (let index = 0; index < value.length;) {
    const character = value[index]!;
    if (character === "\\") {
      let count = 0;
      while (value[index] === "\\") { count += 1; index += 1; }
      if (value[index] === '"') {
        token += "\\".repeat(Math.floor(count / 2));
        if (count % 2) token += '"';
        else quoted = !quoted;
        index += 1;
      } else token += "\\".repeat(count);
      started = true;
      continue;
    }
    if (character === '"') { quoted = !quoted; started = true; index += 1; continue; }
    if (!quoted && /[ \t]/.test(character)) {
      if (started) tokens.push(token);
      token = ""; started = false; index += 1; continue;
    }
    token += character; started = true; index += 1;
  }
  if (quoted) return [];
  if (started) tokens.push(token);
  return tokens;
}

/** Read only the projected WMI identity, never disclose command lines. */
export function parseWindowsPiProcesses(output: string, now: number): PiProcess[] {
  if (Buffer.byteLength(output) > MAX_PROCESS_BYTES) return [];
  let decoded: unknown;
  try { decoded = JSON.parse(output.replace(/^\uFEFF/, "")); } catch { return []; }
  const processes: PiProcess[] = [];
  for (const item of Array.isArray(decoded) ? decoded : [decoded]) {
    if (!item || typeof item !== "object" || Array.isArray(item)) continue;
    const row = item as Record<string, unknown>;
    const pid = row.ProcessId, startedAt = row.startedAtMs;
    if (typeof pid !== "number" || !Number.isSafeInteger(pid) || pid <= 0 || pid > 0x7fffffff
      || typeof startedAt !== "number" || !Number.isSafeInteger(startedAt) || startedAt <= 0 || startedAt > now) continue;
    const command = typeof row.CommandLine === "string" ? row.CommandLine : "";
    const name = typeof row.Name === "string" ? row.Name : "";
    if (isPiInvocation(name, command, windowsCommandTokens(command))) processes.push({ pid, startedAt });
  }
  return processes;
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
export function readProcessSnapshot(command: string, args: string[], options: {
  timeoutMs?: number;
  execute?: typeof execFile;
} = {}): Promise<string> {
  const timeoutMs = options.timeoutMs ?? PROCESS_TIMEOUT_MS;
  return new Promise((resolve, reject) => {
    let settled = false;
    let deadline: ReturnType<typeof setTimeout> | undefined;
    const finish = (error: Error | null, output = ""): void => {
      if (settled) return;
      settled = true;
      if (deadline !== undefined) clearTimeout(deadline);
      if (error) reject(error);
      else resolve(output);
    };
    // execFile's timeout waits for child close; a stuck OS query may never close.
    const child = (options.execute ?? execFile)(command, args, {
      encoding: "utf8", maxBuffer: MAX_PROCESS_BYTES, timeout: timeoutMs, windowsHide: true,
    }, (error, stdout) => finish(error, stdout));
    if (settled) return;
    deadline = setTimeout(() => {
      if (settled) return;
      child.kill("SIGKILL");
      child.stdout?.destroy();
      child.stderr?.destroy();
      child.unref();
      finish(new Error("process snapshot deadline exceeded"));
    }, timeoutMs);
    deadline.unref?.();
  });
}

/** Return an unavailable inventory on every bounded query failure. */
export async function listPiProcesses(options: {
  platform?: NodeJS.Platform;
  now?: () => number;
  readSnapshot?: (command: string, args: string[]) => Promise<string>;
} = {}): Promise<PiProcess[]> {
  const platform = options.platform ?? process.platform;
  const now = (options.now ?? Date.now)();
  const command = platform === "win32" ? "powershell.exe" : "ps";
  const args = platform === "win32"
    ? ["-NoProfile", "-NonInteractive", "-Command", WINDOWS_PROCESS_SCRIPT]
    : platform === "darwin"
    ? ["-axo", "pid=,etime=,stat=,comm=,args="]
    : ["-eo", "pid=,etimes=,stat=,comm=,args="];
  const read = options.readSnapshot ?? ((executable, arguments_) => readProcessSnapshot(executable, arguments_, {
    timeoutMs: platform === "win32" ? 5000 : PROCESS_TIMEOUT_MS,
  }));
  try {
    const output = await read(command, args);
    if (Buffer.byteLength(output) > MAX_PROCESS_BYTES) return [];
    return platform === "win32" ? parseWindowsPiProcesses(output, now) : parsePiProcesses(output, now);
  } catch { return []; }
}
