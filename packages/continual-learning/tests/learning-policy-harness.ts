import { mock } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { EventEmitter } from "node:events";
import { execFileSync } from "node:child_process";

const root = fs.mkdtempSync(path.join(os.tmpdir(), "learning-policy-"));
const cwd = path.join(root, "project");
const agent = path.join(root, "agent");
process.env.PI_CODING_AGENT_DIR = agent;
fs.mkdirSync(cwd); fs.mkdirSync(path.join(agent, "memory"), { recursive: true });
execFileSync("git", ["init", "-q", cwd]);
const scenario = process.argv[2];
const isHarness = scenario.startsWith("harness-");
const isAgents = scenario.startsWith("agents-");
const isManual = scenario.startsWith("manual-");
const policies = { memory: scenario === "all-off" || isHarness || isAgents ? "off" : scenario === "memory-apply" ? "apply" : "propose", harness: isHarness ? scenario === "harness-rejected" ? "apply" : "propose" : "off", agents: isAgents ? scenario === "agents-propose" ? "propose" : "apply" : "off" };
fs.writeFileSync(path.join(agent, "memory", "settings.json"), JSON.stringify({ autoMemory: true, automaticPhases: policies }));
const quote = isAgents ? "Confirmed: the AGENTS.md workflow is wrong. Use pnpm test for this project." : isHarness ? "Never run the retired compiler." : scenario === "manual-constraint" ? "Never run the retired compiler." : isManual ? "Fix the failing build." : "I prefer concise progress updates.";
const oldAgents = "- Run tests with npm test\n";
if (isAgents) fs.writeFileSync(path.join(cwd,"AGENTS.md"),oldAgents);
const kit = await import("../../kit/src/index.ts");
let selectors = 0;
const planners: string[] = [];
const plannerSystemInstructions: boolean[] = [];
mock.module("../../kit/src/index.ts", () => ({
  ...kit,
  resolvePiCli: () => ({ command: process.execPath, args: [] }),
  runPiWorker: async ({ prompt }: { prompt: string }) => {
    selectors += 1;
    return { exitCode: 0, stderr: "", text: JSON.stringify({
      kind: "incremental-memory-selection", version: 1,
      contextDigest: /Context digest: ([a-f0-9]+)/.exec(prompt)![1], selected: [],
      // Request every phase to prove policy masks override the selector. Manual
      // scenarios instead decline every phase after reviewing the slice.
      memory: !isManual, harness: !isManual, agents: !isManual,
      reason: isManual ? "Self-contained fix with no durable evidence for review." : "fixture routing",
    }) };
  },
  spawnPiChild: (_command: string, args: string[]) => {
    const systemIndex = args.indexOf("--append-system-prompt");
    plannerSystemInstructions.push(systemIndex >= 0 && args[systemIndex + 1].includes("untrusted evidence"));
    const taskFile = args.find(arg => arg.startsWith("@"))!.slice(1);
    const manifest = JSON.parse(fs.readFileSync(path.join(path.dirname(taskFile), "manifest.json"), "utf8"));
    const harness = taskFile.endsWith("harness-task.md");
    const agents = taskFile.endsWith("agents-task.md");
    planners.push(agents ? "agents" : harness ? "harness" : "memory");
    const identity = { version: 1, schemaVersion: 1, runId: manifest.runId, scopeKey: manifest.scopeKey, scopeDigest: manifest.scopeDigest, artifactHash: manifest.snapshotDigest, snapshotDigest: manifest.snapshotDigest };
    const plan = isManual ? {
      ...identity, kind: harness ? "harness-consolidation-plan" : "incremental-memory-plan", operations: [],
      ...(harness ? {} : { newMemories: [] }),
    } : agents ? {
      ...identity, kind: "agents-md-consolidation-plan",
      operations: [{ op: scenario === "agents-extraction" ? "extractUnit" : "rewriteUnit", oldText: oldAgents.trim(),
        ...(scenario === "agents-extraction" ? {extraction:{target:"memory",memoryName:"test-command.md",description:"Project test command",type:"project",classification:"safe"},rationale:"Useful only during testing"} : {newText:"- Run tests with pnpm test"}),
        evidence:[{kind:"wrong",quote,entryIndex:0,occurrences:1}] }],
    } : harness ? {
      ...identity, kind: "harness-consolidation-plan",
      operations: [{ op: "addRule", rule: {id:"retired",bash:"^retired-compiler\\s",action:"block",message:"Use the supported compiler."}, cases: {positive:[{bash:"retired-compiler build",expected:"block"}],negative:[{bash:"pnpm test"}]}}],
      evidence: [{index:0,source:"user",quote,count:1}],
    } : {
      ...identity, kind: "incremental-memory-plan", operations: [], newMemories: [{
        name: "concise.md", kind: "preference", classification: "private",
        content: "---\nname: concise\ndescription: For progress updates, keep them concise\ntype: feedback\n---\nPrefer concise progress updates.\n",
        evidence: [{index:0,quote}],
      }],
    };
    const child = Object.assign(new EventEmitter(), { stdout: new EventEmitter(), stderr: new EventEmitter(), killed: false, exitCode: null as number | null, signalCode: null });
    queueMicrotask(() => {
      child.stdout.emit("data", Buffer.from(JSON.stringify({type:"message_end",message:{role:"assistant",content:[{type:"text",text:JSON.stringify(plan)}]}}) + "\n"));
      child.exitCode = 0; child.emit("close", 0);
    });
    return child;
  },
}));
if (scenario === "harness-rejected") {
  const consolidation = await import("../extensions/harness-consolidation.ts");
  mock.module("../extensions/harness-consolidation.ts", () => ({ ...consolidation,
    applyHarnessConsolidationPlan: async () => ({outcome:"rejected",operations:1,error:'Rule already belongs to a manual declaration'}),
  }));
}
try {
  const { default: register, resolveMemoryPaths } = await import("../extensions/inject-memory.ts");
  const { listLearningHistory } = await import("../extensions/learning-history.ts");
  const hooks = new Map();
  const commands = new Map<string, (args: string, ctx: unknown) => Promise<void> | void>();
  const notices: string[] = [];
  register({ on: (name, fn) => hooks.set(name, [...(hooks.get(name) ?? []), fn]),
    registerCommand: (name, definition) => commands.set(name, definition.handler),
    sendMessage: () => {}, appendEntry: () => {}, getCommands: () => [],
    exec: async () => ({ stdout: "", stderr: "", code: 0 }) } as unknown as Parameters<typeof register>[0]);
  const tool = (content: string, extra: Record<string, unknown> = {}) => ({ message: { role: "toolResult", toolName: "bash", content, ...extra } });
  // Repository text that merely mentions policies, harness files, or guardrail
  // words plus one verified recovery: signals a manual run must not treat as
  // durable evidence on their own.
  const noise = [tool('grep -n "policy" extensions/harness-consolidation.ts'), tool('error: bad runtime version', { isError: true }), tool('Changed the runtime; build succeeded.')];
  const marker = { type: "custom", customType: "harness-event", data: { kind: "policy-matched", action: "block" } };
  const entries = scenario === "manual-harness-marker" ? [{ message: { role: "user", content: quote } }, ...noise, marker]
    : isManual ? [{ message: { role: "user", content: quote } }, ...noise]
      : [{ message: { role: "user", content: quote } }];
  const ctx = {cwd,mode:"json",hasUI:false,ui:{notify:(text:string)=>notices.push(text),setWidget:()=>{}},sessionManager:{getBranch:()=>entries,buildContextEntries:()=>entries}};
  const runHook = async (name: string, event: unknown): Promise<void> => { for (const fn of hooks.get(name) ?? []) await fn(event, ctx); };
  await runHook("session_start", {});
  await runHook("input", { source: "interactive" });
  if (isManual) await commands.get("consolidate")!("", ctx);
  else await runHook("agent_settled", {});
  await runHook("session_shutdown", {});
  const paths = resolveMemoryPaths(cwd);
  const history = await listLearningHistory(cwd);
  const receiptOf = (file: string) => { try { return JSON.parse(fs.readFileSync(file, "utf8")) } catch { return undefined } };
  const runs = (fs.existsSync(paths.runsDir) ? fs.readdirSync(paths.runsDir).filter(name => name.startsWith("run_")) : []).map(dir => ({
    dir, files: fs.readdirSync(path.join(paths.runsDir, dir)).sort(),
    receipt: receiptOf(path.join(paths.runsDir, dir, "learning-pipeline-receipt.json")),
  }));
  console.log(JSON.stringify({ selectors,planners,plannerSystemInstructions,notices,history:history.map(record=>({phase:record.phase,status:record.status,changes:record.changes})),
    privateFiles: fs.existsSync(paths.harnessDir) ? fs.readdirSync(paths.harnessDir) : [],
    publicFiles: fs.existsSync(paths.publicDir!) ? fs.readdirSync(paths.publicDir!) : [],
    runs, registryReceipt: receiptOf(path.join(paths.runsDir, "learning-pipeline-receipt.json")),
    harnessExists:fs.existsSync(path.join(cwd,".pi","harness.json")), agentsUnchanged: !isAgents || fs.readFileSync(path.join(cwd,"AGENTS.md"),"utf8") === oldAgents, lock:fs.existsSync(paths.lockFile),
  }));
} finally { fs.rmSync(root,{recursive:true,force:true}); }
