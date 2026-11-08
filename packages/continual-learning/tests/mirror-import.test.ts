/** Project-shared Memory arriving through the git-tracked mirror is imported, never deleted. */
import { expect, test } from "bun:test";
import { execFileSync } from "node:child_process";
import {
  mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync, readdirSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import { resolveMemoryPaths } from "../extensions/memory-paths.ts";
import { normalizeMirrorDrift } from "../extensions/consolidation-run.ts";
import { normalizeTrackedMemory } from "../extensions/learning-history.ts";
import { listLearningHistory } from "../extensions/learning-history.ts";

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
    // A pre-existing canonical root with one private-only entry.
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

    // No public entry may disappear or be rewritten.
    for (const name of SHARED) {
      expect(existsSync(path.join(memory.publicDir!, name))).toBe(true);
      expect(readFileSync(path.join(memory.publicDir!, name), "utf8")).toBe(bodies.get(name));
    }
    expect(outcome.removed).toEqual([]);
    // Each one becomes a byte-identical canonical copy.
    for (const name of SHARED) {
      expect(readFileSync(path.join(memory.harnessDir, name), "utf8")).toBe(bodies.get(name));
    }
    expect(outcome.repaired.filter(row => row.direction === "public-to-harness").map(row => row.name).sort())
      .toEqual([...SHARED].sort());
    // Indexes still list every shared entry on both sides.
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
