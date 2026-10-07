/** Read-only original-input research. Never returns an apply authority. */
import {extractChildPlan,MAX_STDOUT_BYTES,MAX_JSONL_LINES,MAX_JSONL_LINE_BYTES,MAX_PLAN_BYTES} from '../extensions/consolidation-run';
import {validateHarnessPlan,type HarnessConsolidationPlan,type HarnessPlanValidationOptions} from '../extensions/harness-consolidation';
const record=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
export const BINDING_INSTRUCTIONS=[
  "Copy each retained operation's op and rule.id verbatim from immutableRetainedBindings. Do not derive or rename identities.",
  "All evidence properties other than index must remain unchanged. Copy the complete original evidence objects, including source, quote, count and eventIndex where supplied; only reindex index to the retained operation's new position. Do not shorten quotes or omit citation properties.",
];
const anchor='Return exactly one JSON object and no prose. Preserve the supplied identity, retained rule identities and their exact evidence quotes. Omit an unsupported operation rather than invent lasting authorization; reindex retained evidence/report. The parent retains omissions for review. Do not add a new rule identity.';
export function addHarnessRepairBindings(before:string):string {
  const split=before.lastIndexOf('\n'),prefix=before.slice(0,split),payload:unknown=JSON.parse(before.slice(split+1));
  if(!record(payload)||JSON.stringify(payload)!==before.slice(split+1)||Object.keys(payload).join(',')!=='identity,errors,rejectedPlan'
    ||prefix.split(anchor).length!==2||!record(payload.rejectedPlan)||!Array.isArray(payload.rejectedPlan.operations)||!Array.isArray(payload.rejectedPlan.evidence))throw Error('Original repair format changed');
  const plan=payload.rejectedPlan,evidence=plan.evidence as unknown[];
  const bindings=(plan.operations as unknown[]).map((op,originalIndex)=>{
    if(!record(op)||typeof op.op!=='string'||!record(op.rule)||typeof op.rule.id!=='string')throw Error('Original operation identity missing');
    return {originalIndex,op:op.op,ruleId:op.rule.id,evidence:evidence.filter(e=>record(e)&&e.index===originalIndex)};
  });
  return prefix.replace(anchor,[anchor,...BINDING_INSTRUCTIONS].join('\n'))+'\n'+JSON.stringify({identity:payload.identity,immutableRetainedBindings:bindings,errors:payload.errors,rejectedPlan:plan});
}
export type RepairCheck={category:'ready';plan:HarnessConsolidationPlan}|{category:'extraction'|'structure'|'empty'|'identity-mismatch'|'citation-mismatch'};
export function checkFrozenHarnessRepair(stdout:string,original:HarnessConsolidationPlan,options:HarnessPlanValidationOptions):RepairCheck {
  const extracted=extractChildPlan<HarnessConsolidationPlan>(stdout,{expectedIdentity:{runId:original.runId!,scopeDigest:original.scopeDigest!,artifactHash:original.artifactHash!},maxOutputBytes:MAX_STDOUT_BYTES,maxLines:MAX_JSONL_LINES,maxLineBytes:MAX_JSONL_LINE_BYTES,maxPlanBytes:MAX_PLAN_BYTES});
  if(!extracted.ok)return {category:'extraction'};
  let plan=extracted.plan,errors=validateHarnessPlan(plan,options);
  if(errors.length&&errors.every(e=>/^report(?:\[|\s|\.)/.test(e))){const {report:_report,...rest}=plan;plan=rest;errors=validateHarnessPlan(plan,options);}
  if(errors.length||!Array.isArray(original.operations)||!Array.isArray(plan.operations))return {category:'structure'};
  if(!plan.operations.length)return {category:'empty'};
  const identity=(op:unknown)=>record(op)&&record(op.rule)?`${op.op}:${op.rule.id}`:undefined;
  const citations=(values:unknown,index:number)=>JSON.stringify((Array.isArray(values)?values:[]).filter(e=>record(e)&&e.index===index).map(e=>JSON.stringify(Object.entries(e).filter(([key])=>key!=='index').sort(([a],[b])=>a.localeCompare(b)))).sort());
  for(const [index,op]of plan.operations.entries()){
    const previous=original.operations.findIndex(v=>identity(v)===identity(op));
    if(previous<0)return {category:'identity-mismatch'};
    if(citations(original.evidence,previous)!==citations(plan.evidence,index))return {category:'citation-mismatch'};
  }
  return {category:'ready',plan};
}
