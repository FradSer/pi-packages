import { createHash } from "node:crypto";
import { closeSync, constants, fstatSync, lstatSync, openSync, readSync, readdirSync, realpathSync } from "node:fs";
import path from "node:path";
import os from "node:os";
import { debugDirectory, sanitizeDebugValue } from "../../../../packages/continual-learning/extensions/debug.ts";
import { canonicalProjectCwd } from "../../../../packages/continual-learning/extensions/memory-paths.ts";

interface Options { project: string; agentDir: string; session?: string; maxFiles?: number; limit?: number }
interface LocatedRecord { file: string; line: number; record: unknown }
interface Diagnostic { file?: string; line?: number; reason: string }
interface Inspection {
  directory: string; project: ReturnType<typeof sanitizeDebugValue>; projectId: string; filesRead: number; recordsRead: number; omittedFiles: number;
  totalFiles: number; sampledFiles: number; totalBytes: number; sampledBytes: number; coverageFrom?: string; coverageTo?: string;
  incomplete: boolean; diagnostics: Diagnostic[]; eventCounts: Record<string, number>; outcomeCounts: Record<string, number>;
  unclosedInvocations: string[]; closedByDebugShutdown: string[]; unclosedPipelines: string[]; contextSnapshots: number; missingContextRefs: string[];
  sessionLifecycle: { sessionsStarted: number; shutdownEvents: number; processExits: number; missingShutdown: string[]; possibleAbnormalExit: boolean };
  handlerCounts: Record<string, number>; issues: LocatedRecord[]; recent: LocatedRecord[];
  files: Array<{ name: string; sha256: string; bytes: number }>;
  evidenceMeaning: string;
}
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value);
const sha256 = (bytes: Uint8Array): string => createHash("sha256").update(bytes).digest("hex");

function assertDirectory(directory: string, agentDir: string): void {
  const relative = path.relative(agentDir, directory);
  if (relative.startsWith("..") || path.isAbsolute(relative)) throw Error("outside-agent-root");
  let current = agentDir;
  for (const part of ["", ...relative.split(path.sep).filter(Boolean)]) {
    current = path.join(current, part);
    const stat = lstatSync(current);
    if (stat.isSymbolicLink() || !stat.isDirectory() || current !== agentDir && (stat.mode & 0o077) !== 0) throw Error("unsafe-directory");
  }
}

function readLog(file: string, directory: string, agentDir: string): Buffer {
  assertDirectory(directory, agentDir);
  const named = lstatSync(file, { bigint: true });
  if (!named.isFile() || named.isSymbolicLink() || named.nlink !== 1n || (named.mode & 0o077n) !== 0n || named.size > 4n * 1024n * 1024n) throw Error("unsafe-log");
  const fd = openSync(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const before = fstatSync(fd, { bigint: true });
    if (!before.isFile() || before.dev !== named.dev || before.ino !== named.ino || before.size !== named.size) throw Error("log-changed");
    const bytes = Buffer.alloc(Number(before.size));
    let offset = 0;
    while (offset < bytes.length) {
      const count = readSync(fd, bytes, offset, bytes.length - offset, offset);
      if (!count) throw Error("incomplete-log");
      offset += count;
    }
    assertDirectory(directory, agentDir);
    const after = fstatSync(fd, { bigint: true }), current = lstatSync(file, { bigint: true });
    if (after.size !== before.size || after.mtimeNs !== before.mtimeNs || after.ctimeNs !== before.ctimeNs || current.dev !== before.dev || current.ino !== before.ino || current.isSymbolicLink()) throw Error("log-changed");
    return bytes;
  } finally { closeSync(fd); }
}

