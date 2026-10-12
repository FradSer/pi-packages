from support import isolated_run_bun


def test_known_json_capable_no_tool_planners_request_structured_output() -> None:
    # Given a JSON-capable model and an isolated no-tool worker, When its
    # request is prepared, Then constrain content on the wire without changing
    # messages, model, reasoning, tools or caller-supplied output constraints.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';
      import path from 'node:path';
      import extension from './packages/continual-learning/extensions/planner-json-output.ts';
      import {learningPlannerArgs} from './packages/continual-learning/extensions/planner-prompts.ts';
      let handler;let tools=[];
      extension({on:(name,fn)=>{if(name==='before_provider_request')handler=fn},getActiveTools:()=>tools});
      const payload={model:'bailian/qwen3.8-flash',messages:[{role:'user',content:'Return JSON.'}],reasoning_effort:'medium'};
      const context={model:{api:'openai-completions',id:'bailian/qwen3.8-flash'}};
      const notOptedIn=handler({payload},context);
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({plannerJsonOutput:true}));
      const constrained=handler({payload},context);
      tools=['learning_read'];const inspecting=handler({payload},context);tools=[];
      const unsupported=handler({payload},{model:{api:'anthropic-messages',id:'qwen3.8-flash'}});
      const unknown=handler({payload},{model:{api:'openai-completions',id:'unknown'}});
      const explicit={...payload,response_format:{type:'json_schema',json_schema:{name:'caller'}}};
      const existing=handler({payload:explicit},context);
      console.log(JSON.stringify({notOptedIn,constrained,original:payload,inspecting,unsupported,unknown,existing,args:learningPlannerArgs()}));
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert value.get('notOptedIn') is None
    assert value['constrained']['response_format'] == {'type': 'json_object'}
    assert {k: v for k, v in value['constrained'].items() if k != 'response_format'} == value['original']
    assert 'response_format' not in value['original']
    assert value.get('inspecting') is None and value.get('unsupported') is None and value.get('unknown') is None
    assert value.get('existing') is None
    assert any(arg.endswith('/planner-json-output.ts') for arg in value['args'])


def test_actual_pi_no_tool_repair_transmits_json_mode_in_isolation(tmp_path) -> None:
    import json
    import subprocess
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from live_acceptance_support import isolated_environment, workspace_pi
    from live_learning_loop import stream_response
    from support import REPO

    received = []
    identity = {'runId': 'fixture-run', 'scopeKey': 'fixture-scope', 'scopeDigest': 'fixture-digest',
                'artifactHash': 'fixture-artifact', 'snapshotDigest': 'fixture-snapshot'}
    plan = {'kind': 'incremental-memory-plan', 'version': 1, 'schemaVersion': 1,
            **identity, 'operations': [], 'newMemories': []}

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received.append(payload)
            # The negative control imitates the real rejected no-tool output.
            content = json.dumps(plan) if payload.get('response_format') == {'type': 'json_object'} else '<tool_call><function=bash>echo forbidden</function></tool_call>'
            stream_response(self, content)

    agent = tmp_path / 'agent'
    agent.mkdir()
    (agent / 'continual-learning.json').write_text(json.dumps({'plannerJsonOutput': True, 'jev': False}))
    (agent / 'settings.json').write_text(json.dumps({'quietStartup': True, 'packages': []}))
    server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        models = [{'id': name, 'reasoning': False, 'input': ['text'], 'contextWindow': 200000, 'maxTokens': 4096,
                   'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}
                  for name in ['qwen3.8-flash', 'unknown']]
        (agent / 'models.json').write_text(json.dumps({'providers': {'planner-json-loopback': {
            'baseUrl': f'http://127.0.0.1:{server.server_port}/v1', 'api': 'openai-completions',
            'apiKey': 'loopback-fixture-only', 'models': models}}}))
        source = f'''
          import {{repairIncrementalMemoryPlan}} from './packages/continual-learning/extensions/inject-memory.ts';
          const input={{identity:{json.dumps(identity)},rejectedPlan:{json.dumps(plan)},errors:['fixture framing'],selectedNames:[]}};
          const control=await repairIncrementalMemoryPlan({{...input,model:'planner-json-loopback/unknown'}});
          const structured=await repairIncrementalMemoryPlan({{...input,model:'planner-json-loopback/qwen3.8-flash'}});
          console.log(JSON.stringify({{control,structured}}));
        '''
        result = subprocess.run(['bun', '-e', source], cwd=REPO, env=isolated_environment(tmp_path, agent),
                                capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stderr
        value = json.loads(result.stdout.strip().splitlines()[-1])
        assert value['control']['outcome'] == 'failed'
        assert value['control']['failureKind'] == 'framing'
        assert value['structured']['outcome'] == 'repaired'
        assert value['structured']['plan'] == plan
        assert len(received) == 2
        assert all(not request.get('tools') for request in received)
        assert 'response_format' not in received[0]
        assert received[1]['response_format'] == {'type': 'json_object'}
        version = subprocess.run([workspace_pi(REPO), '--version'], check=True, capture_output=True, text=True)
        assert version.stdout.strip(), 'Actual workspace Pi version missing'
    finally:
        server.shutdown()
        server.server_close()


def test_json_mode_capability_opt_in_uses_safe_bounded_config() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import {plannerJsonOutputEnabled} from './packages/continual-learning/extensions/config.ts';
      const root=process.env.PI_CODING_AGENT_DIR;const file=path.join(root,'continual-learning.json');const results=[plannerJsonOutputEnabled()];
      for(const text of ['{"plannerJsonOutput":true}','{"plannerJsonOutput":"true"}','{"plannerJsonOutput":false}','{"plannerJsonOutput":true,"padding":"'+ 'x'.repeat(4096)+'"}','damaged']) {fs.writeFileSync(file,text);results.push(plannerJsonOutputEnabled())}
      fs.unlinkSync(file);const target=path.join(root,'untrusted.json');fs.writeFileSync(target,'{"plannerJsonOutput":true}');fs.symlinkSync(target,file);results.push(plannerJsonOutputEnabled());
      console.log(JSON.stringify(results));
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert value == [False, True, False, False, False, False, False]
