import {expect, test} from "bun:test";
import fs from "node:fs";
import {createHash} from "node:crypto";
import {digest} from "../extensions/consolidation-run.ts";
import {commandMemorySourceProof} from "./continuous-command-proof.ts";

// Existing controlled source/owner framing. It contains no real model answer.
const baseline = JSON.parse(fs.readFileSync(new URL("./fixtures/controlled-command-source-proof.json", import.meta.url), "utf8"));
const hash = (value: string) => createHash("sha256").update(value).digest("hex");
const id = (number: number) => `${String(number).padStart(8,"0")}-1111-4111-8111-111111111111`;
const usage = (input: number) => ({input, output: 2, cacheRead: 0, cacheWrite: 0, totalTokens: input + 2, cost: input / 1000});

function refreshReceipt(input: any): void {
  const rows = input.nativeSession.trimEnd().split("\n").map(JSON.parse);
  rows.at(-1).details = input.receipt;
  input.nativeSession = input.originalSession + JSON.stringify(rows.at(-1)) + "\n";
  input.stdout = JSON.stringify({type:"message_end",message:{customType:"continual-learning-result",details:input.receipt}})+"\n";
  input.completion.sessionDigest = hash(input.nativeSession);
  input.completion.stdoutDigest = hash(input.stdout);
}

