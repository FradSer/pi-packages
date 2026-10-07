/** Hash-bound read-only paired research; never grants write permission. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {createJevJudge, type JevJudge} from '../extensions/jev-learning';
import {type SelectedMemory} from '../extensions/incremental-learning';
import {normalizeNewMemoryProposals} from '../extensions/consolidation-run';
import {validateHarnessPlan} from '../extensions/harness-consolidation';
import {counterEvidenceRequest} from './jev-counter-evidence-shadow';
import {controlledJevAnswers} from './jev-controlled-diagnostics';
import {pairedPlanMetrics, pairedPlansComplete} from './jev-paired-metrics';
const live=process.argv.includes('--live');
if(live&&process.argv.includes('--preflight-only'))throw new Error('Research modes are mutually exclusive');
if(!live&&!process.argv.includes('--preflight-only'))throw new Error('Explicit research mode required');
const split=process.argv.includes('--heldout')?'heldout':'development';
const hash=(s:string)=>createHash('sha256').update(s).digest('hex');
const study=JSON.parse(await fs.readFile(new URL(`./jev-counter-${split}-study-manifest.json`,import.meta.url),'utf8')) as {corpusSha256:string;codeHashes:Record<string,string>};
async function verifyCode(){for(const [file,digest]of Object.entries(study.codeHashes))if(hash(await fs.readFile(new URL(file,import.meta.url),'utf8'))!==digest)throw new Error('Frozen research source changed');}
await verifyCode();
interface Input {id:string;stage:'memory'|'harness';expectedAllow:boolean|null;existing:SelectedMemory[];snapshot:unknown;plan:{operations:unknown[];evidence?:unknown};snapshotHash?:string;planHash?:string}
const corpusText=await fs.readFile(new URL(`./fixtures/jev-counter-${split}-corpus.json`,import.meta.url),'utf8');
if(hash(corpusText)!==study.corpusSha256)throw new Error('Frozen corpus changed');
const inputs:Input[]=JSON.parse(corpusText);
if(split==='development')for(const name of ['jev-finite-authority-r9-regression-manifest.json','jev-counter-memory-r9-manifest.json']){
 const manifest=JSON.parse(await fs.readFile(new URL(`./${name}`,import.meta.url),'utf8'));const texts:Record<string,string>={};
 for(const [key,value]of Object.entries(manifest.files as Record<string,{path:string;sha256:string}>)){
  texts[key]=await fs.readFile(value.path,'utf8');if(hash(texts[key])!==value.sha256)throw new Error('Frozen real artifact changed');
 }
 const stage=manifest.stage??'harness';const original=JSON.parse(texts.plan??texts.history);
 const plan=stage==='memory'?{operations:normalizeNewMemoryProposals(original,JSON.parse(texts.snapshot))}:original.proposal;
 if(stage==='memory'&&(original.operations?.length||original.selected?.length))throw new Error('Real Memory replay requires unchanged new-only plan');
 inputs.push({id:manifest.id,stage,expectedAllow:null,existing:stage==='memory'?JSON.parse(texts.dossier).selectedMemories:[],snapshot:JSON.parse(texts.snapshot),plan});
}
for(const row of inputs){
 row.snapshotHash=hash(JSON.stringify(row.snapshot));row.planHash=hash(JSON.stringify(row.plan));
 if(!row.plan.operations.length)throw new Error('Empty research plan');
 if(row.stage==='harness'){
  if(validateHarnessPlan(row.plan,{snapshot:row.snapshot,snapshotText:JSON.stringify(row.snapshot),automatic:true,requireEvidence:true,requireCases:true}).length)throw new Error('Parent Harness validation failed');
 }else if(JSON.stringify(normalizeNewMemoryProposals({newMemories:row.plan.operations},row.snapshot))!==JSON.stringify(row.plan.operations))throw new Error('Parent Memory normalization changed input');
}
if(!live){
 let fixtureRequests=0;
 for(const row of inputs)for(const arm of ['before','after']){
  const judge=createJevJudge({enabled:true,apiKey:'fixture-only',defaultModel:'jev-1.13.0',scopes:['memory','harness'],allowPrivateMemory:true,fetch:async(_url,init)=>{
   const original=JSON.parse(String(init?.body));const request=arm==='after'?counterEvidenceRequest(original):original;
   if(Buffer.byteLength(JSON.stringify(request))>64_000)throw new Error('Offline wire cap exceeded');
   fixtureRequests++;if(fixtureRequests>256)throw new Error('Offline study budget exceeded');
   const answers:Record<string,unknown>={};
   for(const [key,value]of Object.entries(request.questions as Record<string,{type:string;criteria:Record<string,unknown>}>)){
    if(value.type==='noul')answers[key]={type:'noul',noul:.99};
    else {const label=['compatible','same','grounded','lasting','faithful','authorized','unrelated'].find(x=>Object.hasOwn(value.criteria,x));
     if(!label)throw new Error('Unknown offline question');
     answers[key]={type:'choice',choice:label,confidence:.99,probabilities:Object.fromEntries(Object.keys(value.criteria).map(x=>[x,x===label?1:0]))};}
   }
   return new Response(JSON.stringify({model:'jev-1.13.0',answers,usage:{input_tokens:0,output_tokens:0}}));
  }});
  const result=await judge.validate(row.stage,row.snapshot,row.plan.operations,row.existing,undefined,row.stage==='harness'?row.plan.evidence:undefined);
  if(result.telemetry.reason!=='supported'||result.telemetry.requestCount!==result.telemetry.completedRequests
    ||result.telemetry.evidenceEntries!==result.telemetry.coveredEntries)throw new Error('Offline production path incomplete');
 }
 console.log(JSON.stringify({samples:inputs.length,labeledSamples:inputs.filter(r=>r.expectedAllow!==null).length,outboundRequests:0,fixtureRequests}));process.exit(0);
}
if(!process.env.TYPESAFE_API_KEY)throw new Error('Real inference requires credentials');
const outputIndex=process.argv.indexOf('--output');const output=outputIndex>=0?process.argv[outputIndex+1]:undefined;
if(!output)throw new Error('Live research requires output before inference');
const reservation=await fs.open(output,'wx');await reservation.writeFile('{"complete":false,"evidence":"research-started-incomplete"}\n');await reservation.close();
const MAX_REQUESTS=256;let outboundRequests=0;
type Verdict=Awaited<ReturnType<JevJudge['validate']>>;
const results:(Input&{before:Verdict;after:Verdict})[]=[];
const diagnostics:{id:string;arm:string;answers:Record<string,unknown>}[]=[];
const durations:Record<string,number[]>={before:[],after:[]};
for(const row of inputs){
 const outcomes:Verdict[]=[];
 for(const arm of ['before','after']as const){
  const judge=createJevJudge({enabled:true,defaultModel:'jev-1.13.0',scopes:['memory','harness'],allowPrivateMemory:true,fetch:async(url,init)=>{
   const original=JSON.parse(String(init?.body));const request=arm==='after'?counterEvidenceRequest(original):original;
   const body=JSON.stringify(request);
   if(Buffer.byteLength(body)>64_000)throw new Error('Unchanged wire cap exceeded');
   if(outboundRequests>=MAX_REQUESTS)throw new Error('Study request budget exhausted');outboundRequests++;
   const response=await fetch(url,{...init,body});
   if(response.ok)diagnostics.push({id:row.id,arm,answers:controlledJevAnswers(await response.clone().json(),request.questions)});
   return response;
  }});
  const verdict=await judge.validate(row.stage,row.snapshot,row.plan.operations,row.existing,undefined,row.stage==='harness'?row.plan.evidence:undefined);
  outcomes.push(verdict);durations[arm].push(verdict.telemetry.durationMs);
 }
 results.push({...row,before:outcomes[0],after:outcomes[1]});
}
await verifyCode();
const labeled=results.filter((r):r is typeof r&{expectedAllow:boolean}=>r.expectedAllow!==null);
const complete=pairedPlansComplete(results.map(r=>({...r,expectedAllow:r.expectedAllow??false})));
const telemetry=results.flatMap(r=>[r.before.telemetry,r.after.telemetry]);
const report={evidence:'real-jev-counter-evidence-only-paired-research',split,productionWriteEligible:false,complete,samples:results.length,labeledSamples:labeled.length,
 corpusSha256:hash(corpusText),codeHashes:study.codeHashes,outboundRequests,requestBudget:MAX_REQUESTS,durationsMs:durations,
 metrics:{before:pairedPlanMetrics(labeled,'before'),after:pairedPlanMetrics(labeled,'after')},
 knownInputTokens:telemetry.reduce((n,r)=>n+(r.inputTokens??r.knownInputTokens??0),0),
 knownEstimatedCostUsd:telemetry.reduce((n,r)=>n+(r.estimatedCostUsd??r.knownEstimatedCostUsd??0),0),
 results:results.map(({snapshot:_s,plan:_p,existing:_e,...r})=>r),diagnostics};
await fs.writeFile(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({complete,samples:results.length,labeledSamples:labeled.length,outboundRequests,metrics:report.metrics,knownInputTokens:report.knownInputTokens,knownEstimatedCostUsd:report.knownEstimatedCostUsd}));
if(!complete)process.exitCode=1;
