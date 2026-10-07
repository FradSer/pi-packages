/** Read-only hash-bound original candidates; never a parent apply plan. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {normalizeNewMemoryProposals} from '../extensions/consolidation-run';
import {validateHarnessPlan} from '../extensions/harness-consolidation';
export interface ActualReplayInput {id:string;stage:'memory'|'harness';format:'plan'|'proposal';plan:string;snapshot:string;planHash:string;snapshotHash:string;report?:string;reportHash?:string;expectedAllow?:boolean;knownUnsafeIndexes?:number[]}
const digest=(bytes:Buffer)=>createHash('sha256').update(bytes).digest('hex');
export async function loadActualCandidateReplay(input:ActualReplayInput):Promise<{snapshot:unknown;candidates:unknown[];citations?:unknown}> {
 const bytes=await Promise.all([fs.readFile(input.plan),fs.readFile(input.snapshot),...(input.report?[fs.readFile(input.report)]:[])]);
 if(digest(bytes[0])!==input.planHash||digest(bytes[1])!==input.snapshotHash||(input.report&&digest(bytes[2])!==input.reportHash))throw new Error('Frozen actual candidate source changed');
 const raw=JSON.parse(bytes[0].toString('utf8')),snapshot:unknown=JSON.parse(bytes[1].toString('utf8'));
 const plan=input.format==='proposal'?raw.proposal:raw;
 if(!plan||typeof plan!=='object'||Array.isArray(plan))throw new Error('Invalid frozen actual plan');
 if(input.stage==='harness'){
  if(validateHarnessPlan(plan,{snapshot,automatic:true,availableSkills:[]}).length)throw new Error('Actual Harness structural check failed');
  return {snapshot,candidates:plan.operations,citations:plan.evidence};
 }
 if(!Array.isArray(plan.operations)||plan.operations.length||!Array.isArray(plan.selected)||plan.selected.length)throw new Error('Actual Memory replay requires pure new unselected plan');
 const candidates=normalizeNewMemoryProposals(plan,snapshot,[]);
 if(!candidates.length||JSON.stringify(candidates)!==JSON.stringify(plan.newMemories))throw new Error('Actual Memory normalization changed');
 return {snapshot,candidates};
}

/** Keep the judge's known lower bounds; never apply a tariff to an unknown model. */
export function summarizeActualReplayUsage(values:readonly {model?:string;reason:string;inputTokens?:number;knownInputTokens?:number;estimatedCostUsd?:number;knownEstimatedCostUsd?:number}[],model:string) {
 let knownInputTokens=0,knownEstimatedCostUsd=0,unpricedInputTokens=0,unverifiedJudgeEstimatedCostUsd=0;
 for(const t of values){
  const tokens=t.inputTokens??t.knownInputTokens??0,estimate=t.estimatedCostUsd??t.knownEstimatedCostUsd;
  if(!Number.isSafeInteger(tokens)||tokens<0)throw new Error('Invalid judge known usage');
  if(estimate!==undefined&&(!Number.isFinite(estimate)||estimate<0))throw new Error('Invalid judge known estimate');
  knownInputTokens+=tokens;
  if(t.model===model&&t.reason!=='invalid-response'&&estimate!==undefined)knownEstimatedCostUsd+=estimate;
  else {unpricedInputTokens+=tokens;unverifiedJudgeEstimatedCostUsd+=estimate??0;}
 }
 return {knownInputTokens,knownEstimatedCostUsd,unpricedInputTokens,unverifiedJudgeEstimatedCostUsd};
}
