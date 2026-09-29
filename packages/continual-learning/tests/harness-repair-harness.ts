/**
 * Harness planner repair harness.
 *
 * The planner child is faked through the package's established `mock.module`
 * seam so the sequence of plans it emits is exact. Three live runs of the real
 * pipeline failed on three different planner defects — a missing plan, a
 * negative case that matched its own rule, and a case list of strings instead
 * of objects — which is a recoverable authoring mistake three times over rather
 * than random noise.
 */
import { mock } from "bun:test";
import { EventEmitter } from "node:events";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const scenario = process.argv[2] ?? "repaired";
const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "jev-harness-repair-")));
const rawAgent = path.join(root, "agent");
fs.mkdirSync(rawAgent, { recursive: true });
const agentDir = fs.realpathSync(rawAgent);
process.env.PI_CODING_AGENT_DIR = agentDir;

const cwd = path.join(root, "project");
fs.mkdirSync(cwd, { recursive: true });
fs.writeFileSync(
  path.join(cwd, ".pi-placeholder"),
  "",
);
fs.mkdirSync(path.join(cwd, ".pi"), { recursive: true });

const QUOTE = "Never run the retired compiler through bash";
/** The run identity is generated inside the run, so the child recovers it from
 *  the bound task file the way the real planner reads the same protocol. */
const identityFrom = (text: string) => ({
  runId: /`runId`: `([^`]+)`/.exec(text)?.[1] ?? "",
  scopeDigest: /`scopeDigest`: `([^`]+)`/.exec(text)?.[1] ?? "",
  artifactHash: /`artifactHash`: `([^`]+)`/.exec(text)?.[1] ?? "",
});

/** A negative case that matches the rule it belongs to: the planner's own
 *  self-contradiction, which validation must reject. */
const brokenPlan = (ids: ReturnType<typeof identity>) => ({
  kind: "harness-consolidation-plan",
  ...ids,
  operations: [
    {
      op: "addRule",
      rule: { id: "no-retired-compiler", bash: "^retired-compiler ", action: "block", message: "Use the current compiler." },
      cases: {
        positive: [{ bash: "retired-compiler build", expected: "block" }],
        negative: [{ bash: "retired-compiler build" }],
      },
    },
  ],
  evidence: [{ index: 0, source: "user", quote: QUOTE, count: 1 }],
});

const goodPlan = (ids: ReturnType<typeof identity>) => ({
  kind: "harness-consolidation-plan",
  ...ids,
  operations: [
    {
      op: "addRule",
      rule: { id: "no-retired-compiler", bash: "^retired-compiler ", action: "block", message: "Use the current compiler." },
      cases: {
        positive: [{ bash: "retired-compiler build", expected: "block" }],
        negative: [{ bash: "printf safe" }],
      },
    },
  ],
  evidence: [{ index: 0, source: "user", quote: QUOTE, count: 1 }],
});

const jsonlPlan = (plan: unknown, ids: ReturnType<typeof identity>) =>
  [
    JSON.stringify({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "Working on it." }] } }),
    JSON.stringify({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: JSON.stringify({ ...plan, ...ids }) }] } }),
  ].join("\n");

let spawned = 0;
let emitted: string[] = [];
let repairSeen = 0;
const taskFiles: string[] = [];

const kit = await import("../../kit/src/index.ts");
mock.module("../../kit/src/index.ts", () => ({
  ...kit,
  spawnPiChild: (_command: string, args: string[], options: { cwd: string }) => {
    spawned += 1;
    const taskFile = args.find((arg) => arg.startsWith("@"));
    taskFiles.push(taskFile ?? "");
    try {
      if (fs.readFileSync(taskFile!.slice(1), "utf8").includes("repair ONE rejected harness consolidation plan")) repairSeen += 1;
    } catch { /* the run directory may already be gone */ }
    const child = new EventEmitter() as EventEmitter & Record<string, unknown>;
    const stdout = new EventEmitter();
    const stderr = new EventEmitter();
    child.stdout = stdout;
    child.stderr = stderr;
    child.kill = () => true;
    child.unref = () => child;
    setTimeout(() => {
      const text = fs.existsSync(taskFile!.slice(1))
        ? fs.readFileSync(taskFile!.slice(1), "utf8")
        : "";
      const identity = identityFrom(text);
      const repair = text.includes("repair ONE rejected harness consolidation plan");
      const plan = !repair || scenario === "repair-also-fails" || scenario === "never-repairs" ? brokenPlan(identity) : goodPlan(identity);
      const body = jsonlPlan(plan, identity);
      emitted.push(body);
      stdout.emit("data", Buffer.from(`${body}\n`, "utf8"));
      stderr.emit("data", Buffer.from("", "utf8"));
      child.emit("close", 0);
    }, 1);
    return child;
  },
}));

const { planHarnessConsolidationPhase } = await import("../extensions/harness-consolidation.ts");

try {
  // The plan must carry the run's real identity, which is only known after the
  // consolidation run exists; capture it from the first task file the child saw.
  const result = await planHarnessConsolidationPhase(
    {
      cwd,
      mode: "json",
      hasUI: false,
      ui: { notify: () => {}, setWidget: () => {} },
      sessionManager: {
        getBranch: () => [{ message: { role: "user", content: QUOTE } }],
        buildContextEntries: () => [{ message: { role: "user", content: QUOTE } }],
      },
    } as never,
    { pkgDir: path.resolve("packages/continual-learning"), cwd, reason: "repaired", availableSkills: [] } as never,
  );

  console.log(
    JSON.stringify({
      scenario,
      spawned,
      ok: result.ok,
      detail: result.ok ? null : result.detail,
      operations: result.ok && Array.isArray(result.value.plan.operations) ? result.value.plan.operations.length : 0,
      repairRequested: repairSeen > 0,
      repairSeen,
      identitySeen: identityFrom((() => { try { return fs.readFileSync(taskFiles[0].slice(1), "utf8"); } catch { return ""; } })()),
      emittedHeads: emitted.map((b) => b.slice(0, 260)),
      firstTaskHead: (() => { try { return fs.readFileSync(taskFiles[0].slice(1), "utf8").slice(0, 400); } catch { return ""; } })(),
    }),
  );
} finally {
  fs.rmSync(root, { recursive: true, force: true });
}
