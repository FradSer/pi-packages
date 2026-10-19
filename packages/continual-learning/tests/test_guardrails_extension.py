from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from support import ENGINE, isolated_run_bun as run_bun


def test_default_rules_block_auth_and_otp_but_allow_normal_calls() -> None:
    result = run_bun(f'''
      import {{DEFAULT_RULES,mergeLayers,evaluateBash}} from '{ENGINE}';
      const config=mergeLayers([{{source:'defaults',rules:DEFAULT_RULES}}]);
      console.log(JSON.stringify(['npm login','pnpm adduser','printf otp > /tmp/code','pnpm test'].map(command=>evaluateBash(config,command))));
    ''')
    assert [r['decision'] for r in result] == ['block', 'block', 'block', 'execute']
    assert 'their own terminal' in result[0]['reason']


def test_nearest_rule_completely_replaces_same_id_and_ids_are_exact() -> None:
    result = run_bun(f'''
      import {{mergeLayers,evaluateBash}} from '{ENGINE}';
      const config=mergeLayers([{{source:'user',rules:[{{id:'a',bash:'alpha',action:'block',message:'outer'}},{{id:' a ',bash:'gamma',message:'distinct'}}]}},{{source:'project',rules:[{{id:'a',bash:'beta',message:'inner'}}]}}]);
      console.log(JSON.stringify({{config,alpha:evaluateBash(config,'alpha'),beta:evaluateBash(config,'beta')}}));
    ''')
    assert result['alpha']['matchedRules'] == []
    assert result['beta']['decision'] == 'execute'
    assert result['beta']['messages'] == ['inner']
    assert [r['id'] for r in result['config']['rules']] == [' a ', 'a']


def test_harness_target_resolution_defaults_and_flags() -> None:
    result = run_bun('''
      import {resolveHarnessTarget} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(['x','--global x','-g x','--shared x','--project x','--repo x','--local x','--user x'].map(args=>resolveHarnessTarget(args,'/tmp/project','/tmp/agent'))));
    ''')
    assert [r['scope'] for r in result] == ['project','user','user','project','project','project','project.local','user']
    assert result[0]['targetFile'] == '/tmp/project/.pi/harness.json'
    assert result[1]['targetFile'] == '/tmp/agent/harness.json'
    assert all(r['request'] == 'x' for r in result)


def test_exact_layer_order_and_no_mtime_cache_blind_spot(tmp_path: Path) -> None:
    agent = tmp_path / 'agent'
    project = tmp_path / 'project'
    (project / '.pi/agent').mkdir(parents=True)
    agent.mkdir()
    def config(message: str) -> str:
        return json.dumps({'rules':[{'id':'layered','bash':'fixture','message':message}]})
    for target, text in [(agent/'harness.json','user'), (agent/'harness.local.json','ignored'), (project/'.pi/harness.json','project'), (project/'.pi/harness.local.json','local'), (project/'.pi/agent/harness.json','ignored')]:
        target.write_text(config(text))
    result = run_bun(f'''
      import fs from 'node:fs';
      import {{loadLayers,resolveHarnessConfig,configPaths}} from './packages/continual-learning/extensions/guardrail-config.ts';
      const cwd={json.dumps(str(project))}, agent={json.dumps(str(agent))};
      const first=resolveHarnessConfig(cwd,agent); const file=first.paths.projectLocal;
      const stat=fs.statSync(file);fs.writeFileSync(file,{json.dumps(config('newer'))});fs.utimesSync(file,stat.atime,stat.mtime);
      const second=resolveHarnessConfig(cwd,agent);
      console.log(JSON.stringify({{keys:Object.keys(configPaths(cwd,agent)),sources:loadLayers(cwd,agent).map(l=>l.source),first:first.config.rules.find(r=>r.id==='layered').message,second:second.config.rules.find(r=>r.id==='layered').message}}));
    ''')
    assert result == {'keys':['user','userScoped','project','projectLocal'],
                      # This fixture writes no scoped user file, so that layer is
                      # absent; coverage for it lives in test_harness_user_scope.py.
                      'sources':['user','project','project.local'],
                      'first':'local','second':'newer'}


