import { expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { inspectDebug } from "../../../.agents/skills/continual-learning-debug/scripts/inspect-debug.ts";
import { debugDirectory } from "../extensions/debug.ts";

function fixture() {
  const root = realpathSync(mkdtempSync(path.join(os.tmpdir(), "cl-debug-inspector-")));
  const project = path.join(root, "project"), agentDir = path.join(root, "agent");
  mkdirSync(project); mkdirSync(agentDir, { mode: 0o700 });
  const directory = debugDirectory(project, agentDir); mkdirSync(directory, { recursive: true, mode: 0o700 });
  const row = (id: string, phase = "started", session = "one") => ({ kind: "continual-learning-debug", version: 1,
    timestamp: "2026-11-10T00:00:00.000Z", invocationId: id, parentInvocationId: null,
    source: "extensions/example.ts", event: "tool:learn", phase, outcome: phase === "failed" ? "failed" : phase,
    context: { cwd: project, sessionId: session, entries: [], omittedEntries: 0 }, data: { result: "fixture" } });
  return { root, project, agentDir, directory, row };
}

test("本地检查器按项目和 session 关联失败、未闭合调用及原始行位置", () => {
  const f = fixture();
  try {
    const rows = [f.row("failed"), f.row("failed", "failed"), f.row("open"), f.row("other", "started", "two"),
      { ...f.row("foreign"), context: { cwd: path.join(f.root, "foreign"), sessionId: "one" } }];
    writeFileSync(path.join(f.directory, "fixture.jsonl"), rows.map(row => JSON.stringify(row)).join("\n") + "\n", { mode: 0o600 });
    const report = inspectDebug({ project: f.project, agentDir: f.agentDir, session: "one" });
    expect(report.recordsRead).toBe(3);
    expect(report.issues).toHaveLength(1);
    expect(report.issues[0].line).toBe(2);
    expect(report.unclosedInvocations).toEqual(["open"]);
    expect(report.incomplete).toBe(true);
    expect(report.diagnostics.some(item => item.reason === "foreign-project-record")).toBe(true);
    expect(readFileSync(path.join(f.directory, "fixture.jsonl"), "utf8")).toContain('"foreign"');
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("日志采样、损坏和脱敏不会产生完整证据或泄露敏感值", () => {
  const f = fixture();
  try {
    const secret = "sk-" + "inspector-synthetic-credential-12345";
    const row = { ...f.row("bad", "failed"), data: { error: "api_key: " + secret } };
    writeFileSync(path.join(f.directory, "a.jsonl"), JSON.stringify(row) + "\n", { mode: 0o600 });
    writeFileSync(path.join(f.directory, "z.jsonl"), JSON.stringify(row) + "\n{broken}\n{", { mode: 0o600 });
    const report = inspectDebug({ project: f.project, agentDir: f.agentDir, maxFiles: 1 });
    expect(report.omittedFiles).toBe(1);
    expect(report.incomplete).toBe(true);
    expect(report.diagnostics.map(item => item.reason)).toContain("unterminated-record");
    expect(report.diagnostics.map(item => item.reason)).toContain("malformed-record");
    expect(JSON.stringify(report)).not.toContain(secret);
    expect(JSON.stringify(report)).toContain("redacted");
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("重叠 writer 按实际事件时间选择最近记录", () => {
  const f = fixture();
  try {
    const newest = { ...f.row("newest", "failed"), timestamp: "2026-11-10T12:00:00.000Z" };
    const oldest = { ...f.row("oldest", "failed"), timestamp: "2026-11-10T01:00:00.000Z" };
    writeFileSync(path.join(f.directory, "a.jsonl"), JSON.stringify(newest) + "\n", { mode: 0o600 });
    writeFileSync(path.join(f.directory, "z.jsonl"), JSON.stringify(oldest) + "\n", { mode: 0o600 });
    const report = inspectDebug({ project: f.project, agentDir: f.agentDir, limit: 1 });
    expect(report.recent[0].file).toBe("a.jsonl");
    expect(report.issues[0].file).toBe("a.jsonl");
    expect(report.incomplete).toBe(false);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("agent 根目录别名和已脱敏项目仍能找到同一组私有记录", () => {
  const f = fixture();
  try {
    const alias = path.join(f.root, "alias"); symlinkSync(f.agentDir, alias);
    const projectId = path.basename(f.directory);
    writeFileSync(path.join(f.directory, "fixture.jsonl"), JSON.stringify({ ...f.row("safe", "completed"),
      context: { projectId, cwd: { omitted: "redacted" }, sessionId: "one" } }) + "\n", { mode: 0o600 });
    const report = inspectDebug({ project: f.project, agentDir: alias });
    expect(report.directory).toBe(f.directory);
    expect(report.recordsRead).toBe(1);
    expect(report.incomplete).toBe(false);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("检查器汇总采样覆盖、退出缺口、context 引用和批量 handler 身份", () => {
  const f = fixture();
  try {
    const snapshot = { ...f.row("snapshot", "observed"), event: "context:snapshot", contextDigest: "context-digest" };
    const nested = { ...f.row("nested", "completed"), contextRef: "context-digest" };
    const missing = { ...f.row("missing", "completed"), contextRef: "missing-digest" };
    const batch = { ...f.row("batch", "completed"), event: "lifecycle:batch", data: { handlers: [
      { invocationId: "h1", outcome: "started" }, { invocationId: "h1", outcome: "completed" },
      { invocationId: "h2", outcome: "started" }, { invocationId: "h2", outcome: "completed" },
      { invocationId: "h3", outcome: "failed" },
    ] } };
    const start = { ...f.row("start", "started"), event: "event:session_start" };
    const exit = { ...f.row("exit", "observed"), event: "process:exit", data: { reason: "quit", exitCode: 0 } };
    writeFileSync(path.join(f.directory, "a.jsonl"), [snapshot, nested, missing, batch, start, exit].map(row => JSON.stringify(row)).join("\n") + "\n", { mode: 0o600 });
    writeFileSync(path.join(f.directory, "z.jsonl"), [snapshot, { ...f.row("snapshot-2", "observed"), event: "context:snapshot", contextDigest: "other-digest" }].map(row => JSON.stringify(row)).join("\n") + "\n", { mode: 0o600 });
    const all = inspectDebug({ project: f.project, agentDir: f.agentDir, maxFiles: 2 });
    const report = inspectDebug({ project: f.project, agentDir: f.agentDir, maxFiles: 1 });
    expect(all.missingContextRefs).toEqual(["missing-digest"]);
    expect(all.contextSnapshots).toBe(3);
    expect(report.totalFiles).toBe(2);
    expect(report.sampledFiles).toBe(1);
    expect(report.totalBytes).toBeGreaterThan(report.sampledBytes);
    expect(report.coverageFrom).toBe("2026-11-10T00:00:00.000Z");
    expect(report.incomplete).toBe(true);
    expect(all.handlerCounts["lifecycle:batch"]).toBe(3); // 3 个身份，5 行(started+终态)。
    expect(all.sessionLifecycle).toMatchObject({ sessionsStarted: 1, shutdownEvents: 0, processExits: 1, missingShutdown: ["undefined:one"], possibleAbnormalExit: true });
    expect(all.unclosedInvocations).toEqual(["start"]);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("关闭 debug 只收束显式绑定的在途调用，旧的未闭合调用仍如实保留", () => {
  const f = fixture();
  try {
    const started = (id: string) => ({ ...f.row(id, "started"), timestamp: "2026-11-10T00:00:00.000Z" });
    const disabled = { ...f.row("config", "completed"), event: "debug:configuration", outcome: "disabled",
      timestamp: "2026-11-10T01:00:00.000Z", data: { enabled: false, truncatedInvocations: ["inflight"] } };
    const rows = [started("crashed"), started("inflight"), disabled];
    writeFileSync(path.join(f.directory, "fixture.jsonl"), rows.map(row => JSON.stringify(row)).join("\n") + "\n", { mode: 0o600 });
    const report = inspectDebug({ project: f.project, agentDir: f.agentDir });
    expect(report.unclosedInvocations).toContain("crashed");
    expect(report.unclosedInvocations).not.toContain("inflight");
    expect(report.closedByDebugShutdown).toEqual(["inflight"]);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});

test("检查器拒绝 symlink 和不安全文件，缺失日志保留未知状态", () => {
  const f = fixture();
  try {
    const outside = path.join(f.root, "outside"); writeFileSync(outside, JSON.stringify(f.row("outside")) + "\n", { mode: 0o600 });
    symlinkSync(outside, path.join(f.directory, "linked.jsonl"));
    writeFileSync(path.join(f.directory, "public.jsonl"), JSON.stringify(f.row("public")) + "\n", { mode: 0o644 });
    const report = inspectDebug({ project: f.project, agentDir: f.agentDir });
    expect(report.recordsRead).toBe(0);
    expect(report.incomplete).toBe(true);
    expect(report.diagnostics.filter(item => item.reason === "unsafe-or-changed-log")).toHaveLength(2);
    expect(report.diagnostics.some(item => item.reason === "no-matching-records")).toBe(true);
    expect(report.issues).toEqual([]);
    expect(inspectDebug({ project: f.project, agentDir: path.join(f.root, "missing") }).incomplete).toBe(true);
  } finally { rmSync(f.root, { recursive: true, force: true }); }
});
