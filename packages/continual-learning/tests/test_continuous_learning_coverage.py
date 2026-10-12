from continuous_project_evidence import continuous_coverage, verifier_observation


def test_partial_real_receipt_retains_known_cost_and_counts_unknown_usage(tmp_path, monkeypatch) -> None:
    import io
    import json
    import tarfile
    from pathlib import Path
    import live_continuous_project_learning as study

    receipt = json.loads((Path(__file__).parent / 'fixtures/real-interrupted-learning-receipt.json').read_text())
    receipt['attempts'][0]['usageLedgerId'] = 'already-in-receipt'
    assert receipt['usageAvailable'] is False and receipt['costAvailable'] is False

    def export_tree(container, root, output, proxy):
        with tarfile.open(output, 'w:gz') as archive:
            if root.endswith('/learning'):
                data = json.dumps({'version': 1, 'attempts': [{'outcome': 'failed', 'receipt': receipt}]}).encode()
                item = tarfile.TarInfo('replay-real.json')
                item.size = len(data)
                archive.addfile(item, io.BytesIO(data))
                for name, included in [('harness-repair-usage-failed.json', False), ('harness-task-usage.json', True), ('memory-repair-usage-orphan.json', False)]:
                    data = json.dumps({'knownUsage': receipt['attempts'][0]['usage'] if included else {'input': 1, 'output': 2, 'cacheRead': 0, 'cacheWrite': 0, 'totalTokens': 3, 'cost': .012}, 'assistantMessages': 1, 'complete': included or name.startswith('memory-'), 'ledgerId': 'already-in-receipt' if included else name}).encode()
                    item = tarfile.TarInfo('run/' + name); item.size = len(data)
                    archive.addfile(item, io.BytesIO(data))

    monkeypatch.setattr(study.base, 'export_tree', export_tree)
    monkeypatch.setattr(study.base, 'put', lambda *args: None)
    monkeypatch.setattr(study.base, 'shell', lambda *args: b'')
    monkeypatch.setattr(study.base, 'checked', lambda args: b'{}' if 'python3' in args else b'[null]' if 'node' in args else b'{"pending":2}')
    result = study.artifacts('isolated-fixture', None, tmp_path)
    assert result['knownLearningTokens'] == 31555
    assert result['knownLearningCost'] == receipt['totals']['cost'] + .024
    assert len(result['partialWorkerUsageLedgers']) == 2
    assert result['interruptedUnknownUsage'] == 1
    assert result['allLearningCostsPriced'] is False


def test_harness_only_old_operations_cannot_prove_memory_use_or_correction() -> None:
    report={'stages':[{'id':'orientation','arms':{'with-learning':{'learning':{'actualLearningOperations':1,'memoryEntries':[]},'inference':{'deliveredMemoryEntries':[]},'harness':{'passed':True}}}}]}
    result=continuous_coverage(report)
    assert not result['coverageComplete']
    assert not result['memoryLearned'] and not result['memoryUsed'] and not result['memoryCorrectedAndUsed']
    assert not result['failedTaskBackfilled']


def test_actual_failure_observation_retains_complete_logs_and_source_binding(tmp_path) -> None:
    (tmp_path/'hidden.log').write_text('actual failure\n')
    result=verifier_observation('idle',{'passed':False},tmp_path,{'index.js':'source-digest'},b'original session')
    assert result['kind']=='actual-project-verification'
    assert result['logs']=={'hidden':'actual failure\n'}
    assert result['sourceHashes']=={'index.js':'source-digest'}
    assert len(result['sessionDigest'])==64 and len(result['logsDigest'])==64


def test_completed_execution_alone_is_not_learning_improvement() -> None:
    result=continuous_coverage({'status':'completed','stages':[]})
    assert not result['coverageComplete'] and not result['improvementObserved']


