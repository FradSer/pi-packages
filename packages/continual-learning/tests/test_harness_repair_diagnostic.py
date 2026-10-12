from __future__ import annotations

import hashlib
import json
import pytest
import subprocess
from copy import deepcopy
import live_harness_repair_diagnostic as diagnostic
from live_harness_repair_diagnostic import complete_reads, repair_continuity, frozen_validation_context


def test_complete_frozen_evidence_cannot_be_inferred_from_partial_or_changed_reads(tmp_path) -> None:
    reads = []
    for name in ('snapshot.json', 'dossier.json'):
        file = tmp_path / name
        file.write_text('first\nlast')
        reads.append({'path': str(file), 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
                      'offset': 1, 'limit': 1, 'result': 'first\n[lines 1-1 of 2]'})
    assert not complete_reads(tmp_path, reads)
    for read in list(reads):
        reads.append({**read, 'offset': 2, 'result': 'last\n[lines 2-2 of 2]'})
    assert complete_reads(tmp_path, reads)
    assert not complete_reads(tmp_path, [{**read, 'result': read['result'] + '\nbyte limit reached'} for read in reads])
    assert not complete_reads(tmp_path, [{**read, 'sha256': 'changed'} for read in reads])
    assert not complete_reads(tmp_path, [{**read, 'error': 'refused'} for read in reads])


def test_repair_cannot_erase_failing_cases_quotes_or_restriction() -> None:
    original = {'operations': [{'op': 'addRule', 'rule': {'id': 'npm', 'action': 'block', 'bash': '^npm '},
                               'cases': {'positive': [{'bash': 'npm\r', 'expected': 'block'}], 'negative': [{'bash': 'pnpm test'}]}}],
                'evidence': [{'index': 0, 'source': 'user', 'quote': 'original'}]}
    fixed = deepcopy(original)
    fixed['operations'][0]['rule']['bash'] = '^npm(?: |\\r)'
    assert repair_continuity(original, fixed)
    for key, value in [('id', 'other'), ('action', 'execute'), ('enabled', False)]:
        changed = deepcopy(fixed)
        changed['operations'][0]['rule'][key] = value
        assert not repair_continuity(original, changed)
    for kind in ('positive', 'negative'):
        changed = deepcopy(fixed)
        changed['operations'][0]['cases'][kind] = []
        assert not repair_continuity(original, changed)
    assert not repair_continuity(original, {**fixed, 'evidence': []})


def test_missing_raw_ownership_cannot_be_reconstructed_from_custom_summary() -> None:
    surface = {'rules': [{'source': 'built-in defaults'}], 'availableSkills': [], 'invalidRules': [],
               'learnedRules': {}, 'errors': [], 'reservedLegacyNames': []}
    def prompt(value: dict) -> str:
        return '- Current harness surface summary:\n' + json.dumps(value) + '\n- Target layer'
    assert frozen_validation_context(prompt(surface)) == {'layers': [], 'learnedRules': {}, 'targetSource': 'project', 'availableSkills': []}
    for change in ({'rules': [{'source': 'project', 'id': 'npm', 'enabled': False}]},
                   {'learnedRules': {'npm': 'revision'}}, {'invalidRules': ['invalid']},
                   {'reservedLegacyNames': ['npm']}, {'errors': ['unreadable']}):
        with pytest.raises(ValueError, match='ownership'):
            frozen_validation_context(prompt({**surface, **change}))


