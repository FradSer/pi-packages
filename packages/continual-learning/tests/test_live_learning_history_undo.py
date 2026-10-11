from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from live_learning_history_undo import snapshot_surfaces, assert_restored


def test_restoration_detects_bytes_permissions_and_new_files(tmp_path):
    root = tmp_path / 'surface'
    root.mkdir()
    target = root / 'existing.md'
    target.write_bytes(b'original\r\n')
    target.chmod(0o640)
    before = snapshot_surfaces({'memory': root})
    target.write_bytes(b'changed\n')
    with pytest.raises(AssertionError):
        assert_restored(before, snapshot_surfaces({'memory': root}))
    target.write_bytes(b'original\r\n')
    target.chmod(0o600)
    with pytest.raises(AssertionError):
        assert_restored(before, snapshot_surfaces({'memory': root}))
    target.chmod(0o640)
    added = root / 'new.md'
    added.write_text('new')
    with pytest.raises(AssertionError):
        assert_restored(before, snapshot_surfaces({'memory': root}))
    added.unlink()
    assert_restored(before, snapshot_surfaces({'memory': root}))


def test_snapshot_refuses_symlink(tmp_path):
    (tmp_path / 'unsafe.md').symlink_to('/etc/hosts')
    with pytest.raises(AssertionError, match='symlink'):
        snapshot_surfaces({'memory': tmp_path})


def test_cancel_requires_a_new_confirmation_event():
    from live_learning_history_undo import cancel_observed
    old = [{'kind': 'confirmed', 'value': False}]
    assert not cancel_observed(old, len(old))
    assert cancel_observed(old + [{'kind': 'confirmed', 'value': False}], len(old))


def test_truthful_result_rejects_missing_display_or_wrong_phase():
    from live_learning_history_undo import validate_learning_result
    receipt = {'attempts': [{'phase': 'memory', 'outcome': 'applied', 'operations': 1}, {'phase': 'harness', 'outcome': 'applied', 'operations': 1}]}
    with pytest.raises(AssertionError):
        validate_learning_result(receipt, [], {}, '')
    with pytest.raises(AssertionError):
        validate_learning_result(receipt, [{'phase': 'memory', 'status': 'applied', 'changes': []}], {}, '1 memory and 1 harness change applied')


def test_truthful_result_checks_history_bytes_and_phase():
    import base64
    import hashlib
    from live_learning_history_undo import validate_learning_result
    data = b'fact'
    digest = hashlib.sha256(data).hexdigest()
    state = {'bytes': base64.b64encode(data).decode(), 'digest': digest, 'mode': 0o600}
    records = [
        {'phase': 'harness', 'status': 'applied', 'changes': [{'target': {'root': 'project', 'name': '.pi/harness.json'}, 'after': state}]},
        {'phase': 'memory', 'status': 'applied', 'changes': [{'target': {'root': 'private', 'name': 'fact.md'}, 'after': state}]},
    ]
    learned = {key: {'sha256': digest, 'bytes': data.hex(), 'mode': 0o600} for key in ('harness', 'private/fact.md')}
    receipt = {'attempts': [{'phase': phase, 'outcome': 'applied', 'operations': 1} for phase in ('memory', 'harness')]}
    visible = '1 memory and 1 harness change applied'
    validate_learning_result(receipt, records, learned, visible)
    records[0]['phase'] = 'memory'
    with pytest.raises(AssertionError, match='phases'):
        validate_learning_result(receipt, records, learned, visible)
    records[0]['phase'] = 'harness'
    learned['private/fact.md']['bytes'] = b'wrong'.hex()
    with pytest.raises(AssertionError):
        validate_learning_result(receipt, records, learned, visible)


def test_evidence_runs_never_overwrite_and_detect_source_drift(tmp_path):
    from live_acceptance_support import EvidenceRun
    source = tmp_path / 'source.ts'
    source.write_text('original')
    first = EvidenceRun(tmp_path / 'evidence', {'source.ts': source})
    second = EvidenceRun(tmp_path / 'evidence', {'source.ts': source})
    assert first.output != second.output
    first.write('sentinel.txt', 'keep')
    source.write_text('changed')
    with pytest.raises(AssertionError, match='source'):
        first.verify_sources()
    first.finish({'status': 'passed'})
    assert __import__('json').loads((first.output / 'manifest.json').read_text())['status'] == 'failed'
    assert (first.output / 'sentinel.txt').read_text() == 'keep'
    assert (first.output / 'gallery.zh-CN.md').is_file()


