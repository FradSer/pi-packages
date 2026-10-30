from support import run_bun
import pytest


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


@pytest.mark.parametrize("boundary", ["verifier", "initial-source"])
def test_actual_pi_verifier_wire_declares_exact_full_read_and_rejects_a_foreign_call(tmp_path, boundary) -> None:
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
    (project/'index.js').write_text('{"observed":true}\n')
    requests = []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(body)
            call = len(requests)
            if call <= 2:
                target = str(outside) if call == 1 else ('index.js' if boundary == 'initial-source' else str(verifier))
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
               '--no-prompt-templates', '--no-themes', '--no-approve', '--thinking', 'off', '--tools', 'read,bash' if boundary == 'initial-source' else 'read',
               '-e', str(Path(__file__).with_name('continuous-bash-environment.ts' if boundary == 'initial-source' else 'continuous-tool-budget.ts')), '--model', 'fixture/fixed',
               '--session', str(session), '--print', '--mode', 'json', 'continue']
    env = isolated_environment(tmp_path, agent)
    if boundary == 'initial-source':
        env['PI_STUDY_INITIAL_SOURCE_FILES'] = json.dumps(['index.js'])
    else:
        env.update(PI_STUDY_TASK_TOOL_LIMIT='1', PI_STUDY_VERIFIER_FILE=str(verifier))
    try:
        result = subprocess.run(command, cwd=project, env=env, capture_output=True, timeout=15)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    assert result.returncode == 0, result.stderr.decode()
    assert len(requests) == 3
    for body in requests[:2]:
        if boundary == 'initial-source':
            tools = {t['function']['name']: t['function'] for t in body['tools']}
            assert set(tools) == {'read', 'bash'}
            assert tools['bash']['parameters']['properties']['command']['enum'] == ['node observed-idle-failure.mjs', 'pnpm test']
            assert tools['read']['parameters']['properties']['path']['enum'] == ['index.js', '/work/p-limit/index.js']
            assert 'verification commands' in tools['bash']['description']
            assert 'declared public project file' in tools['read']['description']
            continue
        assert len(body['tools']) == 1
        parameters = body['tools'][0]['function']['parameters']
        assert parameters['properties']['path']['enum'] == [str(verifier)]
        assert set(parameters['properties']) == {'path'}
        assert parameters['required'] == ['path'] and parameters['additionalProperties'] is False
    if boundary == 'verifier':
        assert requests[-1].get('tools', []) == [] and requests[-1]['tool_choice'] == 'none'
    rows = [json.loads(line) for line in session.read_text().splitlines()]
    if boundary == 'initial-source':
        definitions = {t['name']: t for row in rows for t in row.get('message', {}).get('toolsAdded', [])}
        wire = {t['function']['name']: t['function'] for t in requests[0]['tools']}
        assert all(definitions[name]['description'] == wire[name]['description'] and definitions[name]['parameters'] == wire[name]['parameters'] for name in ('read', 'bash'))
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


def test_initial_source_boundary_blocks_environment_and_artifact_discovery() -> None:
    """Given V121 metadata discovery, When requested, Then parent blocks before execution in both arms."""
    value = run_bun(r'''
      import {installInitialSourceBoundary} from './packages/continual-learning/tests/continuous-bash-environment.ts';
      const handlers={},entries=[];
      installInitialSourceBoundary({on:(n,f)=>handlers[n]=f,appendEntry:(n,d)=>entries.push({n,d})},['index.js','observed-idle-failure.mjs','package.json']);
      const call=(toolName,input)=>handlers.tool_call({toolName,input,toolCallId:'x'});
      const allowed=[call('read',{path:'index.js'}),call('read',{path:'/work/p-limit/index.js',offset:1,limit:10}),call('bash',{command:'pnpm test'}),call('bash',{command:'node observed-idle-failure.mjs'})];
      const denied=[call('bash',{command:"env | grep -iE 'memory|harness|plugin|PI_' | sed 's/=.*/=<set>/'"}),call('bash',{command:'ls -a /work/p-limit'}),call('bash',{command:'pnpm test; env'}),call('read',{path:'/home/node/agent/settings.json'}),call('read',{path:'.memory/MEMORY.md'}),call('read',{path:'./index.js'}),call('write',{path:'index.js',content:'changed'})];
      const payload={messages:[],tools:[{type:'function',function:{name:'bash',parameters:{}}},{type:'function',function:{name:'read',parameters:{}}}]};
      const wire=handlers.before_provider_request({payload},{model:{api:'openai-completions'}});
      console.log(JSON.stringify({allowed:allowed.map(x=>x??null),denied,entries,wire}));
    ''')
    assert value['allowed'] == [None]*4
    assert all(row['block'] for row in value['denied'])
    assert len(value['entries']) == 7
    schemas = {row['function']['name']: row['function']['parameters'] for row in value['wire']['tools']}
    assert schemas['bash']['properties']['command']['enum'] == ['node observed-idle-failure.mjs', 'pnpm test']
    assert '/home/node/agent/settings.json' not in schemas['read']['properties']['path']['enum']


