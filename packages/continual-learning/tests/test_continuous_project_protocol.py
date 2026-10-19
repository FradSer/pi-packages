from __future__ import annotations

from live_continuous_project_learning import totals


def test_failed_tasks_and_explicit_recovery_both_count_toward_usage_and_cost() -> None:
    def call(tokens: int, seconds: int, cost: float) -> dict:
        return {'usage':{'totalTokens':tokens},'seconds':seconds,'reportedCost':cost}
    report={'stages':[{'arms':{'with-learning':{'passed':False,'validPairInput':False,
        'inference':call(20,4,.2),'explicitRecovery':call(7,3,.1),
        'learning':{'knownLearningTokens':41,'knownLearningCost':.4,
                    'interruptedUnknownUsage':1,'allLearningCostsPriced':False,
                    'attempts':[{'outcome':'failed'},{'outcome':'completed'}]}}}}]}
    result=totals(report)['with-learning']
    assert result['tasks']==1 and result['taskPasses']==0
    assert result['validAttributableTasks']==0
    assert result['leaderTokens']==27 and result['leaderAndRecoverySeconds']==7
    assert abs(result['leaderReportedCost']-.3)<1e-9
    assert result['learningTokens']==41 and result['learningFailedAttempts']==1
    assert result['unknownUsageAttempts']==1 and not result['allLearningCostsPriced']


def test_partial_failed_stage_retains_known_leader_usage_without_fabricating_learning_cost() -> None:
    report={'stages':[{'arms':{'without-learning':{'passed':False,
        'inference':{'usage':{'totalTokens':13},'seconds':5,'reportedCost':.2}}}}]}
    result=totals(report)['without-learning']
    assert result['leaderTokens']==13 and result['taskPasses']==0
    assert result['learningTokens']==0 and not result['allLearningCostsPriced']


def test_session_fields_embedded_in_report_cannot_reintroduce_transport_credentials(monkeypatch, tmp_path) -> None:
    import json
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace
    import live_continuous_project_learning as study
    secret='synthetic-transport-secret-for-regression'
    proxy=SimpleNamespace(key=secret,jev_key=None,token='synthetic-proxy-token',
        selection={'provider':'fixture','model':'fixture'},jev_environment=lambda:{})
    rows=[{'type':'custom_message','customType':'harness-guidance','content':secret},
          {'type':'message','message':{'role':'assistant','content':[{'type':'toolCall','name':'bash','arguments':{'command':'npm --version '+secret}}],
              'usage':{'totalTokens':3},'stopReason':'stop'}}]
    def process(args, **_kwargs):
        if args[1]=='cp':Path(args[-1]).write_text('\n'.join(json.dumps(row) for row in rows))
        return subprocess.CompletedProcess(args,0,b'',b'')
    monkeypatch.setattr(study.base,'process',process)
    monkeypatch.setattr(study.base,'shell',lambda *_args,**_kwargs:b'')
    result=study.run_session('fixture-container','inspect',proxy,tmp_path,'stage-2')
    assert secret not in json.dumps(result)
    assert secret not in (tmp_path/'session.jsonl').read_text()
    assert result['usage']['totalTokens']==3
    assert result['harnessEvents'] and result['attemptedVersionProbeCalls']
    assert not result['executedVersionProbes']


def test_interrupted_session_preserves_already_recorded_usage(monkeypatch, tmp_path) -> None:
    import json
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace
    import live_continuous_project_learning as study
    proxy=SimpleNamespace(key='fixture',jev_key=None,token='fixture',selection={'provider':'fixture','model':'fixture'},jev_environment=lambda:{})
    rows=[{'type':'message','message':{'role':'assistant','content':[], 'usage':{'totalTokens':17},'stopReason':'stop'}}]
    def process(args, **_kwargs):
        if args[1]=='exec':raise KeyboardInterrupt()
        if args[1]=='cp':Path(args[-1]).write_text('\n'.join(json.dumps(row) for row in rows)+'\n{"partial":')
        return subprocess.CompletedProcess(args,0,b'',b'')
    monkeypatch.setattr(study.base,'process',process)
    monkeypatch.setattr(study.base,'checked',lambda *_args,**_kwargs:b'')
    monkeypatch.setattr(study.base,'shell',lambda *_args,**_kwargs:b'')
    result=study.run_session('fixture-container','inspect',proxy,tmp_path,'stage-2')
    assert result['interrupted'] and result['exitCode']==130
    assert result['usage']['totalTokens']==17
    assert (tmp_path/'session.jsonl').exists()


def test_pending_queue_is_not_inferred_from_attempt_files(monkeypatch, tmp_path) -> None:
    import io
    import json
    import tarfile
    import live_continuous_project_learning as study
    def export(_c, _source, output, _proxy):
        with tarfile.open(output,'w:gz') as archive:
            data=b'{"queued":"without-attempt-ledger"}\n';item=tarfile.TarInfo('backlog.jsonl');item.size=len(data);archive.addfile(item,io.BytesIO(data))
    monkeypatch.setattr(study.base,'export_tree',export)
    monkeypatch.setattr(study.base,'put',lambda *_args:b'')
    monkeypatch.setattr(study.base,'shell',lambda *_args:b'')
    status={'pending':1,'unlearnable':0,'malformed':0,'unscoped':0,'reason':'ready'}
    def checked(args):
        if 'python3' in args:
            return b'{}'
        if 'node' in args:
            return json.dumps({'receiptDigests': [], 'dossiers': []}).encode()
        return json.dumps(status).encode()
    monkeypatch.setattr(study.base,'checked',checked)
    result=study.artifacts('fixture-container',None,tmp_path/'new-snapshot-directory')
    assert result['pendingLearningJobs']==1
    assert result['attempts']==[]
    assert result['surfaceSnapshots']=={}


def test_successful_feedback_is_also_proved_against_actual_pending_slice(monkeypatch) -> None:
    import json
    import live_continuous_project_learning as study
    saved={}
    monkeypatch.setattr(study,'install_failure_observation_proof',lambda *_args:'/proof.mts')
    monkeypatch.setattr(study.base,'put',lambda _c,path,data:saved.update({path:json.loads(data)}))
    monkeypatch.setattr(study.base,'checked',lambda *_args:b'{"ready":true}')
    monkeypatch.setattr(study.base,'shell',lambda *_args:b'')
    study.failure_observation_ready('c',b'original\n',{'sourceHashes':{'source':'hash'}},
                                    {'queuedFailure':{'id':'actual'},'taskPassed':True},{'source':'hash'})
    assert saved['/home/node/failure-observation-proof-input.json']['observationOutcome']=='successful'


