from support import run_bun


def test_study_budget_removes_tools_after_last_result_and_blocks_batch_overflow() -> None:
    value = run_bun(r'''
      import {installStudyToolBudget} from './packages/continual-learning/tests/continuous-tool-budget.ts';
      const handlers={},loadouts=[],entries=[];
      installStudyToolBudget({on:(name,fn)=>handlers[name]=fn,setActiveTools:tools=>loadouts.push(tools),appendEntry:(customType,data)=>entries.push({customType,data})},2);
      const first=await handlers.tool_call({toolCallId:'one'});
      await handlers.tool_result({toolCallId:'one'});
      const before=loadouts.length;
      const second=await handlers.tool_call({toolCallId:'two'});
      const excess=await handlers.tool_call({toolCallId:'three'});
      await handlers.tool_result({toolCallId:'two'});
      // A new agent turn must not reset this CLI invocation's resource budget.
      if(handlers.agent_start)await handlers.agent_start({});
      const later=await handlers.tool_call({toolCallId:'four'});
      console.log(JSON.stringify({first,second,before,excess,later,loadouts,entries}));
    ''')
    assert value['before'] == 0
    assert value.get('first') is None and value.get('second') is None
    assert value['excess']['block'] and value['later']['block']
    assert value['loadouts'] and all(tools == [] for tools in value['loadouts'])
    assert any(row['data']['outcome'] == 'tools-removed' for row in value['entries'])
    assert sum(row['data']['outcome'] == 'blocked' for row in value['entries']) == 2


@__import__("pytest").mark.parametrize("repeat_tools", [False, True])
def test_real_pi_removes_next_turn_tools_and_never_executes_batch_overflow(tmp_path, repeat_tools) -> None:
    import json
    import subprocess
    from pathlib import Path
    from live_acceptance_support import isolated_environment, workspace_pi
    from support import REPO
    project, agent = tmp_path/'project', tmp_path/'agent'
    project.mkdir(); agent.mkdir()
    (agent/'settings.json').write_text('{"packages":[],"quietStartup":true}')
    session=tmp_path/'session.jsonl'
    command=[workspace_pi(REPO),'--offline','--no-extensions','--no-context-files','--no-skills',
             '--no-prompt-templates','--no-themes','--no-approve','--thinking','off','--tools','bash',
             '-e',str(Path(__file__).with_name('continuous-tool-budget-fixture.ts')),
             '--model','study-budget-fixture/deterministic','--session',str(session),'--print','--mode','json','inspect']
    env=isolated_environment(tmp_path,agent)
    if repeat_tools:env['STUDY_BUDGET_REPEAT_TOOLS']='1'
    result=subprocess.run(command,cwd=project,env=env,capture_output=True,timeout=10)
    assert result.returncode == 0, result.stderr.decode()
    rows=[json.loads(line) for line in session.read_text().splitlines()]
    provider=[r['data'] for r in rows if r.get('customType')=='study-budget-provider']
    assert provider == [{'call':1,'tools':['bash']},{'call':2,'tools':[]}]
    assert (project/'one').read_text() == 'observed'
    assert (project/'two').read_text() == 'observed'
    assert not (project/'forbidden').exists()
    assert any(r.get('customType')=='continuous-study-tool-budget' and r['data']['outcome']=='blocked' for r in rows)
    # Retain the original task tool observations in the same real session.
    assert sum(r.get('message',{}).get('role')=='toolResult' for r in rows) == (4 if repeat_tools else 3)
    if repeat_tools:
        assert any(r.get('customType')=='continuous-study-tool-budget' and r['data']['outcome']=='summary-tool-loop-stopped' for r in rows)


def test_budget_counts_reused_tool_ids_as_new_calls() -> None:
    value = run_bun(r'''
      import {installStudyToolBudget} from './packages/continual-learning/tests/continuous-tool-budget.ts';
      const handlers={},entries=[];
      installStudyToolBudget({on:(name,fn)=>handlers[name]=fn,setActiveTools:()=>{},appendEntry:(_type,data)=>entries.push(data)},2);
      await handlers.tool_call({toolCallId:'reused'});
      await handlers.tool_call({toolCallId:'reused'});
      const third=await handlers.tool_call({toolCallId:'reused'});
      console.log(JSON.stringify({third,entries}));
    ''')
    assert value['third']['block']
    assert value['entries'][-1] == {'limit':2,'admitted':2,'outcome':'blocked'}