def test_dialog_results_are_bound_to_the_current_dialog():
    from live_acceptance_support import dialog_result
    rows = [{'kind': 'confirmed', 'dialogId': 1, 'value': False}, {'kind': 'confirmed', 'dialogId': 2, 'value': True}]
    assert not dialog_result(rows, 0, 2, False)
    assert dialog_result(rows, 1, 2, True)


def test_offline_preflight_rejects_inherited_services_and_remote_provider(tmp_path):
    import json
    from live_acceptance_support import preflight
    project, agent = tmp_path / 'project', tmp_path / 'agent'
    project.mkdir(); agent.mkdir()
    (agent / 'continual-learning.json').write_text(json.dumps({'jev': False}))
    (agent / 'memory.json').write_text(json.dumps({'provider': 'fixture', 'model': 'test'}))
    (agent / 'models.json').write_text(json.dumps({'providers': {'fixture': {'baseUrl': 'https://example.com/v1'}}}))
    env = {'HOME': str(tmp_path), 'PI_CODING_AGENT_DIR': str(agent)}
    with pytest.raises(AssertionError, match='loopback'):
        preflight(tmp_path, project, agent, env, real_model=False)
    (agent / 'models.json').write_text(json.dumps({'providers': {'fixture': {'baseUrl': 'http://127.0.0.1:1234/v1'}}}))
    assert preflight(tmp_path, project, agent, env, real_model=False)['provider'] == 'fixture'
    with pytest.raises(AssertionError, match='environment'):
        preflight(tmp_path, project, agent, {**env, 'TYPESAFE_API_KEY': 'inherited'}, real_model=False)


def test_private_copy_selects_one_provider_and_tracks_oauth_secrets(tmp_path):
    import json
    from live_acceptance_support import private_provider_copy
    source, agent = tmp_path / 'source', tmp_path / 'agent'
    source.mkdir(); agent.mkdir()
    (source / 'auth.json').write_text(json.dumps({'chosen': {'access': 'synthetic-access-value', 'refresh': 'synthetic-refresh-value'}, 'other': {'key': 'unrelated-private-value'}}))
    values = private_provider_copy(source, agent, 'chosen')
    copied = json.loads((agent / 'auth.json').read_text())
    assert set(copied) == {'chosen'}
    assert (agent / 'auth.json').stat().st_mode & 0o077 == 0
    assert b'synthetic-access-value' in values and b'synthetic-refresh-value' in values


def test_failed_capture_still_closes_terminal(tmp_path):
    from live_acceptance_support import archive_terminal
    closed = []
    def reject(data):
        raise AssertionError('Refused credential')
    with pytest.raises(AssertionError, match='credential'):
        archive_terminal(b'private bytes', tmp_path / 'events', tmp_path, reject, lambda: closed.append(True))
    assert closed == [True]
    assert not (tmp_path / 'terminal.ansi').exists()


def test_real_model_result_allows_multiple_valid_operations():
    import base64
    import hashlib
    from live_learning_history_undo import validate_learning_result
    data = b'settled fact'
    digest = hashlib.sha256(data).hexdigest()
    state = {'bytes': base64.b64encode(data).decode(), 'digest': digest, 'mode': 0o600}
    records = [{'phase': 'memory', 'status': 'applied', 'changes': [{'target': {'root': 'private', 'name': 'fact.md'}, 'after': state}]}]
    learned = {'private/fact.md': {'sha256': digest, 'bytes': data.hex(), 'mode': 0o600}}
    receipt = {'attempts': [{'phase': 'memory', 'outcome': 'applied', 'operations': 2}]}
    validate_learning_result(receipt, records, learned, '2 memories applied', real_model=True)
    receipt['attempts'].append({'phase': 'memory', 'outcome': 'failed', 'operations': 0})
    with pytest.raises(AssertionError):
        validate_learning_result(receipt, records, learned, '2 memories applied', real_model=True)


def test_loopback_runner_does_not_inherit_service_environment(tmp_path, monkeypatch):
    import json
    import live_learning_loop
    from types import SimpleNamespace
    captured = {}
    monkeypatch.setenv('TYPESAFE_API_KEY', 'must-not-inherit')
    monkeypatch.setattr(live_learning_loop, 'workspace_pi', lambda _repo: '/fixture/pi')
    def launch(*args, **kwargs):
        captured['keys'] = list(kwargs['env'])
        captured['home'] = kwargs['env'].get('HOME')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(live_learning_loop.subprocess, 'run', launch)
    agent = tmp_path / 'agent'
    agent.mkdir()
    live_learning_loop.run_pi(tmp_path, agent, tmp_path / 'session.jsonl', 'synthetic', 1234)
    assert 'TYPESAFE_API_KEY' not in captured['keys']
    assert captured['home'] == str(tmp_path)