def test_source_examples_boundary_allows_only_declared_public_files_and_native_examples(tmp_path) -> None:
    """Given a v2 source task, Then exact examples are writable without granting general shell access."""
    import json
    value = run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {installSourceTaskBoundary} from './packages/continual-learning/tests/continuous-bash-environment.ts';
      const root=process.env.TEST_SOURCE_ROOT;fs.mkdirSync(path.join(root,'examples'));
      fs.writeFileSync(path.join(root,'index.js'),'public');
      const handlers={},entries=[];
      const config={version:2,readPaths:['index.js'],writePaths:['examples/native-wrapper-v1.js'],commands:['node examples/native-wrapper-v1.js']};
      const parameters=installSourceTaskBoundary({on:(n,f)=>handlers[n]=f,appendEntry:(n,d)=>entries.push({n,d})},config,root);
      const call=(toolName,input)=>handlers.tool_call({toolName,input,toolCallId:'call'});
      const allowed=[];allowed.push(await call('write',{path:'examples/native-wrapper-v1.js',content:'before'}));
      fs.writeFileSync(path.join(root,'examples/native-wrapper-v1.js'),'before');
      allowed.push(await call('edit',{path:path.join(root,'examples/native-wrapper-v1.js'),edits:[{oldText:'before',newText:'after'}]}));
      allowed.push(await call('read',{path:'examples/native-wrapper-v1.js'}));
      allowed.push(await call('read',{path:'index.js',offset:1,limit:2}));
      allowed.push(await call('bash',{command:'node examples/native-wrapper-v1.js'}));
      const denied=[];
      for(const [name,input] of [['write',{path:'index.js',content:'no'}],['write',{path:'examples/other.js',content:'no'}],['write',{path:'examples/native-wrapper-v2.js',content:'no'}],['read',{path:'/etc/passwd'}],['read',{path:'.pi/config.json'}],['read',{path:'../index.js'}],['read',{path:'./index.js'}],['bash',{command:'node examples/native-wrapper-v1.js; env'}],['bash',{command:'env'}],['bash',{command:'node examples/native-wrapper-v2.js'}],['read',{path:'index.js',limit:0}],['write',{path:'examples/native-wrapper-v1.js',content:'no',extra:true}]])denied.push(await call(name,input));
      fs.unlinkSync(path.join(root,'examples/native-wrapper-v1.js'));fs.symlinkSync(path.join(root,'index.js'),path.join(root,'examples/native-wrapper-v1.js'));
      denied.push(await call('write',{path:'examples/native-wrapper-v1.js',content:'no'}));
      denied.push(await call('read',{path:'examples/native-wrapper-v1.js'}));
      denied.push(await call('bash',{command:'node examples/native-wrapper-v1.js'}));
      fs.unlinkSync(path.join(root,'examples/native-wrapper-v1.js'));fs.rmdirSync(path.join(root,'examples'));fs.symlinkSync(root,path.join(root,'examples'));
      denied.push(await call('write',{path:'examples/native-wrapper-v1.js',content:'no'}));
      const wire=[];for(const api of ['openai-completions','openai-responses']){
        const tools=Object.keys(parameters).map(name=>api==='openai-responses'?{type:'function',name,parameters:{}}:{type:'function',function:{name,parameters:{}}});
        wire.push(handlers.before_provider_request({payload:{tools,messages:[],input:[]}},{model:{api}}));
      }
      console.log(JSON.stringify({allowed:allowed.map(x=>x??null),denied,entries,parameters,wire}));
    ''', {'TEST_SOURCE_ROOT': str(tmp_path)})
    assert value['allowed'] == [None]*5
    assert all(result['block'] for result in value['denied'])
    assert all(row['d']['version'] == 2 for row in value['entries'])
    assert value['parameters']['bash']['properties']['command']['enum'] == ['node examples/native-wrapper-v1.js']
    for wire in value['wire']:
        for tool in wire['tools']:
            tool = tool.get('function', tool)
            assert tool['parameters'] == value['parameters'][tool['name']]
    assert value['parameters']['write']['properties']['path']['enum'] == ['examples/native-wrapper-v1.js', str(tmp_path/'examples/native-wrapper-v1.js')]
    assert value['parameters']['edit']['properties']['path'] == value['parameters']['write']['properties']['path']
    assert set(value['parameters']['read']['properties']['path']['enum']) == {'index.js',str(tmp_path/'index.js'),'examples/native-wrapper-v1.js',str(tmp_path/'examples/native-wrapper-v1.js')}


@pytest.mark.parametrize('override', [
    {'version':1}, {'root':'/foreign'}, {'writePaths':['index.js']},
    {'writePaths':['examples/../native-wrapper-v1.js']}, {'readPaths':['.pi/settings.json']},
    {'readPaths':['/foreign/index.js']}, {'commands':['env']},
    {'commands':['node examples/native-wrapper-v2.js']}, {'readPaths':['index.js','index.js']},
])
def test_source_examples_boundary_rejects_invalid_configuration(tmp_path, override) -> None:
    import json
    value = run_bun(r'''
      import {installSourceTaskBoundary} from './packages/continual-learning/tests/continuous-bash-environment.ts';
      let rejected=false;try{installSourceTaskBoundary({on:()=>{},appendEntry:()=>{}},JSON.parse(process.env.TEST_SOURCE_CONFIG),process.env.TEST_SOURCE_ROOT)}catch{rejected=true}
      console.log(JSON.stringify({rejected}));
    ''', {'TEST_SOURCE_ROOT':str(tmp_path), 'TEST_SOURCE_CONFIG':json.dumps({
        'version':2,'readPaths':['index.js'],'writePaths':['examples/native-wrapper-v1.js'],
        'commands':['node examples/native-wrapper-v1.js'],**override})})
    assert value['rejected']


def test_source_examples_launcher_uses_explicit_stage_and_keeps_ordinary_tools(monkeypatch, tmp_path) -> None:
    import json,subprocess
    from pathlib import Path
    from types import SimpleNamespace
    import live_continuous_project_learning as study
    proxy=SimpleNamespace(key='fixture',jev_key=None,token='fixture',selection={'provider':'fixture','model':'fixture'},jev_environment=lambda:{})
    commands=[]
    def process(args, **_kwargs):
        if args[1]=='exec':commands.append(args)
        if args[1]=='cp':Path(args[-1]).write_bytes(b'')
        return subprocess.CompletedProcess(args,0,b'',b'')
    monkeypatch.setattr(study.base,'process',process)
    monkeypatch.setattr(study.base,'shell',lambda *_a,**_k:b'')
    config={'version':2,'readPaths':['index.js'],'writePaths':['examples/native-wrapper-v1.js'],'commands':['node examples/native-wrapper-v1.js']}
    for label in ('source-v1','source-v2'):
        stage_config=json.loads(json.dumps(config).replace('wrapper-v1','wrapper-'+label.removeprefix('source-')))
        study.run_session('owned','inspect',proxy,tmp_path/label,label,source_task_boundary=stage_config,expected_pi_version='1.4.0')
    study.run_session('owned','implement',proxy,tmp_path/'use','use-v1')
    for stage,command in enumerate(commands[:2],1):
        assert command[command.index('--tools')+1]=='read,bash,edit,write'
        assert 'PI_STUDY_SOURCE_TASK_BOUNDARY='+json.dumps(config,separators=(',',':')).replace('wrapper-v1','wrapper-v'+str(stage)) in command
        assert not any(x.startswith('PI_STUDY_INITIAL_SOURCE_FILES=') for x in command)
    assert commands[2][commands[2].index('--tools')+1]=='read,bash,edit,write'
    assert not any(x.startswith('PI_STUDY_SOURCE_TASK_BOUNDARY=') for x in commands[2])
    for label,options in [('stage-0',{}),('source-v2',{}),('source-v1',{'command':True}),('source-v2',{'feedback_observation':{}}),('source-v1',{'initial_source_paths':['index.js']})]:
        with pytest.raises(ValueError,match='[Ss]ource'):
            study.run_session('owned','inspect',proxy,tmp_path/'invalid',label,source_task_boundary=config,**options)


@pytest.mark.parametrize('responses_api',[False,True])
def test_actual_pi_source_examples_create_edit_read_run_and_reject_symlinks(tmp_path,responses_api) -> None:
    """Given native Pi and a loopback provider, Then registered schemas and actual execution share the v2 boundary."""
    import json,subprocess,threading
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from pathlib import Path
    from live_acceptance_support import isolated_environment,workspace_pi
    from support import REPO
    from test_planner_json_output import _stream_responses_fixture
    project,agent=tmp_path/'project',tmp_path/'agent'
    project.mkdir();agent.mkdir()
    (project/'index.js').write_text('export const value=1;\n')
    private=tmp_path/'private.txt';private.write_text('PRIVATE_SOURCE_SENTINEL')
    example=project/'examples/native-wrapper-v1.js'
    config={'version':2,'readPaths':['index.js'],'writePaths':['examples/native-wrapper-v1.js'],
            'commands':['node examples/native-wrapper-v1.js','pnpm test']}
    requests=[]
    actions=[('write',{'path':'examples/native-wrapper-v1.js','content':'console.log("before");\n'}),
             ('edit',{'path':'examples/native-wrapper-v1.js','edits':[{'oldText':'before','newText':'after'}]}),
             ('read',{'path':'examples/native-wrapper-v1.js'}),
             ('bash',{'command':'node examples/native-wrapper-v1.js'}),
             ('write',{'path':'examples/native-wrapper-v1.js','content':'forbidden'}),
             ('read',{'path':'examples/native-wrapper-v1.js'}),
             ('bash',{'command':'node examples/native-wrapper-v1.js'}),
             ('write',{'path':'examples/foreign.js','content':'forbidden'}),
             ('read',{'path':str(private)}),
             ('bash',{'command':'env'})]
    class Provider(BaseHTTPRequestHandler):
        def log_message(self,*_args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));requests.append(body)
            call=len(requests)
            if call==5:
                example.unlink();example.symlink_to(private)
            if call>len(actions):
                if responses_api:
                    _stream_responses_fixture(self,body,'Completed controlled source boundary check.');return
                delta={'content':'Completed controlled source boundary check.'};finish='stop'
            else:
                name,arguments=actions[call-1]
                delta={'tool_calls':[{'index':0,'id':f'call-{call}','type':'function',
                       'function':{'name':name,'arguments':json.dumps(arguments)}}]};finish='tool_calls'
            if responses_api:
                item={'id':f'fc_{call}','type':'function_call','call_id':f'call-{call}','name':name,'arguments':'','status':'in_progress'}
                complete={**item,'arguments':json.dumps(arguments),'status':'completed'}
                response={'id':f'resp_{call}','object':'response','created_at':1,'model':'fixed','status':'in_progress','output':[]}
                events=[{'type':'response.created','response':response},
                        {'type':'response.output_item.added','output_index':0,'item':item},
                        {'type':'response.function_call_arguments.delta','item_id':item['id'],'output_index':0,'delta':complete['arguments']},
                        {'type':'response.function_call_arguments.done','item_id':item['id'],'output_index':0,'arguments':complete['arguments']},
                        {'type':'response.output_item.done','output_index':0,'item':complete},
                        {'type':'response.completed','response':{**response,'status':'completed','output':[complete],
                         'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2,'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':0}}}}]
                wire=''.join('event: '+event['type']+'\ndata: '+json.dumps({**event,'sequence_number':i})+'\n\n' for i,event in enumerate(events))
            else:
                frames=[dict(id='fixture',object='chat.completion.chunk',model='fixed',choices=[{'index':0,'delta':delta,'finish_reason':None}]),
                        dict(id='fixture',object='chat.completion.chunk',model='fixed',choices=[{'index':0,'delta':{},'finish_reason':finish}],usage={'prompt_tokens':1,'completion_tokens':1,'total_tokens':2})]
                wire=''.join('data: '+json.dumps(frame)+'\n\n' for frame in frames)+'data: [DONE]\n\n'
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(wire.encode())));self.end_headers();self.wfile.write(wire.encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Provider);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    (agent/'settings.json').write_text('{"packages":[],"retry":{"enabled":false}}')
    (agent/'models.json').write_text(json.dumps({'providers':{'fixture':{'baseUrl':f'http://127.0.0.1:{server.server_port}/v1',
        'api':'openai-responses' if responses_api else 'openai-completions','apiKey':'public-loopback-only',
        'models':[{'id':'fixed','reasoning':False,'input':['text'],'contextWindow':100000,'maxTokens':4096,
                   'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0}}]}}}))
    session=tmp_path/'session.jsonl'
    args=[workspace_pi(REPO),'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates',
          '--no-themes','--no-approve','--thinking','off','--tools','read,bash,edit,write',
          '-e',str(Path(__file__).with_name('continuous-bash-environment.ts')),'--model','fixture/fixed',
          '--session',str(session),'--print','--mode','json','Run the controlled source task.']
    env=isolated_environment(tmp_path,agent);env['PI_STUDY_SOURCE_TASK_BOUNDARY']=json.dumps(config)
    try:process=subprocess.run(args,cwd=project,env=env,capture_output=True,timeout=25)
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
    assert process.returncode==0,process.stderr.decode()
    assert len(requests)==len(actions)+1
    rows=[json.loads(line) for line in session.read_text().splitlines()]
    definitions={tool['name']:tool for row in rows for tool in row.get('message',{}).get('toolsAdded',[])}
    for body in requests:
        wire={tool['name']:tool for tool in (row if responses_api else row['function'] for row in body['tools'])}
        assert set(wire)=={'read','bash','edit','write'}
        assert all(definitions[name]['description']==wire[name]['description'] and definitions[name]['parameters']==wire[name]['parameters'] for name in wire)
        assert wire['bash']['parameters']['properties']['command']['enum']==config['commands']
        assert wire['write']['parameters']['properties']['path']['enum']==['examples/native-wrapper-v1.js',str(example)]
    results=[row['message'] for row in rows if row.get('message',{}).get('role')=='toolResult']
    assert [result['isError'] for result in results]==[False]*4+[True]*6
    assert 'after' in json.dumps(results[2:4])
    assert private.read_text()=='PRIVATE_SOURCE_SENTINEL'
    assert not (project/'examples/foreign.js').exists()
    assert all('PRIVATE_SOURCE_SENTINEL' not in json.dumps(body) for body in requests)
    blocked=[row['data'] for row in rows if row.get('customType')=='continuous-study-source-boundary']
    assert len(blocked)==3 and all(row['version']==2 for row in blocked)


@pytest.mark.parametrize('public_only',[False,True])
def test_real_pi_blocks_initial_source_boundary_before_native_tools(tmp_path,public_only) -> None:
    import json
    import subprocess
    from pathlib import Path
    from live_acceptance_support import isolated_environment, workspace_pi
    from support import REPO
    project, agent = tmp_path/'project', tmp_path/'agent'
    project.mkdir(); agent.mkdir()
    (agent/'settings.json').write_text('{"packages":[],"quietStartup":true}')
    (agent/'private.txt').write_text('PRIVATE_BOUNDARY_SENTINEL')
    (project/'index.js').write_text('export const publicValue = 1;\n')
    session = tmp_path/'session.jsonl'
    command = [workspace_pi(REPO),'--offline','--no-extensions','--no-context-files','--no-skills','--no-prompt-templates',
               '--no-themes','--no-approve','--thinking','off','--tools','read,bash' if public_only else 'read,bash,write',
               '-e',str(Path(__file__).with_name('continuous-tool-budget-fixture.ts')),
               '-e',str(Path(__file__).with_name('continuous-bash-environment.ts')),
               '--model','study-budget-fixture/deterministic','--session',str(session),'--print','--mode','json','inspect']
    env = isolated_environment(tmp_path,agent)
    env.update(STUDY_INITIAL_SOURCE_PROBE='1', PI_STUDY_INITIAL_SOURCE_FILES=json.dumps(['index.js']))
    if public_only:env['STUDY_INITIAL_SOURCE_PUBLIC_ONLY']='1'
    process = subprocess.run(command,cwd=project,env=env,capture_output=True,timeout=20)
    assert process.returncode == 0, process.stderr.decode()
    rows = [json.loads(line) for line in session.read_text().splitlines()]
    results = [row['message'] for row in rows if row.get('message',{}).get('role') == 'toolResult']
    definitions = {tool['name']: tool for row in rows for tool in row.get('message', {}).get('toolsAdded', [])}
    assert definitions['bash']['parameters']['properties']['command']['enum'] == ['node observed-idle-failure.mjs', 'pnpm test']
    assert definitions['read']['parameters']['properties']['path']['enum'] == ['index.js', '/work/p-limit/index.js']
    assert 'verification commands' in definitions['bash']['description']
    assert 'declared public project file' in definitions['read']['description']
    assert len(results) == (2 if public_only else 6)
    assert sum(result['isError'] for result in results) == (1 if public_only else 5)
    public_grep=next(result for result in results if result['toolCallId']=='public-grep')
    assert public_grep['isError'] is True and 'validat' in json.dumps(public_grep).lower()
    assert 'export const publicValue' not in json.dumps(public_grep)
    # Native schemas refuse even a public grep, plus the three invalid calls before the
    # execution hook. The extra write is still refused by the existing guard.
    assert [row['data']['toolCallId'] for row in rows if row.get('customType') == 'continuous-study-source-boundary'] == ([] if public_only else ['mutation'])
    assert all('validat' in json.dumps(result).lower() for result in results[:1 if public_only else 3])
    assert 'PRIVATE_BOUNDARY_SENTINEL' not in json.dumps(results)
    assert 'export const publicValue' in json.dumps(results)
    assert not (project/'boundary-leak.txt').exists()
    assert (project/'index.js').read_text() == 'export const publicValue = 1;\n'


def test_initial_native_validation_reads_the_actual_executed_cli_chain(monkeypatch) -> None:
    import json,subprocess
    from pathlib import Path
    import live_continuous_project_learning as study
    from continuous_project_evidence import INITIAL_NATIVE_VALIDATION
    from support import REPO
    cli=REPO/'node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'
    monkeypatch.setattr(study.base,'PI',str(cli))
    observed=[]
    def checked(args):
        assert args[:3]==['docker','exec','owned-fixture']
        observed.append(args)
        return subprocess.run(args[3:],check=True,capture_output=True).stdout
    monkeypatch.setattr(study.base,'checked',checked)
    assert study.initial_native_validation('owned-fixture','1.3.0')==INITIAL_NATIVE_VALIDATION
    assert len(observed)==1
    with pytest.raises(RuntimeError,match='runtime'):
        study.initial_native_validation('owned-fixture','1.2.0')
    monkeypatch.setattr(study.base,'checked',lambda _args:json.dumps({'cli.js':'0'*64}).encode())
    with pytest.raises(RuntimeError,match='runtime'):
        study.initial_native_validation('owned-fixture','1.3.0')