@__import__("pytest").mark.parametrize("wrong_read", [False, True])
@__import__("pytest").mark.parametrize("operational_failure", [False, True])
def test_real_pi_verifier_continuation_preserves_original_observations_and_reads_actual_file(tmp_path, wrong_read, operational_failure) -> None:
    import json
    import subprocess
    from pathlib import Path
    from live_acceptance_support import isolated_environment, workspace_pi
    from support import REPO, isolated_run_bun
    project=tmp_path/'project';agent=tmp_path/'agent';project.mkdir();agent.mkdir()
    (project/'index.js').write_text('export const observed = 1;\n')
    (agent/'settings.json').write_text('{"packages":[],"quietStartup":true}')
    (agent/'memory').mkdir();(agent/'memory/settings.json').write_text(json.dumps({'autoMemory':False,'automaticPhases':{'memory':'apply','harness':'apply','agents':'off'}}))
    session=agent/'sessions/continuous/stage-0.jsonl';session.parent.mkdir(parents=True);fixture=Path(__file__).with_name('continuous-verifier-fixture.ts')
    command=[workspace_pi(REPO),'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates','--no-themes','--no-approve',
             '--thinking','off','--tools','read','-e',str(fixture),'-e',str(REPO/'packages/continual-learning/index.ts'),'--model','study-verifier-fixture/deterministic','--session',str(session),'--print','--mode','json']
    env=isolated_environment(tmp_path,agent)
    first=subprocess.run(command+['Inspect actual source'],cwd=project,env=env,capture_output=True,timeout=10)
    assert first.returncode==0,first.stderr.decode()
    original=session.read_bytes();original_rows=[json.loads(line) for line in original.splitlines()]
    (tmp_path/'hidden.log').write_text('Actual verifier outcome: missing required behavior\n')
    observation=verifier_observation('fixture',{'passed':operational_failure},tmp_path,{'index.js':'source-digest'},original,
        **({'inference':{'exitCode':0,'modelErrors':1,'toolBudgetExceeded':True}} if operational_failure else {}))
    file=tmp_path/'verification.json';body=json.dumps(observation,ensure_ascii=False,indent=2);file.write_text(body)
    second=subprocess.run(command+['continue'],cwd=project,env={**env,'PI_STUDY_VERIFIER_FILE':str(file),**({'STUDY_VERIFIER_WRONG_READ':'1'} if wrong_read else {})},capture_output=True,timeout=10)
    assert second.returncode==0,second.stderr.decode()
    assert session.read_bytes().startswith(original)
    rows=[json.loads(line) for line in session.read_text().splitlines()]
    new=rows[len(original_rows):]
    assert any(row.get('customType')=='continuous-verifier-reference' for row in new)
    assert any(row.get('message',{}).get('toolCallId')=='verification' and row['message'].get('isError') is False
               and body in ''.join(part.get('text','') for part in row['message'].get('content',[])) for row in new)
    provider=[row['data'] for row in new if row.get('customType')=='study-verifier-provider']
    assert provider==([{'call':1,'tools':['read']},{'call':2,'tools':['read']},{'call':3,'tools':[]}] if wrong_read else [{'call':1,'tools':['read']},{'call':2,'tools':[]}])
    if wrong_read:
        denied=[row['message'] for row in new if row.get('message',{}).get('toolCallId')=='wrong-source']
        assert len(denied)==1 and denied[0]['isError'] is True
        assert 'export const observed' not in str(denied[0])
    # Validate the actual continuation through the production slice helper.
    records=[row for row in rows if row.get('type')!='session'];(tmp_path/'rows.json').write_text(json.dumps(records))
    result=isolated_run_bun('''import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      const rows=await Bun.file('''+json.dumps(str(tmp_path/'rows.json'))+''').json();console.log(JSON.stringify(currentTaskSlice(rows)));''')
    ids={row.get('id') for row in result['entries']}
    assert {row['id'] for row in original_rows if row.get('type')=='message' and row.get('message',{}).get('role') in ('user','toolResult')}.issubset(ids)
    backlog=[json.loads(line) for line in (agent/'learning/backlog.jsonl').read_text().splitlines()]
    assert len(backlog)>=2 and backlog[-1]['to']>backlog[0]['to']
    assert all(entry['sessionFile']==str(session) for entry in backlog)
    assert not list((agent/'memory').glob('runs/*/*/incremental-learning-dossier.json'))