@pytest.mark.parametrize('malformed', ['{broken', '{"rules":[{"id":"same","bash":"x","message":"x"},{"id":"same","enabled":false}]}', '{"rules":[],"policies":{}}'])
def test_structural_errors_use_last_identity_unambiguous_snapshot(tmp_path: Path, malformed: str) -> None:
    (tmp_path / '.pi').mkdir()
    file = tmp_path / '.pi/harness.json'
    file.write_text(json.dumps({'rules':[{'id':'kept','bash':'fixture','action':'block','message':'keep'}]}))
    result = run_bun(f'''
      import fs from 'node:fs';
      import {{resolveHarnessConfig}} from './packages/continual-learning/extensions/guardrail-config.ts';
      import {{evaluateBash}} from '{ENGINE}';
      const cwd={json.dumps(str(tmp_path))}, agent={json.dumps(str(tmp_path/'agent'))};
      resolveHarnessConfig(cwd,agent);fs.writeFileSync({json.dumps(str(file))},{json.dumps(malformed)});
      const {{config}}=resolveHarnessConfig(cwd,agent);
      console.log(JSON.stringify({{config,decision:evaluateBash(config,'fixture'),bytes:fs.readFileSync({json.dumps(str(file))},'utf8')}}));
    ''')
    assert result['config']['configReadIncomplete']
    assert result['decision']['decision'] == 'block'
    assert result['bytes'] == malformed


@pytest.mark.parametrize('symlink_parent', [False, True])
def test_tool_gate_rejects_symlinked_target_or_parent(tmp_path: Path, symlink_parent: bool) -> None:
    project = tmp_path / 'project'; project.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    target = project / '.pi/harness.json'
    if symlink_parent:
        (project / '.pi').symlink_to(outside, target_is_directory=True)
    else:
        target.parent.mkdir(); (outside/'harness.json').write_text('{"rules":[]}'); target.symlink_to(outside/'harness.json')
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}};register({{on:(n,f)=>hooks[n]=f,registerEntryRenderer(){{}},registerCommand(){{}},getCommands:()=>[]}});
      console.log(JSON.stringify(await hooks.tool_call({{toolName:'write',input:{{path:{json.dumps(str(target))},content:'{{"rules":[]}}'}}}},{{cwd:{json.dumps(str(project))}}})));
    ''')
    assert result['block'] and 'Unsafe' in result['reason']


@pytest.mark.parametrize('content', [None, '', '   \n\t\n', '\n', 'null', '{}', '{"rules":[]}'])
def test_absent_or_empty_configuration_executes_by_default(tmp_path: Path, content: str | None) -> None:
    # Given no declarations at all, When tools are evaluated, Then nothing holds:
    # an absent configuration is the default state, not an unreadable one.
    project = tmp_path / 'project'; project.mkdir()
    if content is not None:
        (project / '.pi').mkdir()
        (project / '.pi/harness.local.json').write_text(content)
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}},entries=[];
      register({{on:(n,f)=>hooks[n]=f,appendEntry:(t,d)=>entries.push({{t,d}}),registerEntryRenderer(){{}},registerCommand(){{}},getCommands:()=>[]}});
      const ctx={{cwd:{json.dumps(str(project))},hasUI:false,ui:{{notify(){{}},confirm:async()=>false}}}};
      const bash=await hooks.tool_call({{toolName:'bash',input:{{command:'pnpm test'}}}},ctx);
      const read=await hooks.tool_call({{toolName:'read',input:{{path:'README.md'}}}},ctx);
      console.log(JSON.stringify({{bash:bash??null,read:read??null,emptyNotices:entries.filter(e=>e.t==='harness-event').length}}));
    ''')
    assert result['bash'] is None, result
    assert result['read'] is None, result
    assert result['emptyNotices'] == 0, result


