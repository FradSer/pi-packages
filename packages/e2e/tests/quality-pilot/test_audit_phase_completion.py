import json
from audit_phase_completion import audit_phase


def fixture(tmp_path, *, completed, events):
    (tmp_path / 'result.json').write_text(json.dumps({
        'exitCode': 0, 'transportErrors': 0, 'requests': 8, 'reportCompleted': completed,
    }))
    (tmp_path / 'events.jsonl').write_text(events)
    return tmp_path


def test_zero_exit_cannot_hide_model_error(tmp_path):
    # Given a successful process, when the model errors, then completion fails.
    folder = fixture(tmp_path, completed=True, events=json.dumps({
        'type': 'message_end', 'message': {'stopReason': 'error', 'errorMessage': '400 Bad Request'},
    }))
    audit = audit_phase(folder)
    assert audit['completedWithoutRecordedError'] is False
    assert audit['modelErrorCount'] == 1
    assert audit['errors'][0]['http400'] is True


def test_clean_report_is_complete(tmp_path):
    # Given a clean report, when it completes without error, then accept completion.
    folder = fixture(tmp_path, completed=True, events=json.dumps({
        'type': 'message_end', 'message': {'stopReason': 'stop'},
    }))
    assert audit_phase(folder)['completedWithoutRecordedError'] is True


def test_truncated_evidence_is_not_complete(tmp_path):
    # Given a nominal report, when evidence is truncated, then completion is unproven.
    folder = fixture(tmp_path, completed=True, events='{')
    assert audit_phase(folder)['completedWithoutRecordedError'] is False


def test_missing_report_is_not_complete(tmp_path):
    folder = fixture(tmp_path, completed=False, events='')
    assert audit_phase(folder)['completedWithoutRecordedError'] is False