def full_evidence() -> dict:
    from copy import deepcopy
    import hashlib
    old={'filename':'wrapper.md','revision':'old','content':'limitFunction PromiseLike input contract'}
    new={**old,'revision':'new','content':'limitFunction sync results use Awaited'}
    for entry in (old,new):entry['revision']=hashlib.sha256(entry['content'].encode()).hexdigest()
    ids=['orientation','idle','cancellable-idle','clear-reason','repair-and-sync-wrapper','wrapper-map']
    stages=[]
    other={'id':'unrelated','enabled':True}
    for index,id in enumerate(ids):
        revision='r0' if index<2 else 'r2' if index==2 else 'r3'
        rule={'id':'owned','enabled':index<3};document={'rules':[rule]}
        history=[]
        if index>=2:history.append({'phase':'harness','status':'applied','changes':[{'target':{'root':'project','name':'.pi/harness.json'},'before':{'digest':'d0'},'after':{'digest':'d2'}}]})
        if index>=3:history.append({'phase':'harness','status':'applied','changes':[{'target':{'root':'project','name':'.pi/harness.json'},'before':{'digest':'d2'},'after':{'digest':'d3'}}]})
        arm={'passed':True,'validLearning':True,'inference':{'deliveredMemoryEntries':[{'filename':'wrapper.md','revision':new['revision'] if index==5 else old['revision']}]},
             'harness':{'ownedRevisions':{'owned':revision},'document':document,'documentDigest':'d0' if index<2 else 'd2' if index==2 else 'd3','passed':True,'rules':[rule,deepcopy(other)]},
             'learning':{'memoryEntries':[deepcopy(new if index>=4 else old)],'history':history,'pendingLearningJobs':0}}
        stages.append({'id':id,'validPairInput':True,'arms':{'with-learning':arm,'without-learning':{'passed':index!=1}}})
    feedback={'observation':{'verification':{'passed':False},'sessionDigest':'session','logsDigest':'logs'},'originalObservationsPreserved':True,
              'verifierObserved':True,'taskSourceUnchanged':True,'originalEntryIds':['original-source'],'queuedFailure':{'id':'failure-job','digest':'task-digest'}}
    arm=stages[1]['arms']['with-learning'];arm['verifierFeedback']=feedback;arm['explicitRecovery']={'exitCode':0}
    arm['learning'].update({'completedBacklog':{'failure-job':'receipt-digest'},'attempts':[{'outcome':'completed','receiptDigest':'receipt-digest','receipt':{'batchId':'batch-failure','operations':1,'input':{'backlogId':'failure-job'}}}],
        'dossiers':[{'taskSliceDigest':'task-digest','entryIds':['original-source'],'observations':[{'sessionDigest':'session','logsDigest':'logs'}]}]})
    arm['learning']['history'].append({'id':'failure-change','phase':'memory','status':'applied','batchId':'batch-failure','changes':[{'target':{'root':'private','name':'failure.md'},'before':None,'after':{'digest':'failure-revision'}}]})
    stages[2]['arms']['with-learning']['inference']['deliveredMemoryEntries'].append({'filename':'failure.md','revision':'failure-revision'})
    stages[4]['arms']['with-learning']['memoryAudits']=[{'filename':'wrapper.md','priorRevision':old['revision'],'revision':new['revision'],'passed':True}]
    return {'stages':stages,'status':'completed'}


