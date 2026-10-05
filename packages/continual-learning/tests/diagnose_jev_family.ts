/** Opt-in real inference, fixed public rule grammar variants. */
import {createJevJudge} from '../extensions/jev-learning';
const rows=[];const transport:unknown[]=[];
const judge=createJevJudge({enabled:true,defaultModel:'jev-1.13.0',fetch:async(input,init)=>{const response=await fetch(input,init);transport.push({request:JSON.parse(String(init?.body)),result:await response.clone().json()});return response;}});
for(const [id,evidence] of [['en','Never run git push in this repository.'],['zh','以后在本仓库禁止运行 git push。']]){
 const rule={id:'push',bash:'^git[ \\t]+push(?:[ \\t]|$)',action:'block',message:id==='en'?'Do not push from this repository.':'禁止在本仓库推送。'};
 rows.push({id,rule,result:await judge.validate('harness',{entries:[{message:{role:'user',content:evidence}}]},[{op:'addRule',rule,cases:{positive:[{bash:'git push origin main'}],negative:[{bash:'git status'},{bash:'git\npush'},{bash:'git\u00a0push'},{bash:'git push\u00a0'}]}}],[])});
}
console.log(JSON.stringify({evidence:'real-jev-inference-public-diagnostic',rows,transport},null,2));
