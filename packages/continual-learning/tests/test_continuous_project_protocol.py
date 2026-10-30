from __future__ import annotations

from live_continuous_project_learning import totals


def test_frozen_initialization_proof_uses_owned_container_runtime(monkeypatch):
    # Given a frozen host without Pi dependencies, When checking native evidence,
    # Then run the unchanged shared proof in the caller-owned Pi runtime.
    import json,pytest
    import live_continuous_project_learning as study
    calls=[]
    def checked(args,**kwargs):
        if '--version' in args:return b'1.4.0\n'
        calls.append((args,kwargs))
        return b'{"ready":true,"mutationAuthority":false,"learningBenefitEstablished":false}\n' if 'tsx' in args else b''
    monkeypatch.setattr(study.base,'checked',checked)
    result=study.native_initialization_proof('owned','automaticHarnessPolicyProof',{'owner':{'container':'owned'}},{},{})
    assert result['ready'] and result['learningBenefitEstablished'] is False
    assert len(calls)==4 and all(args[2 if args[1]=='exec' and args[2]!='-i' else 3]=='owned' for args,_ in calls)
    create,module,check,cleanup=[args for args,_ in calls]
    assert 'O_EXCL' in create[-2] and 'O_NOFOLLOW' in create[-2] and '0o600' in create[-2]
    payload=json.loads(calls[0][1]['data']);assert payload=={'input':{'owner':{'container':'owned'}},'prior':{},'current':{},'runtimeVersion':'1.4.0'}
    assert '/home/node/continuous-command-proof.mts' in calls[1][1]['data'].decode() and 'automaticHarnessPolicyProof' in calls[1][1]['data'].decode()
    assert check[-1]==module[-1] and check[-1].endswith('.mts')
    assert cleanup[-3]=='--' and cleanup[-2:]==[create[-1],module[-1]]
    for name,owner in [('unknown','owned'),('automaticHarnessPolicyProof','foreign')]:
        with pytest.raises(ValueError):study.native_initialization_proof('owned',name,{'owner':{'container':owner}},{},{})
    assert len(calls)==4


def test_owned_container_proof_failure_cleans_only_created_inputs(monkeypatch):
    import pytest
    import live_continuous_project_learning as study
    for failure in ('module-create','execution','invalid-output'):
        calls=[]
        def checked(args,**kwargs):
            if '--version' in args:return b'1.3.0\n'
            calls.append(args)
            if failure=='module-create' and len(calls)==2:raise RuntimeError('exclusive create refused')
            if 'tsx' in args:
                if failure=='execution':raise RuntimeError('native proof refused')
                return b'not-json'
            return b''
        monkeypatch.setattr(study.base,'checked',checked)
        with pytest.raises((RuntimeError,ValueError)):
            study.native_initialization_proof('owned','commandMemoryCorpusProof',{'owner':{'container':'owned'}},{},{})
        cleanup=calls[-1]
        assert cleanup[:6]==['docker','exec','owned','rm','-f','--']
        assert cleanup[6]==calls[0][-1]
        assert cleanup[7:]==([] if failure=='module-create' else [calls[1][-1]])


def test_owned_proof_create_removes_partial_files_and_preserves_existing(monkeypatch,tmp_path):
    import subprocess,sys,pytest
    import live_continuous_project_learning as study
    scripts=[]
    def checked(args,**kwargs):
        if '--version' in args:return b'1.3.0\n'
        scripts.append(args[-2])
        raise RuntimeError('Capture create only')
    monkeypatch.setattr(study.base,'checked',checked)
    with pytest.raises(RuntimeError):
        study.native_initialization_proof('owned','automaticHarnessPolicyProof',{'owner':{'container':'owned'}},{},{})
    code=scripts[0]
    for stage in ('write','close'):
        target=tmp_path/stage
        prefix='''import os
original=os.fdopen
class Broken:
    def __init__(self,fd,mode):self.file=original(fd,mode)
    def __enter__(self):return self
    def write(self,data):
        self.file.write(data)
        if STAGE=="write":raise OSError("Injected write failure")
    def __exit__(self,*args):
        self.file.close()
        if STAGE=="close":raise OSError("Injected close failure")
os.fdopen=Broken
'''.replace('STAGE',repr(stage))
        result=subprocess.run([sys.executable,'-c',prefix+code,str(target)],input=b'partial',capture_output=True)
        assert result.returncode!=0 and not target.exists() and ('Injected '+stage+' failure').encode() in result.stderr
        target.write_bytes(b'preexisting')
        result=subprocess.run([sys.executable,'-c',code,str(target)],input=b'replacement',capture_output=True)
        assert result.returncode!=0 and target.read_bytes()==b'preexisting'


@__import__('pytest').mark.parametrize('pi_version',['1.3.0','1.4.0'])
def test_native_command_origin_records_only_actual_cli_and_complete_source(monkeypatch,tmp_path,pi_version):
    # Given an owned complete session, When the real command launcher records
    # its invocation, Then preserve raw evidence and only count the new suffix.
    import hashlib,json,subprocess
    from pathlib import Path
    from types import SimpleNamespace
    import live_continuous_project_learning as study
    prefix=(json.dumps({'type':'session','id':'source','cwd':'/work/p-limit'})+'\n').encode()
    suffix=(json.dumps({'type':'message','message':{'role':'assistant','content':[],
        'usage':{'totalTokens':3,'cost':{'total':.1}},'stopReason':'stop'}})+'\n').encode()
    proxy=SimpleNamespace(key='synthetic-parent-credential',jev_key=None,token='synthetic-parent-token',
        selection={'provider':'fixture','model':'fixture'},jev_environment=lambda:{'TYPESAFE_API_KEY':'synthetic-jev-credential'})
    launched=[]
    def process(args,**kwargs):
        if args[1]=='cp':Path(args[-1]).write_bytes(prefix+suffix)
        else:launched.append(args)
        return subprocess.CompletedProcess(args,0,b'{"type":"result"}\n',b'')
    monkeypatch.setattr(study.base,'process',process)
    actual_version={'value':pi_version}
    monkeypatch.setattr(study.base,'checked',lambda args,**kwargs:(actual_version['value']+'\n').encode() if '--version'in args else prefix)
    monkeypatch.setattr(study.base,'shell',lambda *args,**kwargs:b'')
    calls=[]
    def source_capture(container,provider,path,session):
        calls.append(path.name)
        value={'sources':{'index.js':'actual source'},'manifest':{'sourceHashes':{'index.js':hashlib.sha256(b'actual source').hexdigest()},
            'files':{'index.js':{'sha256':hashlib.sha256(b'actual source').hexdigest(),'mode':0o644,'size':13}}}}
        (path/'candidate-before-convergence.json').write_text(json.dumps(value['manifest']))
        (path/'candidate-before-convergence.tar.gz').write_bytes(b'controlled-source-capture-stub')
        return value
    monkeypatch.setattr(study,'capture_failure_candidate',source_capture)
    output=tmp_path/'command'
    result=study.run_session('owned','/memory 整理记忆',proxy,output,'stage-0',command=True,
        prior_session_digest=hashlib.sha256(prefix).hexdigest(),capture_command_origin=True,expected_pi_version=pi_version)
    assert result['commandOrigin']['verified'] is True
    owner=json.loads((output/'memory-command-started.json').read_text())
    closed=json.loads((output/'memory-command-closed.json').read_text())
    assert owner['argv']==launched[0][launched[0].index('owned')+1:]
    assert owner['argv'][-1]=='/memory 整理记忆' and owner['arguments']=='整理记忆'
    assert owner['piVersion']==pi_version and owner['container']=='owned'
    assert calls==['command-source-before','command-source-after']
    assert (output/'original-session.jsonl').read_bytes()==prefix
    assert closed['ownerDigest']==hashlib.sha256((output/'memory-command-started.json').read_bytes()).hexdigest()
    assert closed['stdoutDigest']==hashlib.sha256((output/'stdout.jsonl').read_bytes()).hexdigest()
    assert closed['sessionDigest']==hashlib.sha256(prefix+suffix).hexdigest()
    assert result['usage']['totalTokens']==3 and result['reportedCost']==.1
    assert not any(secret in json.dumps(owner)+json.dumps(closed) for secret in (proxy.key,proxy.token,'synthetic-jev-credential'))
    actual_version['value']='1.3.0' # Harness policy remains its historical baseline.
    policy=study.run_session('owned',study.INITIAL_HARNESS_POLICY,proxy,tmp_path/'policy','policy',
        unlimited_budget=True,capture_policy_origin=True)
    policy_owner=json.loads((tmp_path/'policy/policy-started.json').read_text())
    policy_closed=json.loads((tmp_path/'policy/policy-closed.json').read_text())
    assert policy['policyOrigin']['verified']
    assert policy_owner['argv']==launched[-1][launched[-1].index('owned')+1:]
    assert '--no-tools' in policy_owner['argv'] and '--tools' not in policy_owner['argv']
    assert policy_owner['prompt']==study.UNLIMITED_COMMON+study.INITIAL_HARNESS_POLICY
    assert policy_owner['sourceFiles']==policy_closed['sourceFiles']
    assert (tmp_path/'policy/original-session.jsonl').read_bytes()==b''
    assert set(policy['policyOrigin']['artifactBindings'])==set(study.POLICY_ORIGIN_ARTIFACTS)
    assert policy['usage']['totalTokens']==3 and policy['reportedCost']==.1
    # After-model source drift remains a failed initialization, with its actual
    # native usage still known. A source failure cannot erase the paid call.
    def drift_capture(container,provider,path,session):
        captured=source_capture(container,provider,path,session)
        if path.name.endswith('after'):captured['manifest']['files']['index.js']['mode']=0o600
        return captured
    monkeypatch.setattr(study,'capture_failure_candidate',drift_capture)
    changed=study.run_session('owned','/memory 整理记忆',proxy,tmp_path/'changed','stage-0',command=True,
        prior_session_digest=hashlib.sha256(prefix).hexdigest(),capture_command_origin=True)
    from continuous_project_evidence import task_outcome
    assert changed['commandOrigin']['verified'] is False
    assert not task_outcome(changed,{'passed':True})['passed']
    assert changed['usage']['totalTokens']==3 and changed['reportedCost']==.1
    changed_policy=study.run_session('owned',study.INITIAL_HARNESS_POLICY,proxy,tmp_path/'policy-changed','policy',
        unlimited_budget=True,capture_policy_origin=True)
    assert changed_policy['policyOrigin']['verified'] is False
    assert not task_outcome(changed_policy,{'passed':True})['passed']
    assert changed_policy['usage']['totalTokens']==3 and changed_policy['reportedCost']==.1
    # A container-controlled copied symlink must not expose or rewrite a host
    # target before rejection. Unknown suffix usage remains unattributed.
    host=tmp_path/'host-target.jsonl'
    sentinel=prefix+suffix+b'synthetic-parent-credential'
    host.write_bytes(sentinel)
    def symlink_process(args,**kwargs):
        if args[1]=='cp':Path(args[-1]).symlink_to(host)
        return subprocess.CompletedProcess(args,0,b'{"type":"result"}\n',b'')
    monkeypatch.setattr(study.base,'process',symlink_process)
    monkeypatch.setattr(study,'capture_failure_candidate',source_capture)
    unsafe=study.run_session('owned','/memory 整理记忆',proxy,tmp_path/'unsafe','stage-0',command=True,
        prior_session_digest=hashlib.sha256(prefix).hexdigest(),capture_command_origin=True)
    assert host.read_bytes()==sentinel
    assert unsafe['commandOrigin']['verified'] is False
    assert unsafe['commandOrigin']['sessionCaptureError']=='ValueError'
    assert unsafe['commandSessionContinuation']['usageAttributionVerified'] is False
    assert not task_outcome(unsafe,{'passed':True})['passed']
    costs=study.totals({'stages':[{'arms':{'with-learning':{'inference':unsafe,'initializationCalls':[changed]}}}]})['with-learning']
    assert costs['unknownLeaderUsageAttempts']==1
    assert costs['leaderTokens']==3 and costs['leaderReportedCost']==.1
    assert costs['taskPasses']==0
    unsafe_policy=study.run_session('owned',study.INITIAL_HARNESS_POLICY,proxy,tmp_path/'policy-unsafe','policy',
        unlimited_budget=True,capture_policy_origin=True)
    assert host.read_bytes()==sentinel and unsafe_policy['sessionCaptureError']=='ValueError'
    assert unsafe_policy['policyOrigin']['verified'] is False
    assert not task_outcome(unsafe_policy,{'passed':True})['passed']
    ordinary=study.run_session('owned','Inspect source',proxy,tmp_path/'ordinary-unsafe','stage-0')
    assert host.read_bytes()==sentinel and ordinary['sessionCaptureError']=='ValueError'
    assert not task_outcome(ordinary,{'passed':True})['passed']
    ordinary_costs=study.totals({'stages':[{'arms':{'without-learning':{'inference':ordinary}}}]})['without-learning']
    assert ordinary_costs['unknownLeaderUsageAttempts']==1 and ordinary_costs['taskPasses']==0
    def failed_copy(args,**kwargs):
        return subprocess.CompletedProcess(args,1 if args[1]=='cp' else 0,b'{"type":"result"}\n',b'copy refused')
    monkeypatch.setattr(study.base,'process',failed_copy)
    missing=study.run_session('owned','Inspect source',proxy,tmp_path/'copy-failed','stage-0')
    assert missing['exitCode']==0 and missing['sessionCaptureError']=='copy-failed'
    assert not task_outcome(missing,{'passed':True})['passed']
    missing_costs=study.totals({'stages':[{'arms':{'without-learning':{'inference':missing}}}]})['without-learning']
    assert missing_costs['unknownLeaderUsageAttempts']==1 and missing_costs['taskPasses']==0


