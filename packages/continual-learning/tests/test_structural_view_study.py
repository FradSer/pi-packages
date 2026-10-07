from structural_view_study import paired_metrics


def test_missing_arm_is_incomplete_not_a_correct_rejection():
    samples = [{'id': 'a', 'expectedCompatible': True}, {'id': 'b', 'expectedCompatible': False}]
    rows = [{'id': 'a', 'arm': 'original', 'judgment': 'compatible'},
            {'id': 'a', 'arm': 'structural', 'judgment': 'uncertain'},
            {'id': 'b', 'arm': 'original', 'judgment': 'conflict'}]
    result = paired_metrics(samples, rows)
    assert result['completePairs'] == 1 and result['incompletePairs'] == 1
    assert result['original']['falseHolds'] == 0
    assert result['structural']['falseHolds'] == 1
    assert result['lostOriginalValid'] == 1
    assert result['meetsComponentCriterion'] is False


def test_more_compatible_with_false_acceptance_is_not_improvement():
    samples = [{'id': 'a', 'expectedCompatible': True}, {'id': 'b', 'expectedCompatible': False}]
    rows = [{'id': s['id'], 'arm': arm, 'judgment': 'compatible' if arm == 'structural' else 'uncertain'}
            for s in samples for arm in ('original', 'structural')]
    result = paired_metrics(samples, rows)
    assert result['structural']['falseCompatible'] == 1
    assert result['meetsComponentCriterion'] is False


def test_strict_complete_component_improvement_grants_no_authority():
    samples = [{'id': 'a', 'expectedCompatible': True}]
    result = paired_metrics(samples, [{'id': 'a', 'arm': 'original', 'judgment': 'uncertain'},
                                     {'id': 'a', 'arm': 'structural', 'judgment': 'compatible'}])
    assert result['meetsComponentCriterion'] is True
    assert result['writeAuthorized'] is False and result['completeGoalEvidence'] is False