@pytest.mark.parametrize('failure', [KeyboardInterrupt, subprocess.TimeoutExpired])
def test_interrupted_child_retains_completed_cost_and_unknown_remainder(tmp_path, monkeypatch, failure) -> None:
    output = tmp_path / 'run'
    def prepare(_archive, directory):
        directory.mkdir()
        frozen = directory / 'frozen'; frozen.mkdir()
        file = frozen / 'repair.md'; file.write_text('retained complete original repair')
        return {'requestBudget': 10, 'timeoutSeconds': 1, 'sourceHashes': {},
                'frozenHashes': {'repair.md': hashlib.sha256(file.read_bytes()).hexdigest()}}
    class Proxy:
        selection = {'provider': 'fixture', 'model': 'fixed'}
        requests, errors = 2, 1
        key, token, jev_key = 'fixture-secret', 'fixture-token', None
        def __init__(self, *_args, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def write_agent_config(self, root):
            root.mkdir()
            (root / 'models.json').write_text(json.dumps({'providers': {'fixture': {'baseUrl': 'http://host.docker.internal:1'}}}))
    class Child:
        pid = 123456
        waits = 0
        def __init__(self, _command, **kwargs):
            message = {'type': 'message_end', 'message': {'role': 'assistant', 'usage': {'cost': {'total': 0.1}}}}
            kwargs['stdout'].write((json.dumps(message) + '\n').encode()); kwargs['stdout'].flush()
            kwargs['stderr'].write(b'fixture-secret'); kwargs['stderr'].flush()
        def wait(self, **_kwargs):
            self.waits += 1
            if self.waits == 1:
                if failure is KeyboardInterrupt: raise KeyboardInterrupt
                raise subprocess.TimeoutExpired('owned child', 1)
            return -15
        def poll(self): return None if self.waits == 1 else -15
    signals = []
    monkeypatch.setattr(diagnostic, 'prepare', prepare)
    monkeypatch.setattr(diagnostic, 'InferenceProxy', Proxy)
    monkeypatch.setattr(diagnostic, 'require_authorized_destination', lambda _proxy: None)
    monkeypatch.setattr(diagnostic.subprocess, 'check_output', lambda *_args, **_kwargs: '1.0.0\n')
    monkeypatch.setattr(diagnostic.subprocess, 'Popen', Child)
    monkeypatch.setattr(diagnostic.os, 'killpg', lambda pid, signal: signals.append(pid))
    report = diagnostic.run(tmp_path / 'archive', output, True)
    assert report['status'] == 'failed'
    assert report['knownReportedCostUsd'] == 0.1 and report['unknownCosts']
    assert report['requests'] == 2 and report['transportErrors'] == 1
    assert signals == [123456]
    assert (output / 'single-attempt.json').exists() and (output / 'output.jsonl').exists()
    assert not (output / 'agent/models.json').exists() and not (output / 'output.partial').exists()
    assert 'fixture-secret' not in (output / 'stderr.txt').read_text()


def test_observed_shell_correction_preserves_every_command_and_requires_exact_observation() -> None:
    original = {'operations': [{'op': 'addRule', 'rule': {'id': 'npm', 'action': 'block'},
        'cases': {'positive': [{'bash': 'npm\r', 'expected': 'block'}], 'negative': [{'bash': 'pnpm test'}]}}], 'evidence': []}
    repaired = deepcopy(original)
    repaired['operations'][0]['cases'] = {'positive': [], 'negative': [{'bash': 'npm\r'}, {'bash': 'pnpm test'}]}
    observations = {'cases': [{'command': 'npm\r', 'firstRecordedExecutable': None, 'returncode': 127}]}
    assert repair_continuity(original, repaired, observations)
    assert not repair_continuity(original, repaired)
    assert not repair_continuity(original, repaired, {'cases': []})
    assert not repair_continuity(original, original, observations)
    erased = deepcopy(repaired); erased['operations'][0]['cases']['negative'].pop(0)
    assert not repair_continuity(original, erased, observations)


def test_diagnostic_refuses_unapproved_destination_or_model() -> None:
    from types import SimpleNamespace
    from urllib.parse import urlsplit
    good = SimpleNamespace(selection={'model': 'bailian/qwen3.8-flash'}, upstream=urlsplit('http://10.10.0.195:8317/v1'))
    diagnostic.require_authorized_destination(good)
    for url, model in [('http://other:8317/v1', 'bailian/qwen3.8-flash'), ('http://10.10.0.195:8317/v1', 'other')]:
        with pytest.raises(ValueError, match='authorized'):
            diagnostic.require_authorized_destination(SimpleNamespace(selection={'model': model}, upstream=urlsplit(url)))
