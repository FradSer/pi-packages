/** Offline native Pi configuration/wire proof; never a learning-effectiveness fixture. */
import {writeFileSync} from 'node:fs';
import {createAssistantMessageEventStream, type AssistantMessage} from '@earendil-works/pi-ai';
import type {ExtensionAPI} from '@earendil-works/pi-coding-agent';
import {createJevJudge} from '../extensions/jev-learning.ts';
export default function(pi: ExtensionAPI) {
  pi.on('session_start', async () => {
    const url=process.env.JEV_FIXTURE_URL!, output=process.env.JEV_FIXTURE_OUTPUT!;
    if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(url)||!output) throw Error('Isolated loopback fixture required');
    const controller=new AbortController();let active=0,peak=0,calls=0;
    const judge=createJevJudge({enabled:true,apiKey:'fixture',baseURL:url,scopes:['memory'],fetch:async(input,options)=>{
      if(!String(input).startsWith(url+'/')) throw Error('External fixture request refused');
      calls++;active++;peak=Math.max(peak,active);
      try {const response=await fetch(input,options);if(process.env.JEV_FIXTURE_CANCEL==='1')controller.abort();return response;}
      finally {active--;}
    }});
    const evidence={contextEnabled:true,entries:[{role:'user',content:'This project uses pnpm.'},{role:'toolResult',content:'Unrelated public source observation. '.repeat(900)}]};
    const candidate={name:'fact.md',kind:'project',classification:'safe',content:'---\nname: fact\ndescription: This project uses pnpm.\ntype: project\n---\nThis project uses pnpm.',evidence:[{index:0,quote:'This project uses pnpm.',role:'user'}]};
    const result=await judge.validate('memory',evidence,[candidate],[],controller.signal);
    writeFileSync(output,JSON.stringify({peak,calls,result,externalRequests:0}),{mode:0o600});
  });
  pi.registerProvider('jev-concurrency-fixture',{api:'jev-concurrency-fixture',baseUrl:'http://127.0.0.1',apiKey:'fixture',models:[{id:'deterministic',name:'Offline fixture',reasoning:false,input:['text'],contextWindow:200000,maxTokens:4096,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}],streamSimple(model){
    const message:AssistantMessage={role:'assistant',api:model.api,provider:model.provider,model:model.id,timestamp:Date.now(),content:[{type:'text',text:'done'}],stopReason:'stop',usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}};
    const stream=createAssistantMessageEventStream();stream.push({type:'start',partial:message});stream.push({type:'done',reason:'stop',message});stream.end();return stream;
  }});
}
