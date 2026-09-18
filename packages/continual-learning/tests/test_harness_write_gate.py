from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_guardrails_extension import run_bun


@pytest.mark.parametrize('predecessor', ['{broken', '{"policies":[],"disabled":[],"skillPrompts":{}}', '{"rules":[{"id":"bad","skill":"unknown","instructions":"old"}]}', '{"rules":[],"custom":{"owner":"user"}}'])
def test_invalid_predecessor_needs_explicit_ui_authorization(tmp_path: Path, predecessor: str) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      import fs from 'node:fs';import path from 'node:path';
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}};register({{on:(n,f)=>hooks[n]=f,registerCommand(){{}},registerEntryRenderer(){{}},getCommands:()=>[]}});
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(path.join(cwd,'.pi'));
      const target=path.join(cwd,'.pi/harness.json');const before={json.dumps(predecessor)};fs.writeFileSync(target,before);
      const event={{toolName:'write',input:{{path:target,content:JSON.stringify({{rules:[{{id:'valid',bash:'fixture',message:'guide'}}]}})}}}};
      const headless=await hooks.tool_call(event,{{cwd,hasUI:false}});
      const denied=await hooks.tool_call(event,{{cwd,hasUI:true,ui:{{confirm:async()=>false}}}});
      const allowed=await hooks.tool_call(event,{{cwd,hasUI:true,ui:{{confirm:async()=>true}}}});
      console.log(JSON.stringify({{headless,denied,allowed:allowed??null,unchanged:fs.readFileSync(target,'utf8')===before}}));
    ''')
    assert result['headless']['block'] and 'authorization' in result['headless']['reason']
    assert result['denied']['block']
    assert result['allowed'] is None and result['unchanged']


def test_complete_write_rejects_unknown_skills_and_provenance_forgery(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const hooks={{}};register({{on:(n,f)=>hooks[n]=f,registerCommand(){{}},registerEntryRenderer(){{}},getCommands:()=>[{{name:'skill:known',source:'skill'}}]}});
      const cwd={json.dumps(str(tmp_path))},target=cwd+'/.pi/harness.json';
      const invoke=config=>hooks.tool_call({{toolName:'write',input:{{path:target,content:JSON.stringify(config)}}}},{{cwd,hasUI:false}});
      console.log(JSON.stringify({{
        edit:await hooks.tool_call({{toolName:'edit',input:{{path:target,edits:[]}}}},{{cwd}}),
        good:(await invoke({{rules:[{{id:'good',skill:'known',instructions:'guide'}}]}}))??null,
        bad:await invoke({{rules:[{{id:'bad',skill:'invented',instructions:'guide'}}]}}),
        legacy:await invoke({{policies:[],disabled:[],skillPrompts:{{}}}}),
        forged:await invoke({{rules:[],learnedRules:{{manual:{{origin:'consolidation',revision:'fake'}}}}}})
      }}));
    ''')
    assert result['good'] is None
    assert all(result[key]['block'] for key in ['edit','bad','legacy','forged'])


