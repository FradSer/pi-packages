"""Given an incomplete reviewer, preserve real findings and reserve a handoff."""
from pathlib import Path
import engine


def test_native_packet_contains_actual_tool_results_only():
    events = [
        {'type': 'message_end', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'unsupported claim'}]}},
        {'type': 'tool_execution_end', 'toolName': 'e2e_verify', 'result': {'details': {'verifiedRun': True}}},
    ]
    assert engine.packet('e2e', events) == {'source': 'native E2E results', 'results': [{'details': {'verifiedRun': True}}]}


def test_incomplete_review_handoff_preserves_diagnostics(monkeypatch):
    calls = []
    def summarize(*args, **kwargs):
        calls.append(kwargs)
        return {'reportCompleted': False, 'events': []}
    monkeypatch.setattr(engine, 'stage', summarize)
    original = {'reportCompleted': False, 'events': [{'type': 'tool_execution_end', 'toolName': 'e2e_verify', 'result': {'error': 'missing coverage'}}]}
    output = engine.handoff(None, Path('.'), Path('solution.mjs'), Path('handoff'), original, 'e2e')
    assert output['events'] == original['events']
    assert calls == [{'tools': '', 'allowance': 1}]


def test_completed_report_does_not_spend_an_extra_request(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('unexpected model call')
    monkeypatch.setattr(engine, 'stage', forbidden)
    original = {'reportCompleted': True, 'events': []}
    assert engine.handoff(None, Path('.'), Path('solution.mjs'), Path('handoff'), original, 'baseline') is original


def test_registered_task_requests_fit_global_reservation():
    assert 4 * ((8+1) + (5+1) + (5+1) + 2*(8+1)) + 5 <= engine.MAX_REQUESTS


def test_grade_timeout_is_recorded_and_container_cleaned(monkeypatch, tmp_path):
    import study
    import subprocess
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        if args[:2] == ['docker', 'run']:
            raise subprocess.TimeoutExpired(args, 30)
        return ''
    monkeypatch.setattr(study, 'cmd', command)
    source = tmp_path / 'solution.mjs'
    source.write_text('while(true){}')
    result = study.grade('memo', source, tmp_path / 'grade.json')
    assert result['status'] == 'grading_timeout'
    assert result['passed'] is None
    assert calls[-1][:3] == ['docker', 'rm', '-f']


def test_fresh_process_and_usage_do_not_prove_semantic_success():
    from study import semantic_mechanism_proven
    data = {'details': {'verifiedRun': True, 'ok': True, 'status': 'fulfilled', 'unjudged': 0,
                        'model': 'jev-1.13.0', 'clauses': []}}
    usage = [{'model': 'jev-1.13.0', 'input_tokens': 10, 'output_tokens': 1}]
    assert not semantic_mechanism_proven([data], usage)
    data['details']['clauses'] = [{'clause': 2, 'source': 'jev', 'status': 'met'}]
    assert semantic_mechanism_proven([data], usage)
    data['details']['modelError'] = 'provider failure'
    assert not semantic_mechanism_proven([data], usage)
