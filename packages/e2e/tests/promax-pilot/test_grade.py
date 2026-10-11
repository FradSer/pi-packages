"""Preserve verifier diagnostics even when Docker grading times out."""
import subprocess
import run


def test_verifier_timeout_keeps_partial_logs(tmp_path, monkeypatch):
    # Given a slow independent verifier, when the host deadline expires, then
    # preserve observed output and classify the control as unsuccessful.
    def fake_command(args, **kwargs):
        if args[-1] == '/tmp/evaluate.sh':
            raise subprocess.TimeoutExpired(args, 2400, output=b'partial test output', stderr=b'compilation in progress')
        return subprocess.CompletedProcess(args, 0, '', '')
    monkeypatch.setattr(run, 'command', fake_command)
    result = run.grade({'image_name': 'fixture'}, '#!/bin/bash\n', '', tmp_path)
    assert result['passed'] is False
    assert (tmp_path / 'stdout.log').read_text() == 'partial test output'
    assert (tmp_path / 'stderr.log').read_text() == 'compilation in progress'


def test_task_command_override_does_not_require_a_repository_default():
    assert run.public_command({'instance_id': 'samber__lo-739', 'repo': 'samber/lo'}) == 'go test -p 1 ./...'


def test_image_proxy_defaults_cannot_intercept_the_internal_model_relay():
    # Given an image with proxy defaults, when starting offline workers, then
    # bypass the external proxy for the only authorized inference transport.
    for key in ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
        assert run.OFFLINE_ENV[key] == ''
    assert 'model-proxy' in run.OFFLINE_ENV['no_proxy'].split(',')
