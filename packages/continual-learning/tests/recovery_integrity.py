"""Parent-owned study recovery safeguards; never authorize a learned mutation."""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path


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
