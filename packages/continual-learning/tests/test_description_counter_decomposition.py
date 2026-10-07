import copy
import json

import pytest

from description_counter_decomposition import paired_request, interpret


def fixture():
    return {'model': 'jev-1.13.0', 'state': json.dumps({'supportEvidence': {'entries': []}, 'reviewEvidence': {'entries': [{'index': 0, 'entry': {'role': 'user', 'content': 'public evidence'}}]}}), 'questions': {'counter_description_0_0': {'type': 'choice', 'instructions': {'question': 'Original question', 'candidate': {'content': 'Verified command'}}, 'criteria': {'compatible': 'No conflict', 'contradicts': 'Conflict', 'unclear': 'Unresolved'}}}}


def test_preserves_original_request_and_adds_only_diagnostic_questions():
    original = fixture()
    before = copy.deepcopy(original)
    result = paired_request(original, 'counter_description_0_0')
    assert original == before
    assert result['state'] == original['state'] and result['model'] == original['model']
    assert result['questions']['counter_description_0_0'] == original['questions']['counter_description_0_0']
    assert set(result['questions']) == {'counter_description_0_0', 'diagnostic_conflict', 'diagnostic_limitation'}
    for key in ('diagnostic_conflict', 'diagnostic_limitation'):
        assert result['questions'][key]['instructions']['candidate'] == {'content': 'Verified command'}
        assert result['questions'][key]['type'] == 'noul'
    assert 'conflicting' in result['questions']['diagnostic_conflict']['instructions']['question']
    assert 'unresolved' in result['questions']['diagnostic_limitation']['instructions']['question']


@pytest.mark.parametrize('conflict,limit,expected', [(0.1, 0.1, 'compatible'), (0.9, 0.01, 'conflict'), (0.01, 0.9, 'limitation'), (0.11, 0.01, 'uncertain'), (0.01, 0.5, 'uncertain'), (float('nan'), 0.01, 'invalid'), (True, 0.01, 'invalid')])
def test_thresholds_and_controlled_output(conflict, limit, expected):
    raw = {'model': 'jev-1.13.0', 'answers': {'counter_description_0_0': {'type': 'choice', 'choice': 'compatible', 'confidence': 0.95, 'probabilities': {'compatible': 0.95, 'contradicts': 0.02, 'unclear': 0.03}, 'raw': 'PRIVATE_CANARY'}, 'diagnostic_conflict': {'type': 'noul', 'noul': conflict}, 'diagnostic_limitation': {'type': 'noul', 'noul': limit}, 'PRIVATE_CANARY': {'content': 'PRIVATE_CANARY'}}}
    result = interpret(raw, 'counter_description_0_0')
    assert result['decomposed'] == expected
    assert result['writeAuthorized'] is False
    assert 'PRIVATE_CANARY' not in json.dumps(result)


def test_missing_wrong_model_and_untrusted_label_are_not_compatible():
    assert interpret({}, 'counter_description_0_0')['decomposed'] == 'invalid'
    assert interpret({'model': 'jev-latest'}, 'counter_description_0_0')['decomposed'] == 'invalid'
    raw = {'model': 'jev-1.13.0', 'answers': {'counter_description_0_0': {'type': 'choice', 'choice': 'PRIVATE_CANARY', 'confidence': 1, 'probabilities': {'PRIVATE_CANARY': 1}}}}
    assert interpret(raw, 'counter_description_0_0')['original'] == 'invalid'


def test_rejects_other_questions_and_models_before_transport():
    for key in ('counter_0_0', 'supported_description_0', 'PRIVATE_CANARY'):
        with pytest.raises(ValueError):
            paired_request(fixture(), key)
    original = fixture()
    original['model'] = 'jev-latest'
    with pytest.raises(ValueError):
        paired_request(original, 'counter_description_0_0')
