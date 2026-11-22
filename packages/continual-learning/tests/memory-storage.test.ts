/** Whitespace-free storage paths, empty learning intermediates, and git-tracked mirror imports. */
import { describe, expect, test } from "bun:test";
import { execFileSync } from "node:child_process";
import {
  existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, realpathSync, rmSync, writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import { normalizeMirrorDrift } from "../extensions/consolidation-run.ts";
import { readBacklog } from "../extensions/learning-backlog.ts";
import { listLearningHistory, normalizeTrackedMemory } from "../extensions/learning-history.ts";
import { claimLearningLease, replayLearningBacklog } from "../extensions/learning-replay.ts";
import { escapedProjectPath, resolveMemoryPaths } from "../extensions/memory-paths.ts";

describe("memory storage paths and empty intermediates", () => {
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
});

describe("git-tracked mirror import", () => {
  function project() {
    const root = mkdtempSync(path.join(os.tmpdir(), "cl-mirror-import-"));
    const repo = path.join(root, "repo");
    const agent = path.join(root, "agent");
    mkdirSync(repo);
    mkdirSync(agent, { recursive: true, mode: 0o700 });
    execFileSync("git", ["init", "-q", repo]);
    process.env.PI_CODING_AGENT_DIR = agent;
    const memory = resolveMemoryPaths(repo);
    mkdirSync(memory.harnessDir, { recursive: true, mode: 0o700 });
    mkdirSync(memory.publicDir!, { recursive: true, mode: 0o700 });
    return { root, memory };
  }

  const SHARED = [
    "agent-evidence-authority-boundaries.md",
    "open-deskos-cm5-personal-bot-service.md",
    "open-deskos-cm5-ssh-access.md",
    "open-deskos-device-diagnostic-gotchas.md",
    "open-deskos-futu-holdings-refresh.md",
    "open-deskos-windows-handheld-access.md",
    "runtime-upgrade-acceptance-boundaries.md",
  ];

  test("git-tracked public-only memories are imported into the private root, not deleted", async () => {
    const { root, memory } = project();
    try {
      writeFileSync(path.join(memory.harnessDir, "private-note.md"), "private body\n");
      writeFileSync(path.join(memory.harnessDir, "MEMORY.md"),
        "# Memory Index\n\n- [private-note.md](private-note.md) (harness only)\n");
      const bodies = new Map<string, string>();
      for (const [index, name] of SHARED.entries()) {
        const body = `---\nname: "${name}"\ndescription: "tracked project knowledge ${index}"\ntype: project\n---\nDurable body ${index}.\n`;
        bodies.set(name, body);
        writeFileSync(path.join(memory.publicDir!, name), body);
      }
      writeFileSync(path.join(memory.publicDir!, "MEMORY.md"),
        `# Memory Index\n\n${SHARED.map(name => `- [${name}](${name})`).join("\n")}\n`);

      const outcome = await normalizeMirrorDrift(memory);

      for (const name of SHARED) {
        expect(existsSync(path.join(memory.publicDir!, name))).toBe(true);
        expect(readFileSync(path.join(memory.publicDir!, name), "utf8")).toBe(bodies.get(name));
      }
      expect(outcome.removed).toEqual([]);
      for (const name of SHARED) {
        expect(readFileSync(path.join(memory.harnessDir, name), "utf8")).toBe(bodies.get(name));
      }
      expect(outcome.repaired.filter(row => row.direction === "public-to-harness").map(row => row.name).sort())
        .toEqual([...SHARED].sort());
      for (const dir of [memory.harnessDir, memory.publicDir!]) {
        const index = readFileSync(path.join(dir, "MEMORY.md"), "utf8");
        for (const name of SHARED) expect(index).toContain(`[${name}](${name})`);
      }
    } finally { rmSync(root, { recursive: true, force: true }); }
  });

  test("tracked project-shared memories never appear as deletions in learning history", async () => {
    const { root, memory } = project();
    try {
      writeFileSync(path.join(memory.harnessDir, "MEMORY.md"), "# Memory Index\n");
      const body = "---\nname: \"tracked.md\"\ndescription: \"tracked knowledge\"\ntype: project\n---\nDurable body.\n";
      writeFileSync(path.join(memory.publicDir!, "tracked.md"), body);
      writeFileSync(path.join(memory.publicDir!, "MEMORY.md"), "# Memory Index\n\n- [tracked.md](tracked.md)\n");

      const outcome = await normalizeTrackedMemory(memory);
      expect(outcome.removed).toEqual([]);
      expect(readFileSync(path.join(memory.publicDir!, "tracked.md"), "utf8")).toBe(body);
      expect(readFileSync(path.join(memory.harnessDir, "tracked.md"), "utf8")).toBe(body);

      const records = await listLearningHistory(memory.cwd);
      const deletions = records.flatMap(record => record.changes.filter(change => change.after === null && change.before !== null)
        .map(change => `${change.target.root}/${change.target.name}`));
      expect(deletions).toEqual([]);
    } finally { rmSync(root, { recursive: true, force: true }); }
  });

  test("a harness-only file leaked into the public mirror is still removed", async () => {
    const { root, memory } = project();
    try {
      writeFileSync(path.join(memory.harnessDir, "secret.md"), "private body\n");
      writeFileSync(path.join(memory.harnessDir, "MEMORY.md"),
        "# Memory Index\n\n- [secret.md](secret.md) (harness only)\n");
      writeFileSync(path.join(memory.publicDir!, "secret.md"), "private body\n");
      writeFileSync(path.join(memory.publicDir!, "MEMORY.md"), "# Memory Index\n");
      const outcome = await normalizeMirrorDrift(memory);
      expect(outcome.removed).toEqual(["secret.md"]);
      expect(existsSync(path.join(memory.publicDir!, "secret.md"))).toBe(false);
      expect(readFileSync(path.join(memory.harnessDir, "secret.md"), "utf8")).toBe("private body\n");
      expect(readdirSync(memory.publicDir!).sort()).toEqual(["MEMORY.md"]);
    } finally { rmSync(root, { recursive: true, force: true }); }
  });
});
