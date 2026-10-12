"""Parent-owned study recovery safeguards; never authorize a learned mutation."""
from __future__ import annotations
import base64
import hashlib
import json
import os
import tarfile
from collections import Counter
from pathlib import Path


def archive_surface_snapshots(memory: Path, project: Path, live_metadata: dict) -> dict:
    """Retained bytes must equal raw live hashes; redaction cannot hide drift."""
    snapshots = {}
    for file in (memory, project):
        with tarfile.open(file) as archive:
            for item in archive:
                name = Path(item.name)
                if name.is_absolute() or '..' in name.parts:
                    raise ValueError('Unsafe retained archive path')
                parts = name.parts
                if file == memory:
                    if not parts or parts[0] != '--work-p-limit--':
                        continue
                    key = 'private/' + '/'.join(parts[1:])
                else:
                    if not parts or not (parts[0] in ('.memory', '.pi') or str(name) == 'AGENTS.md'):
                        continue
                    key = 'project/' + str(name)
                if item.isdir():
                    continue
                if not item.isfile() or key in snapshots:
                    raise ValueError('Unsafe or duplicate learned surface')
                body = archive.extractfile(item).read()
                snapshots[key] = {'bytes': base64.b64encode(body).decode(),
                                  'digest': hashlib.sha256(body).hexdigest(), 'mode': item.mode & 0o777}
    metadata = {key: {k: v for k, v in value.items() if k != 'bytes'} for key, value in snapshots.items()}
    if metadata != live_metadata:
        raise ValueError('Retained learned surfaces differ from raw live metadata')
    return snapshots


def collect_surface_metadata(private: Path, project: Path) -> dict:
    """Read only learned surfaces; emit hashes and modes, never private bodies."""
    def safe(file: Path) -> None:
        if any(parent.is_symlink() for parent in (file, *file.parents)):
            raise ValueError('Learned surface contains a symlink')
    result = {}
    for root, prefix in ((private, 'private/'), (project / '.memory', 'project/.memory/'), (project / '.pi', 'project/.pi/')):
        safe(root)
        if root.exists():
            for file in root.rglob('*'):
                safe(file)
                if file.is_dir():
                    continue
                if not file.is_file():
                    raise ValueError('Non-regular learned surface')
                result[prefix + str(file.relative_to(root))] = {
                    'digest': hashlib.sha256(file.read_bytes()).hexdigest(), 'mode': file.stat().st_mode & 0o777}
    for name in ('AGENTS.md',):
        file = project / name
        safe(file)
        if file.exists():
            if not file.is_file():
                raise ValueError('Non-regular project learned surface')
            result['project/' + name] = {'digest': hashlib.sha256(file.read_bytes()).hexdigest(), 'mode': file.stat().st_mode & 0o777}
    return result


def verify_recovery_delta(before: dict, after: dict) -> dict:
    """Only new receipt-owned history may explain a recovery's full endpoint."""
    try:
        encode = lambda attempt: json.dumps(attempt, sort_keys=True, separators=(',', ':'))
        old_attempts = Counter(encode(attempt) for attempt in before['attempts'])
        new_attempts = Counter(encode(attempt) for attempt in after['attempts'])
        if old_attempts - new_attempts:
            return {'passed': False, 'reason': 'prior-attempt-changed-or-lost'}
        old = {record['id']: record for record in before['history']}
        new = {record['id']: record for record in after['history']}
        if len(old) != len(before['history']) or len(new) != len(after['history']):
            return {'passed': False, 'reason': 'duplicate-history'}
        if any(new.get(id) != record for id, record in old.items()):
            return {'passed': False, 'reason': 'prior-history-changed'}
        old_digests = {attempt.get('receiptDigest') for attempt in before['attempts']}
        old_batches = {attempt.get('receipt', {}).get('batchId') for attempt in before['attempts'] if attempt.get('receipt')}
        owners = {attempt['receipt']['batchId'] for attempt in after['attempts']
                  if attempt.get('receiptDigest') and attempt['receiptDigest'] not in old_digests
                  and (attempt.get('receipt') or {}).get('batchId') and attempt['receipt']['batchId'] not in old_batches}
        histories = [record for id, record in new.items() if id not in old and record.get('status') == 'applied']
        if any(record.get('status') not in ('applied', 'proposed', 'abandoned') for id, record in new.items() if id not in old):
            return {'passed': False, 'reason': 'unfinished-history'}
        return verify_recovery_chains(before['surfaceSnapshots'], after['surfaceSnapshots'], histories, owners)
    except (KeyError, TypeError, ValueError):
        return {'passed': False, 'reason': 'incomplete-recovery-state'}


