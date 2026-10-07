"""Explicit bounded real-Jev component study; no application or production writes."""
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

from description_counter_decomposition import paired_request, interpret


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(root: Path, expected_hash: str, live: bool) -> None:
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    def verify() -> None:
        if sha(manifest_path) != expected_hash:
            raise ValueError('Frozen manifest changed')
        for path, digest in manifest['hashes'].items():
            if sha(Path(path)) != digest:
                raise ValueError('Frozen study file changed')
    verify()
    samples = json.loads((root / 'corpus.json').read_text())
    if len(samples) != 13 or manifest['requestBudget'] != 13 or len({s['id'] for s in samples}) != 13:
        raise ValueError('Frozen sample or request count changed')
    requests = [paired_request(s['request'], s['key']) for s in samples]
    if not live:
        print(json.dumps({'samples': len(samples), 'requestsPrepared': len(requests), 'externalRequests': 0, 'productionWrites': 0}))
        return
    if manifest['paidAllowed'] is not True or not os.environ.get('TYPESAFE_API_KEY'):
        raise ValueError('Authorized live credentials required')
    # An exclusive claim prevents favorable retries after an unknown outcome.
    with (root / 'reservation').open('x') as file:
        file.write(expected_hash)
    opener = urllib.request.build_opener(NoRedirect())
    rows = []
    with (root / 'attempts.jsonl').open('x') as journal:
        for index, (sample, payload) in enumerate(zip(samples, requests, strict=True)):
            verify()
            encoded = json.dumps(payload, ensure_ascii=False).encode()
            journal.write(json.dumps({'event': 'started', 'index': index, 'requestSha256': hashlib.sha256(encoded).hexdigest(), 'bytes': len(encoded)}) + '\n')
            journal.flush()
            started = time.monotonic()
            row: dict[str, Any] = {'id': sample['id'], 'expectedCompatible': sample['expectedCompatible'], 'status': None}
            try:
                request = urllib.request.Request('https://api.typesafe.ai/v1/systemone', data=encoded, headers={'Authorization': 'Bearer ' + os.environ['TYPESAFE_API_KEY'], 'Content-Type': 'application/json'})
                with opener.open(request, timeout=20) as response:
                    row['status'] = response.status
                    body = response.read(512001)
                if len(body) > 512000:
                    raise ValueError('Response size exceeded')
                raw = json.loads(body)
                row.update(interpret(raw, sample['key']))
                row['modelVerified'] = raw.get('model') == 'jev-1.13.0'
                usage = raw.get('usage', {})
                if row['modelVerified'] and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('input_tokens', 'output_tokens')):
                    row['usage'] = {k: usage[k] for k in ('input_tokens', 'output_tokens')}
            except Exception as error:
                row.update(original='invalid', decomposed='invalid', writeAuthorized=False, errorType=type(error).__name__)
                if isinstance(error, urllib.error.HTTPError):
                    row['status'] = error.code
                # No response bodies, URLs, headers or exception text are logged.
            row['durationMs'] = round((time.monotonic() - started) * 1000)
            rows.append(row)
            journal.write(json.dumps({'event': 'finished', 'index': index, **row}) + '\n')
            journal.flush()
            print(json.dumps({'index': index, 'id': row['id'], 'status': row['status'], 'original': row['original'], 'decomposed': row['decomposed']}), flush=True)
    verify()
    complete = [r for r in rows if r['original'] != 'invalid' and r['decomposed'] != 'invalid']
    metrics = {arm: {'complete': len(complete), 'incomplete': len(rows) - len(complete), 'falseCompatible': sum(not r['expectedCompatible'] and r[arm] == 'compatible' for r in complete), 'falseHolds': sum(r['expectedCompatible'] and r[arm] != 'compatible' for r in complete)} for arm in ('original', 'decomposed')}
    report = {'evidence': 'real-Jev-description-counter-component-study', 'manifestSha256': expected_hash, 'actualModel': 'jev-1.13.0' if all(r.get('modelVerified') for r in rows) else None, 'metrics': metrics, 'rows': rows, 'externalRequests': len(rows), 'usageResponses': sum('usage' in r for r in rows), 'knownInputTokens': sum(r.get('usage', {}).get('input_tokens', 0) for r in rows), 'productionWrites': 0, 'writeAuthorized': False, 'adopted': False, 'billingVerified': False, 'completeGoalEvidence': False}
    report['knownEstimatedCostUsd'] = report['knownInputTokens'] * 0.042 / 1000000
    report['limitations'] = ['Component judgment only: not a full learning decision or real Memory application.', 'Authored bilingual development cases and one reused real failure are not blind heldout evidence.', 'Questions share a state but are independent; no per-arm latency/cost isolation.', 'Uncertainty is retained as a hold and failed/missing responses are incomplete, never successes.', 'A positive component result would still require full-path validation with unchanged parent permissions.']
    (root / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'metrics': metrics, 'externalRequests': len(rows), 'knownInputTokens': report['knownInputTokens'], 'knownEstimatedCostUsd': report['knownEstimatedCostUsd']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--manifest-sha', required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--live', action='store_true')
    modes.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    run(args.root, args.manifest_sha, args.live)