function repaired(attempt = 2): any {
  const input = structuredClone(baseline);
  const initial = {ledgerId:id(1), complete:false, knownUsage:usage(3)};
  const structural = {ledgerId:id(2), complete:true, knownUsage:usage(5)};
  const final = {ledgerId:id(3), complete:true, knownUsage:usage(7)};
  input.initialUsageLedger = initial;
  input.usageLedger = attempt === 1 ? structural : final;
  input.appliedUsageLedgerFile = `memory-repair-usage-${input.usageLedger.ledgerId}.json`;
  const audit = input.receipt.attempts[0];
  input.receipt.attempts = [audit,
    {phase:"memory",attempt:0,outcome:"rejected",operations:0,usageLedgerId:initial.ledgerId,usage:initial.knownUsage},
    ...(attempt === 2 ? [{phase:"memory",attempt:1,outcome:"proposed",operations:0,usageComplete:true,
      usageLedgerId:structural.ledgerId,usage:structural.knownUsage,diagnostic:"Memory structural repair"}] : []),
    // Same attempt numbers also belong to independent body/coverage costs.
    {phase:"memory",attempt:1,outcome:"noop",operations:0,usageLedgerId:id(9),usage:usage(11),usageComplete:true},
    {phase:"memory",attempt,outcome:"applied",operations:1,usageComplete:true,usageLedgerId:input.usageLedger.ledgerId,usage:input.usageLedger.knownUsage},
  ];
  if (attempt === 2) {
    input.initialUsageLedgerFile = "memory-task-usage.json";
    input.structuralUsageLedger = structural;
    input.structuralUsageLedgerFile = `memory-repair-usage-${structural.ledgerId}.json`;
    input.repairArtifacts = {};
    input.repairArtifactRunDir = input.reviewManifest.runDir;
    const put = (name: string, value: any) => {input.repairArtifacts[name] = JSON.stringify(value);};
    put("memory-task-usage.json",initial);
    const m = input.reviewManifest;
    const identity = {runId:m.runId,scopeKey:m.scopeKey,scopeDigest:m.scopeDigest,artifactHash:m.snapshotDigest,snapshotDigest:m.snapshotDigest};
    const original = {...input.plan,kind:"incremental-memory-plan",schemaVersion:1};
    const rejected = {...original,representation:"structurally-corrected"};
    put("generation-original-plan.json",{version:1,...identity,originalPlan:original,originalPlanDigest:hash(JSON.stringify(original)),originalPlanRetained:true,sensitive:false});
    put("structural-rejection.json",{version:1,runId:m.runId,snapshotDigest:m.snapshotDigest,originalPlan:original,originalPlanDigest:hash(JSON.stringify(original)),originalPlanRetained:true,sensitive:false});
    put("semantic-rejected-plan.json",rejected);
    for (const [ledger, predecessor] of [[structural,original],[final,rejected]]) {
      const output = JSON.stringify(ledger === structural ? rejected : input.plan);
      const provenance = {ledgerId:ledger.ledgerId,taskInputSha256:hash("controlled task "+ledger.ledgerId),identitySha256:digest(identity),rejectedPlanCanonicalSha256:hash(JSON.stringify(predecessor)),outputSha256:hash(output)};
      Object.assign(ledger,{parentRepairProvenance:provenance});
      const request = {...provenance};delete (request as any).outputSha256;
      put(`memory-repair-usage-${ledger.ledgerId}.json`,ledger);
      put(`memory-repair-lifecycle-${ledger.ledgerId}-started.json`,{version:1,ledgerId:ledger.ledgerId,stage:"started",deadlineMs:600000,parentRepairProvenance:request});
      put(`memory-repair-lifecycle-${ledger.ledgerId}-closed.json`,{version:1,ledgerId:ledger.ledgerId,stage:"closed",exitCode:0,timedOut:false,cancelled:false,parentRepairProvenance:provenance});
      const response = {version:1,runId:m.runId,snapshotDigest:m.snapshotDigest,parentRepairProvenance:provenance,sensitive:false,truncated:false,output};
      put(`memory-repair-response-${ledger.ledgerId}.json`,response);
      if (ledger === structural) put("structural-repair-response.json",response);
      else {
        put("semantic-repair-plan.json",input.plan);
        const artifactHashes = Object.fromEntries([`memory-repair-usage-${ledger.ledgerId}.json`,`memory-repair-lifecycle-${ledger.ledgerId}-started.json`,`memory-repair-lifecycle-${ledger.ledgerId}-closed.json`,`memory-repair-response-${ledger.ledgerId}.json`].map(name=>[name,hash(input.repairArtifacts[name])]));
        put(`semantic-repair-provenance-${ledger.ledgerId}.json`,{version:1,kind:"memory-repair-provenance",status:"validated-repair-proposal",...identity,...provenance,artifactHashes,boundPlanCanonicalSha256:hash(JSON.stringify(input.plan)),responseArtifactFile:`memory-repair-response-${ledger.ledgerId}.json`,responseArtifactSha256:hash(input.repairArtifacts[`memory-repair-response-${ledger.ledgerId}.json`]),rejectedPlanBytesSha256:hash(input.repairArtifacts["semantic-rejected-plan.json"]),semanticPlanFile:"semantic-repair-plan.json",semanticPlanBytesSha256:hash(input.repairArtifacts["semantic-repair-plan.json"]),parentConstrainedDeltaValidated:true,planSchemaValidated:true,semanticApproval:false,writeAuthorized:false});
      }
    }
  }
  refreshReceipt(input);
  return input;
}

test("source proof keeps original generation and one repair contracts", () => {
  expect(commandMemorySourceProof(baseline).ready).toBe(true);
  expect(commandMemorySourceProof(repaired(1))).toMatchObject({ready:true});
});

test("source proof accepts one actual structural plus semantic correction with all three ledgers", () => {
  const input = repaired();
  expect(commandMemorySourceProof(input)).toMatchObject({ready:true});
  expect(input.initialUsageLedger.complete).toBe(false);
  expect(input.receipt.attempts[1].usageComplete).toBeUndefined();
});

