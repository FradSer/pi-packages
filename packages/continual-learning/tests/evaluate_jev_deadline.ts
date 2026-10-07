/** Known public bilingual diagnostic; one paired run, no writes or adoption. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {createJevJudge,type JevTelemetry} from '../extensions/jev-learning';
import {validateHarnessPlan} from '../extensions/harness-consolidation';
import {readFrozenResearchManifest} from './frozen-research-manifest';
import {observeHarnessAnchorJudgments} from './jev-harness-citation-anchor-research';
import {summarizeActualReplayUsage} from './actual-candidate-replay';
import {deadlineResearchOptions,claimFrozenRequestHash,completeDeadlineArm,summarizeDeadlineStudy,type DeadlineArm} from './jev-deadline-research';
const base=new URL('./',import.meta.url),live=process.argv.includes('--live');
if(live===process.argv.includes('--preflight-only'))throw Error('Choose explicit research mode');
const hash=(v:Buffer|string)=>createHash('sha256').update(v).digest('hex');
interface Manifest {codeHashes:Record<string,string>;corpus:string;corpusSha256:string;model:string;requestBudget:number;paidExecutionAllowedNow:boolean;terminalPrerequisite:{report:string;sha256:string};preflightSha256?:string;localVerificationSha256?:string}
interface Sample {id:string;language:string;expectedAllow:boolean;snapshot:unknown;plan:{operations:unknown[];evidence?:unknown}}
const frozen=await readFrozenResearchManifest<Manifest>(new URL('jev-deadline-study-manifest.json',base)),m=frozen.value;
if(m.model!=='jev-1.13.0'||m.requestBudget!==96)throw Error('Research configuration drift');
if(hash(await fs.readFile(new URL(m.terminalPrerequisite.report,base)))!==m.terminalPrerequisite.sha256)throw Error('Terminal prerequisite drift');
const corpus=await fs.readFile(new URL(m.corpus,base));if(hash(corpus)!==m.corpusSha256)throw Error('Frozen corpus changed');
const samples:Sample[]=JSON.parse(corpus.toString());
if(samples.length!==24||samples.filter(r=>r.expectedAllow).length!==12||samples.filter(r=>r.language==='en').length!==12||samples.filter(r=>r.language==='zh').length!==12)throw Error('Corpus coverage drift');
for(const row of samples)if(typeof row.expectedAllow!=='boolean'||validateHarnessPlan(row.plan,{snapshot:row.snapshot,snapshotText:JSON.stringify(row.snapshot),automatic:true,requireEvidence:true,requireCases:true}).length)throw Error('Research plan is not parent valid');
const preflightUrl=new URL('jev-deadline-preflight.json',base);
let preflight: {rows:Row[];fixtureRequests:number}|undefined;
if(live){
 if(m.paidExecutionAllowedNow!==true||!process.env.TYPESAFE_API_KEY||!m.preflightSha256||!m.localVerificationSha256)throw Error('Paid prerequisites incomplete');
 const bytes=await fs.readFile(preflightUrl);
 if(hash(bytes)!==m.preflightSha256||hash(await fs.readFile(new URL('jev-deadline-local-verification.json',base)))!==m.localVerificationSha256)throw Error('Frozen paid gate changed');
 preflight=JSON.parse(bytes.toString());
 if(preflight?.fixtureRequests!==m.requestBudget||preflight.rows.length!==samples.length||preflight.rows.some(r=>!r.arms.before.complete||!r.arms.after.complete))throw Error('Incomplete offline preflight');
}
const output=new URL(live?'jev-deadline-real-results.json':'jev-deadline-preflight.json',base);
const reserve=await fs.open(new URL(output.href+'.reservation'),'wx');await reserve.writeFile(JSON.stringify({manifestSha256:frozen.sha256,requestBudget:m.requestBudget}));await reserve.close();
type NumericObservation=ReturnType<typeof observeHarnessAnchorJudgments>;
interface Observation extends NumericObservation {wireRequestSha256:string;wireBytes:number;durationMs:number;status?:number;failure?:'aborted'|'transport';inputTokens?:number;outputTokens?:number}
interface Arm extends DeadlineArm {telemetry:JevTelemetry;observations:Observation[]}
interface Row {id:string;language:string;expectedAllow:boolean;arms:{before:Arm;after:Arm}}
const rows:Row[]=[],attempts:{id:string;arm:string;observation:Observation}[]=[];
const completedArms:{id:string;arm:string;result:Arm}[]=[];
let requests=0;
async function checkpoint(){const temp=new URL(output.href+'.checkpoint.tmp');await fs.writeFile(temp,JSON.stringify({manifestSha256:frozen.sha256,requests,rows,completedArms,attempts},null,2)+'\n');await fs.rename(temp,new URL(output.href+'.checkpoint'));}
try{
 for(const [index,sample]of samples.entries()){
  const arms:Partial<Record<'before'|'after',Arm>>={};
  for(const arm of (index%2?['after','before']:['before','after']) as ('before'|'after')[]){
   const observations:Observation[]=[];
   const remaining=live?[...preflight!.rows[index].arms[arm].wireRequestHashes]:[];
   const judge=createJevJudge({...deadlineResearchOptions(arm),apiKey:live?process.env.TYPESAFE_API_KEY:'fixture-only',fetch:async(url,init)=>{
    if(String(url)!=='https://api.typesafe.ai/v1/systemone')throw Error('Frozen endpoint changed');
    const body=String(init?.body);if(requests>=m.requestBudget||Buffer.byteLength(body)>64000)throw Error('Unchanged research bounds');
    if(live)claimFrozenRequestHash(remaining,hash(body));
    requests++;
    const request=JSON.parse(body),started=Date.now();
    const observation:Observation={valid:false,modelVerified:false,judgments:[],wireRequestSha256:hash(body),wireBytes:Buffer.byteLength(body),durationMs:0};
    observations.push(observation);attempts.push({id:sample.id,arm,observation});
    try{
     let response:Response;
     if(live)response=await fetch(url,init);
     else{
      const answers=Object.fromEntries(Object.entries(request.questions).map(([key,value])=>{
       const q=value as {type:string;criteria:Record<string,unknown>},label=key.startsWith('authority_')?'lasting':key.startsWith('family_')?'authorized':key.startsWith('counter_')?'compatible':'faithful';
       if(q.type!=='choice'||!Object.hasOwn(q.criteria,label))throw Error('Unexpected original primitive');
       return [key,{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))}];
      }));response=new Response(JSON.stringify({model:m.model,answers,usage:{input_tokens:0,output_tokens:0}}));
     }
     observation.status=response.status;
     const raw:unknown=await response.clone().json();Object.assign(observation,observeHarnessAnchorJudgments(request,raw,m.model));
     if(raw&&typeof raw==='object'&&'model'in raw&&raw.model===m.model&&'usage'in raw){
      const usage=raw.usage as {input_tokens?:unknown;output_tokens?:unknown};
      if(usage&&Number.isSafeInteger(usage.input_tokens)&&Number(usage.input_tokens)>=0)observation.inputTokens=Number(usage.input_tokens);
      if(usage&&Number.isSafeInteger(usage.output_tokens)&&Number(usage.output_tokens)>=0)observation.outputTokens=Number(usage.output_tokens);
     }
     return response;
    }catch(error){observation.failure=init?.signal?.aborted?'aborted':'transport';throw error;}
    finally{observation.durationMs=Date.now()-started;}
   }});
   const result=await judge.validate('harness',sample.snapshot,sample.plan.operations,[],undefined,sample.plan.evidence),t=result.telemetry;
   const complete=completeDeadlineArm(t,observations);
   const wireRequestHashes=observations.map(o=>o.wireRequestSha256);
   if(live&&remaining.length)throw Error('Original wire preflight incomplete');
   if(live&&JSON.stringify([...wireRequestHashes].sort())!==JSON.stringify([...preflight!.rows[index].arms[arm].wireRequestHashes].sort()))throw Error('Original wire differs from offline preflight');
   arms[arm]={decision:result.decision,complete,durationMs:t.durationMs,wireRequestHashes,telemetry:t,observations};
   completedArms.push({id:sample.id,arm,result:arms[arm]});
   await checkpoint();
  }
  rows.push({id:sample.id,language:sample.language,expectedAllow:sample.expectedAllow,arms:arms as Row['arms']});
  await checkpoint();console.log(JSON.stringify({completedSamples:rows.length,requests}));
 }
 await frozen.verify();if(hash(await fs.readFile(new URL(m.corpus,base)))!==m.corpusSha256)throw Error('Frozen corpus changed during study');
 const comparison=summarizeDeadlineStudy(rows);
 if(!comparison.identicalWireRequests||requests!==m.requestBudget)throw Error('Incomplete paired wire coverage');
 const usage=summarizeActualReplayUsage(rows.flatMap(r=>[r.arms.before.telemetry,r.arms.after.telemetry]),m.model);
 const knownWireInputTokens=attempts.reduce((n,v)=>n+(v.observation.inputTokens??0),0);
 const report={evidence:live?'real-jev-known-public-paired-deadline-diagnostic':'offline-forced-answer-deadline-preflight',manifestSha256:frozen.sha256,codeHashes:m.codeHashes,corpusSha256:m.corpusSha256,externalRequests:live?requests:0,fixtureRequests:live?0:requests,requestBudget:m.requestBudget,...comparison,successRuleMet:live&&comparison.successRuleMet,...usage,knownWireInputTokens,knownWireEstimatedCostUsd:knownWireInputTokens*.042/1000000,rows,attempts,productionWrites:0,adopted:false,goalComplete:false,limits:['Known previously queried corpus; not heldout or Docker/full-workflow improvement.','Only per-request deadline differs; exact wire hashes verified against offline preflight and paired arm.','One paid run, alternating arm order, no favorable retry or threshold relaxation.','Missing judgments separated from completed semantic errors; failed/late missing usage is unknown, account billing unverified.','Forced offline answers prove wiring only and never quality; no mutation queue or apply.']};
 await fs.writeFile(output,JSON.stringify(report,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({requests,...comparison,successRuleMet:report.successRuleMet,...usage,knownWireInputTokens}));
}finally{await checkpoint();}
