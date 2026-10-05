/** Opt-in real inference on two fixed public regression samples only. */
import fs from 'node:fs/promises';
import {createJevJudge} from '../extensions/jev-learning';
import type {Sample} from './jev-evaluation';
const samples:Sample[]=JSON.parse(await fs.readFile(new URL('./fixtures/jev-learning.json',import.meta.url),'utf8'));
const transport:unknown[]=[];
const judge=createJevJudge({enabled:true,defaultModel:'jev-1.13.0',fetch:async(input,init)=>{
 const response=await fetch(input,init);
 transport.push({request:JSON.parse(String(init?.body)),result:await response.clone().json()});
 return response;
}});
const rows=[];
for(const sample of samples.filter(s=>s.id.endsWith('harness-narrow'))){
 rows.push({id:sample.id,result:await judge.validate('harness',{entries:[{message:{role:'user',content:sample.evidence}}]},
 [{op:'addRule',...sample.candidate as object,cases:{positive:[{bash:'git push origin main'}],negative:[{bash:'git status'}]}}],[])});
}
console.log(JSON.stringify({evidence:'real-jev-inference-public-diagnostic',rows,transport},null,2));
