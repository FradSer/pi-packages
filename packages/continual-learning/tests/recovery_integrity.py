"""Parent-owned study recovery safeguards; never authorize a learned mutation."""
from __future__ import annotations
import base64
import hashlib
import json
import os
import re
import stat
import tarfile
from collections import Counter
from pathlib import Path


def _revision(info: os.stat_result) -> str:
    return ':'.join(str(value) for value in
                    (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns))


def _valid_revision(value: object, size: int) -> bool:
    return (isinstance(value, str)
            and re.fullmatch(r'[0-9]+:[0-9]+:[0-9]+:-?[0-9]+:-?[0-9]+', value) is not None
            and int(value.split(':')[2]) == size)


PROTECTED_ACCOUNTING_NAMES = frozenset(('cost-ledger.jsonl','authorized-real-study-budget-600.json','600-active-reservation.json'))


def _read_study_artifact(root: Path, relative: str, bound: int, expected: dict | None, immutable: bool) -> tuple[bytes, dict]:
    """Read anchored regular evidence without following any path component."""
    if (not root.is_absolute() or not isinstance(relative,str) or not relative
            or Path(relative).is_absolute() or '\\' in relative
            or str(Path(relative)) != relative or any(part in ('..','.') for part in (*root.parts,*Path(relative).parts))
            or any(part in PROTECTED_ACCOUNTING_NAMES for part in (*root.parts,*Path(relative).parts))
            or type(bound) is not int or not 0 < bound <= 32*1024*1024):
        raise ValueError('Unsafe study artifact path or bound')
    if expected is not None and (not isinstance(expected,dict) or set(expected)!={'sha256','size','mode','revision'}
            or not isinstance(expected['sha256'],str) or re.fullmatch(r'[a-f0-9]{64}',expected['sha256']) is None
            or type(expected['size']) is not int or not 0 <= expected['size'] <= bound
            or type(expected['mode']) is not int or not 0 <= expected['mode'] <= 0o777
            or not _valid_revision(expected['revision'],expected['size'])):
        raise ValueError('Invalid expected study artifact identity')
    descriptors=[];links=[];file_fd=None
    try:
        descriptors.append(os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW))
        parts=[*root.parts[1:],*Path(relative).parts]
        for part in parts[:-1]:
            parent=descriptors[-1]
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            descriptors.append(child);links.append((parent,part,child))
        parent=descriptors[-1];name=parts[-1]
        file_fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(file_fd,'rb') as stream:
            file_fd=None;before=os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_size>bound
                    or immutable and before.st_mode & 0o222):raise ValueError('Artifact is not bounded regular data')
            data=stream.read(bound+1);after=os.fstat(stream.fileno())
        current=os.stat(name,dir_fd=parent,follow_symlinks=False)
        if (len(data)>bound or len(data)!=after.st_size or _revision(before)!=_revision(after)
                or _revision(after)!=_revision(current) or before.st_mode!=after.st_mode or after.st_mode!=current.st_mode):
            raise ValueError('Study artifact changed during capture')
        for parent,part,child in links:
            linked=os.stat(part,dir_fd=parent,follow_symlinks=False);opened=os.fstat(child)
            if not stat.S_ISDIR(linked.st_mode) or (linked.st_dev,linked.st_ino)!=(opened.st_dev,opened.st_ino):
                raise ValueError('Study artifact parent changed')
        binding={'sha256':hashlib.sha256(data).hexdigest(),'size':len(data),'mode':after.st_mode & 0o777,'revision':_revision(after)}
        if expected is not None and binding!=expected:raise ValueError('Study artifact identity differs')
        return data,binding
    except OSError as error:raise ValueError('Study artifact is unavailable or unsafe') from error
    finally:
        if file_fd is not None:os.close(file_fd)
        for descriptor in reversed(descriptors):os.close(descriptor)


def read_study_artifact(root: Path, relative: str, *, bound: int, expected: dict | None = None, immutable: bool = False) -> bytes:
    """Read complete scoped evidence; a matching hash alone is not identity."""
    return _read_study_artifact(root,relative,bound,expected,immutable)[0]


def bind_study_artifact(root: Path, relative: str, *, bound: int) -> dict:
    """Capture an owner-created artifact's exact bytes and physical identity."""
    return _read_study_artifact(root,relative,bound,None,False)[1]