@__import__("pytest").mark.parametrize("outcome", ["blocked", "summary-tool-loop-stopped"])
def test_runner_retains_budget_failure_and_does_not_cap_backfill_workers(monkeypatch, tmp_path, outcome) -> None:
    import json
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace
    import live_continuous_project_learning as study
    proxy=SimpleNamespace(key='fixture',jev_key=None,token='fixture',selection={'provider':'fixture','model':'fixture'},jev_environment=lambda:{})
    commands=[]
    def process(args, **_kwargs):
        if args[1]=='exec':commands.append(args)
        if args[1]=='cp':Path(args[-1]).write_text(json.dumps({'type':'custom','customType':'continuous-study-tool-budget','data':{'limit':18,'admitted':18,'outcome':outcome}}))
        return subprocess.CompletedProcess(args,0,b'',b'')
    monkeypatch.setattr(study.base,'process',process)
    monkeypatch.setattr(study.base,'shell',lambda *_args,**_kwargs:b'')
    task=study.run_session('container','inspect',proxy,tmp_path/'task','stage-0')
    study.run_session('container','/consolidate backfill',proxy,tmp_path/'backfill','recovery-0',command=True)
    assert task['toolBudgetExceeded'] and task['toolBudgetEvents'][0]['outcome']==outcome
    assert '/home/node/continuous-tool-budget.ts' in commands[0]
    assert '/home/node/continuous-tool-budget.ts' not in commands[1]


def test_verifier_boundary_rejects_pagination_and_preserves_single_full_read() -> None:
    value=run_bun(r'''import {installStudyToolBudget} from './packages/continual-learning/tests/continuous-tool-budget.ts';
      const handlers={},entries=[],loadouts=[];let aborted=0;
      installStudyToolBudget({on:(name,fn)=>handlers[name]=fn,setActiveTools:t=>loadouts.push(t),appendEntry:(_type,data)=>entries.push(data)},1,'/verification.json');
      const ctx={abort:()=>aborted++};
      const call=(id,path,extra={})=>handlers.tool_call({toolCallId:id,toolName:'read',input:{path,...extra}},ctx);
      const wrong=await call('source','index.js');
      const paginated=await call('page','/verification.json',{limit:10});
      const full=await call('full','/verification.json');
      await handlers.tool_result({toolCallId:'full'});
      const repeated=await call('repeat','/verification.json');
      console.log(JSON.stringify({wrong,paginated,full,repeated,entries,loadouts,aborted}));''')
    assert value['wrong']['block'] and value['paginated']['block']
    assert value.get('full') is None and value['repeated']['block']
    assert value['aborted']==0
    assert all(row['admitted']==0 for row in value['entries'] if row['outcome']=='verifier-read-blocked')
    assert value['loadouts'] and all(tools==[] for tools in value['loadouts'])


def test_verifier_abort_cannot_admit_a_later_inflight_valid_read() -> None:
    value=run_bun(r'''import {installStudyToolBudget} from './packages/continual-learning/tests/continuous-tool-budget.ts';
      const handlers={},entries=[];let aborted=0;
      installStudyToolBudget({on:(name,fn)=>handlers[name]=fn,setActiveTools:()=>{},appendEntry:(_type,data)=>entries.push(data)},1,'/verification.json');
      const ctx={abort:()=>aborted++};
      for(let i=0;i<3;i++)await handlers.tool_call({toolCallId:'wrong'+i,toolName:'read',input:{path:'index.js'}},ctx);
      const late=await handlers.tool_call({toolCallId:'late',toolName:'read',input:{path:'/verification.json'}},ctx);
      console.log(JSON.stringify({late,aborted,entries}));''')
    assert value['aborted']==1 and value['late']['block']
    assert all(row['admitted']==0 for row in value['entries'])


def test_removed_budget_sets_explicit_no_tool_choice_only_on_empty_openai_requests() -> None:
    value = run_bun(r'''
      import {installStudyToolBudget} from './packages/continual-learning/tests/continuous-tool-budget.ts';
      const handlers={};let active=['read'];
      installStudyToolBudget({on:(name,fn)=>handlers[name]=fn,appendEntry:()=>{},setActiveTools:tools=>active=tools,getActiveTools:()=>active},1);
      const request={messages:[{role:'tool',tool_call_id:'past',content:'observed'}],tools:[]};
      const ctx={model:{api:'openai-completions'}};
      const before=handlers.before_provider_request?.({payload:request},ctx);
      handlers.tool_call({toolCallId:'one'});handlers.tool_result({toolCallId:'one'});
      const after=handlers.before_provider_request?.({payload:request},ctx);
      const other=handlers.before_provider_request?.({payload:request},{model:{api:'anthropic-messages'}});
      const conflicting=handlers.before_provider_request?.({payload:{...request,tools:[{type:'function',function:{name:'unexpected'}}]}},ctx);
      console.log(JSON.stringify({before,after,other,conflicting,request}));
    ''')
    assert value.get('before') is None
    assert value.get('after', {}).get('tool_choice') == 'none'
    assert value['after']['messages'] == value['request']['messages']
    assert value['after']['tools'] == []
    assert 'tool_choice' not in value['request']
    assert value.get('other') is None
    assert value.get('conflicting') is None
