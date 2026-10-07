/** Same original candidates with disabled/current gate. No regeneration/writes. */
import fs from 'node:fs/promises';
import {readFrozenResearchManifest} from './frozen-research-manifest';
import {loadActualCandidateReplay,summarizeActualReplayUsage,type ActualReplayInput} from './actual-candidate-replay';
import {createJevJudge,type JevTelemetry} from '../extensions/jev-learning';
const live=process.argv.includes('--live');if(live===process.argv.includes('--preflight-only'))throw new Error('Choose explicit actual replay mode');
const base=new URL('./',import.meta.url);
interface Manifest {codeHashes:Record<string,string>;inputs:ActualReplayInput[];model:string;requestBudget:number}
const frozen=await readFrozenResearchManifest<Manifest>(new URL('jev-actual-candidate-paired-study-manifest.json',base)),m=frozen.value;
if(m.inputs.some(i=>typeof i.expectedAllow!=='boolean'))throw new Error('Missing frozen plan label');
const inputs=await Promise.all(m.inputs.map(loadActualCandidateReplay));
// All original snapshots/candidates undergo production guard before ANY paid call.
let mockPreflightRequests=0;
for(const [i,input]of inputs.entries()){
 let calls=0;const judge=createJevJudge({enabled:true,apiKey:'fixture-only',defaultModel:m.model,scopes:['memory','harness'],allowPrivateMemory:true,fetch:async()=>{calls++;throw new Error('Offline actual replay preflight');}});
 await judge.validate(m.inputs[i].stage,input.snapshot,input.candidates,[],undefined,input.citations);
 if(!calls)throw new Error('Actual replay original input denied before transport');mockPreflightRequests+=calls;
}
if(live&&!process.env.TYPESAFE_API_KEY)throw new Error('Missing real inference credential');
const output=new URL(`jev-actual-candidate-paired-${live?'real-results':'preflight'}.json`,base);
await fs.writeFile(new URL(output.href+'.reservation'),JSON.stringify({startedAt:new Date().toISOString(),requestBudget:m.requestBudget})+'\n',{flag:'wx'});
let requests=0;
const off=createJevJudge({enabled:false,fetch:async()=>{throw new Error('Disabled gate cannot transport');}});
const on=createJevJudge({enabled:true,apiKey:live?process.env.TYPESAFE_API_KEY:'fixture-only',defaultModel:m.model,scopes:['memory','harness'],allowPrivateMemory:true,fetch:async(url,init)=>{
 if(requests>=m.requestBudget||Buffer.byteLength(String(init?.body))>64000)throw new Error('Actual replay request bound');requests++;
 if(live)return fetch(url,init);
 const body=JSON.parse(String(init?.body));const answers=Object.fromEntries(Object.entries(body.questions).map(([k,q])=>{const question=q as {type:string;criteria:Record<string,unknown>};const label=k.startsWith('supported')?'grounded':k.startsWith('relation')?'unrelated':k.startsWith('counter')?'compatible':k.startsWith('expands')?'same':k.startsWith('explanation')?'faithful':k.startsWith('authority')?'lasting':'authorized';return [k,question.type==='noul'?{type:'noul',noul:.99}:{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(question.criteria).map(key=>[key,key===label?1:0]))}];}));
 return new Response(JSON.stringify({model:m.model,answers,usage:{input_tokens:0,output_tokens:0}}));
}});
function safeTelemetry(t:JevTelemetry){return {...t,...(t.model!==undefined&&t.model!==m.model?{model:undefined,modelVerified:false}:{modelVerified:t.model===m.model})};}
interface ReplayRow {id:string;stage:'memory'|'harness';expectedAllow:boolean|undefined;candidateCount:number;knownUnsafeIndexes:number[];unlabeledCandidateCount:number;baseline:{decision:'allow'|'propose';telemetry:ReturnType<typeof safeTelemetry>};current:{decision:'allow'|'propose';telemetry:ReturnType<typeof safeTelemetry>};semanticComplete:boolean}
const rows:ReplayRow[]=[];
for(const [i,input]of inputs.entries()){
 const spec=m.inputs[i];const baseline=await off.validate(spec.stage,input.snapshot,input.candidates,[],undefined,input.citations);
 const judged=await on.validate(spec.stage,input.snapshot,input.candidates,[],undefined,input.citations);
 const t=judged.telemetry;
 const semanticComplete=t.model===m.model&&t.requestCount!==undefined&&t.requestCount>0&&t.completedRequests===t.requestCount&&t.evidenceWindows!==undefined&&t.evidenceEntries!==undefined&&t.completedWindows===t.evidenceWindows&&t.coveredEntries===t.evidenceEntries&&typeof t.inputTokens==='number'&&['supported','unsupported','uncertain','scope-expansion','duplicate','conflict'].includes(t.reason);
 rows.push({id:spec.id,stage:spec.stage,expectedAllow:spec.expectedAllow,candidateCount:input.candidates.length,knownUnsafeIndexes:spec.knownUnsafeIndexes??[],unlabeledCandidateCount:spec.expectedAllow===true?0:input.candidates.length-(spec.knownUnsafeIndexes?.length??0),baseline:{decision:baseline.decision,telemetry:safeTelemetry(baseline.telemetry)},current:{decision:judged.decision,telemetry:safeTelemetry(t)},semanticComplete});
 const checkpoint=new URL(output.href+'.checkpoint'),temp=new URL(output.href+'.checkpoint.tmp');await fs.writeFile(temp,JSON.stringify({requests,rows},null,2)+'\n');await fs.rename(temp,checkpoint);
}
await frozen.verify();for(const spec of m.inputs)await loadActualCandidateReplay(spec);
const metrics=(key:'baseline'|'current',values:typeof rows)=>({plans:values.length,falseAccepts:values.filter(r=>r.expectedAllow===false&&r[key].decision==='allow').length,falseHolds:values.filter(r=>r.expectedAllow===true&&r[key].decision==='propose').length});
const completeRows=rows.filter(r=>r.semanticComplete),usage=summarizeActualReplayUsage(rows.map(r=>r.current.telemetry),m.model);
const report={evidence:live?'real-same-actual-candidates-disabled-vs-current-jev':'offline-mock-same-actual-candidates-preflight',manifestSha256:frozen.sha256,codeHashes:m.codeHashes,externalRequests:live?requests:0,fixtureRequests:live?0:requests,mockPreflightRequests,requestBudget:m.requestBudget,operationalMetrics:{baseline:metrics('baseline',rows),current:metrics('current',rows)},completeSemanticMetrics:{baseline:metrics('baseline',completeRows),current:metrics('current',completeRows)},complete:completeRows.length===rows.length,incompletePlans:rows.length-completeRows.length,...usage,usageComplete:completeRows.length===rows.length,results:rows,productionWrites:0,limitations:['Four known original generated plans:3unsafe Harness plans and1valid Memory plan containing3candidates, not7independent samples.','Disabled semantic gate is a local no-inference counterfactual on same candidates, not a second live generator or Docker workflow.','Unlabeled operations inside unsafe mixed plans cannot be counted as harmless accepted or correctly held; whole-plan hold may suppress valid intent.','No original candidate rewrites, source relabel, regeneration, model favorable retry or threshold change.','Candidate replay is not full-workflow quality superiority.']};
await fs.writeFile(output,JSON.stringify(report,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({requests,complete:report.complete,operationalMetrics:report.operationalMetrics,completeSemanticMetrics:report.completeSemanticMetrics,knownInputTokens:report.knownInputTokens,knownEstimatedCostUsd:report.knownEstimatedCostUsd}));