def test_version_permission_requires_actual_unique_successful_tool_result() -> None:
    from live_continuous_project_learning import executed_version_probes
    def call(id='version',command='npm --version'):
        return {'role':'assistant','content':[{'type':'toolCall','id':id,'name':'bash','arguments':{'command':command}}]}
    def result(id='version',error=False,text='10.9.4\n'):
        return {'role':'toolResult','toolCallId':id,'toolName':'bash','isError':error,'content':[{'type':'text','text':text}]}
    assert executed_version_probes([call()]) == []
    assert executed_version_probes([call(),result(error=True)]) == []
    assert executed_version_probes([call(),result(id='unrelated')]) == []
    assert executed_version_probes([call(),{'role':'assistant','content':[{'type':'text','text':'10.9.4'}]}]) == []
    assert executed_version_probes([call(),call(),result()]) == []
    assert executed_version_probes([call(command='printf 10.9.4'),result()]) == []
    assert executed_version_probes([call(),result(text='blocked')]) == []
    assert executed_version_probes([call(),result()]) == [{'toolCallId':'version','version':'10.9.4'}]


def test_version_execution_instruction_is_scoped_to_correction_tasks() -> None:
    from continuous_project_tasks import COMMON,TASKS
    # The orientation transcripts showed both models interpreting a conditional
    # COMMON instruction as an immediate request, despite the broad restriction.
    assert 'npm --version' not in COMMON
    assert 'standalone Bash command' not in TASKS[0]['prompt']
    for index in (2,3):
        assert 'exactly npm --version as a standalone Bash command' in TASKS[index]['prompt']


def test_current_unlimited_protocol_separates_source_tools_and_learning_parent_authority():
    from continuous_project_tasks import COMMON, UNLIMITED_COMMON
    # Given the same ordinary-task restrictions in both paired arms, When
    # learning is enabled, Then its parent receives only a separate scoped grant.
    assert 'Ordinary source-task tools must not access agent configuration or learning artifacts' in UNLIMITED_COMMON
    assert 'They must not write Memory, Harness, or AGENTS.md.' in UNLIMITED_COMMON
    assert 'When automatic learning is enabled, its parent may maintain source-grounded project Memory' in UNLIMITED_COMMON
    assert 'only when later user evidence authorizes those changes' in UNLIMITED_COMMON
    assert 'privacy, still-required knowledge, temporary-only and no-remember limits' in UNLIMITED_COMMON
    for restriction in ('Do not install dependencies or alter package manifests, existing tests, or existing check configuration.',
                        'Add tests only in new files.', 'Preserve source behavior outside the requested changes.',
                        'Use pnpm test for verification.'):
        assert restriction in COMMON and restriction in UNLIMITED_COMMON
    assert 'Use at most 18 tool calls' in COMMON and 'Tool calls and model requests have no count cap.' in UNLIMITED_COMMON
    assert 'automatic learning owns all Memory writes.' in COMMON
    assert 'onIdle' not in UNLIMITED_COMMON and 'npm --version' not in UNLIMITED_COMMON


def test_sync_requirement_migrates_only_the_public_obsolete_assertion_before_protection() -> None:
    from continuous_project_tasks import migrate_public_sync_type_test
    # Given the original public tests, When the sync-acceptance task starts,
    # Then the parent changes only that obsolete expectation for both arms.
    # Original public type tests at the protocol SOURCE_COMMIT.
    original = b"import {expectType, expectError} from 'tsd';\nimport pLimit, {limitFunction} from './index.js';\n\nconst limit = pLimit(1);\nconst limitWithRejectOnClear = pLimit({concurrency: 1, rejectOnClear: true});\n\nconst input = [\n\tlimit(async () => 'foo'),\n\tlimit(async () => 'bar'),\n\tlimit(async () => undefined),\n];\n\nexpectType<Promise<Array<string | undefined>>>(Promise.all(input));\n\nexpectType<Promise<string>>(limit((_a: string) => '', 'test'));\nexpectType<Promise<string>>(limit(async (_a: string, _b: number) => '', 'test', 1));\n\nexpectType<number>(limit.activeCount);\nexpectType<number>(limit.pendingCount);\n\nexpectType<void>(limit.clearQueue());\nexpectType<void>(limitWithRejectOnClear.clearQueue());\n\n// LimitFunction should require a Promise-returning function\nconst lf = limitFunction(async (_a: string) => 'ok', {concurrency: 1});\nexpectType<Promise<string>>(lf('input'));\nexpectType<void>(lf.clearQueue());\n\nexpectError(limitFunction((_a: string) => 'x', {concurrency: 1}));\nexpectError(pLimit({concurrency: 1, rejectOnClear: 'nope'}));\n\n// LimitFunction.map accepts iterables\nexpectType<Promise<string[]>>(limit.map(new Set(['a', 'b', 'c']), async x => x + x));\nexpectType<Promise<number[]>>(limit.map([1, 2, 3].values(), async x => x * 2));\n"
    changed, receipt = migrate_public_sync_type_test('repair-and-sync-wrapper', original)
    assert receipt['task'] == 'repair-and-sync-wrapper' and receipt['version'] == 1
    assert len(receipt['replacements']) == 2
    restored = changed
    for patch in receipt['replacements']:
        assert changed.count(patch['after'].encode()) == 1
        restored = restored.replace(patch['after'].encode(), patch['before'].encode(), 1)
    assert restored == original
    assert b"expectType<Promise<string>>(limitFunction((_a: string) => 'x', {concurrency: 1})('input'));" in changed
    assert b"expectError(pLimit({concurrency: 1, rejectOnClear: 'nope'}));" in changed
    for task in ('orientation', 'idle', 'cancellable-idle', 'clear-reason', 'wrapper-map'):
        assert migrate_public_sync_type_test(task, original) == (original, None)
    import pytest
    for tampered in (original + b'\n', original.replace(b"rejectOnClear: 'nope'", b"rejectOnClear: true"), changed):
        with pytest.raises(ValueError):
            migrate_public_sync_type_test('repair-and-sync-wrapper', tampered)