def source_archive_files(raw: bytes) -> dict[str, dict]:
    """Validate a complete, bounded source-only archive before extraction."""
    import gzip
    import io
    from pathlib import PurePosixPath
    bound = 16 * 1024 * 1024
    if len(raw) > bound:
        raise ValueError('Compressed source archive exceeds bound')
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
            expanded = compressed.read(bound + 1)
        if len(expanded) > bound:
            raise ValueError('Expanded source archive exceeds bound')
        files, seen, end = {}, set(), 0
        with tarfile.open(fileobj=io.BytesIO(expanded), mode='r:') as archive:
            for member in archive:
                path = PurePosixPath(member.name)
                key = str(path)
                if (len(seen) >= 512 or path.is_absolute() or '..' in path.parts or '\\' in member.name
                        or key in seen or member.sparse or member.mode & 0o7000
                        or member.name.rstrip('/') not in (key, './' + key)
                        or not (member.isdir() or member.isfile())):
                    raise ValueError('Unsafe source archive member')
                seen.add(key)
                end = max(end, ((member.offset_data + member.size + 511) // 512) * 512)
                if path.parts and path.parts[0] in ('.git', 'node_modules', '.memory', '.pi', 'AGENTS.md'):
                    raise ValueError('Source archive contains learned state or dependency overlay')
                if member.isdir():
                    continue
                if not path.parts or member.size > 2 * 1024 * 1024 or 'continuous-study' in key:
                    raise ValueError('Invalid source file')
                data = archive.extractfile(member).read(member.size + 1)
                if len(data) != member.size:
                    raise ValueError('Incomplete source file')
                files[key] = {'data': data, 'sha256': hashlib.sha256(data).hexdigest(),
                              'size': len(data), 'mode': member.mode & 0o777}
        if len(expanded) - end < 1024 or any(expanded[end:]):
            raise ValueError('Incomplete or trailing source archive')
        for name in files:
            if any(str(parent) in files for parent in PurePosixPath(name).parents):
                raise ValueError('Source file/directory collision')
        return files
    except (OSError, EOFError, tarfile.TarError) as error:
        raise ValueError('Unreadable complete source archive') from error


def load_observed_idle_source(manifest: Path) -> dict:
    """Read admitted immutable inputs; this does not authenticate their origin."""
    def read(file: Path, bound: int) -> bytes:
        return read_study_artifact(file.parent,file.name,bound=bound,immutable=True)
    try:
        manifest_raw = read(manifest, 2 * 1024 * 1024)
        value = json.loads(manifest_raw)
        if (value['kind'] != 'actual-public-project-failed-source-input' or value['version'] != 1
                or value['sourceOnlySeedNotKnowledgeSeed'] is not True or value['learningBenefitEstablished'] is not False):
            raise ValueError('Unsupported failure source input')
        raw = read(manifest.with_name('source.tar.gz'), 16 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != value['sourceArchiveSha256']:
            raise ValueError('Source archive binding changed')
        files = source_archive_files(raw)
        if {name: {key: item[key] for key in ('sha256', 'mode', 'size')} for name, item in files.items()} != value['files']:
            raise ValueError('Complete source inventory differs')
        case = value['publicReproducer']
        if (case['file'] != 'observed-idle-failure.mjs'
                or files[case['file']]['sha256'] != case['sha256']
                or not {'index.js', 'index.d.ts', 'package.json'}.issubset(files)):
            raise ValueError('Missing bound public failure case or source')
        return {'manifest': value, 'manifestSha256': hashlib.sha256(manifest_raw).hexdigest(),
                'archive': raw, 'files': files}
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('Incomplete failure source input') from error


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
                # Tar does not retain inode or nanosecond identity. Bind its exact
                # bytes/mode to the separately collected live identity, never
                # infer that identity from history or from the archive itself.
                live = live_metadata.get(key)
                if isinstance(live, dict) and 'revision' in live:
                    if not _valid_revision(live['revision'], len(body)):
                        raise ValueError('Invalid live learned-surface revision')
                    snapshots[key]['revision'] = live['revision']
    metadata = {key: {k: v for k, v in value.items() if k != 'bytes'} for key, value in snapshots.items()}
    if metadata != live_metadata:
        raise ValueError('Retained learned surfaces differ from raw live metadata')
    return snapshots


def collect_surface_metadata(private: Path, project: Path) -> dict:
    """Read only learned surfaces; emit hashes and modes, never private bodies."""
    def safe(file: Path) -> None:
        if any(parent.is_symlink() for parent in (file, *file.parents)):
            raise ValueError('Learned surface contains a symlink')
    def metadata(file: Path) -> dict:
        safe(file)
        with os.fdopen(os.open(file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError('Non-regular learned surface')
            body = handle.read()
            after = os.fstat(handle.fileno())
        safe(file)
        current = file.lstat()
        if (_revision(before) != _revision(after) or _revision(after) != _revision(current)
                or before.st_mode != after.st_mode or after.st_mode != current.st_mode
                or len(body) != after.st_size):
            raise ValueError('Learned surface changed during metadata capture')
        return {'digest': hashlib.sha256(body).hexdigest(), 'mode': after.st_mode & 0o777,
                'revision': _revision(after)}
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
                result[prefix + str(file.relative_to(root))] = metadata(file)
    for name in ('AGENTS.md',):
        file = project / name
        safe(file)
        if file.exists():
            if not file.is_file():
                raise ValueError('Non-regular project learned surface')
            result['project/' + name] = metadata(file)
    return result


def verify_recovery_delta(before: dict, after: dict) -> dict:
    """Only new receipt-owned history may explain a recovery's full endpoint."""
    return _verify_recovery_delta(before, after)


def verify_command_recovery_delta(before: dict, after: dict, receipt: dict) -> dict:
    """Check direct command ownership, without manufacturing replay attempts.

    Native invocation and receipt authenticity remain separate required proofs.
    """
    return _verify_recovery_delta(before, after, command_receipt=receipt)


def _verify_recovery_delta(before: dict, after: dict, *, command_receipt: dict | None = None) -> dict:
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
        if command_receipt is not None:
            batch = command_receipt.get('batchId')
            matching = [value for value in after['receipts'] if value.get('batchId') == batch]
            attempt_rows = command_receipt.get('attempts')
            memory_attempts = [value for value in attempt_rows if isinstance(value,dict) and value.get('phase') == 'memory'] if isinstance(attempt_rows,list) else []
            if (command_receipt.get('kind') != 'learning-pipeline-receipt' or command_receipt.get('version') != 1
                    or command_receipt.get('mode') != 'manual' or not isinstance(batch, str) or not batch
                    or type(command_receipt.get('operations')) is not int or command_receipt['operations'] < 1
                    or not isinstance(command_receipt.get('attempts'), list)
                    or any(not isinstance(value,dict) for value in attempt_rows)
                    or any(value.get('pendingOperations', 0) > 0 for value in command_receipt['attempts'])
                    or not memory_attempts or memory_attempts[-1].get('outcome') != 'applied'
                    or not any(value.get('phase') == 'memory' and value.get('outcome') == 'applied'
                               and value.get('operations', 0) > 0 for value in command_receipt['attempts'])
                    or matching != [command_receipt]
                    or any(value.get('batchId') == batch for value in before['receipts'])
                    or batch in old_batches or batch in owners):
                return {'passed': False, 'reason': 'invalid-direct-command-owner'}
            # Keep cumulative costs and prior direct receipts exactly, too.
            if Counter(encode(value) for value in before['receipts']) - Counter(encode(value) for value in after['receipts']):
                return {'passed': False, 'reason': 'prior-command-receipt-changed-or-lost'}
            owners.add(batch)
        histories = [record for id, record in new.items() if id not in old and record.get('status') == 'applied']
        if any(record.get('status') not in ('applied', 'proposed', 'abandoned') for id, record in new.items() if id not in old):
            return {'passed': False, 'reason': 'unfinished-history'}
        return verify_recovery_chains(before['surfaceSnapshots'], after['surfaceSnapshots'], histories, owners)
    except (KeyError, TypeError, ValueError, AttributeError):
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
        if not isinstance(value,dict) or set(value) not in ({'bytes','digest','mode'}, {'bytes','digest','mode','revision'}):return False
        if type(value['mode']) is not int or not 0<=value['mode']<=0o777:return False
        try:
            body = base64.b64decode(value['bytes'],validate=True)
            return (hashlib.sha256(body).hexdigest()==value['digest']
                    and ('revision' not in value or _valid_revision(value['revision'], len(body))))
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
