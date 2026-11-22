"""Merged tests from: test_run_start_guidance_preservation.py, test_run_start_harness_guidance.py, test_run_start_prompt_composition.py, test_run_start_section.py."""

import json
from support import run_bun
import os
from pathlib import Path
import pytest

# --- Merged from test_run_start_guidance_preservation.py ---

def test_malformed_config_preserves_complete_scoped_branch_delivery(tmp_path):
    value = run_bun(f'''
      import fs from 'node:fs';
      import register from './packages/continual-learning/extensions/harness-guidance.ts';
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(cwd+'/.pi');
      fs.writeFileSync(cwd+'/.pi/harness.json','{{malformed');
      const scoped='[harness:saved] Only for subjects matching "needle"; a historical match does not extend this guidance to unrelated tasks.\\nCOMPLETE_SCOPED_GUIDANCE';
      const branch=[{{type:'custom',customType:'harness-guidance-delivery',data:{{entries:[{{id:'saved',revision:'old',status:'active',text:scoped,source:'project'}}]}}}}];
      const hooks={{}},appended=[];register({{on:(n,h)=>hooks[n]=h,registerEntryRenderer(){{}},appendEntry:(customType,data)=>appended.push({{customType,data}})}});
      const options={{sections:{{}},skills:[]}};
      const returned=hooks.before_agent_start({{prompt:'plain',systemPromptOptions:options}},{{cwd,sessionManager:{{getBranch:()=>branch,buildContextEntries:()=>[]}}}});
      console.log(JSON.stringify({{options,returned:returned??null,appended,scoped}}));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    assert value['returned'] is None
    assert value['options']['sections']['harness_guidance'] == value['scoped']
    assert any(entry['data'].get('kind') == 'text-incomplete' for entry in value['appended'])
    delivery = next(entry['data'] for entry in value['appended'] if entry['customType'] == 'harness-guidance-delivery')
    assert delivery['entries'][0]['text'] == value['scoped']
    assert delivery['entries'][0]['status'] == 'active'


def test_overbudget_scan_never_reintroduces_old_unscoped_guidance(tmp_path):
    value = run_bun(f'''
      import fs from 'node:fs';
      import register from './packages/continual-learning/extensions/harness-guidance.ts';
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(cwd+'/.pi');
      fs.writeFileSync(cwd+'/.pi/harness.json',JSON.stringify({{rules:[{{id:'old',text:'needle',instructions:'CURRENT_SCOPED_GUIDANCE'}}]}}));
      const scoped='[harness:valid] Only for subjects matching "other"; a historical match does not extend this guidance to unrelated tasks.\\nVALID_SCOPED_GUIDANCE';
      const branch=[{{type:'custom_message',customType:'harness-guidance',details:{{entries:[{{id:'old',revision:'old',status:'active',text:'UNSCOPED OLD GUIDANCE'}},{{id:'valid',revision:'saved',status:'active',text:scoped}}]}}}}];
      const hooks={{}},appended=[];register({{on:(n,h)=>hooks[n]=h,registerEntryRenderer(){{}},appendEntry:(customType,data)=>appended.push({{customType,data}})}});
      const options={{sections:{{}},skills:[]}};
      hooks.before_agent_start({{prompt:'x'.repeat(2000001),systemPromptOptions:options}},{{cwd,sessionManager:{{getBranch:()=>branch,buildContextEntries:()=>[]}}}});
      console.log(JSON.stringify({{options,appended,scoped}}));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    section = value['options']['sections'].get('harness_guidance', '')
    assert 'UNSCOPED OLD GUIDANCE' not in section
    assert value['scoped'] in section
    notices = [entry['data']['prompt'] for entry in value['appended'] if entry['data'].get('kind') == 'text-incomplete']
    assert any('scope' in notice.lower() for notice in notices)


def test_legacy_skill_guidance_has_task_scope_and_plain_read_does_not_invoke(tmp_path):
    value = run_bun(f'''
      import fs from 'node:fs';
      import register from './packages/continual-learning/extensions/harness-guidance.ts';
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(cwd+'/.pi');
      fs.writeFileSync(cwd+'/.pi/harness.json',JSON.stringify({{skillPrompts:{{review:{{prompt:'LEGACY_BODY',target:'user'}}}}}}));
      const hooks={{}};register({{on:(n,h)=>hooks[n]=h,registerEntryRenderer(){{}},appendEntry(){{}}}});
      const ctx={{cwd,sessionManager:{{getBranch:()=>[],buildContextEntries:()=>[]}}}};
      const start=prompt=>{{const options={{sections:{{}},skills:[{{name:'review'}}]}};const returned=hooks.before_agent_start({{prompt,systemPromptOptions:options}},ctx);return {{options,returned:returned??null}};}};
      console.log(JSON.stringify({{invoked:start('<skill name="review" location="/fixture/SKILL.md">\\nbody\\n</skill>\\n\\ntask'),plain:start('Read /fixture/SKILL.md')}}));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    section = value['invoked']['options']['sections']['harness_guidance']
    assert 'Only for this /skill:review task; retained history does not extend its scope.\nLEGACY_BODY' in section
    assert value['invoked']['returned'] is None
    assert 'harness_guidance' not in value['plain']['options']['sections']

# --- Merged from test_run_start_harness_guidance.py ---

def test_guidance_is_additive_repeated_and_old_injections_are_filtered(tmp_path):
    result = run_bun(f'''
      import fs from 'node:fs';
      import register from './packages/continual-learning/extensions/harness-guidance.ts';
      const cwd={json.dumps(str(tmp_path))};fs.mkdirSync(cwd+'/.pi');
      fs.writeFileSync(cwd+'/.pi/harness.json',JSON.stringify({{rules:[{{id:'text',text:'needle',instructions:'SCOPED_TEXT'}},{{id:'skill',skill:'review',instructions:'SCOPED_SKILL'}}],skillPrompts:{{review:{{prompt:'LEGACY_GUIDANCE',target:'system'}}}}}}));
      const hooks={{}},entries=[];register({{on:(n,h)=>hooks[n]=h,registerEntryRenderer(){{}},appendEntry:(customType,data)=>entries.push({{type:'custom',customType,data}})}});
      const ctx={{cwd,sessionManager:{{buildContextEntries:()=>[],getBranch:()=>entries}}}};
      const start=()=>{{const options={{skills:[{{name:'review'}}],sections:{{other:'OTHER_MARKER'}},promptGuidelines:['EXISTING']}};const returned=hooks.before_agent_start({{prompt:'<skill name="review" location="/fixture/SKILL.md">\\nbody\\n</skill>\\n\\nneedle',systemPromptOptions:options}},ctx);return {{options,returned:returned??null}};}};
      const first=start(),second=start();
      ctx.sessionManager.buildContextEntries=()=>{{throw Error('incomplete')}};
      const incomplete=start();
      const filtered=hooks.context({{messages:[{{role:'custom',customType:'harness-guidance',content:'OLD'}},{{role:'custom',customType:'skill-prompt-guidance',content:'OLD'}},{{role:'custom',customType:'workflow',content:'KEEP'}}]}});
      console.log(JSON.stringify({{first,second,incomplete,entries,filtered}}));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    for run in ('first', 'second', 'incomplete'):
        assert result[run]['returned'] is None
        section = result[run]['options']['sections']['harness_guidance']
        assert all(marker in section for marker in ('SCOPED_TEXT', 'SCOPED_SKILL', 'LEGACY_GUIDANCE')), (run, result)
        assert result[run]['options']['sections']['other'] == 'OTHER_MARKER'
        assert result[run]['options']['promptGuidelines'] == ['EXISTING']
    assert result['filtered']['messages'] == [{'role': 'custom', 'customType': 'workflow', 'content': 'KEEP'}]
    assert any(entry['data'].get('entries') for entry in result['entries'])
    text_events = [entry for entry in result['entries'] if entry['data'].get('kind') == 'text-rule']
    assert len(text_events) == 1

# --- Merged from test_run_start_prompt_composition.py ---

def test_memory_and_goal_compose_with_pi_12_prompt_builder(tmp_path):
    configured = os.environ.get("PI_12_PACKAGE_DIR")
    if not configured:
        pytest.skip("Set PI_12_PACKAGE_DIR to a provisioned Pi 1.2 package directory")
    package = Path(configured).resolve()
    version = json.loads((package / "package.json").read_text())["version"]
    assert version.startswith("1.2."), f"Expected Pi 1.2, got {version}"
    builder = (package / "dist/core/system-prompt.js").as_uri()
    result = run_bun(f'''
      import fs from 'node:fs/promises';
      import registerMemory from './packages/continual-learning/extensions/inject-memory.ts';
      import {{registerGoalEvents}} from './packages/goal/src/events.ts';
      import {{normalizeGoalRecord}} from './packages/goal/src/record.ts';
      import {{normalizeBuildSystemPromptOptions,buildSystemPrompt}} from {json.dumps(builder)};
      const cwd={json.dumps(str(tmp_path / 'project'))};await fs.mkdir(cwd);
      const {{resolveMemoryPaths}}=await import('./packages/continual-learning/extensions/memory-paths.ts');
      const paths=resolveMemoryPaths(cwd);await fs.mkdir(paths.harnessDir,{{recursive:true}});
      await fs.writeFile(paths.harnessDir+'/fixture.md','---\\nname: fixture\\ndescription: DISCOVERY_MARKER\\ntype: project\\n---\\nBODY_NOT_INJECTED');
      const memoryHooks=new Map(); const goalHooks=new Map();
      const api=hooks=>({{on:(n,h)=>hooks.set(n,h),registerCommand(){{}},sendMessage(){{}},appendEntry(){{}},getCommands:()=>[],exec:async()=>({{stdout:'',stderr:'',code:0}})}});
      registerMemory(api(memoryHooks));
      let goal;
      registerGoalEvents({{pi:api(goalHooks),get goal(){{return goal}},acceptGoalSetting(){{}},settings:()=>({{}}),currentUnmet:()=>undefined}});
      const rows=[];
      for(const active of [false,true]) for(const reverse of [false,true]) for(const custom of [false,true]) {{
        goal=active?normalizeGoalRecord({{id:'fixture',objective:'ACTIVE_GOAL_MARKER',status:'active'}}):undefined;
        const options=normalizeBuildSystemPromptOptions({{cwd,contextFiles:[],skills:[],...(custom?{{customPrompt:'CUSTOM_OWNER'}}:{{}}),sections:{{fixture:'OTHER_SECTION'}}}});
        const event={{messageType:'custom',systemPromptOptions:options}};
        const handlers=[memoryHooks.get('before_agent_start'),goalHooks.get('before_agent_start')];
        if(reverse)handlers.reverse();
        const results=[];for(const handler of handlers)results.push(await handler(event,{{cwd,ui:{{notify(){{}}}}}}));
        const wire=buildSystemPrompt(options);
        rows.push({{active,reverse,custom,owner:wire.includes('CUSTOM_OWNER'),discovery:wire.includes('DISCOVERY_MARKER'),auto:wire.includes('After this user task settles'),body:wire.includes('BODY_NOT_INJECTED'),capability:wire.includes('[pi-goal capability]'),memory:wire.includes('Project Memory discovery'),state:wire.includes('ACTIVE_GOAL_MARKER'),forced:results.some(r=>r?.systemPrompt!==undefined),customInjection:results.some(r=>r?.message!==undefined),other:wire.includes('OTHER_SECTION'),forceOption:options.forceSystemPrompt!==undefined}});
      }}
      console.log(JSON.stringify(rows));
    ''', env={'PI_CODING_AGENT_DIR': str(tmp_path / 'agent')})
    assert len(result) == 8
    for row in result:
        assert row['capability'] and row['memory']
        assert row['state'] == row['active']
        assert not row['forced'] and not row['forceOption'] and not row['customInjection']
        assert row['other']
        assert row['owner'] == row['custom']
        assert row['discovery'] and row['auto'] and not row['body']

# --- Merged from test_run_start_section.py ---

def test_missing_sections_fails_clearly_without_mutating_guidelines():
    value = run_bun('''
      import {setRunStartSection} from './packages/continual-learning/extensions/run-start-section.ts';
      const rows=[];
      for(const sections of [undefined,null,[],"invalid"]) {
        const options={customPrompt:'OWNER',promptGuidelines:['KEEP'],...(sections===undefined?{}:{sections})};
        let error='';try {setRunStartSection(options,'required','GUIDANCE')} catch(e) {error=e.message}
        rows.push({error,options});
      }
      console.log(JSON.stringify(rows));
    ''')
    for row in value:
        assert row['error'] == 'Continual-learning requires Pi 1.2 structured prompt sections.'
        assert row['options']['promptGuidelines'] == ['KEEP']
        assert row['options']['customPrompt'] == 'OWNER'
