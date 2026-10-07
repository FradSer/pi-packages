import copy
import json

import pytest

from evidence_structural_view import structural_request


def fixture():
    entries = [
        {'index': 2, 'entry': {'type': 'message', 'message': {'role': 'assistant', 'content': [{'type': 'toolCall', 'id': 'call1', 'name': 'bash', 'arguments': {'command': 'pnpm test'}}]}}},
        {'index': 3, 'entry': {'type': 'message', 'message': {'role': 'toolResult', 'toolCallId': 'call1', 'isError': False, 'content': [{'type': 'text', 'text': 'Passed, except integration was skipped'}]}}},
        {'index': 4, 'entry': {'role': 'user', 'content': 'Only use this command offline'}},
    ]
    return {'model': 'jev-1.13.0', 'state': json.dumps({'supportEvidence': {'entries': copy.deepcopy(entries[:1])}, 'reviewEvidence': {'entries': entries}}), 'questions': {'counter_description_0_0': {'type': 'choice', 'instructions': 'Original', 'criteria': {'compatible': 'No conflict', 'contradicts': 'Conflict', 'unclear': 'Unknown'}}}}


def test_original_state_questions_and_input_are_unchanged():
    original = fixture()
    before = copy.deepcopy(original)
    result = structural_request(original)
    assert original == before and result['questions'] == original['questions']
    old, new = json.loads(original['state']), json.loads(result['state'])
    assert {k: new[k] for k in old} == old
    view = new['structuralView']
    assert view['writeAuthorized'] is False
    assert len(view['reviewEvidence']) == 3
    assert view['reviewEvidence'][1]['fields']['content'] == old['reviewEvidence']['entries'][1]['entry']['message']['content']
    assert view['reviewEvidence'][2]['fields']['content'] == 'Only use this command offline'
    assert view['reviewEvidence'][1]['toolCallSources'] == ['reviewEvidence.entries[0].entry.message.content[0]']
    assert 'exitCode' not in view['reviewEvidence'][1]['fields']
    assert 'success' not in json.dumps(view)


def test_every_copied_field_has_a_resolving_source_path():
    result = json.loads(structural_request(fixture())['state'])
    for surface in ('supportEvidence', 'reviewEvidence'):
        for position, row in enumerate(result['structuralView'][surface]):
            entry = result[surface]['entries'][position]['entry']
            message = entry.get('message', entry)
            assert row['position'] == position
            assert row['index'] == result[surface]['entries'][position]['index']
            for field, value in row['fields'].items():
                assert value == message[field]
                prefix = f'{surface}.entries[{position}].entry'
                assert row['fieldSources'][field] == prefix + ('.message' if 'message' in entry else '') + '.' + field


@pytest.mark.parametrize('ambiguous', [False, True])
def test_missing_or_duplicate_call_reference_is_unresolved(ambiguous):
    request = fixture()
    state = json.loads(request['state'])
    if ambiguous:
        state['reviewEvidence']['entries'].insert(1, copy.deepcopy(state['reviewEvidence']['entries'][0]))
        state['reviewEvidence']['entries'][1]['index'] = 10
    else:
        state['reviewEvidence']['entries'][1]['entry']['message']['toolCallId'] = 'missing'
    request['state'] = json.dumps(state)
    rows = json.loads(structural_request(request)['state'])['structuralView']['reviewEvidence']
    result = next(row for row in rows if row['fields'].get('role') == 'toolResult')
    assert result['toolCallReference'] == ('ambiguous' if ambiguous else 'missing')
    assert len(result['toolCallSources']) == (2 if ambiguous else 0)


@pytest.mark.parametrize('mutation', ['model', 'collision', 'entries', 'message', 'index', 'size'])
def test_invalid_or_oversized_request_rejected(mutation):
    request = fixture()
    state = json.loads(request['state'])
    if mutation == 'model':
        request['model'] = 'jev-latest'
    elif mutation == 'collision':
        state['structuralView'] = {}
    elif mutation == 'entries':
        state['reviewEvidence']['entries'] = 'invalid'
    elif mutation == 'message':
        state['reviewEvidence']['entries'][0]['entry']['message'] = None
    elif mutation == 'index':
        state['reviewEvidence']['entries'][0]['index'] = True
    else:
        state['reviewEvidence']['entries'][0]['entry']['message']['content'] = 'x' * 64000
    request['state'] = json.dumps(state)
    with pytest.raises(ValueError):
        structural_request(request)


def test_later_call_is_not_a_prior_observation_reference():
    request = fixture()
    state = json.loads(request['state'])
    state['reviewEvidence']['entries'][:2] = list(reversed(state['reviewEvidence']['entries'][:2]))
    request['state'] = json.dumps(state)
    row = json.loads(structural_request(request)['state'])['structuralView']['reviewEvidence'][0]
    assert row['toolCallReference'] == 'missing' and row['toolCallSources'] == []


def test_call_from_other_evidence_surface_does_not_resolve_result():
    request = fixture()
    state = json.loads(request['state'])
    state['reviewEvidence']['entries'].pop(0)
    request['state'] = json.dumps(state)
    row = json.loads(structural_request(request)['state'])['structuralView']['reviewEvidence'][0]
    assert row['toolCallReference'] == 'missing' and row['toolCallSources'] == []


def test_question_count_bound_rejects_33():
    request = fixture()
    request['questions'] = {str(i): copy.deepcopy(next(iter(request['questions'].values()))) for i in range(33)}
    with pytest.raises(ValueError):
        structural_request(request)


def test_multibyte_bound_uses_bytes_instead_of_character_count():
    request = fixture()
    state = json.loads(request['state'])
    state['reviewEvidence']['entries'][2]['entry']['content'] = '界' * 11000
    request['state'] = json.dumps(state, ensure_ascii=False)
    assert len(request['state']) < 64000
    with pytest.raises(ValueError):
        structural_request(request)