export function inspectDebug(options: Options): Inspection {
  const project = realpathSync(options.project), agentDir = canonicalProjectCwd(options.agentDir);
  const projectId = sha256(Buffer.from(project));
  const maxFiles = options.maxFiles ?? 12, limit = options.limit ?? 20;
  if (!Number.isInteger(maxFiles) || maxFiles < 1 || maxFiles > 32 || !Number.isInteger(limit) || limit < 1 || limit > 100) throw Error("invalid-bounds");
  const directory = debugDirectory(project, agentDir);
  const report: Inspection = { directory, project: sanitizeDebugValue(project), projectId, filesRead: 0, recordsRead: 0, omittedFiles: 0,
    totalFiles: 0, sampledFiles: 0, totalBytes: 0, sampledBytes: 0, incomplete: false,
    diagnostics: [], eventCounts: {}, outcomeCounts: {}, unclosedInvocations: [], closedByDebugShutdown: [], unclosedPipelines: [], contextSnapshots: 0, missingContextRefs: [],
    sessionLifecycle: { sessionsStarted: 0, shutdownEvents: 0, processExits: 0, missingShutdown: [], possibleAbnormalExit: false },
    handlerCounts: {}, issues: [], recent: [], files: [],
    evidenceMeaning: "仅表示这些本地日志中的实际观测；callback 完成、学习落盘、模型消费和任务收益分别验证。未闭合记录和缺失日志不能单独证明崩溃或零费用。" };
  const issue = (diagnostic: Diagnostic) => { report.incomplete = true; report.diagnostics.push(diagnostic); };
  let files: string[];
  try {
    assertDirectory(directory, agentDir);
    files = readdirSync(directory).filter(name => name.endsWith(".jsonl")).sort();
  } catch { issue({ reason: "missing-or-unsafe-debug-directory" }); return report; }
  report.totalFiles = files.length; report.sampledFiles = Math.min(files.length, maxFiles);
  report.omittedFiles = Math.max(0, files.length - maxFiles);
  if (report.omittedFiles) report.incomplete = true;
  try {
    for (const name of files) {
      const stat = lstatSync(path.join(directory, name), { bigint: true });
      if (stat.isFile() && !stat.isSymbolicLink()) report.totalBytes += Number(stat.size);
    }
  } catch { issue({ reason: "segment-inventory-unavailable" }); }
  if (!files.length) issue({ reason: "no-debug-records" });
  const retainRecent = (rows: LocatedRecord[], item: LocatedRecord): void => {
    const timestamp = (row: LocatedRecord): number => object(row.record) && typeof row.record.timestamp === "string" ? Date.parse(row.record.timestamp) : 0;
    rows.push(item);
    rows.sort((a, b) => timestamp(a) - timestamp(b) || a.file.localeCompare(b.file) || a.line - b.line);
    if (rows.length > limit) rows.shift();
  };
  const started = new Map<string, number>(), closed = new Set<string>(), pipelines = new Set<string>(), pipelineClosed = new Set<string>();
  const contexts = new Set<string>(), contextReferences = new Set<string>(), sessionStarts = new Set<string>(), shutdowns = new Set<string>();
  // 只有关闭边界显式列出的在途调用可以被收束；时间戳先后不能推断干净的关闭。
  const truncatedByDebugShutdown = new Set<string>();
  const timestamps: string[] = [];
  for (const name of files.slice(-maxFiles)) {
    const file = path.join(directory, name);
    let bytes: Buffer;
    try { bytes = readLog(file, directory, agentDir); }
    catch { issue({ file: name, reason: "unsafe-or-changed-log" }); continue; }
    report.filesRead++;
    report.sampledBytes += bytes.length;
    report.files.push({ name, sha256: sha256(bytes), bytes: bytes.length });
    const text = bytes.toString("utf8");
    if (!Buffer.from(text).equals(bytes)) { issue({ file: name, reason: "invalid-utf8" }); continue; }
    const lines = text.split("\n");
    if (lines.at(-1) !== "") issue({ file: name, line: lines.length, reason: "unterminated-record" });
    for (let i = 0; i < lines.length - 1; i++) {
      const line = lines[i];
      if (!line.trim()) continue;
      if (Buffer.byteLength(line) > 64 * 1024) { issue({ file: name, line: i + 1, reason: "oversized-record" }); continue; }
      let row: unknown;
      try { row = JSON.parse(line); } catch { issue({ file: name, line: i + 1, reason: "malformed-record" }); continue; }
      if (!object(row) || row.kind !== "continual-learning-debug" || row.version !== 1 || !object(row.context)
        || typeof row.invocationId !== "string" || typeof row.event !== "string" || typeof row.outcome !== "string"
        || typeof row.timestamp !== "string" || !Number.isFinite(Date.parse(row.timestamp))) {
        issue({ file: name, line: i + 1, reason: "unknown-record-shape" }); continue;
      }
      if (row.context.projectId !== undefined ? row.context.projectId !== projectId : row.context.cwd !== project) {
        issue({ file: name, line: i + 1, reason: "foreign-project-record" }); continue;
      }
      if (options.session !== undefined && row.context.sessionId !== options.session) continue;
      report.recordsRead++;
      timestamps.push(row.timestamp);
      report.eventCounts[row.event] = (report.eventCounts[row.event] ?? 0) + 1;
      report.outcomeCounts[row.outcome] = (report.outcomeCounts[row.outcome] ?? 0) + 1;
      if (row.phase === "started") started.set(row.invocationId, Date.parse(row.timestamp));
      if (row.phase === "completed" || row.phase === "failed") closed.add(row.invocationId);
      if (row.event === "debug:configuration" && row.outcome === "disabled" && object(row.data)
        && Array.isArray(row.data.truncatedInvocations)) {
        for (const id of row.data.truncatedInvocations) if (typeof id === "string") truncatedByDebugShutdown.add(id);
      }
      if (row.event === "context:snapshot") {
        contexts.add(typeof row.contextDigest === "string" ? row.contextDigest : row.invocationId);
        report.contextSnapshots++;
      }
      if (typeof row.contextRef === "string" && row.event !== "context:snapshot") {
    contextReferences.add(row.contextRef);
    if (!contexts.has(row.contextRef)) report.missingContextRefs.push(row.contextRef);
  }
      const data = object(row.data) ? row.data : {};
      const handlers = Array.isArray(row.handlers) ? row.handlers : Array.isArray(data.handlers) ? data.handlers : undefined;
      if (handlers) {
        const identities = new Set<string>();
        for (const handler of handlers) {
          if (object(handler) && typeof handler.invocationId === "string") {
            identities.add(handler.invocationId);
            started.set(handler.invocationId, Date.parse(row.timestamp));
            if (typeof handler.outcome === "string" && handler.outcome !== "started") closed.add(handler.invocationId);
          }
        }
        // 成功 handler 在批量里各占 started + 终态两行；按身份数，不按行数。
        report.handlerCounts[row.event] = (report.handlerCounts[row.event] ?? 0) + identities.size;
      }
      const sessionId = typeof row.context?.sessionId === "string" ? row.context.sessionId : "unknown";
      const lifecycleEvent = row.event === "lifecycle:batch" && typeof data.event === "string" ? data.event : row.event;
      if (lifecycleEvent === "event:session_start" && row.phase !== "failed") sessionStarts.add(`${row.pid}:${sessionId}`);
      if (lifecycleEvent === "event:session_shutdown" && row.phase === "completed") shutdowns.add(`${row.pid}:${sessionId}`);
      if (row.event === "process:exit") report.sessionLifecycle.processExits++;
      if (typeof data.batchId === "string") {
        if (row.event === "pipeline:started") pipelines.add(data.batchId);
        if (row.event === "pipeline:closed") pipelineClosed.add(data.batchId);
      }
      const located = { file: name, line: i + 1, record: sanitizeDebugValue(row) };
      const receipt = object(data.receipt) ? data.receipt : undefined;
      const pendingReceipt = receipt && Array.isArray(receipt.attempts) && receipt.attempts.some(attempt => object(attempt) && ["failed", "cancelled", "rejected", "proposed"].includes(String(attempt.outcome)));
      if (["failed", "blocked", "cancelled", "held", "rejected", "proposed"].includes(row.outcome) || ["receipt:failed", "pipeline:failed"].includes(row.event) || pendingReceipt) {
        retainRecent(report.issues, located);
      }
      retainRecent(report.recent, located);
    }
  }
  const open = [...started].map(([id]) => id).filter(id => !closed.has(id));
  report.closedByDebugShutdown = open.filter(id => truncatedByDebugShutdown.has(id));
  report.unclosedInvocations = open.filter(id => !truncatedByDebugShutdown.has(id));
  report.unclosedPipelines = [...pipelines].filter(id => !pipelineClosed.has(id));
  report.missingContextRefs = [...contextReferences].filter(ref => !contexts.has(ref));
  report.sessionLifecycle.sessionsStarted = sessionStarts.size;
  report.sessionLifecycle.shutdownEvents = shutdowns.size;
  report.sessionLifecycle.missingShutdown = [...sessionStarts].filter(session => !shutdowns.has(session));
  report.sessionLifecycle.possibleAbnormalExit = report.sessionLifecycle.missingShutdown.length > 0
    && report.sessionLifecycle.processExits > 0;
  if (timestamps.length) {
    const sorted = timestamps.sort();
    report.coverageFrom = sorted[0]; report.coverageTo = sorted.at(-1);
  }
  if (!report.recordsRead) issue({ reason: "no-matching-records" });
  if (report.missingContextRefs.length) issue({ reason: "unresolved-context-references" });
  return report;
}