def test_explicit_memory_continuation_keeps_original_evidence_without_recounting_usage(monkeypatch, tmp_path):
    # Given a completed source session with reported usage, When the native
    # Memory command continues that exact session, Then retain the prefix but
    # charge only the new suffix, including failed initialization in totals.
    import hashlib, json, subprocess
    from pathlib import Path
    from types import SimpleNamespace
    import live_continuous_project_learning as study
    prefix=b''.join((json.dumps(row)+'\n').encode() for row in [
        {'type':'session','id':'source-session','cwd':'/work/p-limit'},
        {'type':'message','message':{'role':'user','content':'Inspect source.'}},
        {'type':'message','message':{'role':'assistant','content':[], 'usage':{'totalTokens':17,'cost':{'total':.2}},'stopReason':'stop'}}])
    suffix=(json.dumps({'type':'message','message':{'role':'assistant','content':[],
        'usage':{'totalTokens':3,'cost':{'total':.1}},'stopReason':'stop'}})+'\n').encode()
    proxy=SimpleNamespace(key='fixture',jev_key=None,token='fixture',selection={'provider':'fixture','model':'fixture'},jev_environment=lambda:{})
    launched=[]
    def process(args, **_kwargs):
        if args[1]=='cp':Path(args[-1]).write_bytes(prefix+suffix)
        elif args[1]=='exec':launched.append(args)
        return subprocess.CompletedProcess(args,0,b'',b'')
    monkeypatch.setattr(study.base,'process',process)
    monkeypatch.setattr(study.base,'checked',lambda *_args,**_kwargs:prefix)
    monkeypatch.setattr(study.base,'shell',lambda *_args,**_kwargs:b'')
    digest=hashlib.sha256(prefix).hexdigest()
    # The historical fresh-session interface counts all retained rows. That
    # behavior stays unchanged; it cannot be used for this new continuation.
    legacy=study.run_session('fixture','/memory 整理记忆',proxy,tmp_path/'legacy','stage-0',command=True)
    assert legacy['usage']['totalTokens']==20
    result=study.run_session('fixture','/memory 整理记忆',proxy,tmp_path,'stage-0',command=True,
        prior_session_digest=digest,unlimited_budget=True)
    assert result['originalObservationsPreserved']
    assert result['usage']['totalTokens']==3 and result['reportedCost']==.1
    assert (tmp_path/'session.jsonl').read_bytes()==prefix+suffix
    assert all(call[-1]=='/memory 整理记忆' for call in launched)
    assert result['commandSessionContinuation']=={'priorSessionDigest':digest,'priorEntryCount':3,'newEntryCount':1,'usageAttributionVerified':True}
    combined=totals({'stages':[{'arms':{'with-learning':{'passed':False,'validPairInput':False,
        'inference':{'usage':{'totalTokens':17},'reportedCost':.2,'seconds':1},
        'initializationCalls':[result]}}}]})['with-learning']
    assert combined['leaderTokens']==20 and combined['taskPasses']==0
    assert combined['leaderReportedCost']==.2+.1
    # If the prefix changes after launch, retain the raw attempt and reported
    # suffix separately. It cannot become a successful or priced initialization.
    changed=prefix.replace(b'Inspect source.',b'Altered source.')+suffix
    def tampered_process(args, **_kwargs):
        if args[1]=='cp':Path(args[-1]).write_bytes(changed)
        return subprocess.CompletedProcess(args,0,b'',b'')
    monkeypatch.setattr(study.base,'process',tampered_process)
    rejected=study.run_session('fixture','/memory 整理记忆',proxy,tmp_path/'changed','stage-0',command=True,prior_session_digest=digest)
    assert not rejected['originalObservationsPreserved']
    assert rejected['commandSessionContinuation']['usageAttributionVerified'] is False
    from continuous_project_evidence import task_outcome
    assert not task_outcome(rejected,{'passed':True})['passed']
    unknown=totals({'stages':[{'arms':{'with-learning':{'passed':False,
        'inference':{'usage':{'totalTokens':17},'reportedCost':.2,'seconds':1},
        'initializationCalls':[rejected]}}}]})['with-learning']
    assert unknown['leaderTokens']==17 and unknown['leaderReportedCost']==.2
    assert unknown['unknownLeaderUsageAttempts']==1 and unknown['unattributedLeaderReportedTokens']==3
    assert unknown['unattributedLeaderReportedCost']==.1


def test_backfill_continues_actual_source_session_without_recounting_or_inventing_turns(monkeypatch,tmp_path):
    import hashlib,json,subprocess
    from types import SimpleNamespace
    import live_continuous_project_learning as study
    from continuous_project_evidence import task_outcome
    prefix=('\n'.join(json.dumps(row) for row in [
        {'type':'session','id':'actual-source-session','cwd':'/work/p-limit'},
        {'type':'message','message':{'role':'user','content':'Original failed task'}},
        {'type':'message','message':{'role':'assistant','content':[],'usage':{'totalTokens':17,'cost':{'total':.2}},'stopReason':'stop'}}])+'\n').encode()
    proxy=SimpleNamespace(key='fixture',jev_key=None,token='fixture',selection={'provider':'fixture','model':'fixture'},jev_environment=lambda:{})
    monkeypatch.setattr(study.base,'shell',lambda *_a,**_k:b'')
    monkeypatch.setattr(study,'read_command_session',lambda container,label:prefix)
    calls=[];damage=None
    def process(args,**_kwargs):
        calls.append(args)
        if args[1]=='cp':
            if damage=='copy-failed':return subprocess.CompletedProcess(args,1,b'',b'missing')
            Path(args[-1]).write_bytes(prefix.replace(b'Original failed task',b'Changed task') if damage=='changed' else prefix)
        return subprocess.CompletedProcess(args,0,b'',b'')
    from pathlib import Path
    monkeypatch.setattr(study.base,'process',process)
    digest=hashlib.sha256(prefix).hexdigest()
    for damage in (None,'changed','copy-failed'):
        output=tmp_path/(damage or 'valid');output.mkdir()
        result=study.run_session('same-owned-container','/consolidate backfill',proxy,output,'stage-0',command=True,
            unlimited_budget=True,prior_session_digest=digest)
        assert result['exitCode']==0 and result['usage']['totalTokens']==0
        assert result['commandSessionContinuation']['priorSessionDigest']==digest
        assert result['commandSessionContinuation']['usageAttributionVerified'] is (damage is None)
        assert result['originalObservationsPreserved'] is (damage is None)
        assert task_outcome(result,{'passed':True})['passed'] is (damage is None)
        if damage=='copy-failed':assert result['sessionCaptureError']=='copy-failed'
    assert all(call[2]=='same-owned-container:/home/node/agent/sessions/continuous/stage-0.jsonl' for call in calls if call[1]=='cp')
    assert (tmp_path/'valid/session.jsonl').read_bytes()==prefix


def test_real_pi_backfill_without_conversation_does_not_persist_a_fresh_session(tmp_path):
    # Actual native persistence is lazy. A slash command on a fresh path does
    # not create a transcript; an existing conversation remains byte-prefixed.
    import json,subprocess
    from pathlib import Path
    from live_acceptance_support import isolated_environment,workspace_pi
    from support import REPO
    project=tmp_path/'project';agent=tmp_path/'agent';project.mkdir();agent.mkdir()
    (agent/'settings.json').write_text('{"packages":[],"quietStartup":true}')
    (agent/'continual-learning.json').write_text('{"jev":false}')
    (agent/'memory').mkdir();(agent/'memory/settings.json').write_text('{"autoMemory":false}')
    env=isolated_environment(tmp_path,agent)
    fixture=Path(__file__).with_name('continuous-tool-budget-fixture.ts')
    base=[workspace_pi(REPO),'--offline','--no-extensions','--no-context-files','--no-skills',
        '--no-prompt-templates','--no-themes','--no-approve','--thinking','off','--tools','bash',
        '-e',str(fixture),'--model','study-budget-fixture/deterministic','--print','--mode','json']
    existing=project/'source.jsonl'
    initial=subprocess.run([*base,'--session',str(existing),'observe'],cwd=project,env=env,capture_output=True,timeout=30)
    assert initial.returncode==0,initial.stderr.decode()
    original=existing.read_bytes();header=json.loads(original.splitlines()[0])
    assert header['type']=='session' and header['cwd']==str(project)
    for session in (project/'fresh-recovery.jsonl',existing):
        completed=subprocess.run([*base,'-e',str(REPO/'packages/continual-learning/index.ts'),
            '--session',str(session),'/consolidate backfill'],cwd=project,env=env,capture_output=True,timeout=30)
        assert completed.returncode==0,completed.stderr.decode()
        if session==existing:
            raw=session.read_bytes();assert raw.startswith(original)
            assert json.loads(raw.splitlines()[0])==header
        else:assert not session.exists()


def test_explicit_memory_continuation_rejects_changed_or_partial_prefix_before_generation(monkeypatch, tmp_path):
    import hashlib, json, subprocess
    from types import SimpleNamespace
    import pytest
    import live_continuous_project_learning as study
    prefix=(json.dumps({'type':'session','id':'source','cwd':'/work/p-limit'})+'\n').encode()
    proxy=SimpleNamespace(key='fixture',jev_key=None,token='fixture',selection={'provider':'fixture','model':'fixture'},jev_environment=lambda:{})
    generated=[]
    monkeypatch.setattr(study.base,'shell',lambda *_args,**_kwargs:b'')
    monkeypatch.setattr(study.base,'process',lambda *args,**kwargs:generated.append(args))
    invalid=[prefix[:-1],b'not-json\n',b'[]\n',b'{"type":"session","id":"source","cwd":"/work/other"}\n',
             b'{"type":"session","cwd":"/work/p-limit"}\n',prefix+b'\n']
    for raw,digest in [(prefix,'0'*64),*((raw,hashlib.sha256(raw).hexdigest()) for raw in invalid)]:
        monkeypatch.setattr(study.base,'checked',lambda *_args,**_kwargs:raw)
        monkeypatch.setattr(study,'read_command_session',lambda *_args:raw)
        for prompt in ('/memory 整理记忆','/consolidate backfill'):
            with pytest.raises(ValueError):
                study.run_session('fixture',prompt,proxy,tmp_path,'stage-0',command=True,prior_session_digest=digest)
    for prompt in ('/consolidate backfill extra','/consolidate backfill\n','/consolidate status'):
        with pytest.raises(ValueError):
            study.run_session('fixture',prompt,proxy,tmp_path,'stage-0',command=True,prior_session_digest=hashlib.sha256(prefix).hexdigest())
    def refused(*_args):raise ValueError('Refused non-regular source session')
    monkeypatch.setattr(study,'read_command_session',refused)
    with pytest.raises(ValueError):
        study.run_session('fixture','/consolidate backfill',proxy,tmp_path,'stage-0',command=True,prior_session_digest=hashlib.sha256(prefix).hexdigest())
    with pytest.raises(ValueError):
        study.run_session('fixture','ordinary task',proxy,tmp_path,'stage-0',prior_session_digest=hashlib.sha256(prefix).hexdigest())
    assert not generated


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
    source=source.replace("'./continuous-command-proof'","'./packages/continual-learning/tests/continuous-command-proof.ts'")
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
    assert 'then run exactly pnpm test once as a separate standalone Bash command' in changed[0]['prompt']
    assert 'Do not pipe, prefix or combine either verification command' in changed[0]['prompt']
    assert 'unresolved failure' in changed[0]['prompt'] and 'do not infer its cause' in changed[0]['prompt']
    assert 'limitFunction' in changed[0]['prompt'] and 'Permanent project constraint' in changed[0]['prompt']
    assert 'Repair the existing' in changed[1]['prompt'] and 'historical' in changed[1]['prompt']
    assert 'TEMPORARY_IDLE_REVIEW' in changed[1]['prompt']
    assert 'setImmediate' not in ''.join(t['prompt'] for t in changed)