def run_layered_gate(tmp_path: Path, source: str, on_get_commands: str = '') -> dict:
    return run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path / 'agent'))};
      import fs from 'node:fs'; import path from 'node:path';
      const {{createWriteTool}}=await import('@earendil-works/pi-coding-agent');
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const {{resolveHarnessConfig}}=await import('./packages/continual-learning/extensions/guardrail-config.ts');
      const cwd={json.dumps(str(tmp_path / 'project'))};
      fs.mkdirSync(path.join(cwd,'.pi'),{{recursive:true}});
      fs.mkdirSync(process.env.PI_CODING_AGENT_DIR,{{recursive:true}});
      const {{paths}}=resolveHarnessConfig(cwd);
      const files={{user:paths.user,project:paths.project,'project.local':paths.projectLocal}};
      // Genuinely malformed legacy structure, not a valid empty installed config.
      const legacy='{{"policies":{{}},"disabled":[],"skillPrompts":{{}}}}';
      const candidate=JSON.stringify({{rules:[{{id:'candidate',bash:'^fixture$',message:'guidance'}}]}});
      const hooks={{}},commands={{}},entries=[],notices=[];
      register({{on:(n,f)=>hooks[n]=f,registerCommand:(n,c)=>commands[n]=c,
        registerEntryRenderer(){{}},getCommands:()=>{{{on_get_commands};return [];}},appendEntry:(type,data)=>entries.push({{type,data}})}});
      const bytes=()=>Object.fromEntries(Object.entries(files).map(([key,file])=>[key,fs.existsSync(file)?fs.readFileSync(file,'utf8'):null]));
      const event=(scope,content=candidate)=>({{toolName:'write',toolCallId:scope,input:{{path:files[scope],content}}}});
      const context={{cwd,hasUI:true,ui:{{notify:(message,type)=>notices.push({{message,type}})}}}};
      const bash=()=>hooks.tool_call({{toolName:'bash',toolCallId:'probe',input:{{command:'printf harmless'}}}},{{cwd,hasUI:false}});
      {source}
    ''')


@pytest.mark.parametrize('first', ['user', 'project'])
def test_dual_legacy_layers_repair_sequentially_only_after_confirmation_and_native_write(tmp_path: Path, first: str) -> None:
    result = run_layered_gate(tmp_path, f'''
      fs.writeFileSync(files.user,legacy); fs.writeFileSync(files.project,legacy);
      const initial=bytes(), callbacks=[],steps=[];
      const beforeBash=await bash();
      for (const scope of {json.dumps([first, 'project' if first == 'user' else 'user'])}) {{
        const before=bytes();
        const controller=new AbortController();
        const call=event(scope);
        const gate=await hooks.tool_call(call,{{...context,signal:controller.signal,ui:{{...context.ui,
          confirm:async(title,preview,options)=>{{
            callbacks.push({{scope,title,preview,timeout:options.timeout,signal:options.signal===controller.signal,bytes:bytes()}});
            return true;
          }}
        }}}});
        const afterGate=bytes();
        let output=null;
        if (!gate?.block) {{
          const native=await createWriteTool(cwd).execute(scope,call.input);
          const patch=await hooks.tool_result({{...call,...native,isError:false}},context);
          output={{...native,...patch}};
        }}
        const {{config}}=resolveHarnessConfig(cwd);
        const statusStart=notices.length;
        await commands.harness.handler('',context);
        steps.push({{scope,before,gate:gate??null,afterGate,afterWrite:bytes(),output,config,
          bash:(await bash())??null,status:notices.slice(statusStart)}});
      }}
      console.log(JSON.stringify({{initial,beforeBash,callbacks,steps,candidate}}));
    ''')
    assert len(result['callbacks']) == 2, result
    assert result['beforeBash']['block']
    for callback, step in zip(result['callbacks'], result['steps']):
        assert step['gate'] is None
        assert callback['bytes'] == step['before'] == step['afterGate']
        assert callback['timeout'] == 60_000 and callback['signal']
        assert result['candidate'] in callback['preview']
        assert 'policies' in callback['preview']
        assert step['afterWrite'][step['scope']] == result['candidate']
        assert all(step['afterWrite'][scope] == before for scope, before in step['before'].items() if scope != step['scope'])
        assert step['output']['content'][0]['text'].startswith('Successfully wrote')
    first_step, second_step = result['steps']
    other_source = second_step['scope']
    assert 'activation remains incomplete' in result['callbacks'][0]['preview']
    first_output = '\n'.join(block.get('text', '') for block in first_step['output']['content'])
    assert 'activation remains incomplete' in first_output and f'{other_source}:' in first_output
    assert first_step['config']['configReadIncomplete']
    assert not first_step['config']['bashEvaluationComplete']
    assert first_step['bash']['block'] and 'incomplete' in first_step['bash']['reason']
    assert all(error.startswith(f'{other_source}:') for error in first_step['config']['errors'])
    assert 'incomplete' in first_step['status'][0]['message']
    assert second_step['config']['errors'] == []
    assert not second_step['config']['configReadIncomplete'] and second_step['config']['bashEvaluationComplete']
    assert second_step['bash'] is None
    assert 'incomplete' not in second_step['status'][0]['message']
    assert 'incomplete' not in json.dumps(second_step['output'])


@pytest.mark.parametrize('decision', ['headless', 'deny', 'timeout', 'abort'])
def test_other_layer_errors_never_imply_repair_authorization(tmp_path: Path, decision: str) -> None:
    result = run_layered_gate(tmp_path, f'''
      fs.writeFileSync(files.user,legacy); fs.writeFileSync(files.project,legacy);
      const before=bytes(), controller=new AbortController(); let calls=0;
      const decision={json.dumps(decision)};
      const gate=await hooks.tool_call(event('project'),{{...context,hasUI:decision!=='headless',signal:controller.signal,
        ui:{{...context.ui,confirm:async()=>{{
          calls++; if(decision==='abort') controller.abort();
          return decision==='abort'?true:decision==='timeout'?undefined:false;
        }}}}
      }});
      console.log(JSON.stringify({{gate,calls,before,after:bytes(),bash:await bash()}}));
    ''')
    assert result['calls'] == (0 if decision == 'headless' else 1)
    assert result['gate']['block']
    assert 'authoriz' in result['gate']['reason']
    assert result['before'] == result['after']
    assert result['bash']['block']


@pytest.mark.parametrize('candidate', [
    '{broken',
    '{"rules":[],"custom":true}',
    '{"rules":[{"id":"candidate","bash":"[","message":"bad pattern"}]}',
    '{"rules":[{"id":"candidate","skill":"unknown","instructions":"bad skill"}]}',
    '{"rules":[],"learnedRules":{"forged":{"origin":"consolidation","revision":"fake"}}}',
])
def test_repair_never_bypasses_candidate_validation_even_if_shadowed(tmp_path: Path, candidate: str) -> None:
    result = run_layered_gate(tmp_path, f'''
      fs.writeFileSync(files.user,legacy); fs.writeFileSync(files.project,legacy);
      fs.writeFileSync(files['project.local'],candidate);
      const before=bytes(); let calls=0;
      const gate=await hooks.tool_call(event('project',{json.dumps(candidate)}),{{...context,
        ui:{{...context.ui,confirm:async()=>{{calls++;return true;}}}}}});
      console.log(JSON.stringify({{gate,calls,before,after:bytes()}}));
    ''')
    assert result['gate']['block'] and 'Invalid harness configuration' in result['gate']['reason']
    assert result['calls'] == 0 and result['before'] == result['after']


@pytest.mark.parametrize('predecessor', [None, '{"rules":[]}'])
@pytest.mark.parametrize('other_invalid', [False, True])
def test_valid_or_missing_target_keeps_strict_effective_validation(tmp_path: Path, predecessor: str | None, other_invalid: bool) -> None:
    result = run_layered_gate(tmp_path, f'''
      const predecessor={json.dumps(predecessor)};
      if(predecessor!==null) fs.writeFileSync(files.project,predecessor);
      if({json.dumps(other_invalid)}) fs.writeFileSync(files.user,legacy);
      const before=bytes(); let calls=0;
      const gate=await hooks.tool_call(event('project'),{{...context,ui:{{...context.ui,confirm:async()=>{{calls++;return true;}}}}}});
      console.log(JSON.stringify({{gate:gate??null,calls,before,after:bytes()}}));
    ''')
    if other_invalid:
        assert result['gate']['block'] and 'Invalid effective' in result['gate']['reason']
    else:
        assert result['gate'] is None
    assert result['calls'] == 0 and result['before'] == result['after']


@pytest.mark.parametrize('other', [
    '{broken',
    '{"rules":[{"id":"broken-bash","bash":"[","message":"fix"}]}',
    '{"rules":[{"id":"project: misleading diagnostic","skill":"unknown","instructions":"fix"}]}',
])
@pytest.mark.parametrize('target', ['user', 'project', 'project.local'])
def test_unchanged_other_layer_diagnostics_are_attributed_before_authorized_repair(tmp_path: Path, other: str, target: str) -> None:
    result = run_layered_gate(tmp_path, f'''
      const target={json.dumps(target)},other=target==='user'?'project':'user';
      fs.writeFileSync(files[target],legacy);fs.writeFileSync(files[other],{json.dumps(other)});
      const before=bytes();let calls=0,preview='';
      const gate=await hooks.tool_call(event(target),{{...context,ui:{{...context.ui,
        confirm:async(_title,text)=>{{calls++;preview=text;return true;}}
      }}}});
      console.log(JSON.stringify({{gate:gate??null,calls,preview,other,before,after:bytes()}}));
    ''')
    assert result['calls'] == 1 and result['gate'] is None
    assert f"{result['other']}:" in result['preview'] and 'activation remains incomplete' in result['preview']
    assert result['before'] == result['after']


@pytest.mark.parametrize('changed', ['project', 'user', 'project.local'])
def test_repair_rechecks_target_and_unchanged_layers_after_confirmation(tmp_path: Path, changed: str) -> None:
    result = run_layered_gate(tmp_path, f'''
      fs.writeFileSync(files.user,legacy);fs.writeFileSync(files.project,legacy);
      const before=bytes(); let calls=0;
      // The diagnostic text stays identical when only legacy payload bytes change.
      const changed={json.dumps(changed)},concurrent='{{"policies":[{{"name":"concurrent"}}],"disabled":[],"skillPrompts":{{}}}}';
      const gate=await hooks.tool_call(event('project'),{{...context,ui:{{...context.ui,confirm:async()=>{{
        calls++;fs.writeFileSync(files[changed],concurrent);return true;
      }}}}}});
      console.log(JSON.stringify({{gate:gate??null,calls,before,after:bytes(),changed,concurrent}}));
    ''')
    assert result['calls'] == 1
    assert result['gate']['block'] and 'changed during authorization' in result['gate']['reason']
    assert result['after'][changed] == result['concurrent']
    assert all(result['after'][scope] == before for scope, before in result['before'].items() if scope != changed)


@pytest.mark.parametrize('repair', [False, True])
@pytest.mark.parametrize('action', ['block', 'confirm'])
def test_preflight_policy_change_is_evaluated_before_native_write(tmp_path: Path, repair: bool, action: str) -> None:
    policy = {
        'name': 'new-policy', 'tools': ['write'], 'paths': ['content'],
        'pattern': 'FORBIDDEN', 'action': action, 'reason': 'Newly installed protection',
    }
    result = run_layered_gate(tmp_path, f'''
      const repair={json.dumps(repair)};
      fs.writeFileSync(files.project,repair?legacy:'{{"rules":[]}}');
      if(repair) fs.writeFileSync(files.user,legacy);
      const before=bytes();let repairApprovals=0,policyApprovals=0;
      const call=event('project',JSON.stringify({{rules:[{{id:'candidate',text:'FORBIDDEN',instructions:'fixture'}}]}}));
      const gate=await hooks.tool_call(call,{{...context,ui:{{...context.ui,
        confirm:async()=>{{repairApprovals++;return true;}},
        select:async()=>{{policyApprovals++;return 'Block';}}
      }}}});
      const afterGate=bytes();let nativeWrites=0;
      if(!gate?.block) {{await createWriteTool(cwd).execute('preflight',call.input);nativeWrites++;}}
      console.log(JSON.stringify({{gate:gate??null,before,afterGate,afterWrite:bytes(),repairApprovals,policyApprovals,nativeWrites}}));
    ''', on_get_commands=f"fs.writeFileSync(files['project.local'],JSON.stringify({json.dumps({'policies': [policy]})}))")
    assert result['repairApprovals'] == int(repair)
    assert result['policyApprovals'] == (1 if action == 'confirm' else 0)
    assert result['gate'] and result['gate']['block'], result
    assert 'Newly installed protection' in result['gate']['reason']
    assert result['nativeWrites'] == 0
    assert result['afterWrite'] == result['afterGate']
    assert result['afterWrite']['project'] == result['before']['project']
    assert json.loads(result['afterWrite']['project.local']) == {'policies': [policy]}


@pytest.mark.parametrize('changed', [None, 'project', 'user', 'project.local', 'create-local', 'remove-local'])
def test_repair_byte_snapshot_survives_later_policy_confirmation(tmp_path: Path, changed: str | None) -> None:
    result = run_layered_gate(tmp_path, f'''
      const policy={{name:'confirm-config-write',tools:['write'],paths:['content'],pattern:'candidate',action:'confirm',reason:'Approve this configuration write'}};
      const prior={{rules:[{{id:'broken',text:'[',instructions:'Original invalid payload'}}],policies:[policy]}};
      fs.writeFileSync(files.project,JSON.stringify(prior));
      fs.writeFileSync(files.user,'{{"policies":{{"original":true}}}}');
      const changed={json.dumps(changed)};
      if(changed!=='create-local') fs.writeFileSync(files['project.local'],'{{"rules":[],"learnedRules":{{"manual":{{"revision":"old"}}}}}}');
      const call=event('project',JSON.stringify({{rules:[{{id:'candidate',text:'fixture',instructions:'Approved candidate'}}],policies:[policy]}}));
      const before=bytes(), initial=JSON.stringify(resolveHarnessConfig(cwd).config);
      const changedFile=changed==='create-local'||changed==='remove-local'?'project.local':changed;
      let repairApprovals=0,policyApprovals=0,concurrent=null;
      const gate=await hooks.tool_call(call,{{...context,ui:{{...context.ui,
        confirm:async()=>{{repairApprovals++;return true;}},
        select:async()=>{{
          policyApprovals++;
          if(changed==='project') concurrent=JSON.stringify({{...prior,rules:[{{...prior.rules[0],instructions:'New manual instructions'}}]}});
          else if(changed==='user') concurrent='{{"policies":{{"newManualPayload":true}}}}';
          else if(changed==='project.local') concurrent='{{"rules":[],"learnedRules":{{"manual":{{"revision":"new"}}}}}}';
          else if(changed==='create-local') concurrent='{{"rules":[]}}';
          if(changed==='remove-local') fs.unlinkSync(files[changedFile]);
          else if(changedFile) fs.writeFileSync(files[changedFile],concurrent);
          return 'Allow once';
        }}
      }}}});
      const afterGate=bytes();
      const resolvedUnchanged=initial===JSON.stringify(resolveHarnessConfig(cwd).config);
      let nativeWrites=0;
      if(!gate?.block) {{await createWriteTool(cwd).execute('repair',call.input);nativeWrites++;}}
      console.log(JSON.stringify({{gate:gate??null,before,afterGate,afterWrite:bytes(),concurrent,changedFile,repairApprovals,policyApprovals,resolvedUnchanged,nativeWrites,entries,candidate:call.input.content}}));
    ''')
    assert result['repairApprovals'] == result['policyApprovals'] == 1
    assert result['resolvedUnchanged'], 'Fixture must reproduce same resolved diagnostics despite changed raw bytes'
    if changed is None:
        assert result['gate'] is None and result['nativeWrites'] == 1
        assert result['afterGate'] == result['before']
        assert result['afterWrite']['project'] == result['candidate']
        assert sum(entry['data'].get('outcome') == 'allowed once' for entry in result['entries']) == 1
    else:
        assert result['gate'] and result['gate']['block'], result
        assert 'changed' in result['gate']['reason']
        assert result['nativeWrites'] == 0
        assert result['afterWrite'][result['changedFile']] == result['concurrent']
        assert result['afterWrite'] == result['afterGate']
        assert not any(entry['data'].get('outcome') == 'allowed once' for entry in result['entries'])


def test_authoring_prompt_explains_target_only_repair_with_remaining_diagnostics() -> None:
    prompt = run_bun('''
      import {buildHarnessRulePrompt} from './packages/continual-learning/extensions/guardrails.ts';
      console.log(JSON.stringify(buildHarnessRulePrompt('repair legacy target','/tmp/project/.pi/harness.json')));
    ''')
    assert 'unchanged other layers' in prompt
    assert 'submit the valid target-only replacement via write for native confirmation' in prompt
    assert 'report incomplete activation' in prompt
    assert len(prompt) < 6500


def test_write_diagnostics_preserve_native_results_and_do_not_trigger_text_guidance(tmp_path: Path) -> None:
    result = run_layered_gate(tmp_path, '''
      fs.writeFileSync(files.user,legacy);
      const call=event('project');
      const native=await createWriteTool(cwd).execute('project',call.input);
      const original={...call,...native,isError:false,details:{fixture:'native metadata'}};
      const patch=await hooks.tool_result(original,context);
      const merged={...original,...patch};
      const {extractModelVisibleTexts}=await import('./packages/continual-learning/extensions/harness-guidance-planner.ts');
      const scanned=extractModelVisibleTexts([{role:'toolResult',...merged}]);
      const {mergeLayers,evaluateText}=await import('./packages/continual-learning/extensions/guardrail-engine.ts');
      const guidance=mergeLayers([{source:'fixture',rules:[
        {id:'note-only',text:'policies',instructions:'must not trigger'},
        {id:'native-text',text:'Successfully wrote',instructions:'native output still matches'}
      ]}]);
      const matches=evaluateText(guidance,scanned).matches.map(rule=>rule.id);
      const failed=await hooks.tool_result({...original,isError:true},context);
      const ordinary=await hooks.tool_result({...original,input:{path:'notes.txt'}},context);
      // Reporting reads current configuration, not an earlier approval snapshot.
      fs.writeFileSync(files.user,'{"rules":[]}');
      const repaired=await hooks.tool_result(original,context);
      console.log(JSON.stringify({native,original,merged,scanned,matches,failed:failed??null,ordinary:ordinary??null,repaired:repaired??null}));
    ''')
    assert result['merged']['content'][0] == result['native']['content'][0]
    assert 'activation remains incomplete' in result['merged']['content'][1]['text']
    assert result['merged']['details'] == result['original']['details']
    assert result['merged']['isError'] is False
    assert result['scanned'] == [result['native']['content'][0]['text']]
    assert result['matches'] == ['native-text']
    assert result['failed'] is result['ordinary'] is result['repaired'] is None