if (import.meta.main) {
  const repo = path.resolve(import.meta.dir, "../../../..");
  const values = new Map<string, string>();
  try {
    const args = process.argv.slice(2);
    if (args.includes("--help")) {
      console.log("Usage: bun inspect-debug.ts [--project PATH] [--agent-dir PATH] [--session ID] [--max-files 1..32] [--limit 1..100]");
    } else {
      for (let i = 0; i < args.length; i += 2) {
        const key = args[i], value = args[i + 1];
        if (!["--project", "--agent-dir", "--session", "--max-files", "--limit"].includes(key) || !value || values.has(key)) throw Error("invalid-arguments");
        values.set(key, value);
      }
      const entry = lstatSync(path.join(repo, "packages/continual-learning/index.ts"));
      if (!entry.isFile() || entry.isSymbolicLink()) throw Error("wrong-repository");
      const report = inspectDebug({ project: values.get("--project") ?? repo,
        agentDir: values.get("--agent-dir") ?? process.env.PI_CODING_AGENT_DIR ?? path.join(os.homedir(), ".pi", "agent"),
        session: values.get("--session"), maxFiles: values.has("--max-files") ? Number(values.get("--max-files")) : undefined,
        limit: values.has("--limit") ? Number(values.get("--limit")) : undefined });
      console.log(JSON.stringify(report, null, 2));
    }
  } catch { console.error("调试记录读取失败；检查仓库、项目路径、agent 根目录和参数。原记录未修改。"); process.exitCode = 1; }
}
