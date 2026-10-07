from __future__ import annotations

from pathlib import Path

import pytest

import docker_experiment
import live_docker_projects as workflow


def test_default_cohort_preserves_three_historical_projects() -> None:
    assert [p['name'] for p in workflow.select_projects('historical')] == ['click', 'p-limit', 'mitt']


def test_heldout_cohort_is_frozen_and_matches_verified_commands() -> None:
    projects = workflow.select_projects('heldout')
    assert [p['name'] for p in projects] == ['yocto-queue', 'humanize', 'referencing']
    assert [p['commit'] for p in projects] == [
        '72a8fa96a9d389765cdf2bb9c6daba8302fc375d',
        '785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b',
        'f6adc7b74af8347e2c59c45256be7b8a8030a3f5',
    ]
    assert workflow.TASKS['yocto-queue']['check'] == ['pnpm', 'test']
    assert workflow.TASKS['humanize']['check'] == ['uv', 'run', '--no-sync', 'pytest', '-q']
    assert workflow.TASKS['referencing']['check'] == ['uv', 'run', '--no-sync', 'pytest', '-q', 'referencing']
    assert workflow.select_projects('heldout', 'humanize') == [projects[1]]
    with pytest.raises(ValueError, match='cohort'):
        workflow.select_projects('heldout', 'click')
    with pytest.raises(ValueError, match='cohort'):
        workflow.select_projects('historical', 'referencing')


def test_heldout_environment_preserves_pinned_suite_and_source(tmp_path, monkeypatch) -> None:
    calls = []
    project = tmp_path / 'referencing'
    project.mkdir()

    def checked(args, cwd, label):
        calls.append((args, cwd, label))
        return {'exitCode': 0}

    monkeypatch.setattr(workflow, 'checked', checked)
    monkeypatch.setattr(workflow, 'command', lambda args:
        '8a502de2f75cd436ecf023b350c1bd0698f3a395\n')
    workflow.prepare_heldout_dependencies('referencing', project)
    assert calls[0][0] == ['git', 'submodule', 'update', '--init', '--depth', '1', 'suite']
    assert calls[1][0] == ['uv', 'sync', '--python', '3.13', '--group', 'dev']
    monkeypatch.setattr(workflow, 'command', lambda args: 'wrong-commit\n')
    with pytest.raises(AssertionError, match='suite'):
        workflow.prepare_heldout_dependencies('referencing', project)
    assert len(calls) == 3  # Wrong suite must stop before dependency installation.


def test_source_digest_binds_heldout_catalog(monkeypatch) -> None:
    catalog = workflow.PACKAGE / 'tests/heldout_project_catalog.py'
    original = Path.read_bytes
    before = docker_experiment.source_digest()

    def changed(path):
        value = original(path)
        return value + b'\n# changed metadata\n' if path == catalog else value

    monkeypatch.setattr(Path, 'read_bytes', changed)
    assert docker_experiment.source_digest() != before


@pytest.mark.parametrize('policy', ['default', 'composed'])
def test_main_dispatch_pins_requested_model_and_forwards_cohort(tmp_path, monkeypatch, policy) -> None:
    # Offline host-runner wiring: no Docker build, network or inference.
    import sys
    observed = {}

    class Proxy:
        requests = errors = jev_requests = 0
        jev_usage = []

        def __init__(self, root, **kwargs):
            observed['selection'] = kwargs['selection']

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def run_project(image, digest, proxy, project, output, **kwargs):
        observed['project'] = project
        return {'project': project['name'], 'status': 'passed'}

    monkeypatch.setattr(sys, 'argv', ['workflow', '--cohort', 'heldout', '--project', 'humanize',
                                    '--memory-policy', policy, '--output', str(tmp_path / 'output')])
    def build_image(memory_policy):
        observed['builtPolicy'] = memory_policy
        return 'fixture-image', 'fixture-digest'
    monkeypatch.setattr(workflow, 'build_image', build_image)
    monkeypatch.setattr(workflow, 'command', lambda args: 'fixture-image-id')
    monkeypatch.setattr(workflow, 'InferenceProxy', Proxy)
    monkeypatch.setattr(workflow, 'run_project', run_project)
    with pytest.raises(SystemExit) as exit:
        workflow.main()
    assert exit.value.code == 0
    assert observed['selection'] == {'provider': 'cli-proxy', 'model': 'opencode/deepseek-v4.1-flash'}
    assert observed['project']['cohort'] == 'heldout'
    assert observed['project']['name'] == 'humanize'
    assert observed['project']['memoryPolicy'] == policy and observed['builtPolicy'] == policy