def test_incomplete_evaluation_names_the_unreadable_layer_file_and_error(tmp_path: Path) -> None:
    project = tmp_path / 'project'; (project / '.pi').mkdir(parents=True)
    # No snapshot exists in this process, so the layer cannot be evaluated at all.
    broken = project / '.pi/harness.local.json'
    broken.write_text('{broken')
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}},entries=[];
      register({{on:(n,f)=>hooks[n]=f,appendEntry:(t,d)=>entries.push({{t,d}}),registerEntryRenderer(){{}},registerCommand(){{}},getCommands:()=>[]}});
      const ctx={{cwd:{json.dumps(str(project))},ui:{{notify(){{}},confirm:async()=>false}}}};
      const blocked=await hooks.tool_call({{toolName:'bash',input:{{command:'pnpm test'}}}},ctx);
      const read=await hooks.tool_call({{toolName:'read',input:{{path:{json.dumps(str(broken))}}}}},ctx);
      console.log(JSON.stringify({{blocked,read,entries}}));
    ''')
    assert result['blocked']['block']
    reason = result['blocked']['reason']
    # The blocked call must say which file could not be read and why; a generic
    # "unreadable configuration" leaves the user and the model without a repair.
    assert str(broken) in reason, reason
    assert 'invalid JSON' in reason, reason
    # Diagnosing that file stays possible while execution remains unexecuted.
    assert not (result.get('read') or {}).get('block')
    events = [entry for entry in result['entries'] if entry['t'] == 'harness-event']
    assert events and events[-1]['d']['file'] == str(broken), events
    # The diagnostics the block message points at name the same file and reason.
    diagnostics = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const commands={{}},notices=[];
      register({{on(){{}},appendEntry(){{}},registerEntryRenderer(){{}},getCommands:()=>[],registerCommand:(name,def)=>commands[name]=def}});
      await commands.harness.handler('', {{cwd:{json.dumps(str(project))},mode:'tui',ui:{{notify:text=>notices.push(text)}}}});
      console.log(JSON.stringify({{notices}}));
    ''')
    rendered = '\n'.join(diagnostics['notices'])
    assert 'config read incomplete' in rendered, rendered
    assert str(broken) in rendered and 'invalid JSON' in rendered, rendered
    assert 'execution held' in rendered, rendered
    # Authorized repair stays available: a complete validated replacement is
    # confirmed, written, and the repaired layer then evaluates normally.
    repaired = json.dumps({'rules': [{'id': 'probe', 'bash': 'probe-command', 'action': 'block', 'message': 'probe rule'}]})
    recovery = run_bun(f'''
      import fs from 'node:fs';
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}};register({{on:(n,f)=>hooks[n]=f,appendEntry(){{}},registerEntryRenderer(){{}},registerCommand(){{}},getCommands:()=>[]}});
      const ctx={{cwd:{json.dumps(str(project))},hasUI:true,ui:{{notify(){{}},confirm:async()=>true}}}};
      const target={json.dumps(str(broken))}, content={json.dumps(repaired)};
      const write=await hooks.tool_call({{toolName:'write',input:{{path:target,content}}}},ctx);
      fs.writeFileSync(target, content);
      const plain=await hooks.tool_call({{toolName:'bash',input:{{command:'pnpm test'}}}},ctx);
      const matched=await hooks.tool_call({{toolName:'bash',input:{{command:'probe-command'}}}},ctx);
      console.log(JSON.stringify({{writeAllowed:!write?.block,plainBlocked:!!plain?.block,matchedReason:matched?.reason}}));
    ''')
    assert recovery['writeAllowed'], recovery
    assert not recovery['plainBlocked'], recovery
    assert recovery['matchedReason'] == 'probe rule', recovery