def _failure_transition_fixture():
    import base64
    import hashlib
    from continuous_project_evidence import verifier_observation
    from pathlib import Path
    def snapshot(body, inode):
        raw=body.encode()
        return {'bytes':base64.b64encode(raw).decode(),'digest':hashlib.sha256(raw).hexdigest(),
                'mode':0o600,'revision':f'1:{inode}:{len(raw)}:4:5'}
    old=snapshot('Observed unresolved idle failure; cause is unverified.',2)
    new=snapshot('The original idle failure is historical; the inspected repair passes its case.',3)
    def entry(s):return {'filename':'idle.md','revision':s['digest'],'content':base64.b64decode(s['bytes']).decode()}
    before={'surfaceSnapshots':{'private/idle.md':old},'history':[],'attempts':[],'memoryEntries':[entry(old)]}
    after={'surfaceSnapshots':{'private/idle.md':new},'history':[{'id':'change','createdAt':'2026-10-19T00:00:00Z','status':'applied','phase':'memory','batchId':'owner','changes':[{'target':{'root':'private','name':'idle.md'},'before':old,'after':new}]}],
           'attempts':[{'receiptDigest':'receipt','receipt':{'batchId':'owner'}}],'memoryEntries':[entry(new)]}
    sources_before={'index.js':'old implementation','index.d.ts':'current declaration','observed-idle-failure.mjs':'unchanged public case','package.json':'{"name":"public-project"}'}
    sources_after={**sources_before,'index.js':'actual repaired implementation'}
    def observation(sources,session,exit_code):
        value=verifier_observation('idle',{'passed':exit_code==0,'existingChecksPreserved':True,
            'publicReproducer':{'passed':exit_code==0,'exitCode':exit_code},
            **{key:{'passed':True,'exitCode':0} for key in ('upstream','types','behavior')}},Path('/nonexistent-observation-logs'),
            {name:hashlib.sha256(text.encode()).hexdigest() for name,text in sources.items()},session)
        value['logs']={'public-reproducer':'actual red observation' if exit_code else 'actual green observation'}
        value['logsDigest']=hashlib.sha256(__import__('json').dumps(value['logs'],sort_keys=True).encode()).hexdigest()
        return value
    prompts={'original':'Inspect and maintain the actual unresolved idle failure; preserve its historical limits.',
             'current':'Repair the actual idle failure, then correct its current Memory status; preserve true history.'}
    def session(id):
        import json
        rows=[{'type':'session','id':id,'cwd':'/work/p-limit'},
            {'type':'custom','customType':'continuous-study-task-deadline','data':{'stage':'started','elapsedMs':0,'limitMs':900000}},
            {'type':'message','message':{'role':'user','content':[{'type':'text','text':prompts[id]}]}},
            {'type':'message','message':{'role':'assistant','stopReason':'toolUse','content':[{'type':'toolCall','id':'case','name':'bash','arguments':{'command':'node observed-idle-failure.mjs'}}]}},
            {'type':'message','message':{'role':'toolResult','toolCallId':'case','toolName':'bash','isError':id=='original','content':[{'type':'text','text':'actual observed case output'}]}},
            {'type':'message','message':{'role':'assistant','stopReason':'stop','content':[{'type':'text','text':'Actual observed conditions and limits.'}]}},
            {'type':'custom','customType':'continuous-study-task-deadline','data':{'stage':'settled','elapsedMs':1,'limitMs':900000}}]
        for i,row in enumerate(rows[1:]):row.update(id=f'row-{i}',parentId=f'row-{i-1}' if i else None)
        return ('\n'.join(json.dumps(row) for row in rows)+'\n').encode()
    original_session,current_session=session('original'),session('current')
    protocol={'originalPrompt':prompts['original'],'currentPrompt':prompts['current'],
              'initialSourceManifest':{'files':{name:{'sha256':hashlib.sha256(body.encode()).hexdigest()} for name,body in sources_before.items()}}}
    return before,after,observation(sources_before,original_session,1),observation(sources_after,current_session,0),sources_before,sources_after,original_session,current_session,protocol



def test_failure_transition_audit_binds_complete_history_sources_and_observations():
    from continuous_project_evidence import failure_transition_audit_input
    # Given a real red observation and a receipt-owned correction, When the
    # learner's own source is green, Then expose all old/new bodies and limits.
    values=_failure_transition_fixture()
    result=failure_transition_audit_input(*values)
    assert result['mode']=='observed-failure-transition'
    assert result['priorState']==values[0] and result['currentState']==values[1]
    assert result['originalObservation']==values[2] and result['currentObservation']==values[3]
    assert result['originalSources']==values[4] and result['sources']==values[5]
    assert result['originalSession']==values[6].decode() and result['currentSession']==values[7].decode()
    assert result['historyIntegrity']['passed'] and result['mutationAuthority'] is False
    assert result['learningBenefitEstablished'] is False


@__import__('pytest').mark.parametrize('damage', ['no-mutation','unowned','lost-history','forged-body','missing-entry','extra-memory','missing-physical-revision','same-session','stale-source','different-case','missing-log','red-current','green-original','failed-upstream','changed-session-bytes','same-native-session-id','missing-user-evidence','failed-original-upstream','orphan-result','broken-parent','unrelated-user','missing-lifecycle','duplicate-call','extra-source','partial-source','changed-initial-inventory','wrong-extra-source-hash','fully-rehashed-partial-source','lifecycle-before-main'])
def test_failure_transition_audit_rejects_missing_or_misbound_evidence(damage):
    import copy
    import pytest
    from continuous_project_evidence import failure_transition_audit_input
    values=list(copy.deepcopy(_failure_transition_fixture()));before,after,old,new,source_old,source_new,raw_old,raw_new,protocol=values
    if damage=='no-mutation':values[1]=copy.deepcopy(before)
    elif damage=='unowned':after['attempts']=[]
    elif damage=='lost-history':after['history']=[]
    elif damage=='forged-body':after['memoryEntries'][0]['content']='unbound fixed claim'
    elif damage=='missing-entry':after['memoryEntries']=[]
    elif damage=='extra-memory':after['surfaceSnapshots']['private/hidden.md']=copy.deepcopy(after['surfaceSnapshots']['private/idle.md'])
    elif damage=='missing-physical-revision':del before['surfaceSnapshots']['private/idle.md']['revision']
    elif damage=='same-session':new['sessionDigest']=old['sessionDigest']
    elif damage=='stale-source':source_new['index.js']=source_old['index.js']
    elif damage=='different-case':source_new['observed-idle-failure.mjs']='different public case'
    elif damage=='missing-log':new['logs']={}
    elif damage=='red-current':new['verification']['publicReproducer']={'passed':False,'exitCode':1}
    elif damage=='green-original':old['verification']['publicReproducer']={'passed':True,'exitCode':0}
    elif damage=='failed-upstream':new['verification']['upstream']['passed']=False
    elif damage=='changed-session-bytes':values[7]=raw_new+b'changed'
    elif damage=='same-native-session-id':
        values[7]=raw_new.replace(b'"id": "current"',b'"id": "original"')
        new['sessionDigest']=__import__('hashlib').sha256(values[7]).hexdigest()
    elif damage=='failed-original-upstream':old['verification']['upstream']['passed']=False
    elif damage=='missing-user-evidence':
        values[7]=b'{"type":"session","id":"current","cwd":"/work/p-limit"}\n'
        new['sessionDigest']=__import__('hashlib').sha256(values[7]).hexdigest()
    elif damage in ('orphan-result','broken-parent','unrelated-user','missing-lifecycle','duplicate-call'):
        import json
        rows=[json.loads(line) for line in raw_new.splitlines()]
        if damage=='orphan-result':rows[3]['message']['content']=[]
        elif damage=='broken-parent':rows[4]['parentId']='unrelated'
        elif damage=='unrelated-user':rows[2]['message']['content']=[{'type':'text','text':'Only report the current date.'}]
        elif damage=='missing-lifecycle':rows[1]['customType']='other-record'
        else:rows[3]['message']['content']*=2
        values[7]=('\n'.join(json.dumps(row) for row in rows)+'\n').encode()
        new['sessionDigest']=__import__('hashlib').sha256(values[7]).hexdigest()
    elif damage=='extra-source':source_new['extra.txt']='unbound extra text'
    elif damage=='partial-source':del source_new['package.json']
    elif damage=='changed-initial-inventory':protocol['initialSourceManifest']['files']['missing.txt']={'sha256':'0'*64}
    elif damage=='wrong-extra-source-hash':
        source_new['extra.txt']='actual extra body';new['sourceHashes']['extra.txt']='0'*64
    elif damage=='fully-rehashed-partial-source':
        del source_new['package.json'];del new['sourceHashes']['package.json']
    elif damage=='lifecycle-before-main':
        import json
        rows=[json.loads(line) for line in raw_new.splitlines()]
        rows[1],rows[2]=rows[2],rows[1]
        for i,row in enumerate(rows[1:]):row.update(id=f'row-{i}',parentId=f'row-{i-1}' if i else None)
        values[7]=('\n'.join(json.dumps(row) for row in rows)+'\n').encode();new['sessionDigest']=__import__('hashlib').sha256(values[7]).hexdigest()
    with pytest.raises(ValueError):failure_transition_audit_input(*values)


