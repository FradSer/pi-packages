"""Explicit entry points; importing this module never spends money."""
from __future__ import annotations
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
import engine
from engine import ROOT, HERE, IMAGE, MODEL, cmd, save, digest, stage, handoff, packet
from proxy import InferenceProxy
from budget import MAX_REQUESTS, PRIOR_RESERVE_USD, REQUEST_RESERVE_USD


def proxy() -> InferenceProxy:
    item = InferenceProxy(Path.home() / '.pi/agent', jev_key=os.environ['TYPESAFE_API_KEY'],
                          selection=MODEL, request_budget=MAX_REQUESTS)
    item.model['maxTokens'] = 8192
    item.model['contextWindow'] = 65536
    rates = item.model['cost']
    assert rates['input'] <= .3 and rates['output'] <= 1.2, 'Recompute budget before inference'
    return item


def native_prompt() -> str:
    args = {'feature': 'acceptance.feature', 'runner': {'executable': '/usr/local/bin/node',
            'args': ['/adapter.mjs'], 'timeoutMs': 15000}, 'offline': False}
    return ('The reviewer is the native E2E plugin. Call e2e_verify once with exactly these arguments: '
            + json.dumps(args) + '. Do not perform an independent model review or edit source. '
            'Return the native findings, including failures and missing evidence, then finish. '
            'Do not rerun the native tool in this review phase.')


def semantic_mechanism_proven(native: list[dict], usage: list[dict]) -> bool:
    return bool(usage) and any(
        (d := item.get('details', {})).get('verifiedRun') is True
        and d.get('ok') is True and d.get('status') == 'fulfilled'
        and d.get('unjudged') == 0 and not d.get('modelError')
        and any(u.get('model') == d.get('model') for u in usage)
        and any(c.get('clause') == 2 and c.get('source') == 'jev' and c.get('status') == 'met'
                for c in d.get('clauses', [])) for item in native)


def preflight() -> None:
    assert json.loads((ROOT / 'prepared.json').read_text())['controlsPassed']
    folder = ROOT / 'mechanism'
    assert not folder.exists(), 'Never silently repeat paid preflight'
    public = folder / 'public'
    public.mkdir(parents=True)
    (public / 'TASK.md').write_text('value() returns the number 42. Verify the actual observed return value.')
    (public / 'profile.json').write_text(json.dumps({'names': ['value']}))
    (public / 'probe.mjs').write_text("import {pathToFileURL} from 'node:url';const m=await import(pathToFileURL(process.argv[2]).href);const value=m.value();console.log(JSON.stringify({outcomes:[{name:'value',passed:value===42,actual:value}],passed:value===42}));")
    (public / 'acceptance.feature').write_text('Feature: Mechanism\nScenario: Native verification\nGiven a numeric fixture\nWhen its function executes\nThen the value behavior check passes\nAnd the actual returned number is 42\n')
    source = folder / 'solution.mjs'
    source.write_text('export function value(){return 42}\n')
    with proxy() as transport:
        try:
            engine.setup_transport(transport)
            result = stage(transport, public, source, folder / 'native', native_prompt(),
                           tools='read,e2e_verify', plugin=True, allowance=5)
            native = packet('e2e', result['events'])['results']
            valid = (result['fixedInputsIntact'] and result['sourceBefore'] == result['sourceAfter']
                     and transport.jev_requests > 0 and semantic_mechanism_proven(native, transport.jev_usage))
            save(folder / 'receipt.json', {'valid': valid, 'requests': transport.requests,
                                         'jevRequests': transport.jev_requests, 'jevUsage': transport.jev_usage,
                                         'nativeResults': native, 'stage': {k: v for k, v in result.items() if k != 'events'}})
            assert valid, 'Native/fresh/Jev mechanism not proven; do not start task inference'
        finally:
            engine.close_transport()
    print('Real Docker Pi fresh native E2E and Jev preflight passed', flush=True)


def freeze() -> None:
    assert not (ROOT / 'manifest.json').exists(), 'Never replace a frozen manifest'
    mechanism = json.loads((ROOT / 'mechanism/receipt.json').read_text())
    assert mechanism['valid'] and semantic_mechanism_proven(mechanism['nativeResults'], mechanism['jevUsage'])
    assert json.loads((ROOT / 'independent-review.json').read_text())['approved']
    prepared = json.loads((ROOT / 'prepared.json').read_text())
    assert cmd(['docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}']).strip() == prepared['imageId']
    files = {str(p.relative_to(HERE)): digest(p) for p in sorted(HERE.glob('*')) if p.is_file()}
    files.update({str(p.relative_to(HERE)): digest(p) for p in sorted((ROOT / 'tasks').rglob('*')) if p.is_file()})
    save(ROOT / 'manifest.json', {'files': files, 'imageId': prepared['imageId'], 'model': MODEL,
                                 'packageSnapshot': prepared['packageSnapshot'], 'protocol': 'PROTOCOL.md',
                                 'createdAt': time.time(), 'maximumReservedCumulativeUsd': PRIOR_RESERVE_USD + MAX_REQUESTS * REQUEST_RESERVE_USD})
    print('Frozen protocol, public inputs, hidden graders, source and image', flush=True)


