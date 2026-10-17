from support import run_bun


def test_main_deadline_closes_before_learning_without_reset_or_late_abort() -> None:
    # Given a task settles before its 900-second bound, When slow learning starts,
    # Then its independent worker deadlines own cancellation, not the main timer.
    value = run_bun(r'''
      import {installStudyTaskDeadline} from './packages/continual-learning/tests/continuous-task-deadline.ts';
      const callbacks=[],cleared=[],events=[],handlers={};let aborted=0;
      globalThis.setTimeout=(fn,ms)=>{callbacks.push({fn,ms});return callbacks.length};
      globalThis.clearTimeout=id=>cleared.push(id);
      const pi={on:(name,fn)=>handlers[name]=fn,appendEntry:(_type,data)=>events.push(data)};
      installStudyTaskDeadline(pi);
      const ctx={abort:()=>aborted++};
      handlers.before_agent_start({},ctx);handlers.before_agent_start({},ctx);
      handlers.agent_settled({},ctx);
      callbacks[0].fn(); // Already queued callbacks must not abort the learner.
      handlers.session_shutdown({},ctx);
      console.log(JSON.stringify({callbacks:callbacks.map(x=>x.ms),cleared,events,aborted}));
    ''')
    assert value['callbacks'] == [900000]
    assert value['aborted'] == 0
    assert value['cleared'] == [1]
    assert [e['stage'] for e in value['events']] == ['started', 'settled']


def test_expired_main_is_failure_and_blocks_late_tools() -> None:
    value = run_bun(r'''
      import {installStudyTaskDeadline} from './packages/continual-learning/tests/continuous-task-deadline.ts';
      const callbacks=[],events=[],handlers={};let aborted=0;
      globalThis.setTimeout=fn=>{callbacks.push(fn);return 1};globalThis.clearTimeout=()=>{};
      installStudyTaskDeadline({on:(name,fn)=>handlers[name]=fn,appendEntry:(_type,data)=>events.push(data)});
      const ctx={abort:()=>aborted++};handlers.before_agent_start({},ctx);
      callbacks[0]();callbacks[0]();handlers.agent_settled({},ctx);
      const late=handlers.tool_call({},ctx);
      console.log(JSON.stringify({events,aborted,late}));
    ''')
    assert value['aborted'] == 1 and value['late']['block']
    assert [e['stage'] for e in value['events']] == ['started', 'expired']


def test_deadline_failure_cannot_become_a_successful_task() -> None:
    from continuous_project_evidence import task_outcome
    out = task_outcome({'exitCode':0,'taskDeadlineExceeded':True}, {'passed':True})
    assert not out['passed'] and 'task-deadline-exceeded' in out['failures']


@__import__('pytest').mark.parametrize('expire_main', [False, True])
def test_native_pi_main_deadline_and_learning_cancellation_have_separate_owners(tmp_path, expire_main) -> None:
    import json
    import subprocess
    from pathlib import Path
    from live_acceptance_support import isolated_environment, workspace_pi
    from support import REPO
    project, agent = tmp_path/'project', tmp_path/'agent'
    project.mkdir(); agent.mkdir()
    (agent/'settings.json').write_text('{"packages":[],"quietStartup":true}')
    session = tmp_path/'session.jsonl'
    command = [workspace_pi(REPO),'--offline','--no-extensions','--no-context-files','--no-skills',
               '--no-prompt-templates','--no-themes','--no-approve','--thinking','off','--tools','bash',
               '-e',str(Path(__file__).with_name('continuous-deadline-fixture.ts')),
               '--model','study-budget-fixture/deterministic','--session',str(session),'--print','--mode','json','inspect']
    env = isolated_environment(tmp_path, agent)
    if expire_main:env['STUDY_DEADLINE_EXPIRE_MAIN']='1'
    result = subprocess.run(command,cwd=project,env=env,capture_output=True,timeout=30)
    assert result.returncode == 0, result.stderr.decode()
    rows = [json.loads(x) for x in session.read_text().splitlines()]
    events = [r['data'] for r in rows if r.get('customType')=='continuous-study-task-deadline']
    assert [e['stage'] for e in events] == ['started', 'expired' if expire_main else 'settled']
    assert all(e['limitMs']==900000 for e in events)
    results = [r['message'] for r in rows if r.get('message',{}).get('role')=='toolResult']
    assert len(results) == (1 if expire_main else 20)
    relevant = [r for r in rows if r.get('customType') in ('continuous-study-task-deadline','study-deadline-learner')]
    assert [(r['customType'],r['data']['stage']) for r in relevant][-3:] == [
        ('continuous-study-task-deadline','expired' if expire_main else 'settled'),
        ('study-deadline-learner','started'),('study-deadline-learner','closed')]


def test_parent_requires_complete_deadline_lifecycle_and_rejects_aborted_success() -> None:
    from continuous_project_evidence import task_deadline_evidence, task_outcome
    def event(stage, elapsed=0, **extra):
        return {'type':'custom','customType':'continuous-study-task-deadline',
                'data':{'stage':stage,'limitMs':900000,'elapsedMs':elapsed,**extra}}
    valid = [event('started'),event('settled',100)]
    assert not task_deadline_evidence(valid, required=True)['taskDeadlineMissing']
    for rows in ([valid[1]],valid+[valid[1]],
                 [{'type':'custom','customType':'continuous-study-task-deadline','data':{'limitMs':900000,'elapsedMs':0}},valid[1]],[event('started'),event('settled',-1)],
                 [event('started'),event('settled',100,limitMs=1)],
                 [event('started'),{**event('settled',100),'type':'message'}],
                 [event('started'),event('settled',100,elapsedMs=True)]):
        assert task_deadline_evidence(rows,required=True)['taskDeadlineMissing']
    late = task_deadline_evidence([event('started'),event('settled',900001)],required=True)
    assert late['taskDeadlineExceeded'] and late['taskDeadlineMissing']
    expired = task_deadline_evidence([event('started'),event('expired',1)],required=True)
    assert expired['taskDeadlineExceeded']
    assert not task_deadline_evidence([],required=False)['taskDeadlineMissing']
    assert not task_outcome({'exitCode':0,'modelAborted':1},{'passed':True})['passed']