def test_command_initialization_splits_learning_from_unchanged_source_and_later_tasks():
    import ast,inspect
    import live_continuous_project_learning as study
    from continuous_project_tasks import command_initialization_tasks,failure_first_tasks,INITIAL_HARNESS_POLICY
    historical=failure_first_tasks();tasks=command_initialization_tasks()
    assert tasks[1:]==historical[1:] and len(tasks)==6
    assert historical[0]['prompt'].startswith(tasks[0]['prompt'])
    assert 'Remember' not in tasks[0]['prompt'] and 'Permanent project constraint' not in tasks[0]['prompt']
    assert 'Do not edit files' in tasks[0]['prompt'] and 'pnpm test once' in tasks[0]['prompt']
    assert INITIAL_HARNESS_POLICY in historical[0]['prompt']
    assert 'automatic' not in INITIAL_HARNESS_POLICY and 'npm' in INITIAL_HARNESS_POLICY
    function=ast.parse(inspect.getsource(study.run))
    loop=next(node for node in ast.walk(function) if isinstance(node,ast.For) and isinstance(node.target,ast.Name) and node.target.id=='arm_index')
    order=compile(ast.Expression(loop.iter),'actual-arm-order','eval')
    for explicit in (False,True):
        for index in range(6):
            expected=[1,0] if explicit and index==0 else ([0,1] if index%2==0 else [1,0])
            assert eval(order,{'explicit_command_initialization':explicit,'index':index})==expected



def _initialization_noop_attempt(queued,raw):
    import json,hashlib
    from support import run_bun
    source={'source':'backlog-session','entryCount':queued['to']-queued['from']+1,
            'sessionId':json.loads(raw.splitlines()[0])['id'],'sourceDigest':hashlib.sha256(raw.encode()).hexdigest()}
    input={**source,'backlogId':queued['id'],'backlogRange':{key:queued[key]for key in ('from','to','digest')}}
    result=run_bun("""import {createHash} from 'node:crypto';
import {buildLearningReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
const receipt=buildLearningReceipt('manual',{memory:true,harness:false,agents:false,reasons:[]},
 [{phase:'memory',attempt:0,outcome:'noop',operations:0,durationMs:1}],INPUT,'batch_'+'e'.repeat(32));
console.log(JSON.stringify({receipt,digest:createHash('sha256').update(JSON.stringify(receipt)).digest('hex')}));""".replace('INPUT',json.dumps(input)))
    return {'outcome':'completed','sourceBinding':source,'receiptDigest':result['digest'],'receipt':result['receipt']}

def test_command_initialization_closure_requires_exact_noop_and_preserves_costs():
    import copy
    from continuous_project_evidence import initialization_closure_ready
    from recovery_integrity import verify_recovery_delta
    value=_command_audit_fixture();state=value['currentState'];raw=value['commandEvidence']['nativeSession']
    before=copy.deepcopy(state)
    queued={'id':'d'*64,'from':0,'to':3,'digest':'c'*64,'sessionFile':'/home/node/agent/sessions/continuous/stage-0.jsonl'}
    before['pendingLearningJobs']=1;before['backlogStatus']={'pending':1,'pendingEntries':[queued]}
    after=copy.deepcopy(before);after['pendingLearningJobs']=0;after['backlogStatus']={'pending':0,'pendingEntries':[]}
    attempt=_initialization_noop_attempt(queued,raw)
    after['receipts'].append(attempt['receipt']);after['attempts'].append(attempt)
    after['completedBacklog']={queued['id']:attempt['receiptDigest']}
    assert verify_recovery_delta(before,after)['passed']
    assert initialization_closure_ready(before,after,raw.encode(),queued['sessionFile'])['ready']
    for damage in ('pending','mode','history','cost','range','operations','held','ack','contract','digest','source'):
        changed=copy.deepcopy(after)
        if damage=='pending':changed['pendingLearningJobs']=1
        elif damage=='mode':next(iter(changed['surfaceSnapshots'].values()))['mode']^=0o040
        elif damage=='history':changed['history'].append({'id':'unrelated'})
        elif damage=='cost':changed['receipts']=changed['receipts'][1:]
        elif damage=='range':changed['attempts'][-1]['receipt']['input']['backlogRange']['to']=4
        elif damage=='operations':changed['attempts'][-1]['receipt']['operations']=1
        elif damage=='held':changed['attempts'][-1]['receipt']['attempts'][0]['outcome']='proposed'
        elif damage=='ack':changed['completedBacklog'][queued['id']]='foreign'
        elif damage=='contract':changed['attempts'][-1]['receipt']['kind']='foreign'
        elif damage=='digest':
            changed['attempts'][-1]['receiptDigest']='invented';changed['completedBacklog'][queued['id']]='invented'
        elif damage=='source':changed['attempts'][-1]['receipt']['input']['sourceDigest']='f'*64
        assert not initialization_closure_ready(before,changed,raw.encode(),queued['sessionFile'])['ready'],damage


def test_command_initialization_runner_executes_actual_steps_once_and_stops_on_hold(monkeypatch,tmp_path):
    # Controlled orchestration; real command provenance and semantic truth have
    # their separate native and service gates.
    import copy,json
    from types import SimpleNamespace
    import live_continuous_project_learning as study
    value=_command_audit_fixture();first=copy.deepcopy(value['currentState'])
    command=value['commandEvidence'];first['commandReviewInput']=command
    queued={'id':'d'*64,'from':0,'to':3,'digest':'c'*64,'sessionFile':'/home/node/agent/sessions/continuous/stage-0.jsonl'}
    first['pendingLearningJobs']=1;first['backlogStatus']={'pending':1,'pendingEntries':[queued]}
    second=copy.deepcopy(first);second['pendingLearningJobs']=0;second['backlogStatus']={'pending':0,'pendingEntries':[]}
    attempt=_initialization_noop_attempt(queued,command['nativeSession'])
    second['receipts'].append(attempt['receipt']);second['attempts'].append(attempt)
    second['completedBacklog']={queued['id']:attempt['receiptDigest']}
    states=iter([first,second]);calls=[];audits=[]
    proxy=SimpleNamespace(jev_usage=[],requests=0)
    def session(container,prompt,proxy,directory,label,**options):
        calls.append((prompt,label,options));proxy.requests+=2;proxy.jev_usage.append({'cost':.01})
        return {'exitCode':0,'usage':{'totalTokens':3},'reportedCost':.1,'seconds':1}
    monkeypatch.setattr(study,'run_session',session)
    monkeypatch.setattr(study,'artifacts',lambda *a,**k:next(states))
    monkeypatch.setattr(study.base,'protected',lambda *a,**k:{'index.js':'unchanged'})
    monkeypatch.setattr(study,'run_memory_audit',lambda c,p,payload,out:audits.append(payload)or{'passed':True})
    row={}
    result=study.run_command_initialization('owned',proxy,tmp_path,'stage-0',prior=value['priorState'],
        observation=value['observation'],sources=value['sources'],original_session=value['nativeSession'].encode(),protocol=value['protocol'],row=row)
    assert result is second
    assert [call[0]for call in calls]==['/memory 整理记忆','/consolidate backfill']
    assert calls[0][1]=='stage-0' and calls[0][2]['capture_command_origin'] is True
    assert calls[1][1]=='stage-0'
    assert calls[1][2]['prior_session_digest']==__import__('hashlib').sha256(command['nativeSession'].encode()).hexdigest()
    assert row['commandState'] is first and row['closureState'] is second and row['sourceClosure']['ready']
    assert len(row['initializationCalls'])==2 and all(call['allTransportRequests']==2 for call in row['initializationCalls'])
    assert audits[0]['currentState']['pendingLearningJobs']==0 and audits[0]['commandEvidence']['nativeSession']==command['nativeSession']
    # Held knowledge stops before closure, audit or any dependent policy task.
    calls.clear();audits.clear()
    monkeypatch.setattr(study,'artifacts',lambda *a,**k:(_ for _ in ()).throw(ValueError('held command has no applied ledger')))
    held={}
    with __import__('pytest').raises(ValueError):study.run_command_initialization('owned',proxy,tmp_path/'held','stage-0',
        prior=value['priorState'],observation=value['observation'],sources=value['sources'],
        original_session=value['nativeSession'].encode(),protocol=value['protocol'],row=held)
    assert len(calls)==1 and len(held['initializationCalls'])==1 and not audits
    calls.clear()
    held_state=copy.deepcopy(first);held_state.pop('commandReviewInput')
    held_state['commandInitializationHeld']=True
    monkeypatch.setattr(study,'artifacts',lambda *a,**k:held_state)
    held={}
    with __import__('pytest').raises(RuntimeError,match='Memory command remains held'):
        study.run_command_initialization('owned',proxy,tmp_path/'unapplied','stage-0',
            prior=value['priorState'],observation=value['observation'],sources=value['sources'],
            original_session=value['nativeSession'].encode(),protocol=value['protocol'],row=held)
    assert held['learning'] is held_state and held['commandState'] is held_state
    assert held['validPairInput'] is False and held['validLearning'] is False
    assert held['initializationBlocked']=={'phase':'memory-command-held','dependentPolicyStarted':False}
    assert len(calls)==1 and not audits and 'closureState' not in held
    # Exercise the actual owner boundary: an exception leaves neither arm
    # attributable, including a control that ran before the failed learner.
    import ast
    from pathlib import Path
    tree=ast.parse(Path(study.__file__).read_text())
    boundary=next(node for node in ast.walk(tree) if isinstance(node,ast.Try)
        and any(isinstance(statement,ast.Assign) and isinstance(statement.value,ast.Call)
                and isinstance(statement.value.func,ast.Name) and statement.value.func.id=='run_command_initialization'
                for statement in node.body))
    compiled=compile(ast.fix_missing_locations(ast.Module(body=[boundary],type_ignores=[])),study.__file__,'exec')
    for error in (RuntimeError('held'),ValueError('invalid origin'),OSError('capture failed')):
        stage={'validPairInput':True,'arms':{'with-learning':{'validPairInput':True},'without-learning':{'validPairInput':True}}}
        def refuse(*args,**kwargs):raise error
        env=dict(run_command_initialization=refuse,c='owned',proxy=proxy,out=tmp_path,empty_state={},
            main_observation={},candidate={'sources':{}},main_session=b'',audit_protocol={},
            row=stage['arms']['with-learning'],stage=stage)
        with __import__('pytest').raises(type(error)):exec(compiled,env)
        assert stage['validPairInput'] is False and all(r['validPairInput'] is False for r in stage['arms'].values())
    # A request can finish before its evidence reader raises. Keep the failed
    # attempt and request/usage counters even though run_session did not return.
    def failed_session(*args,**kwargs):
        proxy.requests+=2;proxy.jev_usage.append({'cost':.01});raise OSError('postlaunch capture failed')
    monkeypatch.setattr(study,'run_session',failed_session)
    failed={}
    with __import__('pytest').raises(OSError):study.run_command_initialization('owned',proxy,tmp_path/'exception','stage-0',
        prior=value['priorState'],observation=value['observation'],sources=value['sources'],
        original_session=value['nativeSession'].encode(),protocol=value['protocol'],row=failed)
    saved=failed['initializationCalls'][0]
    assert saved['allTransportRequests']==2 and len(saved['jevUsage'])==1
    assert saved['errorType']=='OSError' and saved['sessionCaptureError']=='initialization-call-exception'
    totals=study.totals({'stages':[{'arms':{'with-learning':{'inference':{'usage':{'totalTokens':0},'reportedCost':0,'seconds':0},**failed}}}]})
    assert totals['with-learning']['unknownLeaderUsageAttempts']==1

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


def test_direct_command_initialization_binds_history_without_replay_or_pending_bypass():
    import copy,hashlib
    import pytest
    from continuous_project_evidence import command_initialization_audit_input
    prior,current,observation,sources,session,protocol=_failure_record_fixture()
    receipt={'kind':'learning-pipeline-receipt','version':1,'mode':'manual','batchId':'initial-owner',
        'operations':1,'attempts':[{'phase':'memory','outcome':'applied','operations':1}]}
    current['attempts']=[];current['receipts']=[receipt];prior['receipts']=[]
    current['backlogStatus']={'pending':0};current['pendingLearningJobs']=0
    protocol['explicitCommandInitializationVersion']=1
    command={'kind':'explicit-command-source-review','version':1,'originalSession':session.decode(),
        'owner':{'cwd':'/work/p-limit','priorSessionDigest':hashlib.sha256(session).hexdigest(),
                 'sourceHashes':{name:hashlib.sha256(body.encode()).hexdigest()for name,body in sources.items()}},
        'sources':sources,'receipt':receipt}
    args=[prior,current,observation,sources,session,protocol,command]
    result=command_initialization_audit_input(*args)
    assert result['mode']=='observed-command-memory-initialization'
    assert result['historyIntegrity']['passed'] and result['currentState']['attempts']==[]
    assert result['mutationAuthority'] is False and result['learningBenefitEstablished'] is False
    for kind in ('pending','missing-receipt','changed-command-source','changed-original','old-knowledge','old-protocol'):
        values=copy.deepcopy(args)
        if kind=='pending':values[1]['pendingLearningJobs']=1
        elif kind=='missing-receipt':values[1]['receipts']=[]
        elif kind=='changed-command-source':values[6]['sources']={'index.js':'different'}
        elif kind=='changed-original':values[6]['originalSession']+='{}\n'
        elif kind=='old-knowledge':values[0]['memoryEntries']=copy.deepcopy(values[1]['memoryEntries'])
        elif kind=='old-protocol':values[5].pop('explicitCommandInitializationVersion')
        with pytest.raises(ValueError):command_initialization_audit_input(*values)


