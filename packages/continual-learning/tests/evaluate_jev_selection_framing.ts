/** Frozen paired selection research; never a write or production adoption. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {createJevJudge} from '../extensions/jev-learning';
import {loadSelectionFramingJudge} from './jev-selection-framing-shadow';
const base=new URL('./',import.meta.url),live=process.argv.includes('--live');
if(live===process.argv.includes('--preflight-only'))throw new Error('Choose explicit research mode');
const split=process.argv.includes('--heldout')?'heldout':'development';
const manifest=JSON.parse(await fs.readFile(new URL(`jev-selection-framing-${split}-manifest.json`,base),'utf8')) as {codeHashes:Record<string,string>;requestBudget:number;model:string;samples:{id:string;evidence:unknown;memoryOnly:boolean;expected:{memory:boolean;harness:boolean}}[]};
const hash=(s:Buffer)=>createHash('sha256').update(s).digest('hex');
async function verify(){for(const [file,digest]of Object.entries(manifest.codeHashes))if(hash(await fs.readFile(new URL(file,base)))!==digest)throw new Error('Frozen research source changed');}
await verify();if(live&&!process.env.TYPESAFE_API_KEY)throw new Error('Real inference requires configured credential');
const output=new URL(`jev-selection-framing-${split}-${live?'real-results':'preflight'}.json`,base);
// Reservation persists across failures: absence of final output never allows paid restart.
const reservation=await fs.open(new URL(output.href+'.reservation'),'wx');await reservation.writeFile(JSON.stringify({startedAt:new Date().toISOString(),requestBudget:manifest.requestBudget}));await reservation.close();
const research=await loadSelectionFramingJudge();let requests=0;
const results:{id:string;arm:string;selection:unknown;telemetry:unknown;expected:unknown;answers:Record<string,number>;wireStatus?:number}[]=[];
try{for(const row of manifest.samples)for(const arm of ['before','after']){
 const factory=arm==='before'?createJevJudge:research.createJevJudge;
 const answers:Record<string,number>={};let wireStatus:number|undefined;
 const judge=factory({enabled:true,apiKey:live?process.env.TYPESAFE_API_KEY:'fixture-only',defaultModel:manifest.model,scopes:['selection'],fetch:async(url,init)=>{
  if(requests>=manifest.requestBudget||Buffer.byteLength(String(init?.body))>64000)throw new Error('Research bounds exceeded');requests++;
  const response=live?await fetch(url,init):new Response(JSON.stringify({model:manifest.model,answers:{memory:{type:'noul',noul:.99},harness:{type:'noul',noul:.99}},usage:{input_tokens:0,output_tokens:0}}));wireStatus=response.status;
  if(response.ok){const raw=await response.clone().json() as {answers?:Record<string,{type?:unknown;noul?:unknown}>};for(const key of ['memory','harness']){const a=raw.answers?.[key];if(a?.type==='noul'&&typeof a.noul==='number'&&Number.isFinite(a.noul)&&a.noul>=0&&a.noul<=1)answers[key]=a.noul;}}
  return response;
 }});
 const verdict=await judge.select(row.evidence,[],row.memoryOnly);results.push({id:row.id,arm,expected:row.expected,...verdict,answers,wireStatus});
 await fs.writeFile(new URL(output.href+'.checkpoint'),JSON.stringify({requests,results},null,2)+'\n');
}}finally{await research.dispose();}
await verify();
const metrics:Record<string,{correct:number;wrong:number;fallback:number;falseLearningDirections:number;missedLearningDirections:number;knownInputTokens:number;knownEstimatedCostUsd:number}>={};
for(const arm of ['before','after']){const m={correct:0,wrong:0,fallback:0,falseLearningDirections:0,missedLearningDirections:0,knownInputTokens:0,knownEstimatedCostUsd:0};for(const row of results.filter(x=>x.arm===arm)){const s=row.selection as {memory:boolean;harness:boolean}|null,e=row.expected as {memory:boolean;harness:boolean};if(!s)m.fallback++;else {if(s.memory===e.memory&&s.harness===e.harness)m.correct++;else m.wrong++;for(const key of ['memory','harness'] as const){if(s[key]&&!e[key])m.falseLearningDirections++;if(!s[key]&&e[key])m.missedLearningDirections++;}}const t=row.telemetry as {inputTokens?:number;knownInputTokens?:number;estimatedCostUsd?:number;knownEstimatedCostUsd?:number};m.knownInputTokens+=t.inputTokens??t.knownInputTokens??0;m.knownEstimatedCostUsd+=t.estimatedCostUsd??t.knownEstimatedCostUsd??0;}metrics[arm]=m;}
const report={evidence:live?'real-paired-selection-framing':'offline-mock-selection-framing',split,externalRequests:live?requests:0,fixtureRequests:live?0:requests,requestBudget:manifest.requestBudget,metrics,results,productionWrites:0,adopted:false,limitations:['Selector study only, not candidate validation or end-to-end workflow quality.','Fallback is recorded separately, not counted as wrong accepted learning or successful learned output.','Existing Memory metadata ranking absent in this bounded study.','No thresholds, privacy, permission, timeout or retry changes.']};
await fs.writeFile(output,JSON.stringify(report,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({split,requests,metrics}));
