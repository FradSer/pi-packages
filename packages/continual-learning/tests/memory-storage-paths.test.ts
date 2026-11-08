/** Whitespace-free storage paths and no empty learning intermediates. */
import { expect, test } from "bun:test";
import { mkdtempSync, mkdirSync, existsSync, readdirSync, rmSync, writeFileSync, realpathSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { escapedProjectPath, resolveMemoryPaths } from "../extensions/memory-paths.ts";
import { readBacklog } from "../extensions/learning-backlog.ts";
import { claimLearningLease, replayLearningBacklog } from "../extensions/learning-replay.ts";

const hasWhitespace = (value: string): boolean => /[\s\u0000-\u001f\u007f]/u.test(value);

function isolated() {
  const root = mkdtempSync(path.join(os.tmpdir(), "cl-storage-path-"));
  const agent = path.join(root, "agent");
  const cwd = path.join(root, "Home Lab", "1984");
  mkdirSync(agent, { recursive: true, mode: 0o700 });
  mkdirSync(cwd, { recursive: true });
  return { root, agent, cwd };
}

test("a plain project path keeps its existing readable scope name", () => {
  expect(escapedProjectPath("/tmp/a-b/c")).toBe("--tmp-a-b-c--");
});

test("interior whitespace is folded into one dash in every storage path", () => {
  const { root, agent, cwd } = isolated();
  try {
    const paths = resolveMemoryPaths(cwd, agent);
    const canonical = realpathSync(cwd);
    expect(paths.scopeKey).toBe(`--${canonical.replace(/^[/\\]/, "").replace(/[/\\:]/g, "-").replace(/\s+/gu, "-")}--`);
    for (const value of [paths.scopeKey, paths.harnessDir, paths.runsDir, paths.lockFile]) {
      expect(hasWhitespace(value)).toBe(false);
    }
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("leading, trailing, repeated and control whitespace never reach a path", () => {
  for (const cwd of ["/tmp/ Home  Lab /1984", "/tmp/Home\tLab/1984", "/tmp/Home\u0001Lab/1984"]) {
    expect(hasWhitespace(escapedProjectPath(cwd))).toBe(false);
  }
});

test("inspecting a backlog leaves no empty learning scope directory", () => {
  const { root, agent, cwd } = isolated();
  try {
    expect(readBacklog(cwd, agent).pending).toBe(0);
    expect(existsSync(path.join(agent, "learning", escapedProjectPath(cwd)))).toBe(false);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("a released replay lease leaves no empty learning scope directory", () => {
  const { root, agent, cwd } = isolated();
  try {
    const release = claimLearningLease(cwd, agent);
    expect(release).toBeDefined();
    const directory = path.join(agent, "learning", escapedProjectPath(cwd));
    expect(existsSync(path.join(directory, "replay.lock"))).toBe(true);
    release?.();
    expect(existsSync(directory)).toBe(false);
    expect(existsSync(path.join(agent, "learning", "backlog.lock"))).toBe(false);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("replaying an empty backlog leaves no empty learning scope directory", async () => {
  const { root, agent, cwd } = isolated();
  try {
    const result = await replayLearningBacklog({ cwd, agentDir: agent, learn: async () => undefined });
    expect(result.outcomes).toEqual([]);
    expect(existsSync(path.join(agent, "learning", escapedProjectPath(cwd)))).toBe(false);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("a retained attempt ledger and completion record are never pruned", () => {
  const { root, agent, cwd } = isolated();
  try {
    const directory = path.join(agent, "learning", escapedProjectPath(cwd));
    mkdirSync(directory, { recursive: true, mode: 0o700 });
    writeFileSync(path.join(directory, "replay-abc.json"), JSON.stringify({ attempts: [], nextAttemptAt: 0 }), { mode: 0o600 });
    writeFileSync(path.join(directory, "backlog-completed.json"), "{}", { mode: 0o600 });
    const release = claimLearningLease(cwd, agent);
    release?.();
    expect(readdirSync(directory).sort()).toEqual(["backlog-completed.json", "replay-abc.json"]);
  } finally { rmSync(root, { recursive: true, force: true }); }
});