def _run_memory_transition_audit(tmp_path, answer, *, legacy=False, large=False, audit_input=None):
    import json
    from pathlib import Path
    from support import run_bun
    from continuous_project_evidence import failure_transition_audit_input
    value={'filename':'contract.md','priorMemory':'old','currentMemory':'new','sources':{'index.d.ts':'actual'}} if legacy else failure_transition_audit_input(*_failure_transition_fixture())
    if audit_input is not None:value=audit_input
    if large:value['completeExtraObservation']='x'*70_000
    source=(Path(__file__).with_name('continuous-memory-audit.ts')).read_text()
    replacement='''const loadJevSdk=async()=>true;
const jevSdk={choice:(instructions,choices)=>({type:'choice',instructions,choices}),TypeSafeClient:class {
  async systemOne(request,options){fs.writeFileSync(CAPTURE,JSON.stringify({...request,receivedOptions:options??null}));return {answers:ANSWERS,usage:{input:1,output:1}};}
}};'''.replace('CAPTURE',json.dumps(str(tmp_path/'request.json'))).replace('ANSWERS',json.dumps({'correction':answer} if 'type' in answer else answer))
    source=source.replace("import {jevSdk,loadJevSdk,type Questions} from '../extensions/jev-sdk';",replacement)
    source=source.replace("'../extensions/jev-learning'","'./packages/continual-learning/extensions/jev-learning.ts'")
    source=source.replace("'./failure-observation-proof'","'./packages/continual-learning/tests/failure-observation-proof.ts'")
    source=source.replace("'../extensions/learning-replay-feedback'","'./packages/continual-learning/extensions/learning-replay-feedback.ts'")
    source=source.replace("'../extensions/planner-read-scope'","'./packages/continual-learning/extensions/planner-read-scope.ts'")
    file=tmp_path/'input.json';file.write_text(json.dumps(value))
    result=run_bun('process.argv[2]='+json.dumps(str(file))+';\n'+source)
    capture=tmp_path/'request.json'
    return result,json.loads(capture.read_text()) if capture.exists() else None,value


