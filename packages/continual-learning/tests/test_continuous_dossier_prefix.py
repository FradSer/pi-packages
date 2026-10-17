import copy
import json
import subprocess
import pytest
from pathlib import Path
from continuous_project_evidence import exact_failure_processed, verifier_observation


def summarize(task, ranges):
    helper = Path(__file__).with_name('continuous-dossier-proof.mjs').as_uri()
    code = f"import fs from 'node:fs';import {{summarizeDossier,dossierDigest}} from {json.dumps(helper)};const x=JSON.parse(fs.readFileSync(0,'utf8'));const ranges=x.ranges??[{{from:4,to:5,digest:dossierDigest(x.original)}}];console.log(JSON.stringify(summarizeDossier(x.task,ranges)));"
    return json.loads(subprocess.run(['node', '--input-type=module', '-e', code],
                                    input=json.dumps(task | {'ranges': ranges} if ranges is not None else task),
                                    capture_output=True, text=True, check=True).stdout)


def evidence():
    observation = dict(kind='actual-project-verification', sessionDigest='session', logsDigest='logs')
    entries = [dict(id='user', message=dict(role='user', content='actual request')),
               dict(id='read', message=dict(role='toolResult', toolName='read', isError=False,
                                           content=[dict(type='text', text=json.dumps(observation))]))]
    original = dict(kind='learning-task-slice', version=1, entries=entries)
    feedback = dict(queuedFailure={'id':'job','from':4,'to':5}, originalEntryIds=['user', 'read'], observation=observation)
    learning = dict(attempts=[dict(outcome='completed', receiptDigest='ack', receipt=dict(input=dict(backlogId='job')))],
                    completedBacklog={'job': 'ack'}, dossiers=[])
    return original, feedback, learning


def test_complete_original_prefix_survives_append_without_replacing_review():
    original, feedback, learning = evidence()
    full = copy.deepcopy(original)
    full['entries'].append(dict(id='source', message=dict(role='toolResult', toolName='learning_read', isError=False, content=[])))
    proof = summarize(dict(original=original, task=full), None)
    feedback['queuedFailure']['digest'] = proof['originalPrefixProofs'][0]['digest']
    learning['dossiers'] = [proof]
    assert proof['taskSliceDigest'] != feedback['queuedFailure']['digest']
    assert exact_failure_processed(feedback, learning)
    learning['completedBacklog']['job'] = 'foreign'
    assert not exact_failure_processed(feedback, learning)


def test_prefix_proof_rejects_changed_reordered_shortened_and_forged_evidence():
    original, feedback, learning = evidence()
    reference = summarize(dict(original=original, task=original), None)
    digest = reference['taskSliceDigest']
    feedback['queuedFailure']['digest'] = digest
    variants = []
    changed = copy.deepcopy(original); changed['entries'][0]['message']['content'] = 'different'; variants.append(changed)
    changed = copy.deepcopy(original); changed['entries'].reverse(); variants.append(changed)
    changed = copy.deepcopy(original); changed['entries'].pop(); variants.append(changed)
    changed = copy.deepcopy(original); changed['extraEnvelopeField'] = True; variants.append(changed)
    changed = copy.deepcopy(original); changed['omittedEntries'] = 1; variants.append(changed)
    changed = copy.deepcopy(original); changed['entries'][1]['message']['isError'] = True; variants.append(changed)
    changed = copy.deepcopy(original); changed['entries'][1]['message']['content'] = []; changed['entries'].append(original['entries'][1]); variants.append(changed)
    for task in variants:
        proof = summarize(dict(original=original, task=task), [{'from':4,'to':5,'digest':digest}])
        learning['dossiers'] = [proof]
        assert not exact_failure_processed(feedback, learning)
        assert proof['originalPrefixProofs'] == []


def test_verifier_snapshot_does_not_change_after_recovery(tmp_path):
    checks = dict(passed=False, upstream=dict(passed=False))
    sources = {'index.js': 'old'}
    observation = verifier_observation('task', checks, tmp_path, sources, b'session')
    frozen = json.dumps(observation)
    checks['afterRecovery'] = dict(passed=True)
    checks['upstream']['passed'] = True
    sources['index.js'] = 'new'
    assert json.dumps(observation) == frozen


def test_appended_verifier_cannot_replace_an_original_observation():
    original, feedback, learning = evidence()
    fake = original['entries'][1]
    original['entries'][1] = dict(id='read', message=dict(role='assistant', content='not an observed result'))
    full = copy.deepcopy(original); full['entries'].append(fake)
    proof = summarize(dict(original=original, task=full), None)
    feedback['queuedFailure']['digest'] = proof['originalPrefixProofs'][0]['digest']
    learning['dossiers'] = [proof]
    assert proof['observations'] and not proof['originalPrefixProofs'][0]['observations']
    assert not exact_failure_processed(feedback, learning)


