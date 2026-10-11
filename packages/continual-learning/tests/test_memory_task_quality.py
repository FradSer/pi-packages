from memory_task_quality_cases import cases


def test_cases_have_independent_oracles_and_no_hidden_file_leak():
    from live_memory_task_quality import score, summarize
    rows = cases('heldout')
    assert len(rows) == 12
    assert len({row['id'] for row in rows}) == 12
    for row in rows:
        assert row['expected'] not in row['task'] or row['expected'] == 'unknown'
        assert score({'value': row['expected']}, row)['correct']
        assert not score({'value': row['obsolete']}, row)['correct']
        assert not score({'value': row['expected'], 'extra': True}, row)['correct']
    result = summarize([{'id':'a','category':'durable','baseline':{'correct':False},'memory':{'correct':True}},
                        {'id':'b','category':'conflict','baseline':{'correct':True},'memory':{'correct':False}}])
    assert result['improvements'] == ['a'] and result['regressions'] == ['b']
    assert not result['acceptance']


def test_training_errors_cannot_pass_acceptance_even_if_answers_are_correct():
    from live_memory_task_quality import summarize
    row = {'id':'a','category':'durable','training':[{'error':'process-timeout'}],
           'baseline':{'correct':False},'memory':{'correct':True}}
    result = summarize([row])
    assert not result['acceptance']
    assert result['trainingFailures'] == ['a']


def test_task_cannot_modify_current_evidence_or_leave_cross_arm_files(tmp_path):
    from live_memory_task_quality import task_snapshot, assert_task_unchanged
    import pytest
    (tmp_path/'current.json').write_text('{"value":"current"}')
    before = task_snapshot(tmp_path)
    (tmp_path/'answer.json').write_text('{"value":"answer"}')
    assert_task_unchanged(tmp_path,before)
    (tmp_path/'leak.txt').write_text('leak')
    with pytest.raises(RuntimeError,match='Task mutated'):
        assert_task_unchanged(tmp_path,before)


def test_provider_failure_is_not_a_memory_improvement():
    from live_memory_task_quality import summarize
    row = {'id':'a','category':'durable', 'baseline':{'correct':False,'errors':['rate limited']},
           'memory':{'correct':True}}
    result = summarize([row])
    assert result['improvements'] == []
    assert result['invalidPairs'] == ['a']
    assert not result['acceptance']


def test_real_result_message_receipts_and_missing_learning_are_checked():
    from live_memory_task_quality import learning_receipts, training_ok
    receipt = {'kind':'learning-pipeline-receipt','attempts':[{'phase':'memory','outcome':'rejected'}]}
    messages = [{'role':'custom','customType':'continual-learning-result','details':receipt}]
    found = learning_receipts(messages)
    assert found == [receipt]
    assert not training_ok({'training':[{'exitCode':0,'errors':[],'receipts':found}]})
    assert not training_ok({'training':[{'exitCode':0,'errors':[],'receipts':[]}]})


def test_transfer_task_requires_memory_plus_current_catalogue():
    rows = cases('heldout',task_type='resolve')
    assert len(rows) == 12
    for row in rows:
        assert 'catalog.json' in row['files']
        assert row['expected'] not in '\n'.join(row['training']) or row['expected'] == 'unknown'
        assert row['expected'] not in row['task'] or row['expected'] == 'unknown'
        if row['category'] in {'durable','conflict','correction'}:
            assert row['expected'] != row['knowledgeExpected']
            assert row['files']['catalog.json']['aliases'][row['knowledgeExpected']]['handoffValue'] == row['expected']


def test_transfer_catalogue_has_distractors_and_no_fixed_answer_position():
    rows = cases('heldout',task_type='resolve')
    positions = set()
    for row in rows:
        keys = list(row['files']['catalog.json']['aliases'])
        assert len(keys) >= 5
        positions.add(keys.index(row['currentAlias']))
    assert len(positions) >= 3


def test_case_category_is_not_revealed_in_task_subject():
    for row in cases('heldout',task_type='resolve'):
        assert row['category'] not in row['subject']
