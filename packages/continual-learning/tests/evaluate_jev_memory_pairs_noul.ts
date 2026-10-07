/** Read-only frozen pair-relation study; no parent plan or write permission. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {TypeSafeClient,APIError,APITimeoutError,APIUserAbortError} from '@typesafe-ai/sdk';
import {readFrozenResearchManifest} from './frozen-research-manifest';
import {ensureMemoryPairResearchPreflight} from './jev-memory-pair-judgment';
import {structuredMemoryPairState} from './jev-memory-pair-structured';
import {memoryPairNoulQuestions,interpretMemoryPairNoul} from './jev-memory-pair-noul';
import {normalizeNewMemoryProposals} from '../extensions/consolidation-run';
const live=process.argv.includes('--live');if(live===process.argv.includes('--preflight-only'))throw new Error('Choose explicit research mode');
const split=process.argv.includes('--heldout')?'heldout':'development',base=new URL('./',import.meta.url);
interface Sample{id:string;snapshot:unknown;candidates:unknown[];expectedPairRelation:string}
interface Manifest{codeHashes:Record<string,string>;corpus:string;corpusSha256:string;model:string;requestBudget:number}
const frozen=await readFrozenResearchManifest<Manifest>(new URL(`jev-memory-pair-noul-${split}-study-manifest.json`,base));
const m=frozen.value,bytes=await fs.readFile(new URL(m.corpus,base));const digest=(b:Buffer)=>createHash('sha256').update(b).digest('hex');
if(digest(bytes)!==m.corpusSha256)throw new Error('Frozen pair corpus changed');const samples:Sample[]=JSON.parse(bytes.toString('utf8'));
for(const row of samples)if(JSON.stringify(normalizeNewMemoryProposals({newMemories:row.candidates},row.snapshot))!==JSON.stringify(row.candidates)||row.candidates.length!==2)throw new Error('Pair evidence normalization changed');
let productionPreflightMockRequests=0;for(const row of samples)productionPreflightMockRequests+=await ensureMemoryPairResearchPreflight(row.snapshot,row.candidates);
if(live&&!process.env.TYPESAFE_API_KEY)throw new Error('Real pair inference needs configured environment credential');
const output=new URL(`jev-memory-pair-noul-${split}-${live?'real-results':'preflight'}.json`,base);
const reservation=await fs.open(new URL(output.href+'.reservation'),'wx');await reservation.writeFile(JSON.stringify({startedAt:new Date().toISOString(),requestBudget:m.requestBudget}));await reservation.close();
let requests=0;
const client=new TypeSafeClient({apiKey:live?process.env.TYPESAFE_API_KEY:'fixture-only',defaultModel:m.model,timeout:5000,retry:{maxRetries:0},logLevel:'off',fetch:async(url,init)=>{
 if(requests>=m.requestBudget||Buffer.byteLength(String(init?.body))>64000)throw new Error('Pair study bounds exceeded');requests++;
 return live?fetch(url,init):new Response(JSON.stringify({model:m.model,answers:Object.fromEntries(Object.keys(memoryPairNoulQuestions()).map(k=>[k,{type:'noul',noul:0}])),usage:{input_tokens:0,output_tokens:0}}));
}});
const rows:{id:string;expected:string;status:string;relation:string|null;independenceObserved:boolean;durationMs:number;model?:string;inputTokens?:number;outputTokens?:number;httpStatus?:number;confidence?:number;probabilities?:unknown}[]=[];
for(const row of samples){
 const started=Date.now();let result:typeof rows[number];
 try{const response=await client.systemOne({model:m.model,state:JSON.stringify(structuredMemoryPairState(row.snapshot,row.candidates)),questions:memoryPairNoulQuestions()});
  const verdict=interpretMemoryPairNoul(response.answers);const usage=response.usage;
  const validUsage=Number.isSafeInteger(usage.input_tokens)&&usage.input_tokens>=0&&Number.isSafeInteger(usage.output_tokens)&&usage.output_tokens>=0;
  const validModel=response.model===m.model;
  const validAnswerSet=Object.keys(response.answers).length===4&&Object.keys(memoryPairNoulQuestions()).every(k=>Object.hasOwn(response.answers,k));
  result={id:row.id,expected:row.expectedPairRelation,...verdict,durationMs:Date.now()-started,...(validModel?{model:response.model}:{}),...(validUsage?{inputTokens:usage.input_tokens,outputTokens:usage.output_tokens}:{}),...(!validModel||!validUsage||!validAnswerSet?{status:'invalid-response',independenceObserved:false}:{})};
 }catch(e){result={id:row.id,expected:row.expectedPairRelation,status:e instanceof APITimeoutError?'timeout':e instanceof APIUserAbortError?'cancelled':'unavailable',relation:null,independenceObserved:false,durationMs:Date.now()-started,...(e instanceof APIError&&Number.isSafeInteger(e.status)&&e.status>=400&&e.status<=599?{httpStatus:e.status}:{})};}
 rows.push(result);const checkpoint=new URL(output.href+'.checkpoint');const temp=new URL(output.href+'.checkpoint.tmp');await fs.writeFile(temp,JSON.stringify({requests,rows},null,2)+'\n');await fs.rename(temp,checkpoint);
}
await frozen.verify();if(digest(await fs.readFile(new URL(m.corpus,base)))!==m.corpusSha256)throw new Error('Pair corpus changed during study');
const metrics={correct:rows.filter(r=>r.status==='decided'&&r.relation===r.expected).length,wrong:rows.filter(r=>r.status==='decided'&&r.relation!==r.expected).length,held:rows.filter(r=>r.status!=='decided').length,unsafeIndependence:rows.filter(r=>r.independenceObserved&&r.expected!=='independent').length,missedIndependence:rows.filter(r=>!r.independenceObserved&&r.expected==='independent').length};
const knownInputTokens=rows.reduce((n,r)=>n+(r.inputTokens??0),0);
const pricedInputTokens=rows.reduce((n,r)=>n+(r.model===m.model?(r.inputTokens??0):0),0);
const report={productionPreflightMockRequests,evidence:live?'real-jev-noul-new-memory-pair-research':'offline-mock-noul-new-memory-pair-preflight',split,manifestSha256:frozen.sha256,codeHashes:m.codeHashes,corpusSha256:m.corpusSha256,externalRequests:live?requests:0,fixtureRequests:live?0:requests,requestBudget:m.requestBudget,metrics,knownInputTokens,knownEstimatedCostUsd:pricedInputTokens*.042/1000000,unpricedInputTokens:knownInputTokens-pricedInputTokens,usageComplete:rows.every(r=>r.inputTokens!==undefined),results:rows,productionWrites:0,adopted:false,limitations:['Pair relations only; no proof of original candidate support, full counterevidence or parent permission.','No partial plan applies, no end-to-end quality claim.','Original complete candidate review and bound dossier still required.']};
await fs.writeFile(output,JSON.stringify(report,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({split,requests,metrics,knownInputTokens,knownEstimatedCostUsd:report.knownEstimatedCostUsd}));
