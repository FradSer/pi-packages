from support import run_bun


def test_real_pi_keeps_learning_credentials_out_of_bash_without_disabling_parent_review(tmp_path) -> None:
    import json
    import subprocess
    from pathlib import Path
    from live_acceptance_support import isolated_environment, workspace_pi
    from support import REPO
    # Given the same parent credential and the original V69 environment command,
    # When native Bash executes, Then only its child environment loses the key.
    # The parent must still authenticate actual SDK requests; secret evidence
    # in the unisolated control must remain refused without a review request.
    results = []
    credential = 'CL_BASH_LEARNING_SECRET_0123456789'
    for isolated in (False, True):
        root = tmp_path / ('isolated' if isolated else 'control')
        project, agent = root/'project', root/'agent'
        project.mkdir(parents=True); agent.mkdir()
        (agent/'settings.json').write_text('{"packages":[],"quietStartup":true}')
        session = root/'session.jsonl'
        args = [workspace_pi(REPO),'--offline','--no-extensions','--no-context-files','--no-skills',
                '--no-prompt-templates','--no-themes','--no-approve','--thinking','off','--tools','bash',
                '-e',str(Path(__file__).with_name('continuous-tool-budget-fixture.ts'))]
        if isolated:
            args += ['-e',str(Path(__file__).with_name('continuous-bash-environment.ts'))]
        args += ['--model','study-budget-fixture/deterministic','--session',str(session),'--print','--mode','json','inspect']
        env = isolated_environment(root,agent)
        env.update(STUDY_BASH_ENVIRONMENT_PROBE='1', TYPESAFE_API_KEY=credential)
        result = subprocess.run(args,cwd=project,env=env,capture_output=True,timeout=20)
        assert result.returncode == 0, result.stderr.decode()
        rows = [json.loads(line) for line in session.read_text().splitlines()]
        proof = [r['data'] for r in rows if r.get('customType') == 'study-bash-environment-proof']
        assert len(proof) == 1
        observations = [r['message'] for r in rows if r.get('message',{}).get('role') == 'toolResult']
        assert len(observations) == 1 and observations[0]['isError'] is False
        output = json.dumps(observations)
        assert 'PI_MODEL=deterministic' in output
        assert proof[0]['parentCredentialAvailable']
        assert proof[0]['observationSensitive'] is (not isolated)
        if isolated:
            assert credential not in output and 'TYPESAFE_API_KEY' not in output
            assert proof[0]['authenticatedRequests'] > 0 and proof[0]['decision'] == 'allow'
        else:
            assert credential in output
            assert proof[0]['authenticatedRequests'] == 0 and proof[0]['decision'] == 'propose'
        results.append(next(r['data']['tools'] for r in rows if r.get('customType') == 'study-bash-environment-wire'))
    assert results[0] == results[1]


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


