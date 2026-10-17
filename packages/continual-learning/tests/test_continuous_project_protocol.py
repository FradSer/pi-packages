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
