"""Infrastructure aborts must never become model correctness failures."""
import json
import pytest
from summarize import summarize


@pytest.mark.parametrize("grade", [
    {"passed": False, "reason": "Verifier timed out"},
    {"passed": False, "reason": "verifier_finished", "scriptExitCodes": []},
    {"passed": False, "reason": "verifier_finished", "scriptExitCodes": [1], "testPatchApplyFailed": True},
])
def test_verifier_infrastructure_failure_is_not_a_completed_pair(tmp_path, grade):
    folder = tmp_path / 'task'
    folder.mkdir()
    (folder / 'gate.json').write_text(json.dumps({'eligible': True}))
    for arm in ('baseline', 'e2e'):
        output = folder / arm
        (output / 'grade').mkdir(parents=True)
        (output / 'attempt.json').write_text(json.dumps({'inferenceRequests': 2}))
        (output / 'grade/result.json').write_text(json.dumps(grade))
    result = summarize(tmp_path, [{'instance_id': 'task', 'language': 'python'}])
    assert result['completedPairs'] == 0
    assert result['tasks'][0]['baseline']['state'] == 'infrastructure_blocked'


def test_model_patch_apply_failure_is_a_correctness_failure(tmp_path):
    folder = tmp_path / 'task'
    folder.mkdir()
    (folder / 'gate.json').write_text(json.dumps({'eligible': True}))
    for arm in ('baseline', 'e2e'):
        output = folder / arm
        (output / 'grade').mkdir(parents=True)
        (output / 'attempt.json').write_text(json.dumps({'inferenceRequests': 2}))
        (output / 'grade/result.json').write_text(json.dumps({
            'passed': False, 'reason': 'patch_apply_failed'}))
    result = summarize(tmp_path, [{'instance_id': 'task', 'language': 'python'}])
    assert result['completedPairs'] == 1
    assert result['baselinePassed'] == result['e2ePassed'] == 0


def test_started_verification_is_counted_even_without_a_completed_verdict(tmp_path):
    folder = tmp_path / 'task'
    folder.mkdir()
    output = folder / 'e2e'
    output.mkdir()
    (output / 'attempt.json').write_text(json.dumps({'e2eResults': []}))
    (output / 'events.jsonl').write_text(json.dumps({'type':'tool_execution_start','toolName':'e2e_verify'}) + '\n')
    result = summarize(tmp_path, [{'instance_id':'task','language':'python'}])
    assert result['tasks'][0]['e2e']['e2eVerifyCalls'] == 1


def test_lost_tool_trace_is_unknown_not_zero_calls(tmp_path):
    # Given host disk failure before saving model events, when summarizing,
    # then exclude the interrupted arm and leave its invocation count unknown.
    output = tmp_path / 'task' / 'e2e'
    output.mkdir(parents=True)
    (output / 'attempt.json').write_text(json.dumps({
        'infrastructureError': 'Host ENOSPC before final capture',
        'toolTraceLost': True}))
    result = summarize(tmp_path, [{'instance_id': 'task', 'language': 'typescript'}])
    assert result['completedPairs'] == 0
    assert result['tasks'][0]['e2e']['state'] == 'infrastructure_blocked'
    assert result['tasks'][0]['e2e']['e2eVerifyCalls'] is None