def test_coverage_requires_consumed_correction_and_source_bound_failure_job() -> None:
    from copy import deepcopy
    report=full_evidence();result=continuous_coverage(report)
    assert result['coverageComplete'] and result['improvementObserved']
    for change in ('stale-delivery','different-name','unrelated-completed-job','missing-original-observation','delete-harness','changed-unrelated-rule','stale-text','unrelated-ack','zero-operations','unrelated-batch','failure-not-consumed','failed-semantic-audit','permissions-only'):
        changed=deepcopy(report)
        arms=[stage['arms']['with-learning'] for stage in changed['stages']]
        if change=='stale-delivery':arms[5]['inference']['deliveredMemoryEntries'][0]['revision']='old'
        elif change=='different-name':arms[4]['learning']['memoryEntries'][0]['filename']='new-name.md'
        elif change=='unrelated-completed-job':arms[1]['learning']['attempts'][0]['receipt']['input']['backlogId']='older-job'
        elif change=='missing-original-observation':arms[1]['learning']['dossiers'][0]['entryIds']=[]
        elif change=='delete-harness':arms[3]['harness']['document']['rules']=[]
        elif change=='changed-unrelated-rule':arms[3]['harness']['rules'][1]['enabled']=False
        elif change=='stale-text':arms[4]['learning']['memoryEntries'][0]['content']='limitFunction only accepts PromiseLike; synchronous functions unsupported. Awaited is a future idea.'
        elif change=='unrelated-ack':arms[1]['learning']['completedBacklog']['failure-job']='unrelated-digest'
        elif change=='zero-operations':arms[1]['learning']['attempts'][0]['receipt']['operations']=0
        elif change=='unrelated-batch':arms[1]['learning']['history'][-1]['batchId']='other-job'
        elif change=='failure-not-consumed':arms[2]['inference']['deliveredMemoryEntries'].pop()
        elif change=='failed-semantic-audit':arms[4]['memoryAudits'][0]['passed']=False
        elif change=='permissions-only':arms[1]['learning']['history'][-1]['changes'][0]['before']={'digest':'failure-revision','mode':420}
        assert not continuous_coverage(changed)['coverageComplete'],change


def test_receipt_batch_is_optional_validated_and_parent_supplied() -> None:
    from support import isolated_run_bun
    result=isolated_run_bun("""import {buildLearningReceipt,isLearningPipelineReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      const screen={memory:false,harness:false,agents:false,reasons:[]};
      const legacy=buildLearningReceipt('automatic',screen,[]);
      const bound=buildLearningReceipt('automatic',screen,[],undefined,'batch_'+'a'.repeat(32));
      console.log(JSON.stringify({legacy:isLearningPipelineReceipt(legacy),batch:bound.batchId,valid:isLearningPipelineReceipt(bound),bad:isLearningPipelineReceipt({...bound,batchId:'arbitrary'})}));""")
    assert result=={'legacy':True,'batch':'batch_'+'a'*32,'valid':True,'bad':False}


def test_operational_failure_with_passing_checks_requires_same_backfill_proof():
    report=full_evidence()
    arm=report['stages'][1]['arms']['with-learning']
    observation=arm['verifierFeedback']['observation']
    observation['verification']={'passed':True}
    assert not continuous_coverage(report)['failedTaskProcessed']
    observation['taskOutcome']={'passed':False,'failures':['model-error','tool-budget-exceeded']}
    assert continuous_coverage(report)['failedTaskProcessed']
    arm['learning']['completedBacklog']['failure-job']='wrong-ack'
    assert not continuous_coverage(report)['failedTaskProcessed']


def test_index_only_protocol_requires_actual_exact_revision_reads() -> None:
    from continuous_project_evidence import continuous_coverage
    report = full_evidence()
    report['protocol'] = {'coverageVersion': 3}
    coverage = continuous_coverage(report)
    assert not coverage['memoryUsed']
    assert not coverage['memoryCorrectedAndUsed']
    for stage in report['stages']:
        inference = stage['arms']['with-learning']['inference']
        inference['observedMemoryReads'] = inference.get('deliveredMemoryEntries', [])
    assert continuous_coverage(report)['memoryUsed']
    assert continuous_coverage(report)['memoryCorrectedAndUsed']
