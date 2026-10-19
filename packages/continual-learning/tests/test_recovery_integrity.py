"""Given one failed slice, admit one recovery and verify every owned mutation."""
import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
import pytest
from recovery_integrity import claim_recovery, verify_recovery_chains


def test_current_native_history_matches_live_revision_bound_archive(tmp_path):
    # Given real parent-owned history, When captured, Then keep physical identity.
    import json
    import tarfile
    from support import run_bun
    from recovery_integrity import archive_surface_snapshots, collect_surface_metadata
    root = tmp_path.resolve()
    private, project = root / 'private', root / 'project'
    project.mkdir()
    result = run_bun('''
      import fs from 'node:fs/promises';import path from 'node:path';
      import {withLearningBatch,recordLearningMutation,listLearningHistory} from './packages/continual-learning/extensions/learning-history.ts';
      const root=ROOT,cwd=path.join(root,'project');
      process.env.PI_CODING_AGENT_DIR=path.join(root,'agent');
      await fs.mkdir(process.env.PI_CODING_AGENT_DIR);await fs.mkdir(path.join(cwd,'.pi'));
      const target=path.join(cwd,'.pi/harness.json');
      await withLearningBatch(()=>recordLearningMutation(cwd,'harness',[target],
        ()=>fs.writeFile(target,'{"rules":[]}',{mode:0o600})));
      console.log(JSON.stringify({history:await listLearningHistory(cwd)}));
    '''.replace('ROOT', json.dumps(str(root))))
    metadata = collect_surface_metadata(private, project)
    memory, source = root / 'memory.tar.gz', root / 'source.tar.gz'
    with tarfile.open(memory, 'w:gz'):
        pass
    with tarfile.open(source, 'w:gz') as archive:
        archive.add(project / '.pi', arcname='.pi')
    snapshots = archive_surface_snapshots(memory, source, metadata)
    history = result['history']
    owners = {record['batchId'] for record in history}
    assert verify_recovery_chains({}, snapshots, history, owners)['passed']
    endpoint = snapshots['project/.pi/harness.json']
    assert endpoint['revision'] == history[0]['changes'][0]['after']['revision']
    legacy_endpoint = {key: value for key, value in endpoint.items() if key != 'revision'}
    assert not verify_recovery_chains({}, {'project/.pi/harness.json': legacy_endpoint}, history, owners)['passed']
    # A same-byte replacement has a different identity and cannot inherit proof.
    altered = {**endpoint, 'revision': endpoint['revision'].replace(':', ':0', 1)}
    assert not verify_recovery_chains({}, {'project/.pi/harness.json': altered}, history, owners)['passed']
    target = project / '.pi/harness.json'
    replacement = target.with_suffix('.replacement')
    replacement.write_bytes(target.read_bytes())
    replacement.chmod(target.stat().st_mode & 0o777)
    replacement.replace(target)
    replacement_metadata = collect_surface_metadata(private, project)
    assert replacement_metadata['project/.pi/harness.json']['digest'] == endpoint['digest']
    assert replacement_metadata['project/.pi/harness.json']['revision'] != endpoint['revision']
    replacement_snapshots = archive_surface_snapshots(memory, source, replacement_metadata)
    assert not verify_recovery_chains({}, replacement_snapshots, history, owners)['passed']
    bad_metadata = {key: {**value, 'revision': '1:2:999:3:4'} for key, value in metadata.items()}
    with pytest.raises(ValueError, match='revision'):
        archive_surface_snapshots(memory, source, bad_metadata)


@pytest.mark.parametrize('field,value', [('revision', 'not-a-revision'), ('revision', '1:2:999:3:4'), ('unexpected', 'field')])
def test_recovery_rejects_malformed_or_unbound_revision_metadata(field, value):
    snapshot = {**state('new'), 'revision': '1:2:3:4:5'}
    changed = {**snapshot, field: value}
    record = history('private', 'fact.md', None, changed)
    assert not verify_recovery_chains({}, {'private/fact.md': changed}, [record], {'owner'})['passed']


def test_recovery_delta_requires_complete_owned_history_not_one_private_change():
    from recovery_integrity import verify_recovery_delta
    a,b=state('old'),state('new')
    before={'surfaceSnapshots':{'private/fact.md':a},'history':[],'attempts':[]}
    after={'surfaceSnapshots':{'private/fact.md':b},'history':[history('private','fact.md',a,b)],
           'attempts':[{'receiptDigest':'new','receipt':{'batchId':'owner'}}]}
    assert verify_recovery_delta(before,after)['passed']
    assert not verify_recovery_delta(before,{**after,'attempts':[]})['passed']
    after['surfaceSnapshots']['project/.memory/unrecorded.md']=b
    assert not verify_recovery_delta(before,after)['passed']
    del after['surfaceSnapshots']['project/.memory/unrecorded.md']
    before['attempts']=after['attempts']
    assert not verify_recovery_delta(before,after)['passed']