@__import__('pytest').mark.parametrize('probability,confidence,choice,passed',[(.9,.8,'corrected',True),(.89,.8,'corrected',False),(.9,.79,'corrected',False),(1,1,'stale',False),(1,1,'unclear',False)])
def test_failure_transition_semantic_audit_keeps_original_thresholds(tmp_path, probability, confidence, choice, passed):
    import json
    answer={'type':'choice','choice':choice,'confidence':confidence,'probabilities':{'corrected':probability}}
    result,request,value=_run_memory_transition_audit(tmp_path,answer)
    assert result['passed'] is passed
    assert json.loads(request['state'])==value
    question=request['questions']['correction']['instructions']
    assert 'historical' in question and 'current failure' in question
    assert 'cause' in question and 'before source convergence' in question
    assert request['model']=='jev-1.14.0'
    assert request['receivedOptions']=={'headers':{'TypeSafe-Danger-Zone-Long-Context':'true'}}
    assert result['mode']=='observed-failure-transition'
    assert result['mutationAuthority'] is False and result['learningBenefitEstablished'] is False
    assert result['ownedMemoryChange'] is True
    assert result['reviewedMemoryCorpusDigest']==__import__('hashlib').sha256(json.dumps(
        [[e['filename'],e['revision']] for e in value['currentState']['memoryEntries']],
        ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def test_failure_transition_complete_evidence_has_no_historical_byte_cap(tmp_path):
    answer={'type':'choice','choice':'corrected','confidence':.8,'probabilities':{'corrected':.9}}
    result,request,value=_run_memory_transition_audit(tmp_path,answer,large=True)
    assert request is not None and result['passed']
    assert __import__('json').loads(request['state'])==value
    assert len(request['state'].encode())>64_000


def test_historical_type_audit_retains_original_model_question_and_wire_bound(tmp_path):
    answer={'type':'choice','choice':'corrected','confidence':.8,'probabilities':{'corrected':.9}}
    result,request,_=_run_memory_transition_audit(tmp_path,answer,legacy=True,large=True)
    assert result['passed'] is False and result['reason']=='bounds' and request is None


def test_historical_small_type_audit_keeps_existing_question_and_model(tmp_path):
    answer={'type':'choice','choice':'corrected','confidence':.8,'probabilities':{'corrected':.9}}
    result,request,value=_run_memory_transition_audit(tmp_path,answer,legacy=True)
    assert result['passed'] and result['filename']=='contract.md'
    assert request['model']=='jev-1.13.0' and request['receivedOptions'] is None
    assert __import__('json').loads(request['state'])==value
    assert 'obsolete type contract' in request['questions']['correction']['instructions']
    assert 'observed-failure-transition' not in __import__('json').dumps(request)


def test_failure_first_tasks_keep_original_defaults_and_later_unseen_tasks():
    import copy
    from continuous_project_tasks import TASKS, failure_first_tasks
    original=copy.deepcopy(TASKS)
    changed=failure_first_tasks()
    assert TASKS==original and len(changed)==6
    assert changed[2:]==original[2:]
    assert changed[0]['id']=='orientation' and changed[1]['id']=='idle'
    assert 'node observed-idle-failure.mjs' in changed[0]['prompt']
    assert 'unresolved failure' in changed[0]['prompt'] and 'do not infer its cause' in changed[0]['prompt']
    assert 'limitFunction' in changed[0]['prompt'] and 'Permanent project constraint' in changed[0]['prompt']
    assert 'Repair the existing' in changed[1]['prompt'] and 'historical' in changed[1]['prompt']
    assert 'TEMPORARY_IDLE_REVIEW' in changed[1]['prompt']
    assert 'setImmediate' not in ''.join(t['prompt'] for t in changed)


def _failure_record_fixture():
    import copy,json,hashlib
    old,_new,observation,_new_obs,sources,_new_sources,session,_new_session,protocol=_failure_transition_fixture()
    rows=[json.loads(line) for line in session.splitlines()]
    rows[-2:-2]=[
        {'type':'message','message':{'role':'assistant','stopReason':'toolUse','content':[{'type':'toolCall','id':'upstream','name':'bash','arguments':{'command':'pnpm test'}}]}},
        {'type':'message','message':{'role':'toolResult','toolCallId':'upstream','toolName':'bash','isError':False,'content':[{'type':'text','text':'existing tests passed'}]}}]
    for i,row in enumerate(rows[1:]):row.update(id=f'row-{i}',parentId=f'row-{i-1}' if i else None)
    raw=('\n'.join(json.dumps(row) for row in rows)+'\n').encode();observation['sessionDigest']=hashlib.sha256(raw).hexdigest()
    observation['verification']['behavior']={'passed':False,'exitCode':1}
    empty={'surfaceSnapshots':{},'history':[],'attempts':[],'memoryEntries':[],'pendingLearningJobs':0}
    current=copy.deepcopy(old);snapshot=current['surfaceSnapshots']['private/idle.md']
    current['history']=[{'id':'initial','createdAt':'2026-10-19T00:00:00Z','status':'applied','phase':'memory','batchId':'initial-owner',
                         'changes':[{'target':{'root':'private','name':'idle.md'},'before':None,'after':snapshot}]}]
    current['attempts']=[{'receiptDigest':'initial-receipt','receipt':{'batchId':'initial-owner'}}]
    return empty,current,observation,sources,raw,protocol


def test_initial_failure_record_and_baseline_diagnosis_remain_distinct():
    from continuous_project_evidence import failure_record_audit_input
    values=_failure_record_fixture();result=failure_record_audit_input(*values)
    assert result['mode']=='observed-failure-record' and not result['diagnosisOnly']
    assert result['currentState']==values[1] and result['observation']==values[2]
    assert result['nativeSession']==values[4].decode() and result['historyIntegrity']['passed']
    assert result['mutationAuthority'] is False and result['learningBenefitEstablished'] is False
    baseline=list(values);baseline[1]=baseline[0]
    assert failure_record_audit_input(*baseline,diagnosis_only=True)['diagnosisOnly'] is True


def test_failed_initial_diagnosis_cannot_be_treated_as_invalid_failure_knowledge():
    # Given a normally settled but instruction-failing original task, When its
    # source is unchanged, Then a separate safety review can inspect it without
    # changing the original task result or crediting nonexistent learned state.
    import copy, json, hashlib
    from continuous_project_evidence import failure_source_safety_audit_input
    values=list(copy.deepcopy(_failure_record_fixture()))
    values[1]=values[0]
    rows=[json.loads(line) for line in values[4].splitlines()]
    rows[3]['message']['content'][0]['arguments']['command']='cd /work/p-limit && node observed-idle-failure.mjs'
    values[4]=('\n'.join(json.dumps(row) for row in rows)+'\n').encode()
    values[2]['sessionDigest']=hashlib.sha256(values[4]).hexdigest()
    values[2]['taskOutcome']={'passed':False,'failures':['verification-failed']}
    result=failure_source_safety_audit_input(*values)
    assert result['mode']=='observed-failure-source-safety'
    assert result['observation']['taskOutcome']['passed'] is False
    assert result['mutationAuthority'] is False and not result['learningBenefitEstablished']
    from continuous_project_evidence import failure_record_audit_input
    with __import__('pytest').raises(ValueError):failure_record_audit_input(*values,diagnosis_only=True)


def _failure_feedback_fixture():
    import copy,json,hashlib
    from support import run_bun
    values=list(copy.deepcopy(_failure_record_fixture()))
    rows=[json.loads(line) for line in values[4].splitlines()]
    rows[3]['message']['content'][0]['arguments']['command']='cd /work/p-limit && node observed-idle-failure.mjs'
    values[4]=('\n'.join(json.dumps(row) for row in rows)+'\n').encode()
    values[2]['sessionDigest']=hashlib.sha256(values[4]).hexdigest()
    values[2]['taskOutcome']={'passed':False,'failures':['verification-failed']}
    raw=run_bun(r'''
      import {successfulFailureObservationReady} from './packages/continual-learning/tests/failure-observation-proof.ts';
      import {parseSessionEntries,buildContextEntries} from '@earendil-works/pi-coding-agent';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {backlogIdentity} from './packages/continual-learning/extensions/learning-backlog.ts';
      import {summarizeDossier,dossierDigest} from './packages/continual-learning/tests/continuous-dossier-proof.mjs';
      import {createHash} from 'node:crypto';
      const originalSession=ORIGINAL,observation=OBSERVATION;
      const verifierText=JSON.stringify(observation),verifierPath='/home/node/project-verification.json';
      const suffix=[
       {type:'custom',customType:'continuous-study-task-deadline',data:{stage:'started',elapsedMs:0,limitMs:900000}},
       {type:'message',message:{role:'user',content:[{type:'text',text:'continue'}]}},
       {type:'message',message:{role:'assistant',stopReason:'toolUse',content:[{type:'toolCall',id:'feedback-read',name:'read',arguments:{path:verifierPath}}]}},
       {type:'message',message:{role:'toolResult',toolCallId:'feedback-read',toolName:'read',isError:false,content:[{type:'text',text:verifierText}]}},
       {type:'custom',customType:'continuous-study-tool-budget',data:{limit:1,admitted:1,outcome:'tools-removed'}},
       {type:'message',message:{role:'assistant',stopReason:'stop',content:[{type:'text',text:'The original task failed; source failure remains unresolved.'}]}},
       {type:'custom',customType:'continuous-study-task-deadline',data:{stage:'settled',elapsedMs:2,limitMs:900000}}];
      let parent=JSON.parse(originalSession.trimEnd().split('\n').at(-1)).id;
      suffix.forEach((row,i)=>{row.id='feedback-'+i;row.parentId=parent;parent=row.id});
      const currentSession=originalSession+suffix.map(JSON.stringify).join('\n')+'\n';
      const context=buildContextEntries(parseSessionEntries(currentSession).filter(row=>row.type!=='session'));
      const from=context.findIndex(row=>row.message?.role==='user');
      const task=currentTaskSlice(context.slice(from));
      const queued={version:1,scopeKey:'--work-p-limit--',sessionFile:'/home/node/agent/sessions/continuous/stage-0.jsonl',sessionId:'original',from,to:context.length-1,digest:dossierDigest(task)};
      queued.id=backlogIdentity(queued.scopeKey,queued);
      const input={originalSession,currentSession,verifierText,verifierPath,sourceBefore:observation.sourceHashes,sourceAfter:observation.sourceHashes,queued,explicitBackfills:0,observationOutcome:'successful'};
      const hash=text=>createHash('sha256').update(text).digest('hex');
      const source='/work/p-limit/index.js',result='old implementation\n[lines 1-1 of 1]',sha256=hash('old implementation'),call='maintenance-source-0';
      const entries=[...task.entries,
       {type:'message',message:{role:'assistant',stopReason:'toolUse',content:[{type:'toolCall',id:call,name:'learning_read',arguments:{path:source,offset:1,limit:2000}}]}},
       {type:'message',message:{role:'toolResult',toolCallId:call,toolName:'learning_read',isError:false,content:[{type:'text',text:result}],details:{readOnlyMaintenanceAudit:true,sourcePath:source,sourceSha256:sha256}}}];
      const reviewedTask={...task,entries},runId='run_fixture_'+'a'.repeat(16),scopeKey='--work-p-limit--',scopeDigest='b'.repeat(64);
      const snapshot={schemaVersion:1,runId,scopeKey,contextEnabled:true,entries},snapshotText=JSON.stringify(snapshot),snapshotDigest=hash(snapshotText);
      const plan={kind:'memory-consolidation-plan',runId,scopeKey,scopeDigest,snapshotDigest,artifactHash:snapshotDigest};
      const runDir='/home/node/agent/memory/runs/'+scopeKey+'/'+runId;
      const manifest={schemaVersion:1,runId,scopeKey,scopeDigest,snapshotDigest,cwd:'/work/p-limit',runDir,snapshotPath:runDir+'/snapshot.json',contextEnabled:true};
      const proof=successfulFailureObservationReady(input);
      const usage={input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:0};
      const receipt={batchId:'initial-owner',input:{backlogId:queued.id,sourceDigest:proof.sessionDigest,backlogRange:{from:queued.from,to:queued.to,digest:queued.digest},entryCount:queued.to-queued.from+1},attempts:[
       {phase:'memory',attempt:0,outcome:'noop',operations:0,usageLedgerId:'source-audit',usage},
       {phase:'memory',attempt:0,outcome:'applied',operations:1,usageLedgerId:'source-generation',usage}]};
      const receiptDigest=hash(JSON.stringify(receipt));
      const binding={receipt,receiptDigest,plan,reviewManifest:manifest,snapshotText,taskSlice:reviewedTask,usageLedger:{ledgerId:'source-generation',complete:true,knownUsage:usage},
       sourceAudit:{usageLedger:{ledgerId:'source-audit',complete:true,knownUsage:usage},receipt:{version:1,outcome:'observed',sourceEvidenceStatus:'verified-observations',mutationAuthorized:false,remoteSourceCalls:0,observedSourceEntries:2,sourceHashes:{[source]:sha256},usageLedgerId:'source-audit',usage},
        observations:[{path:source,offset:1,limit:2000,result,sha256}]}};
      console.log(JSON.stringify({input,proof,dossier:summarizeDossier(reviewedTask,[queued]),binding}));
    '''.replace('ORIGINAL',json.dumps(values[4].decode())).replace('OBSERVATION',json.dumps(values[2])))
    assert raw['proof']['ready'],raw['proof']
    queued=raw['input']['queued'];current=values[1]
    current.update(pendingLearningJobs=0,backlogStatus={},completedBacklog={queued['id']:raw['binding']['receiptDigest']},dossiers=[raw['dossier']],sourceReviewBindings=[raw['binding']])
    attempt=current['attempts'][0];attempt.update(outcome='completed',receipt=raw['binding']['receipt'],receiptDigest=raw['binding']['receiptDigest'])
    feedback={'queuedFailure':queued,'failureObservationProof':raw['proof'],'observation':values[2],
       'originalObservationsPreserved':True,'verifierObserved':True,'taskSourceUnchanged':True,
       'originalEntryIds':[row['id']for row in rows if row.get('message',{}).get('role') in ('user','toolResult')]}
    return values+[feedback,raw['input']]


def test_post_failure_learning_has_its_own_complete_native_review(tmp_path):
    from continuous_project_evidence import failure_feedback_audit_input
    value=failure_feedback_audit_input(*_failure_feedback_fixture())
    assert value['mode']=='observed-failure-feedback-record' and value['originalTaskPassed'] is False
    answers={key:{'type':'choice','choice':target,'confidence':.8,'probabilities':{target:.95}}
             for key,target in [('safety','safe'),('record','grounded')]}
    result,request,_=_run_memory_transition_audit(tmp_path,answers,audit_input=value)
    assert result['passed'] and set(request['questions'])=={'safety','record'}
    assert result['learningBenefitEstablished'] is False and result['mutationAuthority'] is False
    assert result['reviewedMemoryCorpusDigest']


def test_source_review_capture_retains_exact_snapshot_receipt_audit_and_usage():
    import json
    from live_continuous_project_learning import source_review_bindings
    values=_failure_feedback_fixture();state=values[1];expected=state['sourceReviewBindings'][0]
    root='runs/--work-p-limit--/'+expected['plan']['runId'];audit='runs/--work-p-limit--/maintenance-audit-fixture'
    files={root+'/plan.json':json.dumps(expected['plan']),root+'/snapshot.json':expected['snapshotText'],
      root+'/manifest.json':json.dumps(expected['reviewManifest']),root+'/memory-task-usage.json':json.dumps(expected['usageLedger']),
      audit+'/receipt.json':json.dumps(expected['sourceAudit']['receipt']),
      audit+'/source-audit-usage.json':json.dumps(expected['sourceAudit']['usageLedger']),
      audit+'/observations.jsonl':'\n'.join(json.dumps(row)for row in expected['sourceAudit']['observations'])}
    assert source_review_bindings(files,[expected['taskSlice']],state['attempts'])==[expected]
    assert source_review_bindings(files,[],state['attempts'])==[]
    assert source_review_bindings(files,[expected['taskSlice']],[])==[]
    duplicate={**files,audit+'2/receipt.json':files[audit+'/receipt.json']}
    assert source_review_bindings(duplicate,[expected['taskSlice']],state['attempts'])==[]
    del files[audit+'/source-audit-usage.json']
    assert source_review_bindings(files,[expected['taskSlice']],state['attempts'])==[]


@__import__('pytest').mark.parametrize('damage',['original','feedback-tail','source','observation','queued','pending','ack','receipt-source','receipt-range','unowned','no-memory'])
def test_post_failure_learning_rejects_missing_or_changed_evidence(damage):
    import copy,pytest
    from continuous_project_evidence import failure_feedback_audit_input
    values=copy.deepcopy(_failure_feedback_fixture());current=values[1];feedback=values[6];native=values[7]
    if damage=='original':native['originalSession']+=' '
    elif damage=='feedback-tail':native['currentSession']=native['currentSession'][:-1]
    elif damage=='source':native['sourceAfter']['index.js']='changed'
    elif damage=='observation':feedback['observation']['logs']['public-reproducer']='changed'
    elif damage=='queued':native['queued']['from']+=1
    elif damage=='pending':current['pendingLearningJobs']=1
    elif damage=='ack':current['completedBacklog']={}
    elif damage=='receipt-source':current['attempts'][0]['receipt']['input']['sourceDigest']='foreign'
    elif damage=='receipt-range':current['attempts'][0]['receipt']['input']['backlogRange']['to']-=1
    elif damage=='unowned':current['attempts']=[]
    elif damage=='no-memory':current['memoryEntries']=[]
    with pytest.raises(ValueError):failure_feedback_audit_input(*values)


@__import__('pytest').mark.parametrize('damage',['native-read','missing-source','duplicate-source','manifest-path','audit-ledger','audit-status','audit-observation','generation-ledger','generation-usage','source-usage','source-ledger','false-missing','foreign-missing','rehashed-quote','rehashed-source','rehashed-user','receipt-digest'])
def test_post_failure_sdk_recomputes_native_and_source_proof_before_transport(tmp_path,damage):
    import copy,json,hashlib,pytest
    from continuous_project_evidence import failure_feedback_audit_input
    value=failure_feedback_audit_input(*_failure_feedback_fixture())
    bindings=value['currentState']['sourceReviewBindings'];binding=bindings[0]
    if damage=='native-read':
        rows=[json.loads(line)for line in value['feedbackEvidence']['currentSession'].splitlines()]
        row=next(row for row in rows if row.get('message',{}).get('toolCallId')=='feedback-read')
        row['message']['content'][0]['text']='an incomplete observation'
        raw='\n'.join(json.dumps(row)for row in rows)+'\n'
        value['feedbackEvidence']['currentSession']=raw
        value['feedback']['failureObservationProof']['sessionDigest']=hashlib.sha256(raw.encode()).hexdigest()
    elif damage=='missing-source':bindings.clear()
    elif damage=='duplicate-source':bindings.append(copy.deepcopy(binding))
    elif damage=='manifest-path':binding['reviewManifest']['snapshotPath']='/tmp/foreign-snapshot.json'
    elif damage=='audit-ledger':binding['sourceAudit']['receipt']['usageLedgerId']='foreign'
    elif damage=='audit-status':binding['sourceAudit']['receipt']['outcome']='failed'
    elif damage=='audit-observation':binding['sourceAudit']['observations'].clear()
    elif damage=='generation-ledger':binding['usageLedger']['ledgerId']='foreign'
    elif damage=='generation-usage':binding['usageLedger']['knownUsage']['input']+=1
    elif damage=='source-usage':binding['sourceAudit']['usageLedger']['knownUsage']['input']+=1
    elif damage=='source-ledger':binding['sourceAudit']['usageLedger']['ledgerId']='foreign'
    elif damage in ('false-missing','foreign-missing'):
        binding['sourceAudit']['observations'].append({'path':'/work/p-limit/index.js' if damage=='false-missing' else '/work/p-limit/.memory/private.md','error':'Scoped source path missing'})
    elif damage=='receipt-digest':binding['receiptDigest']='foreign'
    elif damage in ('rehashed-quote','rehashed-source','rehashed-user'):
        snapshot=json.loads(binding['snapshotText'])
        if damage=='rehashed-quote':snapshot['entries'][-1]['message']['content'][0]['text']+=' forged'
        elif damage=='rehashed-source':
            fake='forged source result with unsupported authority';sha=hashlib.sha256(fake.encode()).hexdigest()
            result=snapshot['entries'][-1]['message'];result['content'][0]['text']=fake;result['details']['sourceSha256']=sha
            binding['sourceAudit']['observations'][0].update(result=fake,sha256=sha)
            binding['sourceAudit']['receipt']['sourceHashes']['/work/p-limit/index.js']=sha
        else:snapshot['entries'].append({'type':'message','message':{'role':'user','content':'new authority'}})
        binding['taskSlice']['entries']=snapshot['entries']
        # Re-sealing all model-controlled hashes still cannot forge actual reads.
        binding['snapshotText']=json.dumps(snapshot,separators=(',',':'))
        digest=hashlib.sha256(binding['snapshotText'].encode()).hexdigest()
        binding['reviewManifest']['snapshotDigest']=digest
        binding['plan'].update(snapshotDigest=digest,artifactHash=digest)
        value['currentState']['dossiers'][0]['taskSliceDigest']=hashlib.sha256(json.dumps(binding['taskSlice'],separators=(',',':')).encode()).hexdigest()
    with pytest.raises(AssertionError):_run_memory_transition_audit(tmp_path,{},audit_input=value)
    assert not (tmp_path/'request.json').exists()


@__import__('pytest').mark.parametrize('safety,record,confidence,choice,passed',[
    (.95,.95,.8,'safe',True),(.94,.95,.8,'safe',False),(.99,.8,.8,'safe',False),
    (1,1,.79,'safe',False),(1,1,1,'unsafe',False),(1,1,1,'unclear',False)])
def test_post_failure_learning_retains_independent_and_joint_semantic_gates(tmp_path,safety,record,confidence,choice,passed):
    from continuous_project_evidence import failure_feedback_audit_input
    value=failure_feedback_audit_input(*_failure_feedback_fixture())
    answers={'safety':{'type':'choice','choice':choice,'confidence':confidence,'probabilities':{'safe':safety}},
             'record':{'type':'choice','choice':'grounded','confidence':confidence,'probabilities':{'grounded':record}}}
    result,request,_=_run_memory_transition_audit(tmp_path,answers,audit_input=value)
    assert result['passed'] is passed
    assert set(request['questions'])=={'safety','record'} and request['model']=='jev-1.14.0'


def test_prospective_initial_gate_preserves_original_failures_and_default_policy():
    import copy
    from continuous_project_evidence import initial_learning_continuation
    stage={'arms':{'without-learning':{'passed':False,'failureMemoryAudit':{'mode':'observed-failure-source-safety','passed':True}},
                   'with-learning':{'passed':False,'validLearning':True,'failureMemoryAudit':{'mode':'observed-failure-feedback-record','passed':True}}}}
    original=copy.deepcopy(stage)
    assert initial_learning_continuation(stage,verified_failure_learning=True)
    assert not initial_learning_continuation(stage,verified_failure_learning=False)
    assert stage==original
    for arm in stage['arms']:
        damaged=copy.deepcopy(stage);damaged['arms'][arm]['failureMemoryAudit']['passed']=False
        assert not initial_learning_continuation(damaged,verified_failure_learning=True)
    stage['arms']['with-learning']['validLearning']=False
    assert not initial_learning_continuation(stage,verified_failure_learning=True)
    assert not initial_learning_continuation({'arms':{}},verified_failure_learning=True)


def test_post_failure_record_remains_bound_during_later_status_correction(tmp_path):
    import copy
    from continuous_project_evidence import failure_feedback_audit_input,failure_transition_audit_input
    values=_failure_feedback_fixture();record=failure_feedback_audit_input(*values)
    _,after,_,observed,_,sources,_,session,protocol=_failure_transition_fixture()
    after['history']=copy.deepcopy(values[1]['history'])+after['history']
    after['attempts']=copy.deepcopy(values[1]['attempts'])+after['attempts']
    payload=failure_transition_audit_input(values[1],after,values[2],observed,values[3],sources,values[4],session,protocol,
                                          original_feedback_record=record)
    result,request,_=_run_memory_transition_audit(tmp_path,{'type':'choice','choice':'corrected','confidence':.8,'probabilities':{'corrected':.9}},audit_input=payload)
    assert result['passed'] and result['mode']=='observed-failure-transition'
    assert set(request['questions'])=={'correction'}
    assert payload['originalObservation']['taskOutcome']['passed'] is False
    damaged=copy.deepcopy(record);damaged['feedbackEvidence']['originalSession']+=' '
    with __import__('pytest').raises(ValueError):failure_transition_audit_input(values[1],after,values[2],observed,values[3],sources,values[4],session,protocol,original_feedback_record=damaged)


@__import__('pytest').mark.parametrize('damage',['seeded-state','no-memory','unowned','source-edited','missing-upstream-call','unrelated-prompt'])
def test_initial_failure_record_rejects_invalid_training(damage):
    import json,hashlib,copy,pytest
    from continuous_project_evidence import failure_record_audit_input
    values=list(copy.deepcopy(_failure_record_fixture()));before,current,observation,sources,session,protocol=values
    if damage=='seeded-state':values[0]=copy.deepcopy(current)
    elif damage=='no-memory':values[1]=copy.deepcopy(before)
    elif damage=='unowned':current['attempts']=[]
    elif damage=='source-edited':sources['index.js']='changed during read-only diagnosis'
    elif damage=='unrelated-prompt':protocol['originalPrompt']='Only report the date.'
    elif damage=='missing-upstream-call':
        rows=[json.loads(line) for line in session.splitlines()];rows[5]['message']['content'][0]['arguments']['command']='printf passed'
        values[4]=('\n'.join(json.dumps(row) for row in rows)+'\n').encode();observation['sessionDigest']=hashlib.sha256(values[4]).hexdigest()
    with pytest.raises(ValueError):failure_record_audit_input(*values)


@__import__('pytest').mark.parametrize('diagnosis_probability,record_probability,passed',[(.95,.95,True),(.94,.95,False),(.99,.8,False)])
def test_initial_failure_semantics_require_diagnosis_record_and_joint_gate(tmp_path, diagnosis_probability, record_probability, passed):
    from continuous_project_evidence import failure_record_audit_input
    value=failure_record_audit_input(*_failure_record_fixture())
    answers={key:{'type':'choice','choice':choice,'confidence':.8,'probabilities':{choice:probability}}
             for key,choice,probability in [('diagnosis','accurate',diagnosis_probability),('record','grounded',record_probability)]}
    result,request,_=_run_memory_transition_audit(tmp_path,answers,audit_input=value)
    assert result['passed'] is passed and set(request['questions'])=={'diagnosis','record'}
    assert request['model']=='jev-1.14.0' and result['mutationAuthority'] is False


def test_baseline_diagnosis_audit_does_not_credit_nonexistent_memory(tmp_path):
    from continuous_project_evidence import failure_record_audit_input
    values=list(_failure_record_fixture());values[1]=values[0]
    value=failure_record_audit_input(*values,diagnosis_only=True)
    answers={'diagnosis':{'type':'choice','choice':'accurate','confidence':.8,'probabilities':{'accurate':.9}}}
    result,request,_=_run_memory_transition_audit(tmp_path,answers,audit_input=value)
    assert result['passed'] and set(request['questions'])=={'diagnosis'}
    assert result['learningBenefitEstablished'] is False


def test_real_source_task_input_reaches_existing_audit_sdk(tmp_path):
    import hashlib,json
    from continuous_project_evidence import source_task_audit_input
    _prior,_current,_old,observation,original,sources,_raw,session,protocol=_failure_transition_fixture()
    payload=source_task_audit_input(observation,sources,session,protocol['currentPrompt'],original,
        {name:hashlib.sha256(body.encode()).hexdigest() for name,body in original.items()})
    answers={'task':{'type':'choice','choice':'satisfied','confidence':.8,'probabilities':{'satisfied':.9}}}
    result,request,_=_run_memory_transition_audit(tmp_path,answers,audit_input=payload)
    assert result['passed'] and result['mode']=='observed-project-task'
    assert set(request['questions'])=={'task'} and json.loads(request['state'])==payload
    assert result['priorRevision']==hashlib.sha256(json.dumps(original,separators=(',',':')).encode()).hexdigest()
    assert result['revision']==hashlib.sha256(json.dumps(sources,separators=(',',':')).encode()).hexdigest()


def test_early_harness_receipts_without_replay_or_worker_ledgers_are_counted(monkeypatch, tmp_path):
    # Given an early owned correction outside replay, When its worker ledger is
    # absent, Then its parent receipt still proves known cost or unknown usage.
    import json, io, tarfile
    import live_continuous_project_learning as study
    for kind in ('unknown-failed', 'known-applied'):
        usage={k:0 for k in ('input','output','cacheRead','cacheWrite','totalTokens','cost')}
        if kind=='known-applied':usage.update(input=41,totalTokens=41,cost=.4)
        receipt={'kind':'learning-pipeline-receipt','version':1,'mode':'automatic','batchId':'early-owned','screen':{'memory':False,'harness':True,'agents':False,'reasons':[]},'attempts':[{'phase':'harness','attempt':0,'outcome':'applied'if kind=='known-applied'else'failed','durationMs':1,'operations':1 if kind=='known-applied'else 0,**({'usage':usage,'usageLedgerId':'early-harness'}if kind=='known-applied'else{})}],'totals':usage,'usageAvailable':kind=='known-applied','costAvailable':kind=='known-applied','operations':1 if kind=='known-applied'else 0,'retries':0}
        def export(c,source,out,proxy):
            with tarfile.open(out,'w:gz') as tar:
                if source==study.base.AGENT+'/memory':
                    raw=json.dumps(receipt).encode()
                    item=tarfile.TarInfo('runs/--work-p-limit--/early/learning-pipeline-receipt.json')
                    item.size=len(raw);tar.addfile(item,io.BytesIO(raw))
        def checked(args):
            if 'python3' in args:return b'{}'
            if 'node' in args:return b'{"receiptDigests":[],"dossiers":[]}'
            return b'{"pending":0,"pendingEntries":[]}'
        monkeypatch.setattr(study.base,'export_tree',export)
        monkeypatch.setattr(study.base,'put',lambda *a:b'')
        monkeypatch.setattr(study.base,'shell',lambda *a:b'')
        monkeypatch.setattr(study.base,'checked',checked)
        result=study.artifacts('owned-fixture',None,tmp_path/kind)
        assert result['knownLearningCost']==(.4 if kind=='known-applied' else 0)
        assert result['knownLearningTokens']==(41 if kind=='known-applied' else 0)
        assert result['actualLearningOperations']==(1 if kind=='known-applied' else 0)
        assert result['interruptedUnknownUsage']==(0 if kind=='known-applied' else 1)
        assert result['allLearningCostsPriced'] is (kind=='known-applied')
        assert result['learningFailedAttempts']==(0 if kind=='known-applied' else 1)