const damage: Record<string,(input:any)=>void> = {
  "missing initial ledger":x=>{delete x.initialUsageLedger;},
  "missing structural ledger":x=>{delete x.structuralUsageLedger;},
  "wrong initial filename":x=>{x.initialUsageLedgerFile="memory-repair-usage-other.json";},
  "wrong structural filename":x=>{x.structuralUsageLedgerFile="elsewhere/"+x.structuralUsageLedgerFile;},
  "wrong semantic filename":x=>{x.appliedUsageLedgerFile="memory-task-usage.json";},
  "foreign artifact run":x=>{x.repairArtifactRunDir+="-foreign";},
  "reused audit identity":x=>{x.initialUsageLedger.ledgerId=x.sourceAudit.usageLedger.ledgerId;},
  "reused correction identity":x=>{x.structuralUsageLedger.ledgerId=x.usageLedger.ledgerId;},
  "swapped ledgers":x=>{[x.initialUsageLedger,x.structuralUsageLedger]=[x.structuralUsageLedger,x.initialUsageLedger];},
  "initial usage drift":x=>{x.initialUsageLedger.knownUsage.input++;},
  "initial explicit complete drift":x=>{x.receipt.attempts[1].usageComplete=true;},
  "structural complete drift":x=>{x.structuralUsageLedger.complete=false;},
  "semantic complete drift":x=>{x.usageLedger.complete=false;},
  "structural missing complete":x=>{delete x.receipt.attempts[2].usageComplete;},
  "missing structural row":x=>{x.receipt.attempts.splice(2,1);},
  "duplicate structural row":x=>{x.receipt.attempts.splice(2,0,structuredClone(x.receipt.attempts[2]));},
  "conflicting generation row":x=>{x.receipt.attempts.splice(2,0,{...x.receipt.attempts[1],usage:usage(99)});},
  "extra correction":x=>{x.receipt.attempts.at(-1).attempt=3;},
  "extra applied correction":x=>{x.receipt.attempts.push({...x.receipt.attempts.at(-1),attempt:3,usageLedgerId:id(8)});},
  "wrong structural role":x=>{x.receipt.attempts[2].diagnostic="Independent body review";},
  "missing original artifact":x=>{delete x.repairArtifacts["memory-task-usage.json"];},
  "malformed artifact":x=>{x.repairArtifacts["memory-task-usage.json"]="PRIVATE_ARTIFACT_MUST_NOT_APPEAR_IN_REASON";},
  "missing structural lifecycle":x=>{delete x.repairArtifacts[`memory-repair-lifecycle-${id(2)}-closed.json`];},
  "missing semantic provenance":x=>{delete x.repairArtifacts[`semantic-repair-provenance-${id(3)}.json`];},
  "foreign structural source":x=>{
    const name="structural-repair-response.json",value=JSON.parse(x.repairArtifacts[name]);value.runId="foreign";x.repairArtifacts[name]=JSON.stringify(value);
  },
  "cancelled correction":x=>{
    const name=`memory-repair-lifecycle-${id(3)}-closed.json`,value=JSON.parse(x.repairArtifacts[name]);value.cancelled=true;x.repairArtifacts[name]=JSON.stringify(value);
  },
  "truncated correction response":x=>{
    const name=`memory-repair-response-${id(3)}.json`,value=JSON.parse(x.repairArtifacts[name]);value.truncated=true;value.output="x".repeat(64000);x.repairArtifacts[name]=JSON.stringify(value);
  },
  "truncated structural response":x=>{
    const name=`memory-repair-response-${id(2)}.json`,value=JSON.parse(x.repairArtifacts[name]);value.truncated=true;value.output="x".repeat(64000);x.repairArtifacts[name]=JSON.stringify(value);x.repairArtifacts["structural-repair-response.json"]=JSON.stringify(value);
  },
  "rehashed different predecessor":x=>{
    const name="generation-original-plan.json",value=JSON.parse(x.repairArtifacts[name]);value.originalPlan.newMemories[0].content+="changed";value.originalPlanDigest=hash(JSON.stringify(value.originalPlan));x.repairArtifacts[name]=JSON.stringify(value);
  },
  "different final stored plan":x=>{x.plan.newMemories[0].content+="changed";},
};
for (const [name,mutate] of Object.entries(damage)) test(`source proof refuses ${name}`, () => {
  const input=repaired();mutate(input);refreshReceipt(input);
  const result=commandMemorySourceProof(input);
  expect(result.ready).toBe(false);
  expect(String(result.reason)).not.toContain("PRIVATE_ARTIFACT_MUST_NOT_APPEAR_IN_REASON");
});