def test_recovery_delta_rejects_rewritten_or_removed_prior_history():
    from recovery_integrity import verify_recovery_delta
    a=state('same');old=history('private','fact.md',None,a)
    before={'surfaceSnapshots':{'private/fact.md':a},'history':[old],'attempts':[]}
    after={**before,'history':[]}
    assert not verify_recovery_delta(before,after)['passed']
    after['history']=[{**old,'status':'undone'}]
    assert not verify_recovery_delta(before,after)['passed']


@pytest.mark.parametrize('replacement',[[],[{'receiptDigest':'old','receipt':{'batchId':'old-owner','totals':{'cost':0}}}]])
def test_recovery_never_discards_or_rewrites_prior_cost_receipts(replacement):
    from recovery_integrity import verify_recovery_delta
    attempt={'receiptDigest':'old','receipt':{'batchId':'old-owner','totals':{'cost':1}}}
    before={'surfaceSnapshots':{},'history':[],'attempts':[attempt]}
    assert verify_recovery_delta(before,before)['passed']
    assert not verify_recovery_delta(before,{**before,'attempts':replacement})['passed']


def test_archive_surfaces_bind_raw_live_metadata_and_reject_symlinks(tmp_path):
    import io
    import tarfile
    from recovery_integrity import archive_surface_snapshots
    memory,project=tmp_path/'memory.tar.gz',tmp_path/'source.tar.gz'
    def archive(file,entries):
        with tarfile.open(file,'w:gz') as output:
            for name,body in entries:
                item=tarfile.TarInfo(name);item.mode=0o600
                if body is None:item.type=tarfile.SYMTYPE;item.linkname='/outside'
                else:item.size=len(body)
                output.addfile(item,io.BytesIO(body) if body is not None else None)
    archive(memory,[('./--work-p-limit--/fact.md',b'old')])
    archive(project,[('./.memory/fact.md',b'old'),('./AGENTS.md',b'guide'),('./.pi/harness.json',b'{}')])
    expected={key:{k:v for k,v in state(text).items() if k!='bytes'} for key,text in
              [('private/fact.md','old'),('project/.memory/fact.md','old'),('project/AGENTS.md','guide'),('project/.pi/harness.json','{}')]}
    assert len(archive_surface_snapshots(memory,project,expected))==4
    with pytest.raises(ValueError):archive_surface_snapshots(memory,project,{})
    expected['private/fact.md']['digest']='redacted-or-changed'
    with pytest.raises(ValueError):archive_surface_snapshots(memory,project,expected)
    archive(project,[('./.memory/fact.md',None)])
    with pytest.raises(ValueError):archive_surface_snapshots(memory,project,expected)


def state(text,mode=0o600):
    data=text.encode()
    return {'bytes':base64.b64encode(data).decode(),'digest':hashlib.sha256(data).hexdigest(),'mode':mode}


def history(root,name,before,after):
    return {'id':name,'batchId':'owner','status':'applied','createdAt':'2026-10-12T00:00:00Z',
            'changes':[{'target':{'root':root,'name':name},'before':before,'after':after}]}


def test_single_use_is_exclusive_and_survives_failed_or_interrupted_attempt(tmp_path):
    def claim(_):
        try:return claim_recovery(tmp_path,'session','job',str(tmp_path/'run'))
        except FileExistsError:return None
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(claim,range(16)))
    files=[p for p in results if p]
    assert len(files)==1 and files[0].stat().st_mode&0o777==0o600
    with pytest.raises(FileExistsError):claim_recovery(tmp_path,'session','job','new-run')


def test_private_and_public_intermediate_mutations_require_exact_byte_chains():
    a,b=state('old'),state('new')
    records=[history('private','fact.md',a,b),history('private','fact.md',b,a)]
    assert verify_recovery_chains({'private/fact.md':a},{'private/fact.md':a},records,{'owner'})['passed']
    records[0]['changes'][0]['after']['bytes']=base64.b64encode(b'forged').decode()
    assert not verify_recovery_chains({'private/fact.md':a},{'private/fact.md':a},records,{'owner'})['passed']


@pytest.mark.parametrize('root,key',[('private','private/fact.md'),('public','project/.memory/fact.md'),('project','project/AGENTS.md')])
def test_all_allowed_roots_and_permissions_are_bound(root,key):
    a,b=state('old'),state('new',0o644)
    record=history(root,'fact.md' if root!='project' else 'AGENTS.md',a,b)
    assert verify_recovery_chains({key:a},{key:b},[record],{'owner'})['passed']
    assert not verify_recovery_chains({key:a},{key:{**b,'mode':0o600}},[record],{'owner'})['passed']
    assert not verify_recovery_chains({key:a},{key:b},[],{'owner'})['passed']
    assert not verify_recovery_chains({key:a},{key:b},[record],{'different'})['passed']


def test_missing_batch_and_unrecorded_private_mutation_are_not_authorized():
    a,b=state('old'),state('new')
    record=history('private','fact.md',a,b);record['batchId']=None
    assert not verify_recovery_chains({'private/fact.md':a},{'private/fact.md':b},[record],{None})['passed']
    assert not verify_recovery_chains({}, {'private/new.md':b},[],{'owner'})['passed']