def test_harness_behavior_binds_rule_revision_call_and_actual_handler_observation(tmp_path: Path) -> None:
    # Given an effective rule revision, When its matching call is allowed or
    # blocked, Then bind the native call and actual handler observation separately.
    project = tmp_path / 'project'; (project / '.pi').mkdir(parents=True)
    rule = {'id': 'version', 'bash': '^npm', 'message': 'Version probe.'}
    (project / '.pi/harness.json').write_text(json.dumps({'rules': [rule]}))
    value = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      import fs from 'node:fs';
      import {{ruleRevision}} from '{ENGINE}';
      import {{createHash}} from 'node:crypto';
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}},entries=[];let leaf='user-entry';
      const pi={{on:(n,f)=>(hooks[n]??=[]).push(f),appendEntry:(customType,data)=>{{leaf='entry-'+entries.length;entries.push({{id:leaf,customType,data}})}},registerEntryRenderer(){{}},registerCommand(){{}},getCommands:()=>[]}};
      register(pi);const ctx={{cwd:{json.dumps(str(project))},hasUI:false,ui:{{notify(){{}}}},sessionManager:{{getSessionId:()=> 'session-a',getLeafId:()=>leaf}}}};
      const call=async(id)=>{{for(const f of hooks.tool_call??[]){{const r=await f({{toolName:'bash',toolCallId:id,input:{{command:'npm --version'}}}},ctx);if(r?.block)return r}}}};
      const end=async(id,extra)=>{{for(const f of hooks.tool_execution_end??[])await f({{toolName:'bash',toolCallId:id,result:{{content:[{{type:'text',text:'12.0.0'}}],details:{{exitCode:0}}}},isError:false,...extra}},ctx)}};
      await call('allowed');await end('allowed',{{durationMs:1}});await end('allowed',{{durationMs:2}});
      fs.writeFileSync({json.dumps(str(project/'.pi/harness.json'))},JSON.stringify({{rules:[{{...{json.dumps(rule)},action:'block'}}]}}));
      await call('blocked');await end('blocked',{{}});
      await end('foreign',{{durationMs:1}});
      console.log(JSON.stringify({{entries:entries.filter(x=>x.customType==='harness-behavior-observation'),revision:ruleRevision({json.dumps(rule)}),idDigest:createHash('sha256').update(JSON.stringify('version')).digest('hex')}}));
    ''')
    events = value['entries']
    assert len(events) == 4, value
    decisions = [x for x in events if x['data']['phase'] == 'decision']
    results = [x for x in events if x['data']['phase'] == 'handler-result']
    assert [x['data']['toolCallIdDigest'] for x in decisions] == [hashlib.sha256(json.dumps(call).encode()).hexdigest() for call in ('allowed', 'blocked')]
    assert next(r for r in decisions[0]['data']['rules'] if r.get('idDigest') == value['idDigest'])['revision'] == value['revision']
    assert next(r for r in decisions[1]['data']['rules'] if r.get('idDigest') == value['idDigest'])['revision'] != value['revision']
    assert next(r for r in decisions[0]['data']['rules'] if r.get('idDigest') == value['idDigest'])['source'] == 'project'
    assert [x['data']['handlerInvoked'] for x in results] == [True, None]
    assert results[0]['data']['decisionEntryId'] == decisions[0]['id']
    assert results[1]['data']['decisionEntryId'] == decisions[1]['id']
    assert all(x['data']['effect'] == 'cannot-attribute' for x in results)
    assert all(x['data']['taskOutcome'] == 'unverified' for x in results)
    assert 'npm --version' not in json.dumps(events)
    assert '12.0.0' not in json.dumps(events)


@pytest.mark.parametrize('case', ['duplicate', 'reuse', 'foreign-session', 'branch', 'invalid-time', 'capacity'])
def test_harness_behavior_keeps_ambiguous_or_incomplete_observations_unverified(tmp_path: Path, case: str) -> None:
    value = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}},rows=[];let leaf='user-entry',session='session-a';
      register({{on:(n,f)=>(hooks[n]??=[]).push(f),appendEntry:(customType,data)=>{{leaf='entry-'+rows.length;rows.push({{id:leaf,customType,data}})}},registerEntryRenderer(){{}},registerCommand(){{}},getCommands:()=>[]}});
      const ctx={{cwd:{json.dumps(str(tmp_path))},hasUI:false,ui:{{notify(){{}}}},sessionManager:{{getSessionId:()=>session,getLeafId:()=>leaf}}}};
      const call=async(id)=>{{for(const f of hooks.tool_call??[])await f({{toolName:'bash',toolCallId:id,input:{{command:'printf safe'}}}},ctx)}};
      const end=async(id,durationMs)=>{{for(const f of hooks.tool_execution_end??[])await f({{toolName:'bash',toolCallId:id,result:{{content:[]}},isError:false,durationMs}},ctx)}};
      const mode={json.dumps(case)};await call('a');
      if(mode==='reuse')await end('a',1);
      if(mode==='branch')for(const f of hooks.session_tree??[])await f({{}},ctx);
      if(['duplicate','reuse','branch'].includes(mode)){{await call('a');await end('a',1)}}
      if(mode==='foreign-session'){{session='session-b';await end('a',1)}}
      if(mode==='invalid-time')await end('a',NaN);
      if(mode==='capacity'){{for(let i=0;i<256;i++)await call('extra-'+i);await end('extra-255',1)}}
      const events=rows.filter(r=>r.customType==='harness-behavior-observation');
      console.log(JSON.stringify({{decisions:events.filter(r=>r.data.phase==='decision').map(r=>({{tracking:r.data.handlerTracking,coverage:r.data.revisionCoverage}})),results:events.filter(r=>r.data.phase==='handler-result').map(r=>r.data)}}));
    ''')
    results = value['results']
    if case in ('duplicate', 'foreign-session', 'branch', 'capacity'):
        assert results == [], value
    elif case == 'reuse':
        assert len(results) == 1 and results[0]['handlerInvoked'] is True, value
    else:
        assert len(results) == 1 and results[0]['handlerInvoked'] is None, value
        assert results[0]['handlerTiming'] == 'invalid'
    if case in ('duplicate', 'reuse', 'branch', 'capacity'):
        assert value['decisions'][-1]['tracking'] == 'unavailable', value
    assert all(r['effect'] == 'cannot-attribute' and r['taskOutcome'] == 'unverified' for r in results)


