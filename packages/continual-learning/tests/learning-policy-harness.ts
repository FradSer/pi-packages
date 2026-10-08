import {createHash} from "node:crypto";
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
const isEmptyFull = scenario === "empty-full";
const isHarness = scenario.startsWith("harness-");
const isAgents = scenario.startsWith("agents-");
const isManual = scenario.startsWith("manual-");
const isRemember = scenario.startsWith("remember-");
const isModelFreeze = scenario === "model-freeze" || scenario === "session-model-freeze";
if (isModelFreeze || scenario === "remember-declined") {
  // These cases specifically exercise model selection, not empty-index routing.
  fs.mkdirSync(path.join(cwd, ".memory"));
  fs.writeFileSync(path.join(cwd, ".memory", "known.md"), "---\nname: known\ndescription: Existing project knowledge\ntype: project\n---\nExisting knowledge.\n");
}
const policies = { memory: isModelFreeze ? "propose" : scenario === "all-off" || isHarness || isAgents ? "off" : scenario === "memory-apply" ? "apply" : "propose", harness: isModelFreeze ? "propose" : isHarness ? scenario === "harness-rejected" ? "apply" : "propose" : "off", agents: isModelFreeze ? "propose" : isAgents ? scenario === "agents-propose" ? "propose" : "apply" : "off" };
fs.writeFileSync(path.join(agent, "memory", "settings.json"), JSON.stringify({ autoMemory: !isRemember, automaticPhases: isRemember ? {memory:"off",harness:"off",agents:"off"} : policies }));
if (isModelFreeze) fs.writeFileSync(path.join(agent, "memory.json"), JSON.stringify(scenario === "model-freeze" ? { provider: "old", model: "one" } : {}));
const quote = scenario === "remember-subset" ? "Remember: this project uses pnpm. Its license is MIT. A cache timeout cleared on retry." : scenario === "semantic-opportunity" ? "Package management happens through pnpm." : isRemember ? scenario === "remember-secret" ? "Remember my API key: sk-test-secret" : scenario === "remember-shared" ? "Remember that the project build convention is CL_MANUAL_SHARED." : "Remember that I prefer concise progress updates." : isAgents ? "Confirmed: the AGENTS.md workflow is wrong. Use pnpm test for this project." : isHarness ? "Never run the retired compiler." : scenario === "manual-constraint" ? "Never run the retired compiler." : isManual ? "Fix the failing build." : "I prefer concise progress updates.";
const oldAgents = "- Run tests with npm test\n";
if (isAgents || isModelFreeze || isRemember) fs.writeFileSync(path.join(cwd,"AGENTS.md"),oldAgents);
// Attribution and pluggability seam: install the absence before any extension
// module loads, so a static SDK import fails exactly as a missing dependency.
if (process.env.CL_ABSENT_TYPESAFE_SDK === "1") {
  mock.module("@typesafe-ai/sdk", () => { throw new Error("Cannot find module '@typesafe-ai/sdk'"); });
}
const kit = await import("../../kit/src/index.ts");
let selectors = 0;
let semanticRepairs = 0;
let structuralContextReceived = false;
let receivedFailureHints = false;
let totalRepairs = 0;
let cancellation: Promise<void> | undefined;
let cancelRun: (() => Promise<void>) | undefined;
const fixtureReason = process.env.CL_JEV_FIXTURE;
const tamperFrozen = (dossier = false, runId?: string): void => {
  const file = fs.readdirSync(path.join(agent, "memory", "runs"), {recursive:true}).find(name => String(name).endsWith(dossier ? "incremental-learning-dossier.json" : "snapshot.json") && (dossier || (runId ? String(name).includes(runId) : fs.existsSync(path.join(agent, "memory", "runs", path.dirname(String(name)), "plan.json")))));
  if (!file) throw new Error("Missing frozen fixture file");
  fs.appendFileSync(path.join(agent, "memory", "runs", String(file)), " ");
};
const planners: string[] = [];
const plannerSystemInstructions: boolean[] = [];
const modelCalls: string[] = [];
let requestCaptured = false;
mock.module("../../kit/src/index.ts", () => ({
  ...kit,
  resolvePiCli: () => ({ command: process.execPath, args: [] }),
  runPiWorker: async ({ prompt, model }: { prompt: string; model?: string }) => {
    if (prompt.startsWith("Task: repair one rejected incremental Memory delta plan.")) {
      totalRepairs += 1;
      const payload = JSON.parse(prompt.split("\n").at(-1)!);
      if (payload.semanticContext && !prompt.includes("existing structural correction slot")) { semanticRepairs += 1; receivedFailureHints = payload.errors.some((error: string) => error.includes("Candidate failures: 0:support:uncertain")); }
      else { selectors += 1; structuralContextReceived = !!payload.semanticContext?.frozenEvidence && Array.isArray(payload.semanticContext?.existingMemories); }
      const repaired = structuredClone(payload.rejectedPlan);
      if (fixtureReason?.startsWith("structural-")) repaired.newMemories[0].kind = "project";
      if (fixtureReason === "repair-held") repaired.newMemories[0].content += "A correction proposal.\n";
      if (fixtureReason === "tamper-repair") tamperFrozen();
      if (fixtureReason === "structural-tamper-snapshot") tamperFrozen(false, payload.identity.runId);
      if (fixtureReason === "structural-tamper-dossier") tamperFrozen(true);
      if (fixtureReason === "repair-cancel") {
        cancellation = cancelRun!();
        return {exitCode:0,stderr:"",text:"",cancelled:true};
      }
      if (process.env.CL_JEV_FIXTURE === "repair-private") repaired.newMemories[0].classification = "private";
      return { exitCode: 0, stderr: "", text: JSON.stringify(repaired), usage: {input:10,output:2,cacheRead:0,cacheWrite:0,totalTokens:12,cost:.01} };
    }
    selectors += 1;
    if (isRemember) requestCaptured = prompt.includes(quote);
    if (isModelFreeze) {
      modelCalls.push(`selector:${model ?? "default"}`);
      if (selectors === 1) await (globalThis as { changeMemoryModel?: () => Promise<void> }).changeMemoryModel?.();
    }
    return { exitCode: 0, stderr: "", text: JSON.stringify({
      kind: "incremental-memory-selection", version: 1,
      contextDigest: /Context digest: ([a-f0-9]+)/.exec(prompt)![1], selected: [],
      // Request every phase to prove policy masks override the selector. Manual
      // scenarios instead decline every phase after reviewing the slice.
      memory: !isManual && scenario !== "remember-declined", harness: !isManual, agents: !isManual,
      reason: isManual ? "Self-contained fix with no durable evidence for review." : "fixture routing",
    }) };
  },
  spawnPiChild: (_command: string, args: string[]) => {
    if (isModelFreeze) {
      const modelIndex = args.indexOf("--model");
      modelCalls.push(`planner:${modelIndex >= 0 ? args[modelIndex + 1] : "default"}`);
    }
    const systemIndex = args.indexOf("--append-system-prompt");
    plannerSystemInstructions.push(systemIndex >= 0 && args[systemIndex + 1].includes("untrusted evidence"));
    const taskFile = args.find(arg => arg.startsWith("@"))!.slice(1);
    const manifest = JSON.parse(fs.readFileSync(path.join(path.dirname(taskFile), "manifest.json"), "utf8"));
    const harness = taskFile.endsWith("harness-task.md") || taskFile.endsWith("harness-repair.md");
    const harnessRepair = taskFile.endsWith("harness-repair.md");
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
        name: "concise.md", kind: scenario === "remember-shared" ? "project" : "preference", classification: scenario === "remember-shared" ? "safe" : "private",
        content: scenario === "remember-shared" ? "---\nname: concise\ndescription: Project build convention\ntype: project\n---\nThe project build convention is CL_MANUAL_SHARED.\n" : "---\nname: concise\ndescription: For progress updates, keep them concise\ntype: feedback\n---\nPrefer concise progress updates.\n",
        evidence: [{index:0,quote:scenario === "remember-invalid" ? "No such request evidence" : quote}],
      }],
    };
    if (scenario === "remember-subset" && !harness && !agents) {
      const facts = [["tools.md", "This project uses pnpm."], ["cache.md", "Cache service is permanently unavailable."], ["license.md", "Its license is MIT."]];
      (plan as {newMemories: unknown[]}).newMemories = facts.map(([name, body]) => ({name, kind: "project", classification: "safe",
        content: `---\nname: ${name.slice(0,-3)}\ndescription: ${body}\ntype: project\n---\n${body}\n`, evidence: [{index: 0, quote}]}));
    }
    if (fixtureReason?.startsWith("structural-") && !harness && !agents) (plan as {newMemories: Array<{kind:string}>}).newMemories[0].kind = "project-fact";
    const child = Object.assign(new EventEmitter(), { stdout: new EventEmitter(), stderr: new EventEmitter(), killed: false, exitCode: null as number | null, signalCode: null });
    queueMicrotask(() => {
      // A planner that reports a model error without any plan. The attribution seam
      // must keep this failure from stopping the phase before the semantic judge.
      if (scenario === "planner-model-error" && !harness && !agents) {
        child.stdout.emit("data", Buffer.from(JSON.stringify({type:"message_end",message:{role:"assistant",stopReason:"error",errorMessage:"Connection error.",content:[]}}) + "\n"));
        child.exitCode = 0; child.emit("close", 0);
        return;
      }
      const tracksRepair = scenario === "harness-repair-cost" && harness;
      const text = tracksRepair && !harnessRepair ? "The planner returned prose instead of a plan." : JSON.stringify(plan);
      const usage = tracksRepair ? { input: harnessRepair ? 20 : 10, output: harnessRepair ? 4 : 2, cacheRead: harnessRepair ? 6 : 3, cacheWrite: 0, totalTokens: harnessRepair ? 30 : 15, cost: {total: harnessRepair ? 0.02 : 0.01} } : undefined;
      child.stdout.emit("data", Buffer.from(JSON.stringify({type:"message_end",message:{role:"assistant",content:[{type:"text",text}],...(usage ? {usage} : {})}}) + "\n"));
      child.exitCode = 0; child.emit("close", 0);
    });
    return child;
  },
}));
let jevValidations: string[] = [];
let relationValidations = 0;
const fixtureDigest = (value: unknown) => createHash("sha256").update(JSON.stringify(value)).digest("hex");
if (process.env.CL_JEV_FIXTURE) {
  const jevModule = await import("../extensions/jev-learning.ts");
  const reason = process.env.CL_JEV_FIXTURE;
  mock.module("../extensions/jev-learning.ts", () => ({ ...jevModule,
    createJevJudge: () => ({ enabled: true, selectionEnabled: true,
      independentMemoryApplicationEnabled: reason.startsWith("subset-") && reason !== "subset-disabled",
      composedMemoryApplicationEnabled: reason === "subset-composed",
      reviewMemoryRelations: async (evidence: unknown, candidates: unknown[], existing: unknown[], review: {evidenceDigest:string;existingDigest:string;candidatesDigest:string;model:string}) => {
        relationValidations++;
        const telemetry = {stage:"memory",status:"decided",reason:"supported",durationMs:1,model:"jev-1.13.0",inputTokens:15,outputTokens:3};
        if (reason === "subset-unavailable") return {telemetry:{...telemetry,status:"propose",reason:"unavailable"}};
        const label = reason === "subset-uncertain" ? "unclear" : "independent";
        const pairs=[];
        for(let a=0;a<candidates.length;a++)for(let b=a+1;b<candidates.length;b++)pairs.push({a,b,
          candidateDigests:[fixtureDigest(candidates[a]),fixtureDigest(candidates[b])],status:label === "unclear" ? "uncertain" : "decided",relation:label,
          answer:{type:"choice",choice:label,confidence:1,probabilities:Object.fromEntries(["independent","duplicate","conflict","dependent","unclear"].map(k=>[k,k===label?1:0]))}});
        if(reason.startsWith("subset-composed"))for(const pair of pairs)if(pair.a===1||pair.b===1){
          pair.relation="unclear";pair.status="uncertain";pair.answer.choice="unclear";
          pair.answer.probabilities=Object.fromEntries(["independent","duplicate","conflict","dependent","unclear"].map(k=>[k,k==="unclear"?1:0]));
        }
        const readiness=reason.startsWith("subset-composed")?{version:1,purpose:"diagnostic-only",complete:true,
          evidenceDigest:fixtureDigest(evidence),existingDigest:fixtureDigest(existing),candidatesDigest:fixtureDigest(candidates),model:review.model,
          candidates:candidates.map((candidate,index)=>({index,candidateDigest:fixtureDigest(candidate),answer:{type:"choice",choice:"selfContained",confidence:1,
            probabilities:{selfContained:1,needsOther:0,unresolved:0}}}))}:undefined;
        return {telemetry,...(readiness?{readiness,readinessTelemetry:{...telemetry,strategy:"standalone-memory"}}:{}),
          review:{version:1,purpose:"diagnostic-only",complete:true,evidenceDigest:fixtureDigest(evidence),existingDigest:fixtureDigest(existing),candidatesDigest:fixtureDigest(candidates),model:review.model,pairs}};
      },
      select: async () => ({ selection: reason === "discover" ? {memory:true,harness:false,selected:[]} : null, telemetry: {stage:"selection",status:"fallback",reason:"unavailable",durationMs:1} }),
      validate: async (stage: string, evidence: unknown, candidates: unknown[], existing: unknown[]) => {
        if(reason.startsWith("subset-")) {
          jevValidations.push(stage);
          const checks=(i:number)=>[`supported_${i}`,`supported_description_${i}`, ...(existing.length?[`relation_${i}`,`relation_description_${i}`]:[]),`counter_${i}_0`,`counter_description_${i}_0`];
          return {decision:"propose",telemetry:{stage,status:"propose",reason:"unsupported",durationMs:2,model:"jev-1.13.0",inputTokens:10,outputTokens:2},
            candidateReview:{version:1,purpose:"diagnostic-only",complete:true,sameBatchIndependenceReviewed:false,evidenceDigest:fixtureDigest(evidence),existingDigest:fixtureDigest(existing),candidatesDigest:fixtureDigest(candidates),model:"jev-1.13.0",
              candidates:candidates.map((c,index)=>({index,candidateDigest:fixtureDigest(c),outcome:index===1?"held":"passed",passedChecks:checks(index).filter(k=>index!==1||k!==`supported_${index}`),heldChecks:index===1?[`supported_${index}`]:[]}))}};
        }
        jevValidations.push(stage);
        if (reason === "tamper-first" || reason === "tamper-dossier") tamperFrozen(reason === "tamper-dossier");
        if (reason === "tamper-second" && jevValidations.length === 2) tamperFrozen();
        const allowed = reason === "supported" || reason === "tamper-first" || reason === "tamper-dossier" || reason === "tamper-queue" || (reason === "repair-supported" || reason === "tamper-second") && jevValidations.length === 2;
        const judgment = (reason.startsWith("repair-") || reason === "structural-held" || reason === "tamper-second" || reason === "tamper-repair") ? allowed ? "supported" : "uncertain" : reason;
        return { decision: allowed ? "allow" : "propose",
          telemetry: {stage,status:allowed ? "decided" : "propose",reason:judgment,durationMs:2,model:"jev-1.13.0",inputTokens:10,outputTokens:2,...(!allowed ? {candidateIndex:0,dimension:"support",candidateFailures:[{candidateIndex:0,dimension:"support",reason:"uncertain"}]} : {})} };
      },
    }),
  }));
}
const snapshotRootFiles = (dirs: readonly string[]) => dirs.map(dir => fs.existsSync(dir)
  ? fs.readdirSync(dir).sort().map(name => [name,fixtureDigest(fs.readFileSync(path.join(dir,name)).toString("base64"))]) : []);
