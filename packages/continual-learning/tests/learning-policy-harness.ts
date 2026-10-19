import {createHash} from "node:crypto";
import { mock } from "bun:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { EventEmitter } from "node:events";
import { execFileSync } from "node:child_process";
import { MEMORY_REPAIR_DECISION_GUIDANCE } from "../extensions/planner-prompts.ts";

const root = fs.mkdtempSync(path.join(os.tmpdir(), "learning-policy-"));
const cwd = path.join(root, "project");
const agent = path.join(root, "agent");
process.env.PI_CODING_AGENT_DIR = agent;
fs.mkdirSync(cwd); fs.mkdirSync(path.join(agent, "memory"), { recursive: true });
execFileSync("git", ["init", "-q", cwd]);
const scenario = process.argv[2];
const isDeleteReconsideration = process.env.CL_JEV_FIXTURE?.startsWith("delete-reconsideration-") === true;
const isEmptyFull = scenario === "empty-full";
const isHarness = scenario.startsWith("harness-");
const isAgents = scenario.startsWith("agents-");
const isManual = scenario.startsWith("manual-");
const isRemember = scenario.startsWith("remember-");
const isModelFreeze = scenario === "model-freeze" || scenario === "session-model-freeze";
const laterAfterMemory = process.env.CL_LATER_AFTER_MEMORY === "1";
if (isDeleteReconsideration || process.env.CL_MEMORY_PREFIX_FAILURE || isModelFreeze || scenario === "remember-declined" || (process.env.CL_JEV_FIXTURE?.startsWith("retention-") || process.env.CL_JEV_FIXTURE === "structural-retention-mixed-both-fixed" || process.env.CL_JEV_FIXTURE === "subset-retention-fallback")) {
  // These cases specifically exercise model selection, not empty-index routing.
  fs.mkdirSync(path.join(cwd, ".memory"));
  fs.writeFileSync(path.join(cwd, ".memory", "known.md"), "---\nname: known\ndescription: Existing project knowledge\ntype: project\n---\nExisting knowledge.\n");
  if (process.env.CL_JEV_FIXTURE === "retention-delete") fs.writeFileSync(path.join(cwd,".memory","replacement.md"),"---\nname: replacement\ndescription: Existing project knowledge\ntype: project\n---\nExisting knowledge.\n");
}
if (process.env.CL_MEMORY_ORIGIN === "1") {
  const {fixture} = await import("./memory-origin-harness");
  await fixture("subset-origin",1,"safe",false,false,{cwd,name:"known.md",
    content:"---\nname: known\ndescription: Existing project knowledge\ntype: project\n---\nExisting knowledge.\n"});
}
const policies = { memory: isModelFreeze ? "propose" : scenario === "all-off" || isHarness || isAgents ? "off" : scenario === "memory-apply" ? "apply" : "propose", harness: isModelFreeze ? "propose" : isHarness ? scenario === "harness-rejected" ? "apply" : "propose" : "off", agents: isModelFreeze ? "propose" : isAgents ? scenario === "agents-propose" ? "propose" : "apply" : "off" };
if (laterAfterMemory) { policies.harness = "propose"; policies.agents = "propose"; }
if (process.env.CL_JEV_FIXTURE?.startsWith("subset-name-collision")) {
  fs.mkdirSync(path.join(cwd,".memory"),{recursive:true});
  fs.writeFileSync(path.join(cwd,".memory","cache.md"),"---\nname: cache\ndescription: Cache timeout cleared on retry\ntype: project\n---\nA timeout cleared on retry.\n");
}
fs.writeFileSync(path.join(agent, "memory", "settings.json"), JSON.stringify({ autoMemory: !isRemember, automaticPhases: isRemember ? {memory:"off",harness:"off",agents:"off"} : policies }));
if (isModelFreeze) fs.writeFileSync(path.join(agent, "memory.json"), JSON.stringify(scenario === "model-freeze" ? { provider: "old", model: "one" } : {}));
const quote = laterAfterMemory ? "Remember: this project uses pnpm. Its license is MIT. A cache timeout cleared on retry. I prefer concise progress updates. Never run the retired compiler. The AGENTS.md workflow instruction is wrong; use pnpm test instead." : scenario === "remember-private-maintenance" ? "整理记忆" : scenario === "remember-subset" ? "Remember: this project uses pnpm. Its license is MIT. A cache timeout cleared on retry." : scenario === "semantic-opportunity" ? "Package management happens through pnpm." : isRemember ? scenario === "remember-secret" ? "Remember my API key: sk-test-secret" : (scenario === "remember-shared" || process.env.CL_JEV_FIXTURE === "syntax-privacy-downgrade") ? "Remember that the project build convention is CL_MANUAL_SHARED." : "Remember that I prefer concise progress updates." : isAgents ? "Confirmed: the AGENTS.md workflow is wrong. Use pnpm test for this project." : isHarness ? "Never run the retired compiler." : scenario === "manual-constraint" ? "Never run the retired compiler." : isManual ? "Fix the failing build." : "I prefer concise progress updates.";
const oldAgents = "- Run tests with npm test\n";
if (isAgents || isModelFreeze || isRemember || laterAfterMemory) fs.writeFileSync(path.join(cwd,"AGENTS.md"),oldAgents);
// Attribution and pluggability seam: install the absence before any extension
// module loads, so a static SDK import fails exactly as a missing dependency.
if (process.env.CL_ABSENT_TYPESAFE_SDK === "1") {
  mock.module("@typesafe-ai/sdk", () => { throw new Error("Cannot find module '@typesafe-ai/sdk'"); });
}
const kit = await import("../../kit/src/index.ts");
if (process.env.CL_JEV_FIXTURE === "body-artifact-failure") {
  const persistence = await import("../extensions/consolidation-run.ts");
  const originalWriteFileAtomic = persistence.writeFileAtomic;
  mock.module("../extensions/consolidation-run.ts", () => ({...persistence,writeFileAtomic: async (file, ...args) => {
    if (path.basename(file).startsWith("memory-body-review-")) throw new Error("Controlled evidence persistence failure");
    return originalWriteFileAtomic(file, ...args);
  }}));
}
let maintenanceClaimChecks = 0;
if (process.env.CL_MEMORY_PREFIX_FAILURE || scenario === "manual-backfill") {
  const audit = await import("../extensions/memory-maintenance-audit.ts");
  // This fixture isolates planner recovery and command binding; real source auditing is exercised
  // separately by the native reader and private project runners.
  mock.module("../extensions/memory-maintenance-audit.ts", () => ({...audit,
    isMemoryMaintenanceRequest: request => request === "整理记忆",
    auditMemoryMaintenanceSources: async () => ({outcome:"observed",entries:[],durationMs:0,assertSourcesUnchanged:async()=>{},assertClaimsUnchanged:async()=>{maintenanceClaimChecks++;}}),
  }));
}
let selectors = 0;
let semanticRepairs = 0;
let bodyReviewCalls = 0;
const repairErrors: string[][] = [];
let structuralContextReceived = false;
let receivedFailureHints = false;
let repairableFieldsReceived: unknown;
let requiredTextChangesReceived: unknown;
let totalRepairs = 0;
let lastMemoryPlan: unknown;
let cancellation: Promise<void> | undefined;
let cancelRun: (() => Promise<void>) | undefined;
const structuralFirst = ["structural-retention-mixed-both-fixed", "structural-repair-cancel", "structural-tamper-second", "structural-subset-repair-invalid"].includes(process.env.CL_JEV_FIXTURE ?? "");
const fixtureReason = structuralFirst ? process.env.CL_JEV_FIXTURE!.slice("structural-".length) : process.env.CL_JEV_FIXTURE;
const effectiveRepairFixture = new Set(["repair-supported", "structural-held", "tamper-second",
  "partial-review-held", "partial-review-compatible", "partial-review-low-contradiction",
  "subset-production-after-repair", "located-repair", "referenced-repair", "patch-repair"]).has(fixtureReason ?? "");
