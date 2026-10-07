from support import isolated_run_bun


def test_failed_or_aborted_assistant_json_is_not_a_plan() -> None:
    result = isolated_run_bun(r'''
      import {extractChildPlan} from './packages/continual-learning/extensions/consolidation-run.ts';
      const kinds=['memory-consolidation-plan','incremental-memory-plan','harness-consolidation-plan','agents-md-consolidation-plan'];
      const rows=kinds.flatMap(kind=>['error','aborted'].map(stopReason=>extractChildPlan(JSON.stringify({type:'message_end',message:{role:'assistant',stopReason,errorMessage:'PRIVATE-DO-NOT-RELAY',content:JSON.stringify({kind})}}))));
      console.log(JSON.stringify(rows));
    ''')
    assert all(row['ok'] is False for row in result)
    assert [row['failure'] for row in result] == ['model-error', 'cancelled'] * 4
    assert all('PRIVATE' not in row['error'] for row in result)


def test_terminal_failure_invalidates_previously_emitted_plan() -> None:
    result = isolated_run_bun(r'''
      import {extractChildPlan} from './packages/continual-learning/extensions/consolidation-run.ts';
      const plan={type:'consolidation_plan',plan:{kind:'harness-consolidation-plan'}};
      const rows=['error','aborted'].map(stopReason=>extractChildPlan([plan,{type:'message_end',message:{role:'assistant',stopReason,content:[]}}].map(JSON.stringify).join('\n')));
      const retry=extractChildPlan([plan,{type:'auto_retry_end',success:false,finalError:'PRIVATE'}].map(JSON.stringify).join('\n'));
      console.log(JSON.stringify([...rows,retry]));
    ''')
    assert all(row['ok'] is False for row in result)
    assert [row['failure'] for row in result] == ['model-error', 'cancelled', 'model-error']


def test_recovery_accepts_only_successful_reply_and_keeps_legacy_protocol() -> None:
    result = isolated_run_bun(r'''
      import {extractChildPlan} from './packages/continual-learning/extensions/consolidation-run.ts';
      const reply=(stopReason,id)=>({type:'message_end',message:{role:'assistant',stopReason,content:JSON.stringify({kind:'incremental-memory-plan',id})}});
      const recovered=extractChildPlan([reply('error','partial'),reply('stop','recovered')].map(JSON.stringify).join('\n'));
      const legacy=extractChildPlan(JSON.stringify({type:'consolidation_plan',plan:{kind:'harness-consolidation-plan'}}));
      console.log(JSON.stringify({recovered,legacy}));
    ''')
    assert result['recovered']['ok'] is True
    assert result['recovered']['plan']['id'] == 'recovered'
    assert result['legacy']['ok'] is True


def test_plan_emitted_during_failure_is_not_restored_by_empty_success() -> None:
    result = isolated_run_bun(r'''
      import {extractChildPlan} from './packages/continual-learning/extensions/consolidation-run.ts';
      const events=[
        {type:'message_end',message:{role:'assistant',stopReason:'error',content:[]}},
        {type:'consolidation_plan',plan:{kind:'harness-consolidation-plan',id:'failed-state'}},
        {type:'message_end',message:{role:'assistant',stopReason:'stop',content:[]}},
      ];console.log(JSON.stringify(extractChildPlan(events.map(JSON.stringify).join('\n'))));
    ''')
    assert result['ok'] is False


def test_failed_incremental_fallback_never_clears_model_error_evidence() -> None:
    result = isolated_run_bun(r'''
      import {createConsolidationEvidence,recordConsolidationEvent} from './packages/continual-learning/extensions/inject-memory.ts';
      const rows=['error','aborted'].map(stopReason=>{
        const e=createConsolidationEvidence();
        recordConsolidationEvent(e,{type:'message_end',message:{role:'assistant',stopReason,errorMessage:'Provider unavailable',content:JSON.stringify({kind:'incremental-memory-plan'})}});
        return {plans:e.planCount,hasPlan:e.finalPlan!==undefined,failed:!!e.plannerModelError};
      });console.log(JSON.stringify(rows));
    ''')
    assert result == [{'plans': 0, 'hasPlan': False, 'failed': True}] * 2


def test_failed_harness_json_stops_before_repair_judgment_and_application() -> None:
    from pathlib import Path
    from support import run_bun_script

    fixture = Path(__file__).with_name('harness-repair-harness.ts')
    for scenario, outcome in [('initial-failed-json', 'failed'), ('initial-aborted-json', 'cancelled'), ('initial-aborted-retry-json', 'cancelled')]:
        result = run_bun_script(fixture, scenario)
        assert result['ok'] is False, result
        assert result['spawned'] == 1, result
        assert result['repairRequested'] is False, result
        assert result['semanticCalls'] == 0, result
        assert result['targetExists'] is False, result
        assert result['operations'] == 0, result
        assert result['attempts'][0]['outcome'] == outcome, result
        assert 'PRIVATE' not in result['detail'], result


def test_retry_bookkeeping_never_clears_aborted_terminal_state() -> None:
    result = isolated_run_bun(r'''
      import {extractChildPlan} from './packages/continual-learning/extensions/consolidation-run.ts';
      import {createConsolidationEvidence,recordConsolidationEvent} from './packages/continual-learning/extensions/inject-memory.ts';
      const reply=stopReason=>({type:'message_end',message:{role:'assistant',stopReason,content:[]}});
      const rows=[true,false].map(success=>{
        const events=[reply('error'),reply('aborted'),{type:'auto_retry_end',success,finalError:'unavailable'}];
        const evidence=createConsolidationEvidence();events.forEach(event=>recordConsolidationEvent(evidence,event));
        return {parsed:extractChildPlan(events.map(JSON.stringify).join('\n')),failed:!!evidence.plannerModelError};
      });console.log(JSON.stringify(rows));
    ''')
    assert all(row['parsed'].get('failure') == 'cancelled' and row['failed'] for row in result)


