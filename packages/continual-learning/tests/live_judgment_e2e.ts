import { mock } from "bun:test";
import { selectIncrementalLearning } from "../extensions/incremental-learning.ts";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { judgmentObservationFile, promotionReport } from "../extensions/judgment-observations.ts";
import { resolveJudgmentConfig } from "../extensions/judgment-config.ts";
import { observeMemoryProposals } from "../extensions/judgment-shadow.ts";

// The selector's own worker call is stubbed. It is not what this script
// verifies, it needs a full agent with authentication, and the point of the
// E2E is the *Judgment* path against the live service. Everything on that path
// is real: the projection, the transport, the real endpoint, the real record.
const kit = await import("../../kit/src/index.ts");
mock.module("../../kit/src/index.ts", () => ({
  ...kit,
  runPiWorker: async ({ prompt }: { prompt: string }) => ({
    text: JSON.stringify({
      kind: "incremental-memory-selection",
      version: 1,
      contextDigest: /Context digest: ([a-f0-9]+)/.exec(prompt)?.[1] ?? "b".repeat(64),
      selected: ["feedback_project_build_command.md"],
      memory: true,
      harness: false,
      agents: false,
      reason: "selector stub",
    }),
    exitCode: 0,
    stderr: "",
  }),
}));

const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "jev-e2e-")));
const agentDir = path.join(root, "agent");
fs.mkdirSync(agentDir, { recursive: true });
process.env.PI_CODING_AGENT_DIR = agentDir;

const cwd = path.join(root, "project");
fs.mkdirSync(cwd, { recursive: true });
const scope = `--${fs.realpathSync(cwd).replace(/^[/\\]/, "").replace(/[/\\:]/g, "-")}--`;
const memoryDir = path.join(agentDir, "memory", scope);
fs.mkdirSync(memoryDir, { recursive: true });

const corpus: Record<string, string> = {
  "feedback_project_build_command.md": "The settled build command for this project is `bun run check`; a failing build is fixed by fixing that command, not by reinstalling dependencies.",
  "feedback_agent_review_style.md": "Review notes in this project are written by the reviewer named in the release notes and are never written by the agent itself.",
  "project_agent_release_channel.md": "Releases for this project ship through the canary channel before the stable channel.",
  "feedback_unrelated_editor_keymap.md": "The user remaps the editor's escape key to a leader sequence and prefers a two-key chord.",
};
const names = Object.keys(corpus);
fs.writeFileSync(
  path.join(memoryDir, "MEMORY.md"),
  `# Memory\n\n${names.map((name) => `- [${name}](${name}) — ${corpus[name].slice(0, 70)}`).join("\n")}\n`,
);
for (const [name, description] of Object.entries(corpus)) {
  fs.writeFileSync(
    path.join(memoryDir, name),
    `---\nname: ${path.basename(name, ".md")}\ndescription: ${description}\ntype: feedback\n---\n\n${description}\n`,
  );
}

const message = (role: string, text: string) => ({
  type: "message",
  message: { role, content: [{ type: "text", text }] },
});

// A realistic request plus a tool result that must never reach the projection.
const taskSlice = {
  kind: "learning-task-slice" as const,
  version: 1 as const,
  entries: [
    message("user", "The build is failing again after the dependency bump. Fix it and record the channel the fix ships through."),
    message("toolResult", "SENSITIVE_TOOL_OUTPUT_bm91dWdubmVjcmV0X2FueXRoaW5n should never be projected"),
  ],
};

const config = resolveJudgmentConfig({ env: process.env, agentDir });
if (!config.active) {
  console.log(JSON.stringify({ ok: false, reason: config.reason }));
  process.exit(1);
}

const started = Date.now();
const result = await selectIncrementalLearning({
  cwd,
  taskSlice,
  contextDigest: "b".repeat(64),
  outputDir: path.join(root, "out"),
  registeredSkills: [],
});
const elapsedMs = Date.now() - started;

const file = judgmentObservationFile(cwd, agentDir);
const raw = fs.existsSync(file) ? fs.readFileSync(file, "utf-8") : "";
const records = raw.split("\n").filter(Boolean).map((line) => JSON.parse(line));
const wire = raw;

// The second half of the surface: what a decision surface makes of the Memory
// plan's own proposals. Uses the same corpus so the duplicate question has a
// real entry to match against.
const proposals = await observeMemoryProposals({
  cwd,
  contextDigest: "b".repeat(64),
  projection: {
    proposals: [
      { name: "project_build_command.md", kind: "project", classification: "safe",
        content: "For this project, the settled build and verification command is `bun run check`; fix failures by fixing that command rather than reinstalling dependencies.",
        evidence: [{ index: 0, source: "user", quote: "run bun run check", count: 1 }] },
      { name: "project_oneoff_flake.md", kind: "project", classification: "safe",
        content: "On 12 March the integration test timed out exactly once at 90 seconds in CI and passed on rerun.",
        evidence: [{ index: 0, source: "tool", quote: "timed out after 90000ms", count: 1 }] },
      { name: "project_restate_channel.md", kind: "project", classification: "safe",
        content: "This project deploys to the canary channel first and stable afterwards.",
        evidence: [{ index: 0, source: "user", quote: "ship canary first", count: 1 }] },
    ],
    memories: Object.entries(corpus).map(([name, description]) => ({ name, type: "feedback", description })),
    selected: ["project_agent_release_channel.md"],
  },
});

console.log(
  JSON.stringify(
    {
      proposals: {
        judged: proposals.judged,
        outcome: proposals.outcome,
        proposed: proposals.proposed,
        kept: proposals.kept,
        duplicates: proposals.duplicates,
        durability: Object.fromEntries(Object.entries(proposals.values).filter(([id]) => id.startsWith("durable::"))),
        generality: Object.fromEntries(Object.entries(proposals.values).filter(([id]) => id.startsWith("general::"))),
        confidence: proposals.confidences,
      },
      ok: result.outcome === "selected",
      outcome: result.outcome,
      error: result.error ?? null,
      selectorSelected: result.selection?.selected ?? null,
      judgmentSummary: result.judgment ?? null,
      elapsedMs,
      observationFile: file,
      underPrivateRoot: file.startsWith(fs.realpathSync(agentDir)),
      publicMirror: fs.existsSync(path.join(cwd, ".memory", "judgment-observations.jsonl")),
      recordCount: records.length,
      record: records[0] ?? null,
      leakChecks: {
        carriesUserRequestText: wire.includes("dependency bump"),
        carriesToolOutput: wire.includes("SENSITIVE_TOOL_OUTPUT"),
        carriesApiKey: wire.includes(String(process.env.TYPESAFE_API_KEY ?? "@@none@@")),
        carriesMemoryFilenameAsAnswerKey: Object.keys(records[0]?.values ?? {}).some((key) => key.endsWith(".md")),
      },
      report: promotionReport(cwd, agentDir),
    },
    null,
    1,
  ),
);
fs.rmSync(root, { recursive: true, force: true });
