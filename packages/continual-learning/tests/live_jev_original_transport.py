"""One bounded same-host original-input matrix; explicit opt-in, never CI inference."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import select
import subprocess
import sys
import tempfile
import time
from typing import Any

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parents[2]
ARMS = ('direct-5s', 'proxy-15s', 'proxy-5s', 'direct-15s')
MANIFEST = TESTS / 'jev-original-transport-study-manifest.json'


def digest(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def require_paid_permission(value: object) -> None:
    if value is not True:
        raise PermissionError('Paid original transport prerequisites incomplete')


def require(value: object) -> None:
    if not value:
        raise ValueError('Frozen original transport prerequisite failed')


def group_gone(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


def run_owned_recorded(command: list[str], *, env: dict[str, str], timeout: int, prefix: Path, secrets: list[str], existing_child: subprocess.Popen[bytes] | None = None, input_data: bytes | None = None) -> dict[str, Any]:
    started = time.monotonic()
    child = existing_child or subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    outcome = 'completed'
    stdout, stderr = b'', b''
    try:
        stdout, stderr = child.communicate(input=input_data, timeout=timeout) if input_data is not None else child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        outcome = 'timeout'
        stdout, stderr = error.stdout or b'', error.stderr or b''
    finally:
        # A normally exited parent can still leave descendants in its owned group.
        if not group_gone(child.pid):
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                stdout, stderr = child.communicate(timeout=5)
            except subprocess.TimeoutExpired as error:
                stdout, stderr = error.stdout or stdout, error.stderr or stderr
            if not group_gone(child.pid):
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    stdout, stderr = child.communicate(timeout=5)
                except subprocess.TimeoutExpired as error:
                    stdout, stderr = error.stdout or stdout, error.stderr or stderr
    stopped = group_gone(child.pid)
    for suffix, data in [('stdout.txt', stdout), ('stderr.txt', stderr)]:
        for secret in secrets:
            if secret:
                data = data.replace(secret.encode(), b'[redacted]')
        target = prefix.with_name(prefix.name + '-' + suffix)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as file:
            file.write(data)
    return {'exitCode': child.returncode, 'outcome': outcome, 'seconds': round(time.monotonic() - started, 3), 'processGroupStopConfirmed': stopped}


def verify(m: dict[str, Any], manifest_sha256: str) -> None:
    require(digest(MANIFEST) == manifest_sha256)
    require(m['requestBudget'] == 12 and m['arms'] == list(ARMS))
    require(all(digest(TESTS / name) == value for name, value in m['codeHashes'].items()))
    require(digest(TESTS / m['profile']) == m['profileSha256'])
    require(digest(TESTS / m['originalPreparation']) == m['originalPreparationSha256'])
    require(digest(TESTS / m['terminalPrerequisite']['report']) == m['terminalPrerequisite']['sha256'])
    require(digest(TESTS / m['gatePrerequisite']['report']) == m['gatePrerequisite']['sha256'])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    require(args.live != args.preflight_only)
    manifest_bytes = MANIFEST.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    m: dict[str, Any] = json.loads(manifest_bytes)
    key = os.environ.get('TYPESAFE_API_KEY', '').strip()
    if args.live:
        require_paid_permission(m['paidExecutionAllowedNow'] is True and bool(key))
    verify(m, manifest_sha256)
    if args.live:
        require(digest(TESTS / 'jev-original-transport-preflight.json') == m['preflightSha256'])
        require(digest(TESTS / 'jev-original-transport-local-verification.json') == m['localVerificationSha256'])
    mode = 'real-results' if args.live else 'preflight'
    output = TESTS / ('jev-original-transport-' + mode + '.json')
    with output.with_suffix(output.suffix + '.reservation').open('x') as file:
        json.dump({'manifestSha256': digest(MANIFEST), 'requestBudget': 12, 'arms': ARMS}, file)
    cache = Path(m['wireDirectory']).parent / ('transport-' + mode)
    cache.mkdir(mode=0o700)
    rows: list[dict[str, Any]] = []
    # Each proxy owns a separate process. Exiting it closes all owned upstream
    # sockets, even when the original transparent handler is blocked for 300s.
    try:
        for arm in ARMS:
            verify(m, manifest_sha256)
            worker: subprocess.Popen[bytes] | None = None
            token = ''
            row: dict[str, Any] = {'arm': arm}
            with tempfile.TemporaryDirectory(prefix='cl-original-transport-settings-') as settings:
                env = {**os.environ, 'PI_CODING_AGENT_DIR': settings}
                env.pop('TYPESAFE_BASE_URL', None)
                prefix = cache / arm
                proxy_url = 'http://127.0.0.1:1/jev'
                try:
                    if arm.startswith('proxy-'):
                        config_root = Path(os.environ.get('PI_CODING_AGENT_DIR', Path.home() / '.pi/agent'))
                        worker = subprocess.Popen([sys.executable, str(TESTS / 'jev_original_transport_proxy.py'), '--live' if args.live else '--preflight-only', str(prefix), str(config_root)], env={**os.environ, 'TYPESAFE_API_KEY': key if args.live else 'fixture-only'}, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
                        require(worker.stdout is not None)
                        ready = select.select([worker.stdout], [], [], 10)[0]
                        require(ready and worker.stdout.readline().strip() == b'{"stage": "ready"}')
                        secret = json.loads(prefix.with_name(prefix.name + '-proxy-ready.json').read_text())
                        require(secret['pid'] == worker.pid)
                        token = secret['token']
                        proxy_url = 'http://127.0.0.1:' + str(secret['port']) + '/jev'
                    if args.live:
                        env['TYPESAFE_API_KEY'] = token if arm.startswith('proxy-') else key
                    else:
                        env.pop('TYPESAFE_API_KEY', None)
                    inputs = {'arm': arm, 'outputPrefix': str(prefix), 'proxyURL': proxy_url, 'expectedManifestSha256': manifest_sha256}
                    path = cache / (arm + '-input.json')
                    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(descriptor, 'w') as file:
                        json.dump(inputs, file)
                    print(json.dumps({'stage': 'original-transport-arm', 'arm': arm, 'live': args.live}), flush=True)
                    row['process'] = run_owned_recorded(['pnpm', 'exec', 'tsx', str(TESTS / 'evaluate_jev_original_transport.ts'), '--live' if args.live else '--preflight-only', str(path)], env=env, timeout=60, prefix=prefix, secrets=[key, token])
                    result = prefix.with_name(prefix.name + '-result.json')
                    if result.exists():
                        row['result'] = json.loads(result.read_text())
                finally:
                    if worker is not None:
                        row['proxyProcess'] = run_owned_recorded([], env={}, timeout=10, prefix=prefix.with_name(prefix.name + '-proxy-worker'), secrets=[key, token], existing_child=worker, input_data=b'stop\n')
                        snapshot = prefix.with_name(prefix.name + '-proxy-final.json')
                        if snapshot.exists():
                            row['proxySnapshot'] = json.loads(snapshot.read_text())
                        row['ownedProxyUpstreamsClosedConfirmed'] = row['proxyProcess']['processGroupStopConfirmed']
                        row['remoteProviderWorkStoppedVerified'] = False
                    journal = prefix.with_name(prefix.name + '-attempts.jsonl')
                    row['attemptJournalSha256'] = digest(journal) if journal.exists() else None
                    rows.append(row)
                    output.with_suffix(output.suffix + '.checkpoint').write_text(json.dumps({'rows': rows}, indent=2) + '\n')
                require(row['process']['processGroupStopConfirmed'])
                require(worker is None or row['ownedProxyUpstreamsClosedConfirmed'])
                if row['process']['outcome'] == 'timeout':
                    break
        verify(m, manifest_sha256)
        all_evaluated = len(rows) == 4 and all(r['process']['exitCode'] == 0 and r.get('result', {}).get('identicalWireRequests') is True for r in rows)
        results = [r['result'] for r in rows if 'result' in r]
        known_input = sum(r['knownInputTokens'] for r in results)
        observed_requests = sum(r['externalRequests'] for r in results)
        report = {'evidence': 'real-same-host-original-large-deadline-transport-matrix' if args.live else 'offline-original-large-deadline-transport-matrix', 'manifestSha256': digest(MANIFEST), 'rows': rows, 'allArmsEvaluated': all_evaluated, 'externalRequestsInReturnedArms': observed_requests, 'fixtureRequests': sum(r['fixtureRequests'] for r in results), 'preSendFixtureRequests': sum(r['preSendFixtureRequests'] for r in results), 'proxyRequests': sum(r.get('proxySnapshot', {}).get('jevRequests', 0) for r in rows), 'requestBudget': 12, 'knownInputTokens': known_input, 'knownEstimatedCostUsd': known_input * .042 / 1_000_000, 'missingUsageRequestsInReturnedArms': sum(r['missingUsageRequests'] for r in results), 'accountBillingVerified': False, 'productionWrites': 0, 'adopted': False, 'semanticGoldEstablished': False, 'goalComplete': False, 'limits': ['One known candidate, one result per fixed arm; no heldout/full-workflow superiority.', 'Same-host runtime and SDK; does not isolate Docker VM networking.', 'Exact current profile identity, not literal historical wire identity.', 'Incomplete/missing/late responses and unreturned arm costs are unknown, not free.', 'Proxy usage and client usage overlap and must not be added together.', 'Owned proxy process exit closes local upstream sockets; remote provider work/cancellation is unverified.', 'No retries, threshold relaxation, automatic adoption or apply.']}
    finally:
        (cache / 'execution-final-state.json').write_text(json.dumps({'rows': rows, 'accountBillingVerified': False, 'productionWrites': 0}, indent=2) + '\n')
    with output.open('x') as file:
        json.dump(report, file, indent=2)
        file.write('\n')
    print(json.dumps({'stage': 'finished', 'live': args.live, 'arms': len(rows), 'allArmsEvaluated': all_evaluated, 'externalRequestsInReturnedArms': observed_requests}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'stage': 'failed', 'category': type(error).__name__}), flush=True)
        raise SystemExit(1)