def _command_audit_fixture():
    # Controlled wire framing, not retained native execution or model efficacy.
    import json,hashlib
    from support import run_bun
    from continuous_project_evidence import command_initialization_audit_input
    prior,current,observation,sources,session,protocol=_failure_record_fixture()
    binding=_failure_feedback_fixture()[1]['sourceReviewBindings'][0]
    command=run_bun(r'''
      import {createHash} from 'node:crypto';
      import {requestedMemoryTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      const binding=BINDING,originalSession=ORIGINAL,sources=SOURCES,content=CONTENT;
      const hash=text=>createHash('sha256').update(text).digest('hex');
      const original=originalSession.trimEnd().split('\n').map(JSON.parse);
      const request='整理记忆',task=requestedMemoryTaskSlice(request,original.slice(1));
      const snapshot=JSON.parse(binding.snapshotText);
      snapshot.entries=[...task.entries,...snapshot.entries.slice(-2)];
      binding.snapshotText=JSON.stringify(snapshot);
      const snapshotDigest=hash(binding.snapshotText);
      Object.assign(binding.plan,{version:1,operations:[],newMemories:[{name:'idle.md',classification:'private',content}],snapshotDigest,artifactHash:snapshotDigest});
      binding.reviewManifest.snapshotDigest=snapshotDigest;
      const receipt={...binding.receipt,kind:'learning-pipeline-receipt',version:1,mode:'manual',operations:1,input:{source:'current-session'}};
      const nativeSession=originalSession+JSON.stringify({type:'custom_message',id:'memory-result',parentId:original.at(-1).id,
        customType:'continual-learning-result',details:receipt})+'\n';
      const stdout=JSON.stringify({type:'message_end',message:{customType:'continual-learning-result',details:receipt}})+'\n';
      const sessionPath='/home/node/agent/sessions/continuous/stage-0.jsonl';
      const owner={kind:'native-memory-command',version:1,argv:['pi','--model','fixture/scripted','--session',sessionPath,'--print','--mode','json','/memory '+request],
        cwd:'/work/p-limit',agentDir:'/home/node/agent',sessionPath,model:'fixture/scripted',piVersion:'1.3.0',arguments:request,
        startedAt:1,priorSessionDigest:hash(originalSession),sourceHashes:Object.fromEntries(Object.entries(sources).map(([name,body])=>[name,hash(body)])),
        sourceFiles:Object.fromEntries(Object.entries(sources).map(([name,body])=>[name,{sha256:hash(body),mode:420,size:Buffer.byteLength(body)}]))};
      const completion={ownerDigest:hash(JSON.stringify(owner)),exitCode:0,cancelled:false,timedOut:false,settledAt:2,
        stdoutDigest:hash(stdout),sessionDigest:hash(nativeSession),sourceHashes:owner.sourceHashes,sourceFiles:owner.sourceFiles};
      console.log(JSON.stringify({...binding,kind:'explicit-command-source-review',version:1,owner,completion,originalSession,nativeSession,stdout,sources,receipt}));
    '''.replace('BINDING',json.dumps(binding)).replace('ORIGINAL',json.dumps(session.decode()))
       .replace('SOURCES',json.dumps(sources)).replace('CONTENT',json.dumps(current['memoryEntries'][0]['content'])))
    current['attempts']=[];prior['receipts']=[];current['receipts']=[command['receipt']]
    current['pendingLearningJobs']=0;current['backlogStatus']={'pending':0}
    protocol['explicitCommandInitializationVersion']=1
    assert command['owner']['priorSessionDigest']==hashlib.sha256(session).hexdigest()
    return command_initialization_audit_input(prior,current,observation,sources,session,protocol,command)


def _command_policy_transition_fixture():
    # Controlled provenance/SDK framing only. No retained or generated task answer.
    import copy,json
    from support import run_bun
    from continuous_project_evidence import policy_initialization_bridge, failure_transition_audit_input
    record=_command_audit_fixture()
    record['currentState']['completedBacklog']={}
    bound=run_bun(r'''
      import {createHash} from 'node:crypto';
      import {currentTaskSlice} from './packages/continual-learning/extensions/incremental-learning.ts';
      import {buildLearningReceipt} from './packages/continual-learning/extensions/learning-efficiency.ts';
      import {backlogIdentity} from './packages/continual-learning/extensions/learning-backlog.ts';
      import {ruleRevision} from './packages/continual-learning/extensions/guardrail-engine.ts';
      const prior=PRIOR,current=structuredClone(prior),hash=s=>createHash('sha256').update(s).digest('hex');
      const cwd='/work/p-limit',agentDir='/home/node/agent',scopeKey='--work-p-limit--',sessionPath=agentDir+'/sessions/continuous/policy.jsonl';
      const prompt='Permanent project constraint: Bash commands whose first executable is npm must be blocked; use pnpm instead.';
      const user={type:'message',id:'policy-user',parentId:null,message:{role:'user',content:[{type:'text',text:prompt}]}},
       assistant={type:'message',id:'policy-assistant',parentId:user.id,message:{role:'assistant',stopReason:'stop',content:[{type:'text',text:'Policy noted.'}]}};
      const entries=[user,assistant],task=currentTaskSlice(entries),range={from:0,to:1,digest:hash(JSON.stringify(task))};
      const batchId='batch_'+'b'.repeat(32),usage={input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:.01},
       usageLedger={ledgerId:'12345678-1234-4234-8234-123456789abc',complete:true,knownUsage:usage};
      const receipt=buildLearningReceipt('automatic',{memory:false,harness:true,agents:false,reasons:[]},
       [{phase:'harness',attempt:0,outcome:'applied',durationMs:1,operations:1,usage,usageComplete:true,usageLedgerId:usageLedger.ledgerId}],
       {source:'current-session',entryCount:2,backlogRange:range,backlogId:backlogIdentity(scopeKey,{sessionFile:sessionPath,...range})},batchId);
      const receiptDigest=hash(JSON.stringify(receipt));
      const rule={id:'auto-npm',bash:'^npm(?:\\s|$)',action:'block',message:'Use pnpm.'};
      const document={rules:[rule],learnedRules:{[rule.id]:{origin:'consolidation',revision:ruleRevision(rule)}}};
      const text=JSON.stringify(document),physical={bytes:Buffer.from(text).toString('base64'),digest:hash(text),mode:384,revision:`1:99:${Buffer.byteLength(text)}:2:2`};
      current.surfaceSnapshots['project/.pi/harness.json']=physical;
      current.history.push({version:1,id:'policy-history',cwd,agentDir,createdAt:'2026-10-19T01:00:00Z',status:'applied',phase:'harness',batchId,
       changes:[{target:{root:'project',name:'.pi/harness.json'},before:null,after:physical}]});
      current.receipts.push(receipt);current.attempts.push({outcome:'completed',receipt,receiptDigest,sourceBinding:{source:'current-session',entryCount:2}});
      current.completedBacklog[receipt.input.backlogId]=receiptDigest;
      const runId='run_policy_0123456789abcdef',runDir=agentDir+'/memory/runs/'+scopeKey+'/'+runId,
       snapshotText=JSON.stringify({runId,scopeKey,entries:task.entries}),snapshotDigest=hash(snapshotText),scopeDigest='d'.repeat(64);
      const owner={kind:'native-automatic-harness-policy',version:1,piVersion:'1.3.0',cwd,agentDir,sessionPath,prompt,startedAt:1,
       argv:['pi','--no-tools','--session',sessionPath,'--print','--mode','json',prompt],sourceFiles:SOURCEFILES};
      const nativeSession=[{type:'session',id:'policy',cwd},...entries,{type:'custom_message',id:'policy-receipt',parentId:assistant.id,customType:'continual-learning-result',details:receipt}].map(r=>JSON.stringify(r)).join('\n')+'\n';
      const stdout=[{type:'message_end',message:assistant.message},{type:'message_end',message:{customType:'continual-learning-result',details:receipt}}].map(r=>JSON.stringify(r)).join('\n')+'\n';
      const completion={ownerDigest:hash(JSON.stringify(owner)),exitCode:0,timedOut:false,cancelled:false,settledAt:2,sourceFiles:owner.sourceFiles,
       sessionDigest:hash(nativeSession),stdoutDigest:hash(stdout)};
      const input={kind:'automatic-harness-policy-review',version:1,owner,completion,nativeSession,stdout,receipt,snapshotText,
       reviewManifest:{cwd,scopeKey,runId,runDir,scopeDigest,snapshotPath:runDir+'/snapshot.json',snapshotDigest},
       usageLedger,usageLedgerPath:runDir+'/harness-task-usage.json',postReceipt:{kind:'harness-consolidation-receipt',phase:'post',runId,scopeDigest,snapshotDigest,
        targetFile:cwd+'/.pi/harness.json',digestBefore:null,digestAfter:physical.digest}};
      console.log(JSON.stringify({input,current}));
    '''.replace('PRIOR',json.dumps(record['currentState'])).replace('SOURCEFILES',json.dumps(record['commandEvidence']['owner']['sourceFiles'])))
    bridge=policy_initialization_bridge(record['currentState'],bound['current'],bound['input'],source_files=record['commandEvidence']['owner']['sourceFiles'])
    values=list(copy.deepcopy(_failure_transition_fixture()));after=copy.deepcopy(bridge['currentState'])
    after['memoryEntries']=values[1]['memoryEntries']
    after['surfaceSnapshots']['private/idle.md']=values[1]['surfaceSnapshots']['private/idle.md']
    after['history']+=values[1]['history'];after['attempts']+=values[1]['attempts']
    values[0]=bridge['currentState'];values[1]=after
    values[2]=record['observation'];values[4]=record['sources'];values[6]=record['nativeSession'].encode()
    values[8]={**record['protocol'],'currentPrompt':values[8]['currentPrompt']}
    return record,bridge,values


def test_command_initialization_and_actual_policy_owner_reach_later_correction(tmp_path):
    from continuous_project_evidence import failure_transition_audit_input
    record,bridge,values=_command_policy_transition_fixture()
    payload=failure_transition_audit_input(*values,original_initialization_record=record,initial_policy_bridge=bridge)
    result,request,_=_run_memory_transition_audit(tmp_path,{'type':'choice','choice':'corrected','confidence':.8,'probabilities':{'corrected':.9}},audit_input=payload)
    assert result['passed'] and request['model']=='jev-1.14.0'
    assert result['mutationAuthority'] is False and result['learningBenefitEstablished'] is False
    assert payload['originalInitializationRecord']['currentState']==bridge['priorState']
    assert payload['priorState']==bridge['currentState']
    assert payload['historyIntegrity']['changedPaths']==['private/idle.md']


