/** Opt-in actual Jev diagnosis on a frozen, public native-generated plan. */
import fs from 'node:fs/promises';
import {createJevJudge} from '../extensions/jev-learning';
const report=JSON.parse(await fs.readFile(new URL('./jev-native-approval-before-confirm-fix.json',import.meta.url),'utf8'));
const run=report.runs.find((r:{enabled:boolean})=>r.enabled);
const rejected=run.harnessRepairs[0];
const snapshot=run.snapshots.find((s:{runId:string})=>s.runId===rejected.identity.runId);
if(!snapshot)throw new Error('Archived frozen snapshot is missing');
const transport:unknown[]=[];
const judge=createJevJudge({enabled:true,defaultModel:'jev-1.13.0',fetch:async(input,init)=>{const response=await fetch(input,init);transport.push({request:JSON.parse(String(init?.body)),result:await response.clone().json()});return response;}});
const result=await judge.validate('harness',snapshot,rejected.rejectedPlan.operations,[]);
console.log(JSON.stringify({evidence:'real-jev-inference-over-archived-native-candidate',sourceArtifact:'jev-native-approval-before-confirm-fix.json',originalOutcome:'propose',originalReason:'uncertain',result,transport},null,2));
