"""Bounded read-only experiment over frozen paired requests."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any
import urllib.error
import urllib.request

from description_counter_decomposition import interpret
from run_description_counter_study import NoRedirect


def paired_metrics(samples: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    arms = ('original', 'structural')
    indexed = {(row['id'], row['arm']): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError('Duplicate attempt')
    complete = [sample for sample in samples if all(indexed.get((sample['id'], arm), {}).get('judgment') in ('compatible', 'conflict', 'uncertain') for arm in arms)]
    result: dict[str, Any] = {'completePairs': len(complete), 'incompletePairs': len(samples) - len(complete), 'writeAuthorized': False, 'completeGoalEvidence': False}
    for arm in arms:
        result[arm] = {'falseCompatible': sum(not s['expectedCompatible'] and indexed[(s['id'], arm)]['judgment'] == 'compatible' for s in complete),
                       'falseHolds': sum(s['expectedCompatible'] and indexed[(s['id'], arm)]['judgment'] != 'compatible' for s in complete)}
    result['lostOriginalValid'] = sum(s['expectedCompatible'] and indexed[(s['id'], 'original')]['judgment'] == 'compatible' and indexed[(s['id'], 'structural')]['judgment'] != 'compatible' for s in complete)
    result['meetsComponentCriterion'] = bool(complete) and result['incompletePairs'] == 0 and result['structural']['falseCompatible'] == 0 and result['lostOriginalValid'] == 0 and result['structural']['falseHolds'] < result['original']['falseHolds']
    return result


def run(root: Path, expected_hash: str, live: bool) -> None:
    manifest_path = root / 'manifest-v3.json'
    manifest = json.loads(manifest_path.read_text())

    def verify() -> None:
        if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError('Frozen manifest changed')
        for path, digest in manifest['sources'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
                raise ValueError('Frozen source changed')

    verify()
    samples = json.loads((root / 'paired-corpus.json').read_text())
    if len(samples) != 13 or len({s['id'] for s in samples}) != 13 or manifest['requestBudget'] != 26:
        raise ValueError('Frozen request budget changed')
    payloads = []
    for index, sample in enumerate(samples):
        if type(sample['expectedCompatible']) is not bool:
            raise ValueError('Invalid binary label')
        # Alternate paired order prospectively, without retrying either arm.
        for arm in (('original', 'structural') if index % 2 == 0 else ('structural', 'original')):
            payload = sample[arm]
            encoded = json.dumps(payload, ensure_ascii=False).encode()
            if payload['model'] != 'jev-1.13.0' or len(encoded) > 64000 or len(payload['questions']) > 32:
                raise ValueError('Frozen wire boundary exceeded')
            payloads.append((sample, arm, encoded))
    if not live:
        print(json.dumps({'preparedRequests': len(payloads), 'externalRequests': 0, 'writeAuthorized': False}))
        return
    if manifest.get('paidAllowed') is not True or not os.environ.get('TYPESAFE_API_KEY'):
        raise ValueError('Authorized inference credentials required')
    with (root / 'reservation').open('x') as file:
        file.write(expected_hash)
    opener = urllib.request.build_opener(NoRedirect())
    rows = []
    with (root / 'attempts.jsonl').open('x') as journal:
        for index, (sample, arm, encoded) in enumerate(payloads):
            verify()
            journal.write(json.dumps({'event': 'started', 'index': index, 'id': sample['id'], 'arm': arm, 'requestSha256': hashlib.sha256(encoded).hexdigest(), 'bytes': len(encoded)}) + '\n')
            journal.flush()
            row: dict[str, Any] = {'id': sample['id'], 'arm': arm, 'judgment': 'invalid', 'writeAuthorized': False}
            start = time.monotonic()
            try:
                request = urllib.request.Request('https://api.typesafe.ai/v1/systemone', data=encoded, headers={'Authorization': 'Bearer ' + os.environ['TYPESAFE_API_KEY'], 'Content-Type': 'application/json'})
                with opener.open(request, timeout=20) as response:
                    row['status'] = response.status
                    body = response.read(512001)
                if len(body) > 512000:
                    raise ValueError('Response size exceeded')
                raw = json.loads(body)
                safe = interpret(raw, sample['key'])
                row['judgment'] = safe['original']
                if 'originalDiagnostic' in safe:
                    row['diagnostic'] = safe['originalDiagnostic']
                row['modelVerified'] = isinstance(raw, dict) and raw.get('model') == 'jev-1.13.0'
                usage = raw.get('usage', {}) if isinstance(raw, dict) else {}
                if row['modelVerified'] and isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('input_tokens', 'output_tokens')):
                    row['usage'] = {k: usage[k] for k in ('input_tokens', 'output_tokens')}
            except Exception as error:
                row['judgment'] = 'invalid'
                row['errorType'] = type(error).__name__
                if isinstance(error, urllib.error.HTTPError):
                    row['status'] = error.code
                # Never retain service bodies, exception text, headers or raw evidence.
            row['durationMs'] = round((time.monotonic() - start) * 1000)
            rows.append(row)
            journal.write(json.dumps({'event': 'finished', 'index': index, **row}) + '\n')
            journal.flush()
            print(json.dumps({'index': index, 'id': row['id'], 'arm': arm, 'status': row.get('status'), 'judgment': row['judgment']}), flush=True)
    verify()
    report = {'evidence': 'real-Jev-structural-view-component-study', 'manifestSha256': expected_hash, 'metrics': paired_metrics(samples, rows), 'rows': rows, 'externalRequests': len(rows), 'usageResponses': sum('usage' in r for r in rows), 'knownInputTokens': sum(r.get('usage', {}).get('input_tokens', 0) for r in rows), 'knownOutputTokens': sum(r.get('usage', {}).get('output_tokens', 0) for r in rows), 'productionWrites': 0, 'adopted': False, 'billingVerified': False, 'blindHeldout': False, 'actualSDKLiveInference': False}
    report['knownEstimatedInputFeeUsd'] = report['knownInputTokens'] * 0.042 / 1000000
    with (root / 'result.json').open('x') as file:
        file.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--manifest-sha', required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--live', action='store_true')
    modes.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    run(args.root, args.manifest_sha, args.live)
