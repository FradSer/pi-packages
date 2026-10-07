/** Frozen paired whole-Memory-judge research. No parent writes or repairs. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {createJevJudge,type JevTelemetry} from '../extensions/jev-learning';
import {normalizeNewMemoryProposals} from '../extensions/consolidation-run';
import {readFrozenResearchManifest} from './frozen-research-manifest';
import {ensureMemoryPairResearchPreflight} from './jev-memory-pair-judgment';
import {temporalCounterRequest} from './jev-temporal-counter-research';
import {summarizeActualReplayUsage} from './actual-candidate-replay';
const base=new URL('./',import.meta.url),live=process.argv.includes('--live');
if(live===process.argv.includes('--preflight-only'))throw Error('Choose explicit research mode');
interface Manifest{codeHashes:Record<string,string>;corpus:string;corpusSha256:string;model:string;requestBudget:number}
interface Sample{id:string;language:string;expectedAllow:boolean;snapshot:unknown;candidates:unknown[]}
const split=process.argv.includes('--heldout')?'heldout':'development';
const frozen=await readFrozenResearchManifest<Manifest>(new URL(`jev-temporal-counter-${split}-study-manifest.json`,base));
const m=frozen.value,corpus=await fs.readFile(new URL(m.corpus,base));
const hash=(bytes:Buffer)=>createHash('sha256').update(bytes).digest('hex');
if(hash(corpus)!==m.corpusSha256)throw Error('Frozen temporal corpus changed');
const samples:Sample[]=JSON.parse(corpus.toString('utf8'));
for(const row of samples){if(typeof row.expectedAllow!=='boolean'||JSON.stringify(normalizeNewMemoryProposals({newMemories:row.candidates},row.snapshot))!==JSON.stringify(row.candidates))throw Error('Invalid or changed temporal input');}
let privacyPreflightMockRequests=0,variantPreflightMockRequests=0;
for(const row of samples){
 privacyPreflightMockRequests+=await ensureMemoryPairResearchPreflight(row.snapshot,row.candidates);
 const beforeVariantRequests=variantPreflightMockRequests;
 const judge=createJevJudge({enabled:true,apiKey:'fixture',defaultModel:m.model,scopes:['memory'],allowPrivateMemory:false,fetch:async(_u,init)=>{
  const body=temporalCounterRequest(String(init?.body),row.candidates);if(Buffer.byteLength(body)>64000)throw Error('Temporal bounds');variantPreflightMockRequests++;throw Error('Offline variant preflight');
 }});await judge.validate('memory',row.snapshot,row.candidates,[]);
 if(variantPreflightMockRequests===beforeVariantRequests)throw Error('Variant input denied before transport');
}
if(variantPreflightMockRequests===0)throw Error('No variant preflight requests');
if(live&&!process.env.TYPESAFE_API_KEY)throw Error('Temporal live research requires configured environment credential');
const output=new URL(`jev-temporal-counter-${split}-${live?'real-results':'preflight'}.json`,base);
const reserved=await fs.open(new URL(output.href+'.reservation'),'wx');await reserved.writeFile(JSON.stringify({startedAt:new Date().toISOString(),requestBudget:m.requestBudget}));await reserved.close();
let requests=0;
interface Row{id:string;language:string;expectedAllow:boolean;arms:Partial<Record<'before'|'after',{decision:string;complete:boolean;telemetry:JevTelemetry}>>}
const rows:Row[]=[];
for(const [sampleIndex,sample] of samples.entries()){
 const row:Row={id:sample.id,language:sample.language,expectedAllow:sample.expectedAllow,arms:{}};
 const order:('before'|'after')[]=sampleIndex%2?['after','before']:['before','after'];
 for(const arm of order){
  const judge=createJevJudge({enabled:true,apiKey:live?process.env.TYPESAFE_API_KEY:'fixture',defaultModel:m.model,scopes:['memory'],allowPrivateMemory:false,timeout:5000,fetch:async(url,init)=>{
   const body=arm==='after'?temporalCounterRequest(String(init?.body),sample.candidates):String(init?.body);
   if(requests>=m.requestBudget||Buffer.byteLength(body)>64000)throw Error('Temporal research budget exceeded');requests++;
   if(live)return fetch(url,{...init,body});
   const request=JSON.parse(body),answers=Object.fromEntries(Object.entries(request.questions).map(([key,value])=>{
    const q=value as {criteria:Record<string,unknown>};const label=key.startsWith('supported')?'grounded':'compatible';return [key,{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))}];
   }));return new Response(JSON.stringify({model:m.model,answers,usage:{input_tokens:0,output_tokens:0}}));
  }});
  const result=await judge.validate('memory',sample.snapshot,sample.candidates,[]),t=result.telemetry;
  const complete=t.model===m.model&&t.requestCount!==undefined&&t.requestCount>0&&t.completedRequests===t.requestCount
   &&t.evidenceEntries!==undefined&&t.coveredEntries===t.evidenceEntries&&t.evidenceWindows!==undefined&&t.completedWindows===t.evidenceWindows
   &&t.inputTokens!==undefined&&!['invalid-response','unavailable','timeout','cancelled','bounds','sensitive','private-memory-denied'].includes(t.reason);
  row.arms[arm]={decision:result.decision,complete,telemetry:t};
 }
 rows.push(row);const temp=new URL(output.href+'.checkpoint.tmp');await fs.writeFile(temp,JSON.stringify({requests,rows},null,2)+'\n');await fs.rename(temp,new URL(output.href+'.checkpoint'));
}
await frozen.verify();if(hash(await fs.readFile(new URL(m.corpus,base)))!==m.corpusSha256)throw Error('Temporal corpus changed during research');
const metrics=Object.fromEntries((['before','after'] as const).map(arm=>[arm,{
 complete:rows.filter(r=>r.arms[arm]?.complete).length,incomplete:rows.filter(r=>!r.arms[arm]?.complete).length,
 falseAccepts:rows.filter(r=>r.arms[arm]?.complete&&!r.expectedAllow&&r.arms[arm]?.decision==='allow').length,
 falseHolds:rows.filter(r=>r.arms[arm]?.complete&&r.expectedAllow&&r.arms[arm]?.decision!=='allow').length,
 correct:rows.filter(r=>r.arms[arm]?.complete&&r.expectedAllow===(r.arms[arm]?.decision==='allow')).length,
}]));
const usage=summarizeActualReplayUsage(rows.flatMap(r=>Object.values(r.arms).map(a=>a!.telemetry)),m.model);
const success=metrics.before.incomplete===0&&metrics.after.incomplete===0&&metrics.after.falseAccepts===0&&metrics.after.falseHolds<metrics.before.falseHolds;
const report={evidence:live?'real-jev-paired-temporal-counter-research':'offline-forced-answer-temporal-preflight',split,manifestSha256:frozen.sha256,codeHashes:m.codeHashes,corpusSha256:m.corpusSha256,privacyPreflightMockRequests,variantPreflightMockRequests,externalRequests:live?requests:0,fixtureRequests:live?0:requests,metrics,successRuleMet:live&&success,...usage,rows,productionWrites:0,adopted:false,limitations:['Synthetic bilingual development; not the historical R13 false-hold cause or Docker workflow quality.','Whole production support, body/description counter and original confidence gates remain; only research counter instructions change.','No favorable retries, sample relabels, input truncation or partial application.','Forced offline answers prove request boundaries, not model accuracy.']};
await fs.writeFile(output,JSON.stringify(report,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({split,requests,metrics,successRuleMet:report.successRuleMet,...usage}));
