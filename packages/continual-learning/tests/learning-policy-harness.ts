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
if (isModelFreeze || scenario === "remember-declined" || (process.env.CL_JEV_FIXTURE?.startsWith("retention-") || process.env.CL_JEV_FIXTURE === "structural-retention-mixed-both-fixed" || process.env.CL_JEV_FIXTURE === "subset-retention-fallback")) {
  // These cases specifically exercise model selection, not empty-index routing.
  fs.mkdirSync(path.join(cwd, ".memory"));
  fs.writeFileSync(path.join(cwd, ".memory", "known.md"), "---\nname: known\ndescription: Existing project knowledge\ntype: project\n---\nExisting knowledge.\n");
  if (process.env.CL_JEV_FIXTURE === "retention-delete") fs.writeFileSync(path.join(cwd,".memory","replacement.md"),"---\nname: replacement\ndescription: Existing project knowledge\ntype: project\n---\nExisting knowledge.\n");
}
const policies = { memory: isModelFreeze ? "propose" : scenario === "all-off" || isHarness || isAgents ? "off" : scenario === "memory-apply" ? "apply" : "propose", harness: isModelFreeze ? "propose" : isHarness ? scenario === "harness-rejected" ? "apply" : "propose" : "off", agents: isModelFreeze ? "propose" : isAgents ? scenario === "agents-propose" ? "propose" : "apply" : "off" };
if (process.env.CL_JEV_FIXTURE?.startsWith("subset-name-collision")) {
  fs.mkdirSync(path.join(cwd,".memory"),{recursive:true});
  fs.writeFileSync(path.join(cwd,".memory","cache.md"),"---\nname: cache\ndescription: Cache timeout cleared on retry\ntype: project\n---\nA timeout cleared on retry.\n");
}
fs.writeFileSync(path.join(agent, "memory", "settings.json"), JSON.stringify({ autoMemory: !isRemember, automaticPhases: isRemember ? {memory:"off",harness:"off",agents:"off"} : policies }));
if (isModelFreeze) fs.writeFileSync(path.join(agent, "memory.json"), JSON.stringify(scenario === "model-freeze" ? { provider: "old", model: "one" } : {}));
const quote = scenario === "remember-private-maintenance" ? "整理记忆" : scenario === "remember-subset" ? "Remember: this project uses pnpm. Its license is MIT. A cache timeout cleared on retry." : scenario === "semantic-opportunity" ? "Package management happens through pnpm." : isRemember ? scenario === "remember-secret" ? "Remember my API key: sk-test-secret" : (scenario === "remember-shared" || process.env.CL_JEV_FIXTURE === "syntax-privacy-downgrade") ? "Remember that the project build convention is CL_MANUAL_SHARED." : "Remember that I prefer concise progress updates." : isAgents ? "Confirmed: the AGENTS.md workflow is wrong. Use pnpm test for this project." : isHarness ? "Never run the retired compiler." : scenario === "manual-constraint" ? "Never run the retired compiler." : isManual ? "Fix the failing build." : "I prefer concise progress updates.";
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
const repairErrors: string[][] = [];
let structuralContextReceived = false;
let receivedFailureHints = false;
let totalRepairs = 0;
let lastMemoryPlan: unknown;
let cancellation: Promise<void> | undefined;
let cancelRun: (() => Promise<void>) | undefined;
const structuralFirst = ["structural-retention-mixed-both-fixed", "structural-repair-cancel", "structural-tamper-second", "structural-subset-repair-invalid"].includes(process.env.CL_JEV_FIXTURE ?? "");
const fixtureReason = structuralFirst ? process.env.CL_JEV_FIXTURE!.slice("structural-".length) : process.env.CL_JEV_FIXTURE;
const tamperFrozen = (dossier = false, runId?: string): void => {
  const file = fs.readdirSync(path.join(agent, "memory", "runs"), {recursive:true}).find(name => String(name).endsWith(dossier ? "incremental-learning-dossier.json" : "snapshot.json") && (dossier || (runId ? String(name).includes(runId) : fs.existsSync(path.join(agent, "memory", "runs", path.dirname(String(name)), "plan.json")))));
  if (!file) throw new Error("Missing frozen fixture file");
  fs.appendFileSync(path.join(agent, "memory", "runs", String(file)), " ");
};
const planners: string[] = [];
const initialMemoryInputs: {noTools:boolean;hasToolAllowlist:boolean;scopedReadExtension:boolean;completeInline:boolean}[] = [];
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
      repairErrors.push(payload.errors);
      if (payload.semanticContext && !prompt.includes("existing structural correction slot")) { semanticRepairs += 1; receivedFailureHints = payload.errors.some((error: string) => error.includes("Candidate failures: 0:support:uncertain")); }
      else { selectors += 1; structuralContextReceived = !!payload.semanticContext?.frozenEvidence && Array.isArray(payload.semanticContext?.existingMemories); }
      if (fixtureReason === "subset-repair-invalid" && !prompt.includes("existing structural correction slot")) return {exitCode:1,stderr:"",text:""};
      const repaired = structuredClone(payload.rejectedPlan.malformedPlanText ? lastMemoryPlan : payload.rejectedPlan);
      if (fixtureReason === "subset-retention-fallback") repaired.operations = [{name:"known.md",kind:"rewrite",classification:"safe",
        content:"---\nname: known\ndescription: Project tool convention\ntype: project\n---\nThis project uses pnpm.\n",evidence:[{index:0,quote}]}];
      if (fixtureReason === "subset-repair-complete") repaired.newMemories[1].content =
        "---\nname: cache\ndescription: A cache timeout cleared on retry\ntype: project\n---\nA cache timeout cleared on retry; this does not establish permanent unavailability.\n";
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
      contextDigest: /Context digest: ([a-f0-9]+)/.exec(prompt)![1], selected: fixtureReason === "retention-delete" ? ["known.md","replacement.md"] : fixtureReason?.startsWith("retention-") || fixtureReason === "subset-retention-fallback" ? ["known.md"] : [],
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
    if (!agents && !harness) initialMemoryInputs.push({noTools:args.includes("--no-tools"),hasToolAllowlist:args.includes("--tools"),scopedReadExtension:args.some(arg=>arg.includes("planner-read-")),completeInline:fs.readFileSync(taskFile,"utf8").includes("End of complete Learning Dossier.")});
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
    if (scenario === "remember-subset" && !harness && !agents) {
      const facts = [["tools.md", "This project uses pnpm."], ["cache.md", "Cache service is permanently unavailable."], ["license.md", "Its license is MIT."]];
      (plan as {newMemories: unknown[]}).newMemories = facts.map(([name, body]) => ({name, kind: "project", classification: "safe",
        content: `---\nname: ${name.slice(0,-3)}\ndescription: ${body}\ntype: project\n---\n${body}\n`, evidence: [{index: 0, quote}]}));
    }
    if ((fixtureReason?.startsWith("structural-") || structuralFirst) && !harness && !agents) (plan as {newMemories: Array<{kind:string}>}).newMemories[0].kind = "project-fact";
    if (fixtureReason?.startsWith("located-") && !harness && !agents) {
      (plan as {newMemories:Array<{evidence:unknown[]}>}).newMemories[0].evidence = [{index:0,lines:{block:0,start:1,end:1}}];
    }
    if (fixtureReason?.startsWith("patch-") && !harness && !agents) {
      (plan as {newMemories:Array<{evidence:unknown[]}>}).newMemories[0].evidence = [{index:2,lines:{source:"patch",block:0,start:1,end:1}}];
    }
    if (fixtureReason?.startsWith("retention-") && !harness && !agents) {
      (plan as {operations:unknown[];newMemories:unknown[]}).operations=[];
      if (!fixtureReason.startsWith("retention-mixed-")) (plan as {operations:unknown[];newMemories:unknown[]}).newMemories=[];
    }
    if (fixtureReason === "retention-mixed-both-fixed" && !harness && !agents) (plan as {newMemories:Array<{content:string}>}).newMemories[0].content += "Unsupported causal explanation.";
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
      const text = scenario.startsWith("remember-syntax") ? JSON.stringify(plan).replace('"concise.md"', '"concise.md') : tracksRepair && !harnessRepair ? "The planner returned prose instead of a plan." : JSON.stringify(plan);
      const usage = tracksRepair ? { input: harnessRepair ? 20 : 10, output: harnessRepair ? 4 : 2, cacheRead: harnessRepair ? 6 : 3, cacheWrite: 0, totalTokens: harnessRepair ? 30 : 15, cost: {total: harnessRepair ? 0.02 : 0.01} } : costTrace ? {input:10,output:2,totalTokens:12,cost:{total:.01}} : undefined;
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
  const jevModule = await import("../extensions/jev-learning.ts");
  const reason = fixtureReason;
  mock.module("../extensions/jev-learning.ts", () => ({ ...jevModule,
    createJevJudge: (options?: {independentMemoryApplication?: boolean; composedMemoryApplication?: boolean}) => {
      productionJudgeOptions = options;
      return { enabled: true, selectionEnabled: true,
      independentMemoryApplicationEnabled: reason.startsWith("subset-production") ? options?.independentMemoryApplication === true : reason.startsWith("subset-") && reason !== "subset-disabled",
      composedMemoryApplicationEnabled: reason.startsWith("subset-production") ? options?.composedMemoryApplication === true : reason === "subset-composed",
      reviewMemoryRelations: async (evidence: unknown, candidates: unknown[], existing: unknown[], review: {evidenceDigest:string;existingDigest:string;candidatesDigest:string;model:string}) => {
        relationValidations++;
        if (reason === "subset-cancel-relations") cancellation = cancelRun!();
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
          const checks=(i:number)=>[`coherence_${i}`,`supported_${i}`,`supported_description_${i}`, ...(existing.length?[`relation_${i}`,`relation_description_${i}`]:[]),`counter_${i}_0`,`counter_description_${i}_0`];
          if (reason === "subset-retention-fallback" && (!candidates.length || candidates.some(c=>JSON.stringify(c).includes('"kind":"rewrite"'))))
            return {decision:"propose",telemetry:{stage,status:"propose",reason:"uncertain",durationMs:2,model:"jev-1.13.0",
              candidateFailures:[{candidateIndex:0,dimension:"support",reason:"uncertain"}]}};
          if (reason === "subset-repair-complete" && candidates.every(c => !JSON.stringify(c).includes("permanently unavailable")))
            return {decision:"allow",telemetry:{stage,status:"decided",reason:"supported",durationMs:2,model:"jev-1.13.0",inputTokens:10,outputTokens:2}};
          if (reason === "subset-repair-complete") return {decision:"propose",
            telemetry:{stage,status:"propose",reason:"unsupported",durationMs:2,model:"jev-1.13.0",candidateFailures:[
              {candidateIndex:1,dimension:"support",reason:"unsupported"},
              {candidateIndex:1,dimension:"support",field:"description",reason:"unsupported"}]},
            candidateReview:{version:1,purpose:"diagnostic-only",complete:true,sameBatchIndependenceReviewed:false,
              evidenceDigest:fixtureDigest(evidence),existingDigest:fixtureDigest(existing),candidatesDigest:fixtureDigest(candidates),model:"jev-1.13.0",
              candidates:candidates.map((c,index)=>({index,candidateDigest:fixtureDigest(c),outcome:index===1?"held":"passed",
                passedChecks:checks(index).filter(k=>index!==1||!k.startsWith("supported_")),
                heldChecks:index===1?[`supported_${index}`,`supported_description_${index}`]:[]}))}};
          return {decision:"propose",telemetry:{stage,status:"propose",reason:"unsupported",durationMs:2,model:"jev-1.13.0",inputTokens:10,outputTokens:2},
            candidateReview:{version:1,purpose:"diagnostic-only",complete:true,sameBatchIndependenceReviewed:false,evidenceDigest:fixtureDigest(evidence),existingDigest:fixtureDigest(existing),candidatesDigest:fixtureDigest(candidates),model:"jev-1.13.0",
              candidates:candidates.map((c,index)=>({index,candidateDigest:fixtureDigest(c),outcome:index===1 || reason === "subset-production-after-repair" && jevValidations.length === 1?"held":"passed",passedChecks:checks(index).filter(k=>(index!==1 && !(reason === "subset-production-after-repair" && jevValidations.length === 1))||k!==`supported_${index}`),heldChecks:index===1 || reason === "subset-production-after-repair" && jevValidations.length === 1?[`supported_${index}`]:[]}))}};
        }
        jevValidations.push(stage);
        if (reason === "tamper-first" || reason === "tamper-dossier") tamperFrozen(reason === "tamper-dossier");
        if (reason === "tamper-second" && jevValidations.length === 2) tamperFrozen();
        const combinedHeld = reason === "retention-mixed-both-fixed" && (!candidates.length || candidates.some(value => JSON.stringify(value).includes("Unsupported causal explanation.")));
        const allowed = !combinedHeld && ((reason === "retention-fixed" || reason === "retention-delete" || reason.startsWith("retention-mixed-")) && candidates.length > 0 || reason === "patch-supported" || reason === "patch-repair" && jevValidations.length === 2 || reason === "located-supported" || reason === "located-repair" && jevValidations.length === 2 || reason === "supported" || reason === "syntax-privacy-downgrade" || reason === "tamper-first" || reason === "tamper-dossier" || reason === "tamper-queue" || (reason === "repair-supported" || reason === "tamper-second") && jevValidations.length === 2);
        const judgment = reason.startsWith("retention-") ? allowed ? "supported" : "conflict" : (reason.startsWith("repair-") || reason === "patch-repair" || reason === "located-repair" || reason === "structural-held" || reason === "tamper-second" || reason === "tamper-repair") ? allowed ? "supported" : "uncertain" : reason;
        const telemetry = {stage,status:allowed ? "decided" : "propose",reason:judgment,durationMs:2,model:"jev-1.13.0",inputTokens:10,outputTokens:2,...(!allowed ? {candidateIndex:0,dimension:"support",candidateFailures:(reason === "retention-delete" ? [0,1] : [0]).map(candidateIndex=>({candidateIndex,dimension:"support",reason:"uncertain"}))} : {}),requestCount:jevValidations.length,completedRequests:jevValidations.length};
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
  if (privateAccepted) await receiptDelivery;
  await cancellation;
  const nextMemory: unknown[] = [];
  if (scenario === "remember-subset") for (const fn of hooks.get("before_agent_start") ?? []) {
    const result = await fn({prompt:"Use pnpm project build tools and MIT license",systemPrompt:"Task"},ctx);
    if (result) nextMemory.push(result);
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
  }));
  if (isRemember) requestCaptured = runs.some(run => run.dossier?.taskSlice?.entries[0]?.message?.content === quote);
  console.log(JSON.stringify({ consentCount,reviewWireCalls,consentConfigUnchanged:!privateAccepted || JSON.parse(fs.readFileSync(path.join(agent,"continual-learning.json"),"utf8")).jev.allowPrivateMemory===false,newAppliedHistoryRecords:history.filter(record=>!(transactionHistoryIdsBefore??historyIdsBefore).has(record.id)&&record.status==="applied").length,memoryFilesRestored:(transactionMemoryFilesBefore??JSON.stringify(memoryFilesBefore))===JSON.stringify(snapshotMemoryFiles()),finalVerificationObservedWrites,...(scenario === "remember-subset" && savedReceipt ? {summarySubject:learningSummarySubject(savedReceipt)} : {}),productionJudgeOptions,nextMemory,initialMemoryInputs,jevValidations,reviewTelemetry,relationValidations,selectors,planners,plannerSystemInstructions,modelCalls,requestCaptured,notices,history:history.map(record=>({phase:record.phase,status:record.status,changes:record.changes,...(scenario === "remember-subset" ? {proposal:record.proposal} : {})})),
    privateFiles: fs.existsSync(paths.harnessDir) ? fs.readdirSync(paths.harnessDir) : [],
    publicFiles: fs.existsSync(paths.publicDir!) ? fs.readdirSync(paths.publicDir!) : [],
    numericUsageLedgers: fs.existsSync(paths.runsDir) ? fs.readdirSync(paths.runsDir,{recursive:true}).filter(name=>String(name).endsWith("memory-task-usage.json")).map(name=>{const file=path.join(paths.runsDir,String(name));return {mode:fs.statSync(file).mode & 0o777,...JSON.parse(fs.readFileSync(file,"utf8"))};}) : [],
    runs, registryReceipt: savedReceipt, receiptComplete: !!savedReceipt && learningReceiptComplete(savedReceipt),
    semanticRepairs, totalRepairs, receivedFailureHints, structuralContextReceived, repairErrors,
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
    harnessExists:fs.existsSync(path.join(cwd,".pi","harness.json")), agentsUnchanged: !(isAgents || isRemember) || fs.readFileSync(path.join(cwd,"AGENTS.md"),"utf8") === oldAgents, lock:fs.existsSync(paths.lockFile),
  }));
} finally { fs.rmSync(root,{recursive:true,force:true}); }