def test_actual_pi_verifier_wire_declares_exact_full_read_and_rejects_a_foreign_call(tmp_path) -> None:
    import json
    import subprocess
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from pathlib import Path
    from live_acceptance_support import isolated_environment, workspace_pi
    from support import REPO
    project, agent = tmp_path/'project', tmp_path/'agent'
    project.mkdir(); agent.mkdir()
    verifier = tmp_path/'complete observation.json'
    verifier.write_text('{"observed":true}\n')
    outside = project/'unrelated.txt'
    outside.write_text('foreign content must not be read')
    requests = []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(body)
            call = len(requests)
            if call <= 2:
                target = str(outside if call == 1 else verifier)
                delta = {'tool_calls': [{'index': 0, 'id': f'read-{call}', 'type': 'function',
                         'function': {'name': 'read', 'arguments': json.dumps({'path': target})}}]}
                finish = 'tool_calls'
            else:
                delta = {'content': 'Observed complete verification; no further tools.'}
                finish = 'stop'
            frames = [dict(id='fixture', object='chat.completion.chunk', model='fixed', choices=[{'index': 0, 'delta': delta, 'finish_reason': None}]),
                      dict(id='fixture', object='chat.completion.chunk', model='fixed', choices=[{'index': 0, 'delta': {}, 'finish_reason': finish}], usage={'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2})]
            output = ''.join('data: '+json.dumps(frame)+'\n\n' for frame in frames)+'data: [DONE]\n\n'
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(output.encode())))
            self.end_headers()
            self.wfile.write(output.encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    (agent/'settings.json').write_text('{"packages":[],"retry":{"enabled":false}}')
    (agent/'models.json').write_text(json.dumps({'providers': {'fixture': {
        'baseUrl': f'http://127.0.0.1:{server.server_port}/v1', 'api': 'openai-completions',
        'apiKey': 'public-offline-fixture', 'models': [{'id': 'fixed', 'name': 'fixed',
        'reasoning': False, 'input': ['text'], 'contextWindow': 100000, 'maxTokens': 4096,
        'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}]}}}))
    session = tmp_path/'session.jsonl'
    command = [workspace_pi(REPO), '--offline', '--no-extensions', '--no-context-files', '--no-skills',
               '--no-prompt-templates', '--no-themes', '--no-approve', '--thinking', 'off', '--tools', 'read',
               '-e', str(Path(__file__).with_name('continuous-tool-budget.ts')), '--model', 'fixture/fixed',
               '--session', str(session), '--print', '--mode', 'json', 'continue']
    env = isolated_environment(tmp_path, agent)
    env.update(PI_STUDY_TASK_TOOL_LIMIT='1', PI_STUDY_VERIFIER_FILE=str(verifier))
    try:
        result = subprocess.run(command, cwd=project, env=env, capture_output=True, timeout=15)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    assert result.returncode == 0, result.stderr.decode()
    assert len(requests) == 3
    for body in requests[:2]:
        assert len(body['tools']) == 1
        parameters = body['tools'][0]['function']['parameters']
        assert parameters['properties']['path']['enum'] == [str(verifier)]
        assert set(parameters['properties']) == {'path'}
        assert parameters['required'] == ['path'] and parameters['additionalProperties'] is False
    assert requests[-1].get('tools', []) == [] and requests[-1]['tool_choice'] == 'none'
    rows = [json.loads(line) for line in session.read_text().splitlines()]
    results = [row['message'] for row in rows if row.get('message', {}).get('role') == 'toolResult']
    assert len(results) == 2 and results[0]['isError'] is True and results[1]['isError'] is False
    assert all('foreign content must not be read' not in json.dumps(body) for body in requests)
    assert any('{"observed":true}' in json.dumps(message).replace('\\"', '"') for message in results)


def test_verifier_schema_changes_only_tools_and_execution_rejects_extra_fields() -> None:
    value = run_bun(r'''
      import {installStudyToolBudget} from './packages/continual-learning/tests/continuous-tool-budget.ts';
      const payload={messages:[{role:'user',content:'continue'},{role:'tool',content:'complete original observation',tool_call_id:'original'}],tools:[{type:'function',function:{name:'read',description:'Native read',parameters:{type:'object',properties:{path:{type:'string'},offset:{type:'number'},limit:{type:'number'}},required:['path']}}}],stream:true};
      const original=JSON.stringify(payload),outputs=[],guards=[];
      for(const arm of ['without-learning','with-learning']){
        const handlers={};installStudyToolBudget({on:(name,fn)=>handlers[name]=fn,appendEntry:()=>{},setActiveTools:()=>{},getActiveTools:()=>['read']},1,'/bound verification.json');
        outputs.push(handlers.before_provider_request({payload},{model:{api:'openai-completions'}}));
        guards.push(handlers.tool_call({toolCallId:arm,toolName:'read',input:{path:'/bound verification.json',encoding:'utf8'}},{abort:()=>{}}));
      }
      const ordinary={};installStudyToolBudget({on:(name,fn)=>ordinary[name]=fn},18);
      console.log(JSON.stringify({outputs,guards,originalUnchanged:original===JSON.stringify(payload),messagesSame:outputs.every(out=>out.messages===payload.messages),toolsOnly:outputs.every(out=>JSON.stringify({...out,tools:payload.tools})===original),ordinary:ordinary.before_provider_request({payload},{model:{api:'openai-completions'}})}));
    ''')
    assert value['originalUnchanged'] and value['messagesSame'] and value['toolsOnly']
    assert value['outputs'][0] == value['outputs'][1]
    assert all(row['block'] for row in value['guards'])
    assert value.get('ordinary') is None


def test_unlimited_tasks_keep_feedback_read_boundary_and_independent_workers(monkeypatch, tmp_path) -> None:
    # Given explicit unlimited study authorization, When either arm runs a task,
    # Then only the task resource cap is removed; feedback still admits one read.
    import hashlib
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace
    import live_continuous_project_learning as study
    from continuous_project_tasks import UNLIMITED_COMMON
    proxy = SimpleNamespace(key='fixture', jev_key=None, token='fixture', selection={'provider':'fixture','model':'fixture'}, jev_environment=lambda:{})
    commands = []
    def process(args, **kwargs):
        if args[1] == 'exec':
            commands.append(args)
            assert kwargs['timeout'] == study.UNLIMITED_CLI_GUARDIAN_SECONDS
        if args[1] == 'cp':
            Path(args[-1]).write_bytes(b'')
        return subprocess.CompletedProcess(args, 0, b'', b'')
    monkeypatch.setattr(study.base, 'process', process)
    monkeypatch.setattr(study.base, 'shell', lambda *_a, **_k: b'')
    monkeypatch.setattr(study.base, 'put', lambda *_a, **_k: None)
    monkeypatch.setattr(study.base, 'checked', lambda *_a, **_k: b'')
    study.run_session('container', 'inspect', proxy, tmp_path/'task', 'stage-0', unlimited_budget=True)
    study.run_session('container', 'read verifier', proxy, tmp_path/'feedback', 'stage-0', unlimited_budget=True,
                      feedback_observation={'sessionDigest':hashlib.sha256(b'').hexdigest()})
    study.run_session('container', '/consolidate backfill', proxy, tmp_path/'backfill', 'recovery', command=True, unlimited_budget=True)
    assert '/home/node/continuous-tool-budget.ts' not in commands[0]
    assert commands[0][-1] == UNLIMITED_COMMON + 'inspect'
    assert '/home/node/continuous-task-deadline.ts' in commands[0]
    assert '/home/node/continuous-task-deadline.ts' in commands[1]
    assert '/home/node/continuous-task-deadline.ts' not in commands[2]
    assert '/home/node/continuous-bash-environment.ts' in commands[0]
    assert all('/home/node/continuous-bash-environment.ts' not in command for command in commands[1:])
    assert '18 tool calls' not in commands[0][-1]
    assert '/home/node/continuous-tool-budget.ts' in commands[1]
    assert 'PI_STUDY_TASK_TOOL_LIMIT=1' in commands[1]
    assert '/home/node/continuous-verifier-reference.ts' in commands[1]
    assert '/home/node/continuous-tool-budget.ts' not in commands[2]


def test_real_pi_unlimited_task_keeps_tools_after_eighteen_results(tmp_path) -> None:
    # Given no task-count intervention, When native Pi finishes twenty calls,
    # Then all observations stay in one session and later turns retain Bash.
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
               '-e',str(Path(__file__).with_name('continuous-unlimited-fixture.ts')),
               '--model','study-budget-fixture/deterministic','--session',str(session),'--print','--mode','json','inspect']
    result = subprocess.run(command,cwd=project,env=isolated_environment(tmp_path,agent),capture_output=True,timeout=30)
    assert result.returncode == 0, result.stderr.decode()
    rows = [json.loads(line) for line in session.read_text().splitlines()]
    assert [r['data'] for r in rows if r.get('customType')=='study-budget-provider'] == [
        {'call':i,'tools':['bash']} for i in range(1,22)]
    results = [r['message'] for r in rows if r.get('message',{}).get('role')=='toolResult']
    assert len(results) == 20 and all(r.get('isError') is False for r in results)
    assert all((project/f'result-{i}').read_text()=='observed' for i in range(1,21))
    assert not any(r.get('customType')=='continuous-study-tool-budget' for r in rows)
