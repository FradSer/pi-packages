/** Paired read-only support primitive study, with complete preflight and numeric observations. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {normalizeNewMemoryProposals} from '../extensions/consolidation-run';
import type {JevTelemetry} from '../extensions/jev-learning';
import {readFrozenResearchManifest} from './frozen-research-manifest';
import {completeMemoryResearchPreflight,observeMemoryJudgments} from './jev-memory-support-research';
import {createJevJudge} from '../extensions/jev-learning';
import {completePublicResearchCitations} from './jev-citation-repair-research';
import {summarizeActualReplayUsage} from './actual-candidate-replay';
const base=new URL('./',import.meta.url),live=process.argv.includes('--live');
if(live===process.argv.includes('--preflight-only'))throw Error('Choose explicit research mode');
const split=process.argv.includes('--heldout')?'heldout':'development';
interface Manifest{codeHashes:Record<string,string>;corpus:string;corpusSha256:string;model:string;requestBudget:number}
interface Sample{id:string;language:string;expectedAllow:boolean;snapshot:unknown;candidates:unknown[]}
const frozen=await readFrozenResearchManifest<Manifest>(new URL(`jev-citation-repair-${split}-study-manifest.json`,base)),m=frozen.value;
const hash=(bytes:Buffer|string)=>createHash('sha256').update(bytes).digest('hex');
const corpus=await fs.readFile(new URL(m.corpus,base));if(hash(corpus)!==m.corpusSha256)throw Error('Frozen support corpus changed');
const samples:Sample[]=JSON.parse(corpus.toString('utf8'));
for(const row of samples)if(typeof row.expectedAllow!=='boolean'||JSON.stringify(normalizeNewMemoryProposals({newMemories:row.candidates},row.snapshot))!==JSON.stringify(row.candidates))throw Error('Invalid or changed support input');
const repaired=samples.map(s=>completePublicResearchCitations(s.snapshot,s.candidates));
{
 const factories={before:createJevJudge,after:createJevJudge};
 const preflight:Record<string,{requests:number;windows:number}[]>={before:[],after:[]};
 for(const [index,sample] of samples.entries())for(const arm of ['before','after'] as const)preflight[arm].push(await completeMemoryResearchPreflight(factories[arm],sample.snapshot,arm==='after'?repaired[index]:sample.candidates));
 const expectedRequests=Object.values(preflight).flat().reduce((n,v)=>n+v.requests,0);
 if(expectedRequests>m.requestBudget)throw Error('Preflight exceeds paid budget');
 if(live&&!process.env.TYPESAFE_API_KEY)throw Error('Support live research requires configured environment credential');
 const output=new URL(`jev-citation-repair-${split}-${live?'real-results':'preflight'}.json`,base);
 const reserve=await fs.open(new URL(output.href+'.reservation'),'wx');await reserve.writeFile(JSON.stringify({startedAt:new Date().toISOString(),requestBudget:m.requestBudget}));await reserve.close();
 let requests=0;
 type Observation=ReturnType<typeof observeMemoryJudgments>&{wireRequestSha256:string};
 interface Arm{decision:string;complete:boolean;modelVerified:boolean;telemetry:JevTelemetry;observations:Observation[]}
 interface Row{id:string;language:string;expectedAllow:boolean;arms:Partial<Record<'before'|'after',Arm>>}
 const rows:Row[]=[];
 for(const [sampleIndex,sample] of samples.entries()){
  const row:Row={id:sample.id,language:sample.language,expectedAllow:sample.expectedAllow,arms:{}};
  const order:('before'|'after')[]=sampleIndex%2?['after','before']:['before','after'];
  for(const arm of order){
   const observations:Observation[]=[];
   const judge=factories[arm]({enabled:true,apiKey:live?process.env.TYPESAFE_API_KEY:'fixture',defaultModel:m.model,scopes:['memory'],allowPrivateMemory:false,timeout:5000,fetch:async(url,init)=>{
    const body=String(init?.body);if(requests>=m.requestBudget||Buffer.byteLength(body)>64000)throw Error('Support research bounds');requests++;
    const request=JSON.parse(body);
    let response:Response;
    if(live)response=await fetch(url,init);
    else{
     const answers=Object.fromEntries(Object.entries(request.questions).map(([key,value])=>{
      const q=value as {type:string;criteria:Record<string,unknown>};if(q.type==='noul')return[key,{type:'noul',noul:.99}];
      const label=key.startsWith('supported')?'grounded':key.startsWith('relation')?'supplement':'compatible';return[key,{type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(Object.keys(q.criteria).map(k=>[k,k===label?1:0]))}];
     }));response=new Response(JSON.stringify({model:m.model,answers,usage:{input_tokens:0,output_tokens:0}}));
    }
    let numeric:ReturnType<typeof observeMemoryJudgments>;
    try{numeric=observeMemoryJudgments(request,await response.clone().json(),m.model)}catch{numeric={valid:false,modelVerified:false,judgments:[]}}
    observations.push({...numeric,wireRequestSha256:hash(body)});return response;
   }});
   const result=await judge.validate('memory',sample.snapshot,arm==='after'?repaired[sampleIndex]:sample.candidates,[]),t=result.telemetry;
   const complete=t.model===m.model&&t.requestCount!==undefined&&t.requestCount>0&&t.completedRequests===t.requestCount
    &&t.evidenceEntries!==undefined&&t.coveredEntries===t.evidenceEntries&&t.evidenceWindows!==undefined&&t.completedWindows===t.evidenceWindows
    &&t.inputTokens!==undefined&&observations.length===t.requestCount&&observations.every(o=>o.valid)
    &&!['invalid-response','unavailable','timeout','cancelled','bounds','sensitive','private-memory-denied'].includes(t.reason);
   const {model,...controlled}=t;
   row.arms[arm]={decision:result.decision,complete,modelVerified:model===m.model,telemetry:{...controlled,...(model===m.model?{model}:{})},observations};
  }
  rows.push(row);const temp=new URL(output.href+'.checkpoint.tmp');await fs.writeFile(temp,JSON.stringify({requests,rows},null,2)+'\n');await fs.rename(temp,new URL(output.href+'.checkpoint'));
 }
 await frozen.verify();if(hash(await fs.readFile(new URL(m.corpus,base)))!==m.corpusSha256)throw Error('Support corpus changed during study');
 const metrics=Object.fromEntries((['before','after'] as const).map(arm=>[arm,{
  complete:rows.filter(r=>r.arms[arm]?.complete).length,incomplete:rows.filter(r=>!r.arms[arm]?.complete).length,
  falseAccepts:rows.filter(r=>r.arms[arm]?.complete&&!r.expectedAllow&&r.arms[arm]?.decision==='allow').length,
  falseHolds:rows.filter(r=>r.arms[arm]?.complete&&r.expectedAllow&&r.arms[arm]?.decision!=='allow').length,
  correct:rows.filter(r=>r.arms[arm]?.complete&&r.expectedAllow===(r.arms[arm]?.decision==='allow')).length,
 }]));
 const usage=summarizeActualReplayUsage(rows.flatMap(r=>Object.values(r.arms).map(a=>a!.telemetry)),m.model);
 const success=metrics.before.incomplete===0&&metrics.after.incomplete===0&&metrics.after.falseAccepts===0&&metrics.after.falseHolds<metrics.before.falseHolds;
 const report={evidence:live?'real-jev-paired-original-citation-completeness-research':'offline-forced-answer-original-citation-completeness-preflight',split,manifestSha256:frozen.sha256,codeHashes:m.codeHashes,corpusSha256:m.corpusSha256,preflight,externalRequests:live?requests:0,fixtureRequests:live?0:requests,requestBudget:m.requestBudget,metrics,successRuleMet:live&&success,...usage,rows,productionWrites:0,adopted:false,limitations:['Known16bilingual temporal cases reused as development, not fresh heldout or Docker quality.','Same original Choice judge and thresholds in both arms. Only complete original public user/tool citations added; knowledge content and classification unchanged.','Forced offline answers prove complete preflight only, not model accuracy.','One paid run, alternating arm order, no favorable retries, relabels, partial writes or automatic adoption.','Unknown/failed usage is a lower bound, tariff estimates are not actual account billing.']};
 await fs.writeFile(output,JSON.stringify(report,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({split,requests,metrics,successRuleMet:report.successRuleMet,...usage}));
}