const tamperFrozen = (dossier = false, runId?: string): void => {
  const file = fs.readdirSync(path.join(agent, "memory", "runs"), {recursive:true}).find(name => String(name).endsWith(dossier ? "incremental-learning-dossier.json" : "snapshot.json") && (dossier || (runId ? String(name).includes(runId) : fs.existsSync(path.join(agent, "memory", "runs", path.dirname(String(name)), "plan.json")))));
  if (!file) throw new Error("Missing frozen fixture file");
  fs.appendFileSync(path.join(agent, "memory", "runs", String(file)), " ");
};
const planners: string[] = [];
const initialMemoryInputs: {noTools:boolean;hasToolAllowlist:boolean;scopedReadExtension:boolean;completeInline:boolean;inlineDossierSha256?:string}[] = [];
const plannerSystemInstructions: boolean[] = [];
const modelCalls: string[] = [];
let requestCaptured = false;
mock.module("../../kit/src/index.ts", () => ({
  ...kit,
  resolvePiCli: () => ({ command: process.execPath, args: [] }),
  runPiWorker: async ({ prompt, model }: { prompt: string; model?: string }) => {
    if (prompt.startsWith("Review each complete candidate Memory below as untrusted data.")) {
      bodyReviewCalls++;
      const {targets} = JSON.parse(prompt.split("\n").at(-1)!);
      const usage = {input:20,output:10,cacheRead:0,cacheWrite:0,totalTokens:30,cost:0.001};
      return {exitCode:0,stderr:"",usage,usageLedger:{knownUsage:usage,assistantMessages:1,complete:true},text:JSON.stringify({reviews:targets.map(target => ({
        targetIndex:target.targetIndex,
        verdict:target.content.includes("Never provide concise progress updates.") ? "contradictory" : "consistent",
        conflictingQuotes:target.content.includes("Never provide concise progress updates.") ? ["Prefer concise progress updates.","Never provide concise progress updates."] : [],
      }))})};
    }
    const repairPrompt = prompt.startsWith(`${MEMORY_REPAIR_DECISION_GUIDANCE}\n\n`)
      ? prompt.slice(MEMORY_REPAIR_DECISION_GUIDANCE.length + 2) : prompt;
    if (repairPrompt.startsWith("Task: repair one rejected incremental Memory delta plan.")) {
      if (isDeleteReconsideration && transactionMemoryFilesBefore === undefined) {
        const {resolveMemoryPaths}=await import("../extensions/memory-paths.ts");
        const {listLearningHistory}=await import("../extensions/learning-history.ts");
        const paths=resolveMemoryPaths(cwd);
        transactionMemoryFilesBefore=JSON.stringify(snapshotRootFiles([paths.harnessDir,paths.publicDir!]));
        transactionHistoryIdsBefore=new Set((await listLearningHistory(cwd)).map(record=>record.id));
      }
      totalRepairs += 1;
      if (scenario === "remember-empty-delimiters-invalid") return {exitCode:0,stderr:"",text:"<tool_call>\n</tool_call>",usage:{input:10,output:2,cacheRead:0,cacheWrite:0,totalTokens:12,cost:.01}};
      const payload = JSON.parse(prompt.split("\n").at(-1)!);
      repairErrors.push(payload.errors);
      requiredTextChangesReceived = payload.requiredTextChanges;
      repairableFieldsReceived = {names:payload.repairableNames,fields:payload.repairableFields};
      if (payload.semanticContext && !prompt.includes("existing structural correction slot")) {
        semanticRepairs += 1;
        const dimension = ["partial-review-consistency", "partial-review-compatible", "partial-review-low-contradiction"].includes(fixtureReason ?? "")
          ? "internal-consistency" : "support";
        receivedFailureHints = payload.errors.some((error: string) =>
          error.includes(`Candidate failures: 0:${dimension}:uncertain`) || error.includes(`Candidate failures: 0:${dimension}:unsupported`));
      }
      else { selectors += 1; structuralContextReceived = !!payload.semanticContext?.frozenEvidence && Array.isArray(payload.semanticContext?.existingMemories); }
      if (fixtureReason === "subset-repair-invalid" && !prompt.includes("existing structural correction slot")) return {exitCode:1,stderr:"",text:""};
      if (fixtureReason?.startsWith("no-entry")) {
        const candidate = payload.repairCandidates[0];
        if (fixtureReason === "no-entry-required") {
          if (candidate.withdrawalAllowed) throw new Error("Required draft became optional");
          return {exitCode:0,stderr:"",text:JSON.stringify({kind:"incremental-memory-amendment",version:1,...payload.identity,replacements:[]})};
        }
        if (!candidate.withdrawalAllowed) throw new Error("Parent optional review missing");
        return {exitCode:0,stderr:"",text:JSON.stringify({kind:"incremental-memory-amendment",version:1,...payload.identity,
          replacements:[],withdrawals:[{candidateRef:candidate.candidateRef,reason:"insufficient-evidence"}]}),
          usage:{input:10,output:2,cacheRead:0,cacheWrite:0,totalTokens:12,cost:.01}};
      }
      const repaired = structuredClone(payload.rejectedPlan.malformedPlanText || payload.rejectedPlan.missingPlanEnvelope ? lastMemoryPlan : payload.rejectedPlan);
      if (fixtureReason?.startsWith("distill-fresh")) repaired.newMemories[0].content =
        '---\nname: concise\ndescription: "Prefer concise progress updates."\ntype: feedback\n---\nPrefer concise progress updates. A newly repaired unsupported explanation.\n';
      if (fixtureReason === "body-correction") repaired.newMemories[0].content = repaired.newMemories[0].content.replace("Never provide concise progress updates.\n", "");
      if (isDeleteReconsideration) repaired.operations = [{name:"known.md",kind:"rewrite",classification:"safe",
        content:"---\nname: known\ndescription: Existing project knowledge and build convention\ntype: project\n---\nExisting knowledge. The project build convention is CL_MANUAL_SHARED.\n",evidence:[{index:0,quote}]}];
      if (fixtureReason === "subset-retention-fallback") repaired.operations = [{name:"known.md",kind:"rewrite",classification:"safe",
        content:"---\nname: known\ndescription: Project tool convention\ntype: project\n---\nThis project uses pnpm.\n",evidence:[{index:0,quote}]}];
      if (fixtureReason === "subset-repair-complete") repaired.newMemories[1].content =
        "---\nname: cache\ndescription: A cache timeout cleared on retry\ntype: project\n---\nA cache timeout cleared on retry; this does not establish permanent unavailability.\n";
      // These fixtures exercise post-correction gates, not resampling identical
      // plans until a controlled judge changes. Remove an unsupported claim.
      if (effectiveRepairFixture && !prompt.includes("existing structural correction slot"))
        repaired.newMemories[0].content = repaired.newMemories[0].content.replace("Unsupported causal explanation.\n", "");
      if (fixtureReason === "subset-production-after-repair") repaired.newMemories[0].content =
        repaired.newMemories[0].content.replaceAll("This project uses npm.", "This project uses pnpm.");
      if (!prompt.includes("existing structural correction slot") && (fixtureReason === "retention-fixed" || fixtureReason === "retention-mixed-fixed" || fixtureReason === "retention-mixed-both-fixed")) repaired.operations = [{name:"known.md",kind:"rewrite",classification:"safe",
        content:"---\nname: known\ndescription: Project build convention\ntype: project\n---\nThe project build convention is CL_MANUAL_SHARED.\n",evidence:[{index:0,quote}]}];
      if (fixtureReason === "retention-mixed-fixed") repaired.newMemories = [];
      if (fixtureReason === "retention-mixed-both-fixed" && !prompt.includes("existing structural correction slot")) {
        if (jevValidations.length !== 2 || !payload.retainedRepairNames.includes("known.md") || !payload.repairableNames.includes("concise.md")) throw new Error("Both review scopes must precede correction");
        repaired.newMemories[0].content = repaired.newMemories[0].content.replace("Unsupported causal explanation.", "");
      }
      if (fixtureReason === "retention-delete") {
        if (!prompt.includes("preservedIn") || !prompt.includes("CONTRADICTED, SUPERSEDED or SUBSUMED") || !prompt.includes("complete replacement Markdown")) throw new Error("Missing retained operation protocol");
        repaired.operations = [{name:"known.md",kind:"delete",classification:"safe",verdict:"SUPERSEDED",preservedIn:["replacement.md"],evidence:[{index:0,quote}]},
          {name:"replacement.md",kind:"rewrite",classification:"safe",content:"---\nname: replacement\ndescription: Project build convention\ntype: project\n---\nThe project build convention is CL_MANUAL_SHARED.\n",evidence:[{index:0,quote}]}];
      }
      if (fixtureReason === "syntax-privacy-downgrade") { repaired.newMemories[0].kind = "project"; repaired.newMemories[0].classification = "safe"; }
      if ((fixtureReason?.startsWith("structural-") || structuralFirst) && fixtureReason !== "structural-failed") repaired.newMemories[0].kind = "project";
      if (fixtureReason === "repair-held") repaired.newMemories[0].content += "A correction proposal.\n";
      if (fixtureReason === "tamper-repair") tamperFrozen();
      if (fixtureReason === "structural-tamper-snapshot") tamperFrozen(false, payload.identity.runId);
      if (fixtureReason === "structural-tamper-dossier") tamperFrozen(true);
      if (fixtureReason === "repair-cancel" && !prompt.includes("existing structural correction slot")) {
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
      contextDigest: /Context digest: ([a-f0-9]+)/.exec(prompt)![1], selected: fixtureReason === "retention-delete" ? ["known.md","replacement.md"] : isDeleteReconsideration || process.env.CL_MEMORY_ORIGIN === "1" || process.env.CL_MEMORY_PREFIX_FAILURE || fixtureReason?.startsWith("retention-") || fixtureReason === "subset-retention-fallback" ? ["known.md"] : [],
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
    if (!agents && !harness) {
      const taskText = fs.readFileSync(taskFile,"utf8");
      const inline = taskText.split("\n\nEnd of complete Learning Dossier.")[0].split("\n").at(-1)!;
      initialMemoryInputs.push({noTools:args.includes("--no-tools"),hasToolAllowlist:args.includes("--tools"),scopedReadExtension:args.some(arg=>arg.includes("planner-read-")),completeInline:taskText.includes("End of complete Learning Dossier."),
        ...(inline.startsWith('{"kind":"incremental-learning-dossier"') ? {inlineDossierSha256:createHash("sha256").update(inline).digest("hex")} : {})});
    }
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
        name: "concise.md", kind: (scenario === "remember-shared" || fixtureReason === "syntax-privacy-downgrade") ? "project" : "preference", classification: scenario === "remember-shared" ? "safe" : "private",
        content: (scenario === "remember-shared" || fixtureReason === "syntax-privacy-downgrade") ? "---\nname: concise\ndescription: Project build convention\ntype: project\n---\nThe project build convention is CL_MANUAL_SHARED.\n" : "---\nname: concise\ndescription: For progress updates, keep them concise\ntype: feedback\n---\nPrefer concise progress updates.\n",
        evidence: [{index:0,quote:scenario === "remember-invalid" ? "No such request evidence" : quote}],
      }],
    };
    if (isDeleteReconsideration && !harness && !agents) {
      Object.assign(plan,{operations:[{name:"known.md",kind:"delete",classification:"safe",verdict:"SUPERSEDED",preservedIn:["missing.md"],evidence:[{index:99,quote}]}],newMemories:[]});
    }
    if (fixtureReason === "body-correction" && !harness && !agents) plan.newMemories[0].content += "Never provide concise progress updates.\n";
    if ((scenario === "remember-subset" || laterAfterMemory && fixtureReason?.startsWith("subset-")) && !harness && !agents) {
      const facts = [["tools.md", fixtureReason === "subset-production-after-repair" ? "This project uses npm." : "This project uses pnpm."], ["cache.md", "Cache service is permanently unavailable."], ["license.md", "Its license is MIT."]];
      (plan as {newMemories: unknown[]}).newMemories = facts.map(([name, body]) => ({name, kind: "project", classification: "safe",
        content: `---\nname: ${name.slice(0,-3)}\ndescription: ${body}\ntype: project\n---\n${body}\n`, evidence: [{index: 0, quote}]}));
    }
    if (effectiveRepairFixture && !harness && !agents) plan.newMemories[0].content += "Unsupported causal explanation.\n";
    if ((fixtureReason?.startsWith("structural-") || structuralFirst) && !harness && !agents) (plan as {newMemories: Array<{kind:string}>}).newMemories[0].kind = "project-fact";
    if ((fixtureReason?.startsWith("located-") || fixtureReason?.startsWith("referenced-")) && !harness && !agents) {
      (plan as {newMemories:Array<{evidence:unknown[]}>}).newMemories[0].evidence = fixtureReason?.startsWith("referenced-")
        ? [{ref:"e0.b0.l1"}] : [{index:0,lines:{block:0,start:1,end:1}}];
    }
    if (fixtureReason?.startsWith("patch-") && !harness && !agents) {
      (plan as {newMemories:Array<{evidence:unknown[]}>}).newMemories[0].evidence = [{index:1,lines:{source:"patch",block:0,start:1,end:1}}];
    }
    if (fixtureReason?.startsWith("retention-") && !harness && !agents) {
      (plan as {operations:unknown[];newMemories:unknown[]}).operations=[];
      if (!fixtureReason.startsWith("retention-mixed-")) (plan as {operations:unknown[];newMemories:unknown[]}).newMemories=[];
    }
    if (fixtureReason === "retention-mixed-both-fixed" && !harness && !agents) (plan as {newMemories:Array<{content:string}>}).newMemories[0].content += "Unsupported causal explanation.";
    if (!harness && !agents && process.env.CL_MEMORY_REJECTED_PLAN_SECRET === "1") plan.newMemories[0].content += "api_key=sk-" + "x".repeat(40);
    if (!harness && !agents) lastMemoryPlan = plan;
    const child = Object.assign(new EventEmitter(), { stdout: new EventEmitter(), stderr: new EventEmitter(), killed: false, exitCode: null as number | null, signalCode: null });
    queueMicrotask(() => {
      // A planner that reports a model error without any plan. The attribution seam
      // must keep this failure from stopping the phase before the semantic judge.
      if (scenario === "planner-model-error" && !harness && !agents) {
        child.stdout.emit("data", Buffer.from(JSON.stringify({type:"message_end",message:{role:"assistant",stopReason:"error",errorMessage:"Connection error.",content:[]}}) + "\n"));
        child.exitCode = 0; child.emit("close", 0);
        return;
      }
      const costTrace = !harness && !agents && process.env.CL_MEMORY_COST_TRACE;
      if (costTrace) {
        child.stdout.emit("data",Buffer.from(JSON.stringify({type:"message_end",message:{role:"assistant",stopReason:"toolUse",content:[],usage:{input:10,output:2,totalTokens:12,cost:{total:.01}}}})+"\n"));
        if (costTrace === "malformed") child.stdout.emit("data",Buffer.from('{"type":"message_end",bad\n'));
      }
      const tracksRepair = scenario === "harness-repair-cost" && harness;
      const prefixFailure = process.env.CL_MEMORY_PREFIX_FAILURE && !harness && !agents
        && (process.env.CL_MEMORY_PREFIX_FAILURE === "always" || planners.filter(phase=>phase==="memory").length === 1);
      const text = prefixFailure ? JSON.stringify(plan).split('"operations"')[0] + '"operations":[' : scenario.startsWith("remember-empty-delimiters") ? "<tool_call>\n<tool_call>\n</function>\n</tool_call>" : scenario.startsWith("remember-syntax") ? JSON.stringify(plan).replace('"concise.md"', '"concise.md') : tracksRepair && !harnessRepair ? "The planner returned prose instead of a plan." : JSON.stringify(plan);
      const usage = tracksRepair ? { input: harnessRepair ? 20 : 10, output: harnessRepair ? 4 : 2, cacheRead: harnessRepair ? 6 : 3, cacheWrite: 0, totalTokens: harnessRepair ? 30 : 15, cost: {total: harnessRepair ? 0.02 : 0.01} } : costTrace || process.env.CL_MEMORY_PREFIX_FAILURE ? {input:10,output:2,cacheRead:0,cacheWrite:0,totalTokens:12,cost:{total:.01}} : undefined;
      if (scenario === "remember-syntax-multiple") for (let i=0;i<2;i++) child.stdout.emit("data", Buffer.from(JSON.stringify({type:"message_end",message:{role:"assistant",content:[{type:"text",text:JSON.stringify(plan)}]}})+"\n"));
      child.stdout.emit("data", Buffer.from(JSON.stringify({type:"message_end",message:{role:"assistant",content:[{type:"text",text}],...(usage ? {usage} : {})}}) + "\n"));
      child.exitCode = 0; child.emit("close", 0);
    });
    return child;
  },
}));
const privateAccepted = scenario === "remember-private-accepted" || scenario === "remember-new-private-accepted";
let consentCount = 0;
let reviewWireCalls = 0;
let receiptDelivered: (() => void) | undefined;
const receiptDelivery = new Promise<void>(resolve => {receiptDelivered=resolve;});
if (privateAccepted) {
  const production = await import("../extensions/jev-learning.ts");
  const productionFactory = production.createJevJudge;
  mock.module("../extensions/jev-learning.ts", () => ({...production, createJevJudge: options => productionFactory({...options, fetch: async (_url, init) => {
    reviewWireCalls++;
    const request=JSON.parse(String(init.body));const answers={};
    for(const [key,question] of Object.entries(request.questions)) {
      const keys=Object.keys(question.criteria);const label=keys.find(k=>["grounded","compatible","unrelated"].includes(k))??keys[0];
      answers[key]={type:"choice",choice:label,confidence:1,probabilities:Object.fromEntries(keys.map(k=>[k,k===label?1:0]))};
    }
    return new Response(JSON.stringify({model:request.model,answers,usage:{input_tokens:1,output_tokens:1}}));
  }})}));
}
let jevValidations: string[] = [];
let reviewTelemetry: unknown[] = [];
let relationValidations = 0;
let productionJudgeOptions: {independentMemoryApplication?: boolean; composedMemoryApplication?: boolean} | undefined;
const fixtureDigest = (value: unknown) => createHash("sha256").update(JSON.stringify(value)).digest("hex");
if (process.env.CL_JEV_FIXTURE) {
  const fixtureJevModel = process.env.CL_JEV_MODEL ?? "jev-1.13.0";
  const jevModule = await import("../extensions/jev-learning.ts");
  const reason = fixtureReason;
  const productionJudgeFactory = jevModule.createJevJudge;
  mock.module("../extensions/jev-learning.ts", () => ({ ...jevModule,
    createJevJudge: (options?: {independentMemoryApplication?: boolean; composedMemoryApplication?: boolean}) => {
      productionJudgeOptions = options;
      if (isDeleteReconsideration) {
        const judge=productionJudgeFactory({...options,defaultModel:fixtureJevModel,enabled:true,apiKey:"fixture",allowPrivateMemory:true,fetch:async(_url,init)=>{
          reviewWireCalls++;const request=JSON.parse(String(init.body));
          const answers=Object.fromEntries(Object.entries(request.questions).map(([key,q])=>{
            const keys=Object.keys(q.criteria);const label=keys.find(k=>["grounded","compatible","unrelated"].includes(k))??keys[0];
            return [key,{type:"choice",choice:label,confidence:1,probabilities:Object.fromEntries(keys.map(k=>[k,k===label?1:0]))}];
          }));return new Response(JSON.stringify({model:request.model,answers,usage:{input_tokens:1,output_tokens:1}}));
        }});
        return {...judge,memoryReviewEnabled:!reason.endsWith("scope-off") && !reason.endsWith("disabled"),selectionEnabled:false,validate:async(...args)=>{
          jevValidations.push(args[0]);const verdict=await judge.validate(...args);
          if(reason.endsWith("wrong-predecessor"))return {...verdict,candidateReview:{...verdict.candidateReview,existingDigest:"0".repeat(64)}};
          if(reason.endsWith("wrong-evidence"))return {...verdict,candidateReview:{...verdict.candidateReview,evidenceDigest:"0".repeat(64)}};
          if(reason.endsWith("missing-proof"))return {...verdict,candidateReview:undefined};
          if(reason.endsWith("partial-proof"))return {...verdict,telemetry:{...verdict.telemetry,completedWindows:0}};
          return verdict;
        }};
      }
      return { enabled: true, requestedModel: fixtureJevModel, selectionEnabled: true, historicalMemoryReviewEnabled: process.env.CL_MEMORY_ORIGIN === "1",
      independentMemoryBodyReviewEnabled: reason?.startsWith("body-") || reason?.startsWith("distill-fresh"),
      independentMemoryApplicationEnabled: reason.startsWith("subset-production") ? options?.independentMemoryApplication === true : reason.startsWith("subset-") && reason !== "subset-disabled",
      composedMemoryApplicationEnabled: reason.startsWith("subset-production") ? options?.composedMemoryApplication === true : reason === "subset-composed",
      reviewMemoryRelations: async (evidence: unknown, candidates: unknown[], existing: unknown[], review: {evidenceDigest:string;existingDigest:string;candidatesDigest:string;model:string}) => {
        relationValidations++;
        if (reason === "subset-cancel-relations") cancellation = cancelRun!();
        const telemetry = {stage:"memory",status:"decided",reason:"supported",durationMs:1,model:fixtureJevModel,inputTokens:15,outputTokens:3};
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
      ...(reason.startsWith("no-entry") ? {reviewMemoryWithdrawals: productionJudgeFactory({enabled:true,apiKey:"fixture",allowPrivateMemory:true,
        defaultModel:fixtureJevModel,fetch:async(_url,init)=>{
          reviewWireCalls++;
          const request=JSON.parse(String(init.body));
          const label=reason === "no-entry-required" || reason === "no-entry-final-held" && request.state.effectiveCandidates !== undefined ? "required" : "optional";
          return new Response(JSON.stringify({model:request.model,answers:Object.fromEntries(Object.keys(request.questions).map(key=>[key,
            {type:"choice",choice:label,confidence:1,probabilities:{optional:label === "optional"?1:0,required:label === "required"?1:0,unclear:0}}])),usage:{input_tokens:10,output_tokens:2}}));
        }}).reviewMemoryWithdrawals} : {}),
      select: async () => ({ selection: reason === "discover" ? {memory:true,harness:false,selected:[]} : null, telemetry: {stage:"selection",status:"fallback",reason:"unavailable",durationMs:1} }),
      validate: async (stage: string, evidence: unknown, candidates: unknown[], existing: unknown[]) => {
        if (reason.startsWith("no-entry")) {
          jevValidations.push(stage);
          return {decision:candidates.length ? "propose" : "allow",telemetry:{stage,status:candidates.length ? "propose" : "decided",reason:candidates.length ? "uncertain" : "supported",durationMs:1,
            model:fixtureJevModel,evidenceWindows:1,candidateFailures:candidates.map((_,candidateIndex)=>({candidateIndex,dimension:"support",reason:"uncertain"}))},
            candidateReview:{version:1,purpose:"diagnostic-only",complete:true,sameBatchIndependenceReviewed:false,model:fixtureJevModel,
              evidenceDigest:fixtureDigest(evidence),existingDigest:fixtureDigest(existing),candidatesDigest:fixtureDigest(candidates),
              candidates:candidates.map((candidate,index)=>({index,candidateDigest:fixtureDigest(candidate),outcome:"held",heldChecks:[`supported_${index}`],passedChecks:[]}))}};
        }

        if (reason?.startsWith("partial-review-")) {
          jevValidations.push(stage);
          const consistency = ["partial-review-consistency", "partial-review-compatible", "partial-review-low-contradiction"].includes(reason);
          const failures=[{candidateIndex:0,dimension:"support",reason:reason === "partial-review-consistency" ? "unsupported" : "uncertain",
            ...(consistency ? {internalConsistency:true, choice:reason === "partial-review-compatible" ? "compatible" : "contradictory",
              probability:reason === "partial-review-consistency" ? 1 : .74, confidence:reason === "partial-review-consistency" ? 1 : .61} : {})}];
          return {decision:"propose",telemetry:{stage,status:"propose",reason:"timeout",durationMs:2,model:fixtureJevModel,
            requestCount:4,completedRequests:3,knownInputTokens:30,knownEstimatedCostUsd:.001,candidateFailures:failures},
            incompleteReview:{version:1,purpose:"diagnostic-only",complete:false,model:fixtureJevModel,
              evidenceDigest:reason === "partial-review-stale" ? "wrong" : fixtureDigest(evidence),
              existingDigest:fixtureDigest(existing),candidatesDigest:fixtureDigest(candidates),failures}};
        }
        if (reason?.startsWith("distill-fresh")) {
          jevValidations.push(stage);
          const index = 0, initial = jevValidations.length === 1;
          const held = initial ? ["supported_0", "supported_description_0"]
            : jevValidations.length === 2 || reason.endsWith("-held") ? ["supported_0"] : [];
          const expected = ["coherence_0", "supported_0", "supported_description_0", "counter_0_0", "counter_description_0_0"];
          return {decision:held.length ? "propose" : "allow", telemetry:{stage,status:held.length ? "propose" : "decided",
            reason:held.length ? "unsupported" : "supported",durationMs:1,model:fixtureJevModel,evidenceWindows:1,requestCount:1,completedRequests:1,inputTokens:10,outputTokens:2,estimatedCostUsd:.001,
            candidateFailures:held.map(key=>({candidateIndex:0,dimension:"support",reason:"unsupported",...(key.includes("description") ? {field:"description"} : {})}))},
            candidateReview:{version:1,purpose:"diagnostic-only",complete:true,sameBatchIndependenceReviewed:false,model:fixtureJevModel,
              evidenceDigest:fixtureDigest(evidence),existingDigest:fixtureDigest(existing),candidatesDigest:fixtureDigest(candidates),
              candidates:[{index,candidateDigest:fixtureDigest(candidates[0]),outcome:held.length ? "held" : "passed",
                heldChecks:held,passedChecks:expected.filter(k=>!held.includes(k))}]}};
        }
        if (reason?.startsWith("body-")) {
          jevValidations.push(stage);
          if (reason === "body-missing-key") return {decision:"allow",telemetry:{stage,status:"disabled",reason:"missing-key",durationMs:0}};
          return {decision:"allow",telemetry:{stage,status:"decided",reason:"supported",durationMs:1,model:fixtureJevModel,inputTokens:10,outputTokens:2,requestCount:1,completedRequests:1},
            candidateReview:{version:1,purpose:"diagnostic-only",complete:true,sameBatchIndependenceReviewed:false,
              evidenceDigest:fixtureDigest(evidence),existingDigest:fixtureDigest(existing),candidatesDigest:fixtureDigest(candidates),model:fixtureJevModel,
              candidates:candidates.map((candidate,index)=>({index,candidateDigest:fixtureDigest(candidate),outcome:"passed",passedChecks:[`coherence_${index}`,`supported_${index}`,`supported_description_${index}`,`counter_${index}_0`,`counter_description_${index}_0`],heldChecks:[]}))}};
        }
        if(process.env.CL_MEMORY_ORIGIN === "1" && !candidates.length) {
          jevValidations.push(stage);
          return {decision:"allow",telemetry:{stage,status:"decided",reason:"supported",durationMs:1,model:fixtureJevModel}};
        }
        if(reason.startsWith("subset-")) {
          jevValidations.push(stage);
          const checks=(i:number)=>[`coherence_${i}`,`supported_${i}`,`supported_description_${i}`, ...(existing.length?[`relation_${i}`,`relation_description_${i}`]:[]),`counter_${i}_0`,`counter_description_${i}_0`];
          if (reason === "subset-retention-fallback" && (!candidates.length || candidates.some(c=>JSON.stringify(c).includes('"kind":"rewrite"'))))
            return {decision:"propose",telemetry:{stage,status:"propose",reason:"uncertain",durationMs:2,model:fixtureJevModel,
              candidateFailures:[{candidateIndex:0,dimension:"support",reason:"uncertain"}]}};
          if (reason === "subset-repair-complete" && candidates.every(c => !JSON.stringify(c).includes("permanently unavailable")))
            return {decision:"allow",telemetry:{stage,status:"decided",reason:"supported",durationMs:2,model:fixtureJevModel,inputTokens:10,outputTokens:2}};
          if (reason === "subset-repair-complete") return {decision:"propose",
            telemetry:{stage,status:"propose",reason:"unsupported",durationMs:2,model:fixtureJevModel,candidateFailures:[
              {candidateIndex:1,dimension:"support",reason:"unsupported"},
              {candidateIndex:1,dimension:"support",field:"description",reason:"unsupported"}]},
            candidateReview:{version:1,purpose:"diagnostic-only",complete:true,sameBatchIndependenceReviewed:false,
              evidenceDigest:fixtureDigest(evidence),existingDigest:fixtureDigest(existing),candidatesDigest:fixtureDigest(candidates),model:fixtureJevModel,
              candidates:candidates.map((c,index)=>({index,candidateDigest:fixtureDigest(c),outcome:index===1?"held":"passed",
                passedChecks:checks(index).filter(k=>index!==1||!k.startsWith("supported_")),
                heldChecks:index===1?[`supported_${index}`,`supported_description_${index}`]:[]}))}};
          const subsetHolds = (index:number) => index===1 ? [`supported_${index}`]
            : reason === "subset-production-after-repair" && jevValidations.length === 1
              ? [`supported_${index}`, ...(index===0 ? [`supported_description_${index}`] : [])] : [];
          return {decision:"propose",telemetry:{stage,status:"propose",reason:"unsupported",durationMs:2,model:fixtureJevModel,inputTokens:10,outputTokens:2,
            ...(reason === "subset-production-after-repair" ? {candidateFailures:candidates.flatMap((_c,index)=>subsetHolds(index).map(key=>({candidateIndex:index,dimension:"support",reason:"unsupported",...(key.includes("description")?{field:"description"}:{})})))} : {})},
            candidateReview:{version:1,purpose:"diagnostic-only",complete:true,sameBatchIndependenceReviewed:false,evidenceDigest:fixtureDigest(evidence),existingDigest:fixtureDigest(existing),candidatesDigest:fixtureDigest(candidates),model:fixtureJevModel,
              candidates:candidates.map((c,index)=>({index,candidateDigest:fixtureDigest(c),outcome:subsetHolds(index).length?"held":"passed",passedChecks:checks(index).filter(k=>!subsetHolds(index).includes(k)),heldChecks:subsetHolds(index)}))}};
        }
        jevValidations.push(stage);
        if (reason === "tamper-first" || reason === "tamper-dossier") tamperFrozen(reason === "tamper-dossier");
        if (reason === "tamper-second" && jevValidations.length === 2) tamperFrozen();
        const combinedHeld = reason === "retention-mixed-both-fixed" && (!candidates.length || candidates.some(value => JSON.stringify(value).includes("Unsupported causal explanation.")));
        const allowed = !combinedHeld && ((reason === "retention-fixed" || reason === "retention-delete" || reason.startsWith("retention-mixed-")) && candidates.length > 0 || reason === "patch-supported" || reason === "patch-repair" && jevValidations.length === 2 || reason === "located-supported" || reason === "located-repair" && jevValidations.length === 2 || reason === "referenced-supported" || reason === "referenced-repair" && jevValidations.length === 2 || reason === "supported" || reason === "syntax-privacy-downgrade" || reason === "tamper-first" || reason === "tamper-dossier" || reason === "tamper-queue" || (reason === "repair-supported" || reason === "tamper-second") && jevValidations.length === 2);
        const judgment = reason.startsWith("retention-") ? allowed ? "supported" : "conflict" : (reason.startsWith("repair-") || reason === "patch-repair" || reason === "located-repair" || reason === "referenced-repair" || reason === "structural-held" || reason === "tamper-second" || reason === "tamper-repair") ? allowed ? "supported" : "uncertain" : reason;
        const telemetry = {stage,status:allowed ? "decided" : "propose",reason:judgment,durationMs:2,model:fixtureJevModel,inputTokens:10,outputTokens:2,...(!allowed ? {candidateIndex:0,dimension:"support",candidateFailures:(reason === "retention-delete" ? [0,1] : [0]).map(candidateIndex=>({candidateIndex,dimension:"support",reason:"uncertain"}))} : {}),requestCount:jevValidations.length,completedRequests:jevValidations.length};
        reviewTelemetry.push(telemetry);
        return {decision:allowed ? "allow" : "propose",telemetry};
      },
    }; },
  }));
}
const snapshotRootFiles = (dirs: readonly string[]) => dirs.map(dir => fs.existsSync(dir)
  ? fs.readdirSync(dir).sort().map(name => [name,fixtureDigest(fs.readFileSync(path.join(dir,name)).toString("base64"))]) : []);
if (fixtureReason === "subset-name-collision-cancel") {
  const incremental = await import("../extensions/incremental-memory-plan.ts");
  const expand = incremental.expandIncrementalMemoryPlan;
  mock.module("../extensions/incremental-memory-plan.ts",()=>({...incremental,
    expandIncrementalMemoryPlan: async (...args: Parameters<typeof incremental.expandIncrementalMemoryPlan>) => {
      try { return await expand(...args); }
      catch(error) {
        if (error instanceof incremental.IncrementalMemoryNameCollisionError) cancellation = cancelRun!();
        throw error;
      }
    }}));
}
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
if (process.env.CL_ORIGIN_AUDIT_FAIL) {
  const history = await import("../extensions/learning-history");
  const recordProposal = history.recordLearningProposal;
  mock.module("../extensions/learning-history",()=>({...history,recordLearningProposal:async(...args)=>{
    if(args[2]?.kind === "independent-memory-review"){
      if(process.env.CL_ORIGIN_AUDIT_FAIL === "cancel")cancellation = cancelRun!();
      throw Error("Controlled history publication failure");
    }
    return recordProposal(...args);
  }}));
}
try {
  const { default: register, resolveMemoryPaths } = await import("../extensions/inject-memory.ts");
  if (scenario === "remember-private-maintenance" || scenario === "remember-private-request" || privateAccepted) {
    const paths=resolveMemoryPaths(cwd);fs.mkdirSync(paths.harnessDir,{recursive:true});
    if (scenario !== "remember-new-private-accepted") fs.writeFileSync(path.join(paths.harnessDir,"private.md"),"---\nname: private\ndescription: Local preference\ntype: feedback\n---\nLocal preference.\n");
    fs.writeFileSync(path.join(agent,"continual-learning.json"),JSON.stringify({jev:{enabled:true,apiKey:"fixture-only",scopes:["memory"],allowPrivateMemory:false}}));
  }
  const { listLearningHistory } = await import("../extensions/learning-history.ts");
  const hooks = new Map();
  const commands = new Map<string, (args: string, ctx: unknown) => Promise<void> | void>();
  const notices: string[] = [];
  register({ on: (name, fn) => hooks.set(name, [...(hooks.get(name) ?? []), fn]),
    registerCommand: (name, definition) => commands.set(name, definition.handler),
    sendMessage: (message) => {if(message.customType==="continual-learning-result")receiptDelivered?.();}, appendEntry: () => {}, getCommands: () => [],
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
  if (fixtureReason?.startsWith("patch-")) entries.push({message:{role:"toolResult",toolName:"edit",isError:false,
    content:"Successfully replaced text.",details:{patch:"+The project build convention is CL_MANUAL_SHARED."}}} as typeof entries[number]);
  if (process.env.CL_STARTUP_SECRET_OBSERVATION === "1") entries.push(
    {message:{role:"assistant",content:[{type:"toolCall",id:"environment",name:"bash",arguments:{command:"env"}}]}} as typeof entries[number],
    {message:{role:"toolResult",toolCallId:"environment",toolName:"bash",isError:false,
      content:"TYPESAFE_API_KEY=CL_BASH_LEARNING_SECRET_0123456789"}} as typeof entries[number]);
  const ctx = {cwd,mode:"json",hasUI:privateAccepted,model:{provider:"session",id:"active"},ui:{notify:(text:string)=>notices.push(text),setWidget:()=>{},confirm:async()=>{consentCount++;return true;}},modelRegistry:{getAll:()=>[{provider:"old",id:"one"},{provider:"new",id:"two"}],getAvailable:()=>[]},sessionManager:{getBranch:()=>entries,buildContextEntries:()=>entries}};
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
  if (scenario === "manual-backfill") {
    const {SessionManager} = await import("@earendil-works/pi-coding-agent");
    const {enqueueBacklog} = await import("../extensions/learning-backlog");
    const {currentTaskSlice} = await import("../extensions/incremental-learning");
    const sessionDir = path.join(agent,"sessions","original");fs.mkdirSync(sessionDir,{recursive:true});
    const manager = SessionManager.create(cwd,sessionDir);
    manager.appendMessage({role:"user",content:quote,timestamp:1});
    manager.appendMessage({role:"assistant",content:[{type:"text",text:"Original task result."}],api:"openai-completions",provider:"fixture",model:"fixture",usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:"stop",timestamp:2});
    const source = manager.buildContextEntries();const slice = currentTaskSlice(source);
    enqueueBacklog({cwd,agentDir:agent,sessionFile:manager.getSessionFile()!,from:0,to:source.length-1,
      digest:createHash("sha256").update(JSON.stringify(slice)).digest("hex"),reason:"learning-failed"});
    await commands.get("consolidate")!("backfill",{...ctx,sessionManager:{...ctx.sessionManager,getSessionId:()=>"current-backfill-invocation"}});
  } else if (isEmptyFull) await commands.get("consolidate")!("full", ctx);
  else if (isRemember) await commands.get("memory")!(scenario === "remember-existing-maintenance" ? "整理记忆" : quote, ctx);
  else if (isManual) await commands.get("consolidate")!(scenario === "manual-full" ? "  full  " : "", ctx);
  else {
    await runHook("agent_settled", {});
    if (isModelFreeze) {
      await runHook("input", { source: "interactive" });
      await runHook("agent_settled", {});
    }
  }
  if (privateAccepted || laterAfterMemory) await receiptDelivery;
  await cancellation;
  const nextMemory: unknown[] = [];
  if (scenario === "remember-subset") for (const fn of hooks.get("before_agent_start") ?? []) {
    const systemPromptOptions = { sections: {}, promptGuidelines: [], skills: [] };
    const result = await fn({prompt:"Use pnpm project build tools and MIT license",systemPrompt:"Task",systemPromptOptions},ctx);
    nextMemory.push({ systemPromptOptions, result: result ?? null });
  }
  await runHook("session_shutdown", {});
  const paths = resolveMemoryPaths(cwd);
  const history = await listLearningHistory(cwd);
  const receiptOf = (file: string) => { try { return JSON.parse(fs.readFileSync(file, "utf8")) } catch { return undefined } };
  const {learningSummarySubject} = await import("../extensions/learning-efficiency.ts");
  const {learningReceiptComplete} = await import("../extensions/learning-replay.ts");
  const savedReceipt = receiptOf(path.join(paths.runsDir, "learning-pipeline-receipt.json"));
  const runs = (fs.existsSync(paths.runsDir) ? fs.readdirSync(paths.runsDir).filter(name => name.startsWith("run_")) : []).map(dir => ({
    dir, files: fs.readdirSync(path.join(paths.runsDir, dir)).sort(),
    receipt: receiptOf(path.join(paths.runsDir, dir, "learning-pipeline-receipt.json")),
    dossier: receiptOf(path.join(paths.runsDir, dir, "incremental-learning-dossier.json")),
    snapshot: receiptOf(path.join(paths.runsDir, dir, "snapshot.json")),
  }));
  if (isRemember) requestCaptured = runs.some(run => run.dossier?.taskSlice?.entries[run.dossier?.memoryRequest?.entryIndex]?.message?.content === quote);
  console.log(JSON.stringify({ originAuditArtifacts:fs.existsSync(paths.runsDir)?fs.readdirSync(paths.runsDir,{recursive:true}).filter(p=>String(p).endsWith("independent-memory-review.json")):[], consentCount,reviewWireCalls,consentConfigUnchanged:!privateAccepted || JSON.parse(fs.readFileSync(path.join(agent,"continual-learning.json"),"utf8")).jev.allowPrivateMemory===false,newAppliedHistoryRecords:history.filter(record=>!(transactionHistoryIdsBefore??historyIdsBefore).has(record.id)&&record.status==="applied").length,memoryFilesRestored:(transactionMemoryFilesBefore??JSON.stringify(memoryFilesBefore))===JSON.stringify(snapshotMemoryFiles()),finalVerificationObservedWrites,...(scenario === "remember-subset" && savedReceipt ? {summarySubject:learningSummarySubject(savedReceipt)} : {}),productionJudgeOptions,nextMemory,initialMemoryInputs,jevValidations,reviewTelemetry,relationValidations,selectors,planners,plannerSystemInstructions,modelCalls,requestCaptured,notices,history:history.map(record=>({phase:record.phase,status:record.status,changes:record.changes,...(scenario === "remember-subset" ? {proposal:record.proposal} : {})})),
    privateFiles: fs.existsSync(paths.harnessDir) ? fs.readdirSync(paths.harnessDir) : [],
    publicFiles: fs.existsSync(paths.publicDir!) ? fs.readdirSync(paths.publicDir!) : [],
    numericUsageLedgers: fs.existsSync(paths.runsDir) ? fs.readdirSync(paths.runsDir,{recursive:true}).filter(name=>String(name).endsWith("memory-task-usage.json")).map(name=>{const file=path.join(paths.runsDir,String(name));return {mode:fs.statSync(file).mode & 0o777,...JSON.parse(fs.readFileSync(file,"utf8"))};}) : [],
    runs, registryReceipt: savedReceipt, receiptComplete: !!savedReceipt && learningReceiptComplete(savedReceipt),
    bodyReviewCalls, conciseMemory: fs.existsSync(path.join(paths.harnessDir,"concise.md")) ? fs.readFileSync(path.join(paths.harnessDir,"concise.md"),"utf8") : undefined, semanticRepairs, totalRepairs, maintenanceClaimChecks, receivedFailureHints, requiredTextChangesReceived, repairableFieldsReceived, structuralContextReceived, repairErrors,
    initialMemoryPlanDigest: lastMemoryPlan ? createHash("sha256").update(JSON.stringify(lastMemoryPlan)).digest("hex") : undefined,
    structuralRejections: fs.existsSync(paths.runsDir) ? fs.readdirSync(paths.runsDir,{recursive:true}).filter(name=>String(name).endsWith("structural-rejection.json")).map(name=>JSON.parse(fs.readFileSync(path.join(paths.runsDir,String(name)),"utf8"))) : [],
    structuralRejectionRecorded: fs.existsSync(path.join(agent,"memory","runs")) && fs.readdirSync(path.join(agent,"memory","runs"), {recursive:true}).some(name => String(name).endsWith("structural-rejection.json")),
    structuralResponseRetained: fs.existsSync(path.join(agent,"memory","runs")) && fs.readdirSync(path.join(agent,"memory","runs"), {recursive:true}).some(name => String(name).endsWith("structural-repair-response.json")),
    originalProposalRetained: history.some(record => {
      if (record.status !== "proposed") return false;
      let proposal = record.proposal;
      if (proposal && typeof proposal === "object" && "kind" in proposal && proposal.kind === "independent-memory-review") {
        if (!("originalPlan" in proposal) || !("reviewedPlanDigest" in proposal)) return false;
        if (createHash("sha256").update(JSON.stringify(proposal.originalPlan)).digest("hex") !== proposal.reviewedPlanDigest) return false;
        proposal = proposal.originalPlan;
      }
      return runs.some(run => JSON.stringify(proposal) === JSON.stringify(receiptOf(path.join(paths.runsDir, run.dir, "plan.json"))));
    }),
    knownMemory: fs.existsSync(path.join(paths.harnessDir,"known.md")) ? fs.readFileSync(path.join(paths.harnessDir,"known.md"),"utf8") : undefined,
    replacementMemory: fs.existsSync(path.join(paths.harnessDir,"replacement.md")) ? fs.readFileSync(path.join(paths.harnessDir,"replacement.md"),"utf8") : undefined,
    memoryMirrored: fs.existsSync(path.join(paths.harnessDir,'concise.md')) && fs.existsSync(path.join(paths.publicDir!,'concise.md')) && fs.readFileSync(path.join(paths.harnessDir,'concise.md')).equals(fs.readFileSync(path.join(paths.publicDir!,'concise.md'))),
    harnessExists:fs.existsSync(path.join(cwd,".pi","harness.json")), agentsUnchanged: !(isAgents || isRemember || laterAfterMemory) || fs.readFileSync(path.join(cwd,"AGENTS.md"),"utf8") === oldAgents, lock:fs.existsSync(paths.lockFile),
  }));
} finally { fs.rmSync(root,{recursive:true,force:true}); }
