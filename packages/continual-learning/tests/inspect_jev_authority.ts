/** Opt-in diagnostic of checked-in public samples, no model mocks. */
import fs from 'node:fs/promises';
import {createJevJudge} from '../extensions/jev-learning';
import type {Sample} from './jev-evaluation';
const rows:Sample[]=JSON.parse(await fs.readFile(new URL('./fixtures/jev-authority-holdout.json',import.meta.url),'utf8'));
const transport:unknown[]=[];
const judge=createJevJudge({enabled:true,defaultModel:'jev-1.13.0',fetch:async(input,init)=>{
 const response=await fetch(input,init);
 transport.push({request:JSON.parse(String(init?.body)),result:await response.clone().json()});
 return response;
}});
const results=[];
for(const sample of rows.filter(x=>['en-authority-valid-0','zh-authority-valid-0','en-authority-risk-0','zh-authority-risk-0'].includes(x.id))){
 const evidence={entries:[{message:{role:'user',content:sample.evidence}}]};
 const candidate=sample.candidate as {rule:Record<string,unknown>;cases:unknown};
 results.push({id:sample.id,verdict:await judge.validate('harness',evidence,[{op:'addRule',...candidate}],[])});
}
console.log(JSON.stringify({evidence:'real-jev-inference-public-diagnostic',results,transport},null,2));
