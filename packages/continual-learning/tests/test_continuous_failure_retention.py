import io
import subprocess
import tarfile

from continuous_failure_retention import retain_failure_container


def archive(root: str, files: dict[str, bytes]) -> bytes:
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w') as tar:
        directory = tarfile.TarInfo(root)
        directory.type = tarfile.DIRTYPE
        tar.addfile(directory)
        for name, body in files.items():
            entry = tarfile.TarInfo(root + '/' + name)
            entry.size = len(body)
            entry.mode = 0o600
            tar.addfile(entry, io.BytesIO(body))
    return data.getvalue()


def test_stopped_container_preserves_source_and_all_ledgers_before_removal(tmp_path) -> None:
    # Given a stopped paid study container, When retention succeeds, Then
    # docker cp preserves every surface and actual bytes before any removal.
    calls = []

    def process(args):
        calls.append(args)
        if args[1] == 'rm':
            assert all((tmp_path / name).is_dir() for name in ('project', 'learning', 'memory', 'sessions'))
            return subprocess.CompletedProcess(args, 0, b'', b'')
        assert args[1] == 'cp' and args[-1] == '-'
        root = args[2].rsplit('/', 1)[-1]
        files = {'index.js': b'source', '.pi/harness.json': b'rules', '.memory/fact.md': b'fact',
                 'node_modules/ignored': b'dep'} if root == 'p-limit' else {'state.json': b'secret ledger'}
        return subprocess.CompletedProcess(args, 0, archive(root, files), b'')

    result = retain_failure_container('owned', tmp_path, process, lambda data: data.replace(b'secret', b'redacted'))
    assert result['passed'] and result['containerRemoved']
    assert (tmp_path / 'project/.pi/harness.json').read_bytes() == b'rules'
    assert (tmp_path / 'project/.memory/fact.md').read_bytes() == b'fact'
    assert not (tmp_path / 'project/node_modules').exists()
    assert (tmp_path / 'learning/state.json').read_bytes() == b'redacted ledger'
    assert calls[-1] == ['docker', 'rm', '-f', 'owned']
    assert not any('exec' in call for call in calls)


def test_copy_failure_keeps_the_only_container_and_partial_evidence(tmp_path) -> None:
    # Given one failed copy, When the other roots are retained, Then the
    # original container survives and missing usage is never imputed as zero.
    calls = []

    def process(args):
        calls.append(args)
        assert args[1] != 'rm'
        root = args[2].rsplit('/', 1)[-1]
        if root == 'sessions':
            return subprocess.CompletedProcess(args, 1, b'', b'private diagnostic')
        return subprocess.CompletedProcess(args, 0, archive(root, {'index.js': b'source'}), b'')

    result = retain_failure_container('owned', tmp_path, process, lambda data: data)
    assert not result['passed'] and not result['containerRemoved']
    assert result['surfaces']['sessions']['error'] == 'copy-failed'
    assert result['surfaces']['learning']['saved']
    assert 'private diagnostic' not in (tmp_path / 'retention.json').read_text()


def test_truncated_source_archive_cannot_authorize_removal(tmp_path) -> None:
    def process(args):
        assert args[1] != 'rm'
        root = args[2].rsplit('/', 1)[-1]
        value = archive(root, {'index.js': b'x' * 4096})
        return subprocess.CompletedProcess(args, 0, value[:1600] if root == 'p-limit' else value, b'')

    result = retain_failure_container('owned', tmp_path, process, lambda data: data)
    assert not result['passed'] and not result['containerRemoved']
    assert result['surfaces']['project']['error'] == 'retention-failed'


def test_study_failure_keeps_container_when_retention_is_incomplete(tmp_path, monkeypatch) -> None:
    import argparse
    import live_continuous_project_learning as study

    class Proxy:
        selection = {'provider': 'fixture', 'model': 'fixture'}
        requests = errors = jev_requests = 0
        jev_usage = []
        jev_observations = []
        token = 'fixture-token'
        jev_key = None
        key = None

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fail_configuration(*args):
        raise RuntimeError('fixture failed before task')

    def process(args, **kwargs):
        assert args[1:3] != ['rm', '-f'], 'Incomplete retention must not remove a container'
        return subprocess.CompletedProcess(args, 1, b'', b'')

    retained = []
    containers = iter(('owned-0', 'owned-1'))

    def retain(container, target, process, redact):
        retained.append(container)
        return {'passed': False, 'container': container, 'containerRemoved': False}

    monkeypatch.setattr(study, 'InferenceProxy', Proxy)
    monkeypatch.setattr(study.base, 'runtime_image', lambda image: 'fixture-image')
    monkeypatch.setattr(study.base, 'container', lambda image: next(containers))
    monkeypatch.setattr(study.base, 'shell', lambda *args: b'')
    monkeypatch.setattr(study.base, 'put', lambda *args: None)
    monkeypatch.setattr(study.base, 'checked', lambda args, **kwargs: b'{"ready":true}' if 'tsx' in args else b'')
    monkeypatch.setattr(study.base, 'configuration', fail_configuration)
    monkeypatch.setattr(study.base, 'process', process)
    monkeypatch.setattr(study, 'retain_failure_container', retain, raising=False)
    report = study.run(argparse.Namespace(output=tmp_path, source=tmp_path, base_image='fixture', preflight_only=False))
    assert report['status'] == 'failed' and len(retained) == 2
    assert len(report['retainedContainers']) == 2
    assert report['retentionIncomplete']