@pytest.mark.parametrize('case', ['append-failure', 'end-append-failure', 'accessor-failure', 'private-id', 'private-call-id', 'switch-during-confirm'])
def test_harness_observation_cannot_change_execution_leak_ids_or_rebind_old_calls(tmp_path: Path, case: str) -> None:
    value = run_bun(f'''
      import fs from 'node:fs';
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const mode={json.dumps(case)},sentinel='PRIVATE_COMMAND_BODY_MARKER printf private';
      fs.mkdirSync({json.dumps(str(tmp_path/'.pi'))});
      fs.writeFileSync({json.dumps(str(tmp_path/'.pi/harness.json'))},JSON.stringify({{rules:[{{id:mode==='private-id'?sentinel:'rule',bash:'^printf',message:'note',...(mode==='switch-during-confirm'?{{action:'confirm'}}:{{}})}}]}}));
      const hooks={{}},rows=[];let session='session-a',leaf='user-a';
      register({{on:(n,f)=>(hooks[n]??=[]).push(f),appendEntry:(customType,data)=>{{if(customType==='harness-behavior-observation'&&(mode==='append-failure'||mode==='end-append-failure'&&data.phase==='handler-result'))throw Error('Observation unavailable');leaf='entry-'+rows.length;rows.push({{id:leaf,customType,data}})}},registerEntryRenderer(){{}},registerCommand(){{}},getCommands:()=>[]}});
      const ctx={{cwd:{json.dumps(str(tmp_path))},hasUI:mode==='switch-during-confirm',ui:{{notify(){{}},select:async()=>{{for(const f of hooks.session_shutdown??[])await f({{}},ctx);session='session-b';leaf='user-b';for(const f of hooks.session_start??[])await f({{}},ctx);return 'Allow once'}}}},sessionManager:{{getSessionId:()=>{{if(mode==='accessor-failure')throw Error('Session unavailable');return session}},getLeafId:()=>leaf}}}};
      const callId=mode==='private-call-id'?sentinel:'old-call';
      let call='allowed';try{{for(const f of hooks.tool_call??[]){{const r=await f({{toolName:'bash',toolCallId:callId,input:{{command:'printf safe'}}}},ctx);if(r?.block)call='blocked'}}}}catch{{call='threw'}}
      for(const f of hooks.tool_execution_end??[])await f({{toolName:'bash',toolCallId:callId,result:{{content:[]}},isError:false,durationMs:1}},ctx);
      const observations=rows.filter(r=>r.customType==='harness-behavior-observation');
      console.log(JSON.stringify({{call,leaked:JSON.stringify(observations).includes(sentinel),observations}}));
    ''')
    assert value['call'] == ('blocked' if case == 'switch-during-confirm' else 'allowed'), value
    assert value['leaked'] is False, value
    if case in ('append-failure', 'accessor-failure', 'switch-during-confirm'):
        assert value['observations'] == [], value
    else:
        rule = next(r for r in value['observations'][0]['data']['rules'] if r['matched'])
        assert rule['action'] == 'message'
        assert 'id' not in rule and len(rule['idDigest']) == 64
        if case == 'end-append-failure':
            assert len(value['observations']) == 1
        if case == 'private-call-id':
            assert all(len(r['data']['toolCallIdDigest']) == 64 for r in value['observations'])