def test_failed_memory_usage_is_unknown_including_after_retry_recovery() -> None:
    result = isolated_run_bun(r'''
      import {createConsolidationEvidence,recordConsolidationEvent} from './packages/continual-learning/extensions/inject-memory.ts';
      const e=createConsolidationEvidence();
      recordConsolidationEvent(e,{type:'message_end',message:{role:'assistant',stopReason:'error',content:[],usage:{input:0,output:0,totalTokens:0,cost:{total:0}}}});
      const failedKnown=e.attemptUsage!==undefined;
      recordConsolidationEvent(e,{type:'message_end',message:{role:'assistant',stopReason:'stop',content:[],usage:{input:10,output:1,totalTokens:11,cost:{total:.01}}}});
      console.log(JSON.stringify({failedKnown,recoveredTotalKnown:e.attemptUsage!==undefined}));
    ''')
    assert result == {'failedKnown': False, 'recoveredTotalKnown': False}


def test_memory_repair_rejects_a_real_childs_failed_json_before_retention() -> None:
    result = isolated_run_bun(r'''
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const root=fs.mkdtempSync(path.join(os.tmpdir(),'failed-memory-repair-')),pkg=path.join(root,'package');fs.mkdirSync(pkg);
      fs.writeFileSync(path.join(pkg,'package.json'),JSON.stringify({name:'@earendil-works/pi-coding-agent'}));
      const cli=path.join(pkg,'cli.mjs'),prior=process.argv[1];process.argv[1]=cli;
      const {repairIncrementalMemoryPlan}=await import('./packages/continual-learning/extensions/inject-memory.ts');
      const identity={runId:'run-failed-repair',scopeKey:'scope',scopeDigest:'digest',artifactHash:'artifact',snapshotDigest:'artifact'};
      const plan={kind:'incremental-memory-plan',version:1,schemaVersion:1,...identity,operations:[],newMemories:[]};
      const rows=[];
      for(const stopReason of ['stop','error','aborted']){
        const event={type:'message_end',message:{role:'assistant',stopReason,errorMessage:'PRIVATE',content:[{type:'text',text:JSON.stringify(plan)}]}};
        fs.writeFileSync(cli,'console.log('+JSON.stringify(JSON.stringify(event))+');');
        const result=await repairIncrementalMemoryPlan({identity,rejectedPlan:plan,errors:['bounded error'],selectedNames:[]});
        rows.push({outcome:result.outcome,hasPlan:result.plan!==undefined,knownUsage:result.usage!==undefined});
      }
      process.argv[1]=prior;fs.rmSync(root,{recursive:true,force:true});console.log(JSON.stringify(rows));
    ''')
    assert [row['outcome'] for row in result] == ['repaired', 'failed', 'cancelled']
    assert [row['hasPlan'] for row in result] == [True, False, False]
    assert all(row['knownUsage'] is False for row in result)


def test_receipt_never_formats_unknown_failed_usage_as_zero_or_free() -> None:
    result = isolated_run_bun(r'''
      import {buildLearningReceipt,learningSummaryDetails,formatLearningSummary,learningSummarySubject,isLearningPipelineReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const screen={memory:true,harness:false,agents:false,reasons:[]};
      const failed={phase:'memory',attempt:0,outcome:'failed',durationMs:1,operations:0};
      const known={phase:'harness',attempt:0,outcome:'applied',durationMs:1,operations:1,usage:{input:10,output:1,cacheRead:0,cacheWrite:0,totalTokens:11,cost:.01}};
      const rows=[[failed],[known,failed],[{...failed,outcome:'cancelled'}]].map(attempts=>{
        const receipt=buildLearningReceipt('manual',screen,attempts);
        return {available:receipt.costAvailable,usageAvailable:receipt.usageAvailable,summary:formatLearningSummary(receipt),details:learningSummaryDetails(receipt),subject:learningSummarySubject(receipt)};
      });
      const skipped=buildLearningReceipt('manual',screen,[{...failed,outcome:'skipped'}]);
      const legacy=buildLearningReceipt('manual',screen,[failed]);delete legacy.usageAvailable;
      const invalid={...legacy,usageAvailable:'yes'};
      console.log(JSON.stringify({rows,skippedAvailable:skipped.costAvailable,legacyValid:isLearningPipelineReceipt(legacy),legacySummary:formatLearningSummary(legacy),invalidValid:isLearningPipelineReceipt(invalid)}));
    ''')
    assert all(row['available'] is False and row['usageAvailable'] is False for row in result['rows'])
    assert all('cost unavailable' in row['summary'] and '$0.0000' not in row['summary'] for row in result['rows'])
    assert 'usage unavailable' in result['rows'][0]['summary']
    assert 'known subtotal' in result['rows'][1]['summary']
    assert result['rows'][2]['subject'] == 'cancelled'
    assert result['skippedAvailable'] is True
    assert result['legacyValid'] is True and 'cost unavailable' in result['legacySummary']
    assert result['invalidValid'] is False