def test_prefix_boundaries_and_full_review_digest_cannot_be_substituted():
    original, feedback, learning = evidence()
    full = copy.deepcopy(original); full['entries'].append(dict(id='source'))
    proof = summarize(dict(original=original, task=full), None)
    feedback['queuedFailure']['digest'] = proof['originalPrefixProofs'][0]['digest']
    learning['dossiers'] = [proof]
    feedback['queuedFailure'].update({'from':9,'to':10})
    assert not exact_failure_processed(feedback, learning)
    feedback['queuedFailure'].update({'from':4,'to':5})
    proof['originalPrefixProofs'][0]['reviewDigest'] = 'foreign'
    assert not exact_failure_processed(feedback, learning)


@pytest.mark.parametrize('variant', ['original', 'dot-root', 'nested', 'parent', 'foreign-scope', 'wrong-digest', 'negative-range', 'boolean-range', 'symlink'])
def test_artifact_capture_preserves_closed_single_range_from_original_backlog(monkeypatch, tmp_path, variant):
    import io
    import tarfile
    import live_continuous_project_learning as study
    original, feedback, _ = evidence()
    complete = copy.deepcopy(original)
    complete['entries'].append(dict(id='fresh-source', message=dict(role='toolResult', toolName='read', isError=False, content=[])))
    reference = summarize(dict(original=original, task=original), [])
    digest = reference['taskSliceDigest']
    job = 'a' * 64
    record = dict(version=1, scopeKey='--work-p-limit--', sessionFile=study.base.AGENT+'/sessions/continuous/stage-1.jsonl', from_=4, to=5, digest=digest)
    record['from'] = record.pop('from_')
    if variant == 'foreign-scope': record['scopeKey'] = '--other-project--'
    if variant == 'wrong-digest': record['digest'] = 'b' * 64
    if variant == 'negative-range': record['from'] = -1
    if variant == 'boolean-range': record['from'] = True
    receipt = dict(input=dict(backlogId=job), totals=dict(totalTokens=0, cost=0), operations=0)
    feedback['queuedFailure'] = dict(id=job, **{k: record[k] for k in ('from', 'to', 'digest')})
    receipt_digest = json.loads(subprocess.run(['node', '-e', "let s='';process.stdin.on('data',b=>s+=b).on('end',()=>console.log(JSON.stringify(require('crypto').createHash('sha256').update(JSON.stringify(JSON.parse(s))).digest('hex'))))"], input=json.dumps(receipt), capture_output=True, text=True, check=True).stdout)
    saved = {}

    def export(_c, source, output, _proxy):
        files = {}
        if source.endswith('/memory'):
            files['runs/--work-p-limit--/run_fixture/incremental-learning-dossier.json'] = json.dumps(dict(kind='incremental-learning-dossier', taskSlice=complete)).encode()
        if source.endswith('/learning'):
            archive_path = {'dot-root':'./backlog.jsonl', 'nested':'foreign/backlog.jsonl', 'parent':'../backlog.jsonl'}.get(variant, 'backlog.jsonl')
            files[archive_path] = (json.dumps(record)+'\n').encode()
            files['--work-p-limit--/replay-owner.json'] = json.dumps(dict(attempts=[dict(outcome='completed', receipt=receipt)])).encode()
            files['backlog-completed.json'] = json.dumps({job: receipt_digest}).encode()
        with tarfile.open(output, 'w:gz') as archive:
            for name, data in files.items():
                entry = tarfile.TarInfo(name)
                if variant == 'symlink' and name == 'backlog.jsonl':
                    entry.type = tarfile.SYMTYPE; entry.linkname = 'foreign/backlog.jsonl'; archive.addfile(entry)
                else:
                    entry.size = len(data); archive.addfile(entry, io.BytesIO(data))

    def checked(args):
        if 'python3' in args:
            return b'{}'
        if 'node' in args:
            local = tmp_path/'node-input.json'; local.write_bytes(saved['/home/node/study-receipts.json'])
            script = args[-1].replace("'/home/node/study-receipts.json'", json.dumps(str(local)))
            return subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, check=True).stdout
        return json.dumps(dict(pending=0, pendingEntries=[])).encode()

    monkeypatch.setattr(study.base, 'export_tree', export)
    monkeypatch.setattr(study.base, 'put', lambda _c, file, content: saved.update({file: content}))
    monkeypatch.setattr(study.base, 'checked', checked)
    monkeypatch.setattr(study.base, 'shell', lambda *_args: b'')
    if variant in ('negative-range', 'boolean-range', 'symlink'):
        with pytest.raises(RuntimeError, match='Original backlog range archive is not regular|Invalid scoped original backlog range'):
            study.artifacts('fixture', None, tmp_path/'captured')
        return
    captured = study.artifacts('fixture', None, tmp_path/'captured')
    assert captured['pendingLearningJobs'] == 0
    admitted = variant in ('original', 'dot-root')
    assert bool(captured['dossiers'][0]['originalPrefixProofs']) == admitted
    assert exact_failure_processed(feedback, captured) == admitted
    assert captured['actualLearningOperations'] == 0, 'Processing must not be relabeled as learned benefit'