@__import__('pytest').mark.parametrize('damage',['wrong-endpoint','replace-initial-state','changed-command','changed-user','lost-prior-receipt','fake-proof','both-origins','missing-bridge','foreign-source'])
def test_command_policy_transition_refuses_incomplete_lineage(tmp_path,damage):
    import copy,pytest
    from continuous_project_evidence import failure_transition_audit_input
    record,bridge,values=_command_policy_transition_fixture()
    options={'original_initialization_record':record,'initial_policy_bridge':bridge}
    if damage=='wrong-endpoint':values[0]['pendingLearningJobs']=1
    elif damage=='replace-initial-state':record['currentState']=copy.deepcopy(bridge['currentState'])
    elif damage=='changed-command':record['commandEvidence']['owner']['arguments']='different request'
    elif damage=='changed-user':bridge['policyEvidence']['owner']['prompt']='different user'
    elif damage=='lost-prior-receipt':bridge['currentState']['receipts'].pop(0)
    elif damage=='fake-proof':bridge['nativePolicyProof']['ruleRevision']='0'*64
    elif damage=='both-origins':options['original_feedback_record']={}
    elif damage=='missing-bridge':options.pop('initial_policy_bridge')
    elif damage=='foreign-source':
        import hashlib,json
        owner=bridge['policyEvidence']['owner'];closed=bridge['policyEvidence']['completion']
        owner['sourceFiles']={'foreign-source.js':{'sha256':'f'*64,'mode':420,'size':1}}
        closed['sourceFiles']=copy.deepcopy(owner['sourceFiles'])
        closed['ownerDigest']=hashlib.sha256(json.dumps(owner,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    with pytest.raises(ValueError):failure_transition_audit_input(*values,**options)


@__import__('pytest').mark.parametrize('damage',['foreign','missing','extra','sha','mode','size'])
def test_sdk_refuses_rehashed_policy_source_change_before_transport(tmp_path,damage):
    import copy,hashlib,json,pytest
    from continuous_project_evidence import failure_transition_audit_input
    record,bridge,values=_command_policy_transition_fixture()
    payload=failure_transition_audit_input(*values,original_initialization_record=record,initial_policy_bridge=bridge)
    changed=payload['initialPolicyBridge'];evidence=changed['policyEvidence'];files=evidence['owner']['sourceFiles']
    key=next(iter(files))
    if damage=='foreign':files={'foreign-source.js':{'sha256':'f'*64,'mode':420,'size':1}}
    elif damage=='missing':files.pop(key)
    elif damage=='extra':files['foreign-source.js']={'sha256':'f'*64,'mode':420,'size':1}
    elif damage=='sha':files[key]['sha256']='f'*64
    elif damage=='mode':files[key]['mode']^=1
    elif damage=='size':files[key]['size']+=1
    evidence['owner']['sourceFiles']=files;evidence['completion']['sourceFiles']=copy.deepcopy(files)
    evidence['completion']['ownerDigest']=hashlib.sha256(json.dumps(evidence['owner'],separators=(',',':')).encode()).hexdigest()
    changed['sourceFiles']=copy.deepcopy(files)
    with pytest.raises(AssertionError):
        _run_memory_transition_audit(tmp_path,{'type':'choice','choice':'corrected','confidence':1,'probabilities':{'corrected':1}},audit_input=payload)
    assert not (tmp_path/'request.json').exists()


def test_initial_policy_caller_retains_both_arms_and_postlaunch_costs(monkeypatch,tmp_path):
    import copy,json,pytest
    from types import SimpleNamespace
    import live_continuous_project_learning as study
    record,bridge,_=_command_policy_transition_fixture()
    prior={**bridge['priorState'],'commandReviewInput':record['commandEvidence']}
    state={**bridge['currentState'],'policyReviewInput':bridge['policyEvidence']}
    proxy=SimpleNamespace(requests=0,jev_usage=[]);calls=[];settings=[]
    monkeypatch.setattr(study.base,'put',lambda c,path,raw:settings.append(json.loads(raw)))
    def launch(c,prompt,proxy,output,label,**options):
        proxy.requests+=2;proxy.jev_usage.append({'estimatedCostUsd':.001})
        calls.append((prompt,label,options))
        return {'exitCode':0,'seconds':2,'usage':{'totalTokens':3},'reportedCost':.1,'policyOrigin':{'verified':True}}
    def artifacts(c,proxy,path,**options):
        path.mkdir(parents=True,exist_ok=True)
        return copy.deepcopy(state if options.get('policy_origin') else prior)
    monkeypatch.setattr(study,'run_session',launch);monkeypatch.setattr(study,'artifacts',artifacts)
    from continuous_project_evidence import _native_initialization_proof
    def native_check(c,name,evidence,before,after):
        assert c=='owned'
        return _native_initialization_proof(name,evidence,before,after)
    monkeypatch.setattr(study,'native_initialization_proof',native_check)
    learner={};result=study.run_initial_policy('owned',proxy,tmp_path/'learner',prior=prior,row=learner,enabled=True)
    assert learner['initialPolicyBridge']['nativePolicyProof']['ready']
    assert learner['learning']==result and learner['initializationCalls'][0]['allTransportRequests']==2
    assert settings[-1]=={'autoMemory':True,'automaticPhases':{'memory':'off','harness':'apply','agents':'off'}}
    control={};study.run_initial_policy('control',proxy,tmp_path/'control',prior=prior,row=control,enabled=False)
    assert settings[-1]['autoMemory'] is False and 'initialPolicyBridge' not in control
    assert calls[0]==calls[1] and calls[0][0]==study.INITIAL_HARNESS_POLICY
    assert calls[0][2]=={'unlimited_budget':True,'capture_policy_origin':True}
    def fail(*args,**kwargs):proxy.requests+=1;raise OSError('postlaunch capture failed')
    monkeypatch.setattr(study,'run_session',fail)
    failed={}
    with pytest.raises(OSError):study.run_initial_policy('owned',proxy,tmp_path/'failed',prior=prior,row=failed,enabled=True)
    call=failed['initializationCalls'][0]
    assert call['sessionCaptureError']=='policy-call-exception' and call['allTransportRequests']==1
    total=study.totals({'stages':[{'arms':{'with-learning':{'inference':{'usage':{'totalTokens':0},'reportedCost':0,'seconds':0},**failed}}}]})
    assert total['with-learning']['unknownLeaderUsageAttempts']==1


def _bound_command_artifacts(tmp_path, *, policy=False, pi_version='1.3.0'):
    # Synthetic complete files exercise loading, never real model semantics.
    import hashlib,io,json,tarfile
    import live_continuous_project_learning as study
    from recovery_integrity import bind_study_artifact,source_archive_files
    if policy:
        record,bridge,_=_command_policy_transition_fixture()
        command={**bridge['policyEvidence'],'sources':record['sources'],'originalSession':''}
    else:command=_command_audit_fixture()['commandEvidence']
    owner={**command['owner'],'container':'owned','piVersion':pi_version}
    owner['sourceHashes']={name:hashlib.sha256(body.encode()).hexdigest()for name,body in command['sources'].items()}
    output=tmp_path/'command';output.mkdir()
    raw_owner=json.dumps(owner).encode()
    completion={**command['completion'],'ownerDigest':hashlib.sha256(raw_owner).hexdigest(),'sourceInventoryVerified':True}
    files={'memory-command-started.json':raw_owner,'memory-command-closed.json':json.dumps(completion).encode(),
           'original-session.jsonl':command['originalSession'].encode(),'session.jsonl':command['nativeSession'].encode(),
           'stdout.jsonl':command['stdout'].encode(),'stderr.txt':b''}
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w:gz') as archive:
        for name,body in command['sources'].items():
            raw=body.encode();member=tarfile.TarInfo(name);member.size=len(raw);member.mode=0o644
            archive.addfile(member,io.BytesIO(raw))
    raw_archive=stream.getvalue();source_files=source_archive_files(raw_archive)
    metadata={name:{key:entry[key] for key in ('sha256','mode','size')} for name,entry in source_files.items()}
    manifest={'archiveSha256':hashlib.sha256(raw_archive).hexdigest(),'files':metadata,'sourceHashes':owner['sourceHashes']}
    if policy:
        owner['sourceFiles']=metadata;completion['sourceFiles']=metadata;completion['sourceHashes']=owner['sourceHashes']
        raw_owner=json.dumps(owner).encode();completion['ownerDigest']=hashlib.sha256(raw_owner).hexdigest()
        files.pop('memory-command-started.json');files.pop('memory-command-closed.json')
        files['policy-started.json']=raw_owner;files['policy-closed.json']=json.dumps(completion).encode()
        command['owner']=owner;command['completion']=completion
    for phase in ('before','after'):
        prefix='command-source-'+phase+'/candidate-before-convergence'
        files[prefix+'.json']=json.dumps(manifest).encode();files[prefix+'.tar.gz']=raw_archive
    for name,raw in files.items():
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    inference={('policyOrigin' if policy else 'commandOrigin'):{'verified':True,'sourceInventoryVerified':True,'artifactBindings':{
        name:bind_study_artifact(output,name,bound=32*1024*1024) for name in (study.POLICY_ORIGIN_ARTIFACTS if policy else study.COMMAND_ORIGIN_ARTIFACTS)}}}
    root='runs/--work-p-limit--/'+command['reviewManifest']['runId']
    if policy:
        artifacts={root+'/manifest.json':json.dumps(command['reviewManifest']),root+'/snapshot.json':command['snapshotText'],
            root+'/harness-post-receipt.json':json.dumps(command['postReceipt']),root+'/harness-task-usage.json':json.dumps(command['usageLedger'])}
        return output,inference,artifacts,command
    audit='runs/--work-p-limit--/maintenance-audit-fixture'
    artifacts={root+'/manifest.json':json.dumps(command['reviewManifest']),root+'/plan.json':json.dumps(command['plan']),
        root+'/snapshot.json':command['snapshotText'],root+'/memory-task-usage.json':json.dumps(command['usageLedger']),
        audit+'/receipt.json':json.dumps(command['sourceAudit']['receipt']),
        audit+'/source-audit-usage.json':json.dumps(command['sourceAudit']['usageLedger']),
        audit+'/observations.jsonl':'\n'.join(json.dumps(row) for row in command['sourceAudit']['observations'])+'\n'}
    return output,inference,artifacts,command


@__import__('pytest').mark.parametrize('damage',['none','replaced','symlink','missing-binding','wrong-container','duplicate-ledger','missing-post','json-array','alias-path'])
def test_policy_origin_loader_binds_actual_native_generation(tmp_path,damage):
    import json,pytest
    import live_continuous_project_learning as study
    output,inference,artifacts,origin=_bound_command_artifacts(tmp_path,policy=True)
    container='owned'
    if damage=='replaced':
        file=output/'session.jsonl';raw=file.read_bytes();file.unlink();file.write_bytes(raw)
    elif damage=='symlink':
        file=output/'stderr.txt';file.unlink();file.symlink_to(output/'stdout.jsonl')
    elif damage=='missing-binding':inference['policyOrigin']['artifactBindings'].pop('stderr.txt')
    elif damage=='wrong-container':container='foreign'
    elif damage=='duplicate-ledger':artifacts['runs/--work-p-limit--/other/harness-task-usage.json']=json.dumps(origin['usageLedger'])
    elif damage=='missing-post':artifacts={name:body for name,body in artifacts.items()if not name.endswith('harness-post-receipt.json')}
    elif damage=='json-array':
        key=next(name for name in artifacts if name.endswith('harness-task-usage.json'));artifacts[key]='[]'
    elif damage=='alias-path':artifacts['./runs/--work-p-limit--/other.json']='{}'
    if damage!='none':
        with pytest.raises(ValueError):study.policy_review_input(output,inference,artifacts,container=container)
        return
    loaded=study.policy_review_input(output,inference,artifacts,container=container)
    for key in ('owner','completion','nativeSession','stdout','sources','receipt','snapshotText','reviewManifest','usageLedger','postReceipt'):
        assert loaded[key]==origin[key]
    assert loaded['usageLedgerPath'].endswith('/harness-task-usage.json')


@__import__('pytest').mark.parametrize('pi_version',['1.3.0','1.4.0'])
def test_command_origin_loader_keeps_complete_native_source_and_actual_ledgers(tmp_path,monkeypatch,pi_version):
    import live_continuous_project_learning as study
    output,inference,artifacts,command=_bound_command_artifacts(tmp_path,pi_version=pi_version)
    monkeypatch.setattr(study.base,'checked',lambda args,**kwargs:(pi_version+'\n').encode())
    loaded=study.command_review_input(output,inference,artifacts,container='owned')
    for key in ('originalSession','nativeSession','stdout','sources','receipt','snapshotText','plan','reviewManifest','sourceAudit','usageLedger'):
        assert loaded[key]==command[key]
    assert loaded['initialUsageLedger']==command['usageLedger']
    assert loaded['appliedUsageLedgerFile']=='memory-task-usage.json'


@__import__('pytest').mark.parametrize('damage',['replaced','symlink','missing-binding','wrong-container','json-array','alias-path','duplicate-ledger','missing-source'])
def test_command_origin_loader_refuses_changed_or_ambiguous_artifacts(tmp_path,monkeypatch,damage):
    import json,pytest
    import live_continuous_project_learning as study
    output,inference,artifacts,command=_bound_command_artifacts(tmp_path)
    monkeypatch.setattr(study.base,'checked',lambda args,**kwargs:b'1.3.0\n')
    container='owned'
    if damage=='replaced':
        file=output/'session.jsonl';raw=file.read_bytes();file.unlink();file.write_bytes(raw)
    elif damage=='symlink':
        file=output/'stderr.txt';file.unlink();file.symlink_to(output/'stdout.jsonl')
    elif damage=='missing-binding':inference['commandOrigin']['artifactBindings'].pop('stderr.txt')
    elif damage=='wrong-container':container='foreign'
    elif damage=='json-array':
        name=next(name for name in artifacts if name.endswith('/memory-task-usage.json'));artifacts[name]='[]'
    elif damage=='alias-path':
        artifacts['./runs/--work-p-limit--/extra.txt']='unexpected alias'
    elif damage=='duplicate-ledger':
        artifacts['runs/--work-p-limit--/other/memory-task-usage.json']=json.dumps(command['usageLedger'])
    elif damage=='missing-source':
        artifacts={name:body for name,body in artifacts.items() if not name.endswith('observations.jsonl')}
    with pytest.raises(ValueError):study.command_review_input(output,inference,artifacts,container=container)


@__import__('pytest').mark.parametrize('safety,record,confidence,passed',[(.95,.95,.8,True),(.94,.95,.8,False),(.99,.8,.8,False),(1,1,.79,False)])
def test_command_initialization_keeps_complete_source_corpus_and_joint_semantics(tmp_path,safety,record,confidence,passed):
    value=_command_audit_fixture()
    answers={key:{'type':'choice','choice':label,'confidence':confidence,'probabilities':{label:probability}}
             for key,label,probability in [('safety','safe',safety),('record','grounded',record)]}
    result,request,_=_run_memory_transition_audit(tmp_path,answers,audit_input=value)
    assert result['passed'] is passed
    assert request['model']=='jev-1.14.0' and set(request['questions'])=={'safety','record'}
    assert result['mutationAuthority'] is False and result['learningBenefitEstablished'] is False
    assert result['reviewedMemoryCorpusDigest']


@__import__('pytest').mark.parametrize('damage',['owner','source','corpus','history','receipt','pending','protocol','prior-memory','prior-history','prior-attempt','prior-surface'])
def test_command_initialization_refuses_incomplete_evidence_before_sdk(tmp_path,damage):
    import pytest
    value=_command_audit_fixture()
    if damage=='owner':value['commandEvidence'].pop('owner')
    elif damage=='source':value['commandEvidence']['sourceAudit']['observations']=[]
    elif damage=='corpus':value['currentState']['memoryEntries'][0]['content']+=' forged'
    elif damage=='history':value['currentState']['history']=[]
    elif damage=='receipt':value['currentState']['receipts']=[]
    elif damage=='pending':value['currentState']['pendingLearningJobs']=1
    elif damage=='protocol':value['protocol']['explicitCommandInitializationVersion']=2
    elif damage=='prior-memory':value['priorState']['memoryEntries']=[{'filename':'prior.md','content':'old knowledge'}]
    elif damage=='prior-history':value['priorState']['history']=[{'id':'old'}]
    elif damage=='prior-attempt':value['priorState']['attempts']=[{'receiptDigest':'old'}]
    elif damage=='prior-surface':value['priorState']['surfaceSnapshots']['private/old.md']={}
    with pytest.raises(AssertionError):_run_memory_transition_audit(tmp_path,{},audit_input=value)
    assert not (tmp_path/'request.json').exists()


def test_command_audit_runtime_installs_its_shared_adapter_without_tools_or_transport(monkeypatch):
    import live_continuous_project_learning as study
    files={}
    monkeypatch.setattr(study.base,'put',lambda container,path,body:files.update({path:body.decode()}))
    study.install_memory_audit_runtime('isolated')
    assert set(files)=={'/home/node/continuous-memory-audit.mts','/home/node/continuous-command-proof.mts'}
    assert "import('./continuous-command-proof.mts')" in files['/home/node/continuous-memory-audit.mts']
    assert "from '/opt/experiment/packages/continual-learning/extensions/incremental-learning.ts'" in files['/home/node/continuous-command-proof.mts']
    assert "from '/opt/experiment/packages/continual-learning/extensions/learning-replay-feedback.ts'" in files['/home/node/continuous-command-proof.mts']
    assert '../extensions/' not in ''.join(files.values())


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
    from continuous_project_evidence import INITIAL_NATIVE_VALIDATION
    prospective=copy.deepcopy(values)
    prospective[-1]['initialSourceRefusalRuntime']=copy.deepcopy(INITIAL_NATIVE_VALIDATION)
    boundary=failure_source_safety_audit_input(*prospective)['initialSourceBoundary']
    assert boundary['runtime']==INITIAL_NATIVE_VALIDATION
    assert boundary['bashCommands']==['node observed-idle-failure.mjs','pnpm test']
    assert boundary['readFiles']==sorted(prospective[3])
    assert boundary['trajectoryEligible'] is False and boundary['refusals']==[]
    assert boundary['taskSuccessEstablished'] is False and boundary['executionAuthorityChanged'] is False
    prospective[-1]['initialSourceRefusalRuntime']={}
    with __import__('pytest').raises(ValueError):failure_source_safety_audit_input(*prospective)
    from continuous_project_evidence import failure_record_audit_input
    with __import__('pytest').raises(ValueError):failure_record_audit_input(*values,diagnosis_only=True)
    # The clarified future prompt does not relax the existing native proof.
    # Neither an output-filter exit nor a prefixed command is the required
    # exact upstream observation, even after recomputing the session digest.
    for command in ('pnpm test | tail -n 60', 'CI=1 pnpm test', 'cd /work/p-limit && pnpm test'):
        changed=list(copy.deepcopy(_failure_record_fixture()))
        changed[1]=changed[0]
        changed_rows=[json.loads(line) for line in changed[4].splitlines()]
        for row in changed_rows:
            message=row.get('message',{})
            if message.get('role')=='assistant':
                for part in message.get('content',[]):
                    if part.get('type')=='toolCall' and part.get('id')=='upstream':
                        part['arguments']['command']=command
        changed[4]=('\n'.join(json.dumps(row) for row in changed_rows)+'\n').encode()
        changed[2]['sessionDigest']=hashlib.sha256(changed[4]).hexdigest()
        changed[2]['taskOutcome']={'passed':False,'failures':['verification-failed']}
        with __import__('pytest').raises(ValueError):
            failure_record_audit_input(*changed,diagnosis_only=True)
        assert failure_source_safety_audit_input(*changed)['observation']['taskOutcome']['passed'] is False


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
    command=copy.deepcopy(stage);command['arms']['with-learning']['failureMemoryAudit']['mode']='observed-command-memory-initialization'
    assert not initial_learning_continuation(command,verified_failure_learning=False,explicit_command_initialization=True)
    command['arms']['with-learning']['initialPolicyBridge']={'kind':'observed-policy-initialization-bridge',
        'nativePolicyProof':{'ready':True},'historyIntegrity':{'passed':True}}
    assert initial_learning_continuation(command,verified_failure_learning=False,explicit_command_initialization=True)
    assert command['arms']['with-learning']['passed'] is False and command['arms']['without-learning']['passed'] is False
    command['arms']['with-learning']['initialPolicyBridge']['nativePolicyProof']['ready']=False
    assert not initial_learning_continuation(command,verified_failure_learning=False,explicit_command_initialization=True)
    for arm in stage['arms']:
        damaged=copy.deepcopy(stage);damaged['arms'][arm]['failureMemoryAudit']['passed']=False
        assert not initial_learning_continuation(damaged,verified_failure_learning=True)
    stage['arms']['with-learning']['validLearning']=False
    assert not initial_learning_continuation(stage,verified_failure_learning=True)
    assert not initial_learning_continuation({'arms':{}},verified_failure_learning=True)


def test_held_control_initialization_keeps_independent_learner_but_stops_later_tasks():
    # Given a normally settled held control audit, When both isolated initial
    # arms run, Then skip control policy, retain its failure, and still inspect
    # the learner under its own gates. Neither arm can admit the later tasks.
    import ast,copy,inspect,json,pytest
    import live_continuous_project_learning as study
    from continuous_project_evidence import initial_learning_continuation
    function=next(node for node in ast.parse(inspect.getsource(study.run)).body if isinstance(node,ast.FunctionDef))
    blocks=[node for node in ast.walk(function) if isinstance(node,ast.If)
            and ast.unparse(node.test)=="audit.get('passed') is not True"]
    assert len(blocks)==1
    harness=ast.parse('''
stage={'arms':{}}
task={'id':'orientation'}
inference={'exitCode':0,'originalObservationsPreserved':True,'modelErrors':0,'modelAborted':0,'malformedSessionRows':0}
verification={'readOnlySourcePreserved':True,'existingChecksPreserved':True}
candidate={'sources':{'index.js':'public source'},'manifest':{'files':{'index.js':{'sha256':'unchanged','mode':420,'size':13}}}}
failure_input={'manifest':{'files':{'index.js':{'sha256':'unchanged','mode':420,'size':13}}}}
main_session=PUBLIC_SESSION
valid_learning_so_far=True
policies=[]
for arm in ('without-learning','with-learning'):
    row={'passed':False,'validPairInput':valid_learning_so_far}
    stage['arms'][arm]=row
    audit={'mode':'observed-failure-source-safety' if arm=='without-learning' else 'observed-command-memory-initialization','passed':arm=='with-learning','answers':{'safety':{'choice':'safe'}}}
    row['failureMemoryAudit']=audit
    PLACEHOLDER
    policies.append(arm)
    row['validLearning']=True
    row['initialPolicyBridge']={'kind':'observed-policy-initialization-bridge','nativePolicyProof':{'ready':True},'historyIntegrity':{'passed':True}}
''')
    loop=next(node for node in harness.body if isinstance(node,ast.For))
    index=next(i for i,node in enumerate(loop.body) if isinstance(node,ast.Expr)and isinstance(node.value,ast.Name)and node.value.id=='PLACEHOLDER')
    loop.body[index]=copy.deepcopy(blocks[0]);ast.fix_missing_locations(harness)
    session=('\n'.join(json.dumps(row)for row in [
        {'type':'session','cwd':'/work/p-limit'},
        {'message':{'role':'assistant','content':[{'type':'toolCall','id':'read','name':'read','arguments':{'path':'/work/p-limit/index.js'}}]}},
        {'message':{'role':'toolResult','toolCallId':'read','toolName':'read','isError':False,'content':[{'type':'text','text':'public source'}]}}])+'\n').encode()
    value={'PUBLIC_SESSION':session,'initial_control_hold_allows_independent_learner':study.initial_control_hold_allows_independent_learner,'json':json}
    exec(compile(harness,'actual-initial-audit-branch','exec'),value)
    stage=value['stage']
    assert value['policies']==['with-learning'] and value['valid_learning_so_far'] is False
    assert set(stage['arms'])=={'without-learning','with-learning'}
    assert stage['arms']['without-learning']['passed'] is False
    assert stage['arms']['without-learning']['failureMemoryAudit']=={'mode':'observed-failure-source-safety','passed':False,'answers':{'safety':{'choice':'safe'}}}
    assert stage['arms']['without-learning']['validLearning'] is False
    assert stage['arms']['with-learning']['validLearning'] is True and stage['arms']['with-learning']['validPairInput'] is False
    assert not initial_learning_continuation(stage,verified_failure_learning=False,explicit_command_initialization=True)
    assert stage['validPairInput'] is False and stage['arms']['without-learning']['validPairInput'] is False
    reversed_harness=copy.deepcopy(harness)
    reverse_loop=next(node for node in reversed_harness.body if isinstance(node,ast.For))
    reverse_loop.iter=ast.parse("('with-learning','without-learning')",mode='eval').body
    ast.fix_missing_locations(reversed_harness)
    events=[]
    reversed_values={'PUBLIC_SESSION':session,'initial_control_hold_allows_independent_learner':study.initial_control_hold_allows_independent_learner,
        'json':json,'print':lambda raw,**_kwargs:events.append(json.loads(raw))}
    exec(compile(reversed_harness,'learner-before-held-control','exec'),reversed_values)
    reverse_stage=reversed_values['stage']
    assert reversed_values['policies']==['with-learning'] and reversed_values['valid_learning_so_far'] is False
    assert events[0]['independentInitialArmPending'] is False
    assert all(row['validPairInput'] is False for row in reverse_stage['arms'].values())
    assert not initial_learning_continuation(reverse_stage,verified_failure_learning=False,explicit_command_initialization=True)
    failed_learner=copy.deepcopy(reversed_harness)
    failed_loop=next(node for node in failed_learner.body if isinstance(node,ast.For))
    failed_branch=next(i for i,node in enumerate(failed_loop.body)if isinstance(node,ast.If))
    failed_loop.body.insert(failed_branch,ast.parse("if arm=='with-learning':audit['passed']=False").body[0])
    ast.fix_missing_locations(failed_learner)
    failed_values={'PUBLIC_SESSION':session,'initial_control_hold_allows_independent_learner':study.initial_control_hold_allows_independent_learner,'json':json}
    with pytest.raises(RuntimeError):exec(compile(failed_learner,'failed-learner-stops-control','exec'),failed_values)
    assert failed_values['policies']==[] and set(failed_values['stage']['arms'])=={'with-learning'}
    assert failed_values['stage']['validPairInput'] is False
    assert failed_values['stage']['arms']['with-learning']['validPairInput'] is False
    for replacement in ("inference['modelErrors']=1", "verification['readOnlySourcePreserved']=False",
                        "candidate['manifest']['files']['index.js']['mode']=511", "main_session=b'incomplete'",
                        "inference['exitCode']=1", "inference['originalObservationsPreserved']=False",
                        "inference['sessionCaptureError']='missing'", "verification['existingChecksPreserved']=False"):
        damaged=copy.deepcopy(harness);damaged.body.insert(next(i for i,n in enumerate(damaged.body)if isinstance(n,ast.For)),ast.parse(replacement).body[0])
        ast.fix_missing_locations(damaged)
        values={'PUBLIC_SESSION':session,'initial_control_hold_allows_independent_learner':study.initial_control_hold_allows_independent_learner,'json':json}
        with pytest.raises(RuntimeError):exec(compile(damaged,'hard-initial-anomaly','exec'),values)
        assert values['policies']==[] and set(values['stage']['arms'])=={'without-learning'}
        assert values['stage']['validPairInput'] is False and values['stage']['arms']['without-learning']['validPairInput'] is False
    for replacement in ("audit['answers']['safety']['choice']='unsafe'", "audit['passed']=None", "audit['mode']='unknown'"):
        damaged=copy.deepcopy(harness);loop=next(node for node in damaged.body if isinstance(node,ast.For))
        branch=next(i for i,node in enumerate(loop.body)if isinstance(node,ast.If))
        loop.body.insert(branch,ast.parse(replacement).body[0]);ast.fix_missing_locations(damaged)
        values={'PUBLIC_SESSION':session,'initial_control_hold_allows_independent_learner':study.initial_control_hold_allows_independent_learner,'json':json}
        with pytest.raises(RuntimeError):exec(compile(damaged,'hard-audit-anomaly','exec'),values)
        assert values['policies']==[] and set(values['stage']['arms'])=={'without-learning'}
        assert values['stage']['validPairInput'] is False and values['stage']['arms']['without-learning']['validPairInput'] is False


def test_initial_public_source_trajectory_rejects_unknown_or_mutating_actions(tmp_path):
    import json
    from continuous_project_evidence import initial_source_actions_are_public
    sources={'index.js':'public source','test.js':'public test','package.json':'{}','observed-idle-failure.mjs':'public failure'}
    def session(name,args,*,failed=False):
        return ('\n'.join(json.dumps(row)for row in [
            {'type':'session','cwd':'/work/p-limit'},
            {'message':{'role':'assistant','content':[{'type':'toolCall','id':'one','name':name,'arguments':args}]}},
            {'message':{'role':'toolResult','toolCallId':'one','toolName':name,'isError':failed,'content':[{'type':'text','text':'public observation'}]}}])+'\n').encode()
    for name,args,failed in [('read',{'path':'index.js'},False),('bash',{'command':'ls /work/p-limit'},False),
            ('bash',{'command':'ls -la /work/p-limit'},False),('bash',{'command':'ls -Alh'},False),
            ('bash',{'command':'ls -la /work/p-limit && echo "---" && cat /work/p-limit/package.json'},False),
            ('bash',{'command':'cat index.js && echo "read complete" && grep -n idle test.js | head -5'},False),
            ('bash',{'command':'cat /work/p-limit/package.json'},False),('bash',{'command':'node observed-idle-failure.mjs'},True),
            ('bash',{'command':'pnpm test'},False),('bash',{'command':'grep -n "onIdle\\|clearQueue\\|idle" /work/p-limit/test.js | head -50'},False)]:
        assert initial_source_actions_are_public(session(name,args,failed=failed),sources)
    for name,args,failed in [('read',{'path':'/home/node/agent/auth.json'},False),('read',{'path':'index.js','cwd':'/private'},False),
            ('read',{'path':'/work/p-limit/node_modules/../package.json'},False),('read',{'path':'./index.js'},False),
            ('read',{'path':'/work/p-limit//index.js'},False),('read',{'path':'/work/p-limit/scripts/../index.js'},False),
            ('write',{'path':'index.js','content':'changed'},False),('bash',{'command':'cat /home/node/agent/auth.json'},False),
            ('bash',{'command':'cat /work/p-limit/node_modules/../package.json'},False),
            ('bash',{'command':'node -e "process.env"'},False),('bash',{'command':'pnpm test; cat /private/auth.json'},False),
            ('bash',{'command':'cat "$(printf /work/p-limit/index.js)"'},False),('bash',{'command':'grep -n x|rm /work/p-limit/test.js'},False),
            ('bash',{'command':'grep -n | /work/p-limit/test.js'},False),('bash',{'command':'grep -n -f/private/auth /work/p-limit/test.js'},False),
            ('bash',{'command':'ls /work/p-limit','cwd':'/private'},False),
            ('bash',{'command':'ls -R /work/p-limit'},False),('bash',{'command':'ls -L /work/p-limit'},False),
            ('bash',{'command':'ls -la /home/node/agent'},False),('bash',{'command':'ls -la /work/p-limit/.pi'},False),
            ('bash',{'command':'ls && cat /home/node/agent/auth.json'},False),
            ('bash',{'command':'cat /home/node/agent/auth.json && ls'},False),
            ('bash',{'command':'ls && rm index.js && cat package.json'},False),
            ('bash',{'command':'ls &&& cat package.json'},False),('bash',{'command':'ls & cat package.json'},False),
            ('bash',{'command':'ls || cat package.json'},False),('bash',{'command':'ls &&'},False),
            ('bash',{'command':'echo "&&" ls'},False),('bash',{'command':"echo '&&' cat package.json"},False),
            ('bash',{'command':r'echo \&\& ls'},False),('bash',{'command':'echo "&""&" ls'},False),
            ('bash',{'command':'echo hi # && cat index.js'},False),
            ('bash',{'command':'echo hi | cat /home/node/agent/auth.json'},False),
            ('bash',{'command':'grep -n |& index.js'},False),('bash',{'command':'grep -n & index.js'},False),
            ('bash',{'command':'grep -n &&& index.js'},False),
            ('bash',{'command':'grep -n needle index.js "|" head -5'},False),
            ('bash',{'command':r'grep -n needle index.js \| head -5'},False),
            ('bash',{'command':'echo ~ && cat package.json'},False),
            ('bash',{'command':'node observed-idle-failure.mjs && echo done'},True),
            ('bash',{'command':'pnpm test && echo done'},False),
            ('bash',{'command':'pnpm test'},True),('read',{'path':'index.js'},True)]:
        assert not initial_source_actions_are_public(session(name,args,failed=failed),sources)
    assert not initial_source_actions_are_public(b'incomplete',sources)
    # Given an intermediate symlink, '..' follows filesystem traversal rather
    # than the lexical parent. Never turn that path into an admitted public read.
    project=tmp_path/'project';foreign=tmp_path/'foreign'
    project.mkdir();(foreign/'child').mkdir(parents=True)
    (project/'package.json').write_text('public')
    (foreign/'package.json').write_text('foreign sentinel')
    (project/'node_modules').symlink_to(foreign/'child',target_is_directory=True)
    assert (project/'node_modules/../package.json').read_text()=='foreign sentinel'
    for prefix in ('','/work/p-limit/'):
        path=prefix+'node_modules/../package.json'
        for name,args in [('read',{'path':path}),('bash',{'command':'cat '+path}),('bash',{'command':'grep -n x '+path})]:
            assert not initial_source_actions_are_public(session(name,args),sources)
    import subprocess
    (project/'index.js').write_text('needle public\n');(project/'|').write_text('ordinary\n')
    (foreign/'package.json').write_text('needle foreign-sentinel\n')
    (project/'head').symlink_to(foreign/'package.json')
    quoted_pipe='grep -n needle index.js "|" head -5'
    probe=subprocess.run(['/bin/sh','-c',quoted_pipe],cwd=project,capture_output=True,text=True)
    assert probe.returncode==0 and 'needle foreign-sentinel' in probe.stdout
    assert not initial_source_actions_are_public(session('bash',{'command':quoted_pipe}),sources)


def test_native_schema_refusal_requires_exact_parent_runtime_and_public_trajectory():
    # Given the actual strict initial schema, When a public grep is refused
    # before execution, Then only a separately authenticated prospective runtime
    # can attribute that refusal; the original error and task hold stay intact.
    import copy,json
    from continuous_project_evidence import initial_source_actions_are_public
    sources={'index.js':'public source'}
    runtime={'version':1,'piVersion':'1.3.0','files':{
        'cli.js':'e79626f2dd6f94aa45d30f3fa63cd84319a6eefcd150b353cfaf274366926774',
        'cli-runtime.js':'f9811fa28c52accb8e2433499a85e857b714a002956005b7859ad00e5e35f380',
        'chunks/chunk-66G7ITPS.js':'0426becd43ff630d8c9129f5606b23d0a43d5c115334884c77aa6595035c8690',
        'chunks/chunk-RH6M5TBT.js':'2490522d0a2f4aae7353481a9ab4b0154ba038602b4f0997bb20659526c80340'}}
    schema={'type':'object','required':['command'],'properties':{'command':{'type':'string','enum':['node observed-idle-failure.mjs','pnpm test']},'timeout':{'type':'number'}},'additionalProperties':False}
    read={'type':'object','required':['path'],'properties':{'path':{'type':'string','enum':['index.js','/work/p-limit/index.js']},'offset':{'type':'integer','minimum':1},'limit':{'type':'integer','minimum':1}},'additionalProperties':False}
    rows=[{'type':'session','id':'native','cwd':'/work/p-limit'},
        {'type':'message','id':'definitions','parentId':None,'message':{'role':'system','toolsAdded':[{'name':'read','parameters':read},{'name':'bash','parameters':schema}]}},
        {'type':'message','id':'assistant','parentId':'definitions','message':{'role':'assistant','content':[{'type':'toolCall','id':'grep','name':'bash','arguments':{'command':'grep -n idle /work/p-limit/index.js | head -50'}}]}},
        {'type':'message','id':'result','parentId':'assistant','message':{'role':'toolResult','toolCallId':'grep','toolName':'bash','isError':True,'content':[{'type':'text','text':'Validation failed: command must be equal to one of the allowed values'}]}}]
    encode=lambda value: ('\n'.join(map(json.dumps,value))+'\n').encode()
    original=encode(rows)
    assert not initial_source_actions_are_public(original,sources)
    refusals=[]
    assert initial_source_actions_are_public(original,sources,native_validation=runtime,refusals=refusals)
    assert refusals==[{'toolCallId':'grep','assistantEntryId':'assistant','resultEntryId':'result','definitionEntryId':'definitions','outcome':'native-schema-refused','executed':False}]
    assert encode(rows)==original and rows[-1]['message']['isError'] is True
    from continuous_project_evidence import initial_control_hold_allows_independent_learner,initial_learning_continuation
    audit={'mode':'observed-failure-source-safety','passed':False,'answers':{'safety':{'choice':'safe','confidence':.49,'probabilities':{'safe':.66}}}}
    inference={'exitCode':0,'originalObservationsPreserved':True,'modelErrors':0,'modelAborted':0,'malformedSessionRows':0}
    verification={'readOnlySourcePreserved':True,'existingChecksPreserved':True}
    candidate={'sources':sources,'manifest':{'files':{'index.js':{'mode':420,'sha256':'unchanged'}}}}
    assert not initial_control_hold_allows_independent_learner(audit,inference,verification,candidate,candidate['manifest'],original)
    assert initial_control_hold_allows_independent_learner(audit,inference,verification,candidate,candidate['manifest'],original,native_validation=runtime)
    stage={'arms':{'without-learning':{'passed':False,'failureMemoryAudit':audit},'with-learning':{'validLearning':True,'failureMemoryAudit':{'mode':'observed-failure-record','passed':True}}}}
    assert not initial_learning_continuation(stage,verified_failure_learning=True)
    assert audit['passed'] is False and audit['answers']['safety']['probabilities']['safe']==.66
    drift=copy.deepcopy(candidate['manifest']);drift['files']['index.js']['mode']=511
    assert not initial_control_hold_allows_independent_learner(audit,inference,verification,candidate,drift,original,native_validation=runtime)
    for mutation in ('private','mutating','unknown','extra-argument','bad-timeout','runtime-error','unreachable-success','missing-schema','late-schema','duplicate-schema','removed-tool','fake-system','duplicate-call','duplicate-result','foreign-parent','changed-schema','early-result','arguments-error'):
        changed=copy.deepcopy(rows);args=changed[2]['message']['content'][0]['arguments']
        if mutation=='private':args['command']='cat /home/node/agent/auth.json'
        elif mutation=='mutating':args['command']='rm index.js'
        elif mutation=='unknown':args['command']='node -e process.env'
        elif mutation=='extra-argument':args['cwd']='/private'
        elif mutation=='bad-timeout':args['timeout']='10'
        elif mutation=='runtime-error':args['command']='pnpm test'
        elif mutation=='unreachable-success':changed[-1]['message']['isError']=False
        elif mutation=='arguments-error':changed[2]['message']['content'][0]['argumentsError']='incomplete input'
        elif mutation=='missing-schema':changed.pop(1)
        elif mutation=='late-schema':changed[1],changed[2]=changed[2],changed[1]
        elif mutation=='duplicate-schema':changed.insert(2,copy.deepcopy(changed[1]))
        elif mutation=='removed-tool':changed[1]['message']['toolsRemoved']=['bash']
        elif mutation=='fake-system':changed[1]['message']['role']='assistant'
        elif mutation=='duplicate-call':changed[2]['message']['content']*=2
        elif mutation=='duplicate-result':changed.append(copy.deepcopy(changed[-1]))
        elif mutation=='foreign-parent':changed[-1]['parentId']='foreign'
        elif mutation=='changed-schema':changed[1]['message']['toolsAdded'][1]['parameters']['additionalProperties']=True
        elif mutation=='early-result':
            changed[2],changed[3]=changed[3],changed[2]
            changed[2]['parentId']='definitions';changed[3]['parentId']='result'
        assert not initial_source_actions_are_public(encode(changed),sources,native_validation=runtime),mutation
    for invalid in (None,{},dict(runtime,piVersion='1.2.0'),dict(runtime,files={})):
        assert not initial_source_actions_are_public(original,sources,native_validation=invalid)
    assert not initial_source_actions_are_public(original,{'index.js':'public source','foreign.js':'extra'},native_validation=runtime)
    for command in ('node observed-idle-failure.mjs ', 'node "observed-idle-failure.mjs"', 'pnpm test '):
        refused_verifier=copy.deepcopy(rows)
        refused_verifier[2]['message']['content'][0]['arguments']['command']=command
        assert not initial_source_actions_are_public(encode(refused_verifier),sources,native_validation=runtime)
    successful=copy.deepcopy(rows)
    successful[2]['message']['content'][0].update(name='read',arguments={'path':'index.js'})
    successful[-1]['message'].update(toolName='read',isError=False)
    assert initial_source_actions_are_public(encode(successful),sources,native_validation=runtime)
    for key,value in [('offset',True),('offset',0),('limit','1'),('limit',-1)]:
        invalid_read=copy.deepcopy(successful)
        invalid_read[2]['message']['content'][0]['arguments'][key]=value
        assert not initial_source_actions_are_public(encode(invalid_read),sources,native_validation=runtime)
    for invalid in ({},dict(runtime,piVersion='1.2.0'),dict(runtime,files={})):
        assert not initial_source_actions_are_public(encode(successful),sources,native_validation=invalid)


def test_automatic_initial_control_audit_stops_before_unavailable_dependent_work():
    # Given a closed control audit, When the actual automatic initial branch
    # runs, Then unavailable/unsafe evidence stops before another paid arm.
    # A normal safe-choice numeric hold can still inspect the isolated learner,
    # but the failed pair and all costs remain unchanged.
    import ast,copy,inspect,json,pytest
    import live_continuous_project_learning as study
    from continuous_project_evidence import initial_learning_continuation
    function=ast.parse(inspect.getsource(study.run)).body[0]
    blocks=[node for node in ast.walk(function) if isinstance(node,ast.If)
        and ast.unparse(node.test).startswith("verified_failure_learning and index == 0 and (arm == 'without-learning')")]
    assert len(blocks)==1
    harness=ast.parse('''
stage={'arms':{},'validPairInput':True}
protocol={}
task={'id':'orientation'}
index=0
verified_failure_learning=True
inference={'exitCode':0,'originalObservationsPreserved':True,'modelErrors':0,'modelAborted':0,'malformedSessionRows':0}
verification={'readOnlySourcePreserved':True,'existingChecksPreserved':True}
candidate={'sources':{'index.js':'public source'},'manifest':{'files':{'index.js':{'sha256':'unchanged','mode':420,'size':13}}}}
failure_input={'manifest':{'files':{'index.js':{'sha256':'unchanged','mode':420,'size':13}}}}
main_session=PUBLIC_SESSION
valid_learning_so_far=True
calls=[]
for arm in ('without-learning','with-learning'):
    calls.append(arm)
    failure_audit=copy.deepcopy(AUDIT) if arm=='without-learning' else {'passed':True}
    stage['arms'][arm]={'passed':False,'validPairInput':valid_learning_so_far,'validLearning':True,
        'failureMemoryAudit':failure_audit,'inference':{'reportedCost':.01},'retainedEvidence':'original'}
    PLACEHOLDER
''')
    loop=next(node for node in harness.body if isinstance(node,ast.For))
    marker=next(i for i,node in enumerate(loop.body)if isinstance(node,ast.Expr)and isinstance(node.value,ast.Name)and node.value.id=='PLACEHOLDER')
    loop.body[marker]=copy.deepcopy(blocks[0]);ast.fix_missing_locations(harness)
    session=('\n'.join(json.dumps(row)for row in [
        {'type':'session','cwd':'/work/p-limit'},
        {'message':{'role':'assistant','content':[{'type':'toolCall','id':'read','name':'read','arguments':{'path':'/work/p-limit/index.js'}}]}},
        {'message':{'role':'toolResult','toolCallId':'read','toolName':'read','isError':False,'content':[{'type':'text','text':'public source'}]}}])+'\n').encode()
    safe={'mode':'observed-failure-source-safety','passed':False,'answers':{'safety':{'choice':'safe'}}}
    for audit,stop,valid in [
        ({'mode':'observed-failure-source-safety','passed':False,'reason':'unavailable'},True,False),
        ({'passed':False,'reason':'incomplete-bound-failure-evidence'},True,False),
        ({**safe,'answers':{'safety':{'choice':'unsafe'}}},True,False),
        ({**safe,'passed':None},True,False),
        ({**safe,'mode':'unknown'},True,False),
        (None,True,False),
        (safe,False,False),
        ({**safe,'passed':True},False,True),
    ]:
        values={'PUBLIC_SESSION':session,'AUDIT':audit,'copy':copy,
            'initial_control_hold_allows_independent_learner':study.initial_control_hold_allows_independent_learner}
        if stop:
            with pytest.raises(RuntimeError):exec(compile(harness,'actual-automatic-control-audit','exec'),values)
        else:exec(compile(harness,'actual-automatic-control-audit','exec'),values)
        assert values['calls']==(['without-learning'] if stop else ['without-learning','with-learning'])
        control=values['stage']['arms']['without-learning']
        assert control['failureMemoryAudit']==audit and control['passed'] is False
        assert control['inference']=={'reportedCost':.01} and control['retainedEvidence']=='original'
        assert values['stage']['validPairInput'] is valid and control['validPairInput'] is valid
        assert values['valid_learning_so_far'] is valid
        assert not initial_learning_continuation(values['stage'],verified_failure_learning=True)


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
    def held_command(*args,**kwargs):raise study.UnappliedMemoryCommand('No applied Memory')
    monkeypatch.setattr(study,'command_review_input',held_command)
    held=study.artifacts('owned-fixture',None,tmp_path/'held-command',source_review=True,command_origin=(tmp_path,{}))
    assert held['commandInitializationHeld'] is True and 'commandReviewInput' not in held
    assert held['knownLearningCost']==.4 and held['receipts'] and held['actualLearningOperations']==1
    def corrupt_command(*args,**kwargs):raise ValueError('Invalid native origin')
    monkeypatch.setattr(study,'command_review_input',corrupt_command)
    with __import__('pytest').raises(ValueError,match='Invalid native origin'):
        study.artifacts('owned-fixture',None,tmp_path/'corrupt-command',source_review=True,command_origin=(tmp_path,{}))


def test_scoped_storage_protocol_keeps_execution_rules_in_both_actual_session_inputs(monkeypatch, tmp_path) -> None:
    # Given unchanged historical execution boundaries and actual future tasks,
    # When opting into a separate storage-scope cohort, Then both arm inputs get
    # the same scope clarification without removing rules or knowledge requests.
    import copy
    import json
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace
    import live_continuous_project_learning as study
    from continuous_project_tasks import COMMON, UNLIMITED_COMMON, STORAGE_SCOPED_UNLIMITED_COMMON, TASKS, failure_first_tasks
    historical=copy.deepcopy(TASKS)
    assert STORAGE_SCOPED_UNLIMITED_COMMON.startswith(UNLIMITED_COMMON)
    assert 'not themselves a request to persist' in STORAGE_SCOPED_UNLIMITED_COMMON
    assert 'source-established applicability conditions' in STORAGE_SCOPED_UNLIMITED_COMMON
    assert 'Optional source-grounded learning' in STORAGE_SCOPED_UNLIMITED_COMMON
    assert 'explicit durable Memory or Harness requests' in STORAGE_SCOPED_UNLIMITED_COMMON
    assert 'temporary-only and no-remember' in STORAGE_SCOPED_UNLIMITED_COMMON
    assert STORAGE_SCOPED_UNLIMITED_COMMON not in COMMON
    assert 'not themselves a request to persist' not in UNLIMITED_COMMON
    sent=[]
    def process(args, **_kwargs):
        if args[1]=='cp':
            Path(args[-1]).write_text(json.dumps({'type':'message','message':{'role':'assistant','content':[],
                'usage':{'totalTokens':0},'stopReason':'stop'}})+'\n')
        elif args[1]=='exec':sent.append(args[-1])
        return subprocess.CompletedProcess(args,0,b'',b'')
    monkeypatch.setattr(study.base,'process',process)
    monkeypatch.setattr(study.base,'shell',lambda *_args,**_kwargs:b'')
    # The prospective immutable owner selects this exact common prompt. Existing
    # run_session owns ordinary input, feedback input and command separation.
    monkeypatch.setattr(study,'UNLIMITED_COMMON',STORAGE_SCOPED_UNLIMITED_COMMON)
    proxy=SimpleNamespace(key='fixture-key',jev_key=None,token='fixture-token',
        selection={'provider':'fixture','model':'fixture'},jev_environment=lambda:{})
    prompt=failure_first_tasks()[0]['prompt']
    for arm in ('without-learning','with-learning'):
        study.run_session('fixture-container',prompt,proxy,tmp_path/arm,'stage-0',unlimited_budget=True)
    assert sent==[STORAGE_SCOPED_UNLIMITED_COMMON+prompt]*2
    assert 'Permanent project constraint' in prompt and 'npm must be blocked' in prompt
    assert 'necessary limits for future maintenance' in prompt
    assert TASKS==historical
    assert any('temporary formatting request' in t['prompt'] for t in TASKS)


def test_memory_command_pure_proofs_bind_explicit_parent_runtime_version():
    # Given complete controlled command evidence, the caller's actual runtime
    # must match the owner. Rehashing a foreign owner cannot bypass the binding.
    import json
    from support import run_bun
    record=_command_audit_fixture()
    result=run_bun('''
      import {createHash} from 'node:crypto';
      import {commandMemoryCorpusProof,commandMemorySourceProof} from './packages/continual-learning/tests/continuous-command-proof.ts';
      const record=RECORD;
      const test=(ownerVersion,runtimeVersion)=>{
        const input=structuredClone(record.commandEvidence);input.owner.piVersion=ownerVersion;
        input.completion.ownerDigest=createHash('sha256').update(JSON.stringify(input.owner)).digest('hex');
        return {source:commandMemorySourceProof(input,runtimeVersion).ready,
          corpus:commandMemoryCorpusProof(input,record.priorState,record.currentState,runtimeVersion).ready};
      };
      console.log(JSON.stringify({legacy:test('1.3.0',undefined),fresh:test('1.4.0','1.4.0'),
        oldOwner:test('1.3.0','1.4.0'),oldRuntime:test('1.4.0','1.3.0'),unknown:test('1.5.0','1.5.0')}));
    '''.replace('RECORD',json.dumps(record)))
    assert result['legacy']==result['fresh']=={'source':True,'corpus':True}
    assert all(result[name]=={'source':False,'corpus':False} for name in ('oldOwner','oldRuntime','unknown'))


@__import__('pytest').mark.parametrize('actual',['1.3.0','1.4.0','1.5.0'])
def test_memory_owned_proof_selects_runtime_only_from_caller_container(monkeypatch,actual):
    import json,pytest
    import live_continuous_project_learning as study
    calls=[]
    def checked(args,**kwargs):
        calls.append((args,kwargs))
        if '--version' in args:return (actual+'\n').encode()
        if 'tsx' in args:return b'{"ready":true}'
        return b''
    monkeypatch.setattr(study.base,'checked',checked)
    evidence={'owner':{'container':'owned','piVersion':'untrusted-version'}}
    if actual=='1.5.0':
        with pytest.raises(ValueError):study.native_initialization_proof('owned','commandMemoryCorpusProof',evidence,{},{})
        assert len(calls)==1
    else:
        assert study.native_initialization_proof('owned','commandMemoryCorpusProof',evidence,{},{}).get('ready')
        assert calls[0][0]==['docker','exec','owned','node',study.base.PI,'--version']
        assert json.loads(calls[1][1]['data'])['runtimeVersion']==actual
        assert 'x.runtimeVersion' in calls[2][1]['data'].decode()
        assert all('untrusted-version' not in str(args) for args,_ in calls)


@__import__('pytest').mark.parametrize('owner_version,actual_version,expected',[
    ('1.3.0','1.4.0',None),('1.4.0','1.3.0',None),('1.4.0','1.5.0',None),
    ('1.4.0','1.4.0','1.3.0'),('1.4.0','1.4.0','1.5.0')])
def test_memory_origin_loader_rejects_runtime_owner_or_expected_mismatch(tmp_path,monkeypatch,owner_version,actual_version,expected):
    import pytest
    import live_continuous_project_learning as study
    output,inference,_,_=_bound_command_artifacts(tmp_path,pi_version=owner_version)
    calls=[]
    def checked(args,**kwargs):
        calls.append(args)
        assert args==['docker','exec','owned','node',study.base.PI,'--version']
        return (actual_version+'\n').encode()
    monkeypatch.setattr(study.base,'checked',checked)
    with pytest.raises(ValueError):study.load_command_origin(output,inference,container='owned',expected_pi_version=expected)
    assert len(calls)==(0 if expected=='1.5.0' else 1)


@__import__('pytest').mark.parametrize('actual,expected',[('1.3.0','1.4.0'),('1.4.0','1.3.0'),('1.5.0','1.4.0'),('1.4.0','1.5.0')])
def test_native_memory_capture_rejects_runtime_before_model_launch(tmp_path,monkeypatch,actual,expected):
    import hashlib,json,pytest
    from types import SimpleNamespace
    import live_continuous_project_learning as study
    prefix=(json.dumps({'type':'session','id':'source','cwd':'/work/p-limit'})+'\n').encode()
    proxy=SimpleNamespace(key='fixture-key',jev_key=None,token='fixture-token',
        selection={'provider':'fixture','model':'fixture'},jev_environment=lambda:{})
    calls=[]
    monkeypatch.setattr(study,'read_command_session',lambda *args:prefix)
    monkeypatch.setattr(study.base,'shell',lambda *args,**kwargs:b'')
    monkeypatch.setattr(study.base,'checked',lambda args,**kwargs:(actual+'\n').encode())
    monkeypatch.setattr(study.base,'process',lambda *args,**kwargs:calls.append(args))
    with pytest.raises((ValueError,RuntimeError)):
        study.run_session('owned','/memory inspect source',proxy,tmp_path/'command','stage-0',command=True,
            prior_session_digest=hashlib.sha256(prefix).hexdigest(),capture_command_origin=True,expected_pi_version=expected)
    assert calls==[]