def claim_recovery(root: Path, session_digest: str, backlog_id: str, output_dir: str) -> Path:
    """An immutable claim survives failure/crash; preflight must never call this."""
    root.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256(json.dumps([session_digest,backlog_id],separators=(',',':')).encode()).hexdigest()
    file=root/(key+'.json')
    fd=os.open(file,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'w') as handle:
            json.dump({'sessionDigest':session_digest,'backlogId':backlog_id,'outputDir':output_dir,
                       'consumed':True,'interruptedUsageMayBeUnknown':True},handle)
            handle.flush();os.fsync(handle.fileno())
        directory=os.open(root,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    except BaseException:
        # Even a partial claim blocks automatic reuse; never reset on uncertainty.
        raise
    return file


def verify_recovery_chains(before: dict, after: dict, histories: list[dict], owner_batches: set[str]) -> dict:
    """Verify intermediate snapshots, all roots, permissions and actual endpoints."""
    def valid(value):
        if value is None:return True
        if not isinstance(value,dict) or set(value)!={'bytes','digest','mode'}:return False
        if type(value['mode']) is not int or not 0<=value['mode']<=0o777:return False
        try:return hashlib.sha256(base64.b64decode(value['bytes'],validate=True)).hexdigest()==value['digest']
        except (ValueError,TypeError):return False
    try:
        if any(not valid(value) or value is None for value in [*before.values(),*after.values()]):
            return {'passed':False,'reason':'invalid-endpoint'}
        chains={}
        for record in sorted(histories,key=lambda item:item['createdAt']):
            if record.get('status')!='applied' or not isinstance(record.get('batchId'),str) or not record['batchId'] or record['batchId'] not in owner_batches:
                return {'passed':False,'reason':'unowned-history'}
            for change in record['changes']:
                target=change['target'];root=target['root'];name=target['name']
                if root not in ('private','public','project') or not isinstance(name,str) or not name or name.startswith('/') or '..' in Path(name).parts:
                    return {'passed':False,'reason':'invalid-target'}
                if root in ('private','public') and (len(Path(name).parts)!=1 or not name.endswith('.md')):
                    return {'passed':False,'reason':'invalid-target'}
                if root=='project' and name not in ('AGENTS.md','.pi/harness.json'):
                    return {'passed':False,'reason':'invalid-target'}
                key=('project/.memory/' if root=='public' else root+'/')+name
                if not valid(change['before']) or not valid(change['after']):return {'passed':False,'reason':'invalid-snapshot'}
                chains.setdefault(key,[]).append(change)
        for key,changes in chains.items():
            current=before.get(key)
            for change in changes:
                if change['before']!=current:return {'passed':False,'reason':'broken-history-chain'}
                current=change['after']
            if current!=after.get(key):return {'passed':False,'reason':'history-endpoint-mismatch'}
        changed={key for key in set(before)|set(after) if before.get(key)!=after.get(key)}
        if not changed.issubset(chains):return {'passed':False,'reason':'unrecorded-mutation'}
        return {'passed':True,'verifiedPaths':sorted(chains),'changedPaths':sorted(changed)}
    except (KeyError,TypeError,ValueError):return {'passed':False,'reason':'malformed-history'}


if __name__ == '__main__':
    import sys
    print(json.dumps(collect_surface_metadata(Path(sys.argv[1]), Path(sys.argv[2]))))
