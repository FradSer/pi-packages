import pytest
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
      extension({registerFlag:()=>{},getFlag:()=>undefined,on:(name,fn)=>{if(name==='before_provider_request')handler=fn},getActiveTools:()=>tools});
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


@pytest.mark.parametrize("strict", [False, True])
def test_actual_pi_no_tool_repair_transmits_json_mode_in_isolation(tmp_path, strict) -> None:
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
    import hashlib
    prior = {'name': 'project_fixture.md', 'kind': 'project', 'classification': 'private',
             'content': 'The project uses npm.', 'evidence': [{'index': 0, 'quote': 'The project uses pnpm.'}]}
    original = {**plan, 'newMemories': [prior]}
    candidate_id = 'newMemories:0:' + hashlib.sha256(json.dumps(prior, separators=(',', ':')).encode()).hexdigest()
    amendment = {'kind': 'incremental-memory-amendment', 'version': 1, **identity,
                 'replacements': [{'candidateId': candidate_id, 'content': 'The project uses pnpm.',
                                   'evidence': [{'ref': 'e0.b0.l1'}]}]}


    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received.append(payload)
            # The negative control imitates the real rejected no-tool output.
            content = json.dumps(plan) if payload.get('response_format', {}).get('type') == ('json_schema' if strict else 'json_object') else '<tool_call><function=bash>echo forbidden</function></tool_call>'
            if payload.get('response_format', {}).get('json_schema', {}).get('name') == 'memory_amendment':
                content = json.dumps(amendment)
                if 'Task: correct source citations' in json.dumps(payload.get('messages', [])):
                    content = json.dumps({**amendment, 'replacements': [{'candidateId': candidate_id, 'evidence': [{'ref': 'e0.b0.l1'}]}]})
            if payload.get('response_format', {}).get('json_schema', {}).get('name') == 'memory_combined_amendment':
                content = json.dumps({**amendment, 'operations': [{'name': 'retained.md', 'kind': 'rewrite', 'classification': 'private', 'content': 'The project uses pnpm.', 'evidence': [{'ref': 'e0.b0.l1'}]}]})
            if payload.get('response_format', {}).get('json_schema', {}).get('name') == 'memory_body_review':
                content = json.dumps({'reviews': {'0': {'verdict': 'consistent', 'conflictingQuotes': [], 'reason': 'Internally compatible.'}}})
            stream_response(self, content)

    agent = tmp_path / 'agent'
    agent.mkdir()
    (agent / 'continual-learning.json').write_text(json.dumps({('plannerStructuredOutput' if strict else 'plannerJsonOutput'): True, 'jev': False}))
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
        semantic_input = {'identity': identity, 'rejectedPlan': original, 'selectedNames': [],
                          'errors': ['fixture held claim'], 'model': 'planner-json-loopback/qwen3.8-flash',
                          'semanticContext': {'frozenEvidence': {'contextEnabled': True, 'entries': [{'role': 'user', 'content': 'The project uses pnpm.'}]}, 'existingMemories': []}}
        semantic_call = f"const semantic=await repairIncrementalMemoryPlan({json.dumps(semantic_input)});" if strict else 'const semantic=null;'
        citation_input = {**semantic_input, 'structuralCorrection': True, 'citationOnly': True}
        citation_call = f"const citation=await repairIncrementalMemoryPlan({json.dumps(citation_input)});" if strict else 'const citation=null;'
        combined_input = {**semantic_input, 'selectedNames': ['retained.md'], 'repairableNames': ['project_fixture.md'], 'retainedRepairNames': ['retained.md'],
                          'semanticContext': {**semantic_input['semanticContext'], 'existingMemories': [{'name': 'retained.md', 'classification': 'private', 'type': 'project', 'description': 'Project tooling', 'content': 'The project uses npm.'}]}}
        combined_call = f"const combined=await repairIncrementalMemoryPlan({json.dumps(combined_input)});" if strict else 'const combined=null;'
        body_call = "const body=await reviewMemoryBodies({candidates:[{name:'fact.md',content:'Complete immutable body.'}],retained:[],model:'planner-json-loopback/qwen3.8-flash'});" if strict else 'const body=null;'
        source = f'''
          import {{repairIncrementalMemoryPlan}} from './packages/continual-learning/extensions/inject-memory.ts';
          import {{reviewMemoryBodies}} from './packages/continual-learning/extensions/memory-body-review.ts';
          const input={{identity:{json.dumps(identity)},rejectedPlan:{json.dumps(plan)},errors:['fixture framing'],selectedNames:[]}};
          const control=await repairIncrementalMemoryPlan({{...input,model:'planner-json-loopback/unknown'}});
          const structured=await repairIncrementalMemoryPlan({{...input,model:'planner-json-loopback/qwen3.8-flash'}});
          {semantic_call}
          {citation_call}
          {combined_call}
          {body_call}
          console.log(JSON.stringify({{control,structured,semantic,citation,combined,body}}));
        '''
        result = subprocess.run(['bun', '-e', source], cwd=REPO, env=isolated_environment(tmp_path, agent),
                                capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stderr
        value = json.loads(result.stdout.strip().splitlines()[-1])
        assert value['control']['outcome'] == 'failed'
        assert value['control']['failureKind'] == 'framing'
        assert value['structured']['outcome'] == 'repaired'
        assert value['structured']['plan'] == plan
        assert len(received) == (6 if strict else 2)
        if strict:
            assert value['body']['status'] == 'reviewed'
            body_schema = received[5]['response_format']['json_schema']
            assert body_schema['name'] == 'memory_body_review' and body_schema['strict']
            slots = body_schema['schema']['properties']['reviews']
            assert slots['required'] == ['0'] and slots['additionalProperties'] is False
            assert set(slots['properties']) == {'0'}
            assert 'Complete immutable body.' in json.dumps(received[5]['messages'])
            assert value['citation']['outcome'] == 'repaired'
            locked = value['citation']['plan']['newMemories'][0]
            assert locked['content'] == prior['content']
            assert locked['classification'] == prior['classification']
            assert locked['evidence'][0]['quote'] == 'The project uses pnpm.'
            assert received[3]['response_format']['json_schema']['name'] == 'memory_amendment'
            assert value['semantic']['outcome'] == 'repaired'
            proposal = value['semantic']['plan']['newMemories'][0]
            assert proposal['kind'] == 'project' and proposal['classification'] == 'private'
            assert proposal['evidence'][0]['quote'] == 'The project uses pnpm.'
            assert received[2]['response_format']['json_schema']['name'] == 'memory_amendment'
            evidence = received[2]['response_format']['json_schema']['schema']['properties']['replacements']['items']['properties']['evidence']['items']
            assert evidence['properties']['ref']['enum'] == ['e0.b0.l1']
            assert set(evidence['properties']) == {'ref', 'endRef', 'role'}
            assert evidence['required'] == ['ref']
            for index in (2, 3, 4):
                patch_schema = received[index]['response_format']['json_schema']['schema']['properties']['replacements']['items']['properties']
                assert patch_schema['candidateId']['enum'] == [candidate_id]
            assert value['combined']['outcome'] == 'repaired'
            combined_plan = value['combined']['plan']
            assert combined_plan['newMemories'][0]['name'] == prior['name']
            assert combined_plan['newMemories'][0]['kind'] == prior['kind']
            assert combined_plan['newMemories'][0]['classification'] == prior['classification']
            assert combined_plan['operations'][0]['name'] == 'retained.md'
            assert combined_plan['operations'][0]['classification'] == 'private'
            combined_schema = received[4]['response_format']['json_schema']
            assert combined_schema['name'] == 'memory_combined_amendment'
            assert 'operations' in combined_schema['schema']['required']
            assert 'newMemories' not in combined_schema['schema']['properties']
        assert all(not request.get('tools') for request in received)
        assert 'response_format' not in received[0]
        if strict:
            assert received[1]['response_format']['type'] == 'json_schema'
            assert received[1]['response_format']['json_schema']['name'] == 'memory_delta'
        else:
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


def test_selector_strict_output_requires_separate_gateway_opt_in() -> None:
    value = isolated_run_bun(r'''
      import fs from 'node:fs';import path from 'node:path';
      import extension from './packages/continual-learning/extensions/planner-json-output.ts';
      import {learningPlannerArgs} from './packages/continual-learning/extensions/planner-prompts.ts';
      let handler;let tools=[];let flag='memory-selector';const registrations=[];
      extension({registerFlag:(name,options)=>registrations.push({name,options}),getFlag:(name)=>name==='learning-output-schema'?flag:undefined,on:(name,fn)=>{if(name==='before_provider_request')handler=fn},getActiveTools:()=>tools});
      const file=path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json');
      const payload={messages:[{role:'user',content:'Return JSON.'}],model:'bailian/qwen3.8-flash'};const ctx={model:{api:'openai-completions',id:payload.model}};
      fs.writeFileSync(file,JSON.stringify({plannerJsonOutput:true}));const legacy=handler({payload},ctx);
      fs.writeFileSync(file,JSON.stringify({plannerStructuredOutput:true}));const strict=handler({payload},ctx);
      tools=['learning_read'];const active=handler({payload},ctx);tools=[];
      const explicit=handler({payload:{...payload,response_format:{type:'caller-constraint'}}},ctx);
      const unsupported=handler({payload},{model:{api:'openai-completions',id:'unknown'}});
      flag=undefined;const missingFlag=handler({payload},ctx);flag='unknown';const unknownFlag=handler({payload},ctx);
      console.log(JSON.stringify({legacy,strict,active,explicit,unsupported,missingFlag,unknownFlag,registrations,args:learningPlannerArgs('memory-selector'),payload}));
    ''', temp_dirs=('PI_CODING_AGENT_DIR',))
    assert value['legacy']['response_format'] == {'type': 'json_object'}
    fmt = value['strict']['response_format']
    assert fmt['type'] == 'json_schema' and fmt['json_schema']['strict'] is True
    schema = fmt['json_schema']['schema']
    assert set(schema['required']) == {'selectedIndices', 'memory', 'harness', 'agents', 'reason'}
    assert schema['additionalProperties'] is False
    assert schema['properties']['selectedIndices']['items'] == {'type': 'integer', 'minimum': 0}
    assert all(schema['properties'][field]['type'] == 'boolean' for field in ['memory', 'harness', 'agents'])
    assert value.get('active') is None and value.get('explicit') is None and value.get('unsupported') is None
    assert value.get('missingFlag') is None and value.get('unknownFlag') is None
    assert value['args'][-2:] == ['--learning-output-schema', 'memory-selector']
    assert 'response_format' not in value['payload']


def test_actual_selector_worker_transmits_schema_and_keeps_parent_range_gate(tmp_path) -> None:
    import json
    import subprocess
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from live_acceptance_support import isolated_environment
    from live_learning_loop import stream_response
    from support import REPO

    requests = []
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(request)
            if len(requests) == 3:
                self.send_error(400, 'Fixture schema unsupported')
                return
            if len(requests) == 4:
                stream_response(self, json.dumps({'selectedIndexes': [], 'reason': 'Fixture wrong schema'}))
                return
            content = {'selectedIndices': [99] if len(requests) == 2 else [],
                       'memory': True, 'harness': False, 'agents': False, 'reason': 'Fixture routing only.'}
            stream_response(self, json.dumps(content))

    server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    agent = tmp_path / 'agent'
    agent.mkdir()
    (agent / 'continual-learning.json').write_text(json.dumps({'plannerStructuredOutput': True, 'jev': False}))
    (agent / 'settings.json').write_text(json.dumps({'quietStartup': True, 'packages': []}))
    (agent / 'models.json').write_text(json.dumps({'providers': {'selector-schema-loopback': {
        'baseUrl': f'http://127.0.0.1:{server.server_port}/v1', 'api': 'openai-completions',
        'apiKey': 'loopback-fixture-only', 'models': [{'id': 'qwen3.8-flash', 'reasoning': False,
        'input': ['text'], 'contextWindow': 200000, 'maxTokens': 4096,
        'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}]}}}))
    try:
        source = r'''
          import fs from 'node:fs';import path from 'node:path';import {execFileSync} from 'node:child_process';
          import {selectIncrementalLearning} from './packages/continual-learning/extensions/incremental-learning.ts';
          const cwd=path.join(process.env.PI_CODING_AGENT_DIR,'project');fs.mkdirSync(cwd);execFileSync('git',['init','-q',cwd]);
          const results=[];
          for(let i=0;i<4;i++) results.push(await selectIncrementalLearning({cwd,outputDir:path.join(cwd,String(i)),contextDigest:'current',taskSlice:{kind:'learning-task-slice',version:1,entries:[]},model:'selector-schema-loopback/qwen3.8-flash',jevJudge:{select:async()=>({telemetry:{status:'disabled'}})}}));
          console.log(JSON.stringify(results));
        '''
        run = subprocess.run(['bun', '-e', source], cwd=REPO, env=isolated_environment(tmp_path, agent),
                             capture_output=True, text=True, timeout=90)
        assert run.returncode == 0, run.stderr
        results = json.loads(run.stdout.strip().splitlines()[-1])
        assert results[0]['outcome'] == 'selected'
        assert results[1]['outcome'] == 'failed'
        assert results[2]['outcome'] == 'failed'
        assert results[3]['outcome'] == 'selected'
        assert [a['outcome'] for a in results[3]['attempts']] == ['failed', 'applied']
        assert len(requests) == 5
        assert all(not request.get('tools') for request in requests)
        assert all(request['response_format']['type'] == 'json_schema' for request in requests)
        assert all(request['response_format']['json_schema']['strict'] is True for request in requests)
    finally:
        server.shutdown()
        server.server_close()
