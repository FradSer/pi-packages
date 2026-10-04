"""Monitor evidence must reflect terminal outcomes, never start acknowledgements."""
import subprocess

from test_goal import REPO, assert_all_pass


def test_monitor_evidence_contracts() -> None:
    assert len(assert_all_pass("goal_monitor_evidence.mts")) == 11


def test_large_safe_labels_do_not_block_evidence_collection() -> None:
    script = """
import assert from 'node:assert/strict';
import { collectGoalEvidence } from './packages/goal/src/evidence.ts';
const at='2026-10-03T00:00:00.000Z';
const goal={id:'g',objective:'Verify',status:'active',autoContinue:true,usage:{tokensUsed:0,activeSeconds:0},createdAt:at,updatedAt:at,revision:0};
const entry={type:'custom_message',id:'terminal',timestamp:at,customType:'monitor-result',content:'y'.repeat(10000),details:{description:'x'.repeat(100000),result:{status:'success'}}};
const evidence=collectGoalEvidence([entry],goal,'thread');
assert.equal(evidence.observations[0].label.length,200);
assert.equal(evidence.observations[0].output.length,3000);
console.log('BOUNDED_EVIDENCE_OK');
"""
    result = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module", "-e", script],
        cwd=REPO, text=True, capture_output=True, timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert "BOUNDED_EVIDENCE_OK" in result.stdout
