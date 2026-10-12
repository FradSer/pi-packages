from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

import docker_experiment as experiment


def test_policy_patch_is_exact_and_default_preserves_bytes() -> None:
    original = b'before\n  const jevJudge = createJevJudge();\nafter\n'
    assert experiment.memory_policy_bytes(original, 'default') == original
    composed = experiment.memory_policy_bytes(original, 'composed')
    assert b'independentMemoryApplication: true, composedMemoryApplication: true' in composed
    assert experiment.memory_policy_bytes(composed, "composed") == composed
    with pytest.raises(ValueError, match="constructor"):
        experiment.memory_policy_bytes(original + composed, "composed")
    assert composed.startswith(b'before\n  ') and composed.endswith(b'\nafter\n')
    for invalid in [b'no constructor', original + original]:
        with pytest.raises(ValueError, match='constructor'):
            experiment.memory_policy_bytes(invalid, 'composed')
    with pytest.raises(ValueError, match='policy'):
        experiment.memory_policy_bytes(original, 'unknown')


def test_composed_context_changes_only_copy_and_retains_provenance(tmp_path) -> None:
    original = (experiment.PACKAGE / 'extensions/inject-memory.ts').read_bytes()
    source = tmp_path / 'extensions/inject-memory.ts'
    source.parent.mkdir()
    source.write_bytes(original)
    manifest = experiment.prepare_memory_policy(tmp_path, 'composed')
    assert manifest['originalSha256'] == hashlib.sha256(original).hexdigest()
    assert manifest['installedSha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert source.read_bytes() == experiment.memory_policy_bytes(original, 'composed')
    assert (experiment.PACKAGE / 'extensions/inject-memory.ts').read_bytes() == original
    assert (tmp_path / 'tests/fixtures/project-policy-original-inject-memory.ts.txt').read_bytes() == original
    assert experiment.verify_memory_policy(tmp_path, 'composed') == manifest
    with pytest.raises(AssertionError, match='differs'):
        experiment.verify_memory_policy(tmp_path, 'default')
    source.write_bytes(source.read_bytes() + b'\n// altered\n')
    with pytest.raises(AssertionError, match='changed'):
        experiment.verify_memory_policy(tmp_path, 'composed')


def test_expected_policy_digest_matches_actual_installed_bytes(tmp_path, monkeypatch) -> None:
    ordinary = experiment.source_digest()
    expected = experiment.source_digest('composed')
    # Production now includes this policy; historical composed copies are identical.
    assert ordinary == expected
    repo = tmp_path / 'repo'
    for name in ['kit', 'continual-learning']:
        shutil.copytree(experiment.REPO / 'packages' / name, repo / 'packages' / name,
                        ignore=shutil.ignore_patterns('node_modules', '__pycache__', '.pytest_cache', '.memory', '.pi', '.git'))
    package = repo / 'packages/continual-learning'
    experiment.prepare_memory_policy(package, 'composed')
    monkeypatch.setattr(experiment, 'REPO', repo)
    monkeypatch.setattr(experiment, 'PACKAGE', package)
    assert experiment.source_digest() == expected
    source = package / 'extensions/inject-memory.ts'
    source.write_bytes(source.read_bytes() + b'\n// unexpected mutation\n')
    assert experiment.source_digest() != expected


def test_default_context_keeps_factory_and_validates_manifest(tmp_path) -> None:
    source = tmp_path / 'extensions/inject-memory.ts'
    source.parent.mkdir()
    original = b'const jevJudge = createJevJudge();\n'
    source.write_bytes(original)
    manifest = experiment.prepare_memory_policy(tmp_path, 'default')
    assert source.read_bytes() == original
    assert experiment.verify_memory_policy(tmp_path, 'default') == manifest
    assert not (tmp_path / 'tests/fixtures/project-policy-original-inject-memory.ts.txt').exists()
