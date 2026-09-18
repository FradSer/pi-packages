import { constants } from "node:fs";
import { lstat, open, opendir } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { boundEventText } from "./events.ts";
import { MAX_SESSIONS_PER_MACHINE } from "./reporter.ts";
import { normalizeSessionId } from "./session-identity.ts";
import { listPiProcesses, type PiProcess } from "./processes.ts";
export { parsePiProcesses } from "./processes.ts";
import type { ReportedSession } from "./types.ts";

export const MAX_METADATA_BYTES = 16 * 1024;
export const MAX_METADATA_FILES = 2048;
export const MAX_WORKSPACES = 256;
export const MAX_SCAN_ENTRIES = 8192;
export const DISCOVERY_INTERVAL_MS = 5000;

export interface DiscoveryOptions {
  registryDir?: string;
  checkProcessAlive?: (pid: number) => boolean;
  listProcesses?: () => Promise<PiProcess[]>;
}

interface Metadata {
  sessionId: string;
  pid?: number;
  name?: string;
  cwd?: string;
  status?: string;
  startedAt?: number;
  updatedAt?: number;
  latestGoal?: string;
  activity?: string;
}

export function directorySessionsPath(env: NodeJS.ProcessEnv = process.env): string {
  return env.PI_DIRECTORY_SESSIONS_DIR || join(
    env.PI_CODING_AGENT_DIR || env.PI_AGENT_DIR || join(homedir(), ".pi", "agent"),
    "directory-sessions",
  );
}

function positiveNumber(value: unknown): number | undefined {
  if (typeof value !== "number" && typeof value !== "string") return undefined;
  const number = Number(value);
  return Number.isSafeInteger(number) && number > 0 ? number : undefined;
}

function checkProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    // Unverifiable is not evidence of a running Pi session.
    return false;
  }
}

/** Accept only descriptive registry fields, never sessionFile or arbitrary data. */
function parseMetadata(value: unknown, filename: string): Metadata | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const raw = value as Record<string, unknown>;
  const sessionId = normalizeSessionId(raw.sessionId ?? filename.slice(0, -5));
  if (!sessionId) return null;
  const record: Metadata = { sessionId };
  const pid = positiveNumber(raw.pid);
  if (pid !== undefined && pid <= 0x7fffffff) record.pid = pid;
  const startedAt = positiveNumber(raw.startedAt);
  const updatedAt = positiveNumber(raw.updatedAt);
  if (startedAt !== undefined) record.startedAt = startedAt;
  if (updatedAt !== undefined) record.updatedAt = updatedAt;
  if (typeof raw.status === "string") record.status = boundEventText(raw.status);
  // cwd is workspace identity, not display copy: shortening merges distinct paths.
  if (typeof raw.cwd === "string" && raw.cwd.length > 0) record.cwd = raw.cwd;
  for (const [key, value] of [
    ["name", raw.sessionName ?? raw.name],
    ["latestGoal", raw.latestGoal],
    ["activity", raw.activity || raw.recap],
  ] as const) {
    const text = boundEventText(value);
    if (text) record[key] = text;
  }
  return record;
}

async function readMetadata(file: string, filename: string): Promise<Metadata | null> {
  // O_NONBLOCK also prevents a file swapped for a FIFO from hanging a refresh.
  const handle = await open(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || stat.nlink !== 1 || stat.size > MAX_METADATA_BYTES) return null;
    const buffer = Buffer.alloc(MAX_METADATA_BYTES + 1);
    let used = 0;
    while (used < buffer.length) {
      const { bytesRead } = await handle.read(buffer, used, buffer.length - used, used);
      if (bytesRead === 0) break;
      used += bytesRead;
    }
    // Bound the read itself, not just the pre-read stat (writers may replace/grow files).
    if (used > MAX_METADATA_BYTES) return null;
    return parseMetadata(JSON.parse(buffer.toString("utf8", 0, used)), filename);
  } finally {
    await handle.close();
  }
}

/**
 * Read-only inventory of the shared directory-sessions registry (pi-utils and
 * pi-keyboard). SessionManager.listAll() reads histories and has no PID/state;
 * it is deliberately not a fallback for this metadata-only boundary.
 */
