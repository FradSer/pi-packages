from pathlib import Path
import pytest
from support import isolated_run_bun


def test_only_actual_current_explicit_durable_user_corrections_nominate_early_review():
    result = isolated_run_bun(r'''
      import {currentUserCorrectionEntry, ownedCorrectionPlan} from './packages/continual-learning/extensions/current-user-harness-correction.ts';
      const text='Permanently retire the automatically learned npm-test restriction: npm commands are no longer forbidden by project policy.';
      const entry={id:'actual-user',type:'message',message:{role:'user',content:[{type:'text',text}]}};
      const nominates=(entries,prompt)=>Boolean(currentUserCorrectionEntry(entries,prompt));
      const old={npm:'a'.repeat(64)};
      const op={op:'updateRule',rule:{id:'npm',enabled:false},correction:{eventIndex:0,quote:text,priorRevision:old.npm}};
      console.log(JSON.stringify({current:nominates([entry],text),extension:nominates([entry],'Please continue.'),
        temporary:nominates([{...entry,message:{role:'user',content:[{type:'text',text:'Allow npm --version for this task only.'}]}}],'Allow npm --version for this task only.'),
        quotedTool:nominates([{...entry,message:{role:'toolResult',content:[{type:'text',text}]}}],text),
        assistant:nominates([{...entry,message:{role:'assistant',content:[{type:'text',text}]}}],text),
        nonOriginal:nominates([{message:entry.message}],text),
        mixed:nominates([{...entry,message:{role:'user',content:[{type:'text',text},{type:'image',data:'data'}]}}],text),
        valid:ownedCorrectionPlan({operations:[op]},old),
        added:ownedCorrectionPlan({operations:[{...op,op:'addRule'}]},old),
        foreign:ownedCorrectionPlan({operations:[{...op,rule:{id:'manual'}}]},old),
        stale:ownedCorrectionPlan({operations:[{...op,correction:{...op.correction,priorRevision:'b'.repeat(64)}}]},old),
        missing:ownedCorrectionPlan({operations:[{...op,correction:undefined}]},old),
        wrongEntry:ownedCorrectionPlan({operations:[{...op,correction:{...op.correction,eventIndex:1}}]},old)}));
    ''')
    assert result['current'] and result['valid']
    assert all(not value for name, value in result.items() if name not in ('current', 'valid'))


