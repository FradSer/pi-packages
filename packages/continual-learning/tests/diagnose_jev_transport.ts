/** Bounded public synthetic transport evidence; no writes or quality claim. */
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {createJevJudge} from '../extensions/jev-learning';
const base=new URL('./',import.meta.url);
const live=process.argv.includes('--live');
if(live===process.argv.includes('--preflight-only'))throw new Error('Choose one explicit diagnostic mode');
const manifest=JSON.parse(await fs.readFile(new URL('jev-transport-r12-followup-manifest.json',base),'utf8')) as {codeHashes:Record<string,string>;samples:{id:string;evidence:unknown}[];requestBudget:number;model:string};
async function verify(){for(const [file,digest]of Object.entries(manifest.codeHashes))if(createHash('sha256').update(await fs.readFile(new URL(file,base))).digest('hex')!==digest)throw new Error('Frozen diagnostic source changed');}
await verify();
const output=new URL(live?'jev-transport-r12-followup-real-results.json':'jev-transport-r12-followup-preflight.json',base);
try{await fs.access(output);throw new Error('Preserve previous diagnostic evidence; output exists');}catch(e){if(!(e instanceof Error&&'code'in e&&e.code==='ENOENT'))throw e;}
if(live&&!process.env.TYPESAFE_API_KEY)throw new Error('Real inference requires configured environment credential');
let requests=0;
const wire:{sample:string;bytes:number;status:number;model?:string;inputTokens?:number}[]=[];
const results:unknown[]=[];
for(const row of manifest.samples){
 const judge=createJevJudge({enabled:true,apiKey:live?process.env.TYPESAFE_API_KEY:'fixture-only',defaultModel:manifest.model,scopes:['selection'],fetch:async(url,init)=>{
  const body=String(init?.body);if(Buffer.byteLength(body)>64000||requests>=manifest.requestBudget)throw new Error('Diagnostic budget exceeded');requests++;
  const response=live?await fetch(url,init):new Response(JSON.stringify({model:manifest.model,answers:{memory:{type:'noul',noul:.99},harness:{type:'noul',noul:.99}},usage:{input_tokens:0,output_tokens:0}}));
  const meta:typeof wire[number]={sample:row.id,bytes:Buffer.byteLength(body),status:response.status};
  if(response.ok){const raw=await response.clone().json() as {model?:unknown;usage?:{input_tokens?:unknown}};if(typeof raw.model==='string'&&/^jev-[0-9.]+$/.test(raw.model))meta.model=raw.model;if(typeof raw.usage?.input_tokens==='number'&&Number.isSafeInteger(raw.usage.input_tokens)&&raw.usage.input_tokens>=0)meta.inputTokens=raw.usage.input_tokens;}
  wire.push(meta);return response;
 }});
 const result=await judge.select(row.evidence,[],false);results.push({id:row.id,...result});
}
await verify();
const knownInputTokens=wire.reduce((n,x)=>n+(x.inputTokens??0),0);
const report={evidence:live?'real-public-synthetic-jev-transport-diagnostic':'offline-mock-transport-preflight',externalRequests:live?requests:0,fixtureRequests:live?0:requests,requestBudget:manifest.requestBudget,knownInputTokens,knownEstimatedCostUsd:knownInputTokens*.042/1000000,wire,results,productionWrites:0,limitations:['Transport diagnostic only; no causal learning-quality comparison.','A current success cannot determine the cause of old R12 failures.','Synthetic public text; not replayed private project evidence.','Cancelled or failed responses may have unreported billable usage.']};
await fs.writeFile(output,JSON.stringify(report,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify(report));
