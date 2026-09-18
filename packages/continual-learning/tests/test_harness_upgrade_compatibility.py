from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_guardrails_extension import run_bun

# Sanitized existing local shape: no real config is read or modified.
LEGACY = {
    'policies': [
        {'name': 'no-project-memory-local-writes', 'tools': ['write', 'edit'],
         'require': {'path': 'path', 'pattern': r'(^|/)\.memory\.local(?:/|$)'},
         'paths': ['content', 'newText', 'edits.newText'], 'pattern': r'[\s\S]+',
         'action': 'block', 'reason': 'Use the canonical private memory root.'},
        {'name': 'pi-kit-no-markdown-agent-run-helper', 'tools': ['write', 'edit'],
         'paths': ['content', 'newText'],
         'require': {'path': 'path', 'pattern': r'^packages/kit/src/.*\.ts$'},
         'pattern': r'\bcreatePackageAgentRun\b', 'action': 'block',
         'reason': 'Use the approved structured run API.'},
    ],
    'disabled': [], 'skillPrompts': {},
    'learnedPolicies': {name: {'origin': 'consolidation', 'learnedAt': '2020-01-01T00:00:00Z'} for name in ['no-project-memory-local-writes', 'pi-kit-no-markdown-agent-run-helper']},
}


def gate_script(tmp_path: Path, body: str, config: dict | None = None) -> str:
    return f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      import fs from 'node:fs';import path from 'node:path';
      const {{default:register}}=await import('./packages/continual-learning/extensions/guardrails.ts');
      const {{resolveHarnessConfig}}=await import('./packages/continual-learning/extensions/guardrail-config.ts');
      const hooks={{}},commands={{}},entries=[],previews=[];let choice='Allow once',approval=true;
      register({{on:(n,f)=>hooks[n]=f,registerCommand:(n,c)=>commands[n]=c,registerEntryRenderer(){{}},appendEntry:(t,d)=>entries.push(d),getCommands:()=>[]}});
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(path.join(cwd,'.pi'),{{recursive:true}});
      const file=path.join(cwd,'.pi/harness.local.json'),before=JSON.stringify({json.dumps(config if config is not None else LEGACY)});
      fs.writeFileSync(file,before);
      const ctx={{cwd,hasUI:true,ui:{{select:async(title,opts,options)=>{{previews.push(title);return choice}},confirm:async(title,preview)=>{{previews.push(title+'\\n'+preview);return approval}},notify(){{}}}}}};
      let counter=0;
      const call=async(toolName,input,context=ctx)=>await hooks.tool_call({{toolName,toolCallId:'c'+(++counter),input}},context)??null;
      {body}
    '''


def test_actual_legacy_shape_keeps_narrow_guards_without_bash_lockout(tmp_path: Path) -> None:
    result = run_bun(gate_script(tmp_path, '''
      const results=await Promise.all([
        call('bash',{command:'printf harness-safe'}),
        call('write',{path:'.memory.local/note.md',content:'private'}),
        call('edit',{path:'.memory.local/note.md',edits:[{oldText:'old',newText:'private'}]}),
        call('write',{path:'packages/kit/src/helper.ts',content:'createPackageAgentRun()'}),
        call('edit',{path:'packages/kit/src/helper.ts',edits:[{oldText:'old',newText:'createPackageAgentRun()'}]}),
        call('edit',{path:'packages/kit/src/helper.ts',edits:[{oldText:'createPackageAgentRun()',newText:''}]}),
        call('edit',{path:'.memory.local/note.md',edits:[{oldText:'private',newText:''}]}),
        call('write',{path:'notes.md',content:'createPackageAgentRun()'})
      ]);
      const config=resolveHarnessConfig(cwd).config;
      console.log(JSON.stringify({results,config,unchanged:fs.readFileSync(file,'utf8')===before}));
    '''))
    assert result['results'][0] is None, result
    assert all(item and item['block'] for item in result['results'][1:5])
    assert result['results'][5:] == [None, None, None]
    assert result['unchanged'] and result['config']['errors'] == []
    assert result['config']['notices'] and not result['config']['configReadIncomplete']


@pytest.mark.parametrize('tools,blocked', [(['write'], [False, True, False]), (None, [True, True, True])])
def test_invalid_legacy_known_tools_fail_closed_without_globalizing_scope(tmp_path: Path, tools: list | None, blocked: list) -> None:
    policy = {'name': 'invalid', 'pattern': '(', 'reason': 'broken'}
    if tools is not None:
        policy['tools'] = tools
    result = run_bun(gate_script(tmp_path, '''
      const results=await Promise.all([call('bash',{command:'safe'}),call('write',{path:'note',content:'x'}),call('read',{path:'note'})]);
      const recovery=await call('read',{path:file});
      console.log(JSON.stringify({results,recovery,config:resolveHarnessConfig(cwd).config}));
    ''', {'policies': [policy]}))
    assert [bool(item and item['block']) for item in result['results']] == blocked
    assert result['recovery'] is None
    assert result['config']['errors']


def test_mixed_actions_are_aggregated_before_any_confirmation(tmp_path: Path) -> None:
    config = {'rules': [{'id': 'flat', 'bash': 'fixture', 'action': 'confirm', 'message': 'flat reason'}],
              'policies': [{'name': 'observe', 'tools': ['bash'], 'pattern': 'fixture', 'action': 'observe'},
                           {'name': 'legacy', 'tools': ['bash'], 'pattern': 'fixture', 'action': 'block', 'reason': 'legacy reason'}]}
    result = run_bun(gate_script(tmp_path, '''
      const blocked=await call('bash',{command:'fixture'}),beforeConfirm=previews.length;
      const changed=JSON.parse(before);changed.policies[1].action='confirm';fs.writeFileSync(file,JSON.stringify(changed));
      const allowed=await call('bash',{command:'fixture'});
      choice='Block';const denied=await call('bash',{command:'fixture'});
      const headless=await call('bash',{command:'fixture'},{...ctx,hasUI:false});
      console.log(JSON.stringify({blocked,beforeConfirm,allowed,denied,headless,previews,entries}));
    ''', config))
    assert result['blocked']['block'] and result['beforeConfirm'] == 0
    assert result['allowed'] is None and result['denied']['block'] and result['headless']['block']
    assert len(result['previews']) == 2
    assert all('flat reason' in text and 'legacy reason' in text for text in result['previews'])
    assert any(entry['outcome'] == 'observed' for entry in result['entries'])


def test_native_write_preserves_legacy_and_requires_preview_for_removal(tmp_path: Path) -> None:
    result = run_bun(gate_script(tmp_path, '''
      const added={...JSON.parse(before),rules:[{id:'new',text:'fixture',instructions:'Only fixture.'}]};
      const preserved=await call('write',{path:file,content:JSON.stringify(added)}),preservedPreviews=previews.length;
      const changed=structuredClone(added);changed.policies[0].pattern='weaker';
      const modified=await call('write',{path:file,content:JSON.stringify(changed)});
      const removed={rules:added.rules};
      const headless=await call('write',{path:file,content:JSON.stringify(removed)},{...ctx,hasUI:false});
      approval=false;const denied=await call('write',{path:file,content:JSON.stringify(removed)});
      approval=true;const approved=await call('write',{path:file,content:JSON.stringify(removed)});
      console.log(JSON.stringify({preserved,preservedPreviews,modified,headless,denied,approved,previews,unchanged:fs.readFileSync(file,'utf8')===before}));
    '''))
    assert result['preserved'] is None and result['preservedPreviews'] == 0
    assert result['modified']['block'] and result['headless']['block'] and result['denied']['block']
    assert result['approved'] is None and result['unchanged']
    assert all('no-project-memory-local-writes' in preview and 'protection' in preview.lower() for preview in result['previews'])


def test_all_layers_overrides_disabled_and_mixed_containers() -> None:
    result = run_bun('''
      import {mergeLayers,DEFAULT_RULES} from './packages/continual-learning/extensions/guardrail-engine.ts';
      import {evaluateLegacyTools} from './packages/continual-learning/extensions/legacy-harness.ts';
      const policy=(name,pattern)=>({name,tools:['write'],paths:['content'],pattern,reason:pattern});
      const config=mergeLayers([
        {source:'built-in defaults',rules:DEFAULT_RULES},
        {source:'user',policies:[policy('same','outer'),policy('disabled','all')],disabled:['no-interactive-auth-automation','flat-independent'],skillPrompts:{review:{prompt:'outer',target:'system'}}},
        {source:'project',rules:[{id:'flat-independent',bash:'flat',action:'block',message:'keep'}],policies:[policy('same','middle')],disabled:['disabled']},
        {source:'project.local',policies:[policy('same','inner'),policy('disabled','all')],skillPrompts:{review:{prompt:'inner',target:'user'}}}
      ]);
      const evaluate=content=>evaluateLegacyTools(config.legacy,'write',{content});
      console.log(JSON.stringify({config,outer:evaluate('outer'),inner:evaluate('inner'),disabled:evaluate('all')}));
    ''')
    assert not result['config']['errors']
    assert result['outer']['matches'] == [] and result['disabled']['matches'] == []
    assert result['inner']['matches'][0]['source'] == 'project.local'
    assert result['config']['legacy']['skillPrompts']['review']['prompt'] == 'inner'
    assert next(rule for rule in result['config']['rules'] if rule['id'] == 'no-interactive-auth-automation')['enabled'] is False
    assert next(rule for rule in result['config']['rules'] if rule['id'] == 'flat-independent')['enabled'] is False


@pytest.mark.parametrize('target', ['system', 'user'])
def test_legacy_skill_suffix_and_target_coexist_with_flat_guidance(tmp_path: Path, target: str) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      import fs from 'node:fs';import path from 'node:path';
      const {{default:register}}=await import('./packages/continual-learning/extensions/context-guidance.ts');
      const {{extractModelVisibleTexts}}=await import('./packages/continual-learning/extensions/harness-guidance-planner.ts');
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(path.join(cwd,'.pi'));
      fs.writeFileSync(path.join(cwd,'.pi/harness.json'),JSON.stringify({{rules:[{{id:'new',skill:'review',instructions:'flat addition'}}],skillPrompts:{{review:{{prompt:'exact legacy guidance',target:{json.dumps(target)},userMessagePattern:'^approved suffix$'}}}}}}));
      const hooks={{}},entries=[];register({{on:(n,f)=>hooks[n]=f,registerEntryRenderer(){{}},appendEntry:(t,d)=>entries.push(d)}});
      const ctx={{cwd,sessionManager:{{buildContextEntries:()=>[]}}}};
      const event=prompt=>({{prompt,systemPrompt:'base',systemPromptOptions:{{skills:[{{name:'review'}}]}}}});
      const expanded=suffix=>['<skill name="review" location="/fixture/SKILL.md">','approved suffix in body','</skill>','',suffix].join('\\n');
      const positive=await hooks.before_agent_start(event(expanded('approved suffix')),ctx);
      const negative=await hooks.before_agent_start(event(expanded('unrelated')),ctx);
      const plain=await hooks.before_agent_start(event('Read /fixture/SKILL.md approved suffix'),ctx);
      const repeated=await hooks.before_agent_start(event(expanded('approved suffix')),ctx);
      const texts=extractModelVisibleTexts([{{role:'custom',customType:'skill-prompt-guidance',content:'never self-trigger'}}]);
      console.log(JSON.stringify({{positive,negative,plain:plain??null,repeated,texts}}));
    ''')
    assert 'flat addition' in result['positive']['message']['content']
    legacy_text = result['positive'].get('systemPrompt', '') if target == 'system' else result['positive']['message']['content']
    assert 'exact legacy guidance' in legacy_text
    assert 'exact legacy guidance' not in json.dumps(result['negative']) and result['plain'] is None
    assert 'exact legacy guidance' in json.dumps(result['repeated'])
    assert result['texts'] == []


