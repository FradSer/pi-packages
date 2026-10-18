from __future__ import annotations

import json
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
