
      import {mock} from 'bun:test';import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'early-harness-'));fs.mkdirSync(path.join(cwd,'.git'));fs.mkdirSync(path.join(cwd,'.pi'));
      const agent=process.env.PI_CODING_AGENT_DIR;fs.mkdirSync(path.join(agent,'memory'),{recursive:true});
      fs.writeFileSync(path.join(agent,'memory','settings.json'),JSON.stringify({autoMemory:true,automaticPhases:{memory:'off',harness:'apply',agents:'off'}}));
      fs.writeFileSync(path.join(agent,'continual-learning.json'),JSON.stringify({jev:{apiKey:'offline-fixture',scopes:['harness']}}));
      const rule={id:'owned-npm',bash:'^npm(?:\\s|$)',action:'block',message:'Block Bash commands whose first executable is npm.'};
      const target=path.join(cwd,'.pi/harness.json');const original=JSON.stringify({rules:[rule],learnedRules:{[rule.id]:{origin:'consolidation',revision:ruleRevision(rule)}}});fs.writeFileSync(target,original);
      const harness=await import('./packages/continual-learning/extensions/harness-consolidation.ts');let plans=0,applications=0,captured,bound;const stage=process.env.CL_EARLY_CANCEL_STAGE??'read';
      mock.module('./packages/continual-learning/extensions/harness-consolidation.ts',()=>({...harness,planHarnessConsolidationPhase:async(ctx,opts)=>{
        plans++;captured=ctx.sessionManager.getBranch();bound=opts.timeoutMs;if(stage==='planner'){blocked();await new Promise(r=>unblock=r);return {ok:true,value:{run:opts.run,plan:{kind:'harness-consolidation-plan',operations:[]},durationMs:1,attempts:[{phase:'harness',attempt:0,outcome:'noop',durationMs:1,operations:0,modelCalls:0}]}};}return {ok:false,detail:'Controlled held plan',durationMs:1,run:opts.run,attempts:[{phase:'harness',attempt:0,outcome:'failed',durationMs:1,operations:0,modelCalls:0}]};
      },applyHarnessConsolidationPlan:async()=>{applications++;return {outcome:'noop',operations:0};}}));
      const hist=await import('./packages/continual-learning/extensions/learning-history.ts');const originalRead=hist.readLearningFile;let unblock,blocked,held=false;const reached=new Promise(r=>blocked=r);mock.module('./packages/continual-learning/extensions/learning-history.ts',()=>({...hist,readLearningFile:async(...args)=>{if(stage==='read'&&!held&&args[0]===target){held=true;blocked();await new Promise(r=>unblock=r);}return originalRead(...args)}}));const {default:register}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const hooks=new Map(),receipts=[];register({on:(name,fn)=>hooks.set(name,[...(hooks.get(name)??[]),fn]),registerCommand:()=>{},registerEntryRenderer:()=>{},getCommands:()=>[],appendEntry:()=>{},sendMessage:m=>receipts.push(m.details)});
      const text='Correction of the prior permanent project constraint: npm --version is now allowed; only Bash commands starting npm test must be blocked. Replace the old broad npm restriction permanently.';
      const entry={id:'actual-user',type:'message',message:{role:'user',content:[{type:'text',text}]}};
      const entries=[{id:'older-user',type:'message',message:{role:'user',content:'Permanently block npm.'}},entry];
      const ctx={cwd,mode:'json',hasUI:false,model:{provider:'fixture',id:'fixture'},ui:{notify:()=>{},setWidget:()=>{}},sessionManager:{getSessionId:()=> 'current-session',getBranch:()=>entries,buildContextEntries:()=>entries}};
      for(const fn of hooks.get('session_start')??[])await fn({},ctx);
      const start=async prompt=>{for(const fn of hooks.get('before_agent_start')??[])await fn({prompt,systemPromptOptions:{sections:{}}},ctx)};
      const before=plans;for(const fn of hooks.get('input')??[])await fn({source:'interactive',text},ctx);const pending=start(text);await reached;const boundary=process.env.CL_EARLY_LIFECYCLE??'session_shutdown';const stopping=Promise.all((hooks.get(boundary==='new-input'?'input':boundary)??[]).map(fn=>fn(boundary==='new-input'?{source:'interactive',text:'A new ordinary task'}:{},ctx)));const plansAtShutdown=plans;unblock();await stopping;await pending;
      const {readBacklog}=await import('./packages/continual-learning/extensions/learning-backlog.ts');
      console.log(JSON.stringify({before,plans,applications,plansAtShutdown,captured,bound,unchanged:fs.readFileSync(target,'utf8')===original,pending:readBacklog(cwd).pendingEntries.length,receipts:receipts.map(r=>({operations:r.operations,attempts:r.attempts.map(a=>a.outcome)}))}));
    