export async function scanDirectorySessions(options: DiscoveryOptions = {}): Promise<ReportedSession[]> {
  const root = options.registryDir ?? directorySessionsPath();
  const alive = options.checkProcessAlive ?? checkProcessAlive;
  const metadata = new Map<string, Metadata>();
  let entries = 0, workspaces = 0, files = 0;
  try {
    if (!(await lstat(root)).isDirectory()) return [];
    const directories = await opendir(root);
    for await (const directory of directories) {
      if (++entries > MAX_SCAN_ENTRIES || workspaces >= MAX_WORKSPACES || files >= MAX_METADATA_FILES) break;
      if (!directory.isDirectory()) continue;
      workspaces += 1;
      const workspace = join(root, directory.name);
      try {
        if (!(await lstat(workspace)).isDirectory()) continue;
        const contents = await opendir(workspace);
        for await (const file of contents) {
          if (++entries > MAX_SCAN_ENTRIES || files >= MAX_METADATA_FILES) break;
          if (!file.isFile() || !file.name.endsWith(".json")) continue;
          files += 1;
          try {
            const candidate = await readMetadata(join(workspace, file.name), file.name);
            if (!candidate) continue;
            const previous = metadata.get(candidate.sessionId);
            // Different writers may omit fields; the newest known field wins.
            metadata.set(candidate.sessionId, !previous ? candidate
              : (candidate.updatedAt ?? 0) >= (previous.updatedAt ?? 0)
                ? { ...previous, ...candidate } : { ...candidate, ...previous });
          } catch {
            // Malformed, oversized, disappearing or unreadable files are not sessions.
          }
        }
      } catch {
        // An unavailable workspace does not suppress the other workspaces.
      }
    }
  } catch {
    // A missing registry is normal on machines without a metadata writer.
  }

  let processes: PiProcess[] = [];
  try {
    processes = await (options.listProcesses ?? listPiProcesses)();
  } catch {
    // Failed process inspection is not proof of live sessions.
  }
  const startedByPid = new Map(processes.map((process) => [process.pid, process.startedAt]));
  const byPid = new Map<number, Metadata[]>();
  for (const item of metadata.values()) {
    if (item.pid === undefined) continue;
    const candidates = byPid.get(item.pid) ?? [];
    candidates.push(item);
    byPid.set(item.pid, candidates);
  }
  const liveIds = new Set<string>();
  for (const [pid, candidates] of byPid) {
    if (!alive(pid)) continue;
    const processStartedAt = startedByPid.get(pid);
    if (processStartedAt === undefined || !Number.isFinite(processStartedAt)) continue;
    const compatible = candidates.filter((candidate) => {
      // The registry must have been written during this process lifetime. This
      // covers resumed sessions without reviving records from a reused PID.
      return (candidate.updatedAt !== undefined && candidate.updatedAt >= processStartedAt - 5000)
        || (candidate.startedAt !== undefined && Math.abs(candidate.startedAt - processStartedAt) <= 5000);
    });
    compatible.sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
    const newest = compatible[0];
    if (!newest) continue;
    // A process can serve just one current session. Ties are not proof of either.
    if (compatible.length > 1 && newest.updatedAt === compatible[1]!.updatedAt) continue;
    if (newest.status !== "exited") liveIds.add(newest.sessionId);
  }

  const sessions: ReportedSession[] = [...metadata.values()].map((item) => {
    const cwd = item.cwd ?? "";
    const workspaceName = cwd.split(/[/\\]/).filter(Boolean).at(-1) ?? "";
    return {
      sessionId: item.sessionId,
      ...(item.name === undefined ? {} : { name: item.name }),
      cwd,
      workspaceName,
      status: !liveIds.has(item.sessionId) ? "exited" : item.status === "running" ? "running" : "settled",
      startedAt: item.startedAt ?? 0,
      updatedAt: item.updatedAt ?? 0,
      ...(item.latestGoal === undefined ? {} : { latestGoal: item.latestGoal }),
      ...(item.activity === undefined ? {} : { activity: item.activity }),
    };
  });
  const priority = { exited: 0, settled: 1, running: 2 };
  sessions.sort((a, b) => priority[b.status] - priority[a.status]
    || (b.updatedAt || b.startedAt) - (a.updatedAt || a.startedAt)
    || a.sessionId.localeCompare(b.sessionId));
  return sessions.slice(0, MAX_SESSIONS_PER_MACHINE);
}

interface SessionDiscoveryOptions {
  discover: () => Promise<ReportedSession[]>;
  onSnapshot: (sessions: ReportedSession[]) => void;
  schedule?: (run: () => void, delayMs: number) => () => void;
}

/** One non-overlapping refresh loop, scoped to a started Pi session. */
export class SessionDiscovery {
  readonly #options: SessionDiscoveryOptions;
  readonly #schedule: NonNullable<SessionDiscoveryOptions["schedule"]>;
  #cancel: (() => void) | undefined;
  #active = false;
  #pending = false;
  #generation = 0;

  constructor(options: SessionDiscoveryOptions) {
    this.#options = options;
    this.#schedule = options.schedule ?? ((run, delayMs) => {
      const timer = setTimeout(run, delayMs);
      timer.unref();
      return () => clearTimeout(timer);
    });
  }

  start(): void {
    if (this.#active) return;
    this.#active = true;
    this.#generation += 1;
    void this.#refresh();
  }

  stop(): void {
    this.#active = false;
    this.#generation += 1;
    this.#cancel?.();
    this.#cancel = undefined;
  }

  async #refresh(): Promise<void> {
    if (!this.#active || this.#pending) return;
    this.#pending = true;
    const generation = this.#generation;
    try {
      const sessions = await this.#options.discover();
      if (this.#active && generation === this.#generation) this.#options.onSnapshot(sessions);
    } catch {
      // Best effort: a failed refresh must not reject into Pi or erase live state.
    } finally {
      this.#pending = false;
      if (this.#active) {
        const current = this.#generation;
        this.#cancel = this.#schedule(() => {
          if (current !== this.#generation) return;
          this.#cancel = undefined;
          void this.#refresh();
        }, DISCOVERY_INTERVAL_MS);
      }
    }
  }
}
