/** Same-host original-candidate transport diagnostic, never an apply queue. */
import fs from 'node:fs/promises';
import {appendFileSync,closeSync,openSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createJevJudge} from '../extensions/jev-learning';
import {DEFAULT_RULES} from '../extensions/guardrail-engine';
import {validateHarnessPlan} from '../extensions/harness-consolidation';
import {checkFrozenHarnessRepair} from './harness-binding-repair-research';
import {readFrozenResearchManifest} from './frozen-research-manifest';
import {originalTransportArm,originalTransportEndpoint,originalTransportWireGuard,verifyOriginalTransportWireSet,originalTransportForcedResponse,originalTransportObservation,originalTransportComplete,type OriginalTransportObservation} from './jev-original-transport-research';
const mode=process.argv[2],live=mode==='--live';if(!['--live','--preflight-only'].includes(mode))throw Error('Explicit mode required');
const base=new URL('./',import.meta.url),hash=(v:Buffer|string)=>createHash('sha256').update(v).digest('hex');
interface Manifest{codeHashes:Record<string,string>;paidExecutionAllowedNow:boolean;runtimeVersion:string;profile:string;profileSha256:string;wireDirectory:string;originalPreparation:string;originalPreparationSha256:string;originalStdout:string;originalStdoutSha256:string;requestBudget:number}
const frozen=await readFrozenResearchManifest<Manifest>(new URL('jev-original-transport-study-manifest.json',base)),m=frozen.value;
if(m.runtimeVersion!==process.version||m.requestBudget!==12)throw Error('Frozen transport runtime changed');
const input:{arm:string;outputPrefix:string;proxyURL?:string;expectedManifestSha256:string}=JSON.parse(await fs.readFile(process.argv[3],'utf8'));
if(input.expectedManifestSha256!==frozen.sha256)throw Error('Frozen matrix manifest changed');
const arm=originalTransportArm(input.arm),endpoint=originalTransportEndpoint(arm,input.proxyURL);
if(live&&(m.paidExecutionAllowedNow!==true||!process.env.TYPESAFE_API_KEY))throw Error('Paid original transport guard denied');
const profileText=await fs.readFile(new URL(m.profile,base)),prepText=await fs.readFile(new URL(m.originalPreparation,base));
if(hash(profileText)!==m.profileSha256||hash(prepText)!==m.originalPreparationSha256)throw Error('Frozen original metadata changed');
const profile=JSON.parse(profileText.toString()),prep=JSON.parse(prepText.toString());
for(const row of profile.wires){const file=m.wireDirectory+'/wire-'+row.index+'.json',stat=await fs.lstat(file);if(stat.isSymbolicLink()||(stat.mode&0o777)!==0o600||hash(await fs.readFile(file))!==row.sha256)throw Error('Frozen original wire changed');}
const directory=prep.originalRunDirectory,snapshotText=await fs.readFile(directory+'/snapshot.json','utf8'),snapshot=JSON.parse(snapshotText);
const before=await fs.readFile(directory+'/harness-repair.md','utf8'),original=JSON.parse(before.split('\n').at(-1)!).rejectedPlan;
const manifestText=await fs.readFile(directory+'/manifest.json','utf8'),manifest=JSON.parse(manifestText),stdout=await fs.readFile(m.originalStdout,'utf8');
if(hash(snapshotText)!==profile.snapshotSha256||hash(before)!==prep.originalTaskSha256||hash(manifestText)!==prep.originalManifestSha256||hash(stdout)!==m.originalStdoutSha256)throw Error('Frozen original input changed');
const options={snapshot,snapshotText,automatic:true,availableSkills:[],targetSource:'project' as const,layers:[{source:'built-in defaults',rules:DEFAULT_RULES.map(v=>({...v}))}],learnedRules:{}};
if(validateHarnessPlan(original,options).length)throw Error('Original plan invalid');
const checked=checkFrozenHarnessRepair(stdout,original,options);if(checked.category!=='ready'||hash(JSON.stringify(checked.plan))!==profile.candidateSha256)throw Error('Original candidate changed');
if(!Array.isArray(checked.plan.operations))throw Error('Original operations invalid');
const parentScope=Object.freeze({repoRoot:manifest.cwd,runId:manifest.runId,scopeKey:manifest.scopeKey,evidenceDigest:hash(JSON.stringify(snapshot))});
const exactHashes:string[]=[];
const config={enabled:true,baseURL:endpoint,defaultModel:'jev-1.13.0',scopes:['harness' as const],allowPrivateMemory:true,timeout:arm.timeout,retry:{maxRetries:0},logLevel:'off' as const};
// Reconstruct the whole current SDK collection before releasing any paid fetch.
const preSend=await createJevJudge({...config,apiKey:'fixture-only',fetch:async(url,init)=>{
 if(String(url)!==endpoint+'/v1/systemone')throw Error('Frozen original endpoint changed');
 const body=String(init?.body);if(Buffer.byteLength(body)>64000)throw Error('Original wire bound exceeded');
 exactHashes.push(hash(body));return originalTransportForcedResponse(JSON.parse(body));
}}).validate('harness',snapshot,checked.plan.operations,[],undefined,checked.plan.evidence,parentScope);
verifyOriginalTransportWireSet(profile.wires.map((r:{sha256:string})=>r.sha256),exactHashes);
if(preSend.telemetry.completedRequests!==3||preSend.telemetry.coveredEntries!==17||preSend.telemetry.completedWindows!==2)throw Error('Incomplete pre-send original review');
await frozen.verify();
const claim=originalTransportWireGuard(profile.wires.map((r:{sha256:string})=>r.sha256));
interface Observation extends OriginalTransportObservation{index:number;wireRequestSha256:string;wireBytes:number;durationMs:number;status?:number;failure?:'aborted'|'transport'}
const observations:Observation[]=[];
const journal=input.outputPrefix+'-attempts.jsonl';closeSync(openSync(journal,'wx',0o600));
const result=await createJevJudge({...config,apiKey:live?process.env.TYPESAFE_API_KEY:'fixture-only',fetch:async(url,init)=>{
 if(String(url)!==endpoint+'/v1/systemone')throw Error('Frozen original endpoint changed');
 const body=String(init?.body),digest=hash(body);if(Buffer.byteLength(body)>64000)throw Error('Original wire bound exceeded');claim(digest);
 const request=JSON.parse(body),started=Date.now(),index=observations.length;
 const observation:Observation={index,wireRequestSha256:digest,wireBytes:Buffer.byteLength(body),durationMs:0,valid:false,modelVerified:false,judgments:[]};
 observations.push(observation);appendFileSync(journal,JSON.stringify({event:'started',index,wireRequestSha256:digest,wireBytes:observation.wireBytes})+'\n');
 try{
  let response:Response;
  if(live)response=await fetch(url,init);
  else response=originalTransportForcedResponse(request);
  observation.status=response.status;Object.assign(observation,originalTransportObservation(request,await response.clone().json()));return response;
 }catch(error){observation.failure=init?.signal?.aborted?'aborted':'transport';throw error;}
 finally{observation.durationMs=Date.now()-started;appendFileSync(journal,JSON.stringify({event:'finished',...observation})+'\n');}
}}).validate('harness',snapshot,checked.plan.operations,[],undefined,checked.plan.evidence,parentScope);
await frozen.verify();
const identicalWireRequests=JSON.stringify(observations.map(v=>v.wireRequestSha256).sort())===JSON.stringify(profile.wires.map((v:{sha256:string})=>v.sha256).sort());
const knownInputTokens=observations.reduce((n,o)=>n+(o.modelVerified?o.inputTokens??0:0),0),usageResponses=observations.filter(o=>o.modelVerified&&o.inputTokens!==undefined&&o.outputTokens!==undefined).length;
const report={evidence:live?'real-original-large-transport-arm':'offline-original-large-transport-arm',arm:arm.id,route:arm.route,timeoutMs:arm.timeout,runtimeVersion:process.version,manifestSha256:frozen.sha256,candidateSha256:profile.candidateSha256,decision:result.decision,telemetry:result.telemetry,complete:originalTransportComplete(result.telemetry,observations),identicalWireRequests,preSendFixtureRequests:exactHashes.length,externalRequests:live?observations.length:0,fixtureRequests:live?0:observations.length,actualModelVerified:live&&observations.length===3&&observations.every(o=>o.modelVerified),knownInputTokens,knownEstimatedCostUsd:knownInputTokens*.042/1000000,usageResponses,missingUsageRequests:observations.length-usageResponses,observations,productionWrites:0,semanticGoldEstablished:false,adopted:false};
await fs.writeFile(input.outputPrefix+'-result.json',JSON.stringify(report,null,2)+'\n',{flag:'wx',mode:0o600});
console.log(JSON.stringify({arm:arm.id,complete:report.complete,identicalWireRequests,requests:observations.length,reason:result.telemetry.reason}));
