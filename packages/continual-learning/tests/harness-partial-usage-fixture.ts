/** Controlled real OS children prove usage retention, not model judgments. */
import {mock} from 'bun:test';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {spawn} from 'node:child_process';
const kit=await import('./packages/kit/src/index.ts');let child,calls=0,expire,bound;
const timer=globalThis.setTimeout;
globalThis.setTimeout=(fn,ms,...args)=>ms===230000?(bound=ms,expire=fn,timer(()=>{},60000)):timer(fn,ms,...args);
const mode=process.env.CL_HARNESS_PARTIAL_MODE??'initial';
const event=cost=>({type:'message_end',message:{role:'assistant',stopReason:'toolUse',content:[{type:'text',text:'fixture'}],usage:{input:2,output:3,cacheRead:0,cacheWrite:0,totalTokens:5,cost:{total:cost}}}});
mock.module('./packages/kit/src/index.ts',()=>({...kit,spawnPiChild:()=>{
  calls++;const firstRepair=mode==='repair'&&calls===1;
  const messages=firstRepair?[event(.1),{type:'consolidation_plan',plan:{kind:'harness-consolidation-plan',runId:'fixture',scopeDigest:'fixture',artifactHash:snapshotDigest,operations:[{op:'invalid'}]}}]:[event(.25)];
  const code=messages.map(m=>`console.log(${JSON.stringify(JSON.stringify(m))});`).join('')+(firstRepair?'':'setInterval(()=>{},1000);');
  child=spawn('node',['-e',code],{stdio:['ignore','pipe','pipe']});
  if(!firstRepair)child.stdout.once('data',()=>queueMicrotask(()=>expire()));
  return child;
}}));
const {planHarnessConsolidationPhase}=await import('./packages/continual-learning/extensions/harness-consolidation.ts');
const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'harness-real-cost-')),runDir=path.join(cwd,'run');fs.mkdirSync(runDir);const snapshotPath=path.join(runDir,'snapshot.json');fs.writeFileSync(snapshotPath,JSON.stringify({entries:[]}));
const {createHash}=await import('node:crypto');const snapshotDigest=createHash('sha256').update(fs.readFileSync(snapshotPath)).digest('hex');
const run={manifest:{runId:'fixture',scopeDigest:'fixture',snapshotDigest,snapshotPath,cwd,runDir}};
// Initial extraction identity must match the actual parent snapshot digest.
// Update the bound field through the injected task's known test identity only.
const result=await planHarnessConsolidationPhase({cwd,ui:{notify(){}}},{pkgDir:process.cwd(),cwd,reason:'fixture',run,resolveCli:()=>({command:'node',args:[]}),timeoutMs:230000});
const ledgers=fs.readdirSync(runDir).filter(n=>/^harness-(?:task|repair)-usage/.test(n)).map(n=>JSON.parse(fs.readFileSync(path.join(runDir,n),'utf8')));
console.log(JSON.stringify({ok:result.ok,detail:result.detail,attempts:result.attempts,usage:result.usage??null,ledgers,bound,calls,childClosed:child.exitCode!==null||child.signalCode!==null}));
