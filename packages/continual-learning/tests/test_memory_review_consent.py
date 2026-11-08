from pathlib import Path

from support import isolated_run_bun, run_bun_script
import pytest


@pytest.mark.parametrize('scenario', ['remember-private-maintenance', 'remember-private-request'])
def test_private_memory_needs_no_consent_gate(scenario: str) -> None:
    # All Memory is reviewable by default: no dialog, no private-memory hold,
    # and no retired `allowPrivateMemory` key written into the config.
    value = run_bun_script(Path(__file__).with_name('learning-policy-harness.ts'), scenario)
    assert value['consentCount'] == 0, value
    assert value['consentConfigUnchanged'], value
    receipt = value['registryReceipt']
    assert 'private-memory-denied' not in str(receipt), receipt
    assert not any('consent' in str(a.get('diagnostic', '')).lower() for a in receipt['attempts']), receipt


def test_preflight_receipt_has_zero_calls_and_rejects_untrusted_count() -> None:
    value = isolated_run_bun(r'''
      import {buildLearningReceipt,learningSummaryDetails,isLearningPipelineReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const receipt=buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},[{phase:'memory',attempt:0,outcome:'failed',operations:0,durationMs:0,modelCalls:0,usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:0}}]);
      const invalid=structuredClone(receipt);invalid.attempts[0].modelCalls=-1;
      console.log(JSON.stringify({text:learningSummaryDetails(receipt).join("\n"),valid:isLearningPipelineReceipt(receipt),invalid:isLearningPipelineReceipt(invalid)}));
    ''')
    assert 'calls · 0' in value['text'] and value['valid'] and not value['invalid']
