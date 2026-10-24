import pytest
from support import isolated_run_bun


def test_incremental_knowledge_contract_precedes_untrusted_dossier() -> None:
    value = isolated_run_bun(r'''
      import {buildIncrementalMemoryConsolidatorPrompt, buildMemoryConsolidatorPrompt, MEMORY_KNOWLEDGE_GUIDANCE, MEMORY_CITATION_GUIDANCE} from './packages/continual-learning/extensions/planner-prompts.ts';
      const prompt=buildIncrementalMemoryConsolidatorPrompt({runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h',dossierPath:'/fixture/dossier',dossierContents:'UNTRUSTED_FROZEN_EVIDENCE'});
      const maintenance=buildMemoryConsolidatorPrompt({pkgDir:'/fixture/pkg',runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h',runDir:'/fixture/run',snapshotPath:'/fixture/snapshot',harnessDir:'/fixture/harness',publicDir:'/fixture/public',repoRoot:'/fixture/repo'});
      console.log(JSON.stringify({prompt,maintenance,contract:MEMORY_KNOWLEDGE_GUIDANCE,citation:MEMORY_CITATION_GUIDANCE}));
    ''')
    assert 'A Promise and a PromiseLike are distinct contracts and must not be conflated.' not in value['citation']
    assert 'compatible native Promise values remain valid PromiseLike inputs' in value['citation']
    assert value['prompt'].startswith(value['contract'])
    assert value['maintenance'].startswith(value['contract'])
    assert value['maintenance'].count('Knowledge output contract:') == 1
    assert value['prompt'].count('Knowledge output contract:') == 1
    assert value['prompt'].index('Knowledge output contract:') < value['prompt'].index('UNTRUSTED_FROZEN_EVIDENCE')
    assert 'no uncertainty authorizes changing a possibly correct fact' in value['contract']
    assert 'Return only the exact attributed declaration' in value['contract']
    assert 'PromiseLike' not in value['contract'] and 'limitFunction' not in value['contract']
    assert 'Return only the exact attributed declaration' not in value['citation']
    # Given a self-returning callable and overlapping value contracts, When
    # writing declaration knowledge, Then role distinctions must not become
    # false runtime-identity claims or new uncited reviewer caveats.
    counterexample = isolated_run_bun(r'''
      const self = () => self;
      const promise = Promise.resolve(1);
      console.log(JSON.stringify({sameCallable: self() === self,
        promiseAlsoThenable: typeof promise.then === 'function'}));
    ''')
    assert counterexample == {'sameCallable': True, 'promiseAlsoThenable': True}
    assert 'A callable returning a value is not that value.' not in value['contract']
    assert 'Different declared roles do not establish different runtime objects or mutually exclusive values.' in value['contract']
    assert 'Do not copy reviewer cautions into learned knowledge as new claims.' in value['contract']
    # Declared members are compatible with both own and inherited methods.
    ownership = isolated_run_bun(r'''
      interface Ready { ready(): boolean }
      class Parent { ready() { return true; } }
      const inherited: Ready = new Parent();
      const own: Ready = {ready() { return true; }};
      console.log(JSON.stringify({bothReady: inherited.ready() && own.ready(),
        inheritedOwn: Object.hasOwn(inherited, 'ready'), ownOwn: Object.hasOwn(own, 'ready')}));
    ''')
    assert ownership == {'bothReady': True, 'inheritedOwn': False, 'ownOwn': True}
    assert 'the members declared on its type' in value['contract']
    assert 'Structural types do not establish whether a member is an own or inherited property.' in value['contract']
    assert 'its invocation result and its own properties' not in value['contract']

    # Given V90's real nested-function error, the outer annotation can describe
    # a callable while only its inner return annotation describes a Promise.
    roles = isolated_run_bun(r'''
      import fs from 'node:fs';
      const fixture=JSON.parse(fs.readFileSync('packages/continual-learning/tests/fixtures/real-description-body-conflict.json','utf8')).nestedReturnRoleCase;
      const factory=(): (()=>Promise<string>) & {reset():void} => Object.assign(()=>Promise.resolve('ok'),{reset(){}});
      const returned=factory(),invocation=returned();
      console.log(JSON.stringify({ambiguousRule:fixture.ambiguousGenerationRule,
        realWrongRole:fixture.original.content.includes('the return-type annotation describes the invocation result, not the returned callable itself'),
        realRepairSeparatesRoles:fixture.repair.content.includes('The declared return type describes the returned callable'),
        returnedCallable:typeof returned==='function',returnedMember:typeof returned.reset==='function',
        invocationPromise:invocation instanceof Promise,invocationHasReset:'reset' in invocation}));
    ''')
    assert roles['realWrongRole'] and roles['realRepairSeparatesRoles']
    assert roles['returnedCallable'] and roles['returnedMember'] and roles['invocationPromise']
    assert not roles['invocationHasReset']
    assert roles['ambiguousRule'] not in value['contract']
    assert "The outer function's return annotation describes what that function returns" in value['contract']
    assert "The return annotation inside that callable's signature describes what invoking it returns" in value['contract']
    # Given V96's real callback-parameter error, parse the complete actual
    # declaration. Its parameter owns a function type; that function owns the
    # nested return annotation. This proves syntax roles, not runtime identity.
    inputs = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {createHash} from 'node:crypto';
      import {parse} from '@babel/parser';
      const fixture=JSON.parse(fs.readFileSync('packages/continual-learning/tests/fixtures/real-description-body-conflict.json','utf8')).inputParameterRoleCase;
      const ast=parse(fixture.sourceText,{sourceType:'module',plugins:['typescript']});
      const decl=ast.program.body.find(node=>node.type==='ExportNamedDeclaration' && node.declaration?.id?.name==='limitFunction').declaration;
      const parameterType=decl.params[0].typeAnnotation.typeAnnotation;
      console.log(JSON.stringify({sourceMatches:createHash('sha256').update(fixture.sourceText).digest('hex')===fixture.provenance.sourceSha256,
        parameterType:parameterType.type,callbackReturn:parameterType.typeAnnotation.typeAnnotation.typeName.name,
        originalWrongRole:fixture.original.content.includes(fixture.rejectedParaphrase),
        repairedWrongRole:fixture.repair.content.includes(fixture.rejectedParaphrase)}));
    ''')
    assert inputs == {'sourceMatches': True, 'parameterType': 'TSFunctionType',
                      'callbackReturn': 'PromiseLike', 'originalWrongRole': True,
                      'repairedWrongRole': True}
    assert "A function-typed input parameter has a callable type" in value['contract']
    assert "the return annotation inside that parameter's call signature describes its invocation result" in value['contract']
    assert "Do not replace the parameter's own type with its callback return annotation" in value['contract']
    # The named return type must be linked to its factory when this relationship
    # is the lesson, rather than merely quoting two disconnected declarations.
    bridge = isolated_run_bun(r'''
      import fs from 'node:fs';
      import {createHash} from 'node:crypto';
      import {parse} from '@babel/parser';
      const f=JSON.parse(fs.readFileSync('packages/continual-learning/tests/fixtures/real-description-body-conflict.json','utf8')).declarationOwnerBridgeCase;
      const ast=parse(f.sourceText,{sourceType:'module',plugins:['typescript']});
      const factory=ast.program.body.find(n=>n.type==='ExportDefaultDeclaration').declaration;
      const named=ast.program.body.find(n=>n.type==='ExportNamedDeclaration' && n.declaration?.id?.name==='LimitFunction').declaration;
      const member=named.typeAnnotation.members.find(n=>n.key?.name==='clearQueue');
      console.log(JSON.stringify({sourceMatches:createHash('sha256').update(f.sourceText).digest('hex')===f.provenance.sourceSha256,
        factory:factory.id.name,returnType:factory.returnType.typeAnnotation.typeName.name,
        member:member.key.name,memberType:member.typeAnnotation.typeAnnotation.type,
        originalHasMember:f.originalContent.includes('clearQueue: () => void;'),
        originalHasBridge:f.originalContent.includes(f.sourceRelation)}));
    ''')
    assert bridge == {'sourceMatches': True, 'factory': 'pLimit', 'returnType': 'LimitFunction',
                      'member': 'clearQueue', 'memberType': 'TSFunctionType',
                      'originalHasMember': True, 'originalHasBridge': False}
    assert 'factory or call site to its named return type and the relevant declared member' in value['contract']


def test_incremental_selection_preserves_independent_contract_facts_and_preference_shape() -> None:
    # Given a failed task with independently inspected contracts, When the
    # existing planner receives its dossier, Then its delivered policy retains
    # applicable relationships instead of selecting only a shorter pitfall.
    # This tests the generation contract, not model compliance or benefit.
    value = isolated_run_bun(r'''
      import {buildIncrementalMemoryConsolidatorPrompt} from './packages/continual-learning/extensions/planner-prompts.ts';
      const prompt=buildIncrementalMemoryConsolidatorPrompt({runId:'r',scopeKey:'s',scopeDigest:'d',artifactHash:'a',snapshotDigest:'h',dossierPath:'/fixture/dossier',dossierContents:'ORIGINAL_DOSSIER_SENTINEL'});
      console.log(JSON.stringify({prompt}));
    ''')
    prompt = value['prompt']
    assert 'Deduplicate repeated statements, not independently applicable contract facts.' in prompt
    assert 'The failure observation does not replace the inspected contract needed to apply it.' in prompt
    assert 'For each new entry, preserve one reusable fact or relationship with its evidenced' in prompt
    assert 'Prioritize a reusable pitfall evidenced by the actual failed verification over' not in prompt
    assert 'For each new entry, write one minimal durable fact or closely related preference' not in prompt
    assert 'An ordinary prose proposal has' not in prompt
    assert 'A preference proposal has `name`, `kind: "preference"`,' in prompt
    # Check actual examples rather than manufacturing new schema authority.
    import json
    import re
    examples = re.findall(r'```json\s*(.*?)\s*```', prompt, re.DOTALL)
    preference = next(json.loads(example) for example in examples
                      if '"name": "preference_example.md"' in example)
    assert preference['kind'] == 'preference'
    assert preference['classification'] == 'private'
    assert isinstance(preference['content'], str) and preference['content']
    assert preference['evidence'] and 'knowledge' not in preference
    project = json.loads(next(line for line in prompt.splitlines()
                              if line.startswith('`{"name":"project_fact.md"')).strip('`.'))
    assert project['kind'] == 'project' and project['classification'] == 'safe'
    assert project['knowledge']['units'] and project['knowledge']['sourceCitations']
    assert 'content' not in project and 'evidence' not in project
    assert 'The parent remains compatible with legacy complete `content`/`evidence` project' in prompt
    assert 'No repository exploration or discovery is granted to this worker' in prompt
    assert 'at most eight items and 2,000 extracted characters per item' in prompt
    assert 'All semantic gates still apply.' in prompt
    assert 'pLimit' not in prompt and 'LimitFunction' not in prompt
    assert prompt.count('ORIGINAL_DOSSIER_SENTINEL') == 1


@pytest.mark.parametrize("model_id", ["bailian/qwen3.8-flash", "deepseek-flash", "bailian/deepseek-v4.1-flash", "deepseek-v4-pro", "gpt-6.1-sol"])
def test_known_json_capable_no_tool_planners_request_structured_output(model_id: str) -> None:
    # Given a JSON-capable model and an isolated no-tool worker, When its
    # request is prepared, Then constrain content on the wire without changing
    # messages, model, reasoning, tools or caller-supplied output constraints.
    value = isolated_run_bun(r'''
      import fs from 'node:fs';
      import path from 'node:path';
      import extension from './packages/continual-learning/extensions/planner-json-output.ts';
      import {learningPlannerArgs} from './packages/continual-learning/extensions/planner-prompts.ts';
      let handler;let tools=[];const flags={};
      extension({registerFlag:()=>{},getFlag:name=>flags[name],on:(name,fn)=>{if(name==='before_provider_request')handler=fn},getActiveTools:()=>tools});
      const responses=process.env.TEST_JSON_MODEL==='gpt-6.1-sol';
      const payload=responses ? {model:process.env.TEST_JSON_MODEL,input:[{role:'user',content:[{type:'input_text',text:'Return JSON.'}]}],reasoning:{effort:'medium'},text:{verbosity:'low'}} : {model:process.env.TEST_JSON_MODEL,messages:[{role:'user',content:'Return JSON.'}],reasoning_effort:'medium'};
      const context={model:{api:responses?'openai-responses':'openai-completions',id:process.env.TEST_JSON_MODEL}};
      const notOptedIn=handler({payload},context);
      fs.writeFileSync(path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json'),JSON.stringify({plannerJsonOutput:true}));
      const constrained=handler({payload},context);
      tools=['learning_read'];const inspecting=handler({payload},context);tools=[];
      const unsupported=handler({payload},{model:{api:'anthropic-messages',id:'qwen3.8-flash'}});
      const unknown=handler({payload},{model:{api:'openai-completions',id:'unknown'}});
      const explicit=responses ? {...payload,text:{...payload.text,format:{type:'json_schema',name:'caller'}}} : {...payload,response_format:{type:'json_schema',json_schema:{name:'caller'}}};
      const existing=handler({payload:explicit},context);
      const wrongSolApi=handler({payload},{model:{api:'openai-completions',id:'gpt-6.1-sol'}});
      const unknownResponses=handler({payload},{model:{api:'openai-responses',id:'gpt-6-sol'}});
      const malformedText=responses?handler({payload:{...payload,text:[]}},context):undefined;
      flags['learning-output-schema']='memory-body-review';flags['learning-body-count']='2';
      const config=path.join(process.env.PI_CODING_AGENT_DIR,'continual-learning.json');
      fs.writeFileSync(config,JSON.stringify({plannerStructuredOutput:true}));
      const schemaOnly=handler({payload},context);
      fs.writeFileSync(config,JSON.stringify({plannerStructuredOutput:true,plannerJsonOutput:true}));
      const bothEnabled=handler({payload},context);
      const otherDeepseek=handler({payload},{model:{api:'openai-completions',id:'deepseek-v3'}});
      console.log(JSON.stringify({notOptedIn,constrained,original:payload,inspecting,unsupported,unknown,existing,schemaOnly,bothEnabled,otherDeepseek,wrongSolApi,unknownResponses,malformedText,args:learningPlannerArgs()}));
    ''', env={'TEST_JSON_MODEL': model_id}, temp_dirs=('PI_CODING_AGENT_DIR',))
    assert value.get('notOptedIn') is None
    if model_id == 'gpt-6.1-sol':
        assert value['constrained']['text'] == {'verbosity': 'low', 'format': {'type': 'json_object'}}
        assert {**value['constrained'], 'text': value['original']['text']} == value['original']
        assert 'format' not in value['original']['text']
    else:
        assert value['constrained']['response_format'] == {'type': 'json_object'}
        assert {k: v for k, v in value['constrained'].items() if k != 'response_format'} == value['original']
        assert 'response_format' not in value['original']
    assert value.get('inspecting') is None and value.get('unsupported') is None and value.get('unknown') is None
    assert value.get('existing') is None
    assert value.get('wrongSolApi') is None and value.get('unknownResponses') is None
    assert value.get('malformedText') is None
    assert any(arg.endswith('/planner-json-output.ts') for arg in value['args'])

    if 'qwen' in model_id:
        assert value['schemaOnly']['response_format']['type'] == 'json_schema'
        assert value['bothEnabled']['response_format']['type'] == 'json_schema'
    else:
        assert value.get('schemaOnly') is None
        assert (value['bothEnabled']['text']['format'] if model_id == 'gpt-6.1-sol' else value['bothEnabled']['response_format']) == {'type': 'json_object'}
    assert value.get('otherDeepseek') is None


@pytest.mark.parametrize("strict,thinking,model_id", [(False, None, "qwen3.8-flash"), (True, None, "qwen3.8-flash"), (True, "low", "qwen3.8-flash"), (False, None, "bailian/deepseek-v4.1-flash"), (False, None, "gpt-6.1-sol")])
def test_actual_pi_no_tool_repair_transmits_json_mode_in_isolation(tmp_path, strict, thinking, model_id) -> None:
    import json
    import subprocess
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from live_acceptance_support import isolated_environment, workspace_pi
    from live_learning_loop import stream_response
    from support import REPO

    received = []
    responses_api = model_id == 'gpt-6.1-sol'
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
            requested_format = payload.get('text', {}).get('format', {}) if responses_api else payload.get('response_format', {})
            content = json.dumps(plan) if requested_format.get('type') == ('json_schema' if strict else 'json_object') else '<tool_call><function=bash>echo forbidden</function></tool_call>'
            if payload.get('response_format', {}).get('json_schema', {}).get('name') == 'memory_amendment':
                content = json.dumps(amendment)
                if 'Task: correct source citations' in json.dumps(payload.get('messages', [])):
                    content = json.dumps({**amendment, 'replacements': [{'candidateId': candidate_id, 'evidence': [{'ref': 'e0.b0.l1'}]}]})
            if payload.get('response_format', {}).get('json_schema', {}).get('name') == 'memory_combined_amendment':
                content = json.dumps({**amendment, 'operations': [{'name': 'retained.md', 'kind': 'rewrite', 'classification': 'private', 'content': 'The project uses pnpm.', 'evidence': [{'ref': 'e0.b0.l1'}]}]})
            if payload.get('response_format', {}).get('json_schema', {}).get('name') == 'memory_body_review':
                content = json.dumps({'reviews': {'0': {'verdict': 'consistent', 'conflictingQuotes': [], 'reason': 'Internally compatible.'}}})
            if payload.get('response_format', {}).get('json_schema', {}).get('name') == 'memory_coverage_review':
                content = json.dumps({'plan': {'verdict': 'covered', 'obligations': []}, 'reviews': {'0': {
                    'scope': {'basis': 'optional', 'statement': 'Project tooling', 'evidence': [{'ref': 'e0.b0.l1'}]},
                    'claims': [{'statement': 'The project uses pnpm.', 'bodyQuote': 'The project uses pnpm.',
                                'evidence': [{'ref': 'e0.b0.l1'}], 'conditions': []}],
                    'uncovered': [], 'verdict': 'uncertain'}}})
            if payload.get('response_format', {}).get('json_schema', {}).get('name') == 'memory_coverage_review' and not payload['response_format']['json_schema']['schema']['properties']['reviews']['properties']:
                content = json.dumps({'plan': {'verdict': 'incomplete', 'obligations': [{
                    'basis': 'requested', 'statement': 'Keep the requested tooling fact',
                    'evidence': [{'ref': 'e0.b0.l1'}], 'coveredBy': [], 'status': 'missing'}]}, 'reviews': {}})
            if responses_api:
                assert self.path == '/v1/responses'
                item = {'id': 'msg_fixture', 'type': 'message', 'role': 'assistant', 'status': 'in_progress', 'content': []}
                part = {'type': 'output_text', 'text': '', 'annotations': []}
                response = {'id': 'resp_fixture', 'object': 'response', 'created_at': 1,
                            'model': payload['model'], 'status': 'in_progress', 'output': []}
                complete_part = {**part, 'text': content}
                complete_item = {**item, 'status': 'completed', 'content': [complete_part]}
                events = [
                    {'type': 'response.created', 'response': response},
                    {'type': 'response.output_item.added', 'output_index': 0, 'item': item},
                    {'type': 'response.content_part.added', 'item_id': item['id'], 'output_index': 0, 'content_index': 0, 'part': part},
                    {'type': 'response.output_text.delta', 'item_id': item['id'], 'output_index': 0, 'content_index': 0, 'delta': content},
                    {'type': 'response.output_text.done', 'item_id': item['id'], 'output_index': 0, 'content_index': 0, 'text': content},
                    {'type': 'response.content_part.done', 'item_id': item['id'], 'output_index': 0, 'content_index': 0, 'part': complete_part},
                    {'type': 'response.output_item.done', 'output_index': 0, 'item': complete_item},
                    {'type': 'response.completed', 'response': {**response, 'status': 'completed', 'output': [complete_item],
                     'usage': {'input_tokens': 10, 'output_tokens': 10, 'total_tokens': 20,
                               'input_tokens_details': {'cached_tokens': 0}, 'output_tokens_details': {'reasoning_tokens': 0}}}},
                ]
                wire = ''.join('event: ' + event['type'] + '\ndata: ' + json.dumps({**event, 'sequence_number': i}) + '\n\n'
                               for i, event in enumerate(events)).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(wire)))
                self.end_headers()
                self.wfile.write(wire)
                self.wfile.flush()
            else:
                stream_response(self, content)

    agent = tmp_path / 'agent'
    agent.mkdir()
    (agent / 'continual-learning.json').write_text(json.dumps({('plannerStructuredOutput' if strict else 'plannerJsonOutput'): True, 'jev': False, **({'plannerThinkingLevel': thinking} if thinking else {})}))
    (agent / 'settings.json').write_text(json.dumps({'quietStartup': True, 'packages': []}))
    server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        models = [{'id': name, 'reasoning': bool(thinking) or responses_api, **({'compat': {'thinkingFormat': 'qwen', 'supportsReasoningEffort': True}, 'thinkingLevelMap': {'off': 'none', 'minimal': None, 'low': 'low', 'medium': 'medium', 'high': None, 'xhigh': 'xhigh', 'max': None}} if thinking else {}), 'input': ['text'], 'contextWindow': 200000, 'maxTokens': 4096,
                   'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}
                  for name in [model_id, 'unknown']]
        (agent / 'models.json').write_text(json.dumps({'providers': {'planner-json-loopback': {
            'baseUrl': f'http://127.0.0.1:{server.server_port}/v1', 'api': 'openai-responses' if responses_api else 'openai-completions',
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
        coverage_call = "const coverage=await reviewMemoryCoverage({candidates:[{name:'fact.md',content:'The project uses pnpm.'}],retained:[],evidence:{contextEnabled:true,entries:[{role:'user',content:'The project uses pnpm.'}]},predecessors:[],plan:{operations:[],newMemories:[{name:'fact.md',content:'The project uses pnpm.'}]},model:'planner-json-loopback/qwen3.8-flash'});" if strict else 'const coverage=null;'
        empty_coverage_call = "const emptyCoverage=await reviewMemoryCoverage({candidates:[],retained:[],evidence:{contextEnabled:true,entries:[{role:'user',content:'Remember the project uses pnpm.'}]},predecessors:[],plan:{operations:[],newMemories:[]},model:'planner-json-loopback/qwen3.8-flash'});" if strict else 'const emptyCoverage=null;'
        source = f'''
          import {{repairIncrementalMemoryPlan}} from './packages/continual-learning/extensions/inject-memory.ts';
          import {{reviewMemoryBodies}} from './packages/continual-learning/extensions/memory-body-review.ts';
          import {{reviewMemoryCoverage}} from './packages/continual-learning/extensions/memory-knowledge-coverage.ts';
          const input={{identity:{json.dumps(identity)},rejectedPlan:{json.dumps(plan)},errors:['fixture framing'],selectedNames:[]}};
          const control=await repairIncrementalMemoryPlan({{...input,model:'planner-json-loopback/unknown'}});
          const structured=await repairIncrementalMemoryPlan({{...input,model:'planner-json-loopback/{model_id}'}});
          {semantic_call}
          {citation_call}
          {combined_call}
          {body_call}
          {coverage_call}
          {empty_coverage_call}
          console.log(JSON.stringify({{control,structured,semantic,citation,combined,body,coverage,emptyCoverage}}));
        '''
        result = subprocess.run(['bun', '-e', source], cwd=REPO, env=isolated_environment(tmp_path, agent),
                                capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stderr
        value = json.loads(result.stdout.strip().splitlines()[-1])
        assert value['control']['outcome'] == 'failed'
        assert value['control']['failureKind'] == 'framing'
        assert value['structured']['outcome'] == 'repaired'
        assert value['structured']['plan'] == plan
        assert len(received) == (8 if strict else 2)
        if strict:
            assert value['emptyCoverage']['status'] == 'reviewed'
            assert value['emptyCoverage']['plan']['verdict'] == 'incomplete'
            assert value['emptyCoverage']['accounts'] == []
            zero_schema = received[7]['response_format']['json_schema']['schema']
            assert set(zero_schema['required']) == {'plan', 'reviews'}
            assert zero_schema['properties']['reviews']['properties'] == {}
            assert 'Remember the project uses pnpm.' in json.dumps(received[7]['messages'])
            assert value['coverage']['status'] == 'reviewed' 
            assert value['coverage']['accounts'][0]['verdict'] == 'uncertain'
            assert value['coverage']['accounts'][0]['scope']['basis'] == 'optional'
            coverage_schema = received[6]['response_format']['json_schema']
            assert coverage_schema['name'] == 'memory_coverage_review' and coverage_schema['strict']
            assert coverage_schema['schema']['properties']['reviews']['required'] == ['0']
            assert 'frozenEvidence' in json.dumps(received[6]['messages'])
            assert 'frozenEvidence' not in json.dumps(received[5]['messages'])
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
            # Given ambiguous declaration prose caused real held Memory, When
            # actual Pi prepares its semantic correction, Then the source-level
            # knowledge contract precedes the frozen context and stays independent
            # of this fixture's project facts.
            semantic_prompt = '\n'.join(str(m.get('content', '')) for m in received[2]['messages'] if m.get('role') == 'user')
            assert 'Knowledge output contract:' in semantic_prompt
            assert 'Different declared roles do not establish different runtime objects or mutually exclusive values.' in semantic_prompt
            assert 'Do not copy reviewer cautions into learned knowledge as new claims.' in semantic_prompt
            assert 'not a requirement that every runtime property become public' in semantic_prompt
            assert 'body and description' in semantic_prompt
            assert 'the input function, its return value, the returned callable, its invocation result and the members declared on its type' in semantic_prompt
            assert semantic_prompt.index('Knowledge output contract:') < semantic_prompt.index('"semanticContext"')
            assert 'Return only the exact attributed declaration when a paraphrase cannot keep those subjects distinct.' in semantic_prompt
            assert value['semantic']['outcome'] == 'repaired'
            proposal = value['semantic']['plan']['newMemories'][0]
            assert proposal['kind'] == 'project' and proposal['classification'] == 'private'
            assert proposal['evidence'][0]['quote'] == 'The project uses pnpm.'
            assert received[2]['response_format']['json_schema']['name'] == 'memory_amendment'
            evidence = received[2]['response_format']['json_schema']['schema']['properties']['replacements']['items']['properties']['evidence']['items']
            assert evidence['properties']['ref'] == {'$ref': '#/$defs/memorySourceReference'}
            assert evidence['properties']['endRef'] == evidence['properties']['ref']
            assert received[2]['response_format']['json_schema']['schema']['$defs']['memorySourceReference'] == {'type': 'string', 'enum': ['e0.b0.l1']}
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
        if thinking:
            # Given semantic body scope is unknown or includes retained records,
            # When actual Pi sends the repair, Then keep xhigh despite configured low.
            # Structural and citation-only requests must retain their configured effort.
            assert [request.get('reasoning_effort') for request in received] == [
                thinking, thinking, 'xhigh', thinking, 'xhigh', 'xhigh', 'xhigh', 'xhigh',
            ]
            assert all(request.get('enable_thinking') is True for request in received)
        assert all(not request.get('tools') for request in received)
        assert 'response_format' not in received[0]
        if responses_api:
            assert received[1]['text']['format'] == {'type': 'json_object'}
            assert 'format' not in received[0].get('text', {})
            assert 'response_format' not in received[1]
            assert all(isinstance(request['input'], list) for request in received)
            assert all(request.get('reasoning', {}).get('effort') in ('low', 'medium', 'high', 'xhigh', 'max') for request in received)
        elif strict:
            assert received[1]['response_format']['type'] == 'json_schema'
            assert received[1]['response_format']['json_schema']['name'] == 'memory_delta'
        else:
            assert received[1]['response_format'] == {'type': 'json_object'}
        version = subprocess.run([workspace_pi(REPO), '--version'], check=True, capture_output=True, text=True)
        assert version.stdout.strip() == '1.3.0', 'Actual workspace Pi 1.3 is required'
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


def test_semantic_amendment_content_requires_complete_markdown_not_body_only() -> None:
    # Given the actual failure returned a plain replacement paragraph,
    # When a semantic amendment requests content, Then its wire schema requires the same complete document as parent validation.
    import re
    value = isolated_run_bun(r'''
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      const kinds=['memory-amendment','memory-semantic-amendment','memory-combined-amendment'];
      console.log(JSON.stringify(kinds.map(kind=>learningOutputSchema(kind,undefined,['bound-id']).properties.replacements.items)));
    ''')
    actual_body = ('When `rejectOnClear` is falsy, `clearQueue` calls `queue.clear()` and returns; '
                   'the `reject` stored on each queued item is not invoked by this path.')
    complete = '---\nname: queue\ndescription: The clearQueue branches differ.\ntype: project\n---\n' + actual_body
    for item in value:
        content = item['properties']['content']
        assert 'frontmatter' in content['description']
        assert re.match(content['pattern'], actual_body) is None
        assert re.match(content['pattern'], complete)
        assert 'content' not in item['required']  # Evidence-only/delete amendments remain valid.


def test_no_entry_schema_requires_explicit_parent_reviewed_new_candidate_domain() -> None:
    # Given complete candidate identities, When only one new draft is optional,
    # Then the default schema grants no withdrawal and the explicit domain cannot include existing operations.
    value = isolated_run_bun(r'''
      import {learningOutputSchema} from './packages/continual-learning/extensions/planner-output-schema.ts';
      const id='newMemories:0:'+ 'a'.repeat(64), op='operations:0:'+ 'b'.repeat(64), foreign='newMemories:1:'+ 'c'.repeat(64);
      const plain=learningOutputSchema('memory-semantic-amendment',undefined,[id,op]);
      const opted=learningOutputSchema('memory-semantic-amendment',undefined,[id,op],undefined,[id]);
      const combined=learningOutputSchema('memory-combined-amendment',undefined,[id,op],undefined,[id]);
      const rejected=[];
      for(const [kind,allowed] of [['memory-amendment',[id]],['memory-semantic-amendment',[op]],['memory-semantic-amendment',[foreign]],['memory-semantic-amendment',[id,id]]]) {
        try{learningOutputSchema(kind,undefined,[id,op],undefined,allowed);rejected.push(false)}catch{rejected.push(true)}
      }
      console.log(JSON.stringify({plain:plain.properties,opted:opted.properties.withdrawals,combined:combined.anyOf,rejected}));
    ''')
    assert 'withdrawals' not in value['plain']
    assert value['opted']['items']['properties']['candidateId']['enum'] == ['newMemories:0:' + 'a' * 64]
    assert value['opted']['items']['properties']['candidateRef']['enum'] == ['newMemories:0']
    assert value['opted']['maxItems'] == 32
    assert value['combined'][1]['properties']['withdrawals']['maxItems'] == 0
    assert value['combined'][2]['properties']['operations']['minItems'] == 1
    assert value['rejected'] == [True] * 4