@pytest.mark.parametrize('mutation', ['in-place-write', 'same-byte-replace'])
def test_live_metadata_rejects_a_change_after_open_before_read(tmp_path, monkeypatch, mutation):
    # Given a regular opened target, When it changes before the read, Then fail.
    import os
    from recovery_integrity import collect_surface_metadata
    root = tmp_path.resolve()
    private, project = root / 'private', root / 'project'
    private.mkdir()
    project.mkdir()
    target = private / 'fact.md'
    target.write_bytes(b'original')
    original_fstat = os.fstat
    calls = 0

    def change_after_first_stat(fd):
        nonlocal calls
        info = original_fstat(fd)
        calls += 1
        if calls == 1:
            if mutation == 'in-place-write':
                target.write_bytes(b'changed-content')
            else:
                replacement = root / 'replacement'
                replacement.write_bytes(target.read_bytes())
                replacement.chmod(target.stat().st_mode & 0o777)
                replacement.replace(target)
        return info

    monkeypatch.setattr(os, 'fstat', change_after_first_stat)
    with pytest.raises(ValueError, match='changed during metadata capture'):
        collect_surface_metadata(private, project)
    assert calls == 2


@pytest.mark.parametrize('link_position', ['leaf', 'ancestor'])
def test_live_metadata_rejects_symbolic_links_before_read(tmp_path, link_position):
    # Given an outside file, When a learned path links to it, Then refuse it.
    from recovery_integrity import collect_surface_metadata
    root = tmp_path.resolve()
    private, project, outside = root / 'private', root / 'project', root / 'outside'
    project.mkdir()
    outside.mkdir()
    (outside / 'fact.md').write_bytes(b'outside fixture')
    if link_position == 'ancestor':
        private.symlink_to(outside, target_is_directory=True)
    else:
        private.mkdir()
        (private / 'fact.md').symlink_to(outside / 'fact.md')
    with pytest.raises(ValueError, match='symlink'):
        collect_surface_metadata(private, project)


def test_observed_failure_input_is_complete_source_only_and_bound(tmp_path):
    import io,json,tarfile
    from recovery_integrity import load_observed_idle_source
    files={'index.js':b'actual failed source','index.d.ts':b'actual declarations',
           'observed-idle-failure.mjs':b'public reproducer','package.json':b'{"name":"p-limit"}'}
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w:gz') as archive:
        for name,body in files.items():
            item=tarfile.TarInfo(name);item.size=len(body);item.mode=0o644;archive.addfile(item,io.BytesIO(body))
    archive=tmp_path/'source.tar.gz';archive.write_bytes(raw.getvalue());archive.chmod(0o444)
    value={'kind':'actual-public-project-failed-source-input','version':1,'sourceOnlySeedNotKnowledgeSeed':True,
        'learningBenefitEstablished':False,'sourceArchiveSha256':hashlib.sha256(raw.getvalue()).hexdigest(),
        'files':{name:{'sha256':hashlib.sha256(body).hexdigest(),'size':len(body),'mode':0o644} for name,body in files.items()},
        'publicReproducer':{'file':'observed-idle-failure.mjs','sha256':hashlib.sha256(files['observed-idle-failure.mjs']).hexdigest()}}
    manifest=tmp_path/'input-manifest.json';manifest.write_text(json.dumps(value));manifest.chmod(0o444)
    result=load_observed_idle_source(manifest)
    assert result['archive']==raw.getvalue() and result['manifest']==value
    assert {name:item['data'] for name,item in result['files'].items()}==files
    # Given complete admitted bytes, reject tampered inventory, implicit knowledge
    # seeds and symlinks before creating a container or making a request.
    for field,bad in [('sourceArchiveSha256','0'*64),('files',{}),('sourceOnlySeedNotKnowledgeSeed',False)]:
        manifest.chmod(0o600);manifest.write_text(json.dumps({**value,field:bad}));manifest.chmod(0o444)
        with pytest.raises(ValueError):load_observed_idle_source(manifest)
    manifest.chmod(0o600);manifest.write_text(json.dumps(value));manifest.chmod(0o444)
    link=tmp_path/'link.json';link.symlink_to(manifest)
    with pytest.raises(ValueError):load_observed_idle_source(link)


@pytest.mark.parametrize('name,kind',[('../outside','file'),('/absolute','file'),('.memory/fact.md','file'),('.pi/harness.json','file'),('AGENTS.md','file'),('source','symlink'),('node_modules/x','file')])
def test_observed_source_archive_rejects_escape_special_files_and_learned_overlays(name,kind):
    import io,tarfile
    from recovery_integrity import source_archive_files
    raw=io.BytesIO()
    with tarfile.open(fileobj=raw,mode='w:gz') as archive:
        item=tarfile.TarInfo(name)
        if kind=='symlink':item.type=tarfile.SYMTYPE;item.linkname='outside'
        else:item.size=1
        archive.addfile(item,io.BytesIO(b'x') if kind=='file' else None)
    with pytest.raises(ValueError):source_archive_files(raw.getvalue())
