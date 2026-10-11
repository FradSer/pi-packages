"""Post-draft budget and accounting acceptance."""
import postfix_protocol as policy


def test_review_and_repair_cannot_receive_separate_full_budgets() -> None:
    assert policy.remaining_seconds(299) == 901
    assert policy.remaining_seconds(1201) == 0


def test_interrupted_review_is_not_a_completed_review() -> None:
    partial = {'type': 'message_end', 'message': {'role': 'assistant', 'stopReason': 'toolUse',
                                               'content': [{'type': 'text', 'text': 'partial'}]}}
    assert policy.review_text([partial]) is None
    final = {'type': 'message_end', 'message': {'role': 'assistant', 'stopReason': 'stop',
                                             'content': [{'type': 'text', 'text': 'missing edge case'}]}}
    assert policy.review_text([partial, final]) == 'missing edge case'


def test_missing_price_and_incomplete_usage_are_not_zero_actual_cost() -> None:
    cost = policy.usage_cost([{'usage': {'input': 20, 'output': 5}}])
    assert cost['piEstimatedUsd'] is None
    assert cost['tokens']['input'] == 20
    assert not cost['billingVerified']
    cost = policy.usage_cost([{'usage': {'input': 1, 'cost': {'total': 0.01}}},
                              {'usage': {'input': 2, 'cost': {'total': 0.02}}}])
    assert cost['piEstimatedUsd'] == 0.03
    assert cost['tokens']['input'] == 3


def test_shared_draft_is_applied_without_replacing_original_capture_baseline(tmp_path) -> None:
    import subprocess
    import run
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True).strip()
    git('init', '-q'); git('config', 'user.name', 'Fixture'); git('config', 'user.email', 'fixture@localhost')
    (tmp_path / 'source.txt').write_text('before\n'); git('add', '-A'); git('commit', '-qm', 'base')
    baseline = git('rev-parse', 'HEAD')
    (tmp_path / 'source.txt').write_text('draft\n')
    patch = subprocess.check_output(['git', '-C', str(tmp_path), 'diff'], text=True)
    (tmp_path / 'seed.patch').write_text(patch); git('checkout', '--', 'source.txt')
    subprocess.run(['bash', '-c', run.apply_seed_script(str(tmp_path / 'seed.patch'))], cwd=tmp_path, check=True)
    assert git('rev-parse', 'HEAD') == baseline
    assert (tmp_path / 'source.txt').read_text() == 'draft\n'
    (tmp_path / 'source.txt').write_text('repaired\n')
    captured = subprocess.check_output(['bash', '-c', run.capture_script(baseline)], cwd=tmp_path, text=True)
    assert '-before' in captured and '+repaired' in captured


def test_empty_draft_is_a_valid_shared_start(tmp_path) -> None:
    import subprocess
    import run
    seed = tmp_path / 'empty draft.patch'
    seed.write_text('')
    completed = subprocess.run(['bash', '-c', run.apply_seed_script(str(seed))], cwd=tmp_path, capture_output=True)
    assert completed.returncode == 0


def test_missing_token_counter_is_unknown() -> None:
    assert policy.usage_cost([{'usage': {'input': 2}}, {'usage': {}}])['tokens']['input'] is None
    assert policy.usage_cost([])['tokens']['output'] is None


def test_review_success_does_not_mask_absent_repair_response() -> None:
    assert not policy.valid_inference([])
    assert not policy.valid_inference([{'stopReason': 'error'}])
    assert not policy.valid_inference([{}])
    assert policy.valid_inference([{'stopReason': 'toolUse'}])


def test_stage_cleanup_is_scoped_and_requires_keeper() -> None:
    import run
    import pytest
    with pytest.raises(ValueError):
        run.stage_cleanup_script(1)
    script = run.stage_cleanup_script(2)
    assert 'SIGSTOP' in script and 'SIGKILL' in script and 'SIGCONT' in script
    assert 'stageClean' in script


def test_exported_runtime_hash_detects_partial_or_modified_runtime(tmp_path) -> None:
    from postfix_batch import runtime_tree
    (tmp_path / 'node').write_bytes(b'original runtime')
    (tmp_path / 'link').symlink_to('node')
    first=runtime_tree(tmp_path)
    assert first==runtime_tree(tmp_path)
    (tmp_path / 'node').write_bytes(b'changed runtime')
    assert first!=runtime_tree(tmp_path)
    second=runtime_tree(tmp_path)
    (tmp_path / 'link').unlink()
    (tmp_path / 'link').symlink_to('different')
    assert second!=runtime_tree(tmp_path)


