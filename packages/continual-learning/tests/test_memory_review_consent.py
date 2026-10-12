from pathlib import Path

from support import isolated_run_bun, run_bun_script
import pytest


@pytest.mark.parametrize('scenario', ['remember-private-maintenance', 'remember-private-request'])
def test_private_maintenance_stops_before_any_paid_worker_without_consent(scenario: str) -> None:
    value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), scenario)
    assert value['selectors'] == 0 and not value['planners'] and not value['modelCalls']
    assert not value['newAppliedHistoryRecords']
    receipt = value['registryReceipt']
    assert receipt['operations'] == 0
    assert receipt['costAvailable'] and receipt['totals']['cost'] == 0
    assert all(a['modelCalls'] == 0 for a in receipt['attempts'])
    assert any(a.get('diagnostic') == 'Private Memory review requires explicit per-run consent; no Memory planner started.' for a in receipt['attempts'])


def test_private_review_consent_is_explicit_and_ui_only() -> None:
    rows = isolated_run_bun(r'''
      import {confirmPrivateMemoryReview} from './packages/continual-learning/extensions/memory-review-consent.ts';
      const rows=[];
      for(const mode of ['headless','declined','accepted','closed']){
        const dialogs=[];const result=await confirmPrivateMemoryReview({hasUI:mode!=='headless',ui:{confirm:async(title,body)=>{dialogs.push({title,body});return mode==='accepted'?true:mode==='closed'?undefined:false;}}});
        rows.push({mode,result,dialogs});
      }
      console.log(JSON.stringify(rows));
    ''')
    for row in rows:
        assert row['result'] is (row['mode'] == 'accepted')
        assert len(row['dialogs']) == (0 if row['mode'] == 'headless' else 1)
        if row['dialogs']:
            body = row['dialogs'][0]['body']
            assert 'TypeSafe Jev' in body and 'task evidence' in body and 'this run only' in body


def test_consent_clone_freezes_service_config_and_does_not_change_next_run() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {createJevJudge} from './packages/continual-learning/extensions/jev-learning.ts';
      const configFile=path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json');
      fs.writeFileSync(configFile,JSON.stringify({jev:{apiKey:'fixture-original',scopes:['memory'],model:'jev-1.13.0'}}));
      let calls=0;const transport=async(_url,init)=>{
        calls++;const r=JSON.parse(String(init.body));const answers={};
        for(const [key,q] of Object.entries(r.questions)){
          const keys=Object.keys(q.criteria);const label=keys.find(k=>['grounded','compatible','unrelated'].includes(k))??keys[0];
          answers[key]={type:'choice',choice:label,confidence:1,probabilities:Object.fromEntries(keys.map(k=>[k,k===label?1:0]))};
        }
        return new Response(JSON.stringify({model:r.model,answers,usage:{input_tokens:1,output_tokens:1}}));
      };
      const original=createJevJudge({fetch:transport});
      fs.writeFileSync(configFile,JSON.stringify({jev:false}));
      const consented=original.withPrivateMemoryReview();
      const existing=[{name:'private.md',classification:'private',type:'feedback',description:'Keep progress concise.',content:'Keep progress concise.'}];
      const evidence={contextEnabled:true,entries:[{message:{role:'user',content:'Keep progress concise.'}}]};
      const denied=await original.validate('memory',evidence,[],existing);
      const reviewed=await consented.validate('memory',evidence,[],existing);
      const next=createJevJudge({fetch:transport});
      console.log(JSON.stringify({denied:denied.telemetry.reason,calls,consentedEnabled:consented.enabled,reviewed:reviewed.telemetry,nextEnabled:next.enabled,unchanged:JSON.parse(fs.readFileSync(configFile)).jev===false}));
    ''')
    assert value['denied'] == 'private-memory-denied'
    assert value['consentedEnabled'] and value['calls'] > 0
    assert value['reviewed']['status'] != 'disabled'
    assert not value['nextEnabled'] and value['unchanged']


@pytest.mark.parametrize('scenario', ['remember-private-accepted', 'remember-new-private-accepted'])
def test_one_time_consent_reaches_review_and_private_write(scenario: str) -> None:
    # Controlled planner and judge answers prove authorization wiring, not efficacy.
    value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), scenario)
    assert value['consentCount'] == 1 and value['reviewWireCalls'] > 0
    assert 'concise.md' in value['privateFiles'] and 'concise.md' not in value['publicFiles']
    assert value['registryReceipt']['operations'] > 0 and value['consentConfigUnchanged']


def test_preflight_receipt_has_zero_calls_and_rejects_untrusted_count() -> None:
    value = isolated_run_bun(r'''
      import {buildLearningReceipt,learningSummaryDetails,isLearningPipelineReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const receipt=buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[{phase:'memory',attempt:0,outcome:'failed',operations:0,durationMs:0,modelCalls:0,usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:0}}]);
      const invalid=structuredClone(receipt);invalid.attempts[0].modelCalls=-1;
      console.log(JSON.stringify({text:learningSummaryDetails(receipt).join("\n"),valid:isLearningPipelineReceipt(receipt),invalid:isLearningPipelineReceipt(invalid)}));
    ''')
    assert 'calls · 0' in value['text'] and value['valid'] and not value['invalid']