let transactionMemoryFilesBefore: string | undefined;
let transactionHistoryIdsBefore: Set<string> | undefined;
let finalVerificationObservedWrites = false;
if (fixtureReason === "subset-final-validator-fails") {
  const consolidation = await import("../extensions/consolidation-run.ts");
  const original = consolidation.writeConsolidationReceipt;
  mock.module("../extensions/consolidation-run.ts", () => ({...consolidation,
    writeConsolidationReceipt: async (...args: Parameters<typeof original>) => {
      if (args[2] === "pre") {
        transactionMemoryFilesBefore = JSON.stringify(snapshotRootFiles([args[0].manifest.harnessDir,args[0].manifest.publicDir!]));
        const {listLearningHistory} = await import("../extensions/learning-history.ts");
        transactionHistoryIdsBefore = new Set((await listLearningHistory(cwd)).map(record=>record.id));
      }
      const file = await original(...args);
      if (args[2] !== "pre") {
        finalVerificationObservedWrites = fs.existsSync(path.join(cwd, ".memory", "tools.md"));
        const receipt = JSON.parse(fs.readFileSync(file, "utf8"));
        fs.writeFileSync(file, JSON.stringify({...receipt,planDigest:"0".repeat(64)}));
      }
      return file;
    },
  }));
}
if (fixtureReason === "subset-preservation-fails") {
  const history = await import("../extensions/learning-history.ts");
  mock.module("../extensions/learning-history.ts", () => ({...history,recordLearningProposal:async()=>{throw Error("Proposal preservation unavailable");}}));
}
if (fixtureReason === "tamper-queue" || fixtureReason === "subset-tamper-queue") {
  const history = await import("../extensions/learning-history.ts");
  const originalRecordMutation = history.recordLearningMutation;
  mock.module("../extensions/learning-history.ts", () => ({...history,
    recordLearningMutation: (project: string, phase: "memory", files: string[], mutate: () => Promise<unknown>, plan: unknown) => originalRecordMutation(project, phase, files, async () => {if (jevValidations.length) tamperFrozen();return mutate();}, plan),
  }));
}
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
    registerEntryRenderer: () => {},
    exec: async () => ({ stdout: "", stderr: "", code: 0 }) } as unknown as Parameters<typeof register>[0]);
  const tool = (content: string, extra: Record<string, unknown> = {}) => ({ message: { role: "toolResult", toolName: "bash", content, ...extra } });
  // Repository text that merely mentions policies, harness files, or guardrail
  // words plus one verified recovery: signals a manual run must not treat as
  // durable evidence on their own.
  const noise = [tool('grep -n "policy" extensions/harness-consolidation.ts'), tool('error: bad runtime version', { isError: true }), tool('Changed the runtime; build succeeded.')];
  const marker = { type: "custom", customType: "harness-event", data: { kind: "policy-matched", action: "block" } };
  const entries = isEmptyFull ? [{ type: "model_change", provider: "session", modelId: "active" }, { type: "thinking_level_change", thinkingLevel: "off" }]
    : scenario === "manual-harness-marker" ? [{ message: { role: "user", content: quote } }, ...noise, marker]
    : isManual ? [{ message: { role: "user", content: quote } }, ...noise]
      : [{ message: { role: "user", content: quote } }];
  const ctx = {cwd,mode:"json",hasUI:false,model:{provider:"session",id:"active"},ui:{notify:(text:string)=>notices.push(text),setWidget:()=>{}},modelRegistry:{getAll:()=>[{provider:"old",id:"one"},{provider:"new",id:"two"}],getAvailable:()=>[]},sessionManager:{getBranch:()=>entries,buildContextEntries:()=>entries}};
  (globalThis as { changeMemoryModel?: () => Promise<void> }).changeMemoryModel = async () => {
    await commands.get("memory")!("model new/two", ctx);
  };
  const runHook = async (name: string, event: unknown): Promise<void> => { for (const fn of hooks.get(name) ?? []) await fn(event, ctx); };
  cancelRun = () => runHook("session_shutdown", {});
  await runHook("session_start", {});
  await runHook("input", { source: "interactive" });
  const snapshotMemoryFiles = () => {
    const memory = resolveMemoryPaths(cwd);
    return snapshotRootFiles([memory.harnessDir,memory.publicDir!]);
  };
  const memoryFilesBefore = snapshotMemoryFiles();
  const historyIdsBefore = new Set((await listLearningHistory(cwd)).map(record=>record.id));
  if (isEmptyFull) await commands.get("consolidate")!("full", ctx);
  else if (isRemember) await commands.get("memory")!(quote, ctx);
  else if (isManual) await commands.get("consolidate")!("", ctx);
  else {
    await runHook("agent_settled", {});
    if (isModelFreeze) {
      await runHook("input", { source: "interactive" });
      await runHook("agent_settled", {});
    }
  }
  await cancellation;
  await runHook("session_shutdown", {});
  const paths = resolveMemoryPaths(cwd);
  const history = await listLearningHistory(cwd);
  const receiptOf = (file: string) => { try { return JSON.parse(fs.readFileSync(file, "utf8")) } catch { return undefined } };
  const {learningSummarySubject} = await import("../extensions/learning-efficiency.ts");
  const savedReceipt = receiptOf(path.join(paths.runsDir, "learning-pipeline-receipt.json"));
  const runs = (fs.existsSync(paths.runsDir) ? fs.readdirSync(paths.runsDir).filter(name => name.startsWith("run_")) : []).map(dir => ({
    dir, files: fs.readdirSync(path.join(paths.runsDir, dir)).sort(),
    receipt: receiptOf(path.join(paths.runsDir, dir, "learning-pipeline-receipt.json")),
    dossier: receiptOf(path.join(paths.runsDir, dir, "incremental-learning-dossier.json")),
  }));
  if (isRemember) requestCaptured = runs.some(run => run.dossier?.taskSlice?.entries[0]?.message?.content === quote);
  console.log(JSON.stringify({ newAppliedHistoryRecords:history.filter(record=>!(transactionHistoryIdsBefore??historyIdsBefore).has(record.id)&&record.status==="applied").length,memoryFilesRestored:(transactionMemoryFilesBefore??JSON.stringify(memoryFilesBefore))===JSON.stringify(snapshotMemoryFiles()),finalVerificationObservedWrites,...(scenario === "remember-subset" && savedReceipt ? {summarySubject:learningSummarySubject(savedReceipt)} : {}),jevValidations,relationValidations,selectors,planners,plannerSystemInstructions,modelCalls,requestCaptured,notices,history:history.map(record=>({phase:record.phase,status:record.status,changes:record.changes,...(scenario === "remember-subset" ? {proposal:record.proposal} : {})})),
    privateFiles: fs.existsSync(paths.harnessDir) ? fs.readdirSync(paths.harnessDir) : [],
    publicFiles: fs.existsSync(paths.publicDir!) ? fs.readdirSync(paths.publicDir!) : [],
    runs, registryReceipt: receiptOf(path.join(paths.runsDir, "learning-pipeline-receipt.json")),
    semanticRepairs, totalRepairs, receivedFailureHints, structuralContextReceived,
    originalProposalRetained: history.some(record => record.status === "proposed" && runs.some(run => JSON.stringify(record.proposal) === JSON.stringify(receiptOf(path.join(paths.runsDir, run.dir, "plan.json"))))),
    memoryMirrored: fs.existsSync(path.join(paths.harnessDir,'concise.md')) && fs.existsSync(path.join(paths.publicDir!,'concise.md')) && fs.readFileSync(path.join(paths.harnessDir,'concise.md')).equals(fs.readFileSync(path.join(paths.publicDir!,'concise.md'))),
    harnessExists:fs.existsSync(path.join(cwd,".pi","harness.json")), agentsUnchanged: !(isAgents || isRemember) || fs.readFileSync(path.join(cwd,"AGENTS.md"),"utf8") === oldAgents, lock:fs.existsSync(paths.lockFile),
  }));
} finally { fs.rmSync(root,{recursive:true,force:true}); }