def test_stagnation_requires_repeated_observations_and_resets_after_edit() -> None:
    from workflow_v2 import Stagnation
    monitor = Stagnation(limit=3)
    event = {'type': 'tool_execution_end', 'toolName': 'read', 'result': {'content': [{'text': 'same'}]}}
    assert not monitor.observe(event)
    assert not monitor.observe(event)
    assert monitor.observe(event)
    assert not monitor.observe({'type': 'tool_execution_end', 'toolName': 'edit', 'result': {}})
    assert not monitor.observe(event)


def test_completed_workflow_requires_final_model_stop() -> None:
    from workflow_v2 import completed
    assert not completed(0, [{'role': 'assistant', 'stopReason': 'error'}])
    assert not completed(124, [{'role': 'assistant', 'stopReason': 'stop'}])
    assert completed(0, [{'role': 'assistant', 'stopReason': 'stop'}])


def test_durable_invocation_bounds_inherited_pipe_timeout(tmp_path) -> None:
    import time
    from workflow_v2 import invoke
    started = time.monotonic()
    stdout, stderr, code = invoke(['bash', '-c', 'echo "{}"; sleep 60 & wait'], .2, tmp_path / 'stage', lambda text: text)
    assert code == 124 and time.monotonic() - started < 4
    assert (tmp_path / 'stage.jsonl').read_text() == '{}\n'
    assert (tmp_path / 'stage.stop.json').exists()


def test_recovery_keeps_prior_budget_and_requires_completed_review(tmp_path) -> None:
    import json
    import pytest
    from workflow_v2 import recovery
    (tmp_path / 'progress.json').write_text(json.dumps({'inferenceRequests': 41, 'elapsedSeconds': 645.7}))
    (tmp_path / 'stage-1.jsonl').write_text(json.dumps({'type':'message_end','message':{'role':'assistant','stopReason':'stop','content':[{'type':'text','text':'no major defects'}]}})+'\n')
    (tmp_path / 'stage-2.jsonl').write_text('')
    r = recovery(tmp_path)
    assert r['remainingRequests'] == 38  # one request reserve for interruption uncertainty
    assert r['remainingSeconds'] == pytest.approx(554.3)
    assert r['review'] == 'no major defects'
    (tmp_path / 'stage-1.jsonl').write_text('')
    with pytest.raises(ValueError, match='completed review'):
        recovery(tmp_path)


def test_recovery_shell_restores_patch_and_coverage_with_empty_or_nonempty_seed(tmp_path) -> None:
    import json
    import subprocess
    import run
    for empty in [False, True]:
        cwd=tmp_path/str(empty);cwd.mkdir()
        def git(*args):
            return subprocess.check_output(['git','-C',str(cwd),*args],text=True)
        git('init','-q');git('config','user.name','Fixture');git('config','user.email','fixture@localhost')
        (cwd/'source.txt').write_text('base\n');git('add','source.txt');git('commit','-qm','base')
        if not empty:(cwd/'source.txt').write_text('seed\n')
        seed=git('diff');(cwd/'seed.patch').write_text(seed)
        (cwd/'source.txt').write_text('partial repair\n');partial=git('diff');(cwd/'resume.patch').write_text(partial)
        (cwd/'source.txt').write_text('base\n');(cwd/'.e2e').mkdir()
        (cwd/'coverage.json').write_text(json.dumps({'1':{'tests':['actual']}}))
        subprocess.run(['bash','-c',run.apply_seed_script(str(cwd/'seed.patch'))],cwd=cwd,check=True)
        script=run.restore_recovery_script(str(cwd/'seed.patch'),str(cwd/'resume.patch'),str(cwd/'coverage.json'))
        subprocess.run(['bash','-n'],input=script,text=True,check=True)
        subprocess.run(['bash','-c',script],cwd=cwd,check=True)
        assert (cwd/'source.txt').read_text()=='partial repair\n'
        assert json.loads((cwd/'.e2e/coverage.json').read_text())['1']['tests']==['actual']