def test_registered_early_review_uses_only_current_user_and_never_acknowledges_unfinished_task():
    result = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
      import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'early-harness-'));fs.mkdirSync(path.join(cwd,'.git'));fs.mkdirSync(path.join(cwd,'.pi'));
      const agent=process.env.PI_CODING_AGENT_DIR;fs.mkdirSync(path.join(agent,'memory'),{recursive:true});
      fs.writeFileSync(path.join(agent,'memory','settings.json'),JSON.stringify({autoMemory:true,automaticPhases:{memory:'off',harness:'apply',agents:'off'}}));
      fs.writeFileSync(path.join(agent,'continual-learning.json'),JSON.stringify({jev:{apiKey:'offline-fixture',scopes:['harness']}}));
      const rule={id:'owned-npm',bash:'^npm(?:\\s|$)',action:'block',message:'Block Bash commands whose first executable is npm.'};
      const target=path.join(cwd,'.pi/harness.json');const original=JSON.stringify({rules:[rule],learnedRules:{[rule.id]:{origin:'consolidation',revision:ruleRevision(rule)}}});fs.writeFileSync(target,original);
      const harness=await import('./packages/continual-learning/extensions/harness-consolidation.ts');let plans=0,captured,bound;
      mock.module('./packages/continual-learning/extensions/harness-consolidation.ts',()=>({...harness,planHarnessConsolidationPhase:async(ctx,opts)=>{
        plans++;captured=ctx.sessionManager.getBranch();bound=opts.timeoutMs;return {ok:false,detail:'Controlled held plan',durationMs:1,run:opts.run,attempts:[{phase:'harness',attempt:0,outcome:'failed',durationMs:1,operations:0,modelCalls:0}]};
      }}));
      const {default:register}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const hooks=new Map(),receipts=[];register({on:(name,fn)=>hooks.set(name,[...(hooks.get(name)??[]),fn]),registerCommand:()=>{},registerEntryRenderer:()=>{},getCommands:()=>[],appendEntry:()=>{},sendMessage:m=>receipts.push(m.details)});
      const text='Correction of the prior permanent project constraint: npm --version is now allowed; only Bash commands starting npm test must be blocked. Replace the old broad npm restriction permanently.';
      const entry={id:'actual-user',type:'message',message:{role:'user',content:[{type:'text',text}]}};
      const entries=[{id:'older-user',type:'message',message:{role:'user',content:'Permanently block npm.'}},entry];
      const ctx={cwd,mode:'json',hasUI:false,model:{provider:'fixture',id:'fixture'},ui:{notify:()=>{},setWidget:()=>{}},sessionManager:{getSessionId:()=> 'current-session',getBranch:()=>entries,buildContextEntries:()=>entries}};
      for(const fn of hooks.get('session_start')??[])await fn({},ctx);
      const start=async prompt=>{for(const fn of hooks.get('before_agent_start')??[])await fn({prompt,systemPromptOptions:{sections:{}}},ctx)};
      await start('Extension continuation');const before=plans;for(const fn of hooks.get('input')??[])await fn({source:'interactive',text},ctx);await start(text);await start(text);
      const {readBacklog}=await import('./packages/continual-learning/extensions/learning-backlog.ts');
      console.log(JSON.stringify({before,plans,captured,bound,unchanged:fs.readFileSync(target,'utf8')===original,pending:readBacklog(cwd).pendingEntries.length,receipts:receipts.map(r=>({operations:r.operations,attempts:r.attempts.map(a=>a.outcome)}))}));
    ''')
    assert result['before'] == 0
    assert result['plans'] == 1
    assert len(result['captured']) == 1 and result['captured'][0]['inputProvenance']['source'] == 'interactive'
    assert result['bound'] == 230000
    assert result['unchanged'] and result['pending'] == 0
    assert result['receipts'] and result['receipts'][0]['operations'] == 0
    assert 'failed' in result['receipts'][0]['attempts']


def test_ordinary_config_writes_preserve_exact_owned_rules_and_markers():
    value = isolated_run_bun(r'''
      import {preservesOwnedHarnessRules} from './packages/continual-learning/extensions/current-user-harness-correction.ts';
      import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const rule={id:'owned',bash:'^npm$',action:'block',message:'Block npm.'};
      const before={rules:[rule],learnedRules:{owned:{origin:'consolidation',revision:ruleRevision(rule)}}};
      const changed={...before,rules:[{...rule,enabled:false}]};
      console.log(JSON.stringify({same:preservesOwnedHarnessRules(before,structuredClone(before)),
        unrelated:preservesOwnedHarnessRules(before,{...before,rules:[rule,{id:'manual',text:'topic',instructions:'Manual instruction.'}]}),
        changed:preservesOwnedHarnessRules(before,changed),removed:preservesOwnedHarnessRules(before,{rules:[],learnedRules:before.learnedRules}),
        markerRemoved:preservesOwnedHarnessRules(before,{rules:[rule]}),markerChanged:preservesOwnedHarnessRules(before,{...before,learnedRules:{owned:{origin:'consolidation',revision:'a'.repeat(64)}}}),
        manual:preservesOwnedHarnessRules({rules:[rule]},changed),stale:preservesOwnedHarnessRules({...before,rules:[{...rule,message:'Manually changed.'}]},changed)}));
    ''')
    assert value['same'] and value['unrelated'] and value['manual'] and value['stale']
    assert not value['changed'] and not value['removed'] and not value['markerRemoved'] and not value['markerChanged']


def test_total_early_deadline_terminates_child_and_retains_partial_cost_without_mutation():
    value = isolated_run_bun(r'''
      import {mock} from 'bun:test';import fs from 'node:fs';import path from 'node:path';import os from 'node:os';import {spawn} from 'node:child_process';
      import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const cwd=fs.mkdtempSync(path.join(os.tmpdir(),'early-deadline-'));fs.mkdirSync(path.join(cwd,'.git'));fs.mkdirSync(path.join(cwd,'.pi'));
      const agent=process.env.PI_CODING_AGENT_DIR;fs.mkdirSync(path.join(agent,'memory'),{recursive:true});
      fs.writeFileSync(path.join(agent,'memory/settings.json'),JSON.stringify({autoMemory:true,automaticPhases:{memory:'off',harness:'apply',agents:'off'}}));
      fs.writeFileSync(path.join(agent,'continual-learning.json'),JSON.stringify({jev:{apiKey:'offline-fixture',scopes:['harness']}}));
      const rule={id:'owned',bash:'^npm$',action:'block',message:'Block npm.'};const original=JSON.stringify({rules:[rule],learnedRules:{owned:{origin:'consolidation',revision:ruleRevision(rule)}}});const target=path.join(cwd,'.pi/harness.json');fs.writeFileSync(target,original);
      let fire,bound,pid,closed=false;
      const timer=globalThis.setTimeout;globalThis.setTimeout=(fn,ms,...args)=>ms===230_000?(bound=ms,fire=fn,timer(()=>{},60000)):timer(fn,ms,...args);
      const harness=await import('./packages/continual-learning/extensions/harness-consolidation.ts');
      mock.module('./packages/continual-learning/extensions/harness-consolidation.ts',()=>({...harness,planHarnessConsolidationPhase:async(ctx,opts,hooks)=>{
        const child=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:'ignore'});pid=child.pid;hooks.onChild(child);
        await new Promise(resolve=>{child.once('close',()=>{closed=true;resolve();});child.once('spawn',()=>fire());});
        return {ok:false,detail:'Controlled terminated worker',run:opts.run,durationMs:1,attempts:[{phase:'harness',attempt:0,outcome:'cancelled',operations:0,durationMs:1,usage:{input:2,output:3,cacheRead:0,cacheWrite:0,totalTokens:5,cost:0.25},usageComplete:false,costAvailable:false}]};
      }}));
      const {default:register}=await import('./packages/continual-learning/extensions/inject-memory.ts');const hooks=new Map();register({on:(n,f)=>hooks.set(n,[...(hooks.get(n)??[]),f]),registerCommand:()=>{},registerEntryRenderer:()=>{},getCommands:()=>[],appendEntry:()=>{},sendMessage:()=>{}});
      const ctx={cwd,mode:'json',hasUI:false,model:{provider:'fixture',id:'fixture'},ui:{notify:()=>{},setWidget:()=>{}},sessionManager:{getSessionId:()=> 'deadline-session',getBranch:()=>[],buildContextEntries:()=>[]}};
      const text='Permanently retire the owned rule.';for(const f of hooks.get('session_start')??[])await f({},ctx);for(const f of hooks.get('input')??[])await f({source:'rpc',text},ctx);for(const f of hooks.get('before_agent_start')??[])await f({prompt:text,systemPromptOptions:{sections:{}}},ctx);
      let alive=true;try{process.kill(pid,0)}catch{alive=false}
      const receipts=fs.readdirSync(agent,{recursive:true}).filter(f=>String(f).endsWith('learning-pipeline-receipt.json')).map(f=>JSON.parse(fs.readFileSync(path.join(agent,String(f)),'utf8')));
      console.log(JSON.stringify({bound,closed,alive,unchanged:fs.readFileSync(target,'utf8')===original,receipts}));
    ''', timeout=15)
    assert value['bound'] == 230000 and value['closed'] and not value['alive'] and value['unchanged']
    assert len(value['receipts']) == 1
    receipt = value['receipts'][0]
    assert receipt['operations'] == 0 and receipt['totals']['cost'] == 0.25 and not receipt['costAvailable']
    assert any(a.get('diagnostic') == 'Early Harness correction exceeded its 230-second deadline.' for a in receipt['attempts'])
    assert receipt['attempts'][-1]['outcome'] == 'cancelled'


@pytest.mark.parametrize('boundary', ['session_shutdown', 'session_start', 'new-input'])
@pytest.mark.parametrize('stage', ['read', 'planner'])
def test_preflight_cannot_restart_after_session_or_input_changes(boundary, stage):
    value = isolated_run_bun(Path(__file__).with_name('current-user-harness-cancel-fixture.ts').read_text(), env={'CL_EARLY_LIFECYCLE': boundary, 'CL_EARLY_CANCEL_STAGE': stage})
    assert value['plansAtShutdown'] == value['plans'] == (1 if stage == 'planner' else 0)
    assert value['applications'] == 0 and value['unchanged'] and value['pending'] == 0
    if stage == 'read':
        assert not value['receipts']


@pytest.mark.parametrize('mode', ['initial', 'repair'])
def test_real_harness_child_partial_usage_reaches_attempt_receipts(mode):
    value = isolated_run_bun(Path(__file__).with_name('harness-partial-usage-fixture.ts').read_text(), env={'CL_HARNESS_PARTIAL_MODE': mode}, timeout=15)
    assert value['childClosed'] and not value['ok'] and value['bound'] == 230000
    assert value['calls'] == (2 if mode == 'repair' else 1)
    attempt = value['attempts'][-1]
    ledger = next(item for item in value['ledgers'] if item['ledgerId'] == attempt.get('usageLedgerId'))
    assert not ledger['complete'] and ledger['knownUsage']['cost'] == 0.25
    assert attempt['usage']['cost'] == 0.25 and not attempt['usageComplete'] and not attempt['costAvailable']
    assert value['usage']['cost'] == (0.35 if mode == 'repair' else 0.25)


def test_ordinary_nearer_layer_cannot_shadow_owned_rule_in_another_layer():
    value = isolated_run_bun(r'''
      import {preservesOwnedHarnessRules} from './packages/continual-learning/extensions/current-user-harness-correction.ts';
      import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const rule={id:'owned',bash:'^npm$',action:'block',message:'Block npm.'};
      const other={source:'project',rules:[rule],learnedRules:{owned:{origin:'consolidation',revision:ruleRevision(rule)}}};
      const shadow={...rule,enabled:false};
      console.log(JSON.stringify({newShadow:preservesOwnedHarnessRules({}, {rules:[shadow]},[other]),
        sameCopy:preservesOwnedHarnessRules({}, {rules:[rule]},[other]),
        unchangedManual:preservesOwnedHarnessRules({rules:[shadow]},{rules:[shadow,{id:'unrelated',text:'topic',instructions:'Manual.'}]},[other]),
        changedManual:preservesOwnedHarnessRules({rules:[shadow]},{rules:[rule]},[other])}));
    ''')
    assert not value['newShadow'] and not value['sameCopy'] and not value['changedManual']
    assert value['unchangedManual']
