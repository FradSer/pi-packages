"""Given a timed-out real-model transport, exported evidence must omit credentials."""
from pathlib import Path
import json
import subprocess
import pytest

import docker_experiment as experiment


def test_timeout_evidence_redacts_all_transport_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Proxy:
        key = 'fixture-main-credential'
        jev_key = 'fixture-jev-credential'
        token = 'fixture-container-credential'

        def write_agent_config(self, root: Path) -> None:
            root.mkdir()
            (root / 'settings.json').write_text('{}')

        def jev_environment(self) -> dict[str, str]:
            return {'TYPESAFE_API_KEY': self.token}

    def command(args: list[str], **kwargs: object) -> str:
        return 'fixture-container' if args[1] == 'run' else ''

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if '-c' in args:
            return subprocess.CompletedProcess(args, 0, '', '')
        raise subprocess.TimeoutExpired(args + [Proxy.key, Proxy.jev_key], 1)

    monkeypatch.setattr(experiment, 'command', command)
    monkeypatch.setattr(experiment.subprocess, 'run', run)
    output = tmp_path / 'evidence'
    result = experiment.run_project('fixture-image', 'fixture-digest', Proxy(),
        {'name': 'p-limit', 'repository': 'public-fixture', 'commit': 'public-fixture'}, output, jev_enabled=True)
    serialized = json.dumps(result) + ''.join(p.read_text() for p in output.iterdir() if p.is_file())
    assert result['status'] == 'failed'
    assert 'timed out' in result['error']
    assert all(secret not in serialized for secret in (Proxy.key, Proxy.jev_key, Proxy.token))


def test_copied_artifacts_and_merged_report_redact_transport_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Proxy:
        key = 'fixture-main-copy-secret'
        jev_key = 'fixture-jev-copy-secret'
        token = 'fixture-container-copy-secret'

        def write_agent_config(self, root: Path) -> None:
            root.mkdir()
            (root / 'settings.json').write_text('{}')

        def jev_environment(self) -> dict[str, str]:
            return {'TYPESAFE_API_KEY': self.token}

    def command(args: list[str], **kwargs: object) -> str:
        if args[1] == 'cp':
            target = Path(args[-1])
            (target / 'report.json').write_text(json.dumps({'status': 'failed', 'error': Proxy.token}))
            (target / 'failure.txt').write_text(Proxy.key + Proxy.jev_key)
            (target / 'public.md').write_bytes(b'Unchanged\r\npublic bytes\r')
        return 'fixture-container' if args[1] == 'run' else ''

    monkeypatch.setattr(experiment, 'command', command)
    monkeypatch.setattr(experiment.subprocess, 'run', lambda args, **kwargs: subprocess.CompletedProcess(args, 0, '', ''))
    output = tmp_path / 'copied'
    result = experiment.run_project('fixture-image', 'fixture-digest', Proxy(),
        {'name': 'p-limit', 'repository': 'public-fixture', 'commit': 'public-fixture'}, output, jev_enabled=True)
    serialized = json.dumps(result) + ''.join(p.read_text() for p in output.iterdir() if p.is_file())
    assert result['status'] == 'failed'
    assert all(secret not in serialized for secret in (Proxy.key, Proxy.jev_key, Proxy.token))
    assert (output / 'failure.txt').read_text() == '[redacted][redacted]'
    assert (output / 'public.md').read_bytes() == b'Unchanged\r\npublic bytes\r'


def test_docker_errors_redact_before_bounded_output_truncation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Proxy:
        key = 'fixture-main-truncation-secret'
        jev_key = 'fixture-jev-truncation-secret'
        token = 'fixture-container-truncation-secret'

        def write_agent_config(self, root: Path) -> None:
            root.mkdir()
            (root / 'settings.json').write_text('{}')

        def jev_environment(self) -> dict[str, str]:
            return {'TYPESAFE_API_KEY': self.token}

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ['docker', 'run']:
            return subprocess.CompletedProcess(args, 0, 'fixture-container', '')
        if args[:2] in (['docker', 'cp'], ['docker', 'rm']):
            return subprocess.CompletedProcess(args, 1, '', Proxy.token + 'x' * 1990)
        return subprocess.CompletedProcess(args, 0, '', '')

    monkeypatch.setattr(experiment.subprocess, 'run', run)
    output = tmp_path / 'truncated'
    result = experiment.run_project('fixture-image', 'fixture-digest', Proxy(),
        {'name': 'p-limit', 'repository': 'public-fixture', 'commit': 'public-fixture'}, output, jev_enabled=True)
    serialized = json.dumps(result) + ''.join(p.read_text() for p in output.iterdir() if p.is_file())
    assert result['status'] == 'failed'
    assert 'artifactError' in result and 'cleanupError' in result
    assert Proxy.token[-10:] not in serialized


def test_credential_bearing_artifact_paths_are_rejected_before_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Proxy:
        key = 'fixture-main-path-secret'
        jev_key = 'fixture-jev-path-secret'
        token = 'fixture-container-path-secret'

        def write_agent_config(self, root: Path) -> None:
            root.mkdir()
            (root / 'settings.json').write_text('{}')

        def jev_environment(self) -> dict[str, str]:
            return {'TYPESAFE_API_KEY': self.token}

    def command(args: list[str], **kwargs: object) -> str:
        if args[1] == 'cp':
            target = Path(args[-1])
            (target / (Proxy.token + '.txt')).write_text('public fixture')
        return 'fixture-container' if args[1] == 'run' else ''

    monkeypatch.setattr(experiment, 'command', command)
    monkeypatch.setattr(experiment.subprocess, 'run', lambda args, **kwargs: subprocess.CompletedProcess(args, 0, '', ''))
    output = tmp_path / 'path-export'
    result = experiment.run_project('fixture-image', 'fixture-digest', Proxy(),
        {'name': 'p-limit', 'repository': 'public-fixture', 'commit': 'public-fixture'}, output, jev_enabled=True)
    assert result['status'] == 'failed'
    assert 'artifactError' in result
    assert all(Proxy.token not in str(path) for path in output.rglob('*'))