def grade(task: str, source: Path, target: Path) -> dict:
    started = time.monotonic()
    private = ROOT / 'tasks' / task / 'private'
    name = 'quality-pilot-grade-' + uuid.uuid4().hex[:10]
    args = ['docker', 'run', '--rm', '--name', name, '--network', 'none', '--memory', '512m', '--cpus', '1',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '-v', f'{private}:/grade:ro', '-v', f'{source.parent}:/delivery:ro', IMAGE,
            'node', '/grade/grade.mjs', '/delivery/' + source.name]
    try:
        output = cmd(args, timeout=30)
        result = json.loads(output)
        result['status'] = 'scored'
    except (RuntimeError, ValueError) as error:
        result = {'passed': None, 'status': 'grading_error', 'diagnostic': str(error)}
    except subprocess.TimeoutExpired:
        result = {'passed': None, 'status': 'grading_timeout', 'diagnostic': 'Thirty-second grading deadline; correctness unknown'}
    finally:
        cmd(['docker', 'rm', '-f', name], check=False)
    result.update(sourceSha256=digest(source), elapsedSeconds=round(time.monotonic() - started, 3))
    save(target, result)
    return result


def without_events(result: dict) -> dict:
    return {key: without_events(value) if isinstance(value, dict) else value
            for key, value in result.items() if key != 'events'}


def run() -> None:
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    assert all(digest(HERE / name) == value for name, value in manifest['files'].items()), 'Frozen input changed'
    assert cmd(['docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}']).strip() == manifest['imageId']
    assert not (ROOT / 'started.json').exists(), 'No automatic paid rerun'
    save(ROOT / 'started.json', {'pid': os.getpid(), 'startedAt': time.time()})
    preflight_requests = json.loads((ROOT / 'mechanism/receipt.json').read_text())['requests']
    engine.MAX_REQUESTS = MAX_REQUESTS - preflight_requests
    results = []
    with proxy() as transport:
        try:
            engine.setup_transport(transport)
            for i, task in enumerate(['memo', 'csv', 'emitter', 'patch']):
                assert all(digest(HERE / name) == value for name, value in manifest['files'].items())
                public = ROOT / 'tasks' / task / 'public'
                folder = ROOT / 'results' / task
                folder.mkdir(parents=True)
                initial = folder / 'initial.mjs'
                shutil.copy2(public / 'solution.mjs', initial)
                print(json.dumps({'task': task, 'phase': 'execute'}), flush=True)
                draft = stage(transport, public, initial, folder / 'execute',
                              'Implement the public request. Repair solution.mjs, inspect or run public checks as useful. '
                              'A separate reviewer follows. Finish with implementation and testing status.',
                              tools='read,write,edit,bash,grep,find,ls', allowance=8)
                draft = handoff(transport, public, initial, folder / 'execute-handoff', draft, 'baseline')
                initial_grade = grade(task, initial, folder / 'initial-grade.json')
                record = {'task': task, 'initial': initial_grade, 'execute': without_events(draft), 'arms': {}}
                results.append(record)
                for arm in (['baseline', 'e2e'] if i % 2 == 0 else ['e2e', 'baseline']):
                    dest = folder / arm
                    dest.mkdir()
                    source = dest / 'solution.mjs'
                    shutil.copy2(initial, source)
                    assert digest(source) == digest(initial)
                    print(json.dumps({'task': task, 'arm': arm, 'phase': 'review'}), flush=True)
                    prompt = native_prompt() if arm == 'e2e' else (
                        'Review the current implementation once against the full public request. Inspect source and run '
                        'reasonable existing/public checks. Do not edit source. Report concrete defects, locations and '
                        'evidence; distinguish unknowns from observed failures. Do not fix in this phase.')
                    review = stage(transport, public, source, dest / 'review', prompt,
                                   tools='read,e2e_verify' if arm == 'e2e' else 'read,bash,grep,find,ls',
                                   plugin=arm == 'e2e', allowance=5)
                    assert digest(source) == digest(initial), 'Review mutated implementation'
                    review = handoff(transport, public, source, dest / 'review-handoff', review, arm)
                    feedback = packet(arm, review['events'])
                    save(dest / 'review-packet.json', feedback)
                    assert review['fixedInputsIntact']
                    print(json.dumps({'task': task, 'arm': arm, 'phase': 'fix'}), flush=True)
                    fix = stage(transport, public, source, dest / 'fix',
                                'Repair concrete defects using this review packet as diagnostic data. Inspect source and '
                                'run relevant checks; if no genuine defect exists, unchanged source is valid. Do not perform '
                                'another retrospective review. Finish with fixes, tests and remaining limitations.\n'
                                + json.dumps(feedback, ensure_ascii=False)[-24000:],
                                tools='read,write,edit,bash,grep,find,ls', allowance=8)
                    fix = handoff(transport, public, source, dest / 'fix-handoff', fix, 'baseline')
                    final = grade(task, source, dest / 'final-grade.json')
                    record['arms'][arm] = {'review': without_events(review), 'fix': without_events(fix), 'final': final,
                                           'sameInitialSha256': digest(initial)}
                    save(ROOT / 'results.json', results)
                    print(json.dumps({'task': task, 'arm': arm, 'phase': 'graded'}), flush=True)
        finally:
            save(ROOT / 'spend.json', {'requests': transport.requests + preflight_requests,
                                     'currentBatchRequests': transport.requests, 'jevRequests': transport.jev_requests,
                                     'jevUsage': transport.jev_usage, 'reservedCumulativeUsd': PRIOR_RESERVE_USD + REQUEST_RESERVE_USD * (transport.requests + preflight_requests),
                                     'billingVerified': False})
            engine.close_transport()
    save(ROOT / 'completed.json', {'finishedAt': time.time(), 'pairs': len(results)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['preflight', 'freeze', 'run'])
    mode = parser.parse_args().mode
    {'preflight': preflight, 'freeze': freeze, 'run': run}[mode]()