def test_output_artifact_protections_and_invalid_diagnostics_remain_registered(tmp_path: Path) -> None:
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      import fs from 'node:fs';import path from 'node:path';
      const {{default:register}}=await import('./packages/continual-learning/extensions/output-checks.ts');
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(path.join(cwd,'.pi'));
      const file=path.join(cwd,'.pi/harness.json');
      fs.writeFileSync(file,JSON.stringify({{policies:[
        {{name:'output',phase:'output',pattern:'forbidden output',reason:'Correct output'}},
        {{name:'artifact',phase:'artifact',tools:['write'],pattern:'forbidden artifact',reason:'Correct artifact'}},
        {{name:'invalid-output',phase:'output',pattern:'('}},
        {{name:'invalid-artifact',phase:'artifact',tools:['write'],pattern:'('}}
      ]}}));
      fs.writeFileSync(path.join(cwd,'artifact.txt'),'forbidden artifact');
      const hooks={{}},entries=[],repairs=[];register({{on:(n,f)=>hooks[n]=f,registerEntryRenderer(){{}},appendEntry:(t,d)=>entries.push(d),sendMessage:(m,o)=>repairs.push({{m,o}})}});
      const ctx={{cwd}};
      await hooks.message_end({{message:{{role:'assistant',content:[{{type:'text',text:'forbidden output'}}],stopReason:'stop'}}}},ctx);
      await hooks.tool_result({{toolName:'write',input:{{path:'artifact.txt'}},isError:false}},ctx);
      await hooks.message_end({{message:{{role:'assistant',content:[{{type:'text',text:'forbidden output'}}],stopReason:'stop'}}}},ctx);
      console.log(JSON.stringify({{entries,repairs}}));
    ''')
    assert len(result['repairs']) == 2
    assert any('already been shown' in repair['m']['content'] for repair in result['repairs'])
    assert {'output', 'artifact'} <= {entry['phase'] for entry in result['entries'] if entry['status'] == 'violated'}
    assert {'invalid-output', 'invalid-artifact'} <= {entry['policy'] for entry in result['entries'] if entry['status'] == 'unsupported'}
    assert any(entry['status'] == 'repair-exhausted' for entry in result['entries'])


def test_automatic_add_preserves_legacy_only_target_and_reserves_legacy_names(tmp_path: Path) -> None:
    from test_harness_flat_unification import cases, evidence, rule, snapshot
    result = run_bun(f'''
      process.env.PI_CODING_AGENT_DIR={json.dumps(str(tmp_path/'agent'))};
      import fs from 'node:fs';import path from 'node:path';
      const {{applyHarnessOps,validateHarnessPlan}}=await import('./packages/continual-learning/extensions/harness-consolidation.ts');
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(path.join(cwd,'.pi'));const target=path.join(cwd,'.pi/harness.json');
      const base={json.dumps(LEGACY)};fs.writeFileSync(target,JSON.stringify(base));
      const options={{automatic:true,snapshot:{json.dumps(snapshot())},evidence:{json.dumps(evidence())}}};
      const op={{op:'addRule',rule:{json.dumps(rule())},cases:{json.dumps(cases())}}};
      const result=await applyHarnessOps(target,[op],options);
      const collision=validateHarnessPlan({{kind:'harness-consolidation-plan',operations:[{{...op,rule:{{...op.rule,id:base.policies[0].name}}}}],evidence:options.evidence}},{{...options,layers:[{{...base,source:'project.local'}}]}});
      console.log(JSON.stringify({{result,after:JSON.parse(fs.readFileSync(target,'utf8')),collision}}));
    ''')
    assert result['result']['ok'], result
    assert {key: result['after'][key] for key in LEGACY} == LEGACY
    assert result['after']['rules'] == [rule()]
    assert any('conflict' in error or 'already' in error for error in result['collision'])


def test_duplicate_legacy_identity_does_not_lose_any_known_phase_or_tools() -> None:
    result = run_bun('''
      import {mergeLayers} from './packages/continual-learning/extensions/guardrail-engine.ts';
      import {evaluateLegacyTools} from './packages/continual-learning/extensions/legacy-harness.ts';
      const config=mergeLayers([{source:'project',policies:[
        {name:'duplicate',tools:['write'],pattern:'x'},
        {name:'duplicate',phase:'output',pattern:'x'},
        {name:'duplicate',phase:'artifact',tools:['edit'],pattern:'x'}
      ]}]);
      console.log(JSON.stringify({config,write:evaluateLegacyTools(config.legacy,'write',{}),edit:evaluateLegacyTools(config.legacy,'edit',{})}));
    ''')
    assert result['write']['incomplete'] and not result['edit']['incomplete']
    assert {scope['phase'] for scope in result['config']['legacy']['invalidPolicies'][0]['scopes']} == {'tool-call', 'output', 'artifact'}


def test_legacy_override_of_equivalent_builtin_preserves_nearest_action(tmp_path: Path) -> None:
    config = {'policies': [{'name': 'no-interactive-auth-automation', 'tools': ['bash'], 'paths': ['command'], 'pattern': 'npm login', 'action': 'confirm', 'reason': 'User override'}]}
    result = run_bun(gate_script(tmp_path, '''
      const allowed=await call('bash',{command:'npm login'});
      const changed=JSON.parse(before);changed.rules=[{id:'no-interactive-auth-automation',bash:'npm login',action:'block',message:'Explicit flat protection'}];fs.writeFileSync(file,JSON.stringify(changed));
      const blocked=await call('bash',{command:'npm login'});
      console.log(JSON.stringify({allowed,blocked,previews}));
    ''', config))
    assert result['allowed'] is None and len(result['previews']) == 1
    assert result['blocked']['block'] and 'Explicit flat protection' in result['blocked']['reason']


def test_empty_historic_config_is_valid_and_never_blocks_unrelated_tools(tmp_path: Path) -> None:
    result = run_bun(gate_script(tmp_path, '''
      console.log(JSON.stringify({config:resolveHarnessConfig(cwd).config,bash:await call('bash',{command:'printf safe'}),write:await call('write',{path:'note',content:'safe'})}));
    ''', {}))
    assert result['config']['errors'] == []
    assert result['bash'] is None and result['write'] is None


@pytest.mark.parametrize('phase,tools', [('output', None), ('artifact', ['write'])])
def test_duplicate_known_postgeneration_scopes_do_not_block_preexecution(tmp_path: Path, phase: str, tools: list | None) -> None:
    policy = {'name': 'duplicate', 'phase': phase, 'pattern': 'forbidden'}
    if tools is not None:
        policy['tools'] = tools
    result = run_bun(gate_script(tmp_path, '''
      console.log(JSON.stringify({config:resolveHarnessConfig(cwd).config,bash:await call('bash',{command:'safe'}),write:await call('write',{path:'note',content:'safe'})}));
    ''', {'policies': [policy, policy]}))
    assert result['config']['errors']
    assert result['bash'] is None and result['write'] is None


def test_config_recovery_exception_never_bypasses_valid_legacy_protection(tmp_path: Path) -> None:
    config = {'policies': [{'name': 'protect-config', 'tools': ['write'], 'paths': ['content'], 'require': {'path': 'path', 'pattern': 'harness[.]local[.]json$'}, 'pattern': 'FORBIDDEN', 'action': 'block', 'reason': 'Forbidden config content'}]}
    result = run_bun(gate_script(tmp_path, '''
      const candidate={...JSON.parse(before),rules:[{id:'new',text:'FORBIDDEN',instructions:'fixture'}]};
      const gate=await call('write',{path:file,content:JSON.stringify(candidate)});
      console.log(JSON.stringify({gate,unchanged:fs.readFileSync(file,'utf8')===before}));
    ''', config))
    assert result['gate']['block'] and 'Forbidden config content' in result['gate']['reason']
    assert result['unchanged']


@pytest.mark.parametrize('mutation', ["event.input.content='not valid JSON'", "event.input.path='unrelated.txt'", "event.input.path='./.pi/harness.local.json'"])
def test_native_replacement_approval_binds_exact_tool_input(tmp_path: Path, mutation: str) -> None:
    result = run_bun(gate_script(tmp_path, f'''
      const event={{toolName:'write',input:{{path:file,content:'{{"rules":[]}}'}}}};
      const gate=await hooks.tool_call(event,{{...ctx,ui:{{...ctx.ui,confirm:async()=>{{{mutation};return true}}}}}});
      console.log(JSON.stringify({{gate:gate??null,unchanged:fs.readFileSync(file,'utf8')===before}}));
    '''))
    assert result['gate']['block'] and 'changed' in result['gate']['reason']
    assert result['unchanged']
