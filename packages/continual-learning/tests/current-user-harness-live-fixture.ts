/** Offline native correction scheduling proof, never model-quality evidence. */
import fs from 'node:fs';
import path from 'node:path';
import {createAssistantMessageEventStream, type AssistantMessage} from '@earendil-works/pi-ai';
import type {ExtensionAPI} from '@earendil-works/pi-coding-agent';
import register from '../index.ts';
import {writeLearningSettings} from '../extensions/learning-settings.ts';

export default function(pi: ExtensionAPI) {
  const endpoint=process.env.CL_EARLY_FIXTURE_URL!, output=process.env.CL_EARLY_FIXTURE_OUTPUT!;
  if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(endpoint)||!output)throw Error('Isolated loopback fixture required');
  const originalFetch=globalThis.fetch;
  globalThis.fetch=async(input,init)=>{
    const raw=input instanceof Request?input.url:String(input),url=new URL(raw);
    if(url.hostname==='api.typesafe.ai')return originalFetch(endpoint+'/v1/systemone',init);
    if(url.origin===endpoint)return originalFetch(input,init);
    throw Error('External fixture request refused');
  };
  // This fixture disables ordinary post-task learning, after the early phase,
  // so its receipts cannot be mistaken for learning an unfinished task.
  pi.on('agent_settled',async(_event,ctx)=>{await writeLearningSettings({autoMemory:false},ctx.cwd);});
  register(pi);
  const writeProbe=process.env.CL_EARLY_FIXTURE_WRITE_PROBE;
  const probeWrite=writeProbe==='1'||writeProbe==='2';
  let mainCalls=0;
  let atMain: unknown;
  pi.registerProvider('early-harness-native-fixture',{
    api:'early-harness-native-fixture',baseUrl:endpoint,apiKey:'offline-fixture',
    models:[{id:'deterministic',name:'Offline native scheduling',reasoning:false,input:['text'],contextWindow:200000,maxTokens:4096,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}],
    streamSimple(model){
      mainCalls++;
      if(mainCalls===1)atMain=JSON.parse(fs.readFileSync(path.join(process.cwd(),'.pi/harness.json'),'utf8'));
      const writeConfig=probeWrite&&mainCalls===1 ? JSON.stringify({...atMain as Record<string,unknown>,rules:[{id:'owned-npm',bash:'^npm(?:\\s|$)',action:'block',message:'Bypassed correction.'}]}) : '';
      const versionTurn=mainCalls===(probeWrite?2:1);
      const toolTurn=versionTurn||(probeWrite&&mainCalls===1);
      const message:AssistantMessage={role:'assistant',api:model.api,provider:model.provider,model:model.id,timestamp:Date.now(),
        content:probeWrite&&mainCalls===1?[{type:'toolCall',id:'native-write',name:'write',arguments:{path:path.join(process.cwd(),writeProbe==='2'?'.pi/harness.local.json':'.pi/harness.json'),content:writeConfig}}]:versionTurn?[{type:'toolCall',id:'native-version',name:'bash',arguments:{command:'npm --version'}}]:[{type:'text',text:'Native fixture completed.'}],
        stopReason:toolTurn?'toolUse':'stop',usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}};
      const stream=createAssistantMessageEventStream();stream.push({type:'start',partial:message});stream.push({type:'done',reason:message.stopReason,message});stream.end();return stream;
    },
  });
  pi.on('session_shutdown',async(_event,ctx)=>{
    const rows=ctx.sessionManager.getBranch();
    const results=rows.filter(row=>row.type==='message'&&row.message.role==='toolResult'&&row.message.toolCallId==='native-version');
    const writeResults=rows.filter(row=>row.type==='message'&&row.message.role==='toolResult'&&row.message.toolCallId==='native-write');
    const behaviorObservations=rows.filter(row=>row.type==='custom'&&row.customType==='harness-behavior-observation');
    fs.writeFileSync(output,JSON.stringify({mainCalls,atMain,results,writeResults,behaviorObservations,externalRequests:0}),{mode:0o600});
  });
}
