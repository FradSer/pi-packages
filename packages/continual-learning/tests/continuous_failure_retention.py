"""Retain owned study-container evidence without requiring a running process."""
from pathlib import Path, PurePosixPath
from typing import Callable, Any
import hashlib
import io
import json
import os
import tarfile


def retain_failure_container(
    container: str,
    target: Path,
    process: Callable[..., Any],
    redact: Callable[[bytes], bytes],
) -> dict:
    target.mkdir(parents=True, exist_ok=True)
    report: dict = {'passed': False, 'container': container, 'surfaces': {}, 'containerRemoved': False}
    roots = {'learning': '/home/node/agent/learning', 'memory': '/home/node/agent/memory',
             'sessions': '/home/node/agent/sessions', 'project': '/work/p-limit'}
    for name, source in roots.items():
        state: dict = {'saved': False}
        report['surfaces'][name] = state
        try:
            # docker cp works after docker stop; docker exec does not. Never
            # classify a failed copy as an absent directory from stderr text.
            result = process(['docker', 'cp', container + ':' + source, '-'])
            if result.returncode:
                state.update(error='copy-failed', exitCode=result.returncode)
                continue
            root = PurePosixPath(source).name
            files: dict = {}
            root_seen = False
            with tarfile.open(fileobj=io.BytesIO(result.stdout), mode='r:*') as archive:
                for member in archive:
                    path = PurePosixPath(member.name)
                    if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != root:
                        raise ValueError('Unexpected archive path')
                    relative = path.parts[1:]
                    if name == 'project' and relative and relative[0] in ('node_modules', '.git'):
                        continue
                    if not relative:
                        if not member.isdir():
                            raise ValueError('Missing archive directory')
                        root_seen = True
                    destination = target / name / Path(*relative)
                    if member.isdir():
                        destination.mkdir(parents=True, exist_ok=True)
                    elif member.isfile():
                        if not relative or member.size > 16 * 1024 * 1024:
                            raise ValueError('Invalid evidence file')
                        stream = archive.extractfile(member)
                        if stream is None:
                            raise ValueError('Missing evidence bytes')
                        data = redact(stream.read())
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with destination.open('xb') as output:
                            output.write(data)
                            output.flush()
                            os.fsync(output.fileno())
                        destination.chmod(member.mode & 0o777)
                        digest = hashlib.sha256(data).hexdigest()
                        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest or destination.stat().st_mode & 0o777 != member.mode & 0o777:
                            raise ValueError('Retained bytes differ')
                        files['/'.join(relative)] = {'sha256': digest, 'mode': member.mode & 0o777}
                    else:
                        raise ValueError('Unsupported evidence file')
            if not root_seen:
                raise ValueError('Archive root was not retained')
            if name == 'project' and 'index.js' not in files:
                raise ValueError('Project source missing')
            state.update(saved=True, files=files, transportRedactionApplied=True)
        except Exception as error:
            # Exception text and child stderr may contain private evidence.
            state.update(error='retention-failed', errorType=type(error).__name__)
    report['passed'] = all(state['saved'] for state in report['surfaces'].values())
    def write_report() -> None:
        with (target / 'retention.json').open('w') as stream:
            stream.write(json.dumps(report, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    write_report()
    if report['passed']:
        try:
            # Persist directory entries too before dropping the original copy.
            for parent, _, _ in os.walk(target, topdown=False):
                descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            removed = process(['docker', 'rm', '-f', container])
            report['containerRemoved'] = removed.returncode == 0
        except Exception:
            report['containerRemoved'] = False
        if not report['containerRemoved']:
            report['passed'] = False
            report['cleanupError'] = 'container-removal-failed'
    write_report()
    return report


def valid_learning_usage(value: Any) -> bool:
    import math
    return isinstance(value, dict) and all(
        isinstance(value.get(key), (int, float)) and not isinstance(value[key], bool)
        and math.isfinite(value[key]) and value[key] >= 0
        for key in ('input', 'output', 'cacheRead', 'cacheWrite', 'totalTokens', 'cost'))


def unique_learning_receipts(values: list[dict]) -> dict[str, dict]:
    """Reconcile parent snapshots by batch identity, never by numeric totals.

    Different snapshots of one batch are unresolved evidence. Do not choose a
    larger or later snapshot without a proved lifecycle ordering.
    """
    receipts = {}
    for value in values:
        if not isinstance(value, dict) or value.get('kind') != 'learning-pipeline-receipt':
            raise ValueError('Invalid parent receipt')
        identity = value.get('batchId')
        if not isinstance(identity, str) or not identity or not valid_learning_usage(value.get('totals')):
            raise ValueError('Invalid retained receipt')
        if identity in receipts and receipts[identity] != value:
            raise ValueError('Conflicting retained receipt identity')
        receipts[identity] = value
    return receipts


def validate_receipt_usage_totals(receipt: dict) -> None:
    usage_rows = [a['usage'] for a in receipt.get('attempts', []) if a.get('usage') is not None]
    if any(not valid_learning_usage(row) for row in usage_rows):
        raise ValueError('Invalid receipt attempt usage')
    # Match totalLearningUsage's ordered JavaScript Number additions exactly.
    # Python's compensated sum can differ by one ULP from a genuine receipt.
    # Keep exact equality below; do not admit altered totals with a tolerance.
    expected = {key: 0.0 for key in receipt['totals']}
    for row in usage_rows:
        for key in expected:
            expected[key] += float(row[key])
    if expected != receipt['totals']:
        raise ValueError('Receipt totals do not match known attempt usage')


def learning_cost_summary(receipt_values: list[dict], attempts: list[dict], workers: list[dict]) -> dict:
    """Count all owned pipelines, including early corrections outside replay."""
    receipts = unique_learning_receipts(receipt_values + [a['receipt'] for a in attempts if a.get('receipt')])
    included = {}
    for batch, receipt in receipts.items():
        validate_receipt_usage_totals(receipt)
        for attempt in receipt.get('attempts', []):
            identity = attempt.get('usageLedgerId')
            if not identity or not valid_learning_usage(attempt.get('usage')):
                continue
            if identity in included:
                raise ValueError('Conflicting or duplicate receipt worker usage identity')
            included[identity] = attempt['usage']
    ledgers = {}
    for row in workers:
        identity = row.get('ledgerId')
        if not isinstance(identity, str) or not identity or not valid_learning_usage(row.get('knownUsage')):
            raise ValueError('Invalid worker usage ledger')
        previous = ledgers.get(identity)
        if previous and (previous['knownUsage'] != row['knownUsage'] or previous.get('complete') != row.get('complete')):
            raise ValueError('Conflicting worker usage ledger identity')
        ledgers[identity] = row
        if identity in included and included[identity] != row['knownUsage']:
            raise ValueError('Conflicting receipt and worker usage')
    additional = [row for identity, row in ledgers.items() if identity not in included]
    known = [receipt['totals'] for receipt in receipts.values()] + [row['knownUsage'] for row in additional]
    unknown = (sum(not a.get('receipt') for a in attempts)
               + sum(r.get('usageAvailable') is not True for r in receipts.values()))
    return {
        'knownLearningTokens': sum(row['totalTokens'] for row in known),
        'knownLearningCost': sum(row['cost'] for row in known),
        'partialWorkerUsageLedgers': additional,
        'interruptedUnknownUsage': unknown,
        'unknownWorkerUsageLedgers': sum(row.get('complete') is not True for row in additional),
        'actualLearningOperations': sum(r.get('operations', 0) for r in receipts.values()),
        # Count failed phase attempts once per parent batch, plus failed jobs
        # without receipts. Replay final-state failures remain a separate unit.
        'learningFailedAttempts': sum(not a.get('receipt') and a.get('outcome') != 'completed' for a in attempts)
            + sum(a.get('outcome') in ('failed', 'rejected', 'cancelled')
                  for r in receipts.values() for a in r.get('attempts', [])),
        'learningFailedReplayAttempts': sum(a.get('outcome') != 'completed' for a in attempts),
        'allLearningCostsPriced': not additional and unknown == 0
            and all(row.get('complete') is True for row in ledgers.values())
            and all(r.get('costAvailable') is True for r in receipts.values()),
    }


def retained_learning_costs(target: Path) -> dict:
    """Recover a known lower bound from retained parent-owned evidence.

    Interrupted calls remain unknown. Receipt copies are keyed by batch, workers
    by ledger identity; numeric equality alone never establishes call identity.
    """
    valid_usage = valid_learning_usage

    receipts: dict = {}
    workers: dict = {}
    legacy: list = []
    errors: list = []

    def collect(value: Any) -> None:
        receipts.update(unique_learning_receipts([*receipts.values(), value]))

    paths = [*target.glob('memory/runs/*/*/*.json'), *target.glob('learning/*/replay-*.json')]
    for path in sorted(paths):
        relative = path.relative_to(target)
        name = path.name
        replay = relative.parts[0] == 'learning'
        receipt = name == 'learning-pipeline-receipt.json'
        worker = name.startswith(('memory-task-usage', 'memory-repair-usage', 'memory-body-usage',
                                  'harness-task-usage', 'harness-repair-usage')) or name == 'source-audit-usage.json'
        if not (replay or receipt or worker):
            continue
        if target.is_symlink() or any((target / Path(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts) + 1)):
            raise ValueError('Symlink in retained cost evidence')
        try:
            value = json.loads(path.read_text())
        except (ValueError, UnicodeError):
            errors.append(str(path.relative_to(target)))
            continue
        if receipt:
            collect(value)
        if replay:
            if not isinstance(value, dict) or not isinstance(value.get('attempts'), list):
                raise ValueError('Invalid parent replay ledger')
            for attempt in value['attempts']:
                if isinstance(attempt, dict) and attempt.get('receipt'):
                    collect(attempt['receipt'])
        if not isinstance(value, dict) or not valid_usage(value.get('knownUsage')):
            continue
        name = path.name
        if not (name.startswith(('memory-task-usage', 'memory-repair-usage', 'memory-body-usage',
                                 'harness-task-usage', 'harness-repair-usage')) or name == 'source-audit-usage.json'):
            continue
        row = {'path': str(path.relative_to(target)), **value}
        identity = value.get('ledgerId')
        if not isinstance(identity, str) or not identity:
            if name == 'source-audit-usage.json':
                legacy.append(row)
            else:
                errors.append(row['path'])
            continue
        if identity in workers and (workers[identity]['knownUsage'] != value['knownUsage']
                                    or workers[identity].get('complete') != value.get('complete')):
            raise ValueError('Conflicting worker usage ledger identity')
        workers[identity] = row

    included: dict = {}
    unkeyed_receipt_usage = False
    for batch, receipt in receipts.items():
        for attempt in receipt.get('attempts', []):
            if not valid_usage(attempt.get('usage')):
                continue
            identity = attempt.get('usageLedgerId')
            if not identity:
                unkeyed_receipt_usage = True
                continue
            if identity in included:
                raise ValueError('Conflicting or duplicate receipt worker usage identity')
            included[identity] = {'batch': batch, 'usage': attempt['usage']}
    for receipt in receipts.values():
        validate_receipt_usage_totals(receipt)
    additional = []
    for identity, row in workers.items():
        if identity in included:
            if included[identity]['usage'] != row['knownUsage']:
                raise ValueError('Conflicting receipt and worker usage')
        else:
            additional.append(row)
    # Historical collectors lacked IDs. Only absent unkeyed receipt usage
    # rules out receipt inclusion; otherwise retain an unresolved lower bound.
    unresolved = [row['path'] for row in legacy] if unkeyed_receipt_usage else []
    if not unkeyed_receipt_usage:
        additional.extend(legacy)
    known = [r['totals'] for r in receipts.values()] + [r['knownUsage'] for r in additional]
    return {'knownLearningCost': sum(row['cost'] for row in known),
            'knownLearningTokens': sum(row['totalTokens'] for row in known),
            'receiptBatches': sorted(receipts), 'additionalWorkerLedgers': additional,
            'unresolvedLegacySourceAudits': unresolved, 'parseErrors': errors,
            'unknownCosts': True, 'allLearningCostsPriced': False,
            'basis': 'retained-interrupted-evidence; known lower bound, not completion'}
